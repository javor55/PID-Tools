"""
Veřejný režim webu (`PIDTOOLS_AUTH=public`, docs/deployment.md): bez přihlášení, každý prohlížeč dostane anonymní relaci
(náhodné ID v cookie `HttpOnly; Secure; SameSite=Strict`), která funguje jako „uživatel“ pro vlastnictví prostorů a úloh.
Na serveru se nic neukládá na disk (nastavení jen v paměti relace) a relace po nečinnosti zanikne i s prostory a úlohami.
Tady jsou: relace, jednoduchý token bucket po IP, ASGI vrstva (relace, limit těla, kontrola původu, limity požadavků)
a hlavičky zabezpečení (ty platí ve všech režimech).
"""
import contextvars
import hashlib
import json
import re
import secrets
import threading
import time
from urllib.parse import urlsplit

from fastapi import HTTPException

from . import deploy

COOKIE = "pidtools_sid"
_SID_RE = re.compile(r"[A-Za-z0-9_\-]{43}")
CLIENT_IP = contextvars.ContextVar("pidtools_client_ip", default="-")
UNSAFE = ("POST", "PUT", "PATCH", "DELETE")


class SessionLimitError(RuntimeError):
    """Server má už nejvyšší počet relací."""


class Sessions:
    """Anonymní relace v paměti: ID → čas posledního požadavku; vypršení po nečinnosti volá `on_expire(sid)`."""

    def __init__(self, ttl_s=7200.0, max_count=200, on_expire=None, clock=time.time):
        self.ttl_s, self.max_count, self.on_expire, self._clock = float(ttl_s), int(max_count), on_expire, clock
        self._d = {}
        self._lock = threading.Lock()
        self._swept = 0.0

    def sweep(self, now=None, force=False):
        now = self._clock() if now is None else now
        with self._lock:
            if not force and now - self._swept < min(30.0, self.ttl_s / 2):
                return []
            self._swept = now
            gone = [k for k, t in self._d.items() if now - t > self.ttl_s]
            for k in gone:
                del self._d[k]
        for k in gone:
            if self.on_expire:
                self.on_expire(k)
        return gone

    def touch(self, sid):
        """Obnoví relaci a vrátí True; neznámá nebo vypršelá → False."""
        now = self._clock()
        self.sweep(now)
        with self._lock:
            if sid in self._d and now - self._d[sid] <= self.ttl_s:
                self._d[sid] = now
                return True
        return False

    def create(self):
        """Nová relace (ID 256 bitů); při plném počtu SessionLimitError."""
        self.sweep(force=True)
        with self._lock:
            if len(self._d) >= self.max_count:
                raise SessionLimitError
            sid = secrets.token_urlsafe(32)
            self._d[sid] = self._clock()
            return sid

    def __len__(self):
        return len(self._d)


class RateLimiter:
    """Token bucket po klíči (IP): `per_min` požadavků za minutu, rázem nejvýš `burst`; paměť omezená čištěním."""

    def __init__(self, per_min, burst=None, clock=time.monotonic, max_keys=10000):
        self.rate = float(per_min) / 60.0
        self.burst = float(burst if burst is not None else max(1.0, per_min / 6.0))
        self._clock, self.max_keys = clock, int(max_keys)
        self._d = {}                               # klíč → (tokeny, čas)
        self._lock = threading.Lock()

    def allow(self, key):
        if self.rate <= 0:
            return True
        now = self._clock()
        with self._lock:
            tok, t = self._d.get(key, (self.burst, now))
            tok = min(self.burst, tok + (now - t) * self.rate)
            ok = tok >= 1.0
            if ok:
                tok -= 1.0
            if len(self._d) >= self.max_keys and key not in self._d:
                full = [k for k, (a, b) in self._d.items() if min(self.burst, a + (now - b) * self.rate) >= self.burst]
                for k in full or list(self._d)[: max(1, self.max_keys // 10)]:
                    del self._d[k]
            self._d[key] = (tok, now)
            return ok


def fingerprint(sid):
    """Krátký otisk ID relace pro logy (ID samo je tajné)."""
    return "s-" + hashlib.sha256(sid.encode()).hexdigest()[:8]


def client_ip(scope, trust_cf):
    """IP klienta: hlavička CF-Connecting-IP jen s výslovným souhlasem (za Cloudflare Tunnel), jinak protistrana spojení."""
    if trust_cf:
        for k, v in scope.get("headers") or []:
            if k == b"cf-connecting-ip":
                ip = v.decode("latin-1").strip()
                if re.fullmatch(r"[0-9A-Fa-f:.]{2,45}", ip):
                    return ip
    c = scope.get("client")
    return c[0] if c else "-"


async def _respond(send, status, detail, headers=()):
    body = json.dumps({"detail": detail}).encode()
    await send({"type": "http.response.start", "status": status, "headers": [
        (b"content-type", b"application/json"), (b"content-length", str(len(body)).encode()), *headers]})
    await send({"type": "http.response.body", "body": body})


def _cookie_of(scope):
    for k, v in scope.get("headers") or []:
        if k == b"cookie":
            for part in v.decode("latin-1").split(";"):
                name, _, val = part.strip().partition("=")
                if name == COOKIE:
                    return val
    return ""


class PublicGate:
    """
    ASGI vrstva veřejného režimu: limit požadavků po IP (obecný a přísnější pro velká těla), limit velikosti těla,
    kontrola `Origin` u změn (ochrana proti CSRF vedle SameSite=Strict), anonymní relace v cookie a USER pro API.
    """

    def __init__(self, app, cfg, sessions, api_prefix):
        self.app, self.cfg, self.sessions, self.prefix = app, cfg, sessions, api_prefix
        self.general = RateLimiter(cfg.rate_limit)
        self.uploads = RateLimiter(cfg.rate_upload, burst=max(1.0, cfg.rate_upload / 2))
        self.creations = RateLimiter(10.0, burst=5.0)             # nové relace po IP (zabrání zaplnění tabulky relací)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        cfg, path, method = self.cfg, scope["path"], scope["method"]
        ip = client_ip(scope, cfg.trust_cf_ip)
        CLIENT_IP.set(ip)
        is_api = path.startswith(self.prefix + "/") or path.startswith(("/workspaces", "/jobs"))
        gated = is_api and path != self.prefix + "/health"
        if gated:
            if not self.general.allow(ip):
                return await _respond(send, 429, "pub_rate", [(b"retry-after", b"10")])
            hdr = dict(scope.get("headers") or [])
            if method in UNSAFE:
                if self._cross_origin(hdr):
                    return await _respond(send, 403, "cross-origin request")
                clen = hdr.get(b"content-length")
                try:
                    n = int(clen) if clen is not None else 0
                except ValueError:
                    return await _respond(send, 400, "bad content-length")
                if n > cfg.max_upload:
                    return await _respond(send, 413, "data_too_big")
                if clen is None and b"transfer-encoding" in hdr:
                    return await _respond(send, 411, "content-length required")
                if n >= 256 * 1024 and not self.uploads.allow(ip):
                    return await _respond(send, 429, "pub_rate", [(b"retry-after", b"30")])
        sid = _cookie_of(scope)
        sid = sid if _SID_RE.fullmatch(sid) and self.sessions.touch(sid) else ""
        fresh = False
        if not sid and gated:
            if not self.creations.allow(ip):
                return await _respond(send, 429, "pub_rate", [(b"retry-after", b"30")])
            try:
                sid, fresh = self.sessions.create(), True
            except SessionLimitError:
                return await _respond(send, 503, "pub_busy", [(b"retry-after", b"60")])
        if sid:
            deploy.USER.set(sid)
            scope[deploy.SCOPE_USER] = fingerprint(sid)

        async def send_(msg):
            if fresh and msg["type"] == "http.response.start":
                flags = ["HttpOnly", "SameSite=Strict", "Path=/", f"Max-Age={int(cfg.session_ttl)}"]
                if cfg.cookie_secure:
                    flags.append("Secure")
                cookie = f"{COOKIE}={sid}; {'; '.join(flags)}".encode()
                msg = dict(msg, headers=[*msg["headers"], (b"set-cookie", cookie)])
            await send(msg)
        await self.app(scope, receive, send_)

    @staticmethod
    def _cross_origin(hdr):
        origin = hdr.get(b"origin")
        if origin is None:
            return False
        o = origin.decode("latin-1")
        host = (hdr.get(b"host") or b"").decode("latin-1")
        try:
            return o == "null" or urlsplit(o).netloc.lower() != host.lower()
        except ValueError:
            return True


async def public_auth():
    """Závislost FastAPI veřejného režimu: bez relace (cookie vydá ASGI vrstva) 401."""
    if deploy.USER.get() is None:
        raise HTTPException(401, "no session")


CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
       "font-src 'self' data:; connect-src 'self'; worker-src 'self' blob:; object-src 'none'; frame-ancestors 'none'; "
       "base-uri 'none'; form-action 'self'")
SECURITY_HEADERS = {
    "content-security-policy": CSP, "x-content-type-options": "nosniff", "referrer-policy": "no-referrer",
    "x-frame-options": "DENY", "cross-origin-opener-policy": "same-origin",
    "permissions-policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=(), interest-cohort=()",
}


# Hostitel náhledu protokolu (frontend/public/report-host.html): protokol nese skripty Plotly a vlastní styly, proto má
# vlastní CSP – ale v sandboxu bez přístupu k aplikaci a k síti (žádné connect-src, jen data: obrázky).
REPORT_HOST = "/report-host.html"
REPORT_CSP = ("default-src 'none'; script-src 'unsafe-inline' https://cdn.plot.ly; style-src 'unsafe-inline'; "
              "img-src data: blob:; font-src data:; sandbox allow-scripts allow-modals; frame-ancestors 'self'; "
              "base-uri 'none'; form-action 'none'")


class SecurityHeaders:
    """ASGI: bezpečnostní hlavičky na každé odpovědi (co nastavila cesta sama, např. logo, se nepřepisuje)."""

    def __init__(self, app, hsts=False, api_prefix="/api/v1", no_store=False):
        self.app, self.prefix, self.no_store = app, api_prefix, no_store
        self.extra = {"strict-transport-security": "max-age=31536000"} if hsts else {}

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        api = scope["path"].startswith(self.prefix + "/")
        host = scope["path"] == REPORT_HOST
        docs = scope["path"] in ("/docs", "/redoc")          # Swagger UI / ReDoc (jen mimo veřejný režim) potřebují CDN

        async def send_(msg):
            if msg["type"] == "http.response.start":
                have = {k.lower() for k, _ in msg["headers"]}
                add = {**SECURITY_HEADERS, **self.extra}
                if docs:
                    del add["content-security-policy"]
                if host:
                    add.update({"content-security-policy": REPORT_CSP, "x-frame-options": "SAMEORIGIN"})
                if self.no_store and api:
                    add["cache-control"] = "no-store"
                msg = dict(msg, headers=[*msg["headers"], *((k.encode(), v.encode()) for k, v in add.items()
                                                            if k.encode() not in have)])
            await send(msg)
        await self.app(scope, receive, send_)
