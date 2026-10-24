"""
API – techniky APC (M11b), další struktury: split range, regulace polohy ventilu (VPC), poměrová regulace
s křížovým omezením a interakce N×N (RGA); stejné výpočty jako okna desktopu (app.apc.splitrange, vpc, ratio, rgan).

Druhý akční člen (split range, VPC) a model vzduchu (poměr) zadává uživatel – desktop ani web je do projektu
neukládají (jen stav widgetů), proto jsou vstupy tělem požadavku; GET vrací výchozí hodnoty (= tlačítko „Původní
hodnoty“) a výsledky pro ně. RGA nemá vstupy: počítá z modelů všech smyček projektu (aktivní + ostatní s modelem).
Výpočty jsou na demu pod 0,1–0,3 s, proto bez úloh.
"""
from typing import Literal

import numpy as np
from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel, Field

from ..app import guides, signalpack
from ..app.apc import ratio as aratio
from ..app.apc import rgan
from ..app.apc import splitrange as asr
from ..app.apc import vpc as avpc
from ..core import MODELS
from ..i18n import T
from .data import _plain
from .tuning import Note, Pid


# ---- společné
class Check(BaseModel):
    """Položka kontrolního seznamu struktury (app.guides): True splněno, False chybí, None připomínka."""
    state: bool | None
    text: str
    action: str | None = None


class ModelInfo(BaseModel):
    code: str
    params: list[str]            # názvy parametrů modelu
    values: list[float]


MODE = Literal["opposite", "sequence"]


def _f(x):
    """Číslo pro JSON (NaN / ∞ → None)."""
    x = float(x)
    return x if np.isfinite(x) else None


def _checks(items):
    return [Check(state=s, text=t, action=a) for s, t, a in items]


def _model_info(g):
    return ModelInfo(code=g[0], params=list(MODELS[g[0]]["params"]), values=[float(v) for v in g[1]])


def _own_model(ws, p, what):
    """Model druhého členu: typ jako u smyčky, parametry zadané (p[1:] ≥ 0 jako v desktopu); None = bez změny."""
    code = ws.model[0]
    if p is None:
        return None
    if len(p) != len(MODELS[code]["params"]):
        raise HTTPException(422, f"{what}: expected {len(MODELS[code]['params'])} parameters for {code}")
    if not all(np.isfinite(p)):
        raise HTTPException(422, f"{what}: parameters must be finite")
    return code, [float(p[0])] + [max(float(v), 0.0) for v in p[1:]]


def _loop_name(proj):
    return str(proj.names()[proj.active])


def _rec_a(proj):
    """Minimální záznam aktivní smyčky pro kontroly struktur (app.guides)."""
    s = proj.state
    return dict(name=_loop_name(proj), model=s.model, c_mv=s.c_mv)


def _frame(t, cols):
    return signalpack.frame(signalpack.pack(list(cols), np.asarray(t, float), cols.__getitem__, cap=None))


def _same_grid(*ts):
    if len({len(t) for t in ts}) != 1:
        raise HTTPException(500, "inconsistent simulation grids")


CURVES = {200: {"content": {"application/octet-stream": {}}}}


# ---- split range
class SplitIn(BaseModel):
    mode: MODE = "opposite"
    b0: float = Field(50.0, ge=1, le=99)         # současný bod rozdělení [%]
    gap: float = Field(0.0, ge=-20, le=20)       # mezera (překryv / pásmo) [%]
    valve_a: list[float] | None = None           # parametry modelu ventilu A; None = výchozí (default_a)


class SplitHalf(BaseModel):
    k: float                     # zesílení výstup regulátoru → PV [%PV / %]
    ms: float | None             # citlivost Ms regulátoru (sada 2) v dané polovině
    stable: bool


class SplitCase(BaseModel):
    b: float
    lower: SplitHalf
    upper: SplitHalf


class SplitDesign(BaseModel):
    mode: MODE
    b0: float
    gap: float
    valve_a: ModelInfo
    valve_b: ModelInfo           # model smyčky přepočtený na % ventilu B při b0
    bstar: float                 # vyvážený bod rozdělení
    corr: float                  # násobek Gain regulátoru při přechodu na b*
    now: SplitCase
    new: SplitCase
    impl_text: str
    checks: list[Check]


class SplitInfo(BaseModel):
    model: str
    defaults: SplitIn            # včetně výchozího modelu ventilu A (valve_a vyplněno)
    design: SplitDesign


class SplitKpi(BaseModel):
    iae: float
    maxdev: float
    rev: int                     # změny směru výstupu regulátoru


class SplitSim(BaseModel):
    T_end: float
    amp: float                   # amplituda skoku SP [% PV]
    bstar: float
    kpis: dict[str, SplitKpi]    # now | new


def _split_models(ws, body):
    """(ga, gb) podle vstupu; ventil A výchozí z modelu ventilu B a režimu."""
    gb = asr.valve_b(ws.model, body.b0)
    return (_own_model(ws, body.valve_a, "valve_a") or asr.default_a(gb, body.mode)), gb


def _split_case(ga, gb, ctrl, b, mode):
    lo, up = asr.halves(ga, gb, ctrl, b, mode)
    return SplitCase(b=float(b), lower=SplitHalf(k=float(lo[0]), ms=_f(lo[1]), stable=bool(lo[2])),
                     upper=SplitHalf(k=float(up[0]), ms=_f(up[1]), stable=bool(up[2])))


def _split_design(proj, body):
    ws = proj.state
    ga, gb = _split_models(ws, body)
    bstar = asr.balanced(ga[1][0], gb[1][0])
    ctrl = ws.set_ctrl(2)
    up1 = asr.eff_gains(ga[1][0], gb[1][0], bstar, body.mode)[1]
    return SplitDesign(mode=body.mode, b0=body.b0, gap=body.gap, valve_a=_model_info(ga), valve_b=_model_info(gb),
                       bstar=bstar, corr=float(ws.model[1][0] / up1 if up1 else 1.0),
                       now=_split_case(ga, gb, ctrl, body.b0, body.mode),
                       new=_split_case(ga, gb, ctrl, bstar, body.mode),
                       impl_text=T("g_impl_split", b=f"{bstar:.1f}", g=f"{body.gap:.3g}"),
                       checks=_checks(guides.apc_actuators(_rec_a(proj), "split")))


def _split_run(ws, body):
    ga, gb = _split_models(ws, body)
    bstar = asr.balanced(ga[1][0], gb[1][0])
    runs, amp = asr.simulate(ga, gb, ws.set_ctrl(2), body.b0, bstar, body.mode, body.gap, float(ws.get("samp")))
    return runs, amp, bstar


def _split_frame(ws, runs):
    (t0, o0), (t1, o1) = runs["now"], runs["new"]
    _same_grid(t0, t1)
    cols = {"sp": ws.EP(np.asarray(o1["SP"])), "pv_now": ws.EP(np.asarray(o0["PV"])),
            "pv_new": ws.EP(np.asarray(o1["PV"])), "u_now": np.asarray(o0["U"]), "u_new": np.asarray(o1["U"]),
            "va": np.asarray(o1["VA"]), "vb": np.asarray(o1["VB"])}
    return _frame(t1, cols)


# ---- VPC
class VpcIn(BaseModel):
    mv2: list[float] | None = None               # parametry modelu MV2 (velký člen); None = výchozí
    sp: float = Field(50.0, ge=5, le=95)         # SP regulátoru VPC = žádaná poloha MV1 [%]
    factor: float = Field(5.0, ge=1, le=30)      # τc = factor × doba odezvy hlavní smyčky
    d: float = Field(35.0, ge=-100, le=100)      # skok zatížení [% MV1]


class VpcDesign(BaseModel):
    mv2: ModelInfo
    controller: Pid              # PI regulátor VPC (Kc = Gain, Ti = TI)
    surrogate: ModelInfo         # náhradní model MV2 → MV1 (P1D: K, T, θ)
    tc: float
    loop_time: float             # doba odezvy hlavní smyčky [s]
    impl_text: str
    checks: list[Check]


class VpcInfo(BaseModel):
    model: str
    defaults: VpcIn
    design: VpcDesign


class VpcKpi(BaseModel):
    iae: float
    at_lim: float                # čas MV1 v limitu [%]
    reserve: float               # rezerva MV1 na konci [%]


class VpcSim(BaseModel):
    T_end: float
    controller: Pid
    kpis: dict[str, VpcKpi]      # off | on


def _vpc_tune(ws, body):
    g1 = (ws.model[0], list(ws.model[1]))
    g2 = _own_model(ws, body.mv2, "mv2") or avpc.default_mv2(g1)
    cv, p, tc = avpc.tune_vpc(g1, g2, ws.set_ctrl(2), ws.base_ctrl(), body.factor)
    return g1, g2, cv, p, tc


def _vpc_design(proj, body):
    ws = proj.state
    g1, g2, cv, p, tc = _vpc_tune(ws, body)
    return VpcDesign(mv2=_model_info(g2), controller=Pid(Kc=float(cv["Gain"]), Ti=float(cv["TI"]), Td=float(cv["TD"])),
                     surrogate=ModelInfo(code="P1D", params=list(MODELS["P1D"]["params"]), values=[float(x) for x in p]),
                     tc=float(tc), loop_time=float(avpc.loop_time(g1, ws.set_ctrl(2))),
                     impl_text=T("g_impl_vpc", sp=f"{body.sp:.3g}", g=f"{cv['Gain']:.4g}", ti=f"{cv['TI']:.4g}"),
                     checks=_checks(guides.apc_actuators(_rec_a(proj), "vpc")))


def _vpc_run(ws, body):
    g1, g2, cv, _, _ = _vpc_tune(ws, body)
    return cv, avpc.simulate(g1, g2, ws.set_ctrl(2), cv, body.d, body.sp, float(ws.get("samp")))


def _vpc_frame(ws, runs):
    (t0, o0), (t1, o1) = runs["off"], runs["on"]
    _same_grid(t0, t1)
    cols = {"sp": ws.EP(np.asarray(o1["SP"])), "pv_off": ws.EP(np.asarray(o0["PV"])),
            "pv_on": ws.EP(np.asarray(o1["PV"])), "mv1_off": np.asarray(o0["MV1"]),
            "mv1_on": np.asarray(o1["MV1"]), "mv2_on": np.asarray(o1["MV2"])}
    return _frame(t1, cols)


# ---- poměrová regulace
class RatioIn(BaseModel):
    air_loop: int | None = Field(None, ge=0)     # index smyčky vzduchu v projektu; None = zadaný model
    air: list[float] | None = None               # parametry modelu vzduchu (jen při air_loop = None)
    R: float = Field(1.2, ge=0.01, le=100)       # poměr vzduch / palivo
    step: float = Field(15.0, ge=-50, le=50)     # skok požadavku výkonu [%]


class RatioSource(BaseModel):
    index: int
    name: str


class RatioDesign(BaseModel):
    air_loop: int | None
    air: ModelInfo
    sources: list[RatioSource]   # ostatní smyčky s modelem (zdroj vzduchu)
    impl_text: str
    checks: list[Check]


class RatioInfo(BaseModel):
    model: str
    defaults: RatioIn
    design: RatioDesign


class RatioKpi(BaseModel):
    lam_min: float               # nejmenší poměr vzduch / potřebný vzduch
    t_rich: float                # čas s λ < 1 [s]
    iae: float                   # IAE paliva vůči požadavku [jedn. paliva·s]


class RatioSim(BaseModel):
    T_end: float
    lam_min: dict[str, float]    # plain | cross (podklad textu ra_result)
    kpis: dict[str, RatioKpi]    # plain | cross


def _ratio_air(proj, body):
    """(model vzduchu, sada 2 regulátoru vzduchu); zdroj smyčka → její model a sada 2, jinak zadaný / výchozí."""
    ws = proj.state
    gf = (ws.model[0], list(ws.model[1]))
    if body.air_loop is None:
        return (_own_model(ws, body.air, "air") or aratio.default_air(gf)), ws.set_ctrl(2)
    if body.air is not None:
        raise HTTPException(422, "air and air_loop are mutually exclusive")
    rec = dict(proj.others()).get(body.air_loop)
    if rec is None:
        raise HTTPException(404, "loop not found or without model")
    return (rec["model"][0], list(rec["model"][1])), proj.loops[body.air_loop].set_ctrl(2)


def _ratio_design(proj, body):
    ga, _ = _ratio_air(proj, body)
    others = proj.others()
    return RatioDesign(air_loop=body.air_loop, air=_model_info(ga),
                       sources=[RatioSource(index=i, name=str(rec["name"])) for i, rec in others],
                       impl_text=T("g_impl_ratio", r=f"{body.R:.4g}"),
                       checks=_checks(guides.apc_ratio(_rec_a(proj), len(others))))


def _ratio_run(proj, body):
    ws = proj.state
    ga, ctrl_a = _ratio_air(proj, body)
    gf = (ws.model[0], list(ws.model[1]))
    return aratio.simulate(gf, ga, ws.set_ctrl(2), ctrl_a, body.R, body.step, float(ws.get("samp")))


def _ratio_frame(runs, R):
    (tc, oc), (tp, op) = runs["cross"], runs["plain"]
    _same_grid(tc, tp)
    cols = {"demand": np.asarray(oc["D"]), "fuel": np.asarray(oc["PVF"]), "air_r": np.asarray(oc["PVA"]) / R,
            "air_r_plain": np.asarray(op["PVA"]) / R, "lam": np.asarray(oc["LAM"]),
            "lam_plain": np.asarray(op["LAM"])}
    return _frame(tc, cols)


# ---- RGA
class RgaInfo(BaseModel):
    ready: bool                  # alespoň dvě smyčky s modelem
    names: list[str] = []        # smyčky (PV, první = aktivní)
    mvs: list[str] = []          # jejich MV (sloupce matic)
    K: list[list[float]] = []    # ustálená zesílení [%PV_i / %MV_j]
    known: list[list[bool]] = []  # vazba je v modelech (jinak 0 bez modelu)
    L: list[list[float | None]] = []  # RGA (None u singulární matice)
    NI: float | None = None      # Niederlinskiho index
    pairing: list[int] | None = None  # doporučené MV (index sloupce) pro PV_i
    advice: list[Note] = []
    checks: list[Check] = []


def _rga_records(proj):
    pr = proj.state
    return [dict(pr.report_record(), name=_loop_name(proj))] + [rec for _, rec in proj.others()]


def _rga_info(proj):
    recs = _rga_records(proj)
    if len(recs) < 2:
        return RgaInfo(ready=False, checks=_checks(guides.apc_rga(_rec_a(proj), len(recs), 0)))
    r = rgan.analyse(recs)
    n_cross = int(r["known"].sum() - len(recs))
    return RgaInfo(ready=True, names=[str(x) for x in r["names"]], mvs=[str(x) for x in r["mvs"]],
                   K=_plain(r["K"]), known=r["known"].tolist(), L=_plain(r["L"]), NI=_f(r["NI"]),
                   pairing=None if r["pairing"] is None else [int(j) for j in r["pairing"]],
                   advice=[Note(key=k) for k in r["advice"]],
                   checks=_checks(guides.apc_rga(_rec_a(proj), len(recs), n_cross)))


def router(get_proj):
    r = APIRouter(prefix="/workspaces/{wid}", tags=["apc"])

    def need_model(wid):
        proj = get_proj(wid)
        if not proj.state.has_data:
            raise HTTPException(409, "no data")
        if proj.state.model is None:
            raise HTTPException(409, "no model")
        return proj

    # ---- split range
    @r.get("/apc/split", response_model=SplitInfo)
    def split_get(wid: str, mode: MODE = "opposite", b0: float = Query(50.0, ge=1, le=99),
                  gap: float = Query(0.0, ge=-20, le=20)):
        """Split range: výchozí vstupy (model ventilu A podle režimu a b0) a vyvážený bod rozdělení, poloviny rozsahu."""
        proj = need_model(wid)
        ga, _ = _split_models(proj.state, SplitIn(mode=mode, b0=b0, gap=gap))
        body = SplitIn(mode=mode, b0=b0, gap=gap, valve_a=list(ga[1]))
        return SplitInfo(model=proj.state.model[0], defaults=body, design=_split_design(proj, body))

    @r.post("/apc/split/design", response_model=SplitDesign)
    def split_design(wid: str, body: SplitIn):
        """Výsledky pro zadané vstupy: b*, zesílení a Ms obou polovin teď / s b*, hodnoty pro šablonu."""
        return _split_design(need_model(wid), body)

    @r.post("/apc/split/simulate", response_model=SplitSim)
    def split_simulate(wid: str, body: SplitIn):
        """Skok SP přes bod rozdělení se současným a vyváženým rozdělením: IAE, max. odchylka PV, změny směru."""
        ws = need_model(wid).state
        runs, amp, bstar = _split_run(ws, body)
        return SplitSim(T_end=float(runs["new"][0][-1]), amp=amp, bstar=bstar,
                        kpis={k: SplitKpi(**_plain(asr.kpis(runs[k], ws.PR))) for k in ("now", "new")})

    @r.post("/apc/split/simulate/curves", response_class=Response,
            responses={200: dict(CURVES[200], description=(
                "app.signalpack.frame: sp, pv_now, pv_new in engineering units; u_now, u_new, va, vb in % "
                "(output of the controller and valves)"))})
    def split_curves(wid: str, body: SplitIn):
        ws = need_model(wid).state
        return Response(_split_frame(ws, _split_run(ws, body)[0]), media_type="application/octet-stream")

    # ---- VPC
    @r.get("/apc/vpc", response_model=VpcInfo)
    def vpc_get(wid: str):
        """Regulace polohy ventilu: výchozí vstupy (model MV2) a návrh PI regulátoru VPC."""
        proj = need_model(wid)
        ws = proj.state
        body = VpcIn(mv2=list(avpc.default_mv2((ws.model[0], list(ws.model[1])))[1]))
        return VpcInfo(model=ws.model[0], defaults=body, design=_vpc_design(proj, body))

    @r.post("/apc/vpc/design", response_model=VpcDesign)
    def vpc_design(wid: str, body: VpcIn):
        """Návrh regulátoru VPC pro zadaný model MV2, SP a násobek τc."""
        return _vpc_design(need_model(wid), body)

    @r.post("/apc/vpc/simulate", response_model=VpcSim)
    def vpc_simulate(wid: str, body: VpcIn):
        """Skokové zatížení s VPC a bez něj: IAE PV, čas MV1 v limitu, rezerva MV1."""
        ws = need_model(wid).state
        cv, runs = _vpc_run(ws, body)
        return VpcSim(T_end=float(runs["on"][0][-1]),
                      controller=Pid(Kc=float(cv["Gain"]), Ti=float(cv["TI"]), Td=float(cv["TD"])),
                      kpis={k: VpcKpi(**_plain(avpc.kpis(runs[k], ws.PR))) for k in ("off", "on")})

    @r.post("/apc/vpc/simulate/curves", response_class=Response,
            responses={200: dict(CURVES[200], description=(
                "app.signalpack.frame: sp, pv_off, pv_on in engineering units; mv1_off, mv1_on, mv2_on in %"))})
    def vpc_curves(wid: str, body: VpcIn):
        ws = need_model(wid).state
        return Response(_vpc_frame(ws, _vpc_run(ws, body)[1]), media_type="application/octet-stream")

    # ---- poměrová regulace
    @r.get("/apc/ratio", response_model=RatioInfo)
    def ratio_get(wid: str, air_loop: int | None = Query(None, ge=0)):
        """Poměrová regulace: výchozí vstupy, zdroje modelu vzduchu (ostatní smyčky) a model vzduchu."""
        proj = need_model(wid)
        body = RatioIn(air_loop=air_loop)
        ga, _ = _ratio_air(proj, body)
        if air_loop is None:
            body.air = list(ga[1])
        return RatioInfo(model=proj.state.model[0], defaults=body, design=_ratio_design(proj, body))

    @r.post("/apc/ratio/design", response_model=RatioDesign)
    def ratio_design(wid: str, body: RatioIn):
        """Model vzduchu (zadaný / výchozí / z jiné smyčky), implementace a kontroly pro zadané vstupy."""
        return _ratio_design(need_model(wid), body)

    @r.post("/apc/ratio/simulate", response_model=RatioSim)
    def ratio_simulate(wid: str, body: RatioIn):
        """Skok požadavku výkonu s křížovým omezením a bez: nejmenší λ, čas s λ < 1, IAE paliva."""
        proj = need_model(wid)
        runs = _ratio_run(proj, body)
        pr = proj.state.PR
        kp = {k: aratio.kpis(runs[k], pr) for k in ("plain", "cross")}
        return RatioSim(T_end=float(runs["cross"][0][-1]), lam_min={k: v["lam_min"] for k, v in kp.items()},
                        kpis={k: RatioKpi(**_plain(v)) for k, v in kp.items()})

    @r.post("/apc/ratio/simulate/curves", response_class=Response,
            responses={200: dict(CURVES[200], description=(
                "app.signalpack.frame: demand, fuel, air_r (air / R), air_r_plain, lam, lam_plain "
                "(flows in % of ranges)"))})
    def ratio_curves(wid: str, body: RatioIn):
        proj = need_model(wid)
        return Response(_ratio_frame(_ratio_run(proj, body), body.R), media_type="application/octet-stream")

    # ---- RGA
    @r.get("/apc/rga", response_model=RgaInfo)
    def rga_get(wid: str):
        """Interakce N×N: matice zesílení, RGA, Niederlinskiho index a doporučené párování ze smyček projektu."""
        return _rga_info(need_model(wid))

    return r
