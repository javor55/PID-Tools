"""
APC – poměrová regulace s křížovým omezením (palivo–vzduch u hořáků, míchání proudů). Požadavek výkonu vede
na SP paliva a SP vzduchu = R × palivo. Křížové omezení (cross-limiting): vzduch = max(požadavek, skutečné palivo)
× R, palivo = min(požadavek, skutečný vzduch / R) – při růstu výkonu jde napřed vzduch, při poklesu palivo,
takže nikdy nevznikne přebytek paliva (nedokonalé spalování, CO).
"""
import numpy as np

from ...core import iae
from ...core.apc import ratio_sim
from .common import clean, grid, tchar


def default_air(model):
    """Výchozí model vzduchu: stejné zesílení, 2× pomalejší (ventilátor / klapka bývá pomalejší než palivo)."""
    code, p = model[0], list(model[1])
    for i in range(1, len(p)):
        p[i] *= 2
    return code, p


def simulate(gf, ga, ctrl_f, ctrl_a, R, step, samp=1.0):
    """Skok požadavku výkonu +step v 5 % a zpět v 50 % délky; s křížovým omezením a bez. {"cross"|"plain": běh}."""
    t_end = 20 * max(tchar(gf), tchar(ga)) + 200 * samp
    h, n, t = grid(t_end, samp)
    d0 = 50.0
    dem = np.where((t >= 0.05 * t_end) & (t < 0.5 * t_end), d0 + step, d0)
    pv0 = (d0, d0 * R)
    return {k: ratio_sim(gf, ga, clean(ctrl_f), clean(ctrl_a), h, dem, R, k == "cross", pv0, (50.0, 50.0))
            for k in ("cross", "plain")}


def kpis(run, f_span):
    """Nejmenší poměr λ (vzduch / potřebný vzduch), čas s λ < 1 [s], IAE paliva vůči požadavku [jedn. paliva·s]."""
    t, o = run
    lam = o["LAM"]
    h = t[1] - t[0] if len(t) > 1 else 1.0
    return dict(lam_min=float(np.nanmin(lam)), t_rich=float(np.sum(lam < 0.999) * h),
                iae=iae(t, o["D"], o["PVF"]) * f_span / 100)
