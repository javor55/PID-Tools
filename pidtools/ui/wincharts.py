"""
Grafy záložky Model s úseky pro identifikaci (komponenta wins.js): PV s modelem, MV a měřené poruchy, každý vstup
s táhly svých úseků (režim „Podle vstupů“), nebo jeden společný úsek s táhly pod PV (režim „Společný úsek“).
Vyřazené části jsou šrafované. Změny úseků se vrací do session state (wins|soubor, rng_id|…), přepnutí režimu
do „win_mode“.
"""
import numpy as np
import streamlit as st

from ..app.timefmt import UNITS, unit_for
from ..i18n import T
from .widgets import static_asset, v2_component

ss = st.session_state
MAX_PTS = 6000          # bodů na průběh poslaný do prohlížeče (min/max po skupinách, tvar zůstane)

WIN_STYLE = {           # barvy úseků podle vstupu: výplň, okraj/táhlo, pozadí štítku, rámeček štítku
    "MV": ("#f59e0b", "#c77d00", "#fff4dc", "#f2c46d", "#7a4a00"),
}
DIST_STYLE = [("#0d9488", "#0b7a70", "#e3f5f2", "#8fd3ca", "#0b5c55"),
              ("#7c3aed", "#5b21b6", "#f3effc", "#c9b8f0", "#4c1d95"),
              ("#db2777", "#9d174d", "#fdf0f6", "#f5b8d3", "#831843"),
              ("#0891b2", "#0e7490", "#e6f6fa", "#9fdcec", "#155e75")]

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
.pidw-lab { font-size: 13px; color: var(--pidw-muted); }
.pidw-note { font-size: 12px; color: var(--pidw-muted); }
.pidw-help { width: 20px; height: 20px; border-radius: 50%; border: 1px solid #9aa5b1; color: var(--pidw-muted);
  font-size: 12px; font-weight: 600; display: inline-flex; align-items: center; justify-content: center; cursor: help; }
.pidw-seg { display: inline-flex; border: 1px solid var(--pidw-axis); border-radius: 8px; overflow: hidden; }
.pidw-seg button { font: inherit; font-size: 13px; padding: 6px 12px; border: 0; background: var(--pidw-btn);
  color: var(--pidw-text); cursor: pointer; }
.pidw-seg button + button { border-left: 1px solid var(--pidw-axis); }
.pidw-seg button.on { background: #1f5fa8; color: #fff; font-weight: 500; }
.pidw-model button { font-size: 12px; padding: 5px 10px; }
.pidw-model button.on { background: #5b3fa8; }
.pidw-leg { display: flex; gap: 14px; margin-left: auto; flex-wrap: wrap; font-size: 12px; color: var(--pidw-muted); }
.pidw-leg span, .pidw-leg2 span { display: inline-flex; align-items: center; gap: 6px; }
.pidw-leg i { display: inline-block; width: 14px; height: 10px; border: 1px solid; }
.pidw-hatch { background: repeating-linear-gradient(135deg, #8a96a3 0 2px, var(--pidw-hbg) 2px 5px) !important;
  border-color: #8a96a3 !important; }
.pidw-leg2 { margin-left: auto; font-size: 12px; color: var(--pidw-muted); display: inline-flex; gap: 14px; }
.pidw-leg2 i { display: inline-block; width: 18px; height: 0; }
.pidw-head { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 16px; margin-bottom: 8px; }
.pidw-head h2 { margin: 0; padding: 0; font-size: 15px; font-weight: 600; color: var(--pidw-text); }
.pidw-badge { font-size: 12px; padding: 2px 8px; border-radius: 999px; border: 1px solid; }
.pidw-chk { font-size: 13px; display: inline-flex; align-items: center; gap: 6px; color: var(--pidw-muted); cursor: pointer; }
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
.pidw-track { position: relative; height: 26px; }
.pidw-rail { position: absolute; left: 0; right: 0; top: 11px; height: 4px; background: var(--pidw-grid); border-radius: 2px; }
.pidw-fill { position: absolute; top: 9px; height: 8px; border-radius: 4px; cursor: grab; touch-action: none; }
.pidw-handle { position: absolute; top: 3px; width: 20px; height: 20px; margin-left: -10px; border-radius: 50%;
  border: 2px solid; background: #fff; padding: 0; cursor: ew-resize; touch-action: none; }
.pidw-chips { display: flex; flex-wrap: wrap; gap: 8px; margin: 8px 0 0 50px; align-items: center; }
.pidw-chip { font-family: 'IBM Plex Mono', monospace; font-size: 12px; padding: 4px 8px; border-radius: 6px; border: 1px solid;
  display: inline-flex; align-items: center; gap: 6px; }
.pidw-chip input { font: inherit; width: 58px; padding: 1px 4px; border: 1px solid; border-color: inherit; border-radius: 4px;
  background: var(--pidw-btn); color: var(--pidw-text); }
.pidw-mini { font: inherit; font-size: 11px; padding: 1px 6px; border: 1px solid; border-color: inherit; background: var(--pidw-btn);
  color: inherit; border-radius: 4px; cursor: pointer; }
.pidw-add { font: inherit; font-size: 12px; padding: 4px 10px; border: 1px dashed var(--pidw-axis); background: var(--pidw-btn);
  color: var(--pidw-muted); border-radius: 6px; cursor: pointer; }
.pidw-xax { position: relative; height: 18px; font-family: 'IBM Plex Mono', monospace; font-size: 11px; color: var(--pidw-muted); }
.pidw-xax span { position: absolute; transform: translateX(-50%); white-space: nowrap; }
.pidw-xax .pidw-xu { right: 0; left: auto !important; transform: none; font-family: inherit; }
.pidw-tip { position: absolute; display: none; pointer-events: none; z-index: 5; font-family: 'IBM Plex Mono', monospace;
  font-size: 11.5px; padding: 4px 8px; border-radius: 6px; border: 1px solid var(--pidw-line); background: var(--pidw-card);
  box-shadow: 0 2px 8px rgba(0,0,0,.12); white-space: nowrap; color: var(--pidw-text); }
"""


def _decimate(t, ys):
    """Společná zřeďovací maska pro dlouhé záznamy: z každé skupiny vzorků min a max (tvar křivky zůstane)."""
    n = len(t)
    if n <= MAX_PTS:
        return np.arange(n)
    g = int(np.ceil(n / (MAX_PTS / 2)))
    idx = set()
    ref = np.asarray(ys[0], float)
    for s in range(0, n, g):
        seg = ref[s:s + g]
        if not np.isfinite(seg).any():
            idx.add(s)
            continue
        idx.add(s + int(np.nanargmin(seg)))
        idx.add(s + int(np.nanargmax(seg)))
    return np.array(sorted(idx))


def _js(a, idx):
    a = np.asarray(a, float)[idx]
    return [None if not np.isfinite(v) else float(f"{v:.6g}") for v in a]


def _rng(y, pad=0.06):
    y = np.asarray(y, float)
    y = y[np.isfinite(y)]
    if not len(y):
        return 0.0, 1.0
    lo, hi = float(y.min()), float(y.max())
    if hi - lo < 1e-9:
        lo, hi = lo - 1, hi + 1
    m = pad * (hi - lo)
    return lo - m, hi + m


def _runs(mask, t):
    """Souvislé úseky True v masce → [(od, do) s]."""
    m = np.asarray(mask, bool)
    if not m.any():
        return []
    d = np.diff(np.r_[0, m.astype(int), 0])
    a, b = np.where(d == 1)[0], np.where(d == -1)[0]
    return [(float(t[i]), float(t[min(j, len(t) - 1)])) for i, j in zip(a[:300], b[:300])]


def _on_mode():
    v = ss.get("model_wins")
    m = getattr(v, "mode", None) if not isinstance(v, dict) else v.get("mode")
    if m in ("common", "inputs"):
        ss["win_mode"] = m


def _on_wins(fname, rng_key):
    v = ss.get("model_wins")
    w = getattr(v, "wins", None) if not isinstance(v, dict) else v.get("wins")
    if not w:
        return
    if w.get("wins") is not None:
        ss[f"wins|{fname}"] = {k: [[float(a), float(b)] for a, b in v_] for k, v_ in w["wins"].items()}
    if w.get("common"):
        ss["pending_rng"] = (float(w["common"][0]), float(w["common"][1]))


def render(ctx, model=None, fits=None, rng_key=None):
    """
    Grafy s úseky. model = dict(all, mv, dv, full) průběhů modelu v % PV na celém záznamu (NaN mimo úseky) nebo None;
    fits = {vstup: [FIT úseků]}.
    """
    t = ctx.t
    tu = unit_for(ss.get("chart_tunit"), float(t[-1]))
    pv_e = ctx.EP(ctx.pv)
    series = [pv_e, ctx.EM(ctx.mv)] + [np.asarray(d, float) for d in ctx.dists]
    idx = _decimate(t, series)
    lo, hi = _rng(pv_e)
    near = 0.15 * (hi - lo)                              # mez měření PV v grafu, je-li blízko dat
    if 0 <= lo - ctx.pv_lo < near:
        lo = float(ctx.pv_lo) - 0.02 * (hi - lo)
    if 0 <= ctx.pv_hi - hi < near:
        hi = float(ctx.pv_hi) + 0.02 * (hi - lo)
    pv_row = dict(id="PV", kind="pv", title=f"PV · {ctx.c_pv}" + (f" [{ctx.u_pv}]" if ctx.u_pv else ""), color="#1f5fa8",
                  y=_js(pv_e, idx), lo=lo, hi=hi, h=220, wins=[])
    if model is not None:
        pv_row["model"] = {k: (_js(ctx.EP(v), idx) if v is not None else None) for k, v in model.items()}
        allm = model.get("all")
        if allm is not None:
            pv_row["resid"] = _js((ctx.pv - allm) * ctx.PR / 100, idx)
    rows = [pv_row]
    wins = ss.get(f"wins|{ctx.fname}") or {}
    fits = fits or {}
    inputs = [("MV", ctx.mv_e if ctx.mv_e is not None else ctx.EM(ctx.mv), ctx.c_mv, ctx.u_mv, WIN_STYLE["MV"])]
    for j, (nm, d) in enumerate(zip(ctx.c_d, ctx.dists)):
        inputs.append((str(nm), d, nm, "", DIST_STYLE[j % len(DIST_STYLE)]))
    for k, (rid, y, col_name, unit, sty) in enumerate(inputs):
        w = wins.get(rid, [])
        lo_, hi_ = _rng(y)
        n = len(w)
        badge = (T("mw_badge", k=k + 1, n=n) if ctx.win_mode == "inputs" else None)
        rows.append(dict(id=rid, kind="in", title=f"{rid if rid == 'MV' else T('mw_dist')} · {col_name}"
                         + (f" [{unit}]" if unit else ""), color="#c2410c" if rid == "MV" else sty[0], y=_js(y, idx),
                         lo=lo_, hi=hi_, h=110, wins=[[float(a), float(b)] for a, b in w], fits=fits.get(rid, []),
                         wcol=sty[0], wtx=sty[1], wbg=sty[2], wbd=sty[3], badge=badge,
                         note=T("mw_note_in") if ctx.win_mode == "inputs" else None))
    excl = _runs(~ctx.valid, t) if (ctx.win_mode == "inputs" and ctx.valid is not None) else []
    rng0 = ss.get(rng_key) or (0.0, float(t[-1]))
    from .theme import palette
    data = dict(dark=palette()["bg"] != "#eef1f5", mode=ctx.win_mode, t=_js(t, idx), T=float(t[-1]), step=float(ctx.Ts), unit=dict(u=tu, f=UNITS[tu]),
                dec="," if ss.get("lang", "cs") == "cs" else ".", rows=rows, excl=excl,
                common=[float(rng0[0]), float(rng0[1])], view_key=f"{ctx.fname}|{len(t)}",
                txt={k: T("mw_" + k) for k in (
                    "mode", "h_mode", "common", "inputs", "zoom", "zoom_all", "zoom_win", "zoom_note", "excluded",
                    "m_all", "m_mv", "m_dv", "resid", "only_win", "model", "win", "drag_win", "start", "end",
                    "zoom_one", "del", "add", "time")})
    comp = v2_component("pidtools_wins", css=_CSS, js=static_asset("wins.js"))
    comp(key="model_wins", data=data, on_mode_change=_on_mode, on_wins_change=lambda: _on_wins(ctx.fname, rng_key))
