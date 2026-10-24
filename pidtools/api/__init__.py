"""
API nad aplikační vrstvou (FastAPI): pracovní prostory, texty, dlouhé úlohy s průběhem (docs/cs/milniky.md, M6).

Bezpečnost pro desktop: server poslouchá jen na 127.0.0.1 a vyžaduje token (hlavička `Authorization: Bearer …`
nebo `X-PID-Token`); bez tokenu odpoví jen /health. CORS jen pro zadané původy (okno aplikace).
Spuštění: python -m pidtools.api --port 8765 --token TAJNE
Rozhraní je popsané v openapi.json vedle tohoto souboru (generované; test hlídá, že odpovídá kódu).
"""
import asyncio
import contextvars
import hmac
import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .. import __version__, i18n
from ..app.jobs import FINAL, JobManager
from . import analysis, apc, data, model, opcua, projects, tuning
from .common import JobInfo
from .data import WorkspaceInfo, info
from .store import WorkspaceStore


class Health(BaseModel):
    status: str
    version: str


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


UI_DIR = Path(__file__).resolve().parent / "ui"                      # sestavené rozhraní (frontend: npm run build)
FONTS_DIR = Path(__file__).resolve().parents[2] / "static" / "fonts"  # přibalené fonty IBM Plex (OFL)


def _mount_static(app):
    """Fonty a sestavené rozhraní – až za endpointy API (ty mají přednost)."""
    if FONTS_DIR.is_dir():
        app.mount("/fonts", StaticFiles(directory=FONTS_DIR), name="fonts")
    if (UI_DIR / "index.html").exists():
        app.mount("/", StaticFiles(directory=UI_DIR, html=True), name="ui")


def create_app(token=None, cors_origins=(), workspace_ttl=3600.0, max_workspaces=20, max_jobs=2):
    """Aplikace FastAPI. token=None jen pro testy a vývoj (bez kontroly)."""
    jobs = JobManager(max_parallel=max_jobs)

    @asynccontextmanager
    async def lifespan(_app):
        yield
        jobs.shutdown()                      # běžící procesy úloh se ukončí se serverem

    app = FastAPI(title="PID Tools API", version=__version__, lifespan=lifespan,
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

    app.state.jobs = jobs
    if cors_origins:
        app.add_middleware(CORSMiddleware, allow_origins=list(cors_origins), allow_methods=["*"],
                           allow_headers=["*"])

    def auth(authorization: str | None = Header(None), x_pid_token: str | None = Header(None)):
        if token is None:
            return
        got = x_pid_token or (authorization[7:] if authorization and authorization.startswith("Bearer ") else "")
        if not hmac.compare_digest(str(got), str(token)):
            raise HTTPException(401, "invalid token")

    def project(wid: str):
        try:
            return app.state.store.get(wid)
        except KeyError:
            raise HTTPException(404, "workspace not found") from None

    def workspace(wid: str):
        """Aktivní smyčka projektu."""
        return project(wid).state

    def job(jid: str):
        try:
            return app.state.jobs.status(jid)
        except KeyError:
            raise HTTPException(404, "job not found") from None

    app.state.workspace = workspace          # pro další moduly API (M7–M11)
    app.include_router(data.router(project), dependencies=[Depends(auth)])
    app.include_router(projects.router(project), dependencies=[Depends(auth)])
    app.include_router(model.router(project, jobs), dependencies=[Depends(auth)])
    app.include_router(tuning.router(project, jobs), dependencies=[Depends(auth)])
    app.include_router(analysis.router(project), dependencies=[Depends(auth)])
    app.include_router(apc.router(project, jobs), dependencies=[Depends(auth)])
    app.include_router(opcua.router(project, jobs), dependencies=[Depends(auth)])

    @app.get("/health", response_model=Health, tags=["system"])
    def health():
        return Health(status="ok", version=__version__)

    @app.get("/i18n/{lang}", response_model=dict[str, str], tags=["system"], dependencies=[Depends(auth)])
    def texts(lang: str):
        if lang not in i18n.TEXTS:
            raise HTTPException(404, "language not found")
        return i18n.TEXTS[lang]

    @app.post("/workspaces", response_model=WorkspaceInfo, tags=["workspace"], dependencies=[Depends(auth)])
    def ws_create():
        wid, proj = app.state.store.create()
        return info(wid, proj.state)

    @app.get("/workspaces/{wid}", response_model=WorkspaceInfo, tags=["workspace"], dependencies=[Depends(auth)])
    def ws_get(wid: str):
        return info(wid, workspace(wid))

    @app.delete("/workspaces/{wid}", status_code=204, tags=["workspace"], dependencies=[Depends(auth)])
    def ws_delete(wid: str):
        if not app.state.store.delete(wid):
            raise HTTPException(404, "workspace not found")

    @app.get("/jobs/{jid}", response_model=JobInfo, tags=["jobs"], dependencies=[Depends(auth)])
    def job_get(jid: str):
        return JobInfo(**job(jid))

    @app.post("/jobs/{jid}/cancel", response_model=JobInfo, tags=["jobs"], dependencies=[Depends(auth)])
    def job_cancel(jid: str):
        job(jid)
        app.state.jobs.cancel(jid)
        return JobInfo(**job(jid))

    @app.get("/jobs/{jid}/result", tags=["jobs"], dependencies=[Depends(auth)])
    def job_result(jid: str):
        """Výsledek hotové úlohy jako JSON (u úloh nad pracovním prostorem jen vrácená hodnota metody)."""
        st = job(jid)
        if st["state"] != "done":
            raise HTTPException(409, f"job {st['state']}")
        res = app.state.jobs.result(jid)
        if isinstance(res, dict) and {"result", "state", "settings"} <= set(res):
            res = res["result"]
        return data._plain(res)

    @app.get("/jobs/{jid}/events", tags=["jobs"], dependencies=[Depends(auth)],
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

    _mount_static(app)
    return app
