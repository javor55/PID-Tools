"""
APC – dopředná vazba z měřených poruch: návrh, ověření skokem poruchy, hodnoty pro PIDConL (FFwd).
"""
import numpy as np
import pandas as pd
import streamlit as st

from ....i18n import T
from ... import cache
from ... import ff as ffmod
from ...charts import mkfig, show, style, tr
from ...theme import C_SET1, C_SET2
from ...widgets import num
from . import guide
from ...layout import section, workspace
from ....app import guides as app_guides
from .recommend import rec_a
from ....app.apc import feedforward as app_ff
from .common import C_REF


ss = st.session_state


# ---------------------------------------------------------------- dopředná vazba z měřených poruch
def _reset(k_, vals):
    """Zesílení, lead, lag a zpoždění znovu z návrhu podle modelu (zapnutí a dynamika zůstanou)."""
    for k, v in zip(("gain", "lead", "lag", "delay"), vals):
        ss[k_[k]] = float(v)


def ff_rows(ctx, des):
    """Hodnoty do PCS 7 pro zapnuté poruchy: [(porucha, [(parametr, hodnota, jednotka)])] v jednotkách MV."""
    return app_ff.rows(ctx.c_d, ctx.dists, des, ctx.MR, ctx.u_mv or "MV")


def ff_render(ctx):
    code, p, pdl = ctx.model[0], list(ctx.model[1]), ctx.model[2]
    if not pdl:
        guide.render("ff", app_guides.apc_ff(rec_a(ctx), [], [], p), None)
        st.info(T("ff_need_dist"), icon=":material/info:")
        return
    ws = workspace()
    des = ffmod.design(code, p, pdl)
    names = [str(x) for x in ctx.c_d]
    with ws.main:
        guide.render("ff", app_guides.apc_ff(rec_a(ctx), names, des, p), T("g_impl_ff"))

    # ---- 1. návrh pro každou měřenou poruchu (panel)
    for j, (dn, pdm) in enumerate(zip(names, pdl)):
        k_ = ffmod.keys(j, code, p, pdm)
        g0, tl0, tg0, dl0 = ffmod.defaults(code, p, pdm)
        with section(ws.side, T("ff_dist_title", d=dn), f"apc_ff_d{j}", icon=":material/fast_forward:"):
            st.caption(T("ff_model", k=f"{pdm[0]:.4g}", t=f"{pdm[1]:.4g}", th=f"{pdm[2]:.4g}", tp=f"{p[-1]:.4g}"))
            use = st.toggle(T("ff_use", d=dn), key=k_["use"], help=T("h_ff_use"))
            g = num(T("ff_gain", d=dn), k_["gain"], g0, format="%.5g", help=T("h_ff_gain"))
            st.metric(T("ff_gain_eng", u=ctx.u_mv or "MV", d=dn), f"{ffmod.eng_gain(g, ctx.MR):.4g}",
                      help=T("h_ff_gain_eng"))
            dyn = st.toggle(T("ff_dyn"), key=k_["dyn"], help=T("h_ff_dyn"))
            if dyn:
                num(T("ff_lead"), k_["lead"], tl0, min_value=0.0, format="%.4g", help=T("h_ff_lead"))
                num(T("ff_lag"), k_["lag"], tg0, min_value=0.0, format="%.4g", help=T("h_ff_lag"))
                num(T("ff_delay"), k_["delay"], dl0, min_value=0.0, format="%.4g", help=T("h_ff_delay"))
            if use and pdm[2] < p[-1]:
                st.caption(T("ff_faster", d=dn, td=f"{pdm[2]:.3g}", t=f"{p[-1]:.3g}"))
            st.caption(T("ff_proposal", g=f"{g0:.4g}", tl=f"{tl0:.4g}", tg=f"{tg0:.4g}", dl=f"{dl0:.4g}"))
            vals = [ss.get(k_[k], v) for k, v in (("gain", g0), ("lead", tl0), ("lag", tg0), ("delay", dl0))]
            st.button(T("ff_reset"), key=f"g_ffreset|{j}", icon=":material/restart_alt:", help=T("h_ff_reset"),
                      on_click=_reset, args=(k_, (g0, tl0, tg0, dl0)),
                      disabled=all(abs(float(a) - b) <= 1e-9 * max(1.0, abs(b)) for a, b in zip(vals, (g0, tl0, tg0, dl0))))
    des = ffmod.design(code, p, pdl)
    ffmod.save_state(des)

    # ---- 2. ověření: skok poruchy bez FF / statická / dynamická
    with section(ws.side, T("ff_sim_title"), "apc_ff_sim", icon=":material/timeline:"):
        jsel = st.selectbox(T("ff_sim_dist"), list(range(len(names))), format_func=lambda i: names[i], key="ff_sim_j")
        dd = ctx.dists[jsel]
        span = float(np.nanmax(dd) - np.nanmin(dd)) if len(dd) else 1.0
        step = num(T("ff_step", d=names[jsel]), f"ff_step|{jsel}", float(f"{(span / 2 or 1.0):.3g}"), format="%.4g",
                   help=T("h_ff_step"))
    t, outs = app_ff.simulate(code, p, pdl, ctx.set2_ctrl, des, jsel, step, ctx.samp, cache.pidconl_sim_full)
    kp = app_ff.sim_kpis(t, outs, ctx.PR)
    f = mkfig(2, [0.62, 0.38])
    rows = []
    for key, col, dash in (("none", C_REF, "dot"), ("static", C_SET1, "dash"), ("dynamic", C_SET2, "solid")):
        o = outs[key]
        f.add_trace(tr(t, ctx.EP(o["PV"]), T("ff_" + key), col, 1.8, dash), 1, 1)
        f.add_trace(tr(t, ctx.EM(o["MV"]), T("ff_" + key), col, 1.5, dash, show=False), 2, 1)
        rows.append({T("setting"): T("ff_" + key), T("iae_load"): round(kp[key]["iae"], 4),
                     T("ff_maxdev"): float(f"{kp[key]['maxdev']:.4g}")})
    with ws.main:
        show(style(f, ctx.H, [ctx.lab_pv, ctx.lab_mv], ctx.lab_t, rev="apc_ff"), key="chart_apc_ff",
             fname="feedforward", report=T("apc_ff"))
        st.dataframe(pd.DataFrame(rows), hide_index=True)
        st.caption(T("ff_sim_help"))

    # ---- 3. hodnoty do PCS 7
    tab = ff_rows(ctx, des)
    with section(ws.side, T("ff_tab_title"), "apc_ff_tab", icon=":material/table:"):
        if not tab:
            st.info(T("ff_none_on"), icon=":material/info:")
        for dn, rws in tab:
            st.markdown(f"**{dn}**")
            st.dataframe(pd.DataFrame([{T("sm_apl_block"): a, T("sm_apl_value"): float(f"{v:.4g}"),
                                        T("sm_apl_unit"): u} for a, v, u in rws]), hide_index=True)
        st.caption(T("ff_help"))
