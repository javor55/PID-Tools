"""Načtení a příprava dat: CSV/Excel, dlouhý formát z historianu, čas, převzorkování a kontrola komprese."""
import io

import numpy as np
import pandas as pd
import streamlit as st

from ..i18n import T


def read_table(name, raw_bytes):
    if name.lower().endswith((".xlsx", ".xls")):
        return pd.read_excel(io.BytesIO(raw_bytes))
    raw = raw_bytes.decode("utf-8", errors="replace")
    n_num = lambda d: sum(pd.api.types.is_numeric_dtype(d[c]) for c in d.columns)
    df = pd.read_csv(io.StringIO(raw), sep=None, engine="python")
    try:
        df2 = pd.read_csv(io.StringIO(raw), sep=None, engine="python", decimal=",")
        if n_num(df2) > n_num(df):
            df = df2
    except Exception:
        pass
    return df


def to_seconds(col, unit_mult=1.0):
    if pd.api.types.is_numeric_dtype(col):
        v = col.astype(float).to_numpy() * unit_mult
        return v - np.nanmin(v)
    ts = pd.to_datetime(col, dayfirst=True, errors="coerce")
    if ts.isna().mean() > 0.5:
        raise ValueError(T("err_time"))
    return (ts - ts.min()).dt.total_seconds().to_numpy()


def to_num(col):
    if pd.api.types.is_numeric_dtype(col):
        return col.to_numpy(float)
    return pd.to_numeric(col.astype(str).str.replace(",", ".", regex=False).str.strip(),
                         errors="coerce").to_numpy(float)


def resample(t, cols, zoh, Ts_user=None, ref=0):
    valid = []
    for c in cols:
        m = np.isfinite(t) & np.isfinite(c)
        tv, cv = t[m], c[m]
        o = np.argsort(tv, kind="stable")
        tv, cv = tv[o], cv[o]
        tv, idx = np.unique(tv, return_index=True)
        valid.append((tv, cv[idx]))
    if any(len(v[0]) < 5 for v in valid):
        raise ValueError(T("err_few"))
    t0 = max(v[0][0] for v in valid)
    t1 = (min(v[0][-1] for i, v in enumerate(valid) if i not in zoh) if len(zoh) < len(valid)
          else max(v[0][-1] for v in valid))
    Ts = Ts_user if Ts_user else float(np.median(np.diff(valid[ref][0])))
    n = int((t1 - t0) / Ts) + 1
    if n > 30000:
        Ts = (t1 - t0) / 30000
        n = 30001
    tg = t0 + np.arange(n) * Ts
    out = []
    for i, (tv, cv) in enumerate(valid):
        if i in zoh:
            j = np.clip(np.searchsorted(tv, tg, side="right") - 1, 0, len(tv) - 1)
            out.append(cv[j])
        else:
            out.append(np.interp(tg, tv, cv))
    return tg - t0, Ts, out, t0


def compression_warnings(t, v, name):
    m = np.isfinite(t) & np.isfinite(v)
    t, v = t[m], v[m]
    o = np.argsort(t)
    t, v = t[o], v[o]
    w = []
    dt = np.diff(t)
    dt = dt[dt > 0]
    if len(dt) > 10 and np.std(dt) / np.median(dt) > 1.0:
        w.append(T("warn_irregular", name=name))
    if len(v) > 20 and np.mean(np.diff(v) == 0) > 0.5:
        w.append(T("warn_repeated", name=name))
    return w


# ---- varianty s cache (drahé kroky se provedou jen jednou pro daný soubor)
@st.cache_data(show_spinner=False, max_entries=4)
def load_table(cache_key, name, _raw):
    """Načtení souboru – jen jednou pro daný soubor (klíč = název, velikost, id nahrání)."""
    return read_table(name, _raw)


@st.cache_data(show_spinner=False, max_entries=8)
def time_cached(cache_key, col, unit_mult, _series):
    return to_seconds(_series, unit_mult)


@st.cache_data(show_spinner=False, max_entries=4)
def pivot_cached(cache_key, c_tag, c_tim, c_val, unit_mult, _df):
    tmp = pd.DataFrame({"tag": _df[c_tag].astype(str), "t": to_seconds(_df[c_tim], unit_mult), "v": to_num(_df[c_val])})
    wide = tmp.pivot_table(index="t", columns="tag", values="v", aggfunc="mean").reset_index()
    wide.columns.name = None
    return wide


@st.cache_data(show_spinner=False, max_entries=8)
def resample_cached(cache_key, _t_all, _cols, Ts_user):
    return resample(_t_all, _cols, zoh={1}, Ts_user=Ts_user, ref=0)
