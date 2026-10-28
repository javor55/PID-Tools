"""
API – Přehled smyček (M20): smyčky v souboru (návrh z tagů, uložené v nastavení `audit_loops`), analýza výkonu
a společných oscilací (app.audit) a přehled smyček projektu se stavem každé z nich.
"""
import numpy as np
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..app import audit
from ..app.signalpack import minmax_idx
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


class LoopsOverview(BaseModel):
    active: int
    loops: list[LoopRow]


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


def _health(ls):
    """Stav smyčky projektu: analýza celého záznamu jejími sloupci (jako v přehledu smyček)."""
    d = audit.LoopDef(name=str(ls.c_pv), pv=ls.c_pv, mv=ls.c_mv, sp=ls.c_sp if ls.c_sp not in ("", "—") else None,
                      pos=ls.c_pos if ls.c_pos not in ("", "—") else None,
                      integ=bool(ls.model and ls.model[0].startswith("I")))
    r = audit.analyse_loop(ls.sig, d, ls.ts_user)
    return LoopHealth(ok=bool(r["ok"]), err=r["err"], score=int(r["score"]), kpis=_plain(r.get("kpis")),
                  problems=[AuditProblem(key=k, severity=int(v)) for k, v in r["problems"]])


def _set(ls, n):
    g = lambda k: None if ls.get(f"set{n}_{k}") is None else float(ls.get(f"set{n}_{k}"))      # noqa: E731
    return LoopSet(gain=g("gain"), ti=g("ti"), td=g("td"))


def overview(p):
    names = p.names()
    rows = []
    for i, ls in enumerate(p.loops):
        rows.append(LoopRow(
            index=i, name=str(names[i]), active=i == p.active, pv=ls.c_pv, mv=ls.c_mv,
            sp=ls.c_sp if ls.c_sp not in ("", "—") else None, pos=ls.c_pos if ls.c_pos not in ("", "—") else None,
            model=ls.model[0] if ls.model else None, params=_plain(list(ls.model[1])) if ls.model else [],
            set1=_set(ls, 1), set2=_set(ls, 2), health=_health(ls)))
    return LoopsOverview(active=p.active, loops=rows)


def router(get_proj):
    r = APIRouter(prefix="/workspaces/{wid}", tags=["audit"])

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
        win = (body.a, body.b) if body.a is not None and body.b is not None and body.b > body.a else None
        ws.set(audit_loops=audit.to_records(defs))
        res = audit.analyse(ws.sig, defs, ws.ts_user, win)
        return Audit(results=[_result(x) for x in res],
                     common=[AuditCommon(**g) for g in _plain(audit.common_oscillations(res))])

    @r.get("/loops/overview", response_model=LoopsOverview)
    def loops_overview(wid: str):
        """Smyčky projektu: sloupce, model, sady parametrů a stav (problémy podle přehledu smyček)."""
        return overview(get_proj(wid))

    return r
