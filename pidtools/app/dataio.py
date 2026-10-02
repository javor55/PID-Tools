"""Načtení a příprava dat: CSV/Excel, dlouhý formát z historianu, čas, převzorkování a kontrola komprese."""
import io
import re

import numpy as np
import pandas as pd

from ..i18n import T


def decode_text(raw_bytes):
    """
    Text exportu: UTF-16 / UTF-8 podle BOM (WinCC, Excel „Unicode text“), jinak UTF-8 a při chybě windows-1250
    (CSV z českých Windows – „Čas“, „°C“). Neznámé znaky se nahradí, načtení nespadne.
    """
    if raw_bytes.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw_bytes.decode("utf-16", errors="replace")
    if raw_bytes.startswith(b"\xef\xbb\xbf"):
        return raw_bytes[3:].decode("utf-8", errors="replace")
    try:
        return raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return raw_bytes.decode("cp1250", errors="replace")


def read_table(name, raw_bytes):
    if name.lower().endswith((".xlsx", ".xls")):
        return pd.read_excel(io.BytesIO(raw_bytes))
    raw = decode_text(raw_bytes)

    def n_num(d):
        return sum(pd.api.types.is_numeric_dtype(d[c]) for c in d.columns)
    df = pd.read_csv(io.StringIO(raw), sep=None, engine="python")
    try:
        df2 = pd.read_csv(io.StringIO(raw), sep=None, engine="python", decimal=",")
        if n_num(df2) > n_num(df):
            df = df2
    except Exception:
        pass
    return df


# ---- čas: číslo, nebo datum/čas v různých národních formátech
_DATE_FMTS = {"iso": ["%Y-%m-%d", "%Y/%m/%d"], "cz": ["%d.%m.%Y", "%d.%m.%y"], "us": ["%m/%d/%Y", "%m/%d/%y"],
              "eu": ["%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y"]}
_TIME_FMTS = ["%H:%M:%S.%f", "%H:%M:%S", "%H:%M", "%I:%M:%S %p", "%I:%M:%S.%f %p", "%I:%M %p"]
TIME_FORMATS = ["auto", "num", "iso", "cz", "us", "eu", "clock"]


def _clean_time_text(col):
    """Sjednocení zápisu: „1. 2. 2024“ → „1.2.2024“, desetinná čárka ve vteřinách, ISO „T“ a zóna „Z“."""
    s = col.astype(str).str.strip()
    s = s.str.replace(r"(\d)\.\s+(?=\d)", r"\1.", regex=True)
    s = s.str.replace(r"(\d{1,2}:\d{2}:\d{2}),(\d+)", r"\1.\2", regex=True)
    s = s.str.replace(r"^(\d{4}-\d{2}-\d{2})T", r"\1 ", regex=True).str.replace(r"Z$", "", regex=True)
    return s


def _formats(kind):
    """Kandidátní formáty strftime pro druh zápisu (datum + volitelně čas; „clock“ = jen čas)."""
    if kind == "clock":
        return list(_TIME_FMTS)
    out = []
    for d in _DATE_FMTS[kind]:
        out += [f"{d} {t}" for t in _TIME_FMTS] + [d]
    return out


def _score(ts):
    """
    Kvalita parsování: podíl převedených hodnot, podíl rostoucích kroků a pravidelnost kroku.
    Pořadí den/měsíc u nejednoznačných dat (01/02/2024) rozhodne, která varianta dá rostoucí a pravidelný čas.
    """
    ok = round(float(ts.notna().mean()), 2)
    d = np.diff(ts.dropna().to_numpy().astype("datetime64[ns]").astype(np.int64)).astype(float)
    if not len(d):
        return ok, 0.0, 0.0
    mono = round(float(np.mean(d >= 0)), 2)
    pos = d[d > 0]
    reg = -float(np.std(pos) / np.median(pos)) if len(pos) > 1 else 0.0
    return ok, mono, reg


def detect_time_format(col):
    """
    Rozpozná zápis času ve sloupci → (druh, formát strftime nebo None).
    Druh: "num" (číslo), "dt" (už datum z Excelu), "iso", "cz", "us", "eu", "clock" (jen hodiny), None (není čas).
    """
    if pd.api.types.is_datetime64_any_dtype(col):
        return "dt", None
    if pd.api.types.is_numeric_dtype(col):
        return "num", None
    s = _clean_time_text(col.dropna())
    if not len(s):
        return None, None
    sample = s.iloc[:: max(1, len(s) // 300)][:300]
    if pd.to_numeric(sample.str.replace(",", ".", regex=False), errors="coerce").notna().mean() > 0.9:
        return "num", None
    best = ((0.0, 0.0, 0.0), None, None)
    for kind in ("iso", "cz", "us", "eu", "clock"):
        for f in _formats(kind):
            sc = _score(pd.to_datetime(sample, format=f, errors="coerce"))
            if sc > best[0]:
                best = (sc, kind, f)
    return (best[1], best[2]) if best[0][0] > 0.8 else (None, None)


def parse_time(col, unit_mult=1.0, fmt="auto"):
    """
    Sloupec času → (sekundy jako pole float, počátek: pd.Timestamp nebo None).
    Sekundy jsou absolutní (u data od epochy), aby šly sloučit časy různých sloupců; čísla se násobí unit_mult.
    fmt: "auto" nebo vynucený druh zápisu z TIME_FORMATS.
    """
    if fmt == "auto":
        kind, f = detect_time_format(col)
    elif fmt == "num" or pd.api.types.is_datetime64_any_dtype(col):
        kind, f = ("num" if fmt == "num" else "dt"), None
    else:
        kind = fmt
        txt = _clean_time_text(col)
        sample = txt.iloc[:: max(1, len(txt) // 300)][:300]
        f = max(_formats(fmt), key=lambda f_: _score(pd.to_datetime(sample, format=f_, errors="coerce")))
    filled = col.notna().to_numpy()  # kratší sloupce (export „čas, hodnota…“) mají na konci prázdné řádky
    if not filled.any():
        raise ValueError(T("err_time"))
    if fmt == "num" or kind == "num":
        v = to_num(col) * unit_mult
        if np.isfinite(v[filled]).mean() < 0.5:
            raise ValueError(T("err_time"))
        return v, None
    if kind == "dt":
        ts = pd.to_datetime(col, errors="coerce")
    elif kind is None:
        raise ValueError(T("err_time"))
    else:
        ts = pd.to_datetime(_clean_time_text(col).where(filled), format=f, errors="coerce")
    if ts[filled].isna().mean() > 0.5:
        raise ValueError(T("err_time"))
    if getattr(ts.dt, "tz", None) is not None:
        ts = ts.dt.tz_localize(None)
    sec = (ts - pd.Timestamp("1970-01-01")).dt.total_seconds().to_numpy(float)
    if kind == "clock":  # jen hodiny: přechod přes půlnoc → další den
        d = np.diff(np.nan_to_num(sec, nan=0.0))
        sec = sec + 86400.0 * np.r_[0, np.cumsum(d < -43200)]
        return sec, None
    return sec, pd.Timestamp("1970-01-01")


def to_seconds(col, unit_mult=1.0, fmt="auto"):
    """Čas od začátku záznamu [s]."""
    v, _ = parse_time(col, unit_mult, fmt)
    return v - np.nanmin(v)


_TIME_WORDS = ("time", "čas", "cas", "date", "datum", "timestamp", "zeit", "uhrzeit", "ts", "t", "sec", "seconds")


def time_columns(df):
    """Sloupce, které obsahují čas: podle názvu (a čitelného obsahu), nebo datum/čas v textu."""
    out = []
    for c in df.columns:
        toks = _tokens(c)
        named = any(w in toks for w in _TIME_WORDS) or any(str(c).lower().startswith(w) for w in _TIME_WORDS[:6])
        kind, _ = detect_time_format(df[c])
        if kind in ("dt", "iso", "cz", "us", "eu", "clock"):
            out.append(c)
        elif named and kind == "num":  # číselný čas jen s „časovým“ názvem a (skoro) rostoucí
            v = to_num(df[c])
            v = v[np.isfinite(v)]
            if len(v) > 2 and np.mean(np.diff(v) >= 0) > 0.95:
                out.append(c)
    return out


def pair_time_columns(df, tcols):
    """Ke každé veličině čas: nejbližší sloupec času vlevo (u exportů „čas, hodnota, čas, hodnota…“), jinak vpravo."""
    cols = list(df.columns)
    pos = [cols.index(c) for c in tcols]
    pairs = {}
    for i, c in enumerate(cols):
        if c in tcols:
            continue
        left = [p for p in pos if p < i]
        pairs[c] = cols[max(left)] if left else cols[min(pos, key=lambda p: abs(p - i))]
    return pairs


def pairs_to_wide(df, pairs, unit_mult=1.0, fmt="auto"):
    """Veličiny s vlastními časy → jedna tabulka: sjednocené časy (sloupec „t“, absolutní s) a hodnoty (NaN mezi)."""
    parsed = {tc: parse_time(df[tc], unit_mult, fmt) for tc in set(pairs.values())}
    parts = [pd.DataFrame({"t": parsed[tc][0], "tag": str(c), "v": to_num(df[c])}) for c, tc in pairs.items()]
    long = pd.concat(parts, ignore_index=True).dropna(subset=["t"])
    wide = long.pivot_table(index="t", columns="tag", values="v", aggfunc="mean").reset_index()
    wide.columns.name = None
    origin = next((o for _, o in parsed.values() if o is not None), None)
    return wide[["t"] + [str(c) for c in pairs]], origin


def _tokens(name):
    return [t for t in re.split(r"[^0-9a-zA-Zá-žÁ-Ž]+", str(name).lower()) if t]


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
