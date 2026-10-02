"""
APC – gain scheduling podle regulační odchylky (ER): vyšší zesílení při velké odchylce, srovnání s ConZone.
"""
import numpy as np
import pandas as pd
import streamlit as st

from ....core import (gs_er_table, iae, settled)
from ....i18n import T
from ... import cache
from ...charts import mkfig, show, style, tr
from ...theme import C_SET1, C_SET2, C_SP
from ...widgets import num, sld
from . import guide
from .recommend import chk_model_a
from ....app.apc import gainsched as app_gs
from .common import C_B, best_cz, clean, gs_frame, grid, gs_sim_c, tchar, ss


# ---------------------------------------------------------------- gain scheduling podle regulační odchylky
def _gs_er_E(ctx):
    """Práh E [jednotky PV] – od této odchylky platí plné zesílení k·Gain."""
    return float(ss.get("gs_er_E") or round(0.05 * ctx.PR, 6))


def gs_er_tab(ctx):
    return app_gs.er_table(_gs_er_E(ctx), float(ss.get("gs_er_k") or 2.0), ctx.set2_ctrl, ctx.u_pv or "PV")


def _k_max(code, p, ctrl, ms_lim=2.0):
    """Největší násobek zesílení k (krok 0,25), při kterém je smyčka stabilní a Ms ≤ ms_lim."""
    return app_gs.k_max(code, p, ctrl, ms_lim, cache.robustness)


def gs_er_render(ctx):
    code, p = ctx.model[0], list(ctx.model[1])
    E, M_ = ctx.EP, ctx.EM
    set2 = clean(ctx.set2_ctrl)
    PR = ctx.PR
    kmax = _k_max(code, p, set2)
    st.markdown(T("gs_er_intro"))

    with st.container(border=True):
        st.markdown(f"**{T('gs_er_s1')}**")
        c1, c2, c3 = st.columns(3)
        e_u = num(T("gs_er_E", u=ctx.u_pv or "PV"), "gs_er_E", round(0.05 * PR, 6), c1, min_value=1e-9,
                  format="%.4g", help=T("h_gs_er_E"))
        k = sld(c2, T("gs_er_k"), 1.0, 6.0, float(min(2.0, max(kmax, 1.0))), "gs_er_k", step=0.25, help=T("h_gs_er_k"))
        rb_k = cache.robustness(code, p, dict(set2, Gain=k * set2["Gain"]))
        ms_k = rb_k["Ms"] if rb_k["stable"] and np.isfinite(rb_k["Ms"]) else np.inf
        c3.metric(T("gs_er_ms"), "∞" if not np.isfinite(ms_k) else f"{ms_k:.2f}",
                  help=T("h_gs_er_ms", k=f"{kmax:.2f}"))
        st.caption(T("gs_er_kmax", k=f"{kmax:.2f}", g=f"{set2['Gain']:.4g}", ti=f"{set2['TI']:.4g}"))
        if kmax < 1.0:
            st.error(T("gs_er_base_bad"), icon=":material/warning:")
        elif not np.isfinite(ms_k) or ms_k > 2.0:
            st.error(T("gs_er_unstable", k=f"{k:.2f}", m=f"{kmax:.2f}"), icon=":material/warning:")

    checks = [chk_model_a(ctx),
              (bool(np.isfinite(ms_k) and ms_k <= 2.0), T("g_chk_gser_ms", m="∞" if not np.isfinite(ms_k) else f"{ms_k:.2f}"),
               None),
              (None, T("g_chk_gser_noise"), None),
              (None, T("g_chk_gser_sat"), None),
              (None, T("g_chk_gser_bumpless"), None)]
    guide.render("gs_er", checks, T("g_impl_gs_er", u=ctx.u_pv or "PV"))

    st.markdown(f"#### {T('gs_tab_title')}", help=T("h_gs_er_tab"))
    st.dataframe(gs_frame(gs_er_tab(ctx)), hide_index=True)

    # ---- simulace: jedna sada / scheduling podle ER / řídicí pásmo
    st.markdown(f"#### {T('gs_er_sim')}", help=T("h_gs_er_sim"))
    s1, s2 = st.columns(2)
    sp_step = num(T("gs_er_spstep", u=ctx.u_pv or "PV"), "gs_er_spstep", round(0.2 * PR, 6), s1, format="%.4g",
                  help=T("h_gs_er_spstep"))
    d_mv = num(T("gs_er_d"), "gs_er_d", 10.0, s2, format="%.3g", help=T("h_gs_er_d"))
    step_pct = float(np.clip(sp_step / PR * 100, -45, 45))
    tp = 15 * tchar((code, p)) + 50 * ctx.samp
    h, nn, t = grid(2 * tp, ctx.samp)
    sp = np.where(t >= 0.05 * tp, 50.0 + step_pct, 50.0)
    d = np.where(t >= tp, float(d_mv), 0.0)
    plant = [dict(x=50.0, u=50.0, p=p)]
    e_pct = float(e_u) / PR * 100
    rows = gs_er_table(e_pct, k, set2["Gain"], set2["TI"], set2.get("TD", 0.0))
    sched = {kk: [q[kq] for q in rows] for kk, kq in (("X", "x"), ("gain", "gain"), ("ti", "ti"), ("td", "td"))}
    tf, of = gs_sim_c(code, plant, set2, None, h, sp, d)
    te, oe = gs_sim_c(code, plant, set2, sched, h, sp, d, "er")
    widths = tuple(float(f) * abs(step_pct) for f in (0.15, 0.3, 0.45, 0.6, 0.75, 0.9))
    cz, scan = best_cz(code, plant, set2, h, sp, d, widths)
    oz = gs_sim_c(code, plant, dict(set2, ConZone=cz), None, h, sp, d)[1] if cz else None
    f = mkfig(3, [0.5, 0.27, 0.23])
    f.add_trace(tr(t, E(sp), "SP", C_SP, 1.3, "dash", "hv"), 1, 1)
    f.add_trace(tr(tf, E(of["PV"]), T("gs_fixed"), C_SET1, 1.6, "dot"), 1, 1)
    f.add_trace(tr(te, E(oe["PV"]), T("gs_er_sched"), C_SET2, 2.0), 1, 1)
    if oz is not None:
        f.add_trace(tr(t, E(oz["PV"]), T("gs_er_cz"), C_B, 1.6, "dashdot"), 1, 1)
    f.add_trace(tr(tf, M_(of["MV"]), T("gs_fixed"), C_SET1, 1.4, "dot", show=False), 2, 1)
    f.add_trace(tr(te, M_(oe["MV"]), T("gs_er_sched"), C_SET2, 1.6, show=False), 2, 1)
    if oz is not None:
        f.add_trace(tr(t, M_(oz["MV"]), T("gs_er_cz"), C_B, 1.4, "dashdot", show=False), 2, 1)
    f.add_trace(tr(tf, of["Gain"], T("gs_fixed"), C_SET1, 1.4, "dot", show=False), 3, 1)
    f.add_trace(tr(te, oe["Gain"], T("gs_er_sched"), C_SET2, 1.6, show=False), 3, 1)
    show(style(f, ctx.H + 120, [ctx.lab_pv, ctx.lab_mv, "Gain"], ctx.lab_t, rev="apc_gser"), key="chart_apc_gser",
         fname="gainsched_er", report=T("gs_x_er"))
    a, b = t < tp, t >= tp
    PRf = PR / 100

    def kpi(name, o):
        return {T("setting"): name, T("iae_sp"): round(iae(t[a], sp[a], o["PV"][a]) * PRf, 4),
                T("iae_load"): round(iae(t[b], sp[b], o["PV"][b]) * PRf, 4),
                T("gs_er_maxdev"): float(f"{np.max(np.abs(sp[b] - o['PV'][b])) * PRf:.4g}"),
                T("gs_er_sat"): f"{100 * np.mean((o['MV'] <= set2.get('MV_Lo', 0) + 1e-6) | (o['MV'] >= set2.get('MV_Hi', 100) - 1e-6)):.0f} %",
                T("gs_er_settled"): "✓" if settled(t, sp, o["PV"]) else "✗"}
    kp = [kpi(T("gs_fixed"), of), kpi(T("gs_er_sched"), oe)] + ([kpi(T("gs_er_cz"), oz)] if oz is not None else [])
    st.dataframe(pd.DataFrame(kp), hide_index=True)
    if cz:
        st.caption(T("gs_er_cz_best", w=f"{cz * PRf:.4g}", u=ctx.u_pv or "PV"))
    else:
        st.info(T("gs_er_cz_none"), icon=":material/info:")
    with st.expander(T("gs_er_cz_scan"), icon=":material/table_rows:"):
        st.dataframe(pd.DataFrame([{f"ConZone [{ctx.u_pv or 'PV'}]": float(f"{w * PRf:.4g}"),
                                    T("iae_sp") + " + " + T("iae_load"): round(v * PRf, 4),
                                    T("gs_er_settled"): "✓" if ok else "✗"} for w, v, ok in scan]), hide_index=True)
        st.caption(T("gs_er_cz_help"))
    st.caption(T("gs_er_sim_help"))
