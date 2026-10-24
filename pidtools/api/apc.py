"""
API – techniky APC (M11b): dopředná vazba (FF) a Smithův prediktor; stejné výpočty jako okna desktopu
(app.feedforward, app.apc.feedforward, app.apc.smith).

FF: nastavení poruch je v ws.ff_state (app.feedforward.state), čte ho i ladění (ws.set_ctrl). Smith: vstupy jsou
klíče nastavení (apc_sm_method, apc_sm_ct, apc_sm_tc|…, apc_sm_man, apc_sm_ek / et / eth) a mění se přes
PATCH /settings; robustní optimalizace (OPT) běží jako úloha a výsledek se drží u prostoru.
"""
import math

import numpy as np
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

from ..app import feedforward as ffm
from ..app import signalpack
from ..app.apc import feedforward as aff
from ..app.apc import smith as asm
from ..app.apc.common import tchar
from ..core import MODELS
from ..i18n import T
from .common import JobInfo, job_info
from .data import _plain
from .tuning import Note, Pid


# ---- dopředná vazba
class FFDesign(BaseModel):
    use: bool
    dyn: bool
    gain: float                  # % rozsahu MV na jednotku poruchy
    lead: float
    lag: float
    delay: float


class FFDesignIn(BaseModel):
    """Částečná změna jedné poruchy; chybějící hodnoty zůstanou."""
    use: bool | None = None
    dyn: bool | None = None
    gain: float | None = None
    lead: float | None = Field(None, ge=0)
    lag: float | None = Field(None, ge=0)
    delay: float | None = Field(None, ge=0)


class FFDefaults(BaseModel):
    gain: float
    lead: float
    lag: float
    delay: float


class ValueRow(BaseModel):
    param: str
    value: float
    unit: str


class FFDist(BaseModel):
    index: int
    name: str
    design: FFDesign
    defaults: FFDefaults         # návrh podle modelu
    edited: bool                 # hodnoty se liší od návrhu
    eng_gain: float              # zesílení v jednotkách MV na jednotku poruchy (vstup FFwd)
    step: float                  # výchozí skok poruchy pro ověření (polovina rozkmitu)
    values: list[ValueRow] = []  # hodnoty pro PIDConL (jen zapnutá porucha)


class FFInfo(BaseModel):
    model: str
    mv_unit: str
    mv_range: float
    dists: list[FFDist]


class FFReset(BaseModel):
    index: int | None = None     # None = všechny poruchy


class FFSimReq(BaseModel):
    dist: int = 0
    step: float | None = None


class FFKpi(BaseModel):
    iae: float
    maxdev: float


class FFSim(BaseModel):
    dist: int
    step: float
    T_end: float
    kpis: dict[str, FFKpi]       # none | static | dynamic


def _ff_step(ws, j):
    dd = ws.grid.dists[j]
    span = float(np.nanmax(dd) - np.nanmin(dd)) if len(dd) else 1.0
    return float(f"{((span if math.isfinite(span) else 1.0) / 2 or 1.0):.3g}")


def _ff_info(ws):
    code, p, pdl = ws.model
    des = ffm.design(code, p, pdl, ws.ff_state)
    u_mv = ws.get("u_mv") or "MV"
    used = [j for j, d in enumerate(des) if d["use"]]
    rows = dict(zip(used, aff.rows(ws.c_d, ws.grid.dists, des, ws.MR, u_mv)))
    edited = set(ffm.edited(code, p, pdl, des))
    out = []
    for j, (d, pd) in enumerate(zip(des, pdl)):
        g, tl, tg, dl = ffm.defaults(code, p, pd)
        vals = [ValueRow(param=a, value=float(v), unit=u) for a, v, u in rows[j][1]] if j in rows else []
        out.append(FFDist(index=j, name=str(ws.c_d[j]), design=FFDesign(**d), edited=j in edited,
                          defaults=FFDefaults(gain=g, lead=tl, lag=tg, delay=dl),
                          eng_gain=float(ffm.eng_gain(d["gain"], ws.MR)), step=_ff_step(ws, j), values=vals))
    return FFInfo(model=code, mv_unit=u_mv, mv_range=float(ws.MR), dists=out)


def _ff_run(ws, body):
    """Skok poruchy bez FF / se statickou / s dynamickou (jako okno desktopu): (čas, výsledky, KPI, skok)."""
    code, p, pdl = ws.model
    if not 0 <= body.dist < len(pdl):
        raise HTTPException(404, "disturbance not found")
    step = _ff_step(ws, body.dist) if body.step is None else float(body.step)
    des = ffm.design(code, p, pdl, ws.ff_state)
    t, outs = aff.simulate(code, p, pdl, ws.set_ctrl(2), des, body.dist, step, float(ws.get("samp")))
    return t, outs, aff.sim_kpis(t, outs, ws.PR), step


def _ff_frame(ws, t, outs):
    cols = {}
    for k, o in outs.items():
        cols[f"pv_{k}"], cols[f"mv_{k}"] = ws.EP(np.asarray(o["PV"])), ws.EM(np.asarray(o["MV"]))
    return signalpack.frame(signalpack.pack(list(cols), np.asarray(t, float), cols.__getitem__, cap=None))


def _ff_merge(ws, rows):
    """Změny poruch (po pořadí; None = beze změny) do ws.ff_state."""
    code, p, pdl = ws.model
    if len(rows) > len(pdl):
        raise HTTPException(422, f"too many disturbances: {len(rows)} > {len(pdl)}")
    des = ffm.design(code, p, pdl, ws.ff_state)
    for d, row in zip(des, rows):
        if row is not None:
            d.update({k: v for k, v in row.model_dump().items() if v is not None})
    ws.ff_state = ffm.state(des)


# ---- Smithův prediktor
class SmithInputs(BaseModel):
    method: str
    methods: list[str]
    ctype: str
    tc: float
    tc_default: float
    tc_key: str                  # klíč nastavení τc (pro PATCH /settings)
    manual: list[float]          # Gain, TI, TD ruční metody
    ek: float                    # chyba procesu [%]: zesílení, časové konstanty, zpoždění
    et: float
    eth: float


class GeneralRow(BaseModel):
    key: str                     # klíč textu (frontend přeloží)
    value: float
    unit: str


class SmithRow(BaseModel):
    block: str
    input: str
    value: float
    unit: str


class SmithController(Pid):
    notes: list[Note] = []


class SmithInfo(BaseModel):
    model: str
    inputs: SmithInputs
    integ: bool
    ratio: float                 # θ / charakteristický čas
    opt_ready: bool              # robustní optimalizace je spočtená pro aktuální zadání
    controller: SmithController | None = None
    pv_op: float | None = None   # pracovní bod v jednotkách PV / MV
    mv_op: float | None = None
    basis_text: str | None = None
    impl_text: str | None = None
    general_rows: list[GeneralRow] | None = None
    values: dict | None = None   # výsledek smith_apl
    rows: list[SmithRow] | None = None


class SmithSimReq(BaseModel):
    ek: float | None = Field(None, ge=-90, le=200)
    et: float | None = Field(None, ge=-90, le=200)
    eth: float | None = Field(None, ge=-90, le=200)


class SmithIae(BaseModel):
    iae_sp: float
    iae_load: float


class SmithSim(BaseModel):
    T_end: float
    controller: SmithController
    kpis: dict[str, SmithIae]    # pid | smith [jednotky PV · s]


def tc_key(method, code, p):
    """Klíč τc v nastavení – stejný jako v desktopu a webu (u SIMC dřívější tvar kvůli projektům)."""
    return f"apc_sm_tc|{code}|{p[-1]:.4g}" if method == "SIMC" else f"apc_sm_tc|{method}|{code}|{p[-1]:.4g}"


def _manual(ws):
    man = ws.get("apc_sm_man")
    if not man and all(ws.get(k) is not None for k in ("apc_sm_mg", "apc_sm_mti", "apc_sm_mtd")):      # projekt z webu
        man = [ws.get("apc_sm_mg"), ws.get("apc_sm_mti"), ws.get("apc_sm_mtd")]
    man = man or [ws.get("set2_gain", 1.0), ws.get("set2_ti", 100.0), ws.get("set2_td", 0.0)]
    return [float(x) for x in man]


def _smith_inputs(ws):
    code, p, _ = ws.model
    samp = float(ws.get("samp"))
    method = ws.get("apc_sm_method", asm.DEFAULT_METHOD)
    if method not in asm.METHODS:
        method = asm.DEFAULT_METHOD
    key = tc_key(method, code, p)
    tc0 = asm.tc_default(p, samp, method)
    return SmithInputs(method=method, methods=list(asm.METHODS), ctype=ws.get("apc_sm_ct", "PI"),
                       tc=float(ws.get(key, tc0)), tc_default=tc0, tc_key=key, manual=_manual(ws),
                       ek=float(ws.get("apc_sm_ek", 0.0)), et=float(ws.get("apc_sm_et", 0.0)),
                       eth=float(ws.get("apc_sm_eth", 0.0)))


def _opt_key(ws, ctype):
    code, p, _ = ws.model
    return (code, tuple(p), ctype, float(ws.get("samp")), tuple(sorted(ws.base_ctrl().items())))


def _smith_ctrl(ws, inp):
    """Regulátor prediktoru podle zadání; OPT jen z vypočtených výsledků (None, dokud neproběhla úloha)."""
    code, p, _ = ws.model
    samp = float(ws.get("samp"))
    if inp.method != "OPT":
        return asm.controller(code, p, inp.method, inp.ctype, inp.tc, samp, ws.base_ctrl(), tuple(inp.manual))
    return ws.smith_opt.get(_opt_key(ws, inp.ctype))


def _ctrl_out(r):
    return SmithController(Kc=float(r["Kc"]), Ti=float(r["Ti"]), Td=float(r["Td"]),
                           notes=[Note(key=k, args=_plain(a)) for k, a in r.get("notes", [])])


def _smith_values(ws, inp, r):
    """Pracovní bod, z čeho výpočet vychází a hodnoty pro šablonu (jen proces bez integrace)."""
    code, p, _ = ws.model
    samp = float(ws.get("samp"))
    _, pv_id, mv_id, _ = ws.segment()
    pv_op, mv_op = asm.operating_point(pv_id, mv_id)
    u_pv, u_mv = ws.get("u_pv") or "PV", ws.get("u_mv") or "MV"
    out = dict(pv_op=float(ws.EP(pv_op)), mv_op=float(ws.EM(mv_op)),
               basis_text=asm.basis_text(code, p, ws, pv_op, mv_op, samp, u_pv, u_mv))
    if r is None:
        return out
    gen = asm.general_rows(code, p, ws, pv_op, mv_op, r, inp.tc, inp.method, inp.ctype, u_pv, u_mv)
    v, r_, rows = asm.values(code, p, ws, pv_op, mv_op, inp.ctype, inp.tc, samp, u_pv, u_mv, r=r)
    out.update(general_rows=[GeneralRow(key=k, value=float(x), unit=u) for k, x, u in gen], values=_plain(v),
               rows=[SmithRow(block=b, input=i, value=float(x), unit=u) for b, i, x, u in rows],
               impl_text=T("g_impl_smith", k=f"{v['k']:.4g}", u=f"{u_pv}/{u_mv}", t=f"{v['lag']:.4g}",
                           th=f"{v['theta']:.4g}", pv0=f"{v['pv0']:.4g}", g=f"{r_['Kc']:.4g}", ti=f"{r_['Ti']:.4g}"))
    return out


def _smith_info(ws):
    code, p, _ = ws.model
    inp = _smith_inputs(ws)
    integ = bool(MODELS[code]["integ"])
    r = _smith_ctrl(ws, inp)
    ratio = p[-1] / max(tchar((code, p)), 1e-9)
    extra = {} if integ else _smith_values(ws, inp, r)
    return SmithInfo(model=code, inputs=inp, integ=integ, ratio=float(ratio), opt_ready=r is not None,
                     controller=None if r is None else _ctrl_out(r), **extra)


def _smith_run(ws, body):
    """Simulace PID (sada 2) vs. Smith na procesu s chybou modelu (jako okno desktopu)."""
    code, p, _ = ws.model
    inp = _smith_inputs(ws)
    r = _smith_ctrl(ws, inp)
    if r is None:
        raise HTTPException(409, "optimization not run")
    e = [x if x is not None else d for x, d in ((body.ek, inp.ek), (body.et, inp.et), (body.eth, inp.eth))]
    plant = asm.plant_error(p, *e)
    sim = asm.simulate(code, p, plant, ws.base_ctrl(), ws.set_ctrl(2), inp.ctype, inp.tc, float(ws.get("samp")), r=r)
    return sim, r


def _smith_frame(ws, sim):
    tb, PVb, MVb = sim["pid"]
    tt, o = sim["smith"]
    t = np.asarray(sim["t"], float)
    if not (len(tb) == len(tt) == len(t)):
        raise HTTPException(500, "inconsistent simulation grids")
    cols = {"sp": ws.EP(np.asarray(sim["sp"], float)), "pv_pid": ws.EP(np.asarray(PVb)),
            "mv_pid": ws.EM(np.asarray(MVb)), "pv_smith": ws.EP(np.asarray(o["PV"])),
            "mv_smith": ws.EM(np.asarray(o["MV"]))}
    return signalpack.frame(signalpack.pack(list(cols), t, cols.__getitem__, cap=None))


def _optimize(code, p, ctype, samp, base):
    """Robustní optimalizace regulátoru prediktoru (v procesu úlohy)."""
    return asm.controller(code, p, "OPT", ctype, None, samp, base)


def router(get_proj, jobs):
    r = APIRouter(prefix="/workspaces/{wid}", tags=["apc"])

    def need_model(wid):
        ws = get_proj(wid).state
        if not ws.has_data:
            raise HTTPException(409, "no data")
        if ws.model is None:
            raise HTTPException(409, "no model")
        return ws

    # ---- dopředná vazba
    @r.get("/apc/ff", response_model=FFInfo)
    def ff_get(wid: str):
        """Dopředná vazba po měřených poruchách: nastavení, návrh podle modelu, hodnoty pro PIDConL."""
        return _ff_info(need_model(wid))

    @r.put("/apc/ff", response_model=FFInfo)
    def ff_put(wid: str, body: list[FFDesignIn | None]):
        """Nastavení poruch po pořadí (částečné; null = beze změny) → ws.ff_state, čte ho i ladění."""
        ws = need_model(wid)
        _ff_merge(ws, body)
        return _ff_info(ws)

    @r.post("/apc/ff/reset", response_model=FFInfo)
    def ff_reset(wid: str, body: FFReset | None = None):
        """Zesílení, lead, lag a zpoždění znovu z návrhu podle modelu (zapnutí a dynamika zůstanou)."""
        ws = need_model(wid)
        code, p, pdl = ws.model
        idx = body.index if body else None
        if idx is not None and not 0 <= idx < len(pdl):
            raise HTTPException(404, "disturbance not found")
        ws.ff_state = ffm.state(ffm.reset(code, p, pdl, ffm.design(code, p, pdl, ws.ff_state), idx))
        return _ff_info(ws)

    @r.post("/apc/ff/simulate", response_model=FFSim)
    def ff_simulate(wid: str, body: FFSimReq):
        """Skok měřené poruchy bez FF / se statickou / s dynamickou (sada 2): IAE a max. odchylka PV."""
        ws = need_model(wid)
        t, _, kp, step = _ff_run(ws, body)
        return FFSim(dist=body.dist, step=step, T_end=float(t[-1]), kpis={k: FFKpi(**v) for k, v in kp.items()})

    @r.post("/apc/ff/simulate/curves", response_class=Response,
            responses={200: {"content": {"application/octet-stream": {}},
                             "description": "app.signalpack.frame: pv_none, mv_none, pv_static, mv_static, "
                                            "pv_dynamic, mv_dynamic in engineering units"}})
    def ff_curves(wid: str, body: FFSimReq):
        ws = need_model(wid)
        t, outs, _, _ = _ff_run(ws, body)
        return Response(_ff_frame(ws, t, outs), media_type="application/octet-stream")

    # ---- Smithův prediktor
    @r.get("/apc/smith", response_model=SmithInfo)
    def smith_get(wid: str):
        """Smithův prediktor: vstupy (z nastavení), regulátor, pracovní bod, hodnoty pro šablonu."""
        return _smith_info(need_model(wid))

    @r.post("/apc/smith/simulate", response_model=SmithSim)
    def smith_simulate(wid: str, body: SmithSimReq):
        """Skok SP a porucha na vstupu: PID (sada 2) vs. Smith na procesu s chybou modelu (ek, et, eth [%])."""
        ws = need_model(wid)
        sim, ctrl = _smith_run(ws, body)
        f = ws.PR / 100
        return SmithSim(T_end=float(sim["t"][-1]), controller=_ctrl_out(ctrl),
                        kpis={k: SmithIae(iae_sp=float(a * f), iae_load=float(b * f)) for k, (a, b) in
                              sim["iae"].items()})

    @r.post("/apc/smith/simulate/curves", response_class=Response,
            responses={200: {"content": {"application/octet-stream": {}},
                             "description": "app.signalpack.frame: sp, pv_pid, mv_pid, pv_smith, mv_smith in "
                                            "engineering units"}})
    def smith_curves(wid: str, body: SmithSimReq):
        ws = need_model(wid)
        return Response(_smith_frame(ws, _smith_run(ws, body)[0]), media_type="application/octet-stream")

    @r.post("/apc/smith/optimize", response_model=JobInfo)
    def smith_optimize(wid: str):
        """Robustní optimalizace regulátoru prediktoru (úloha); výsledek se uloží, dále GET /apc/smith."""
        ws = need_model(wid)
        inp = _smith_inputs(ws)
        code, p, _ = ws.model
        key = _opt_key(ws, inp.ctype)

        def done(res):
            try:
                cur = get_proj(wid).state
            except HTTPException:
                return
            cur.smith_opt[key] = res
        jid = jobs.submit(_optimize, code, list(p), inp.ctype, float(ws.get("samp")), dict(ws.base_ctrl()),
                          timeout=600, on_done=done)
        return job_info(jobs, jid)

    return r
