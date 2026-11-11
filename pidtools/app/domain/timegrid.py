"""
Společná časová mřížka více zdrojů (čisté funkce nad poli numpy, bez stavu).

Vstup: řady `(t, v)` s časy v sekundách na společné ose (posun a časové pásmo zdroje už jsou započtené).
Výstup: mřížka s pravidelnou periodou a hodnoty všech řad na ní; kde zdroj nemá data (mimo jeho úsek, nebo
uvnitř mezery delší než práh), je NaN – přes dlouhou mezeru se neinterpoluje.

  overlap – jen společný úsek všech řad (výchozí, jako dnes u jednoho souboru)
  union   – od nejdřívějšího po nejpozdější vzorek
Perioda: ruční, jinak nejjemnější z period zdrojů (medián kroku, nebo zadané vlastní vzorkování zdroje).
"""
from dataclasses import dataclass

import numpy as np

from ...i18n import T
from .model import TimeGrid

MAX_POINTS = 30000          # nejvyšší počet bodů mřížky (jako app.dataio.resample): delší záznam se zhrubí


def clean(t, v):
    """Řada bez neplatných vzorků, seřazená podle času, bez opakovaných časů."""
    t, v = np.asarray(t, float), np.asarray(v, float)
    m = np.isfinite(t) & np.isfinite(v)
    t, v = t[m], v[m]
    o = np.argsort(t, kind="stable")
    t, v = t[o], v[o]
    t, idx = np.unique(t, return_index=True)
    return t, v[idx]


def median_step(t):
    """Medián kroku řady [s]; None, když řada nemá dva různé časy."""
    d = np.diff(np.asarray(t, float))
    d = d[d > 0]
    return float(np.median(d)) if len(d) else None


@dataclass
class GridResult:
    t: np.ndarray                    # časy bodů mřížky na společné ose [s]
    Ts: float                        # perioda mřížky [s]
    t0: float                        # čas prvního bodu (= t[0])
    values: list                     # hodnoty řad na mřížce (NaN = bez dat)
    gaps: list                       # u každé řady [(od, do)] mezery delší než práh [s na společné ose]


def choose_period(series, tg: TimeGrid, own=None):
    """
    Perioda mřížky: ruční (`tg.period`), jinak nejjemnější perioda řad. `own` = vlastní perioda zdroje u řady
    (None = medián kroku z dat) – zdroj s deklarovaným vzorkováním tak určuje periodu i bez dostatku vzorků.
    """
    if tg.period:
        return float(tg.period)
    own = own or [None] * len(series)
    ps = [o or median_step(t) for (t, _), o in zip(series, own)]
    ps = [p for p in ps if p]
    if not ps:
        raise ValueError(T("err_few"))
    return min(ps)


def gap_limit(tg: TimeGrid, step):
    """Nejdelší krok zdroje, který se ještě interpoluje [s]: ručně zadaný práh, jinak násobek kroku zdroje."""
    return float(tg.max_gap) if tg.max_gap else tg.gap_factor * step


def _span(series, mode):
    starts = [t[0] for t, _ in series]
    ends = [t[-1] for t, _ in series]
    return (max(starts), min(ends)) if mode == "overlap" else (min(starts), max(ends))


def common_grid(series, tg: TimeGrid | None = None, zoh=(), own=None) -> GridResult:
    """
    Řady → společná mřížka. `zoh` = indexy řad, které se drží (MV, režim: schodovitý průběh), ostatní se
    interpolují lineárně. Řada s méně než dvěma vzorky nebo prázdný překryv → ValueError (`err_few` / `err_overlap`).
    """
    tg = tg or TimeGrid()
    tg.check()
    cl = [clean(t, v) for t, v in series]
    if not cl or any(len(t) < 2 for t, _ in cl):
        raise ValueError(T("err_few"))
    t0, t1 = _span(cl, tg.mode)
    if not t1 > t0:
        raise ValueError(T("err_overlap"))
    Ts = choose_period(cl, tg, own)
    n = int(np.floor((t1 - t0) / Ts + 1e-6)) + 1
    if n > MAX_POINTS:
        Ts = (t1 - t0) / MAX_POINTS
        n = MAX_POINTS + 1
    tgrid = t0 + np.arange(n) * Ts
    out, gaps = [], []
    for i, (tv, cv) in enumerate(cl):
        if i in zoh:
            j = np.clip(np.searchsorted(tv, tgrid, side="right") - 1, 0, len(tv) - 1)
            v = cv[j]
        else:
            v = np.interp(tgrid, tv, cv)
        v = np.where((tgrid < tv[0] - 1e-9) | (tgrid > tv[-1] + 1e-9), np.nan, v)       # mimo úsek zdroje
        step = median_step(tv) or Ts
        lim = gap_limit(tg, (own[i] if own and own[i] else step))
        gi = np.nonzero(np.diff(tv) > lim)[0]
        g = [(float(tv[k]), float(tv[k + 1])) for k in gi]
        for a, b in g:                                                                    # uvnitř mezery NaN
            v[(tgrid > a) & (tgrid < b)] = np.nan
        out.append(v)
        gaps.append(g)
    return GridResult(tgrid, float(Ts), float(tgrid[0]), out, gaps)


def overlap(series):
    """Společný úsek řad (od, do) [s], nebo None, když se nepřekrývají."""
    cl = [clean(t, v) for t, v in series]
    cl = [c for c in cl if len(c[0])]
    if not cl:
        return None
    a, b = _span(cl, "overlap")
    return (float(a), float(b)) if b > a else None
