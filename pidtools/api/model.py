"""
API – model (M9): úseky podle vstupů a vyřazení dat, identifikace (úloha s průběhem), výsledky a výběr modelu,
ruční úpravy a dofitování, křížové ověření, nejistota (bootstrap) a průběhy modelu pro graf.

Výpočty běží jako úlohy (app.jobs) na odlehčené kopii pracovního prostoru (Workspace.lean); po dokončení se
výsledek zapíše do prostoru (api.tasks.apply). Nastavení identifikace (chosen, thmax, dist_level, id_mode,
win_mode, ed|…, fx|…) se mění přes PATCH /settings.
"""
from typing import Literal

import numpy as np
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from ..app import loopmode as lm
from ..app import model as mdl
from ..app import signalpack
from ..app import windows as wn
from . import tasks
from .data import _plain
from .common import JobInfo, job_info


class Windows(BaseModel):
    wins: dict[str, list[list[float]]]
    excl: dict[str, list] | None = None
    tol: float | None = None


class WindowsInfo(BaseModel):
    wins: dict[str, list[list[float]]]
    excl: list[list] = []
    tol: float
    mv_modes: list[Literal["man", "auto"]] = []
    inputs: list[str] = []


class MvMode(BaseModel):
    index: int
    mode: Literal["man", "auto"]


class Check(BaseModel):
    key: str
    args: dict = {}


class ModelRes(BaseModel):
    code: str
    p: list[float]
    pdl: list[list[float]] = []
    fit: float | None = None
    fit_live: float | None = None
    nrmse: float | None = None
    status: int | None = None       # hodnocení modelu (text st_{status})
    method: str | None = None
    mixed: bool = False
    fit_cl_pv: float | None = None
    fit_cl_mv: float | None = None
    p_open: list[float] | None = None
    structs: list[str] = []
    window_fits: list[float | None] = []
    checks: list[Check] = []


class ModelState(BaseModel):
    has_fit: bool
    stale: bool = False
    selected: str | None = None
    current: dict | None = None
    results: list[ModelRes] = []
    warnings: list[list[str]] = []
    crossval: dict[str, list[float | None]] | None = None
    uncertainty: dict | None = None


class Select(BaseModel):
    code: str


class Refit(BaseModel):
    code: str


class Uncertainty(BaseModel):
    n: int = 15


def _f(x):
    x = None if x is None else float(x)
    return None if x is None or not np.isfinite(x) else x


def model_state(ws):
    if not ws.fit:
        return ModelState(has_fit=False)
    res = ws.fit["res"]
    out = []
    try:
        ts, pv, mv, d = ws.segment()
        summ = {q["code"]: q for q in mdl.summary(res, ts, pv, mv, d, ws.grid.Ts)}
        live = ws.live_fits()
    except Exception:                                   # data se od identifikace změnila (jiné sloupce)
        summ, live = {}, {}
    for c, r in res.items():
        q = summ.get(c, {})
        wf = ws.window_fits(c) if r.get("method") == "win" and ws.inputs_mode else []
        out.append(ModelRes(
            code=c, p=[float(x) for x in r["p"]], pdl=[[float(x) for x in d_] for d_ in r.get("pdl", [])],
            fit=_f(r.get("fit")), fit_live=_f(live.get(c)), nrmse=_f(q.get("NRMSE")), status=q.get("status"),
            method=r.get("method"), mixed=bool(r.get("mixed")), fit_cl_pv=_f(r.get("fit_cl_pv")),
            fit_cl_mv=_f(r.get("fit_cl_mv")), p_open=r.get("p_open"), structs=list(wn.structs(c, r)),
            window_fits=[_f(x) for x in wf],
            checks=[Check(key=k, args=_plain(a)) for k, a in lm.model_checks(c, r["p"], ws.grid.Ts)]))
    m = ws.model
    cur = dict(code=m[0], p=[float(x) for x in m[1]], pdl=[[float(x) for x in d_] for d_ in m[2]]) if m else None
    cv = ws.cv["res"] if ws.cv and ws.cv.get("key") == ws.fit_key() else None
    unc = ws.unc if ws.unc_models() else None
    return ModelState(has_fit=True, stale=ws.stale, selected=ws.get("mcode"), current=cur, results=out,
                      warnings=[list(w) for w in mdl.warnings(res, float(ws.t[-1]), float(ws.get("thmax") or 0))],
                      crossval={k: [_f(x) for x in v] for k, v in cv.items()} if cv else None,
                      uncertainty=_plain(unc) if unc else None)


def _set_windows(ws, body):
    allowed = set(wn.inputs(ws.c_d))
    bad = [k for k in body.wins if k not in allowed]
    if bad:
        raise HTTPException(422, f"unknown input: {', '.join(bad)}")
    ws.wins = {}
    for k, v in body.wins.items():
        ws.set_wins(k, v)
    if body.excl is not None:
        ws.excl = {str(k): list(v) for k, v in body.excl.items()}
    if body.tol is not None:
        ws.excl_tol = float(body.tol)


def _curves_frame(ws):
    """
    Průběhy modelu na mřížce smyčky v inženýrských jednotkách (jako /signals?source=grid) → binární balík. model_mv /
    model_dv jen s měřenými poruchami; residual = PV − model (jednotky PV).
    """
    c = ws.model_curves()
    cols = {"pv": ws.EP(ws.pv), "mv": ws.EM(ws.mv)}
    names = {"all": "model", "mv": "model_mv", "dv": "model_dv", "full_all": "full"}
    for k, v in c.items():
        if k in names and v is not None:
            cols[names[k]] = ws.EP(np.asarray(v, float))
    if "model" in cols:
        cols["residual"] = cols["pv"] - cols["model"]
    return signalpack.frame(signalpack.pack(list(cols), ws.t, cols.__getitem__, cap=None))


def router(get_proj, jobs):
    r = APIRouter(prefix="/workspaces/{wid}", tags=["model"])

    def need_data(wid):
        ws = get_proj(wid).state
        if not ws.has_data:
            raise HTTPException(409, "no data")
        return ws

    def need_model(wid):
        ws = need_data(wid)
        if ws.model is None:
            raise HTTPException(409, "no model")
        return ws

    def submit(wid, ws, method, args=(), kwargs=None, steps=1, key=None, timeout=1800):
        """Úloha nad kopií prostoru; výsledek se po dokončení zapíše do prostoru (pokud mezitím nezmizel)."""
        def done(out):
            try:
                cur = get_proj(wid).state
            except HTTPException:
                return
            tasks.apply(cur, out)
        jid = jobs.submit(tasks.run, ws.lean(), method, args, kwargs, steps, key=key, timeout=timeout,
                          on_done=done)
        return job_info(jobs, jid)

    @r.get("/windows", response_model=WindowsInfo)
    def get_windows(wid: str):
        ws = need_data(wid)
        return WindowsInfo(wins=ws.wins_s, excl=_plain([list(x) for x in ws.excl_rows()]), tol=float(ws.excl_tol),
                           mv_modes=ws.mv_modes(), inputs=list(wn.inputs(ws.c_d)))

    @r.put("/windows", response_model=WindowsInfo)
    def set_windows(wid: str, body: Windows):
        """Úseky podle vstupů {vstup: [[od, do] s]} (MV a měřené poruchy), vyřazení dat {signál: [zap, min, max]}."""
        _set_windows(need_data(wid), body)
        return get_windows(wid)

    @r.put("/windows/mode", response_model=WindowsInfo)
    def set_mv_mode(wid: str, body: MvMode):
        """Režim úseku MV (ručně / AUTO) pro kombinovanou identifikaci."""
        ws = need_data(wid)
        if not 0 <= body.index < len(ws.wins_s.get("MV", [])):
            raise HTTPException(404, "MV segment not found")
        ws.set_mv_mode(body.index, body.mode)
        return get_windows(wid)

    @r.post("/identify", response_model=JobInfo)
    def identify(wid: str):
        """Identifikace zvolených modelů (úloha). Výsledek: GET /model."""
        ws = need_data(wid)
        steps = len(ws.get("chosen")) * (2 if ws.id_closed and not ws.inputs_mode else 1)
        return submit(wid, ws, "identify", steps=steps, key=(wid, "identify", repr(ws.fit_key())))

    @r.get("/model", response_model=ModelState)
    def get_model(wid: str):
        return model_state(need_data(wid))

    @r.put("/model/select", response_model=ModelState)
    def select(wid: str, body: Select):
        ws = need_data(wid)
        if not ws.fit or body.code not in ws.fit["res"]:
            raise HTTPException(404, "model not found")
        ws.set(mcode=body.code)
        return model_state(ws)

    @r.post("/model/reset", response_model=ModelState)
    def reset(wid: str, body: Select):
        """Ruční úpravy parametrů modelu zpět na identifikované."""
        ws = need_data(wid)
        if not ws.fit or body.code not in ws.fit["res"]:
            raise HTTPException(404, "model not found")
        ws.reset_edits(body.code)
        return model_state(ws)

    @r.post("/model/refit", response_model=JobInfo)
    def refit(wid: str, body: Refit):
        """Dofitování se zafixovanými parametry (zaškrtnutí fx|kód|i v nastavení, hodnoty ed|kód|i) – úloha."""
        ws = need_model(wid)
        if body.code != ws.model[0]:
            ws.set(mcode=body.code)
        return submit(wid, ws, "refit", (body.code, ws.fixed_from_settings(body.code)))

    @r.post("/model/crossval", response_model=JobInfo)
    def crossval(wid: str):
        """Křížové ověření (úseky podle vstupů): fit bez každého úseku a shoda na něm – úloha."""
        ws = need_data(wid)
        if not ws.fit or not ws.inputs_mode:
            raise HTTPException(409, "needs a fit from per-input segments")
        return submit(wid, ws, "cross_validate", steps=len(ws.fit["res"]))

    @r.post("/model/uncertainty", response_model=JobInfo)
    def uncertainty(wid: str, body: Uncertainty):
        """Nejistota modelu – bootstrap reziduí (n refitů) – úloha."""
        ws = need_model(wid)
        return submit(wid, ws, "bootstrap", (int(body.n),), steps=int(body.n))

    @r.get("/model/curves", response_class=Response,
           responses={200: {"content": {"application/octet-stream": {}},
                            "description": "app.signalpack.frame on the loop grid in engineering units: pv, mv, "
                                           "model (all), model_mv, model_dv, full (whole record), residual"}})
    def curves(wid: str):
        """Průběhy aktuálního modelu na mřížce smyčky (NaN mimo úseky) – binárně jako /signals."""
        return Response(_curves_frame(need_model(wid)), media_type="application/octet-stream")

    return r
