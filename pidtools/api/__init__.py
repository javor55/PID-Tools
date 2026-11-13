"""
API nad aplikační vrstvou (FastAPI): pracovní prostory, texty, dlouhé úlohy s průběhem (docs/cs/milniky.md, M6).

Bezpečnost pro desktop: server poslouchá jen na 127.0.0.1 a vyžaduje token (hlavička `Authorization: Bearer …`
nebo `X-PID-Token`); bez tokenu odpoví jen /health. CORS jen pro zadané původy (okno aplikace).
Spuštění: python -m pidtools.api --port 8765 --token TAJNE
Týmový web (M26): přihlášení za Cloudflare Access, pracovní prostory a úlohy po uživatelích – deploy.py.
Rozhraní je popsané v openapi.json vedle tohoto souboru (generované; test hlídá, že odpovídá kódu).

Stabilní cesty mají prefix `/api/v1` (plán v2, kap. 7); stejné cesty bez prefixu jsou dočasné aliasy pro starší klienty
(desktop, skripty) – v OpenAPI nejsou a po vydání verze 4.0 zaniknou. Změna bez zpětné kompatibility = nová verze `/api/v2`.
"""
import asyncio
import contextvars
import hmac
import json
import re
import weakref
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .. import __version__, i18n
from ..app import appsettings as aps
from ..app.autosave import NullUserData, UserData
from ..app.jobs import FINAL
from ..controllers import Library
from . import (analysis, apc, apc_loops, apc_more, appsettings, audit, controllers, data, deploy, guide, journal,
               mapping, model, opcua, projects, sources, triage, tuning, tuning_profile)
from .common import JobInfo
from .data import WorkspaceInfo, info
from .public import SecurityHeaders
from .store import WorkspaceStore


class Health(BaseModel):
    status: str
    version: str


class Config(BaseModel):
    """Co potřebuje rozhraní vědět o nasazení: režim (desktop / team / public), limit nahrání a doba relace."""
    mode: str
    max_upload_mb: float
    session_ttl_min: float | None = None            # jen veřejný režim: relace zanikne po tolika minutách nečinnosti


_LANG = contextvars.ContextVar("pidtools_lang", default=i18n.DEFAULT_LANG)


def _request_lang(request):
    """Jazyk textů odpovědi: ?lang=cs, jinak hlavička Accept-Language, jinak výchozí."""
    q = request.query_params.get("lang")
    if q in i18n.TEXTS:
        return q
    for part in request.headers.get("accept-language", "").split(","):
        code = part.strip()[:2].lower()
        if code in i18n.TEXTS:
            return code
    return i18n.DEFAULT_LANG


API_PREFIX = "/api/v1"
UI_DIR = Path(__file__).resolve().parent / "ui"                      # sestavené rozhraní (frontend: npm run build)
FONTS_DIR = Path(__file__).resolve().parents[2] / "static" / "fonts"  # přibalené fonty IBM Plex (OFL)


def _mount_static(app):
    """Fonty a sestavené rozhraní – až za endpointy API (ty mají přednost)."""
    if FONTS_DIR.is_dir():
        app.mount("/fonts", StaticFiles(directory=FONTS_DIR), name="fonts")
    if (UI_DIR / "index.html").exists():
        app.mount("/", StaticFiles(directory=UI_DIR, html=True), name="ui")


def _serialize_workspaces(app):
    """
    Požadavky na jeden pracovní prostor jeden po druhém: prostor není stavěný na souběh (změna nastavení během
    simulace) a souběžné výpočty se přetahují o GIL – dvojice ukazatele + křivky téže simulace trvala souběžně
    několikanásobně déle než po sobě, kdy druhý požadavek vezme výsledek z mezipaměti. Úlohy běží v procesech.
    """
    ws_locks = weakref.WeakKeyDictionary()      # {event loop: {prostor: zámek}} – zámek asyncio patří ke smyčce

    @app.middleware("http")
    async def workspace_mw(request, call_next):
        m = re.match(rf"(?:{API_PREFIX})?/workspaces/([^/]+)/", request.url.path)
        if not m:
            return await call_next(request)
        locks = ws_locks.setdefault(asyncio.get_running_loop(), {})
        async with locks.setdefault(m.group(1), asyncio.Lock()):
            resp = await call_next(request)
        if request.method not in ("GET", "HEAD", "OPTIONS") and resp.status_code < 400 and not request.url.path.endswith("/autosave"):
            try:
                app.state.store.get(m.group(1)).touch()      # počítadlo změn (neuloženo, záchranná kopie)
            except KeyError:
                pass
        return resp


def _opt(team, names, defaults):
    """Hodnoty z týmového nastavení, bez něj výchozí."""
    return tuple(defaults) if team is None else tuple(getattr(team, n) for n in names)


def _routers(project, jobs, team, library, settings, userdata):
    """Všechny routery API (jeden prostor = jedna cesta `/workspaces/{wid}/…`)."""
    max_upload = _opt(team, ["max_upload"], [data.MAX_UPLOAD])
    public = team is not None and team.public
    return [data.router(project, *max_upload),
            projects.router(project, appsettings.remember(userdata), max_upload[0] if public else projects.MAX_PROJECT),
            projects.pending_router(team is None), appsettings.router(project, settings, userdata, library, public),
            sources.router(project, *max_upload), mapping.router(project), model.router(project, jobs),
            tuning.router(project, jobs), tuning_profile.router(project), analysis.router(project), audit.router(project), apc.router(project, jobs),
            apc_more.router(project), apc_loops.router(project, jobs), opcua.router(project, jobs, not public), guide.router(project),
            triage.router(project, jobs), controllers.router(library, team is None),
            controllers.loop_router(project, library), journal.router(project, settings, public)]


def _stores(public, config_dir, data_dir):
    """Nastavení a uživatelská data: veřejný režim nic neukládá na disk (nastavení v paměti relace, bez záchranné kopie)."""
    if public:
        return aps.MemorySettingsStore(), NullUserData()
    return aps.SettingsStore(config_dir), UserData(data_dir)


def _is_public(team):
    return team is not None and team.public


def _security(app, team):
    """Bezpečnostní hlavičky ve všech režimech (nejvnější vrstva); HSTS a no-store jen ve veřejném režimu."""
    public = team is not None and team.public
    app.add_middleware(SecurityHeaders, hsts=public and team.cookie_secure, api_prefix=API_PREFIX, no_store=public)


def _docs(public):
    """Veřejný režim bez popisu rozhraní (OpenAPI, Swagger, ReDoc)."""
    return dict(docs_url=None, redoc_url=None, openapi_url=None) if public else {}


def _expirer(app, jobs, settings):
    def expire(sid):
        """Relace vypršela: její prostory, úlohy a nastavení se uvolní."""
        app.state.store.drop_owner(sid)
        jobs.drop_owner(sid)
        settings.drop(sid)
    return expire


def _config(team):
    if team is None:
        return Config(mode="desktop", max_upload_mb=data.MAX_UPLOAD / 2 ** 20)
    return Config(mode=team.mode, max_upload_mb=team.max_upload_mb, session_ttl_min=team.session_ttl / 60 if team.public else None)


def _config_route(system, auth, team):
    @system.get("/config", response_model=Config, tags=["system"], dependencies=[Depends(auth)])
    def config():
        """Režim nasazení a limity pro rozhraní (ve veřejném režimu tímto voláním prohlížeč dostane relaci)."""
        return _config(team)


def _include(app, routers, system, auth):
    """Stabilní cesty `/api/v1` (v OpenAPI) a dočasný alias bez prefixu pro starší klienty (skrytý v OpenAPI)."""
    for r in routers:
        app.include_router(r, prefix=API_PREFIX, dependencies=[Depends(auth)])
        app.include_router(r, include_in_schema=False, dependencies=[Depends(auth)])
    app.include_router(system, prefix=API_PREFIX)
    app.include_router(system, include_in_schema=False)


def create_app(token=None, cors_origins=(), workspace_ttl=3600.0, max_workspaces=20, max_jobs=2, team=None,
               verifier=None, controllers_dir=None, config_dir=None, data_dir=None):
    """
    Aplikace FastAPI. token=None jen pro testy a vývoj (bez kontroly). team (deploy.DeployConfig s přihlášením
    cloudflare / header) zapne týmový režim: uživatel místo tokenu, prostory a úlohy po uživatelích, limity, logy;
    verifier (jen testy) nahradí ověřování JWT; config_dir / data_dir = složka nastavení aplikace a uživatelských dat
    (záchranná kopie, nedávné projekty). controllers_dir = složka vlastních regulátorů (výchozí uživatelská složka,
    proměnná PIDTOOLS_CONTROLLERS_DIR); v týmovém režimu je knihovna jen ke čtení.
    """
    workspace_ttl, max_workspaces, max_jobs = _opt(team, ("ttl", "max_workspaces", "max_jobs"),
                                                   (workspace_ttl, max_workspaces, max_jobs))
    jobs = deploy.make_jobs(team, max_jobs)

    @asynccontextmanager
    async def lifespan(_app):
        yield
        jobs.shutdown()                      # běžící procesy úloh se ukončí se serverem

    public = _is_public(team)
    app = FastAPI(title="PID Tools API", version=__version__, lifespan=lifespan, **_docs(public),
                  description="Identification, tuning and simulation of PIDConL loops (PCS 7).")
    app.state.store = WorkspaceStore(workspace_ttl, max_workspaces)
    i18n.set_lang_provider(_LANG.get)            # texty výpočtů (doporučení, protokol) v jazyce požadavku

    @app.middleware("http")
    async def lang_mw(request, call_next):
        tok = _LANG.set(_request_lang(request))
        try:
            return await call_next(request)
        finally:
            _LANG.reset(tok)

    _serialize_workspaces(app)

    app.state.jobs = jobs
    if cors_origins:
        app.add_middleware(CORSMiddleware, allow_origins=list(cors_origins), allow_methods=["*"],
                           allow_headers=["*"])

    def token_auth(authorization: str | None = Header(None), x_pid_token: str | None = Header(None)):
        if token is None:
            return
        got = x_pid_token or (authorization[7:] if authorization and authorization.startswith("Bearer ") else "")
        if not hmac.compare_digest(str(got), str(token)):
            raise HTTPException(401, "invalid token")

    auth = token_auth if team is None else deploy.make_auth(team, verifier)

    def project(wid: str):
        try:
            return app.state.store.get(wid, owner=deploy.USER.get())     # v týmovém režimu jen vlastní prostor
        except KeyError:
            raise HTTPException(404, "workspace not found") from None

    def workspace(wid: str):
        """Aktivní smyčka projektu."""
        return project(wid).state

    def job(jid: str):
        try:
            if not deploy.visible(jobs, jid):
                raise KeyError(jid)
            return app.state.jobs.status(jid)
        except KeyError:
            raise HTTPException(404, "job not found") from None

    app.state.workspace = workspace          # pro další moduly API (M7–M11)
    library = Library(controllers_dir)
    settings, userdata = _stores(public, config_dir, data_dir)
    routers = _routers(project, jobs, team, library, settings, userdata)
    system = APIRouter()

    @system.get("/health", response_model=Health, tags=["system"])
    def health():
        return Health(status="ok", version=__version__)

    _config_route(system, auth, team)

    @system.get("/i18n/{lang}", response_model=dict[str, str], tags=["system"], dependencies=[Depends(auth)])
    def texts(lang: str):
        if lang not in i18n.TEXTS:
            raise HTTPException(404, "language not found")
        return i18n.TEXTS[lang]

    @system.post("/workspaces", response_model=WorkspaceInfo, tags=["workspace"], dependencies=[Depends(auth)])
    def ws_create():
        wid, proj = app.state.store.create(owner=deploy.USER.get(),
                                           max_per_owner=_opt(team, ["max_workspaces_user"], [None])[0],
                                           defaults=appsettings.new_defaults(settings.load(deploy.USER.get()), library))
        return info(wid, proj.state)

    @system.get("/workspaces/{wid}", response_model=WorkspaceInfo, tags=["workspace"], dependencies=[Depends(auth)])
    def ws_get(wid: str):
        return info(wid, workspace(wid))

    @system.delete("/workspaces/{wid}", status_code=204, tags=["workspace"], dependencies=[Depends(auth)])
    def ws_delete(wid: str):
        if not app.state.store.delete(wid, owner=deploy.USER.get()):
            raise HTTPException(404, "workspace not found")

    @system.get("/jobs/{jid}", response_model=JobInfo, tags=["jobs"], dependencies=[Depends(auth)])
    def job_get(jid: str):
        return JobInfo(**job(jid))

    @system.post("/jobs/{jid}/cancel", response_model=JobInfo, tags=["jobs"], dependencies=[Depends(auth)])
    def job_cancel(jid: str):
        job(jid)
        app.state.jobs.cancel(jid)
        return JobInfo(**job(jid))

    @system.get("/jobs/{jid}/result", tags=["jobs"], dependencies=[Depends(auth)])
    def job_result(jid: str):
        """Výsledek hotové úlohy jako JSON (u úloh nad pracovním prostorem jen vrácená hodnota metody)."""
        st = job(jid)
        if st["state"] != "done":
            raise HTTPException(409, f"job {st['state']}")
        res = app.state.jobs.result(jid)
        if isinstance(res, dict) and {"result", "state", "settings"} <= set(res):
            res = res["result"]
        return data._plain(res)

    @system.get("/jobs/{jid}/events", tags=["jobs"], dependencies=[Depends(auth)],
             responses={200: {"content": {"text/event-stream": {}}, "description": "JobInfo as server-sent events"}})
    async def job_events(jid: str, request: Request):
        """Průběh úlohy jako server-sent events (JobInfo při každé změně, konec u hotové / zrušené úlohy)."""
        job(jid)

        async def gen():
            last = None
            while True:
                st = app.state.jobs.status(jid)
                cur = (st["state"], round(st["progress"], 3), st["text"])
                if cur != last:
                    yield f"data: {json.dumps(JobInfo(**st).model_dump())}\n\n"
                    last = cur
                if st["state"] in FINAL or await request.is_disconnected():
                    return
                await asyncio.sleep(0.1)
        return StreamingResponse(gen(), media_type="text/event-stream")

    _include(app, routers, system, auth)
    _mount_static(app)
    deploy.install(app, team, _expirer(app, jobs, settings))
    _security(app, team)
    return app
