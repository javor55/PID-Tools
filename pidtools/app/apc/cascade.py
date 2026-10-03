"""APC – kaskáda: model vnitřní smyčky, ladění vnitřní a vnější smyčky, oddělení rychlostí, simulace."""
import numpy as np

from ... import core
from ...core import outer_with_inner, predict
from ..tuning import tune_method


def manual_inner(k, t1, t2, theta):
    """Model vnitřní smyčky zadaný ručně: P2D při T2 > 0, jinak P1D."""
    if t2 > 0:
        return "P2D", [k, max(t1, t2), max(min(t1, t2), 1e-3), theta]
    return "P1D", [k, t1, theta]


def fit_inner(ts, ipv, imv, Ts, fit_model=core.fit_model):
    """Model vnitřní smyčky z dat (P1D a P2D, P2D jen když je o 0,5 % lepší). Vrací (výsledek nebo None, chyby)."""
    k = int(np.ceil(len(ts) / 2500))
    best, errs = None, []
    for code in ("P1D", "P2D"):
        try:
            r = dict(fit_model(code, ts[::k], ipv[::k], imv[::k], Ts * k))
            r["fit"] = predict(code, r["p"], [], ts, ipv, imv, [], Ts)[1]
            if best is None or r["fit"] > best["fit"] + 0.5:
                best = r
        except Exception as ex:
            errs.append(str(ex))
    return best, errs


def inner_ctrl(s, diffgain, samp):
    """Regulátor vnitřní smyčky (PI, výstup 0–100 %)."""
    return dict(Gain=s["Kc"], TI=s["Ti"], TD=0.0, DiffGain=diffgain, SampleTime=samp, MV_Lo=0.0, MV_Hi=100.0,
                PropFacSP=1.0, DiffFbk=True)


def inner_response(code, p, ictrl, samp, sim=core.pidconl_sim):
    """Skok SP uzavřené vnitřní smyčky: (čas dosažení 63,2 % [s], efektivní časová konstanta bez zpoždění [s])."""
    T_sim = 30 * (p[-1] + sum(p[1:-1]) + samp)
    h = max(samp / max(1, min(10, int(6000 * samp / T_sim))), T_sim / 30000)   # nejvýš ~30 000 kroků
    n = int(T_sim / h) + 1
    sp = np.ones(n)
    sp[0] = 0
    t, _, P, _ = sim(code, p, [], h, sp, 0.0, 50.0, ictrl)
    k63 = int(np.argmax(P >= 0.632)) if np.any(P >= 0.632) else len(P) - 1
    return float(t[k63]), float(max(t[k63] - p[-1], h))


def outer_model(model, tc_inner_eff, theta_inner):
    """Model vnější smyčky včetně uzavřené vnitřní smyčky."""
    return outer_with_inner(model[0], model[1], tc_inner_eff, theta_inner)


def tune_loop(code, p, method, ctype, samp, diffgain, tc=None, opt_migo=None):
    return tune_method(code, p, method, ctype, samp, diffgain, tc, 1.6, opt_migo)


def separation(tc_outer, s_outer, t63_inner):
    """Oddělení rychlostí: τc vnější smyčky (nebo TI/4) / doba odezvy vnitřní smyčky; doporučeno ≥ 4."""
    return (tc_outer or s_outer["Ti"] / 4) / max(t63_inner, 1e-9)


def simulate(inner, ictrl, outer, octrl, samp, samp_i, p_o, co, tc_outer=None, sim=core.cascade_sim):
    """
    Simulace kaskády: skok SP vnější smyčky (5 %), porucha vnitřní smyčky (40 %) a vnější smyčky (70 % délky).
    Vrací (čas, sloupce [SP_o, PV_o, SP_i, PV_i, ventil], stabilní).
    """
    Tc_sim = max(15 * (p_o[-1] + (p_o[1] if co in ("P1D", "P2D", "I1D") else 0) + (tc_outer or 0)), 50 * samp)
    hc = min(samp, samp_i) / max(1, min(5, int(15000 * min(samp, samp_i) / Tc_sim)))
    hc = max(hc, Tc_sim / 30000)          # velmi pomalý vnější proces: nejvýš ~30 000 kroků (jinak výpočet trvá sekundy)
    nc = int(Tc_sim / hc) + 1
    ts = np.arange(nc) * hc
    sp_o = np.full(nc, 50.0)
    sp_o[ts >= 0.05 * Tc_sim] = 55.0
    d_i = np.where(ts >= 0.4 * Tc_sim, 5.0, 0.0)
    d_o = np.where(ts >= 0.7 * Tc_sim, 5.0, 0.0)
    ts, oc = sim(inner, ictrl, outer, octrl, hc, sp_o, d_i, d_o)
    return ts, oc, bool(np.all(np.isfinite(oc)) and np.abs(oc).max() < 1e5)
