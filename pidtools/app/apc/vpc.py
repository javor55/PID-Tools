"""
APC – regulace polohy ventilu (mid-range / valve position control): hlavní regulátor drží PV rychlým (malým)
akčním členem MV1, pomalý regulátor VPC přestavuje velký akční člen MV2 tak, aby MV1 zůstal kolem středu
(např. 50 %) a měl rezervu na obě strany. Typicky: malý a velký ventil paralelně, by-pass a hlavní ventil,
otáčky čerpadla a ventil.

VPC vidí (při uzavřené hlavní smyčce) proces MV2 → MV1 se zesílením −K2/K1 a dynamikou hlavní smyčky + MV2;
ladí se výrazně pomaleji (τc = násobek doby odezvy hlavní smyčky), aby se smyčky nepraly.
"""
import numpy as np

from ...core import iae, settling_time, tune
from ...core.apc import vpc_sim
from ..loop import rule_ctrl
from .common import clean, grid, tchar


def default_mv2(model):
    """Výchozí model velkého akčního členu: 4× větší zesílení, 1,5× pomalejší."""
    code, p = model[0], list(model[1])
    p[0] *= 4
    for i in range(1, len(p)):
        p[i] *= 1.5
    return code, p


def loop_time(g1, ctrl1):
    """Doba odezvy hlavní smyčky [s] (čtvrtina doby ustálení, jinak charakteristický čas procesu)."""
    st = settling_time(g1[0], tuple(g1[1]), clean(ctrl1))
    return float(st / 4) if st else float(tchar(g1))


def tune_vpc(g1, g2, ctrl1, base, factor=5.0):
    """
    Návrh PI regulátoru VPC (SIMC na náhradním modelu 1. řádu): K = −K2/K1, T = doba odezvy hlavní smyčky + T2,
    θ = zpoždění MV2, τc = factor × doba odezvy hlavní smyčky. Vrací (ctrl VPC, náhradní model, τc).
    """
    T1 = loop_time(g1, ctrl1)
    K = -g2[1][0] / g1[1][0] if g1[1][0] else -1.0
    T2 = g2[1][1] if g2[0] in ("P1D", "P2D", "I1D") else 0.0
    p = [K, T1 + T2, g2[1][-1]]
    tc = factor * T1
    r = tune("P1D", p, "SIMC", tc, "PI", base["SampleTime"])
    return rule_ctrl(dict(base, MV_Lo=0.0, MV_Hi=100.0), r), p, tc


def simulate(g1, g2, ctrl1, ctrl_vpc, d_amp, sp_vpc=50.0, samp=1.0, t_end=None):
    """
    Porucha zatížení (d_amp % MV1 v 5 % délky, opačná v 55 %) s VPC a bez něj (MV2 stojí).
    Vrací {"on" | "off": (t, průběhy)}.
    """
    t_end = t_end or 30 * loop_time(g1, ctrl1) + 20 * tchar(g2) + 200 * samp
    h, n, t = grid(t_end, samp)
    d = np.where((t >= 0.05 * t_end) & (t < 0.55 * t_end), d_amp, np.where(t >= 0.55 * t_end, -d_amp, 0.0))
    sp = np.full(n, 50.0)
    return {k: vpc_sim(g1, g2, clean(ctrl1), ctrl_vpc, h, sp, sp_vpc, d, 50.0, sp_vpc, 50.0, enabled=k == "on")
            for k in ("on", "off")}


def kpis(run, pv_span, lo=0.0, hi=100.0):
    """IAE PV, čas MV1 v limitu [%], rezerva MV1 na konci (vzdálenost od bližšího limitu) [%]."""
    t, o = run
    m1 = o["MV1"]
    at = float(np.mean((m1 <= lo + 0.5) | (m1 >= hi - 0.5)) * 100)
    return dict(iae=iae(t, o["SP"], o["PV"]) * pv_span / 100, at_lim=at,
                reserve=float(min(m1[-1] - lo, hi - m1[-1])))
