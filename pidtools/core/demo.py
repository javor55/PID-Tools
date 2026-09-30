"""Ukázková data (simulovaná nádrž s měřeným přítokem)."""
import numpy as np

from .models import model_dev

def demo_data(seed=1):
    """
    Nádrž: hladina = integrační proces s malým zpožděním, MV = odtokový ventil (záporné zesílení),
    měřený přítok jako porucha. Záznam: 1 h ručního režimu se skoky MV.
    Ki = -0.004 %/(%·s), T1 = 15 s, θ = 8 s; přítok: Kd = 0.01 %/(m3/h·s).
    """
    rng = np.random.default_rng(seed)
    h = 1.0
    t = np.arange(0, 3600, h)
    mv = np.full_like(t, 50.0)
    for t0, v in [(300, 55), (600, 50), (1200, 45), (1500, 50), (2400, 57), (2650, 50)]:
        mv[t >= t0] = v
    q = np.full_like(t, 20.0)
    for t0, v in [(900, 24), (1900, 18), (3000, 22)]:
        q[t >= t0] = v
    q = q + rng.normal(0, 0.15, t.size)
    p = [-0.004, 15.0, 8.0]
    pdl = [[0.01, 5.0, 3.0]]
    pv = 50 + model_dev("I1D", p, pdl, t, mv - mv[0], [q - 20.0], h) + rng.normal(0, 0.1, t.size)
    sp = np.full_like(t, 50.0)
    return t, sp, pv, mv, q
