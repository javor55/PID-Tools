"""
Ladění PIDConL: dostupné metody, návrh parametrů (pravidla i optimalizace), srovnání metod, robustnost sad.

Optimalizace se volají přes funkce opt_migo / opt_time / opt_scenario s hashovatelnými argumenty (n-tice),
aby si je frontend mohl uložit do cache (web: st.cache_data). Návrh `suggest` je bere jako parametr `solvers`.
"""
from dataclasses import dataclass
from types import SimpleNamespace

import numpy as np

from .. import core
from ..core import (closed_loop_steps, default_tc, integ_gain, mv_noise, overshoot_ratio, robustness, tune)

CRITERIA = ("MIGO", "IAE", "ISE", "ITAE", "OVS")
TARGETS = ("dist", "sp", "both", "scen")


# ---- optimalizace s hashovatelnými argumenty (cache ve frontendu)
def opt_migo(code, p, ctype, samp, dg, ms, hf, starts, extra=(), pvf=0.0):
    return core.optimize_migo(code, list(p), ctype, samp, dg, ms, hf, starts, [list(e) for e in extra], pvf)


def opt_time(code, p, ctype, samp, dg, crit, target, ms, hf, starts, extra=(), ovs=0.02, pfac=1.0, dfb=True,
             pvf=0.0, rate=0.0, sp_amp=1.0, d_amp=1.0):
    return core.optimize_time(code, list(p), ctype, samp, dg, crit, target, ms, hf, starts, [list(e) for e in extra],
                              ovs, pfac, dfb, pvf, rate, sp_amp, d_amp)


def opt_scenario(code, p, pdl, ctype, ctrl_base, crit, h, sp, pv0, mv0, dmeas, dist_mv, dist_pv, ms, hf, starts,
                 extra=(), ovs=0.02):
    return core.optimize_scenario(code, list(p), [list(d) for d in pdl], ctype, dict(ctrl_base), crit, h,
                                  np.asarray(sp), pv0, mv0, [np.asarray(d) for d in dmeas], np.asarray(dist_mv),
                                  np.asarray(dist_pv), ms, hf, starts, [list(e) for e in extra], ovs)


SOLVERS = SimpleNamespace(opt_migo=opt_migo, opt_time=opt_time, opt_scenario=opt_scenario)


# ---- metody a nastavení
# výchozí návrh: optimalizace PI na IAE s omezením překmitu, skok SP i porucha
DEFAULT_METHOD, DEFAULT_CRIT, DEFAULT_TARGET = "OPT", "OVS", "both"


def methods(code, p):
    """Metody ladění dostupné pro model (iSIMC jen pro P1D/P2D, průměrování jen s integračním zesílením)."""
    return (["SIMC"] + (["iSIMC"] if code in ("P1D", "P2D") else []) + ["Lambda", "AMIGO", "OPT"]
            + (["AVG"] if integ_gain(code, p) is not None and code != "P0D" else []))


def p_eff(p, samp):
    """Model s efektivním zpožděním (+ polovina SampleTime za vzorkování regulátoru)."""
    return list(p[:-1]) + [p[-1] + samp / 2]


def corner_models(p):
    """Rohové modely pro robustní optimalizaci bez bootstrapu: K × 0,8 / 1,2, θ × 0,8 / 1,3."""
    out = []
    for kf in (0.8, 1.2):
        for tf in (0.8, 1.3):
            q = list(p)
            q[0] *= kf
            q[-1] *= tf
            out.append(tuple(q))
    return out


def robust_models(p, unc_models, on):
    """Modely, na kterých musí optimalizace splnit Ms: varianty z nejistoty (nejvýš 15), jinak rohové modely."""
    if not on:
        return ()
    return tuple(tuple(q) for q in unc_models[:15]) if unc_models else tuple(corner_models(p))


def hf_max(noise_e, mv_range, sigma_pv):
    """Limit vysokofrekvenčního zesílení regulátoru z povoleného šumu MV [jednotky MV] a šumu PV [%]."""
    return (noise_e / mv_range * 100) / sigma_pv if (noise_e and sigma_pv > 0) else None


@dataclass
class Request:
    """Požadavek na návrh: metoda, typ regulátoru a její nastavení."""
    method: str = "SIMC"
    ctype: str = "PI"
    tc: float = None               # τc (SIMC, iSIMC, Lambda); None = výchozí
    avg: tuple = None              # (ΔPV %, ΔMV %) pro průměrování
    ms: float = 1.6                # limit Ms (optimalizace)
    hf: float = None               # limit šumu MV (PID)
    crit: str = "MIGO"
    target: str = "both"
    ovs: float = 0.02


def suggest(code, p, pdl, base_ctrl, req, robust=(), scen=None, solvers=SOLVERS):
    """
    Návrh parametrů {Kc, Ti, Td, notes}. base_ctrl = konfigurace bloku (SampleTime, DiffGain, PropFacSP, …);
    scen = sestavený scénář (dict h, sp, pv0, mv0, dmeas, dmv, dpv, plant, sp_amp, d_amp) pro cíl „scen“.
    """
    samp, dg = base_ctrl["SampleTime"], base_ctrl["DiffGain"]
    ct = req.ctype
    if req.method != "OPT":
        tc = req.tc if req.tc else default_tc(code, p, samp, req.method, ct, dg)
        return tune(code, p, req.method, tc, ct, samp, req.avg)
    pvf = base_ctrl.get("PVFilt", 0.0) or 0.0
    starts = []
    for m0 in ("SIMC", "AMIGO"):
        r0 = tune(code, p, m0, default_tc(code, p, samp, m0, ct, dg), ct, samp)
        starts.append((r0["Kc"], r0["Ti"], r0["Td"]))
    mg = solvers.opt_migo(code, tuple(p), ct, samp, dg, req.ms, req.hf, tuple(starts), robust, pvf)
    if req.crit == "MIGO":
        return mg
    starts.append((mg["Kc"], mg["Ti"], mg["Td"]))
    sp_amp, d_amp = (scen["sp_amp"], scen["d_amp"]) if scen else (5.0, 5.0)
    tg_lin = "both" if req.target == "scen" else req.target
    lin = solvers.opt_time(code, tuple(p), ct, samp, dg, req.crit, tg_lin, req.ms, req.hf, tuple(starts), robust,
                           req.ovs, core.propfac(base_ctrl), base_ctrl.get("DiffFbk", True), pvf,
                           base_ctrl.get("MVRate", 0.0), sp_amp, d_amp)
    if req.target != "scen":
        return lin
    if scen is None:
        return dict(lin, notes=lin["notes"] + [("note_scen_missing", {})])
    starts.append((lin["Kc"], lin["Ti"], lin["Td"]))
    cb = dict(base_ctrl, **scen["plant"])
    return solvers.opt_scenario(code, tuple(p), tuple(tuple(d) for d in pdl), ct, cb, req.crit, scen["h"], scen["sp"],
                                scen["pv0"], scen["mv0"], tuple(scen["dmeas"]), scen["dmv"], scen["dpv"], req.ms, req.hf,
                                tuple(starts), robust, req.ovs)


def compare(code, p, pdl, base_ctrl, req, avg=None, sigma_pv=0.0, robust=(), solvers=SOLVERS, robustness_fn=robustness):
    """
    Srovnání všech metod (a kritérií optimalizace) pro PI i PID: [{method, crit, ctype, Kc, Ti, Td, Ms, iae_load,
    iae_sp, ovs [%], noise [% MV]}]. req: společné nastavení (Ms, šum, cíl, překmit); avg: nastavení průměrování
    (bez něj se metoda vynechá). Optimalizace na scénáři se nahradí lineárním cílem „both“ (je pomalá).
    """
    samp = base_ctrl["SampleTime"]
    pe = p_eff(p, samp)
    T_c = pe[-1] + (p[1] if code in ("P1D", "P2D", "I1D") else 0) + samp
    T_cmp = max(25 * T_c, 100 * samp)
    h = max(samp, T_cmp / 6000)
    n = int(T_cmp / h) + 1
    variants = []
    for m in methods(code, p):
        variants += [("OPT", c) for c in CRITERIA] if m == "OPT" else [(m, None)]
    out = []
    for m, cr in variants:
        if m == "AVG" and avg is None:
            continue
        for ct in ("PI", "PID"):
            tg = "both" if req.target == "scen" else req.target
            if cr == "OVS" and tg == "dist":
                tg = "sp"            # překmit má smysl hlavně u změny SP
            r = Request(m, ct, None, avg if m == "AVG" else None, req.ms, req.hf, cr or "MIGO", tg,
                        req.ovs if cr == "OVS" else 0.02)
            try:
                s = suggest(code, p, pdl, base_ctrl, r, robust, None, solvers)
            except Exception:
                continue
            if ct == "PID" and s["Td"] <= 0:
                continue             # PID by byl shodný s PI
            ctrl = dict(base_ctrl, Gain=s["Kc"], TI=s["Ti"], TD=s["Td"], FF=[], DeadBand=0.0, MV_Lo=-1e12, MV_Hi=1e12)
            rb = robustness_fn(code, p, ctrl)
            e_sp, e_d = closed_loop_steps(code, p, ctrl, h, n)
            ok = rb["stable"] and np.all(np.isfinite(e_sp)) and np.abs(e_sp).max() < 1e3
            out.append(dict(method=m, crit=cr, ctype=ct, Kc=s["Kc"], Ti=s["Ti"], Td=s["Td"],
                            Ms=rb["Ms"] if rb["stable"] else None,
                            iae_load=float(np.sum(np.abs(e_d)) * h) if ok else None,
                            iae_sp=float(np.sum(np.abs(e_sp)) * h) if ok else None,
                            ovs=100 * overshoot_ratio(e_sp) if ok else None,
                            noise=mv_noise(ctrl, sigma_pv) if sigma_pv > 0 else None))
    return out


def set_metrics(code, p, ctrl, sigma_pv=0.0, unc_models=(), robustness_fn=robustness):
    """Robustnost sady: dict(stable, Ms, GM, PM, noise [% MV], Ms_worst přes varianty modelu nebo None)."""
    rb = robustness_fn(code, p, ctrl)
    worst = max(robustness_fn(code, q, ctrl)["Ms"] for q in unc_models) if len(unc_models) else None
    return dict(stable=rb["stable"], Ms=rb["Ms"], GM=rb["GM"], PM=rb["PM"], noise=mv_noise(ctrl, sigma_pv),
                Ms_worst=worst)


def is_placeholder(gain, ti, td):
    """Sada 1 má ještě výchozí zástupné hodnoty (ne skutečné nastavení z faceplatu)."""
    return (gain, ti, td) == (1.0, 100.0, 0.0)


def tune_method(code, p, method, ctype, samp, diffgain=5.0, tc=None, ms=1.6, opt_migo=None):
    """Jednoduchý návrh pro pomocné smyčky (kaskáda): SIMC (τc nebo výchozí), AMIGO, nebo OPT = MIGO od SIMC."""
    if method == "AMIGO":
        return tune(code, p, "AMIGO", None, ctype, samp)
    r0 = tune(code, p, "SIMC", tc if tc else default_tc(code, p, samp, "SIMC", ctype, diffgain), ctype, samp)
    if method == "SIMC":
        return r0
    starts = ((r0["Kc"], r0["Ti"], r0["Td"]),)
    return (opt_migo or SOLVERS.opt_migo)(code, tuple(p), ctype, samp, diffgain, ms, None, starts)
