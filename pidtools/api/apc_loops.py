"""
API – techniky APC (M11b), druhá část: kaskáda, gain scheduling podle PV a podle regulační odchylky (ER), rozvazbení
a override; stejné výpočty jako okna desktopu (app.apc.cascade / gainsched / decouple / override).

Vstupy jsou klíče nastavení jako v desktopu a webu (cas_*, gs_*, gs_er_*; mění se přes PATCH /settings). Rozvazbení
a override nemají v desktopu uložené nastavení – jejich vstupy (typ decoupleru, amplitudy, výběr, skok, mez) jsou
parametry simulace. Techniky se dvěma smyčkami berou druhou smyčku projektu podle indexu `loop` (jako GET /loops;
výchozí je první jiná smyčka), projekt s jedinou smyčkou odpoví 409. Pomalé kroky (identifikace bodů gain scheduling,
model vnitřní smyčky z dat) běží jako úlohy a výsledek se uloží do pracovního prostoru.
"""
import re
from typing import Literal

import numpy as np
from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel, Field

from ..app import guides, signalpack
from ..app.apc import cascade as acas
from ..app.apc import decouple as adec
from ..app.apc import gainsched as ags
from ..app.apc import override as aov
from ..app.apc import recommend as reco
from ..app.apc.common import clean, tchar
from ..app.dataset import on_grid
from ..core import MODELS, default_tc, gs_issues, iae, robustness
from ..core.apc import rga_advice
from ..i18n import T
from .apc import ValueRow
from .common import JobInfo, job_info
from .data import _plain
from .tuning import Note, Pid

METHODS = ["SIMC", "AMIGO", "OPT"]


class LoopCheck(BaseModel):
    """Položka kontrolního seznamu struktury (app.guides): ok True / False / None = jen k ověření."""
    ok: bool | None
    text: str
    action: str | None = None


class Tuned(Pid):
    notes: list[Note] = []


class PointRow(BaseModel):
    input: str                   # X1 … X3, Gain1 … Gain3, TI1 … TI3, TD1 … TD3
    values: list[float | None]
    unit: str


def _fin(x):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return x if np.isfinite(x) else None


def _checks(items):
    return [LoopCheck(ok=ok, text=txt, action=act) for ok, txt, act in items]


def _tuned(r):
    return Tuned(Kc=float(r["Kc"]), Ti=float(r["Ti"]), Td=float(r["Td"]),
                 notes=[Note(key=k, args=_plain(a)) for k, a in r.get("notes", [])])


def _impl(kind, **kw):
    """Postup pro PCS 7 jako v desktopu: text bez zástupných položek jen, když nejsou potřeba (kw)."""
    raw = T("g_impl_" + kind)
    if kw:
        return T("g_impl_" + kind, **kw)
    return None if re.search(r"\{\w+\}", raw) else raw


def _frame(t, cols):
    t = np.asarray(t, float)
    bad = [k for k, v in cols.items() if len(v) != len(t)]
    if bad:
        raise HTTPException(500, f"inconsistent simulation grids: {', '.join(bad)}")
    return signalpack.frame(signalpack.pack(list(cols), t, cols.__getitem__, cap=None))


def _octets(data):
    return Response(data, media_type="application/octet-stream")


def _store(ws):
    """Výsledky výpočtů techniky, které nejsou v nastavení (model vnitřní smyčky z dat, poslední simulace)."""
    return ws.__dict__.setdefault("apc_loops", {})


def _a_record(proj):
    return dict(proj.state.report_record(), name=proj.names()[proj.active])


def _ep(rng):
    lo, hi = rng
    return lambda x: lo + np.asarray(x, float) * (hi - lo) / 100


# ---- kaskáda
class CascadeLoopRef(BaseModel):
    index: int
    name: str
    has_model: bool


class ParamRow(BaseModel):
    name: str
    value: float


class ModelOut(BaseModel):
    code: str
    params: list[ParamRow]


class CascadeInputs(BaseModel):
    source: str                  # loop | manual | data
    sources: list[str]
    loops: list[CascadeLoopRef]  # ostatní smyčky projektu (zdroj „loop“)
    loop: int | None             # zvolená smyčka vnitřní smyčky
    manual: list[float]          # K, T1, T2, θ
    inner_method: str
    outer_method: str
    outer_ctype: str
    methods: list[str]
    samp_i: float
    samp_default: float
    tci: float | None
    tci_default: float
    tci_edited: bool
    tco: float | None
    tco_default: float | None
    tco_edited: bool
    signals: list[str]


class CascadeFit(BaseModel):
    model: ModelOut
    fit: float


class CascadeInfo(BaseModel):
    model: str
    inputs: CascadeInputs
    inner_fit: CascadeFit | None = None
    inner_model: ModelOut | None = None
    inner_note: str | None = None        # smyčka bez modelu / zdroj bez dat
    inner: Tuned | None = None
    t63: float | None = None
    tc_eff: float | None = None
    outer_model: ModelOut | None = None
    outer: Tuned | None = None
    separation: float | None = None
    sep_warn: bool = False
    rows: list[ValueRow] = []
    impl_text: str | None = None
    checks: list[LoopCheck] = []


class CascadeReset(BaseModel):
    part: Literal["manual", "inner", "outer"]


class CascadeFitReq(BaseModel):
    ipv: str
    imv: str
    ilo: float | None = None     # rozsah vnitřní PV; výchozí = zaokrouhlené minimum a maximum z dat
    ihi: float | None = None


class CascadeSim(BaseModel):
    ok: bool                     # False = simulace nestabilní
    T_end: float | None = None
    t63: float
    separation: float
    iae_outer: float | None = None


def _model_out(code, p):
    return ModelOut(code=code, params=[ParamRow(name=n, value=float(v)) for n, v in zip(MODELS[code]["params"], p)])


def _cas_others(proj):
    return proj.others(include_without_model=True)


def _cas_inputs(ws, proj, loop, inner_calc):
    """Vstupy z nastavení (klíče cas_*); inner_calc = (tci0, tco0 nebo None) z posledního výpočtu."""
    others = _cas_others(proj)
    src = ws.get("cas_src") or ("loop" if others else "manual")
    if src not in ("loop", "manual", "data") or (src == "loop" and not others):
        src = "manual"
    ids = [i for i, _ in others]
    if loop is not None and loop not in ids:
        raise HTTPException(404, "loop not found")
    sel = loop if loop is not None else (ids[0] if ids else None)
    samp = float(ws.get("samp"))
    tci0, tco0 = inner_calc
    tci, tco = ws.get("cas_tci"), ws.get("cas_tco")
    ims, oms = ws.get("cas_im", "SIMC"), ws.get("cas_om", "SIMC")
    return CascadeInputs(
        source=src, sources=["loop", "manual", "data"],
        loops=[CascadeLoopRef(index=i, name=r["name"], has_model=r["model"] is not None) for i, r in others],
        loop=sel, manual=[float(ws.get(k, d)) for k, d in (("cas_k", 1.0), ("cas_t1", 5.0), ("cas_t2", 0.0),
                                                           ("cas_th", 1.0))],
        inner_method=ims if ims in METHODS else "SIMC", outer_method=oms if oms in METHODS else "SIMC",
        outer_ctype=ws.get("cas_oct") if ws.get("cas_oct") in ("PI", "PID") else "PI", methods=METHODS,
        samp_i=float(ws.get("cas_samp", samp)), samp_default=samp,
        tci=None if tci is None else float(tci), tci_default=float(tci0),
        tci_edited=tci is not None and abs(float(tci) - tci0) > 1e-9 * max(1.0, abs(tci0)),
        tco=None if tco is None else float(tco), tco_default=None if tco0 is None else float(tco0),
        tco_edited=tco is not None and tco0 is not None and abs(float(tco) - tco0) > 1e-9 * max(1.0, abs(tco0)),
        signals=[str(x) for x in ws.sig.sigs])


def _cas_inner(ws, proj, inp):
    """Model vnitřní smyčky podle zdroje: ((kód, p) nebo None, poznámka-klíč s argumenty)."""
    if inp.source == "loop":
        if inp.loop is None:
            return None, None
        rec = dict(_cas_others(proj))[inp.loop]
        if rec["model"] is None:
            return None, ("cas_loop_nomodel", dict(n=rec["name"]))
        return (rec["model"][0], list(rec["model"][1])), None
    if inp.source == "manual":
        return acas.manual_inner(*inp.manual), None
    fit = _store(ws).get("inner_fit")
    return (None if fit is None else (fit["code"], list(fit["p"]))), None


def _cas_calc(ws, inp, inner):
    """Ladění vnitřní a vnější smyčky jako v desktopu (CascadePanel._update)."""
    ci, pi = inner
    samp, dg = float(ws.get("samp")), float(ws.get("diffgain"))
    tci0 = default_tc(ci, pi, inp.samp_i)
    tci = (inp.tci if inp.tci and inp.tci > 0 else tci0) if inp.inner_method == "SIMC" else None
    si = acas.tune_loop(ci, pi, inp.inner_method, "PI", inp.samp_i, dg, tci)
    ictrl = acas.inner_ctrl(si, dg, inp.samp_i)
    t63, tc_eff = acas.inner_response(ci, pi, ictrl, inp.samp_i)
    co, po = acas.outer_model(ws.model, tc_eff, pi[-1])
    tco0 = default_tc(co, po, samp, "SIMC", inp.outer_ctype, dg)
    tco = (inp.tco if inp.tco and inp.tco > 0 else tco0) if inp.outer_method == "SIMC" else None
    so = acas.tune_loop(co, po, inp.outer_method, inp.outer_ctype, samp, dg, tco)
    octrl = dict(ws.base_ctrl(), Gain=so["Kc"], TI=so["Ti"], TD=so["Td"], MV_Lo=0.0, MV_Hi=100.0)
    return dict(ci=ci, pi=pi, si=si, ictrl=ictrl, t63=t63, tc_eff=tc_eff, co=co, po=po, so=so, octrl=octrl,
                tci0=tci0, tco0=tco0, tco=tco, sep=acas.separation(tco, so, t63))


def _cas_state(ws, proj, loop):
    """(vstupy, vnitřní model, poznámka, výpočet nebo None); výchozí τc se doplní po výpočtu."""
    inp = _cas_inputs(ws, proj, loop, (default_tc(*ws.model[:2], float(ws.get("samp"))), None))
    inner, note = _cas_inner(ws, proj, inp)
    if inner is None:
        return inp, None, note, None
    calc = _cas_calc(ws, inp, inner)
    inp = _cas_inputs(ws, proj, loop, (calc["tci0"], calc["tco0"]))
    return inp, inner, note, calc


def _cas_rows(c):
    rows = [ValueRow(param="inner.Gain", value=float(c["si"]["Kc"]), unit="–"),
            ValueRow(param="inner.TI", value=float(c["si"]["Ti"]), unit="s"),
            ValueRow(param="outer.Gain", value=float(c["so"]["Kc"]), unit="–"),
            ValueRow(param="outer.TI", value=float(c["so"]["Ti"]), unit="s")]
    if c["so"]["Td"] > 0:
        rows.append(ValueRow(param="outer.TD", value=float(c["so"]["Td"]), unit="s"))
    return rows


def _cas_info(ws, proj, loop):
    inp, inner, note, c = _cas_state(ws, proj, loop)
    a = _a_record(proj)
    out = dict(model=ws.model[0], inputs=inp, checks=_checks(guides.apc_cascade(a, _cas_others(proj))),
               impl_text=_impl("cascade"), inner_note=None if note is None else T(note[0], **note[1]))
    fit = _store(ws).get("inner_fit")
    if fit is not None:
        out["inner_fit"] = CascadeFit(model=_model_out(fit["code"], fit["p"]), fit=float(fit["fit"]))
    if inner is None:
        return CascadeInfo(**out)
    out.update(inner_model=_model_out(*inner), inner=_tuned(c["si"]), t63=float(c["t63"]), tc_eff=float(c["tc_eff"]),
               outer_model=_model_out(c["co"], c["po"]), outer=_tuned(c["so"]), separation=float(c["sep"]),
               sep_warn=bool(c["sep"] < 4), rows=_cas_rows(c))
    return CascadeInfo(**out)


def _cas_run(ws, proj, loop):
    """Simulace kaskády jako v desktopu: (vstupy, výpočet, (čas, sloupce, stabilní))."""
    inp, inner, _, c = _cas_state(ws, proj, loop)
    if inner is None:
        raise HTTPException(409, "no inner model")
    sim = acas.simulate(inner, c["ictrl"], (ws.model[0], ws.model[1]), c["octrl"], float(ws.get("samp")),
                        inp.samp_i, c["po"], c["co"], c["tco"])
    return inp, c, sim


def _cas_reset(ws, part):
    if part == "manual":
        ws.set(cas_k=1.0, cas_t1=5.0, cas_t2=0.0, cas_th=1.0)
    elif part == "inner":
        ws.settings.pop("cas_tci", None)
        ws.set(cas_samp=float(ws.get("samp")))
    else:
        ws.settings.pop("cas_tco", None)


def _fit_inner(ts, ipv, imv, Ts):
    """Model vnitřní smyčky z dat (v procesu úlohy)."""
    best, errs = acas.fit_inner(ts, ipv, imv, Ts)
    if best is None:
        raise ValueError("; ".join(T(e) for e in errs) or "fit failed")
    return dict(code=best["code"], p=[float(x) for x in best["p"]], fit=float(best["fit"]))


def _cas_fit_args(ws, body):
    """Podklady identifikace vnitřní smyčky z dat: (čas, vnitřní PV [%], vnitřní MV [%], Ts)."""
    sigs = {str(x) for x in ws.sig.sigs}
    bad = [c for c in (body.ipv, body.imv) if c not in sigs]
    if bad:
        raise HTTPException(422, f"unknown signal: {', '.join(bad)}")
    raw = on_grid(ws.sig, ws.grid, body.ipv)
    lo = float(np.floor(np.nanmin(raw))) if body.ilo is None else float(body.ilo)
    hi = float(np.ceil(np.nanmax(raw))) if body.ihi is None else float(body.ihi)
    m = ws.sel_mask
    ts = ws.segment()[0]
    return ts, (raw[m] - lo) / max(hi - lo, 1e-9) * 100, ws.M(on_grid(ws.sig, ws.grid, body.imv, zoh=True)[m]), ws.grid.Ts


# ---- gain scheduling podle PV
class GsInputs(BaseModel):
    n: int
    ranges: list[list[float]]    # úseky dat bodů [od, do] v s
    ranges_auto: bool            # úseky ještě nejsou v nastavení (návrh z dat)
    method: str
    methods: list[str]
    ctype: str
    tcf: float                   # násobek τc (SIMC)
    ms: float                    # limit Ms (OPT)
    tcf_default: float
    ms_default: float


class GsPoint(BaseModel):
    index: int
    x: float                     # pracovní bod PV a MV v inženýrských jednotkách
    u: float
    fit: float                   # shoda modelu [%]
    params: list[ParamRow]
    gain: float
    ti: float | None             # None = bez integrační složky
    td: float


class GsInfo(BaseModel):
    model: str
    integ: bool                  # proces s integrací: scheduling se nenavrhuje
    inputs: GsInputs
    fitted: bool                 # jsou identifikované body (aspoň 2)
    stale: bool                  # body jsou z jiných úseků / rozsahů než zadání
    points: list[GsPoint] = []
    issues: list[str] = []       # klíče gs_issue_*
    spread: float | None = None  # poměr největšího a nejmenšího lokálního zesílení
    table: list[PointRow] = []   # tabulka pro blok GainSched
    filled: bool = False         # třetí bod byl doplněn
    impl_text: str | None = None
    checks: list[LoopCheck] = []


class GsPointKpi(BaseModel):
    from_x: float
    to_x: float
    iae_fixed: float
    iae_sched: float


class GsSim(BaseModel):
    T_end: float
    kpis: list[GsPointKpi]


def _gs_valid(ws, v):
    t = ws.grid.t
    return isinstance(v, (list, tuple)) and len(v) == 2 and float(t[0]) <= v[0] < v[1] <= float(t[-1])


def _gs_n(ws):
    return 2 if ws.get("gs_n") == 2 else 3


def _gs_auto(ws, n):
    g = ws.grid
    return ags.auto_ranges(g.t, ws.pv, ws.mv, ws.sp, g.Ts, g.has_sp, 4 * tchar(ws.model), n)


def _gs_ranges(ws, n):
    """Úseky bodů z nastavení (gs_r1…), jinak automatický návrh: (úseky, z návrhu)."""
    cur = [ws.get(f"gs_r{i + 1}") for i in range(n)]
    if all(_gs_valid(ws, v) for v in cur):
        return [(float(a), float(b)) for a, b in cur], False
    return _gs_auto(ws, n), True


def _gs_inputs(ws):
    n = _gs_n(ws)
    rg, auto = _gs_ranges(ws, n)
    m, ct = ws.get("gs_m", "SIMC"), ws.get("gs_ct", "PI")
    return GsInputs(n=n, ranges=[list(r) for r in rg], ranges_auto=auto, method=m if m in METHODS else "SIMC",
                    methods=METHODS, ctype=ct if ct in ("PI", "PID") else "PI", tcf=float(ws.get("gs_tcf", 1.0)),
                    ms=float(ws.get("gs_ms", 1.6)), tcf_default=1.0, ms_default=1.6)


def _gs_points(ws, rg):
    """Identifikované body (po případném přepočtu na nové rozsahy NormPV / NormMV) a příznak zastaralosti."""
    pts_raw = ws.get("gs_pts")
    key = ags.key(ws.model[0], [tuple(x) for x in rg], ws.norm)
    if ws.get("gs_key") and pts_raw:
        new = ags.rescale(ws.get("gs_key"), key, pts_raw)
        if new is not None:
            ws.set(gs_pts=new, gs_key=key)
            pts_raw = new
    pts = ags.points(pts_raw)
    return pts, bool(pts) and ws.get("gs_key") != key


def _gs_tune(ws, inp, pts):
    code = ws.model[0]
    for q in pts:
        r = ags.tune_point(code, q["p"], inp.method, inp.ctype, float(ws.get("samp")), float(ws.get("diffgain")),
                           inp.tcf, inp.ms)
        q.update(gain=float(r["Kc"]), ti=float(r["Ti"]) if r["Ti"] > 0 else np.inf, td=float(r["Td"]))
    return pts


def _gs_spread(ws):
    ts, pv, mv, d = ws.segment()
    return reco.nl_spread(ws.model[0], ws.model[1], ws.model[2], ts, pv, mv, d, ws.grid.Ts)


def _gs_info(ws, proj):
    code = ws.model[0]
    integ = bool(MODELS[code]["integ"])
    inp = _gs_inputs(ws)
    a = _a_record(proj)
    if integ:
        return GsInfo(model=code, integ=True, inputs=inp, fitted=False, stale=False,
                      checks=_checks(guides.apc_gainsched(a, True)))
    pts, stale = _gs_points(ws, inp.ranges)
    spread = _gs_spread(ws)
    fitted = len(pts) >= 2
    issues = gs_issues(pts) if fitted else []
    out = dict(model=code, integ=False, inputs=inp, fitted=fitted, stale=stale, spread=spread, issues=list(issues),
               checks=_checks(guides.apc_gainsched(a, False, spread, pts, stale, issues)))
    if fitted:
        pts = _gs_tune(ws, inp, pts)
        tab, filled = ags.table(pts, ws.EP, ws.get("u_pv") or "PV")
        names = MODELS[code]["params"]
        out.update(points=[GsPoint(index=i, x=float(ws.EP(q["x"])), u=float(ws.EM(q["u"])), fit=float(q["fit"]),
                                   params=[ParamRow(name=n, value=float(v)) for n, v in zip(names, q["p"])],
                                   gain=q["gain"], ti=_fin(q["ti"]), td=q["td"]) for i, q in enumerate(pts)],
                   table=[PointRow(input=nm, values=[_fin(v) for v in vals], unit=u) for nm, vals, u in tab],
                   filled=bool(filled), impl_text=T("g_impl_gainsched", u=ws.get("u_pv") or "PV"))
    return GsInfo(**out)


def _gs_need(ws):
    if MODELS[ws.model[0]]["integ"]:
        raise HTTPException(409, "integrating process")


def _gs_run(ws):
    """Simulace na nelineárním procesu (jedna sada vs. scheduling) jako desktop; 409 bez identifikovaných bodů."""
    _gs_need(ws)
    inp = _gs_inputs(ws)
    pts, _ = _gs_points(ws, inp.ranges)
    if len(pts) < 2:
        raise HTTPException(409, "points not identified")
    pts = _gs_tune(ws, inp, pts)
    return ags.simulate_pv(ws.model[0], pts, ws.base_ctrl(), ws.set_ctrl(2), float(ws.get("samp")))


def _gs_frame(ws, sim):
    tf, of = sim["fixed"]
    ts_, os_ = sim["sched"]
    if not (len(tf) == len(ts_) == len(sim["t"])):
        raise HTTPException(500, "inconsistent simulation grids")
    return _frame(tf, {"sp": ws.EP(sim["sp"]), "pv_fixed": ws.EP(of["PV"]), "pv_sched": ws.EP(os_["PV"]),
                       "mv_fixed": ws.EM(of["MV"]), "mv_sched": ws.EM(os_["MV"]), "gain_fixed": of["Gain"],
                       "gain_sched": os_["Gain"]})


def _fit_points(code, ranges, t, pv, mv, Ts):
    """Identifikace modelu v úsecích bodů (v procesu úlohy); chyba úseku = chyba úlohy."""
    pts, err = ags.fit_points(code, ranges, t, pv, mv, Ts)
    if err:
        raise ValueError(err)
    return pts


# ---- gain scheduling podle regulační odchylky
class GsErInputs(BaseModel):
    E: float                     # práh |ER| [jednotky PV]
    k: float                     # násobek zesílení
    spstep: float                # skok SP [jednotky PV]
    d: float                     # porucha na vstupu [% MV]
    E_default: float
    k_default: float
    spstep_default: float
    d_default: float
    edited: bool


class GsErInfo(BaseModel):
    model: str
    integ: bool
    inputs: GsErInputs
    k_max: float | None = None   # největší bezpečný násobek (0 = nevyhoví ani sada sama)
    ms_k: float | None = None    # Ms při zesílení k·Gain (None = nestabilní)
    base: Tuned | None = None    # sada 2, ze které scheduling vychází
    table: list[PointRow] = []
    impl_text: str | None = None
    checks: list[LoopCheck] = []


class GsErKpi(BaseModel):
    name: str                    # fixed | sched | zone
    iae_sp: float
    iae_d: float
    maxdev: float
    sat: float
    settled: bool


class GsErScan(BaseModel):
    width: float                 # ConZone [jednotky PV]
    iae: float
    settled: bool


class GsErSim(BaseModel):
    T_end: float
    kpis: list[GsErKpi]
    zone: float | None = None    # nejlepší řídicí pásmo ConZone [jednotky PV]
    scan: list[GsErScan] = []


def _er_inputs(ws):
    PR = float(ws.PR)
    d = dict(E=round(0.05 * PR, 6), k=2.0, spstep=round(0.2 * PR, 6), d=10.0)
    cur = {x: float(ws.get(f"gs_er_{x}", dv)) for x, dv in d.items()}
    return GsErInputs(**cur, **{f"{x}_default": v for x, v in d.items()},
                      edited=any(abs(cur[x] - d[x]) > 1e-9 * max(1.0, abs(d[x])) for x in d))


def _er_set2(ws):
    return clean(ws.set_ctrl(2))


def _er_info(ws, proj):
    code, p, _ = ws.model
    inp = _er_inputs(ws)
    if MODELS[code]["integ"]:
        return GsErInfo(model=code, integ=True, inputs=inp, checks=_checks(guides.apc_gs_er(_a_record(proj), np.inf)))
    set2 = _er_set2(ws)
    rb = robustness(code, list(p), dict(set2, Gain=inp.k * set2["Gain"]))
    ms_k = rb["Ms"] if rb["stable"] and np.isfinite(rb["Ms"]) else np.inf
    u_pv = ws.get("u_pv") or "PV"
    return GsErInfo(model=code, integ=False, inputs=inp, k_max=ags.k_max(code, p, ws.set_ctrl(2)), ms_k=_fin(ms_k),
                    base=Tuned(Kc=float(set2["Gain"]), Ti=float(set2["TI"]), Td=float(set2.get("TD", 0.0))),
                    table=[PointRow(input=nm, values=[_fin(v) for v in vals], unit=u)
                           for nm, vals, u in ags.er_table(inp.E, inp.k, set2, u_pv)],
                    impl_text=T("g_impl_gs_er", u=u_pv), checks=_checks(guides.apc_gs_er(_a_record(proj), ms_k)))


def _er_run(ws):
    """Simulace jako desktop; výsledek se drží u prostoru (stejné vstupy → bez nového výpočtu)."""
    code, p, _ = ws.model
    if MODELS[code]["integ"]:
        raise HTTPException(409, "integrating process")
    inp = _er_inputs(ws)
    set2, PR = _er_set2(ws), float(ws.PR)
    key = (code, tuple(p), inp.E, inp.k, inp.spstep, inp.d, tuple(sorted(set2.items())), float(ws.get("samp")))
    st = _store(ws)
    if st.get("er_key") != key:
        step_pct = float(max(-45, min(45, inp.spstep / PR * 100)))
        r = ags.simulate_er(code, p, set2, inp.E / PR * 100, inp.k, step_pct, inp.d, float(ws.get("samp")))
        st["er_key"], st["er"] = key, r
    return st["er"], set2, PR


def _er_curves(r):
    """Průběhy variant: (název, (čas, výsledek)); ConZone jen když se našlo."""
    out = [("fixed", r["fixed"]), ("sched", r["sched"])]
    if r["zone"] is not None:
        out.append(("zone", (r["t"], r["zone"])))
    return out


# ---- rozvazbení a override: druhá smyčka projektu
def _pair(proj, loop):
    """(index druhé smyčky, záznam A, záznam B); 409 u projektu s jedinou smyčkou nebo smyčky bez modelu."""
    others = dict(_cas_others(proj))
    if not others:
        raise HTTPException(409, "project has only one loop")
    bi = next(iter(others)) if loop is None else loop
    if bi not in others:
        raise HTTPException(404, "loop not found")
    b = others[bi]
    if b["model"] is None:
        raise HTTPException(409, "loop has no model")
    return bi, _a_record(proj), b


class LoopHead(BaseModel):
    loop: int                    # index druhé smyčky (jako GET /loops)
    a: str
    b: str
    loops: list[CascadeLoopRef]  # ostatní smyčky projektu k výběru


def _head(proj, bi, a, b):
    return dict(loop=bi, a=a["name"], b=b["name"],
                loops=[CascadeLoopRef(index=i, name=r["name"], has_model=r["model"] is not None)
                       for i, r in _cas_others(proj)])


class DecParam(BaseModel):
    source_mv: str
    target: str
    gain: float                  # [% rozsahu MV cíle / % rozsahu MV zdroje]
    gain_eng: float              # v jednotkách MV
    lead: float
    lag: float
    delay: float


class DecDefaults(BaseModel):
    dtype: str
    amp_a: float
    amp_b: float


class DecInfo(LoopHead):
    ok: bool                     # existuje aspoň jedna vazba mezi smyčkami
    lam: float | None = None     # RGA λ11
    advice_key: str | None = None
    advice: str | None = None
    params: list[DecParam] = []
    defaults: DecDefaults
    impl_text: str | None = None
    checks: list[LoopCheck] = []


class DecSimReq(BaseModel):
    dtype: Literal["static", "dyn"] = "dyn"
    amp_a: float = Field(5.0, ge=-100, le=100)
    amp_b: float = Field(5.0, ge=-100, le=100)


class DecIae(BaseModel):
    variant: str                 # none | static | dyn
    iae_a: float                 # [jednotky PV]
    iae_b: float


class DecSim(BaseModel):
    dtype: str
    T_end: float
    kpis: list[DecIae]


def _dec_info(proj, bi, a, b):
    dz = adec.design(a, b)
    out = dict(**_head(proj, bi, a, b), defaults=DecDefaults(dtype="dyn", amp_a=5.0, amp_b=5.0),
               impl_text=_impl("decouple"),
               checks=_checks(guides.apc_decouple(a, b, proj.active, bi, dz["xab"], dz["xba"])))
    if dz["xab"] is None and dz["xba"] is None:
        return DecInfo(ok=False, **out)
    lam = dz["lam"]
    return DecInfo(ok=True, lam=_fin(lam), advice_key=rga_advice(lam), **out,
                   advice=T(rga_advice(lam), a=a["name"], b=b["name"], mva=a["c_mv"], mvb=b["c_mv"]),
                   params=[DecParam(source_mv=str(s), target=str(d), gain=float(g), gain_eng=float(ge),
                                    lead=float(ld), lag=float(lg), delay=float(dl))
                           for s, d, g, ge, ld, lg, dl in adec.params(dz, a, b)])


def _dec_run(proj, loop, body):
    bi, a, b = _pair(proj, loop)
    dz = adec.design(a, b)
    if dz["xab"] is None and dz["xba"] is None:
        raise HTTPException(409, "no cross coupling")
    runs = adec.simulate(dz, clean(a["ctrl"]), clean(b["ctrl"]), body.amp_a, body.amp_b)
    return a, b, runs


def _dec_frame(a, b, runs, dtype):
    tt, o_ref = runs["none"]
    _, o = runs[dtype]
    ea, eb, ma, mb = _ep(a["pv_rng"]), _ep(b["pv_rng"]), _ep(a["mv_rng"]), _ep(b["mv_rng"])
    return _frame(tt, {"sp_a": ea(o["SP_A"]), "pv_a_none": ea(o_ref["PV_A"]), "pv_a": ea(o["PV_A"]),
                       "sp_b": eb(o["SP_B"]), "pv_b_none": eb(o_ref["PV_B"]), "pv_b": eb(o["PV_B"]),
                       "mv_a": ma(o["MV_A"]), "mv_b": mb(o["MV_B"])})


class OvDefaults(BaseModel):
    step: float                  # skok SP hlavní smyčky A [jednotky PV A]
    lim: float                   # mez PV omezující smyčky B [jednotky PV B]


class OvInfo(LoopHead):
    sel: str
    sels: list[str]
    defaults: OvDefaults
    mv_differs: bool             # smyčky nemají společný ventil (MV)
    mv_a: str
    mv_b: str
    impl_text: str | None = None
    checks: list[LoopCheck] = []


class OvSimReq(BaseModel):
    sel: Literal["min", "max"] = "min"
    step: float | None = None    # chybí = výchozí scénář (aov.defaults)
    lim: float | None = None


class OvKpi(BaseModel):
    peak: float                  # nejhorší PV B s výběrem [jednotky PV B]
    peak_without: float
    share: float                 # podíl času řízení omezujícím regulátorem
    switches: int


class OvSim(BaseModel):
    sel: str
    step: float
    lim: float
    T_end: float
    kpis: OvKpi


def _ov_info(proj, bi, a, b, sel):
    step, lim = aov.defaults(a, b, sel)
    return OvInfo(**_head(proj, bi, a, b), sel=sel, sels=["min", "max"], defaults=OvDefaults(step=float(step),
                  lim=float(lim)), mv_differs=b["c_mv"] != a["c_mv"], mv_a=str(a["c_mv"]), mv_b=str(b["c_mv"]),
                  impl_text=_impl("override", a=a["name"], b=b["name"], s=T("ov_" + sel), lim=f"{lim:.4g}",
                                  u=b["u_pv"] or ""),
                  checks=_checks(guides.apc_override(a, b, bi)))


def _ov_run(proj, loop, body):
    bi, a, b = _pair(proj, loop)
    d_step, d_lim = aov.defaults(a, b, body.sel)
    step = float(d_step if body.step is None else body.step)
    lim = float(d_lim if body.lim is None else body.lim)
    tt, o, o0 = aov.simulate(a, b, step, lim, body.sel)
    return a, b, (step, lim), (tt, o, o0)


def _ov_frame(a, b, tt, o, o0):
    ea, eb, ma = _ep(a["pv_rng"]), _ep(b["pv_rng"]), _ep(a["mv_rng"])
    return _frame(tt, {"sp_a": ea(o["SP_A"]), "pv_a_without": ea(o0["PV_A"]), "pv_a": ea(o["PV_A"]),
                       "lim_b": eb(o["SP_B"]), "pv_b_without": eb(o0["PV_B"]), "pv_b": eb(o["PV_B"]),
                       "u_a": ma(o["U_A"]), "u_b": ma(o["U_B"]), "mv": ma(o["MV"])})


_LOOP_Q = Query(None, ge=0, description="index of the second loop of the project (as in GET /loops)")
_CURVES = {200: {"content": {"application/octet-stream": {}}}}


class _Deps:
    """Závislosti endpointů: přístup k projektu a správce úloh."""

    def __init__(self, get_proj, jobs):
        self.get_proj, self.jobs = get_proj, jobs

    def need_model(self, wid):
        ws = self.get_proj(wid).state
        if not ws.has_data:
            raise HTTPException(409, "no data")
        if ws.model is None:
            raise HTTPException(409, "no model")
        return ws

    def need_proj(self, wid):
        self.need_model(wid)
        return self.get_proj(wid)

    def stored(self, wid, ws):
        """Smyčka ještě patří do projektu (prostor mezitím nemusel zaniknout) – výsledek úlohy se smí zapsat."""
        try:
            proj = self.get_proj(wid)
        except HTTPException:
            return False
        return any(x is ws for x in proj.loops)


def _routes_cascade(r, d):
    # ---- kaskáda
    @r.get("/apc/cascade", response_model=CascadeInfo)
    def cascade_get(wid: str, loop: int | None = _LOOP_Q):
        """Kaskáda (aktivní smyčka = vnější): zdroj modelu vnitřní smyčky, ladění obou smyček, oddělení rychlostí."""
        proj = d.need_proj(wid)
        return _cas_info(proj.state, proj, loop)

    @r.post("/apc/cascade/reset", response_model=CascadeInfo)
    def cascade_reset(wid: str, body: CascadeReset, loop: int | None = _LOOP_Q):
        """Původní hodnoty: ruční model (K, T1, T2, θ), ladění vnitřní smyčky (SampleTime, τc) nebo vnější (τc)."""
        proj = d.need_proj(wid)
        _cas_reset(proj.state, body.part)
        return _cas_info(proj.state, proj, loop)

    @r.post("/apc/cascade/fit", response_model=JobInfo)
    def cascade_fit(wid: str, body: CascadeFitReq):
        """Model vnitřní smyčky z dat (úloha, P1D / P2D); výsledek se uloží, dále GET /apc/cascade (zdroj data)."""
        ws = d.need_model(wid)
        ts, ipv, imv, Ts = _cas_fit_args(ws, body)

        def done(res):
            if d.stored(wid, ws):
                _store(ws)["inner_fit"] = res
        jid = d.jobs.submit(_fit_inner, ts, ipv, imv, float(Ts), timeout=600, on_done=done)
        return job_info(d.jobs, jid)

    @r.post("/apc/cascade/simulate", response_model=CascadeSim)
    def cascade_simulate(wid: str, loop: int | None = _LOOP_Q):
        """Skok SP vnější smyčky a poruchy obou smyček: stabilita, doba odezvy vnitřní smyčky, IAE vnější smyčky."""
        proj = d.need_proj(wid)
        ws = proj.state
        _, c, (ts, oc, ok) = _cas_run(ws, proj, loop)
        iae_o = float(iae(ts, oc[:, 0], oc[:, 1]) * ws.PR / 100) if ok else None
        return CascadeSim(ok=ok, T_end=float(ts[-1]) if ok else None, t63=float(c["t63"]), separation=float(c["sep"]),
                          iae_outer=iae_o)

    @r.post("/apc/cascade/simulate/curves", response_class=Response,
            responses={200: {"content": {"application/octet-stream": {}},
                             "description": "app.signalpack.frame: sp_o, pv_o in engineering units of PV, "
                                            "sp_i, pv_i, valve in %; 409 when the simulation is unstable"}})
    def cascade_curves(wid: str, loop: int | None = _LOOP_Q):
        proj = d.need_proj(wid)
        ws = proj.state
        _, _, (ts, oc, ok) = _cas_run(ws, proj, loop)
        if not ok:
            raise HTTPException(409, "simulation unstable")
        return _octets(_frame(ts, {"sp_o": ws.EP(oc[:, 0]), "pv_o": ws.EP(oc[:, 1]), "sp_i": oc[:, 2],
                                   "pv_i": oc[:, 3], "valve": oc[:, 4]}))


def _routes_gs(r, d):
    # ---- gain scheduling podle PV
    @r.get("/apc/gainsched", response_model=GsInfo)
    def gs_get(wid: str):
        """Gain scheduling podle PV: úseky bodů, identifikované body, ladění v bodech, tabulka pro GainSched."""
        proj = d.need_proj(wid)
        return _gs_info(proj.state, proj)

    @r.post("/apc/gainsched/auto", response_model=GsInfo)
    def gs_auto(wid: str):
        """Úseky bodů znovu z automatického návrhu (do gs_r1 …); body zůstanou, ale označí se jako zastaralé."""
        proj = d.need_proj(wid)
        ws = proj.state
        _gs_need(ws)
        n = _gs_n(ws)
        ws.set(**{f"gs_r{i + 1}": [float(a), float(b)] for i, (a, b) in enumerate(_gs_auto(ws, n))})
        return _gs_info(ws, proj)

    @r.post("/apc/gainsched/reset", response_model=GsInfo)
    def gs_reset(wid: str):
        """Původní hodnoty ladění bodů: násobek τc = 1, Ms = 1,6."""
        proj = d.need_proj(wid)
        proj.state.set(gs_tcf=1.0, gs_ms=1.6)
        return _gs_info(proj.state, proj)

    @r.post("/apc/gainsched/fit", response_model=JobInfo)
    def gs_fit(wid: str):
        """Identifikace modelu v úsecích bodů (úloha); úseky se uloží do gs_r*, body do gs_pts / gs_key."""
        ws = d.need_model(wid)
        _gs_need(ws)
        rg, _ = _gs_ranges(ws, _gs_n(ws))
        ws.set(**{f"gs_r{i + 1}": [float(a), float(b)] for i, (a, b) in enumerate(rg)})
        code, g = ws.model[0], ws.grid
        key = ags.key(code, rg, ws.norm)

        def done(pts):
            if d.stored(wid, ws):
                ws.set(gs_pts=pts, gs_key=key)
        jid = d.jobs.submit(_fit_points, code, rg, np.asarray(g.t), np.asarray(ws.pv), np.asarray(ws.mv), float(g.Ts),
                          timeout=900, on_done=done)
        return job_info(d.jobs, jid)

    @r.post("/apc/gainsched/simulate", response_model=GsSim)
    def gs_simulate(wid: str):
        """Nelineární proces z bodů: SP do všech bodů a zpět, porucha v každém úseku; IAE jedna sada vs. scheduling."""
        ws = d.need_model(wid)
        sim = _gs_run(ws)
        f = ws.PR / 100
        return GsSim(T_end=float(sim["t"][-1]), kpis=[
            GsPointKpi(from_x=float(ws.EP(a)), to_x=float(ws.EP(b)), iae_fixed=float(i1 * f), iae_sched=float(i2 * f))
            for a, b, i1, i2 in sim["iae"]])

    @r.post("/apc/gainsched/simulate/curves", response_class=Response,
            responses={200: {"content": {"application/octet-stream": {}},
                             "description": "app.signalpack.frame: sp, pv_fixed, pv_sched, mv_fixed, mv_sched, "
                                            "gain_fixed, gain_sched in engineering units"}})
    def gs_curves(wid: str):
        ws = d.need_model(wid)
        return _octets(_gs_frame(ws, _gs_run(ws)))


def _routes_er(r, d):
    # ---- gain scheduling podle regulační odchylky
    @r.get("/apc/gainsched_er", response_model=GsErInfo)
    def er_get(wid: str):
        """Gain scheduling podle ER: vstupy (gs_er_*), největší bezpečný násobek k, tabulka pro GainSched."""
        proj = d.need_proj(wid)
        return _er_info(proj.state, proj)

    @r.post("/apc/gainsched_er/reset", response_model=GsErInfo)
    def er_reset(wid: str):
        """Původní hodnoty: práh E = 5 % rozsahu PV, k = 2, skok SP = 20 % rozsahu PV, porucha 10 %."""
        proj = d.need_proj(wid)
        for k in ("E", "k", "spstep", "d"):
            proj.state.settings.pop(f"gs_er_{k}", None)
        return _er_info(proj.state, proj)

    @r.post("/apc/gainsched_er/simulate", response_model=GsErSim)
    def er_simulate(wid: str):
        """Skok SP a porucha: jedna sada vs. scheduling podle ER vs. nejlepší řídicí pásmo ConZone (výpočet ~2 s,
        stejné vstupy se nepočítají znovu)."""
        ws = d.need_model(wid)
        res, set2, PR = _er_run(ws)
        t, sp, tp = res["t"], res["sp"], res["tp"]
        kp = [GsErKpi(name=n, **ags.er_kpis(t, sp, tp, o, set2, PR)) for n, (_, o) in _er_curves(res)]
        f = PR / 100
        return GsErSim(T_end=float(t[-1]), kpis=kp, zone=None if res["cz"] is None else float(res["cz"] * f),
                       scan=[GsErScan(width=float(w * f), iae=float(v * f), settled=bool(ok))
                             for w, v, ok in res["scan"]])

    @r.post("/apc/gainsched_er/simulate/curves", response_class=Response,
            responses={200: {"content": {"application/octet-stream": {}},
                             "description": "app.signalpack.frame: sp, pv_*, mv_*, gain_* for fixed and sched, "
                                            "pv_zone, mv_zone with ConZone, in engineering units"}})
    def er_curves(wid: str):
        ws = d.need_model(wid)
        res, _, _ = _er_run(ws)
        cols = {"sp": ws.EP(res["sp"])}
        for n, (tt, o) in _er_curves(res):
            if len(tt) != len(res["t"]):
                raise HTTPException(500, "inconsistent simulation grids")
            cols[f"pv_{n}"], cols[f"mv_{n}"] = ws.EP(o["PV"]), ws.EM(o["MV"])
            if n != "zone":
                cols[f"gain_{n}"] = o["Gain"]
        return _octets(_frame(res["t"], cols))


def _routes_dec(r, d):
    # ---- rozvazbení
    @r.get("/apc/decouple", response_model=DecInfo)
    def dec_get(wid: str, loop: int | None = _LOOP_Q):
        """Rozvazbení 2×2 s druhou smyčkou projektu: RGA, parametry decouplerů pro PCS 7."""
        proj = d.need_proj(wid)
        return _dec_info(proj, *_pair(proj, loop))

    @r.post("/apc/decouple/simulate", response_model=DecSim)
    def dec_simulate(wid: str, body: DecSimReq, loop: int | None = _LOOP_Q):
        """Změny SP obou smyček bez rozvazbení, se statickými a s dynamickými decouplery: IAE v jednotkách PV."""
        a, b, runs = _dec_run(d.need_proj(wid), loop, body)
        return DecSim(dtype=body.dtype, T_end=float(runs["none"][0][-1]),
                      kpis=[DecIae(variant=v, iae_a=float(x), iae_b=float(y)) for v, x, y in adec.iae_table(runs, a, b)])

    @r.post("/apc/decouple/simulate/curves", response_class=Response,
            responses={200: {"content": {"application/octet-stream": {}},
                             "description": "app.signalpack.frame: sp_a, pv_a_none, pv_a, sp_b, pv_b_none, pv_b, "
                                            "mv_a, mv_b in engineering units of the loops (pv_* with the chosen "
                                            "decoupler)"}})
    def dec_curves(wid: str, body: DecSimReq, loop: int | None = _LOOP_Q):
        a, b, runs = _dec_run(d.need_proj(wid), loop, body)
        return _octets(_dec_frame(a, b, runs, body.dtype))


def _routes_ov(r, d):
    # ---- override
    @r.get("/apc/override", response_model=OvInfo)
    def ov_get(wid: str, loop: int | None = _LOOP_Q, sel: Literal["min", "max"] = "min"):
        """Override s druhou smyčkou projektu: výchozí scénář (skok SP hlavní smyčky, mez omezující smyčky)."""
        proj = d.need_proj(wid)
        return _ov_info(proj, *_pair(proj, loop), sel)

    @r.post("/apc/override/simulate", response_model=OvSim)
    def ov_simulate(wid: str, body: OvSimReq, loop: int | None = _LOOP_Q):
        """Simulace s výběrem MIN / MAX a bez něj; skok a mez chybějící v těle = výchozí scénář."""
        a, b, (step, lim), (tt, o, o0) = _ov_run(d.need_proj(wid), loop, body)
        return OvSim(sel=body.sel, step=step, lim=lim, T_end=float(tt[-1]), kpis=OvKpi(**aov.kpis(a, b, o, o0, body.sel)))

    @r.post("/apc/override/simulate/curves", response_class=Response,
            responses={200: {"content": {"application/octet-stream": {}},
                             "description": "app.signalpack.frame: sp_a, pv_a_without, pv_a, lim_b, pv_b_without, "
                                            "pv_b, u_a, u_b, mv in engineering units"}})
    def ov_curves(wid: str, body: OvSimReq, loop: int | None = _LOOP_Q):
        a, b, _, (tt, o, o0) = _ov_run(d.need_proj(wid), loop, body)
        return _octets(_ov_frame(a, b, tt, o, o0))


def router(get_proj, jobs):
    r = APIRouter(prefix="/workspaces/{wid}", tags=["apc"])
    d = _Deps(get_proj, jobs)
    for fn in (_routes_cascade, _routes_gs, _routes_er, _routes_dec, _routes_ov):
        fn(r, d)
    return r
