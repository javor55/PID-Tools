"""
APC – split range: jeden regulátor, dva akční členy (ohřev / chlazení, malý a velký ventil). Bod rozdělení
vyrovná zesílení obou polovin rozsahu, aby jedno nastavení regulátoru sedělo v obou.

Model smyčky (výstup regulátoru → PV) odpovídá horní polovině rozsahu (ventil B) při současném rozdělení b₀:
K_B (na % ventilu) = K · (100 − b₀) / 100. Ventil A se zadá (výchozí: stejná dynamika, opačné / třetinové zesílení).
"""
import numpy as np

from ...core import iae, robustness
from ...core.apc import split_map, split_range_sim
from .common import clean, grid, tchar


def valve_b(model, b0):
    """Model ventilu B [% ventilu → % PV] z modelu smyčky při současném rozdělení b₀."""
    code, p = model[0], list(model[1])
    p[0] = p[0] * (100 - b0) / 100
    return code, p


def default_a(gb, mode):
    """Výchozí model ventilu A: stejná dynamika; zesílení opačné (ohřev/chlazení) nebo třetinové (malý ventil)."""
    code, p = gb[0], list(gb[1])
    p[0] = -p[0] if mode == "opposite" else p[0] / 3
    return code, p


def eff_gains(Ka, Kb, b, mode):
    """Zesílení výstup regulátoru → PV v dolní a horní části rozsahu [%PV / %u]."""
    lower = Ka * 100 / max(b, 1e-9) * (-1 if mode == "opposite" else 1)
    return lower, Kb * 100 / max(100 - b, 1e-9)


def balanced(Ka, Kb):
    """Bod rozdělení se stejným zesílením obou polovin: b* = 100 |K_A| / (|K_A| + |K_B|)."""
    return float(100 * abs(Ka) / max(abs(Ka) + abs(Kb), 1e-12))


def halves(ga, gb, ctrl, b, mode):
    """Robustnost (Ms) regulátoru v dolní a horní části rozsahu: [(K_eff, Ms, stabilní)]."""
    lo, up = eff_gains(ga[1][0], gb[1][0], b, mode)
    out = []
    for g, k in ((ga, lo), (gb, up)):
        p = list(g[1])
        p[0] = k
        r = robustness(g[0], p, clean(ctrl))
        out.append((k, r["Ms"], r["stable"]))
    return out


def _pv_static(ga, gb, u, b, mode):
    va, vb = split_map(u, b, mode)
    return ga[1][0] * va + gb[1][0] * vb


def simulate(ga, gb, ctrl, b_now, b_new, mode, gap=0.0, samp=1.0):
    """
    Skok SP z horní části rozsahu do dolní (přes bod rozdělení) a zpět, pro současné a navržené rozdělení.
    Vrací {"now" | "new": (t, průběhy)} a amplitudu skoku [% PV].
    """
    integ = ga[0][0] == "I" or gb[0][0] == "I"
    u0 = b_now + (100 - b_now) / 2
    amp = 10.0 if integ else abs(_pv_static(ga, gb, u0, b_now, mode) - _pv_static(ga, gb, b_now / 2, b_now, mode))
    amp = float(np.clip(amp, 2.0, 40.0))
    t_end = 16 * max(tchar(ga), tchar(gb)) + 200 * samp
    h, n, t = grid(t_end, samp)
    sp = np.where((t >= 0.05 * t_end) & (t < 0.5 * t_end), 50.0 - amp * np.sign(gb[1][0] or 1), 50.0)
    runs = {}
    for key, b in (("now", b_now), ("new", b_new)):
        u0 = b + (100 - b) / 2
        runs[key] = split_range_sim(ga, gb, clean(ctrl), h, sp, b, mode, gap, 50.0, u0)
    return runs, amp


def kpis(run, pv_span):
    """IAE [PV·s], max. odchylka [PV], změny směru výstupu regulátoru."""
    t, o = run
    du = np.diff(o["U"])
    s = np.sign(du[np.abs(du) > 1e-6])
    return dict(iae=iae(t, o["SP"], o["PV"]) * pv_span / 100,
                maxdev=float(np.max(np.abs(o["SP"] - o["PV"]))) * pv_span / 100,
                rev=int(np.sum(s[1:] != s[:-1])) if len(s) > 1 else 0)
