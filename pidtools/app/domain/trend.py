"""
Podklady pro Trendy (čisté funkce nad poli): zředění řady na min / max po skupinách, základní statistika signálu
a hodnota v čase kurzoru. Pracují s časy na společné ose [s]; mezery (NaN) se nepřepočítávají.
"""
import numpy as np

from ..signalpack import minmax_idx
from .timegrid import clean, median_step


def window(t, v, a=None, b=None):
    """Řada bez neplatných vzorků v úseku [a, b] (None = bez omezení)."""
    t, v = clean(t, v)
    m = np.ones(len(t), bool)
    if a is not None:
        m &= t >= a
    if b is not None:
        m &= t <= b
    return t[m], v[m]


def decimate(t, v, a=None, b=None, n=1000):
    """
    Řada v úseku [a, b] zředěná na nejvýše ~2·n bodů: v každé skupině vzorků zůstane minimum a maximum
    (špičky se neztratí), body jsou seřazené podle času. Kratší řada se vrací beze změny.
    """
    tt, vv = window(t, v, a, b)
    n = max(int(n), 1)
    if len(tt) <= 2 * n:
        return tt, vv
    idx = minmax_idx(vv, int(np.ceil(len(tt) / n)))
    return tt[idx], vv[idx]


def stats(t, v, a=None, b=None):
    """Statistika v úseku [a, b]: min, max, průměr, σ, počet platných a chybějících vzorků (NaN v původní řadě)."""
    t = np.asarray(t, float)
    v = np.asarray(v, float)
    m = np.isfinite(t)
    if a is not None:
        m &= t >= a
    if b is not None:
        m &= t <= b
    x = v[m]
    ok = np.isfinite(x)
    n = int(ok.sum())
    xs = x[ok]
    return dict(min=float(xs.min()) if n else None, max=float(xs.max()) if n else None,
                mean=float(xs.mean()) if n else None, std=float(xs.std()) if n else None,
                count=n, missing=int(len(x) - n))


def value_at(t, v, x, max_gap=None):
    """
    Hodnota řady v čase x (kurzor): lineární interpolace mezi sousedními vzorky; mimo záznam, nebo uvnitř mezery
    delší než `max_gap` (výchozí 5 × medián kroku) None.
    """
    tt, vv = clean(t, v)
    if len(tt) < 2 or x < tt[0] or x > tt[-1]:
        return None
    lim = max_gap if max_gap else 5.0 * (median_step(tt) or 0.0)
    j = int(np.searchsorted(tt, x, side="right"))
    if j >= len(tt):
        return float(vv[-1])
    if tt[j - 1] == x:
        return float(vv[j - 1])
    if lim and tt[j] - tt[j - 1] > lim:
        return None
    f = (x - tt[j - 1]) / (tt[j] - tt[j - 1])
    return float(vv[j - 1] + f * (vv[j] - vv[j - 1]))
