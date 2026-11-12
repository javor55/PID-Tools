"""
API – Diagnostika všech smyček (E5, triáž): úloha na pozadí s průběhem, poslední výsledek (verdikty s důkazy,
metriky, společné oscilace, pořadí „kde začít“) a prahy pravidel verdiktu (nastavení projektu `tri_thr`).
"""
import json

import numpy as np
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..app import triage
from ..i18n import T
from .common import JobInfo, job_info
from .data import _plain


class Evidence(BaseModel):
    metric: str
    value: float | None = None
    threshold: float | None = None
    text_key: str
    text: str


class TriageLoop(BaseModel):
    index: int
    tag: str
    verdict: str
    label: str
    severity: int
    evidence: list[Evidence]
    metrics: dict
    err: str | None = None
    slave: int | None = None


class TriageCommon(BaseModel):
    period: float
    loops: list[int]
    source: int
    by_stiction: bool


class TriageResult(BaseModel):
    ready: bool = False
    loops: list[TriageLoop] = []
    common: list[TriageCommon] = []
    start: list[int] = []
    counts: dict[str, int] = {}


class ThresholdInfo(BaseModel):
    rule: str
    label: str
    name: str
    name_label: str
    value: float
    default: float
    lo: float
    hi: float
    unit: str


class Thresholds(BaseModel):
    values: dict[str, dict[str, float]]
    items: list[ThresholdInfo]


class ThresholdsReq(BaseModel):
    values: dict[str, dict[str, float]]


def _user_thr(proj):
    try:
        return json.loads(proj.loops[0].get("tri_thr") or "{}")
    except (TypeError, ValueError):
        return {}


def _thr_out(proj):
    vals = triage.merge_thresholds(_user_thr(proj))
    sch = [ThresholdInfo(rule=r.id, label=r.label, name=k, name_label=t.label, value=vals[r.id][k],
                         default=t.default, lo=t.lo, hi=t.hi, unit=t.unit)
           for r in triage.RULES for k, t in r.thresholds.items()]
    return Thresholds(values=vals, items=sch)


def _fmt(x):
    return "–" if x is None else f"{x:.3g}"


def _out(res):
    rows = []
    for r in res["rows"]:
        ev = [Evidence(metric=e["metric"], value=e["value"], threshold=e["threshold"], text_key=e["text"],
                       text=T(e["text"], v=_fmt(e["value"]), t=_fmt(e["threshold"]), err=r.get("err") or "")) for e in r["evidence"]]
        rows.append(TriageLoop(index=r["index"], tag=r["tag"], verdict=r["verdict"], label=T(triage.BY_ID[r["verdict"]].label),
                               severity=r["severity"], evidence=ev, metrics=_plain(r["metrics"]), err=r.get("err"),
                               slave=r.get("slave")))
    counts = {}
    for r in rows:
        counts[r.verdict] = counts.get(r.verdict, 0) + 1
    return TriageResult(ready=True, loops=rows, common=[TriageCommon(**_plain(c)) for c in res["common"]],
                        start=res["start"], counts=counts)


def _theta_model(ls):
    return float(ls.model[1][-1]) if ls.model else None


def _hyst_pct(ls):
    """Hystereze ventilu v % rozsahu MV (z polohy), nebo None bez polohy / při chybě."""
    try:
        h = ls.hysteresis(float(ls.t[0]), float(ls.t[-1]))
    except Exception:
        return None
    rng = float(ls.mv_hi - ls.mv_lo)
    return float(h / rng * 100) if h is not None and np.isfinite(h) and rng > 0 else None


def _nonlin(ls):
    try:
        r = ls.nonlinearity()
    except Exception:
        return None
    return float(r[1]) if r and r[1] is not None and np.isfinite(r[1]) else None


def _inputs(proj):
    """Vstupy dávky z každé smyčky projektu (signály jako obyčejná pole, aby šly předat do procesu úlohy)."""
    names, out = proj.names(), []
    for i, ls in enumerate(proj.loops):
        sp = ls.c_sp if ls.c_sp not in ("", "—", None) else None
        pos = ls.c_pos if ls.c_pos not in ("", "—", None) else None
        cols = {c: np.asarray(ls.sig.get(c), float) for c in {ls.c_pv, ls.c_mv, sp, pos} if c}
        th = ls.get("diag_theta")
        out.append(dict(tag=str(names[i]), pv=ls.c_pv, mv=ls.c_mv, sp=sp, pos=pos, integ=bool(ls.model and ls.model[0].startswith("I")),
                        ts_user=ls.ts_user, t_all=np.asarray(ls.sig.t_all, float), cols=cols, hyst_pct=_hyst_pct(ls) if pos else None,
                        nonlin=_nonlin(ls), theta_model=_theta_model(ls), theta_user=float(th) if th else None))
    return out


def _links(proj):
    """Kaskády: řídicí smyčka, jejíž MV je SP jiné (podřazené) smyčky → {index řídicí: index podřazené}."""
    out = {}
    for i, a in enumerate(proj.loops):
        for j, b in enumerate(proj.loops):
            if i != j and b.c_sp not in ("", "—", None) and b.c_sp == a.c_mv:
                out[i] = j
    return out


def router(get_proj, jobs):
    r = APIRouter(prefix="/workspaces/{wid}", tags=["triage"])

    @r.post("/triage", response_model=JobInfo)
    def start(wid: str):
        """Spustí triáž všech smyček projektu jako úlohu na pozadí; výsledek pak vrací GET /triage."""
        proj = get_proj(wid)
        if not proj.state.has_data:
            raise HTTPException(409, "no data")
        inputs, links, thr = _inputs(proj), _links(proj), _user_thr(proj)

        def done(res):
            try:
                get_proj(wid).triage = res
            except HTTPException:
                pass
        jid = jobs.submit(triage.run, inputs, thr, links, timeout=1800, on_done=done)
        return job_info(jobs, jid)

    @r.get("/triage", response_model=TriageResult)
    def last(wid: str):
        """Poslední výsledek triáže (`ready` False, dokud žádný není)."""
        res = getattr(get_proj(wid), "triage", None)
        return _out(res) if res else TriageResult()

    @r.get("/triage/thresholds", response_model=Thresholds)
    def get_thr(wid: str):
        """Prahy pravidel verdiktu (výchozí + uživatelské) a jejich schéma."""
        return _thr_out(get_proj(wid))

    @r.put("/triage/thresholds", response_model=Thresholds)
    def put_thr(wid: str, body: ThresholdsReq):
        """Uloží prahy do projektu (hodnoty se ořežou na meze); neznámá pravidla a názvy se vynechají."""
        proj = get_proj(wid)
        proj.loops[0].set(tri_thr=json.dumps(triage.merge_thresholds(body.values)))
        return _thr_out(proj)

    return r
