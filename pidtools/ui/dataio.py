"""Varianty načtení a přípravy dat s cache Streamlitu (výpočty jsou v pidtools.app.dataio)."""
import numpy as np
import pandas as pd
import streamlit as st

from ..app.dataio import pairs_to_wide, parse_time, read_table, resample, time_columns, to_num


# ---- varianty s cache (drahé kroky se provedou jen jednou pro daný soubor)
@st.cache_data(show_spinner=False, max_entries=4)
def load_table(cache_key, name, _raw):
    """Načtení souboru – jen jednou pro daný soubor (klíč = název, velikost, id nahrání)."""
    return read_table(name, _raw)


@st.cache_data(show_spinner=False, max_entries=8)
def time_cached(cache_key, col, unit_mult, fmt, _series):
    """Čas jednoho sloupce → (sekundy od začátku, počátek jako pd.Timestamp nebo None)."""
    v, origin = parse_time(_series, unit_mult, fmt)
    t0 = float(np.nanmin(v))
    return v - t0, (origin + pd.Timedelta(seconds=t0)) if origin is not None else None


@st.cache_data(show_spinner=False, max_entries=4)
def pivot_cached(cache_key, c_tag, c_tim, c_val, unit_mult, fmt, _df):
    v, origin = parse_time(_df[c_tim], unit_mult, fmt)
    tmp = pd.DataFrame({"tag": _df[c_tag].astype(str), "t": v, "v": to_num(_df[c_val])})
    wide = tmp.pivot_table(index="t", columns="tag", values="v", aggfunc="mean").reset_index()
    wide.columns.name = None
    t0 = float(wide["t"].min())
    wide["t"] -= t0
    return wide, (origin + pd.Timedelta(seconds=t0)) if origin is not None else None


@st.cache_data(show_spinner=False, max_entries=4)
def pairs_cached(cache_key, pairs_items, unit_mult, fmt, _df):
    wide, origin = pairs_to_wide(_df, dict(pairs_items), unit_mult, fmt)
    t0 = float(wide["t"].min())
    wide["t"] -= t0
    return wide, (origin + pd.Timedelta(seconds=t0)) if origin is not None else None


@st.cache_data(show_spinner=False, max_entries=8)
def time_columns_cached(cache_key, _df):
    return time_columns(_df)


@st.cache_data(show_spinner=False, max_entries=8)
def resample_cached(cache_key, _t_all, _cols, Ts_user):
    return resample(_t_all, _cols, zoh={1}, Ts_user=Ts_user, ref=0)
