"""
Diagnostika provozu na úseku dat: výkon smyčky, oscilace a stikce ventilu, hystereze polohy, nelinearita
(lokální zesílení pro každý skok MV). Vstupy PV, SP, MV v %; výstupy pro uživatele přepočtené na jednotky.
"""
import numpy as np

from .. import core
from ..core import oscillation, stiction_ccf, valve_hysteresis


def kpis(sc, t, sp, pv, mv, Ts, mv_lo, mv_hi, theta, has_sp, loop_kpis=core.loop_kpis):
    """
    Výkon smyčky: dict(std_e [PV], iae_h [PV·s/h], travel_h [MV/h], rev_h [1/h], at_lim [%], harris, osc) –
    mv_lo, mv_hi v %, theta = efektivní zpoždění [s].
    """
    k = loop_kpis(t, sp if has_sp else pv, pv, mv, Ts, mv_lo, mv_hi, theta, has_sp)
    return dict(std_e=k["std_e"] * sc.PR / 100, iae_h=k["iae_h"] * sc.PR / 100, travel_h=k["travel_h"] * sc.MR / 100,
                rev_h=k["rev_h"], at_lim=k["at_lim"], harris=k["harris"], osc=k["osc"])


def valve(sp, pv, mv, Ts, has_sp, integ):
    """
    Oscilace a stikce: dict(osc = výsledek oscillation, stic = výsledek stiction_ccf, verdict = None | "likely" |
    "unlikely" | "unclear"). U integračních procesů se křížová korelace počítá s derivací PV.
    """
    sig = (sp - pv) if has_sp else pv
    osc = oscillation(sig, Ts)
    sc = stiction_ccf(mv, pv, Ts, integ, osc["period"] if osc["osc"] else None)
    r = sc["ratio"]
    verdict = None
    if osc["osc"] and np.isfinite(r):
        verdict = "likely" if r < 0.35 else ("unlikely" if r > 0.7 else "unclear")
    return dict(osc=osc, stic=sc, verdict=verdict)


def hysteresis(mv_e, pos_e):
    """Hystereze ventilu z polohy [jednotky MV] (NaN = nelze určit)."""
    return float(valve_hysteresis(mv_e, pos_e))


def nonlinearity(model, ts, pv, mv, d, Ts, local_gains=core.local_gains):
    """Lokální zesílení pro každý skok MV a poměr největšího a nejmenšího: (seznam, poměr nebo None)."""
    code, p, pdl = model
    lg = local_gains(code, p, pdl, ts, pv, mv, d, Ts)
    if len(lg) < 2:
        return lg, None
    g = np.abs([q["gain"] for q in lg])
    return lg, float(np.max(g) / max(np.min(g), 1e-12))
