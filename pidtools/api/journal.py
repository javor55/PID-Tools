"""
API – deník ladění (E10): neměnné snímky stavu smyčky v projektu (seznam, vytvoření, detail, stav a poznámky, přílohy,
porovnání dvou verzí, obnova stavu, report ze snímku), zápis výsledku živé simulace a sekce reportu (registr), souhrnný
report více smyček. Autor záznamu = přihlášený uživatel týmového režimu, jinak jméno z Nastavení › Deník, jinak „local“.
"""
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from ..app import journal as jr
from ..app import report as rpt
from . import deploy
from .analysis import ReportReq


class HistoryItem(BaseModel):
    status: str
    when: str
    author: str
    note: str = ""


class NoteItem(BaseModel):
    when: str
    author: str
    text: str


class AttachmentInfo(BaseModel):
    id: str
    name: str
    mime: str
    size: int
    when: str
    author: str
    desc: str = ""


class SnapshotSummary(BaseModel):
    id: str
    loop: str
    v: int
    created: str
    author: str
    kind: str
    label: str
    status: str
    app_version: str
    sha256: str
    verified: bool                  # obsah odpovídá otisku
    n_notes: int
    n_attachments: int
    sets: dict                      # sada 1 / 2: Gain, TI, TD
    results: dict                   # Ms, GM, PM, IAE … sady 1 a 2
    model: dict | None = None       # typ, parametry, FIT
    controller: dict | None = None  # profil, verze
    live: dict | None = None        # souhrn běhu živé simulace (druh live)


class SnapshotDetail(SnapshotSummary):
    history: list[HistoryItem]
    notes: list[NoteItem]
    attachments: list[AttachmentInfo]
    content: dict


class JournalList(BaseModel):
    snapshots: list[SnapshotSummary]
    statuses: list[str]


class NewSnapshot(BaseModel):
    loop: str | int | None = None        # smyčka (index / název), výchozí aktivní
    label: str = ""
    note: str = ""


class SnapshotPatch(BaseModel):
    status: str | None = None
    status_note: str = ""
    note: str | None = None              # přidá poznámku


class NewAttachment(BaseModel):
    name: str
    data_b64: str
    mime: str = "application/octet-stream"
    desc: str = ""


class AttachmentData(AttachmentInfo):
    data_b64: str


class DiffRow(BaseModel):
    section: str
    key: str
    a: object | None = None
    b: object | None = None


class Compare(BaseModel):
    a: SnapshotSummary
    b: SnapshotSummary
    rows: list[DiffRow]


class Restored(BaseModel):
    snapshot: SnapshotSummary
    autosave: SnapshotSummary
    data_changed: list[str]              # zdroje, jejichž data se od snímku změnila


class LiveRun(BaseModel):
    when: str | None = None
    struct: str = "pid"
    kpi: dict = {}


class SectionInfo(BaseModel):
    id: str
    title: str
    help: str
    default: bool
    available: bool


class SummaryReq(BaseModel):
    meta: dict = {}
    findings: list[dict] = []            # nálezy z auditu / triáže: [{name, finding}]


def _summary(s):
    c = s.content
    sets = {n: {k: (c.get("sets") or {}).get(f"set{n}_{k}") for k in ("gain", "ti", "td")} for n in "12"}
    return SnapshotSummary(
        id=s.id, loop=s.loop, v=s.v, created=s.created, author=s.author, kind=s.kind, label=s.label, status=s.status,
        app_version=s.app_version, sha256=s.sha256, verified=s.verify(), n_notes=len(s.notes),
        n_attachments=len(s.attachments), sets=sets, results=c.get("results") or {}, model=c.get("model"),
        controller=c.get("controller"), live=c.get("live"))


def _detail(s):
    d = s.to_dict()
    return SnapshotDetail(**_summary(s).model_dump(), history=d["history"], notes=d["notes"],
                          attachments=[{k: v for k, v in a.items() if k != "data"} for a in d["attachments"]],
                          content={k: v for k, v in s.content.items() if k != "record"})


def _journal_cfg(settings):
    """Nastavení deníku (Nastavení aplikace › Deník) přihlášeného uživatele; bez úložiště výchozí."""
    if settings is None:
        return {"author": "", "require_note": False}
    try:
        return settings.load(deploy.USER.get() or None).get("journal") or {}
    except Exception:                                                   # noqa: BLE001 – poškozené nastavení deník neblokuje
        return {"author": "", "require_note": False}


def _author(settings=None):
    """Autor záznamu: přihlášený uživatel týmového režimu, jinak jméno z Nastavení › Deník, jinak „local“."""
    return deploy.USER.get() or _journal_cfg(settings).get("author") or "local"


def router(get_proj, settings=None):
    r = APIRouter(prefix="/workspaces/{wid}", tags=["journal"])

    def guard(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except KeyError as ex:
            raise HTTPException(404, str(ex.args[0])) from ex
        except ValueError as ex:
            raise HTTPException(422, str(ex)) from ex

    @r.get("/journal", response_model=JournalList)
    def listing(wid: str, loop: str | None = None, status: str | None = None):
        """Snímky deníku (nové první), případně jen jedné smyčky nebo stavu."""
        p = get_proj(wid)
        return JournalList(snapshots=[_summary(s) for s in jr.listing(p, loop, status)], statuses=list(jr.STATUSES))

    @r.post("/journal", response_model=SnapshotDetail)
    def create(wid: str, body: NewSnapshot):
        """Uloží neměnný snímek stavu smyčky (výchozí aktivní)."""
        p = get_proj(wid)
        return _detail(guard(jr.create, p, body.loop, body.label, body.note, _author(settings)))

    @r.post("/journal/live", response_model=SnapshotDetail)
    def live(wid: str, body: LiveRun):
        """„Zapsat výsledek do deníku“ ze živé simulace: snímek aktivní smyčky s výsledky běhu."""
        p = get_proj(wid)
        return _detail(jr.add_live(p, body.model_dump(), None, _author(settings)))

    @r.get("/journal/compare", response_model=Compare)
    def compare(wid: str, a: str, b: str):
        """Strukturovaný rozdíl dvou snímků (změněné parametry, modely, výsledky)."""
        d = guard(jr.compare, get_proj(wid), a, b)
        return Compare(a=_summary(d["a"]), b=_summary(d["b"]), rows=d["rows"])

    @r.get("/journal/{sid}", response_model=SnapshotDetail)
    def detail(wid: str, sid: str):
        return _detail(guard(jr.get, get_proj(wid), sid))

    @r.patch("/journal/{sid}", response_model=SnapshotDetail)
    def patch(wid: str, sid: str, body: SnapshotPatch):
        """Změna stavu (Návrh → Nasazeno → Ověřeno / Zamítnuto, s historií) a / nebo nová poznámka."""
        p = get_proj(wid)
        s = guard(jr.get, p, sid)
        if body.status is None and body.note is None:
            raise HTTPException(422, "nothing to change")
        if body.status is not None and _journal_cfg(settings).get("require_note") and not (body.status_note or "").strip():
            raise HTTPException(422, "note required")                   # Nastavení › Deník: poznámka povinná
        if body.status is not None:
            guard(jr.set_status, p, sid, body.status, _author(settings), body.status_note)
        if body.note is not None:
            guard(jr.add_note, p, sid, body.note, _author(settings))
        return _detail(s)

    @r.post("/journal/{sid}/attachments", response_model=AttachmentInfo)
    def attach(wid: str, sid: str, body: NewAttachment):
        """Příloha (malý soubor v base64; velikost je omezená, uloží se do projektu)."""
        _, a = guard(jr.add_attachment, get_proj(wid), sid, body.name, body.data_b64, body.mime, body.desc, _author(settings))
        return {k: v for k, v in a.items() if k != "data"}

    @r.get("/journal/{sid}/attachments/{aid}", response_model=AttachmentData)
    def attachment(wid: str, sid: str, aid: str):
        a = guard(jr.attachment, get_proj(wid), sid, aid)
        return dict(a, data_b64=a["data"])

    @r.post("/journal/{sid}/restore", response_model=Restored)
    def restore(wid: str, sid: str):
        """„Otevřít tento stav“: obnoví smyčku ze snímku; aktuální stav se předtím uloží jako „autosave před obnovením“."""
        out = guard(jr.restore, get_proj(wid), sid, _author(settings))
        return Restored(snapshot=_summary(out["snapshot"]), autosave=_summary(out["autosave"]),
                        data_changed=out["data_changed"])

    @r.post("/journal/{sid}/report", response_class=Response,
            responses={200: {"content": {"text/html": {}}, "description": "report from a journal snapshot (HTML)"}})
    def report(wid: str, sid: str, body: ReportReq):
        """Report ze snímku (jazyk podle `?lang=`): z uložených hodnot, ne z aktuálního stavu."""
        bad = [x for x in body.sections if x not in rpt.ALL_SECTIONS]
        if bad:
            raise HTTPException(422, f"unknown section: {', '.join(bad)}")
        return Response(guard(jr.report_snapshot, get_proj(wid), sid, body.meta, body.sections, body.chart_mode),
                        media_type="text/html")

    @r.get("/report/sections", response_model=list[SectionInfo])
    def sections(wid: str):
        """Registr sekcí reportu (id, název a nápověda v jazyce požadavku, výchozí, dostupnost podle projektu)."""
        p = get_proj(wid)
        ctx = dict(history=bool(p.journal), attachments=any(s.attachments for s in p.journal),
                   live=any(s.content.get("live") for s in p.journal), ab=False)
        return rpt.section_info(ctx)

    @r.post("/report/summary", response_class=Response,
            responses={200: {"content": {"text/html": {}}, "description": "summary report of all loops (HTML)"}})
    def summary(wid: str, body: SummaryReq):
        """Souhrnný report všech smyček projektu (audit / triáž): model, sada 2, Ms, stav v deníku, nález."""
        p = get_proj(wid)
        return Response(rpt.build_summary(jr.summary_rows(p, body.findings), body.meta), media_type="text/html")

    return r
