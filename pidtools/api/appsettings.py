"""
API – globální nastavení aplikace, záchranná kopie projektu a nedávné projekty (E10-B).

`/app-settings` (čtení, změna, export / import souboru, logo reportu, schéma prahů diagnostiky) platí pro celou aplikaci;
v týmovém režimu je nastavení po uživatelích. `/workspaces/{wid}/save-state` říká, zda má prostor neuložené změny a kdy
se naposledy uložil; `/workspaces/{wid}/autosave` zapíše záchrannou kopii do složky uživatelských dat (po pádu
`/autosave/latest` + `/workspaces/{wid}/autosave/restore`), `/recent` je seznam naposledy uložených / otevřených projektů.
"""
import json
import os
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ..app import appsettings as aps
from ..app import project as prj
from ..app import triage as tri
from ..app.autosave import UserData
from ..controllers import Library
from . import deploy
from ..app.dataio import read_table
from .data import WorkspaceInfo, info
from .triage import ThresholdInfo

MAX_SETTINGS = 2 ** 20
EXAMPLES = {"ff": "apc_ff_example.csv"}                    # ukázky k datům kromě `/data/demo` (soubory v pidtools/assets/examples)
EXAMPLES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "examples")


class AppGeneral(BaseModel):
    autosave_min: Literal[0, 1, 5, 15, 30] = 1
    embed_data: bool = True


class AppAppearance(BaseModel):
    language: Literal["", "cs", "en"] = ""
    theme: Literal["", "system", "light", "dark"] = ""
    font_size: Literal["s", "m", "l", "xl"] = "m"


class AppCharts(BaseModel):
    height: int = Field(220, ge=120, le=1000)
    time_unit: Literal["auto", "s", "min", "h", "clock"] = "auto"
    decimal: Literal["auto", "comma", "dot"] = "auto"
    ti_unit: Literal["s", "min"] = "s"
    gain_view: Literal["kc", "pb"] = "kc"


class AppDiagnostics(BaseModel):
    thresholds: dict[str, dict[str, float]] = {}


class AppSimDefaults(BaseModel):
    ctype: Literal["PI", "PID", "PD"] = "PI"
    opt_ms: float = Field(1.6, ge=1.1, le=2.5)
    opt_ovs: int = Field(2, ge=0, le=50)
    opt_robust: bool = False


class AppDefaults(BaseModel):
    controller: str = "pcs7_pidconl"
    sim: AppSimDefaults = AppSimDefaults()


class AppJournal(BaseModel):
    author: str = Field("", max_length=80)
    require_note: bool = False


class AppReport(BaseModel):
    company: str = Field("", max_length=120)
    language: Literal["app", "cs", "en"] = "app"
    header: str = Field("", max_length=300)
    footer: str = Field("", max_length=300)
    logo: str = ""                                        # název souboru loga (nahrává se zvlášť), prázdné = bez loga


class AppOpcServer(BaseModel):
    name: str = Field(max_length=80)
    url: str = Field(max_length=300)


class AppHistorians(BaseModel):
    pcs7: str = ""
    deltav: str = ""
    pi: str = ""


class AppConnections(BaseModel):
    opc: list[AppOpcServer] = []
    historians: AppHistorians = AppHistorians()


class AppTestMemo(BaseModel):
    verdict: str = ""
    text: str = ""
    ok: int = 0
    warn: int = 0
    fail: int = 0
    at: str = ""


class AppSettings(BaseModel):
    """Nastavení aplikace (soubor `settings.json`, formát `pidtools.settings`)."""
    general: AppGeneral = AppGeneral()
    appearance: AppAppearance = AppAppearance()
    charts: AppCharts = AppCharts()
    diagnostics: AppDiagnostics = AppDiagnostics()
    defaults: AppDefaults = AppDefaults()
    journal: AppJournal = AppJournal()
    report: AppReport = AppReport()
    connections: AppConnections = AppConnections()
    controller_tests: dict[str, AppTestMemo] = {}            # poslední výsledek testu použitelnosti profilu


class SaveState(BaseModel):
    has_data: bool
    dirty: bool                                           # od posledního ručního uložení / otevření byly změny
    rev: int
    autosave_pending: bool                                # od poslední záchranné kopie byly změny
    saved_at: float | None = None                         # čas posledního ručního uložení (epocha, s)
    autosaved_at: float | None = None


class RecoveryInfo(BaseModel):
    available: bool
    at: float | None = None
    name: str = ""
    loops: int = 0
    bytes: int = 0


class RecentItem(BaseModel):
    id: str
    name: str
    at: float
    loops: int
    bytes: int
    snapshot: bool                                        # kopie souboru je uložená (jde znovu otevřít)


def project_label(p):
    """Název projektu pro seznamy: první zdroj / soubor, jinak štítek smyčky."""
    name = str(p.state.fname or "").split("|")[-1].strip() or (p.names()[0] if p.loops else "")
    return name or "project"


def new_defaults(settings, lib: Library):
    """Výchozí hodnoty nového prostoru z nastavení uživatele; výchozí regulátor, který v knihovně nejde najít, se vynechá."""
    ctl = settings["defaults"]["controller"]
    profile = None
    if ctl != "pcs7_pidconl":
        try:
            profile = lib.get(ctl)
        except KeyError:
            profile = None
    return aps.new_project_defaults(settings, profile)


def router(get_proj, store: aps.SettingsStore, data: UserData, lib: Library, public=False):
    r = APIRouter(tags=["app-settings"])

    def user():
        return deploy.USER.get()

    def out(s):
        return AppSettings(**s)

    # ---- nastavení aplikace
    @r.get("/app-settings", response_model=AppSettings)
    def get_settings():
        """Nastavení aplikace (výchozí hodnoty, co ještě není uložené)."""
        return out(store.load(user()))

    @r.put("/app-settings", response_model=AppSettings)
    def put_settings(body: AppSettings):
        """Uloží nastavení (hodnoty mimo meze se ořežou; logo se nahrává zvlášť, název loga zůstane)."""
        s = body.model_dump()
        s["report"]["logo"] = store.load(user())["report"]["logo"]
        return out(store.save(s, user()))

    @r.delete("/app-settings", response_model=AppSettings)
    def reset_settings():
        """Obnoví výchozí nastavení (i smaže logo)."""
        return out(store.reset(user()))

    @r.get("/app-settings/export", response_class=Response,
           responses={200: {"content": {"application/json": {}}, "description": "settings file (pidtools.settings)"}})
    def export_settings():
        """Nastavení jako soubor JSON ke stažení (bez loga)."""
        return Response(aps.export_text(store.load(user())), media_type="application/json",
                        headers={"Content-Disposition": 'attachment; filename="pidtools_settings.json"'})

    @r.post("/app-settings/import", response_model=AppSettings,
            openapi_extra={"requestBody": {"required": True, "content": {"application/json": {"schema": {"type": "object"}}}}})
    async def import_settings(request: Request):
        """Nahradí nastavení souborem z exportu (cizí formát nebo novější verze = 400)."""
        raw = await request.body()
        if len(raw) > MAX_SETTINGS:
            raise HTTPException(413, "settings too large")
        try:
            s = aps.parse_export(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as ex:
            raise HTTPException(400, f"invalid settings: {ex}") from ex
        s["report"]["logo"] = store.load(user())["report"]["logo"]
        return out(store.save(s, user()))

    @r.get("/app-settings/diagnostics-schema", response_model=list[ThresholdInfo])
    def thr_schema():
        """Schéma prahů pravidel verdiktu s výchozími hodnotami (pro formulář Diagnostika – kritéria)."""
        return [ThresholdInfo(rule=ru.id, label=ru.label, name=k, name_label=t.label, value=t.default, default=t.default,
                              lo=t.lo, hi=t.hi, unit=t.unit) for ru in tri.RULES for k, t in ru.thresholds.items()]

    @r.post("/app-settings/logo", response_model=AppSettings,
            openapi_extra={"requestBody": {"required": True, "content": {"application/octet-stream": {
                "schema": {"type": "string", "format": "binary"}}}}})
    async def put_logo(request: Request, name: str = Query(description="file name (extension png or jpg)")):
        """Nahraje logo firmy pro report (png / jpg do 1 MB; SVG se nepřijímá, ve veřejném režimu 403)."""
        if public:
            raise HTTPException(403, "logo_disabled")
        raw = await request.body()
        try:
            return out(store.put_logo(raw, name.rsplit(".", 1)[-1], user()))
        except ValueError as ex:
            raise HTTPException(422, str(ex)) from ex

    @r.get("/app-settings/logo", response_class=Response,
           responses={200: {"content": {"image/*": {}}, "description": "report logo"}, 404: {}})
    def get_logo():
        p = store.logo_path(user())
        if not p:
            raise HTTPException(404, "no logo")
        ext = p.rsplit(".", 1)[-1]
        # starý soubor SVG (dnes se nenahrává) se nikdy nevykreslí jako stránka: příloha + sandbox bez skriptů
        hdr = {"Content-Disposition": 'attachment; filename="logo.svg"', "Content-Security-Policy": "sandbox; default-src 'none'"} if ext == "svg" else {}
        return FileResponse(p, media_type=aps.LOGO_EXTS[ext], headers=hdr)

    @r.delete("/app-settings/logo", response_model=AppSettings)
    def delete_logo():
        return out(store.drop_logo(user()))

    r.include_router(save_router(get_proj, data, public))
    return r


def save_router(get_proj, data: UserData, public=False):
    """Stav uložení, záchranná kopie, nedávné projekty a ukázková data."""
    r = APIRouter(tags=["app-settings"])

    def user():
        return deploy.USER.get()

    @r.get("/workspaces/{wid}/save-state", response_model=SaveState)
    def save_state(wid: str):
        p = get_proj(wid)
        has = p.state.has_data
        return SaveState(has_data=has, dirty=has and p.rev != p.saved_rev, rev=p.rev,
                         autosave_pending=has and p.rev != p.autosaved_rev and p.rev != p.saved_rev,
                         saved_at=p.saved_at, autosaved_at=p.autosaved_at)

    @r.post("/workspaces/{wid}/autosave", response_model=SaveState)
    def autosave(wid: str):
        """Zapíše záchrannou kopii projektu (včetně dat) do složky uživatelských dat; bez dat nic (veřejný režim: 403)."""
        p = get_proj(wid)
        if public:
            raise HTTPException(403, "autosave_disabled")
        if not p.state.has_data:
            raise HTTPException(409, "no data")
        raw = prj.serialize_project(p.to_project(include_data=True)).encode("utf-8")
        data.save_recovery(raw, dict(name=project_label(p), loops=len(p.loops)), user())
        p.mark_saved(manual=False)
        return save_state(wid)

    @r.get("/autosave/latest", response_model=RecoveryInfo)
    def latest():
        """Záchranná kopie z minula (po pádu nebo zavření bez uložení), nebo `available = false`."""
        m = data.recovery(user())
        return RecoveryInfo(available=False) if m is None else RecoveryInfo(
            available=True, at=m.get("at"), name=str(m.get("name") or ""), loops=int(m.get("loops") or 0), bytes=int(m.get("bytes") or 0))

    @r.delete("/autosave", status_code=204)
    def drop_autosave():
        data.clear_recovery(user())

    def open_raw(wid, raw):
        p = get_proj(wid)
        try:
            p.apply_project(prj.load_project(raw.decode("utf-8")))
        except (ValueError, KeyError, TypeError, json.JSONDecodeError, UnicodeDecodeError, RecursionError) as ex:
            raise HTTPException(400, f"invalid project: {ex}") from ex
        p.mark_loaded()
        return info(wid, p.state)

    @r.post("/workspaces/{wid}/autosave/restore", response_model=WorkspaceInfo)
    def restore(wid: str):
        """Otevře záchrannou kopii do prostoru (projekt zůstane „neuložený“, kopie se nemaže)."""
        if data.recovery(user()) is None:
            raise HTTPException(404, "no recovery file")
        res = open_raw(wid, data.recovery_raw(user()))
        get_proj(wid).saved_rev = -1                      # neuloženo – záchranná kopie není soubor projektu
        return res

    @r.post("/workspaces/{wid}/data/example", response_model=WorkspaceInfo)
    def load_example(wid: str, name: Literal["ff"] = Query(description="example data set: ff = feedforward (APC)")):
        """Ukázková data k technice APC (CSV dodané s aplikací) jako nový projekt."""
        p = get_proj(wid)
        fname = EXAMPLES[name]
        with open(os.path.join(EXAMPLES_DIR, fname), "rb") as f:
            p.load_frame(read_table(fname, f.read()), fname)
        return info(wid, p.state)

    @r.get("/recent", response_model=list[RecentItem])
    def recent():
        return [RecentItem(**e) for e in data.recent(user())]

    @r.post("/workspaces/{wid}/recent/{rid}/open", response_model=WorkspaceInfo)
    def open_recent(wid: str, rid: str):
        try:
            raw = data.recent_raw(rid, user())
        except (KeyError, OSError):
            raise HTTPException(404, "recent project not found") from None
        return open_raw(wid, raw)

    @r.delete("/recent/{rid}", status_code=204)
    def drop_recent(rid: str):
        if not data.remove_recent(rid, user()):
            raise HTTPException(404, "recent project not found")

    return r


def remember(data: UserData):
    """Funkce pro `projects.router`: projekt, který se právě uložil / otevřel, se zapíše mezi nedávné; uložením
    záchranná kopie přestane být potřeba."""
    def fn(p, raw, saved=False):
        try:
            data.add_recent(raw, project_label(p), len(p.loops), deploy.USER.get())
            if saved:
                data.clear_recovery(deploy.USER.get())
        except OSError:
            pass                                          # seznam nedávných je jen pomůcka
    return fn
