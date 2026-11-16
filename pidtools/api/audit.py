"""
API – Přehled smyček (M20): smyčky v souboru (návrh z tagů, uložené v nastavení `audit_loops`), analýza výkonu
a společných oscilací (app.audit) a přehled smyček projektu se stavem každé z nich.
"""
from collections import OrderedDict
from typing import Any, Literal

import numpy as np
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

from .. import i18n
from ..app import audit
from ..app import batch
from ..app import tuning as tun
from ..app import tuning_export as tex
from ..app.signalpack import minmax_idx
from . import tasks
from .common import JobInfo, job_info
from .data import _plain

MAX_PTS = 1500          # bodů průběhu smyčky v odpovědi (min / max po skupinách)


class AuditLoop(BaseModel):
    name: str
    pv: str
    mv: str
    sp: str | None = None
    pos: str | None = None
    theta: float | None = None
    integ: bool = False


class AuditLoops(BaseModel):
    loops: list[AuditLoop]
    saved: bool = False             # False = návrh z názvů tagů (zatím neuloženo v projektu)


class AuditReq(BaseModel):
    loops: list[AuditLoop] | None = None      # výchozí: uložené / navržené smyčky
    a: float | None = None                    # okno analýzy [s]; bez něj celý záznam
    b: float | None = None
    project: bool = False                     # smyčky projektu (každá nad svými daty) místo seznamu smyček souboru


class AuditProblem(BaseModel):
    key: str
    severity: int


class AuditResult(BaseModel):
    name: str
    ok: bool
    err: str | None = None
    score: int = 0
    problems: list[AuditProblem] = []
    kpis: dict | None = None
    t: list[float] = []
    pv: list[float | None] = []
    mv: list[float | None] = []
    sp: list[float | None] | None = None


class AuditCommon(BaseModel):
    period: float
    loops: list[str]
    source: str
    by_stiction: bool


class Audit(BaseModel):
    results: list[AuditResult]
    common: list[AuditCommon]


class LoopHealth(BaseModel):
    ok: bool
    err: str | None = None
    score: int = 0
    problems: list[AuditProblem] = []
    kpis: dict | None = None


class LoopSet(BaseModel):
    gain: float | None = None
    ti: float | None = None
    td: float | None = None


class LoopRow(BaseModel):
    index: int
    name: str
    active: bool
    pv: str | None = None
    mv: str | None = None
    sp: str | None = None
    pos: str | None = None
    model: str | None = None
    params: list[float | None] = []
    set1: LoopSet
    set2: LoopSet
    health: LoopHealth
    fit: float | None = None            # FIT vybraného modelu [%]
    ms: float | None = None             # Ms Setu 2 (je-li zadán), jinak Setu 1 (je-li zadán); None = bez modelu / nestabilní
    set2_defined: bool = False
    change_pct: float | None = None     # změna Gain Set 1 → Set 2 [%]; jen když je Set 2 zadán a Set 1 není zástupný
    stage: Literal["no_data", "data", "model", "proposal", "set2"] = "no_data"


class LoopsOverview(BaseModel):
    active: int
    loops: list[LoopRow]


class BatchParams(BaseModel):
    """Parametry akce `tune` (stejné hodnoty jako Ladění: metoda, τc, typ regulátoru, kritérium a cíl optimalizace)."""
    method: str | None = None                                   # None = metoda uložená u modelu smyčky
    tc: float | None = Field(None, gt=0)
    ctype: Literal["PI", "PID"] | None = None
    crit: Literal["MIGO", "IAE", "ISE", "ITAE", "OVS"] | None = None
    target: Literal["dist", "sp", "both", "scen"] | None = None


class BatchReq(BaseModel):
    loops: list[int] = Field(min_length=1)
    action: Literal["identify", "tune", "accept"]
    params: BatchParams = BatchParams()


class BatchReason(BaseModel):
    key: str                                                    # klíč textu (i18n) – kontrola kvality dat nebo batch_*
    args: dict[str, str | float | int | None] = {}


class BatchRow(BaseModel):
    loop: int
    name: str
    status: Literal["ok", "skipped", "error"]
    reason: BatchReason | None = None


class BatchOut(BaseModel):
    job: JobInfo
    action: Literal["identify", "tune", "accept"]
    total: int
    rows: list[BatchRow]                                        # hotové smyčky (i u zrušené úlohy)


def _defs(ws):
    """Smyčky přehledu: uložené v projektu (jen s platnými sloupci), jinak návrh z názvů tagů."""
    saved = audit.from_records(ws.get("audit_loops"), list(ws.sig.sigs))
    return (saved, True) if saved else (audit.propose(ws.sig.sigs, ws.sig.get), False)


def _record(d):
    return AuditLoop(**audit.to_records([d])[0])


def _thin(x, idx):
    return None if x is None else _plain(np.asarray(x, float)[idx])


def _result(r):
    """Výsledek analýzy jedné smyčky; průběhy zředěné na MAX_PTS bodů."""
    probs = [AuditProblem(key=k, severity=int(v)) for k, v in r["problems"]]
    if not r["ok"]:
        return AuditResult(name=r["name"], ok=False, err=r["err"], score=int(r["score"]), problems=probs)
    n = len(r["t"])
    idx = minmax_idx(np.asarray(r["pv"], float), int(np.ceil(n / (MAX_PTS / 2)))) if n > MAX_PTS else np.arange(n)
    return AuditResult(name=r["name"], ok=True, score=int(r["score"]), problems=probs, kpis=_plain(r["kpis"]),
                       t=_thin(r["t"], idx), pv=_thin(r["pv"], idx), mv=_thin(r["mv"], idx), sp=_thin(r["sp"], idx))


def _loop_def(ls, name):
    """Smyčka projektu jako definice přehledu (sloupce a typ procesu z modelu)."""
    return audit.LoopDef(name=str(name), pv=ls.c_pv, mv=ls.c_mv, sp=ls.c_sp if ls.c_sp not in ("", "—") else None,
                         pos=ls.c_pos if ls.c_pos not in ("", "—") else None,
                         integ=bool(ls.model and ls.model[0].startswith("I")))


def _health(ls):
    """Stav smyčky projektu: analýza celého záznamu jejími sloupci (jako v přehledu smyček)."""
    r = audit.analyse_loop(ls.sig, _loop_def(ls, ls.c_pv), ls.ts_user)
    return LoopHealth(ok=bool(r["ok"]), err=r["err"], score=int(r["score"]), kpis=_plain(r.get("kpis")),
                  problems=[AuditProblem(key=k, severity=int(v)) for k, v in r["problems"]])


def _set(ls, n):
    g = lambda k: None if ls.get(f"set{n}_{k}") is None else float(ls.get(f"set{n}_{k}"))      # noqa: E731
    return LoopSet(gain=g("gain"), ti=g("ti"), td=g("td"))


def _fit(ls):
    """FIT vybraného modelu z identifikace (None = bez modelu)."""
    r = ls.fit["res"].get(ls.get("mcode")) if ls.fit and ls.model is not None else None
    return None if r is None else _fin(r.get("fit"))


def _fin(x):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return x if np.isfinite(x) else None


def _set1_real(ls):
    """Set 1 je skutečné nastavení z řídicího systému (ne výchozí zástupné hodnoty)."""
    return not tun.is_placeholder(*(float(ls.get(f"set1_{k}")) for k in ("gain", "ti", "td")))


def _ms(ls):
    """Ms sady, kterou smyčka používá (Set 2, jinak Set 1); stejný výpočet jako tabulka robustnosti v Ladění."""
    if ls.model is None:
        return None
    n = 2 if ls.get("set2_defined") else 1
    if n == 1 and not _set1_real(ls):
        return None
    m = ls.ctrl_metrics(ls.set_ctrl(n), worst=False)
    return _fin(m["Ms"]) if m["stable"] else None


def _change(ls):
    g1, g2 = float(ls.get("set1_gain")), float(ls.get("set2_gain"))
    return 100.0 * (g2 / g1 - 1.0) if ls.get("set2_defined") and _set1_real(ls) and g1 != 0 else None


def overview(p):
    names = p.names()
    rows = []
    for i, ls in enumerate(p.loops):
        rows.append(LoopRow(
            index=i, name=str(names[i]), active=i == p.active, pv=ls.c_pv, mv=ls.c_mv,
            sp=ls.c_sp if ls.c_sp not in ("", "—") else None, pos=ls.c_pos if ls.c_pos not in ("", "—") else None,
            model=ls.model[0] if ls.model else None, params=_plain(list(ls.model[1])) if ls.model else [],
            set1=_set(ls, 1), set2=_set(ls, 2), health=_health(ls), fit=_fit(ls), ms=_ms(ls),
            set2_defined=bool(ls.get("set2_defined")), change_pct=_change(ls), stage=batch.stage(ls)))
    return LoopsOverview(active=p.active, loops=rows)


KEEP_BATCH = 50          # kolik posledních hromadných úloh si API pamatuje (řádky výsledků)


def router(get_proj, jobs):
    r = APIRouter(prefix="/workspaces/{wid}", tags=["audit"])
    runs: OrderedDict[str, dict] = OrderedDict()      # ID úlohy → {wid, action, total, rows}

    def need_data(wid):
        ws = get_proj(wid).state
        if not ws.has_data:
            raise HTTPException(409, "no data")
        return ws

    @r.get("/audit/loops", response_model=AuditLoops)
    def audit_loops(wid: str, propose: bool = False):
        """Smyčky v souboru: uložené v projektu, jinak (nebo s `propose`) návrh z názvů tagů."""
        ws = need_data(wid)
        if propose:
            return AuditLoops(loops=[_record(d) for d in audit.propose(ws.sig.sigs, ws.sig.get)])
        defs, saved = _defs(ws)
        return AuditLoops(loops=[_record(d) for d in defs], saved=saved)

    @r.post("/audit/analyse", response_model=Audit)
    def analyse(wid: str, body: AuditReq):
        """Analýza smyček souboru (výchozí uložené / navržené); zadané smyčky se uloží do projektu jako v aplikaci."""
        ws = need_data(wid)
        win = (body.a, body.b) if body.a is not None and body.b is not None and body.b > body.a else None
        if body.project:                      # smyčky projektu, každá nad vlastními daty (úpravy jen ve Zdrojích a smyčkách)
            p = get_proj(wid)
            names = p.names()
            res = [audit.analyse_loop(ls.sig, _loop_def(ls, names[i]), ls.ts_user, win)
                   for i, ls in enumerate(p.loops) if ls.has_data and ls.c_pv and ls.c_mv]
            res.sort(key=lambda r: (-r["score"], -(r["kpis"]["std_e_pct"] if r["ok"] else -1)))
            return Audit(results=[_result(x) for x in res],
                         common=[AuditCommon(**g) for g in _plain(audit.common_oscillations(res))])
        if body.loops is None:
            defs = _defs(ws)[0]
        else:
            sigs = list(ws.sig.sigs)
            bad = [c for x in body.loops for c in (x.pv, x.mv, x.sp, x.pos) if c and c not in sigs]
            if bad:
                raise HTTPException(422, f"unknown signal: {', '.join(bad)}")
            defs = audit.from_records([x.model_dump() for x in body.loops], sigs)
        if not defs:
            raise HTTPException(422, "no loops")
        ws.set(audit_loops=audit.to_records(defs))
        res = audit.analyse(ws.sig, defs, ws.ts_user, win)
        return Audit(results=[_result(x) for x in res],
                     common=[AuditCommon(**g) for g in _plain(audit.common_oscillations(res))])

    def _indices(p, loops):
        """Smyčky v daném pořadí bez opakování; neexistující index = 404."""
        bad = [i for i in loops if not 0 <= i < len(p.loops)]
        if bad:
            raise HTTPException(404, f"loop not found: {bad[0]}")
        return list(dict.fromkeys(loops))

    @r.post("/batch", response_model=JobInfo)
    def batch_start(wid: str, body: BatchReq):
        """
        Hromadná akce nad vybranými smyčkami jako jedna úloha (průběh „3 / 12 · název“, zrušení zachová hotové smyčky):
        `identify` (výchozí nastavení smyčky), `tune` (návrh uložený u smyčky, Set 2 se nemění), `accept` (návrhy →
        Set 2). Smyčka bez použitelných dat se přeskočí s důvodem. Výsledek po smyčkách: GET /batch/{jid}.
        """
        p = get_proj(wid)
        loops = _indices(p, body.loops)
        params = body.params.model_dump()
        items = batch.plan(p, loops, body.action, params)
        orig = {it["loop"]: p.loops[it["loop"]] for it in items}
        run: dict[str, Any] = dict(wid=wid, action=body.action, total=len(items), rows=[])

        def partial(d):
            """Výsledek jedné smyčky se zapíše do smyčky v hlavním procesu (smyčka mezitím smazaná / přesunutá = nic)."""
            delta = d.pop("delta", None)
            run["rows"].append(d)
            try:
                cur = get_proj(wid)
            except HTTPException:
                return
            ls = orig[d["loop"]]
            if delta is None or ls not in cur.loops:
                return
            if "out" in delta:                                    # identifikace: stav a nastavení jako u /identify
                tasks.apply(ls, delta["out"])
                batch.apply_delta(ls, dict(drop=batch.sug_keys(ls)))    # starý návrh platil pro starý model
            else:
                batch.apply_delta(ls, delta)
            cur.touch()

        jid = jobs.submit(batch.run, items, body.action, params, tasks.run, timeout=1800 + 900 * len(items),
                          on_partial=partial)
        runs[jid] = run
        while len(runs) > KEEP_BATCH:
            runs.popitem(last=False)
        return job_info(jobs, jid)

    @r.get("/batch/export", response_class=Response,
           responses={200: {"content": {"text/plain": {}, "text/csv": {}},
                            "description": "one file with the set of every selected loop (fmt: csv, pcs7, tia, deltav); "
                                           "header X-Skipped-Loops lists loops without data or model"}})
    def batch_export(wid: str, loops: str, fmt: str = "csv", n: int = 2):
        """Export sady `n` vybraných smyček (indexy oddělené čárkou) do jednoho souboru; formát řádků jako `/tuning/export`."""
        p = get_proj(wid)
        try:
            idx = _indices(p, [int(x) for x in loops.split(",") if x.strip() != ""])
        except ValueError as ex:
            raise HTTPException(422, "loops: comma-separated loop indexes") from ex
        if not idx:
            raise HTTPException(422, "no loops selected")
        if fmt not in tex.FORMATS or n not in (1, 2):
            raise HTTPException(422, f"unknown export format: {fmt}")
        text, skipped = batch.export(p, idx, fmt, n, i18n.decimal())
        if len(skipped) == len(idx):
            raise HTTPException(409, "no model")
        f = tex.FORMATS[fmt]
        return Response(text, media_type=f"{f['mime']}; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="tuning_set{n}_{fmt}_loops.{f["ext"]}"',
                                 "X-Skipped-Loops": ",".join(map(str, skipped))})

    @r.get("/batch/{jid}", response_model=BatchOut)
    def batch_get(wid: str, jid: str):
        """Stav hromadné úlohy a řádky výsledku hotových smyček (průběžně; po zrušení zůstanou)."""
        run = runs.get(jid)
        if run is None or run["wid"] != wid:
            raise HTTPException(404, "batch not found")
        return BatchOut(job=job_info(jobs, jid), action=run["action"], total=run["total"],
                        rows=[BatchRow(**x) for x in run["rows"]])

    @r.get("/loops/overview", response_model=LoopsOverview)
    def loops_overview(wid: str):
        """Smyčky projektu: sloupce, model, sady parametrů a stav (problémy podle přehledu smyček)."""
        return overview(get_proj(wid))

    return r
