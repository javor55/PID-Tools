"""
APC – dopředná vazba z měřených poruch: návrh, ověření skokem poruchy, hodnoty pro PIDConL (FFwd).
"""
import numpy as np
import pandas as pd
import streamlit as st

from ....core import (iae)
from ....i18n import T
from ... import cache
from ... import ff as ffmod
from ...charts import mkfig, show, style, tr
from ...theme import C_SET1, C_SET2
from ...widgets import num
from . import guide
from .recommend import chk_model_a
from .common import C_REF, clean, grid


# ---------------------------------------------------------------- dopředná vazba z měřených poruch
def ff_rows(ctx, des):
    """Hodnoty do PCS 7 pro zapnuté poruchy: [(porucha, [(parametr, hodnota, jednotka)])] v jednotkách MV."""
    out = []
    u_mv = ctx.u_mv or "MV"
    for j, (dn, d) in enumerate(zip(ctx.c_d, des)):
        if not d["use"]:
            continue
        g = ffmod.eng_gain(d["gain"], ctx.MR)
        dd = ctx.dists[j]
        span = float(np.nanmax(dd) - np.nanmin(dd)) if len(dd) else 0.0
        lim = float(min(ctx.MR, 1.5 * abs(g) * span)) if span > 0 else float(ctx.MR)
        rows = [(T("ff_p_gain"), g, f"{u_mv} / 1 {dn}")]
        if d["dyn"]:
            lead, lag, delay = ffmod.lead_lag(d)
            if lag > 0:
                rows += [(T("ff_p_lead"), lead, "s"), (T("ff_p_lag"), lag, "s")]
            if delay > 0:
                rows.append((T("ff_p_delay"), delay, "s"))
        rows += [("PIDConL.FFwdHiLim", lim, u_mv), ("PIDConL.FFwdLoLim", -lim, u_mv)]
        out.append((str(dn), rows))
    return out


def ff_render(ctx):
    code, p, pdl = ctx.model[0], list(ctx.model[1]), ctx.model[2]
    if not pdl:
        guide.render("ff", [chk_model_a(ctx), (False, T("g_chk_ff_dist"), (T("tgb_data"), guide.goto, (None, "data")))],
                     None)
        st.info(T("ff_need_dist"), icon=":material/info:")
        return
    des = ffmod.design(code, p, pdl)
    names = [str(x) for x in ctx.c_d]
    slow = [n for n, pdm, d in zip(names, pdl, des) if d["use"] and pdm[2] < p[-1]]
    checks = [chk_model_a(ctx),
              (True, T("g_chk_ff_dist_ok", d=", ".join(names)), None),
              (any(d["use"] for d in des), T("g_chk_ff_on"), None),
              ((None if slow else True), T("g_chk_ff_fast", d=", ".join(slow)) if slow else T("g_chk_ff_fast_ok"), None),
              (None, T("g_chk_ff_indep"), None),
              (None, T("g_chk_ff_commission"), None)]
    guide.render("ff", checks, T("g_impl_ff"))

    # ---- 1. návrh pro každou měřenou poruchu
    set2 = clean(ctx.set2_ctrl)
    for j, (dn, pdm) in enumerate(zip(names, pdl)):
        k_ = ffmod.keys(j, code, p, pdm)
        g0, tl0, tg0, dl0 = ffmod.defaults(code, p, pdm)
        with st.container(border=True):
            st.markdown(f"**{T('ff_dist_title', d=dn)}**")
            st.caption(T("ff_model", k=f"{pdm[0]:.4g}", t=f"{pdm[1]:.4g}", th=f"{pdm[2]:.4g}", tp=f"{p[-1]:.4g}"))
            f1, f2, f3 = st.columns([1, 1.4, 1.4], vertical_alignment="bottom")
            use = f1.toggle(T("ff_use", d=dn), key=k_["use"], help=T("h_ff_use"))
            g = num(T("ff_gain", d=dn), k_["gain"], g0, f2, format="%.5g", help=T("h_ff_gain"))
            f3.metric(T("ff_gain_eng", u=ctx.u_mv or "MV", d=dn), f"{ffmod.eng_gain(g, ctx.MR):.4g}",
                      help=T("h_ff_gain_eng"))
            dyn = st.toggle(T("ff_dyn"), key=k_["dyn"], help=T("h_ff_dyn"))
            if dyn:
                l1, l2, l3 = st.columns(3)
                num(T("ff_lead"), k_["lead"], tl0, l1, min_value=0.0, format="%.4g", help=T("h_ff_lead"))
                num(T("ff_lag"), k_["lag"], tg0, l2, min_value=0.0, format="%.4g", help=T("h_ff_lag"))
                num(T("ff_delay"), k_["delay"], dl0, l3, min_value=0.0, format="%.4g", help=T("h_ff_delay"))
            if use and pdm[2] < p[-1]:
                st.caption(T("ff_faster", d=dn, td=f"{pdm[2]:.3g}", t=f"{p[-1]:.3g}"))
    des = ffmod.design(code, p, pdl)
    ffmod.save_state(des)

    # ---- 2. ověření: skok poruchy bez FF / statická / dynamická
    st.markdown(f"#### {T('ff_sim_title')}", help=T("h_ff_sim"))
    s1, s2 = st.columns(2)
    jsel = s1.selectbox(T("ff_sim_dist"), list(range(len(names))), format_func=lambda i: names[i], key="ff_sim_j")
    dd = ctx.dists[jsel]
    span = float(np.nanmax(dd) - np.nanmin(dd)) if len(dd) else 1.0
    step = num(T("ff_step", d=names[jsel]), f"ff_step|{jsel}", float(f"{(span / 2 or 1.0):.3g}"), s2, format="%.4g",
               help=T("h_ff_step"))
    pdm = pdl[jsel]
    t_end = 12 * (max(p[-1], pdm[2]) + sum(p[1:-1]) + pdm[1]) + 50 * ctx.samp
    h, n, t = grid(t_end, ctx.samp)
    dm = [np.where((t >= 0.1 * t_end) & (i == jsel), float(step), 0.0) for i in range(len(pdl))]
    sp = np.full(n, 50.0)
    dsel = dict(des[jsel], use=True)
    variants = [("none", [0.0] * len(pdl), [(0.0, 0.0, 0.0)] * len(pdl), C_REF, "dot"),
                ("static", *ffmod.to_ctrl([dsel if i == jsel else des[i] for i in range(len(des))], only=jsel,
                                          dyn=False), C_SET1, "dash"),
                ("dynamic", *ffmod.to_ctrl([dict(dsel, dyn=True) if i == jsel else des[i] for i in range(len(des))],
                                           only=jsel, dyn=True), C_SET2, "solid")]
    f = mkfig(2, [0.62, 0.38])
    rows = []
    PRf = ctx.PR / 100
    for key, ffv, ffl, col, dash in variants:
        o = cache.pidconl_sim_full(code, p, [list(x) for x in pdl], h, sp, 50.0, 50.0,
                                   dict(set2, FF=ffv, FF_LL=ffl), dm)
        f.add_trace(tr(t, ctx.EP(o["PV"]), T("ff_" + key), col, 1.8, dash), 1, 1)
        f.add_trace(tr(t, ctx.EM(o["MV"]), T("ff_" + key), col, 1.5, dash, show=False), 2, 1)
        rows.append({T("setting"): T("ff_" + key), T("iae_load"): round(iae(t, sp, o["PV"]) * PRf, 4),
                     T("ff_maxdev"): float(f"{np.max(np.abs(o['PV'] - 50.0)) * PRf:.4g}")})
    show(style(f, ctx.H, [ctx.lab_pv, ctx.lab_mv], ctx.lab_t, rev="apc_ff"), key="chart_apc_ff", fname="feedforward",
         report=T("apc_ff"))
    st.dataframe(pd.DataFrame(rows), hide_index=True)
    st.caption(T("ff_sim_help"))

    # ---- 3. hodnoty do PCS 7
    tab = ff_rows(ctx, des)
    st.markdown(f"#### {T('ff_tab_title')}", help=T("h_ff_tab"))
    if not tab:
        st.info(T("ff_none_on"), icon=":material/info:")
    for dn, rws in tab:
        st.markdown(f"**{dn}**")
        st.dataframe(pd.DataFrame([{T("sm_apl_block"): a, T("sm_apl_value"): float(f"{v:.4g}"), T("sm_apl_unit"): u}
                               for a, v, u in rws]), hide_index=True)
    st.caption(T("ff_help"))
