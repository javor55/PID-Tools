"""
Týmové nasazení webu (docs/cs/milniky.md, M26; návod docs/deployment.md): přihlášení za Cloudflare Access (nebo
jiným proxy s hlavičkou uživatele), pracovní prostory a úlohy po uživatelích, limity a strukturované logy.
Nastavení se čte z proměnných prostředí `PIDTOOLS_*` (`DeployConfig.from_env`); výchozí režim `token` (desktop) se
nemění. Spuštění kontejneru: python -m pidtools.api.serve.
"""
import contextvars
import json
import logging
import os
import re
import sys
import threading
import time
import urllib.request
from dataclasses import dataclass, replace

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from ..app.jobs import FINAL, JobManager

access_log = logging.getLogger("pidtools.access")
job_log = logging.getLogger("pidtools.jobs")

USER = contextvars.ContextVar("pidtools_user", default=None)     # přihlášený uživatel (None = desktop, bez dělení)
CF_HEADER = "Cf-Access-Jwt-Assertion"
SCOPE_USER = "pidtools.user"                                      # klíč ve scope požadavku pro přístupový log
_USER_RE = re.compile(r"[A-Za-z0-9._@+\-]{1,254}")


class AuthError(Exception):
    """Přihlášení se nepovedlo (status 401; 503, když nejdou stáhnout klíče)."""

    def __init__(self, msg, status=401):
        super().__init__(msg)
        self.status = status


class JobLimitError(RuntimeError):
    """Uživatel má už nejvyšší povolený počet čekajících a běžících úloh."""


class ServerBusyError(JobLimitError):
    """Server má už nejvyšší celkový počet úloh (veřejný režim) – 503, klient to zkusí později."""


def _env_bool(v):
    return str(v).strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class DeployConfig:
    auth: str = "token"                    # token (desktop) | cloudflare | header | public (bez přihlášení)
    token: str = ""
    cf_team: str = ""                      # tým Cloudflare Zero Trust: "firma" nebo "firma.cloudflareaccess.com"
    cf_aud: str = ""                       # Application Audience (AUD) tag aplikace
    user_header: str = "X-Forwarded-Email"
    trust_header: bool = False             # bez výslovného souhlasu se hlavička uživatele nepřijme
    ttl: float = 3600.0                    # vypršení pracovního prostoru po nečinnosti [s]
    max_workspaces: int = 20               # celkem
    max_workspaces_user: int = 5
    max_jobs: int = 2                      # souběžně běžících procesů úloh
    max_jobs_user: int = 2                 # čekajících + běžících na uživatele
    max_upload_mb: float = 100.0
    log_level: str = "INFO"
    cors: tuple = ()
    # ---- veřejný režim (auth=public)
    cookie_secure: bool = True             # cookie relace jen přes HTTPS (pro místní http zkoušky vypnout)
    session_ttl: float = 7200.0            # vypršení relace po nečinnosti [s]
    max_sessions: int = 200                # relací celkem
    max_queue: int = 4                     # čekajících úloh celkem (nad běžící); víc = 503
    trust_cf_ip: bool = False              # IP klienta z CF-Connecting-IP (jen za Cloudflare Tunnel)
    rate_limit: float = 300.0              # požadavků na API za minutu a IP
    rate_upload: float = 10.0              # nahrání souboru / spuštění úlohy za minutu a IP

    @property
    def team(self):
        return self.auth != "token"

    @property
    def public(self):
        return self.auth == "public"

    @property
    def mode(self):
        return "public" if self.public else "team" if self.team else "desktop"

    @property
    def max_upload(self):
        return int(self.max_upload_mb * 2 ** 20)

    @classmethod
    def from_env(cls, env=None):
        e = os.environ if env is None else env
        d = cls()
        if e.get("PIDTOOLS_AUTH", "").strip().lower() == "public":
            d = replace(d, ttl=3600.0, max_workspaces=100, max_workspaces_user=3, max_jobs=max(1, os.cpu_count() or 1),
                        max_jobs_user=2, max_upload_mb=20.0)        # veřejné výchozí hodnoty (docs/deployment.md)

        def num(name, default, conv=float):
            raw = e.get(f"PIDTOOLS_{name}", "").strip()
            try:
                return conv(raw) if raw else default
            except ValueError:
                raise ValueError(f"PIDTOOLS_{name}: invalid number {raw!r}") from None

        cfg = cls(
            auth=e.get("PIDTOOLS_AUTH", d.auth).strip().lower() or d.auth, token=e.get("PIDTOOLS_TOKEN", ""),
            cf_team=e.get("PIDTOOLS_CF_TEAM", "").strip(), cf_aud=e.get("PIDTOOLS_CF_AUD", "").strip(),
            user_header=e.get("PIDTOOLS_USER_HEADER", d.user_header).strip() or d.user_header,
            trust_header=_env_bool(e.get("PIDTOOLS_TRUST_USER_HEADER", "")),
            ttl=num("WORKSPACE_TTL", d.ttl), max_workspaces=num("MAX_WORKSPACES", d.max_workspaces, int),
            max_workspaces_user=num("MAX_WORKSPACES_USER", d.max_workspaces_user, int),
            max_jobs=num("MAX_JOBS", d.max_jobs, int), max_jobs_user=num("MAX_JOBS_USER", d.max_jobs_user, int),
            max_upload_mb=num("MAX_UPLOAD_MB", d.max_upload_mb),
            log_level=e.get("PIDTOOLS_LOG_LEVEL", d.log_level).strip().upper() or d.log_level,
            cors=tuple(x.strip() for x in e.get("PIDTOOLS_CORS", "").split(",") if x.strip()),
            cookie_secure=_env_bool(e.get("PIDTOOLS_COOKIE_SECURE", "1")),
            session_ttl=num("SESSION_TTL", d.session_ttl), max_sessions=num("MAX_SESSIONS", d.max_sessions, int),
            max_queue=num("MAX_QUEUE", d.max_queue, int), trust_cf_ip=_env_bool(e.get("PIDTOOLS_TRUST_CF_IP", "")),
            rate_limit=num("RATE_LIMIT", d.rate_limit), rate_upload=num("RATE_UPLOAD", d.rate_upload))
        cfg.validate()
        return cfg

    def validate(self):
        if self.auth not in ("token", "cloudflare", "header", "public"):
            raise ValueError(f"PIDTOOLS_AUTH: unknown mode {self.auth!r} (token, cloudflare, header, public)")
        if self.public and (self.session_ttl <= 0 or self.max_sessions < 1 or self.max_upload_mb <= 0):
            raise ValueError("PIDTOOLS_SESSION_TTL, PIDTOOLS_MAX_SESSIONS and PIDTOOLS_MAX_UPLOAD_MB must be positive")
        if self.auth == "cloudflare" and not (self.cf_team and self.cf_aud):
            raise ValueError("PIDTOOLS_AUTH=cloudflare needs PIDTOOLS_CF_TEAM and PIDTOOLS_CF_AUD")
        if self.auth == "header" and not self.trust_header:
            raise ValueError("PIDTOOLS_AUTH=header trusts a user header sent by the proxy – "
                             "enable it explicitly with PIDTOOLS_TRUST_USER_HEADER=1 (see docs/deployment.md)")
        if self.auth == "token" and not self.token:
            raise ValueError("PIDTOOLS_AUTH=token needs PIDTOOLS_TOKEN")
        if logging.getLevelName(self.log_level) == f"Level {self.log_level}":
            raise ValueError(f"PIDTOOLS_LOG_LEVEL: unknown level {self.log_level!r}")


def _fetch_json(url, timeout=5.0):
    with urllib.request.urlopen(url, timeout=timeout) as r:        # noqa: S310 – https adresa týmu Cloudflare
        return json.loads(r.read().decode("utf-8"))


class CloudflareVerifier:
    """
    Ověření JWT z hlavičky Cf-Access-Jwt-Assertion podle JWKS týmu (https://<tým>.cloudflareaccess.com/cdn-cgi/
    access/certs): podpis RS256, vydavatel, audience tag a platnost. Klíče se drží v paměti (keys_ttl), neznámé
    `kid` (rotace klíčů) vyvolá nové stažení, nejvýš jednou za min_refresh s.
    """

    def __init__(self, team, aud, fetch=None, keys_ttl=3600.0, min_refresh=60.0, leeway=30):
        host = re.sub(r"^https?://", "", team.strip()).strip("/")
        if "." not in host:
            host += ".cloudflareaccess.com"
        self.issuer = f"https://{host}"
        self.certs_url = f"{self.issuer}/cdn-cgi/access/certs"
        self.aud, self.leeway = aud, leeway
        self.keys_ttl, self.min_refresh = keys_ttl, min_refresh
        self._fetch = fetch or _fetch_json
        self._keys, self._loaded, self._tried = {}, 0.0, 0.0   # kid → veřejný klíč, čas stažení a posledního pokusu
        self._lock = threading.Lock()

    def _refresh(self):
        import jwt
        data = self._fetch(self.certs_url)
        keys = {}
        for k in data.get("keys", []):
            try:
                keys[k["kid"]] = jwt.PyJWK(k).key
            except Exception:                                   # noqa: BLE001 – nepoužitelný klíč se přeskočí
                continue
        if not keys:
            raise ValueError("no usable keys")
        self._keys, self._loaded = keys, time.time()

    def _key(self, kid):
        now = time.time()
        with self._lock:
            if (now - self._loaded > self.keys_ttl or kid not in self._keys) and now - self._tried >= self.min_refresh:
                self._tried = now                             # stažení nejvýš jednou za min_refresh (i při výpadku)
                try:
                    self._refresh()
                except Exception as ex:                       # noqa: BLE001
                    if not self._keys:
                        raise AuthError(f"cannot load signing keys: {type(ex).__name__}", 503) from None
            if not self._keys:
                raise AuthError("cannot load signing keys", 503)
            if kid not in self._keys:
                raise AuthError("unknown signing key")
            return self._keys[kid]

    def verify(self, token):
        """Uživatel (e-mail, u servisního tokenu common_name) z platného JWT, jinak AuthError."""
        import jwt
        try:
            kid = jwt.get_unverified_header(token).get("kid")
            claims = jwt.decode(token, self._key(kid), algorithms=["RS256"], audience=self.aud, issuer=self.issuer,
                                leeway=self.leeway, options={"require": ["exp", "iss", "aud"]})
        except AuthError:
            raise
        except jwt.PyJWTError as ex:
            raise AuthError(f"invalid token: {type(ex).__name__}") from None
        user = claims.get("email") or claims.get("common_name") or claims.get("sub")
        if not user or not _USER_RE.fullmatch(str(user)):
            raise AuthError("token without a usable user")
        return str(user).lower()


def make_auth(cfg, verifier=None):
    """Závislost FastAPI: určí uživatele, uloží ho (contextvar + scope pro log) nebo odpoví 401."""
    if cfg.public:
        from .public import public_auth
        return public_auth
    verifier = verifier or (CloudflareVerifier(cfg.cf_team, cfg.cf_aud) if cfg.auth == "cloudflare" else None)

    async def auth(request: Request):
        try:
            if cfg.auth == "cloudflare":
                tok = request.headers.get(CF_HEADER)
                if not tok:
                    raise AuthError("missing Cloudflare Access token")
                from starlette.concurrency import run_in_threadpool
                user = await run_in_threadpool(verifier.verify, tok)       # může stahovat klíče (síť)
            else:
                user = request.headers.get(cfg.user_header, "").strip().lower()
                if not _USER_RE.fullmatch(user):
                    raise AuthError("missing user header")
        except AuthError as ex:
            raise HTTPException(ex.status, str(ex)) from None
        USER.set(user)
        request.scope[SCOPE_USER] = user
    return auth


class TeamJobs(JobManager):
    """Úlohy s vlastníkem: limit čekajících + běžících na uživatele a log začátku a konce úlohy."""

    def __init__(self, max_parallel=2, max_per_user=2, max_total=0, gate=None, **kw):
        self.max_per_user = int(max_per_user)
        self.scrub = bool(max_total)                        # veřejný režim: v chybě úlohy bez cest k souborům
        self.max_total = int(max_total)                     # čekajících + běžících celkem (0 = bez limitu)
        self.gate = gate                                    # veřejný režim: povolení spuštění po IP (limit četnosti)
        self._owners = {}                                   # id úlohy → uživatel
        self._team_lock = threading.Lock()
        super().__init__(max_parallel=max_parallel, **kw)

    def submit(self, fn, *args, **kwargs):
        user = USER.get()
        with self._team_lock:
            if user is not None and self.max_per_user and self.active(user) >= self.max_per_user:
                raise JobLimitError(user)
            if self.max_total and self.active_total() >= self.max_total:
                raise ServerBusyError("busy")
            if self.gate is not None and not self.gate():
                raise JobLimitError("rate")
            jid = super().submit(fn, *args, **kwargs)
            self._owners[jid] = user
            for k in [k for k in self._owners if k not in self._jobs]:      # zapomenuté úlohy
                del self._owners[k]
        job_log.info("job submit id=%s user=%s fn=%s", jid, user or "-", getattr(fn, "__name__", "?"))
        return jid

    def owner(self, jid):
        return self._owners.get(jid)

    def active(self, user):
        with self._lock:
            return sum(self._owners.get(j.id) == user and j.state not in FINAL for j in self._jobs.values())

    def status(self, jid):
        st = super().status(jid)
        if self.scrub and st.get("error"):
            st = dict(st, error=scrub(st["error"]))
        return st

    def active_total(self):
        with self._lock:
            return sum(j.state not in FINAL for j in self._jobs.values())

    def drop_owner(self, user):
        """Zrušení všech úloh uživatele (vypršení relace)."""
        for jid in [j for j, u in list(self._owners.items()) if u == user]:
            try:
                self.cancel(jid)
            except KeyError:
                pass
            self._owners.pop(jid, None)

    def _who(self, job):
        return self._owners.get(job.id) or USER.get() or "-"

    def _start(self, job):
        super()._start(job)
        job_log.info("job start id=%s user=%s fn=%s", job.id, self._who(job), getattr(job.fn, "__name__", "?"))

    def _finish(self, job, state, progress=None, error=None):
        super()._finish(job, state, progress, error)
        sec = job.finished - (job.started or job.created)
        job_log.info("job end id=%s user=%s state=%s seconds=%.2f%s", job.id, self._who(job), job.state, sec,
                     f" error={job.error!r}" if job.error else "")


def make_jobs(team, max_jobs):
    """Správce úloh: v týmovém režimu s vlastníky a limity; ve veřejném i s celkovým limitem (běžící + fronta)."""
    if team is None:
        return JobManager(max_parallel=max_jobs)
    return TeamJobs(max_jobs, team.max_jobs_user, max_total=max_jobs + team.max_queue if team.public else 0)


def visible(jobs, jid):
    """Úloha je viditelná přihlášenému uživateli (jeho vlastní); bez vlastníků (desktop) vždy."""
    return not isinstance(jobs, TeamJobs) or jobs.owner(jid) == USER.get()


_PATH_RE = re.compile(r"(?:[A-Za-z]:\\[^\s'\"]+|(?<![\w.])/(?:[\w.\-]+/)+[\w.\-]*)")


def scrub(text):
    """Text chyby bez cest k souborům (veřejný režim: odpověď nesmí prozradit strukturu serveru)."""
    return _PATH_RE.sub("<path>", str(text)) if text else text


def _clean(s):
    return str(s).replace("\n", "\\n").replace("\r", "\\r")


class AccessLog:
    """ASGI middleware: jeden řádek na požadavek (uživatel, metoda, cesta, stav, trvání)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        t0, status = time.perf_counter(), [500]

        async def send_(msg):
            if msg["type"] == "http.response.start":
                status[0] = msg["status"]
            await send(msg)
        try:
            await self.app(scope, receive, send_)
        finally:
            lvl = logging.DEBUG if scope["path"] == "/health" else logging.INFO
            access_log.log(lvl, "user=%s method=%s path=%s status=%d ms=%.1f", scope.get(SCOPE_USER) or "-",
                           scope["method"], _clean(scope["path"]), status[0], (time.perf_counter() - t0) * 1000)


def install(app, cfg, on_expire=None):
    """Týmový režim: limit úloh jako 429 (celkový limit veřejného režimu 503), veřejná vrstva a přístupový log
    (nejvnější vrstva); bez týmu nic."""
    if cfg is None:
        return

    @app.exception_handler(JobLimitError)
    async def _job_limit(_request, ex):
        if isinstance(ex, ServerBusyError):
            return JSONResponse({"detail": "pub_busy"}, status_code=503, headers={"Retry-After": "30"})
        return JSONResponse({"detail": "job limit reached"}, status_code=429)

    if cfg.public:
        from .public import CLIENT_IP, PublicGate, RateLimiter, Sessions
        app.state.sessions = Sessions(cfg.session_ttl, cfg.max_sessions, on_expire)
        job_rate = RateLimiter(cfg.rate_upload, burst=max(1.0, cfg.rate_upload / 2))      # spuštění úloh po IP
        app.state.jobs.gate = lambda: job_rate.allow(CLIENT_IP.get())
        app.add_middleware(PublicGate, cfg=cfg, sessions=app.state.sessions, api_prefix="/api/v1")
    app.add_middleware(AccessLog)


def configure_logging(level="INFO", stream=None):
    """Logy `pidtools.*` na stderr jako text (čas, úroveň, zdroj, klíč=hodnota)."""
    lg = logging.getLogger("pidtools")
    lg.setLevel(level)
    if not any(getattr(h, "_pidtools", False) for h in lg.handlers):
        h = logging.StreamHandler(stream or sys.stderr)
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        h._pidtools = True
        lg.addHandler(h)


def app_from_env(env=None):
    """Aplikace podle proměnných prostředí (kontejner)."""
    from . import create_app
    cfg = DeployConfig.from_env(env)
    configure_logging(cfg.log_level)
    if cfg.team:
        return create_app(team=cfg, cors_origins=cfg.cors)
    return create_app(token=cfg.token, cors_origins=cfg.cors, workspace_ttl=cfg.ttl,
                      max_workspaces=cfg.max_workspaces, max_jobs=cfg.max_jobs)
