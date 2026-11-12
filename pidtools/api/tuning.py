"""
API – ladění a simulace (M10): sady parametrů a jejich robustnost, metody a návrh ladění s kontrolami, porovnání
metod (úloha), historie, scénář a simulace (souhrn i průběhy binárně), frekvenční charakteristiky.

Blok PIDConL (SampleTime, DiffGain, NormPV / NormMV, filtry, rychlosti …) a parametry metod (ctype, opt_ms,
opt_crit, opt_target, opt_ovs, opt_robust) se mění přes PATCH /settings.
"""
import math
from typing import Any

import numpy as np
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from .. import i18n
from ..app import ctl_tuning as ctl
from ..app import frequency as fq
from ..app import live
from ..app import loopmode as lm
from ..app import scenario as scn
from ..app import signalpack
from ..app import tuning as tun
from ..app import tuning_export as tex
from .common import JobInfo, job_info
from .data import _plain


class Pid(BaseModel):
    Kc: float
    Ti: float
    Td: float = 0.0


class Note(BaseModel):
    key: str
    args: dict = {}


class Warn(BaseModel):
    key: str
    text: str


class Robust(BaseModel):
    stable: bool
    Ms: float | None = None
    Mt: float | None = None
    GM: float | None = None
    PM: float | None = None


class Suggestion(Pid):
    """Návrh v kanonickém tvaru (Kc, Ti, Td) a v parametrech regulátoru smyčky (`values` v jednotkách bloku)."""
    method: str
    notes: list[Note] = []
    checks: list[Note] = []
    values: dict[str, Any] = {}              # klíč parametru profilu → hodnota v jednotkách bloku
    warnings: list[Warn] = []                # upozornění mapování (např. sériová forma, chybějící váha b)
    tc: float | None = None                  # použité τc [s] (SIMC / iSIMC / Lambda; zadané, jinak výchozí)
    robust: Robust | None = None             # robustnost sady po převodu na profil (Ms, Mt, GM, PM)
    approximate: bool = False                # nelineární profil: robustnost z linearizované části


class SuggestReq(BaseModel):
    method: str | None = None
    tc: float | None = None


class WriteSet(BaseModel):
    """Sada v kanonickém tvaru (Kc, Ti, Td), nebo v jednotkách bloku (`values`: klíč parametru profilu → hodnota)."""
    Kc: float | None = None
    Ti: float | None = None
    Td: float = 0.0
    values: dict[str, Any] | None = None
    log: dict | None = None


class SetInfo(BaseModel):
    n: int
    gain: float
    ti: float
    td: float
    placeholder: bool
    metrics: dict | None = None
    values: dict[str, Any] = {}              # sada v parametrech profilu (jednotky bloku)
    warnings: list[Warn] = []


class ParamRef(BaseModel):
    key: str
    name: str
    unit: str | None = None
    role: str


class BlockParam(ParamRef):
    setting: str | None = None               # klíč nastavení smyčky, který hodnotu drží (None = jen zobrazení)
    value: Any = None
    default: Any = None


class LoopCtrlRef(BaseModel):
    id: str
    name: str
    vendor: str
    block: str
    tag: str                                 # preset / custom
    verified: bool
    is_default: bool


class TuningInfo(BaseModel):
    model: str | None
    methods: list[str]
    default_method: str
    sets: list[SetInfo]
    d_advice: dict | None = None
    history: list[dict] = []
    controller: LoopCtrlRef | None = None
    tuning_params: list[ParamRef] = []       # parametry sady (Gain / TI / TD u PIDConL, Kp / Ki / Kd u paralelní formy …)
    block_params: list[BlockParam] = []      # ostatní parametry bloku podle profilu
    export_formats: list[str] = []


class PlantSet(BaseModel):
    stic: float | None = None                # stikce [jednotky MV]
    slip: float | None = None                # skluz J [% stikce]
    noise: float | None = None               # šum PV [jednotky PV]
    vchar: list[float] | None = None         # charakteristika ventilu: zesílení 10 pásem


class PlantInfo(BaseModel):
    stic: float
    stic_default: float
    slip: float
    noise: float
    sigma_pv: float
    vchar: list[float]
    curve_x: list[float]
    curve_y: list[float]


class RobRow(Robust):
    name: str                                # set1 / set2 / sug
    noise: float | None = None
    Ms_worst: float | None = None
    approximate: bool = False


class Scenario(BaseModel):
    kind: str
    kinds: list[str]
    rows: list[list]
    T_end: float
    sp_from_to: list[float]


class ScenarioSet(BaseModel):
    kind: str | None = None
    rows: list[list] | None = None
    sp_from_to: list[float] | None = None
    T_end: float | None = None


class SimReq(BaseModel):
    preview: Pid | None = None
    T_end: float | None = None
    robust: bool = False
    spread: bool = False
    ff_cmp: bool = False


class SimInfo(BaseModel):
    T_end: float
    src: str | None = None
    kpis: dict


class FreqSet(BaseModel):
    name: str
    stable: bool
    Ms: float | None = None
    GM: float | None = None
    PM: float | None = None
    wc: float | None = None
    w180: float | None = None
    bw: float | None = None
    w: list[float]
    mag_db: list[float]
    phase_deg: list[float]
    S_db: list[float]
    T_db: list[float]
    re: list[float]          # Nyquistův diagram: reálná a imaginární část L
    im: list[float]


def _fin(x):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return x if np.isfinite(x) else None


def _num(x):
    """Hodnoty bloku do JSON: nekonečno (bez I složky, bez filtru) = None."""
    return None if isinstance(x, float) and not math.isfinite(x) else x


def _view(ws, kc, ti, td):
    """Kanonická sada → (hodnoty v jednotkách bloku, varování mapování)."""
    try:
        m = ws.block_view(kc, ti, td)
    except (ValueError, KeyError, ZeroDivisionError):
        return {}, []
    return ({k: _num(v) for k, v in m["values"].items()},
            [Warn(key=k, text=i18n.T(k, **a)) for k, a in m["warnings"]])


def _sets(ws):
    out = []
    for n in (1, 2):
        g, ti, td = (float(ws.get(f"set{n}_{k}")) for k in ("gain", "ti", "td"))
        m = None
        if ws.model is not None:
            try:
                m = _plain({k: v for k, v in ws.set_metrics(n).items()})
            except Exception:
                m = None
        vals, warns = _view(ws, g, ti, td)
        out.append(SetInfo(n=n, gain=g, ti=ti, td=td, placeholder=tun.is_placeholder(g, ti, td), metrics=m, values=vals,
                           warnings=warns))
    return out


def _loop_ref(ws):
    from ..controllers import load_preset, presets
    data = ctl.profile_data(ws.controller)
    pre = data.get("id") in presets() and data == load_preset(data["id"])
    return LoopCtrlRef(id=data.get("id", ""), name=data.get("name", ""), vendor=data.get("vendor", ""),
                       block=data.get("block", ""), tag="preset" if pre else "custom",
                       verified=(data.get("verification") or {}).get("status") == "verified",
                       is_default=ws.controller is None)


def _sim(ws, body):
    preview = body.preview.model_dump() if body.preview else None
    return ws.simulate(body.T_end, robust=body.robust, spread=body.spread, ff_cmp=body.ff_cmp, preview=preview)


def _sim_frame(ws, sim):
    """Průběhy simulace v inženýrských jednotkách: sp a pro každý běh pv_*, mv_* (1, 2, sug, extra_i)."""
    cols = {"sp": ws.EP(np.asarray(sim["sp"], float))}
    for k, r in sim["runs"].items():
        cols[f"pv_{k}"], cols[f"mv_{k}"] = ws.EP(np.asarray(r["PV"])), ws.EM(np.asarray(r["MV"]))
    for i, (name, r) in enumerate(sim["extra"]):
        cols[f"pv_x{i}_{name}"] = ws.EP(np.asarray(r["PV"]))
    return signalpack.frame(signalpack.pack(list(cols), np.asarray(sim["t"], float), cols.__getitem__, cap=None))


def _freq(code, p, sets):
    out = []
    for name, ctrl in sets.items():
        r = fq.response(code, p, ctrl)
        out.append(FreqSet(name=name, stable=bool(r["stable"]), Ms=_fin(r["Ms"]), GM=_fin(r["GM"]), PM=_fin(r["PM"]),
                           wc=_fin(r["wc"]), w180=_fin(r["w180"]), bw=_fin(fq.bandwidth(r)),
                           w=[float(x) for x in r["w"]], mag_db=[float(x) for x in r["mag_db"]],
                           phase_deg=[float(x) for x in r["phase_deg"]],
                           S_db=[float(x) for x in fq.db(r["S"])], T_db=[float(x) for x in fq.db(r["T"])],
                           re=[float(x) for x in r["L"].real], im=[float(x) for x in r["L"].imag]))
    return out


def _live_cascade(ws, proj):
    """Návrh kaskády z APC (jen čtení; stejný výpočet jako záložka APC) pro živou simulaci, nebo None."""
    from .apc_loops import _cas_state
    try:
        _, inner, _n, c = _cas_state(ws, proj, None)
    except Exception:
        return None
    if c is None or inner is None:
        return None
    src = ws.get("cas_src") or "manual"
    return dict(inner=dict(code=c["ci"], p=[float(x) for x in c["pi"]], ctrl=live.ctrl_js(c["ictrl"])),
                octrl=c["octrl"], source=str(src))


def router(get_proj, jobs):
    r = APIRouter(prefix="/workspaces/{wid}", tags=["tuning"])

    def need_model(wid):
        ws = get_proj(wid).state
        if not ws.has_data:
            raise HTTPException(409, "no data")
        if ws.model is None:
            raise HTTPException(409, "no model")
        return ws

    @r.get("/tuning", response_model=TuningInfo)
    def info(wid: str):
        ws = need_model(wid)
        return TuningInfo(model=ws.model[0], methods=list(ws.methods()), default_method=tun.DEFAULT_METHOD,
                          sets=_sets(ws), d_advice=_plain(ws.d_advice()), history=_plain(ws.history()),
                          controller=_loop_ref(ws),
                          tuning_params=[ParamRef(key=q["key"], name=q.get("name") or q["key"], unit=q.get("unit"),
                                                  role=q["role"]) for q in ctl.tuning_params(ws.controller)],
                          block_params=[BlockParam(**dict(q, value=_num(q["value"]), default=_num(q["default"])))
                                        for q in ws.block_rows()],
                          export_formats=list(tex.FORMATS))

    @r.post("/tuning/suggest", response_model=Suggestion)
    def suggest(wid: str, body: SuggestReq):
        """Návrh ladění metodou (výchozí: metoda uložená u modelu) s upozorněními a kontrolami věrohodnosti."""
        ws = need_model(wid)
        method = body.method or ws.get(f"method|{ws.get('mcode')}", tun.DEFAULT_METHOD)
        if method not in ws.methods():
            raise HTTPException(422, f"method not available: {method}")
        try:
            s = ws.suggest(method, body.tc)
        except (ValueError, RuntimeError) as ex:
            raise HTTPException(400, str(ex)) from ex
        code, p, _ = ws.model
        g1 = float(ws.get("set1_gain"))
        g1 = None if tun.is_placeholder(g1, float(ws.get("set1_ti")), float(ws.get("set1_td"))) else g1
        checks = lm.tuning_checks(code, p, float(s["Kc"]), float(ws.grid.Ts), g1)
        vals, warns = _view(ws, float(s["Kc"]), float(s["Ti"]), float(s["Td"]))
        base = ws.base_ctrl()
        tc = (body.tc or tun.default_tc(code, p, base["SampleTime"], method, ws.get("ctype"), base["DiffGain"])
              ) if method in ("SIMC", "iSIMC", "Lambda") else None
        rb = ws.ctrl_metrics(ws.ctrl_of(s), worst=False, mt=True)
        return Suggestion(method=method, Kc=float(s["Kc"]), Ti=float(s["Ti"]), Td=float(s["Td"]),
                          notes=[Note(key=k, args=_plain(a)) for k, a in s.get("notes", [])],
                          checks=[Note(key=k, args=_plain(a)) for k, a in checks], values=vals, warnings=warns, tc=tc,
                          robust=Robust(stable=bool(rb["stable"]), Ms=_fin(rb["Ms"]), Mt=_fin(rb.get("Mt")),
                                        GM=_fin(rb["GM"]), PM=_fin(rb["PM"])),
                          approximate=bool(rb.get("approximate")))

    @r.put("/tuning/sets/{n}", response_model=TuningInfo)
    def write_set(wid: str, n: int, body: WriteSet):
        """Parametry do sady 1 (současné nastavení) nebo 2 (nové); log = záznam do historie ladění."""
        ws = need_model(wid)
        if n not in (1, 2):
            raise HTTPException(404, "set not found")
        if body.values is not None:               # sada v jednotkách bloku → kanonická (přes profil)
            try:
                s = ws.values_to_canon(body.values)
            except (ValueError, KeyError, TypeError) as ex:
                raise HTTPException(422, str(ex)) from ex
        elif body.Kc is not None and body.Ti is not None:
            s = dict(Kc=body.Kc, Ti=body.Ti, Td=body.Td)
        else:
            raise HTTPException(422, "Kc and Ti, or values, required")
        ws.write_set(n, s, body.log)
        return info(wid)

    @r.post("/tuning/compare", response_model=JobInfo)
    def compare(wid: str):
        """Porovnání všech metod a kritérií pro PI i PID (úloha; výsledek: GET /jobs/{id}/result)."""
        from . import tasks
        ws = need_model(wid)
        jid = jobs.submit(tasks.run, ws.lean(), "compare_methods", timeout=1800)
        return job_info(jobs, jid)

    @r.get("/scenario", response_model=Scenario)
    def get_scenario(wid: str):
        ws = need_model(wid)
        T_end = float(ws._scenario_inputs(None)["T_end"])          # délka jako v simulaci (i ruční)
        return Scenario(kind=ws.scen_kind, kinds=list(scn.PRESETS), rows=_plain(ws.scen_rows(T_end)), T_end=T_end,
                        sp_from_to=list(ws.sp_from_to()))

    @r.put("/scenario", response_model=Scenario)
    def set_scenario(wid: str, body: ScenarioSet):
        """Druh scénáře (předvolba), vlastní události [[čas, vstup, …]], SP z → na, délka simulace."""
        ws = need_model(wid)
        if body.kind is not None:
            if body.kind not in scn.PRESETS:
                raise HTTPException(422, f"unknown scenario: {body.kind}")
            ws.set_scen_kind(body.kind)
        if body.sp_from_to is not None:
            ws.sim_sp = tuple(float(x) for x in body.sp_from_to[:2])
        if body.rows is not None:
            ws.set_scen_kind("custom")
            ws.set_scen_rows(body.rows, float(body.T_end or ws._scenario_inputs(None)["T_end"]))
        return get_scenario(wid)

    @r.post("/simulate", response_model=SimInfo)
    def simulate(wid: str, body: SimReq):
        """Simulace scénáře se sadou 1 a 2 (a návrhem `preview`): ukazatele odezvy."""
        ws = need_model(wid)
        sim = _sim(ws, body)
        return SimInfo(T_end=float(sim["T_end"]), src=sim.get("src"), kpis=_plain({str(k): v for k, v in
                                                                                   sim["kpis"].items()}))

    @r.post("/simulate/curves", response_class=Response,
            responses={200: {"content": {"application/octet-stream": {}},
                             "description": "app.signalpack.frame: sp, pv_1, mv_1, pv_2, mv_2 (pv_sug, mv_sug, "
                                            "pv_x…) in engineering units"}})
    def simulate_curves(wid: str, body: SimReq):
        ws = need_model(wid)
        return Response(_sim_frame(ws, _sim(ws, body)), media_type="application/octet-stream")

    @r.post("/frequency", response_model=list[FreqSet])
    def frequency(wid: str, preview: Pid | None = None):
        """Frekvenční charakteristiky (otevřená smyčka L, citlivost S a T) pro sadu 1, 2 a návrh."""
        ws = need_model(wid)
        code, p, _ = ws.model
        sets = {"set1": ws.set_ctrl(1), "set2": ws.set_ctrl(2)}
        if preview is not None:
            sets["sug"] = ws.ctrl_of(preview.model_dump())
        return _freq(code, p, {k: ws.ana_ctrl(c) for k, c in sets.items()})

    @r.get("/live", response_model=dict)
    def live_config(wid: str):
        """Konfigurace živé simulace pro prohlížeč (live_ui.js); texty v jazyce požadavku. Ladění: PUT /tuning/sets/2."""
        ws = need_model(wid)
        return _plain(live.web_config_ws(ws, _live_cascade(ws, get_proj(wid))))

    return r
