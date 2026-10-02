"""
Data smyčky: tabulka ze souboru → signály s časem (rozložení „wide“, „pairs“, „long“) → společná časová mřížka.

Rozložení:
  wide   – jeden sloupec času pro všechny veličiny
  pairs  – každá veličina má vlastní sloupec času (export „čas, hodnota, čas, hodnota …“)
  long   – dlouhý formát z historianu: tag, čas, hodnota
"""
from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import pandas as pd

from .dataio import pair_time_columns, pairs_to_wide, parse_time, resample, time_columns, to_num

LAYOUTS = ("wide", "pairs", "long")
UNITS = {"s": 1.0, "ms": 1e-3, "min": 60.0, "h": 3600.0}


def guess_col(cols, keys, default=0):
    """Index sloupce, jehož název obsahuje některé z klíčových slov."""
    for k in keys:
        for i, c in enumerate(cols):
            if k in str(c).lower():
                return i
    return min(default, len(cols) - 1)


def is_long(df):
    """Dlouhý formát z historianu: sloupec s opakujícími se názvy tagů (text) a jediný sloupec s čísly mimo čas."""
    tcols = time_columns(df)
    other = [c for c in df.columns if c not in tcols]
    if len(df) < 20 or not other:
        return False
    texts = [c for c in other if np.isfinite(to_num(df[c])).mean() < 0.5]
    nums = [c for c in other if c not in texts]
    return len(nums) == 1 and any(1 < df[c].nunique() <= max(50, len(df) // 20) for c in texts)


def default_layout(df):
    """Výchozí rozložení: dlouhý formát (tag, čas, hodnota), víc sloupců času → „pairs“, jinak „wide“."""
    if is_long(df):
        return "long"
    return "pairs" if len(time_columns(df)) >= 2 else "wide"


@dataclass
class Signals:
    """Signály tabulky: časy všech vzorků [s od začátku], názvy veličin a přístup k hodnotám."""
    t_all: np.ndarray
    sigs: list
    get: Callable
    origin: object = None          # pd.Timestamp času 0 (čas zadaný datem), jinak None
    time_src: list = field(default_factory=list)


def signals(df, layout="wide", time_fmt="auto", unit="s", c_time=None, c_tag=None, c_val=None):
    """Tabulka → Signals podle rozložení. Sloupce času, tagu a hodnoty se doplní odhadem, nejsou-li zadané."""
    um = UNITS[unit]
    cols = list(df.columns)
    tcols = time_columns(df)
    if layout == "long":
        c_tag = c_tag or cols[guess_col(cols, ["tag", "name", "název", "variable"])]
        c_time = c_time or cols[guess_col(cols, ["time", "čas", "cas", "timestamp"], 1)]
        c_val = c_val or cols[guess_col(cols, ["value", "hodnota", "val"], 2)]
        v, origin = parse_time(df[c_time], um, time_fmt)
        tmp = pd.DataFrame({"tag": df[c_tag].astype(str), "t": v, "v": to_num(df[c_val])})
        wide = tmp.pivot_table(index="t", columns="tag", values="v", aggfunc="mean").reset_index()
        wide.columns.name = None
        src = [c_time]
    elif layout == "pairs":
        if not tcols:
            raise ValueError("err_no_time_cols")
        wide, origin = pairs_to_wide(df, pair_time_columns(df, tcols), um, time_fmt)
        src = list(tcols)
    else:
        c_time = c_time or (tcols[0] if tcols else cols[guess_col(cols, ["cas", "čas", "time", "datum", "date"])])
        v, origin = parse_time(df[c_time], um, time_fmt)
        t0 = float(np.nanmin(v))
        sigs = [c for c in cols if c != c_time and c not in tcols]
        return Signals(v - t0, sigs, lambda c: to_num(df[c]),
                       (origin + pd.Timedelta(seconds=t0)) if origin is not None else None, [c_time])
    t0 = float(wide["t"].min())
    wide["t"] -= t0
    return Signals(wide["t"].to_numpy(float), [c for c in wide.columns if c != "t"],
                   lambda c: wide[c].to_numpy(float), (origin + pd.Timedelta(seconds=t0)) if origin is not None else None,
                   src)


@dataclass
class Grid:
    """Veličiny smyčky na společné mřížce (inženýrské jednotky)."""
    t: np.ndarray
    Ts: float
    T0: float
    pv_e: np.ndarray
    mv_e: np.ndarray
    sp_e: np.ndarray
    dists: list
    has_sp: bool


def to_grid(s, c_pv, c_mv, c_sp=None, c_d=(), Ts_user=None):
    """Převzorkování PV, MV (podržení hodnoty), SP a měřených poruch na společnou mřížku."""
    has_sp = c_sp not in (None, "", "—")
    cols = [s.get(c_pv), s.get(c_mv)] + [s.get(c) for c in c_d] + ([s.get(c_sp)] if has_sp else [])
    t, Ts, rs, T0 = resample(s.t_all, cols, zoh={1}, Ts_user=Ts_user, ref=0)
    pv_e, mv_e = rs[0], rs[1]
    return Grid(t, Ts, T0, pv_e, mv_e, rs[-1] if has_sp else np.full_like(pv_e, np.nan), list(rs[2:2 + len(c_d)]),
                has_sp)


def on_grid(s, g, col, zoh=False):
    """Libovolný sloupec převzorkovaný na mřížku g (např. poloha ventilu, sloupce jiné smyčky)."""
    v = s.get(col)
    m = np.isfinite(s.t_all) & np.isfinite(v)
    tv, cv = s.t_all[m], v[m]
    o = np.argsort(tv)
    tv, cv = tv[o], cv[o]
    if len(tv) < 2:
        return np.full_like(g.t, np.nan)
    if zoh:
        j = np.clip(np.searchsorted(tv, g.t + g.T0, side="right") - 1, 0, len(tv) - 1)
        return cv[j]
    return np.interp(g.t + g.T0, tv, cv)


DEMO_SET1 = (-2.0, 200.0, 0.0)     # „současné“ parametry ukázkové smyčky (odtokový ventil → záporné zesílení)
DEMO_DISTS = ["FI100.Pritok"]                     # měřená porucha ukázkových dat


def demo_frame():
    """Ukázková data (hladina s odtokovým ventilem a měřeným přítokem) jako tabulka se společným časem."""
    from ..core import demo_data
    t, sp, pv, mv, q = demo_data()
    return pd.DataFrame({"Cas": t, "LIC101.SP": sp, "LIC101.PV": pv, "LIC101.MV": mv, "FI100.Pritok": q})
