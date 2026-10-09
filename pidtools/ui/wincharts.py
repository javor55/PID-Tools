"""
Grafy záložky Model s úseky pro identifikaci (společná komponenta grafu průběhů, pidtools.ui.trend): PV s modelem, MV a měřené poruchy, každý vstup
s táhly svých úseků (režim „Podle vstupů“), nebo jeden společný úsek s táhly pod PV (režim „Společný úsek“).
Vyřazené části jsou šrafované. Změny úseků se vrací do session state (wins|soubor, rng_id|…), přepnutí režimu
do „win_mode“.
"""
import numpy as np
import streamlit as st

from ..i18n import T
from . import trend

ss = st.session_state

WIN_STYLE = {           # barvy úseků podle vstupu: výplň, okraj/táhlo, pozadí štítku, rámeček štítku
    "MV": ("#f59e0b", "#c77d00", "#fff4dc", "#f2c46d", "#7a4a00"),
}
DIST_STYLE = [("#0d9488", "#0b7a70", "#e3f5f2", "#8fd3ca", "#0b5c55"),
              ("#7c3aed", "#5b21b6", "#f3effc", "#c9b8f0", "#4c1d95"),
              ("#db2777", "#9d174d", "#fdf0f6", "#f5b8d3", "#831843"),
              ("#0891b2", "#0e7490", "#e6f6fa", "#9fdcec", "#155e75")]

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
    from .charts import visible
    if not visible():                       # jiná záložka – nic nepočítat ani neposílat
        return
    t = ctx.t
    pv_e = ctx.EP(ctx.pv)
    series = [pv_e, ctx.EM(ctx.mv)] + [np.asarray(d, float) for d in ctx.dists]
    idx = trend.decimate(t, series)
    lo, hi = trend.rng(pv_e)
    near = 0.15 * (hi - lo)                              # mez měření PV v grafu, je-li blízko dat
    if 0 <= lo - ctx.pv_lo < near:
        lo = float(ctx.pv_lo) - 0.02 * (hi - lo)
    if 0 <= ctx.pv_hi - hi < near:
        hi = float(ctx.pv_hi) + 0.02 * (hi - lo)
    pv_row = dict(id="PV", kind="pv", title=f"PV · {ctx.c_pv}" + (f" [{ctx.u_pv}]" if ctx.u_pv else ""), color="#1f5fa8",
                  y=trend.js(pv_e, idx), lo=lo, hi=hi, h=220)
    if model is not None:
        pv_row["model"] = {k: (trend.js(ctx.EP(v), idx) if v is not None else None) for k, v in model.items()}
        allm = model.get("all")
        if allm is not None:
            pv_row["resid"] = trend.js((ctx.pv - allm) * ctx.PR / 100, idx)
    rows = [pv_row]
    wins = ss.get(f"wins|{ctx.fname}") or {}
    fits = fits or {}
    inputs = [("MV", ctx.mv_e if ctx.mv_e is not None else ctx.EM(ctx.mv), ctx.c_mv, ctx.u_mv, WIN_STYLE["MV"])]
    for j, (nm, d) in enumerate(zip(ctx.c_d, ctx.dists)):
        inputs.append((str(nm), d, nm, "", DIST_STYLE[j % len(DIST_STYLE)]))
    legend = []
    for k, (rid, y, col_name, unit, sty) in enumerate(inputs):
        w = wins.get(rid, [])
        lo_, hi_ = trend.rng(y)
        badge = (T("mw_badge", k=k + 1, n=len(w)) if ctx.win_mode == "inputs" else None)
        rows.append(dict(id=rid, kind="in", title=f"{rid if rid == 'MV' else T('mw_dist')} · {col_name}"
                         + (f" [{unit}]" if unit else ""), color="#c2410c" if rid == "MV" else sty[0], y=trend.js(y, idx),
                         lo=lo_, hi=hi_, h=110, wins=[[float(a), float(b)] for a, b in w], fits=fits.get(rid, []),
                         wcol=sty[0], wtx=sty[1], wbg=sty[2], wbd=sty[3], badge=badge,
                         note=T("mw_note_in") if ctx.win_mode == "inputs" else None))
        legend.append([sty[1], rid, sty[2]])
    excl = trend.runs(~ctx.valid, t) if (ctx.win_mode == "inputs" and ctx.valid is not None) else []
    if excl:
        legend.append(["#8a96a3", T("mw_excluded"), "hatch"])
    rng0 = ss.get(rng_key) or (0.0, float(t[-1]))
    data = dict(trend.base(t, f"model|{ctx.fname}|{len(t)}", trend.clock_ms(ctx)), mode=ctx.win_mode,
                t=trend.js(t, idx), step=float(ctx.Ts), rows=rows, excl=excl, common=[float(rng0[0]), float(rng0[1])],
                bar=dict(mode_switch=True, zoom=True, legend=legend if ctx.win_mode == "inputs" else []))
    trend.render("model_wins", data, on_wins=lambda: _on_wins(ctx.fname, rng_key), on_mode=_on_mode)
