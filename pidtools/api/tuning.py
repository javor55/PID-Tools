"""
API – ladění a simulace (M10): sady parametrů a jejich robustnost, metody a návrh ladění s kontrolami, porovnání
metod (úloha), historie, scénář a simulace (souhrn i průběhy binárně), frekvenční charakteristiky.

Blok PIDConL (SampleTime, DiffGain, NormPV / NormMV, filtry, rychlosti …) a parametry metod (ctype, opt_ms,
opt_crit, opt_target, opt_ovs, opt_robust) se mění přes PATCH /settings.
"""
import numpy as np
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from ..app import frequency as fq
from ..app import live
from ..app import loopmode as lm
from ..app import scenario as scn
from ..app import signalpack
from ..app import tuning as tun
from .common import JobInfo, job_info
from .data import _plain


class Pid(BaseModel):
    Kc: float
    Ti: float
    Td: float = 0.0


class Note(BaseModel):
    key: str
    args: dict = {}


class Suggestion(Pid):
    method: str
    notes: list[Note] = []
    checks: list[Note] = []


class SuggestReq(BaseModel):
    method: str | None = None
    tc: float | None = None


class WriteSet(Pid):
    log: dict | None = None


class SetInfo(BaseModel):
    n: int
    gain: float
    ti: float
    td: float
    placeholder: bool
    metrics: dict | None = None


class TuningInfo(BaseModel):
    model: str | None
    methods: list[str]
    default_method: str
    sets: list[SetInfo]
    d_advice: dict | None = None
    history: list[dict] = []


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


def _fin(x):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return x if np.isfinite(x) else None


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
        out.append(SetInfo(n=n, gain=g, ti=ti, td=td, placeholder=tun.is_placeholder(g, ti, td), metrics=m))
    return out


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
                           S_db=[float(x) for x in fq.db(r["S"])], T_db=[float(x) for x in fq.db(r["T"])]))
    return out


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
                          sets=_sets(ws), d_advice=_plain(ws.d_advice()), history=_plain(ws.history()))

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
        return Suggestion(method=method, Kc=float(s["Kc"]), Ti=float(s["Ti"]), Td=float(s["Td"]),
                          notes=[Note(key=k, args=_plain(a)) for k, a in s.get("notes", [])],
                          checks=[Note(key=k, args=_plain(a)) for k, a in checks])

    @r.put("/tuning/sets/{n}", response_model=TuningInfo)
    def write_set(wid: str, n: int, body: WriteSet):
        """Parametry do sady 1 (současné nastavení) nebo 2 (nové); log = záznam do historie ladění."""
        ws = need_model(wid)
        if n not in (1, 2):
            raise HTTPException(404, "set not found")
        ws.write_set(n, dict(Kc=body.Kc, Ti=body.Ti, Td=body.Td), body.log)
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
        return _freq(code, p, sets)

    @r.get("/live", response_model=dict)
    def live_config(wid: str):
        """Konfigurace živé simulace pro prohlížeč (live_ui.js); texty v jazyce požadavku. Ladění: PUT /tuning/sets/2."""
        return _plain(live.web_config_ws(need_model(wid)))

    return r
