"""
Graf průběhů – jedna komponenta pro celou aplikaci (static/trend.js): karty pod sebou se společnou časovou osou,
zoom kolečkem, posun tažením, hodnoty pod myší a volitelně úseky s táhly (společný úsek, úseky podle vstupů,
úseky A / B). Používají ji záložky Data (záznam), Model (úseky pro identifikaci) a Diagnostika (provozní úseky).

Data se do prohlížeče posílají jen pro aktivní záložku; stejná data (otisk) prohlížeč znovu nepřekresluje.
"""
import hashlib
import json

import numpy as np
import streamlit as st

from ..app.timefmt import UNITS, unit_for
from ..i18n import T
from .widgets import static_asset, v2_component

ss = st.session_state
MAX_PTS = 6000          # bodů na průběh poslaný do prohlížeče (min/max po skupinách, tvar zůstane)

_CSS = """
.pidw { position: relative; display: flex; flex-direction: column; gap: 12px; font-family: inherit;
  color: var(--pidw-text); --pidw-text: #1f2933; --pidw-muted: #52606d; --pidw-line: #d7dde5; --pidw-card: #ffffff;
  --pidw-grid: #e5e9ef; --pidw-axis: #c3ccd6; --pidw-hbg: #eef1f5; --pidw-btn: #ffffff; }
@media (prefers-color-scheme: dark) { .pidw.dark-auto { } }
.pidw.dark { --pidw-text: #e2e8f0; --pidw-muted: #94a3b8; --pidw-line: #26324a; --pidw-card: #111a2e;
  --pidw-grid: #1c2740; --pidw-axis: #334155; --pidw-hbg: #0b1220; --pidw-btn: #0f172a; }
.pidw-card { background: var(--pidw-card); border: 1px solid var(--pidw-line); border-radius: 10px; padding: 12px 14px; }
.pidw-bar { display: flex; flex-wrap: wrap; gap: 10px 22px; align-items: center; padding: 10px 14px; }
.pidw-grp { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.pidw-title { margin: 0; padding: 0; font-size: 14px; font-weight: 600; color: var(--pidw-text); }
.pidw-lab { font-size: 12px; color: var(--pidw-muted); }
.pidw-note { font-size: 11px; color: var(--pidw-muted); }
.pidw-help { width: 20px; height: 20px; border-radius: 50%; border: 1px solid #9aa5b1; color: var(--pidw-muted);
  font-size: 11px; font-weight: 600; display: inline-flex; align-items: center; justify-content: center; cursor: help; }
.pidw-seg { display: inline-flex; border: 1px solid var(--pidw-axis); border-radius: 8px; overflow: hidden; }
.pidw-seg button { font: inherit; font-size: 12px; padding: 4px 10px; border: 0; background: var(--pidw-btn);
  color: var(--pidw-text); cursor: pointer; }
.pidw-seg button + button { border-left: 1px solid var(--pidw-axis); }
.pidw-seg button.on { background: #1f5fa8; color: #fff; font-weight: 500; }
.pidw-model button { font-size: 11px; padding: 5px 10px; }
.pidw-model button.on { background: #5b3fa8; }
.pidw-leg { display: flex; gap: 14px; margin-left: auto; flex-wrap: wrap; font-size: 11px; color: var(--pidw-muted); }
.pidw-leg span, .pidw-leg2 span { display: inline-flex; align-items: center; gap: 6px; }
.pidw-leg i { display: inline-block; width: 14px; height: 10px; border: 1px solid; }
.pidw-leg i.pidw-ln { height: 0; border: 0; border-top: 2px solid; }
.pidw-hatch { background: repeating-linear-gradient(135deg, #8a96a3 0 2px, var(--pidw-hbg) 2px 5px) !important;
  border-color: #8a96a3 !important; }
.pidw-leg2 { margin-left: auto; font-size: 11px; color: var(--pidw-muted); display: inline-flex; gap: 14px; }
.pidw-leg2 i { display: inline-block; width: 18px; height: 0; }
.pidw-head { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 16px; margin-bottom: 8px; }
.pidw-head h2 { margin: 0; padding: 0; font-size: 14px; font-weight: 600; color: var(--pidw-text); }
.pidw-badge { font-size: 11px; padding: 2px 8px; border-radius: 999px; border: 1px solid; }
.pidw-chk { font-size: 12px; display: inline-flex; align-items: center; gap: 6px; color: var(--pidw-muted); cursor: pointer; }
.pidw-chk input { width: 15px; height: 15px; }
.pidw-plot { display: grid; grid-template-columns: 44px minmax(0, 1fr); gap: 6px; }
.pidw-yax { position: relative; font-family: 'IBM Plex Mono', monospace; font-size: 11px; color: var(--pidw-muted); }
.pidw-yax span { position: absolute; right: 0; transform: translateY(-50%); }
.pidw-area { position: relative; border-left: 1px solid var(--pidw-axis); border-bottom: 1px solid var(--pidw-axis);
  cursor: grab; touch-action: none; overflow: hidden; }
.pidw-area svg { display: block; }
.pidw-resid { margin-top: 4px; }
.pidw-wlab { position: absolute; top: 6px; transform: translateX(-104%); font-size: 11px; padding: 1px 6px;
  border-radius: 4px; border: 1px solid; white-space: nowrap; pointer-events: none; }
.pidw-trackrow { margin-top: 6px; }
.pidw-track { position: relative; height: 26px; cursor: grab; touch-action: none; }
.pidw-rail { position: absolute; left: 0; right: 0; top: 11px; height: 4px; background: var(--pidw-grid); border-radius: 2px; }
.pidw-fill { position: absolute; top: 9px; height: 8px; border-radius: 4px; cursor: grab; touch-action: none; }
.pidw-handle { position: absolute; top: 3px; width: 20px; height: 20px; margin-left: -10px; border-radius: 50%;
  border: 2px solid; background: #fff; padding: 0; cursor: ew-resize; touch-action: none; }
.pidw-chips { display: flex; flex-wrap: wrap; gap: 8px; margin: 8px 0 0 50px; align-items: center; }
.pidw-chip { font-family: 'IBM Plex Mono', monospace; font-size: 11px; padding: 4px 8px; border-radius: 6px; border: 1px solid;
  display: inline-flex; align-items: center; gap: 6px; }
.pidw-chip input { font: inherit; width: 58px; padding: 1px 4px; border: 1px solid; border-color: inherit; border-radius: 4px;
  background: var(--pidw-btn); color: var(--pidw-text); }
.pidw-mini { font: inherit; font-size: 11px; padding: 1px 6px; border: 1px solid; border-color: inherit; background: var(--pidw-btn);
  color: inherit; border-radius: 4px; cursor: pointer; }
.pidw-add { font: inherit; font-size: 11px; padding: 4px 10px; border: 1px dashed var(--pidw-axis); background: var(--pidw-btn);
  color: var(--pidw-muted); border-radius: 6px; cursor: pointer; }
.pidw-xax { position: relative; height: 16px; margin-top: 2px; font-family: 'IBM Plex Mono', monospace; font-size: 11px; color: var(--pidw-muted); }
.pidw-xax span { position: absolute; transform: translateX(-50%); white-space: nowrap; }
.pidw-xax .pidw-xu { right: 0; left: auto !important; transform: none; font-family: inherit; }
.pidw-tip { position: absolute; display: none; pointer-events: none; z-index: 5; font-family: 'IBM Plex Mono', monospace;
  font-size: 11px; padding: 4px 8px; border-radius: 6px; border: 1px solid var(--pidw-line); background: var(--pidw-card);
  box-shadow: 0 2px 8px rgba(0,0,0,.12); white-space: nowrap; color: var(--pidw-text); }
"""


def decimate(t, ys):
    """Společná zřeďovací maska pro dlouhé záznamy: z každé skupiny vzorků min a max prvního průběhu."""
    n = len(t)
    if n <= MAX_PTS:
        return np.arange(n)
    g = int(np.ceil(n / (MAX_PTS / 2)))
    ref = np.asarray(ys[0], float)
    m = int(np.ceil(n / g)) * g
    a = np.full(m, np.nan)
    a[:n] = ref
    a = a.reshape(-1, g)
    ok = np.isfinite(a).any(axis=1)
    base = np.arange(a.shape[0]) * g
    imin = base + np.argmin(np.where(np.isfinite(a), a, np.inf), axis=1)
    imax = base + np.argmax(np.where(np.isfinite(a), a, -np.inf), axis=1)
    idx = np.unique(np.concatenate([np.where(ok, imin, base), np.where(ok, imax, base)]))
    return idx[idx < n]


def js(a, idx):
    """Průběh pro prohlížeč: zředěný, zaokrouhlený na 6 platných číslic největší hodnoty, NaN → null."""
    a = np.asarray(a, float)[idx]
    fin = np.isfinite(a)
    big = float(np.abs(a[fin]).max()) if fin.any() else 1.0
    dec = int(np.clip(5 - np.floor(np.log10(max(big, 1e-12))), 0, 12))
    r = np.round(np.where(fin, a, 0.0), dec).tolist()
    return [v if f else None for v, f in zip(r, fin.tolist())]


def rng(y, pad=0.06):
    y = np.asarray(y, float)
    y = y[np.isfinite(y)]
    if not len(y):
        return 0.0, 1.0
    lo, hi = float(y.min()), float(y.max())
    if hi - lo < 1e-9:
        lo, hi = lo - 1, hi + 1
    m = pad * (hi - lo)
    return lo - m, hi + m


def runs(mask, t):
    """Souvislé úseky True v masce → [(od, do) s]."""
    m = np.asarray(mask, bool)
    if not m.any():
        return []
    d = np.diff(np.r_[0, m.astype(int), 0])
    a, b = np.where(d == 1)[0], np.where(d == -1)[0]
    return [(float(t[i]), float(t[min(j, len(t) - 1)])) for i, j in zip(a[:300], b[:300])]


TXT_KEYS = ("mode", "h_mode", "common", "inputs", "zoom", "zoom_all", "zoom_win", "zoom_note", "excluded", "m_all",
            "m_mv", "m_dv", "resid", "only_win", "model", "win", "drag_win", "start", "end", "zoom_one", "del", "add",
            "time")


def base(t, view_key, clock=None):
    """Společná část dat: časy, jednotka osy, hodiny (ms epochy pro t = 0), jazyk, téma, texty."""
    from .theme import palette
    tu = unit_for(ss.get("chart_tunit"), float(t[-1]))
    return dict(T=float(t[-1]), unit=dict(u=tu, f=UNITS[tu]), clock=clock, view_key=view_key,
                dec="," if ss.get("lang", "cs") == "cs" else ".", dark=palette()["bg"] != "#eef1f5",
                txt={k: T("mw_" + k) for k in TXT_KEYS})


def clock_ms(ctx):
    """Absolutní čas začátku záznamu (ms epochy), když data mají datum a čas; jinak None (osa v s / min / h)."""
    try:
        import pandas as pd
        if ctx.t_origin is None or (ss.get("chart_tunit") or "auto") != "auto":
            return None
        return float((pd.Timestamp(ctx.t_origin) + pd.to_timedelta(float(ctx.T0 or 0.0), unit="s")).value / 1e6)
    except Exception:
        return None


def render(key, data, on_wins=None, on_mode=None):
    """Vykreslí komponentu (jen na aktivní záložce). data = base(...) + t, step, mode, rows, …"""
    from .charts import visible
    if not visible():
        return None
    data = dict(data, key=key)
    data["sig"] = hashlib.md5(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()
    comp = v2_component("pidtools_trend", css=_CSS, js=static_asset("trend.js"))
    kw = {}
    if on_wins is not None:
        kw["on_wins_change"] = on_wins
    if on_mode is not None:
        kw["on_mode_change"] = on_mode
    return comp(key=key, data=data, **kw)


def record(ctx, key, title=None, note=None, ab=None, on_wins=None):
    """
    Záznam smyčky (záložky Data a Diagnostika): PV (+ SP), MV, měřené poruchy a poloha ventilu, každá veličina
    ve vlastním grafu. ab = dict(a, b, ca, cb, la, lb) → úseky A / B s táhly (Diagnostika).
    """
    from .charts import visible
    from .theme import C_MV, C_PV, C_SP, _c_dist
    if not visible():
        return None
    t = ctx.t
    pv_e = ctx.EP(ctx.pv)
    series = [pv_e, ctx.EM(ctx.mv)] + [np.asarray(d, float) for d in ctx.dists]
    idx = decimate(t, series)
    lo, hi = rng(np.r_[pv_e, ctx.EP(ctx.sp)] if ctx.has_sp else pv_e)
    pv_row = dict(id="PV", kind="pv", title=f"PV · {ctx.c_pv}" + (f" [{ctx.u_pv}]" if ctx.u_pv else ""), color=C_PV,
                  y=js(pv_e, idx), lo=lo, hi=hi, h=170,
                  lines=[[js(ctx.EP(ctx.sp), idx), C_SP, "5 4", 1.3, "SP"]] if ctx.has_sp else [])
    mv_e = ctx.EM(ctx.mv)
    rows = [pv_row]
    mlo, mhi = rng(mv_e)
    mv_row = dict(id="MV", kind="sig", title=f"MV · {ctx.c_mv}" + (f" [{ctx.u_mv}]" if ctx.u_mv else ""), color=C_MV,
                  y=js(mv_e, idx), lo=mlo, hi=mhi, h=100, lines=[])
    if ctx.pos_e is not None:
        mv_row["lines"].append([js(ctx.pos_e, idx), "#7c3aed", "2 3", 1.2, T("prev_pos")])
        plo, phi = rng(np.r_[mv_e, ctx.pos_e])
        mv_row["lo"], mv_row["hi"] = plo, phi
    rows.append(mv_row)
    for j, (nm, d) in enumerate(zip(ctx.c_d, ctx.dists)):
        dlo, dhi = rng(d)
        rows.append(dict(id=str(nm), kind="sig", title=f"{T('mw_dist')} · {nm}", color=_c_dist()[j % 4],
                         y=js(d, idx), lo=dlo, hi=dhi, h=90, lines=[]))
    data = dict(base(t, f"{key}|{ctx.fname}|{len(t)}", clock_ms(ctx)), mode="ab" if ab else "view", t=js(t, idx),
                step=float(ctx.Ts), rows=rows, excl=[], bar=dict(title=title, note=note, zoom=True))
    if ab:
        data["ab"] = ab
    else:
        data["txt"]["zoom_note"] = T("tr_zoom_note_view")
    return render(key, data, on_wins=on_wins)
