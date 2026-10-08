"""
APC – override: hlavní a omezující regulátor na jednom ventilu, výběr MIN/MAX s externím resetem.
"""
import streamlit as st

from ....i18n import T
from ...charts import mkfig, show, style, tr
from ...theme import C_MV, C_PV, C_SP
from ...widgets import num, reset_button, seg
from . import guide
from ...layout import section
from ....app.apc import override as aov
from ....app import guides as app_guides
from .common import C_B, C_REF, active_model, eng, lab, override_sim_c


# ---------------------------------------------------------------- override
def override_render(ctx, bi, b, ws):
    a = active_model(ctx)
    same = b["c_mv"] == a["c_mv"]
    checks = app_guides.apc_override(a, b, bi)
    guide_ph = ws.main.container()   # průvodce nahoře, vyplní se až se známou mezí
    if not same:
        ws.main.warning(T("ov_mv_differs", a=a["name"], b=b["name"], mva=a["c_mv"], mvb=b["c_mv"]),
                        icon=":material/warning:")
    with section(ws.side, T("ov_select"), "apc_ov_set", icon=":material/tune:"):
        sel = seg(st, T("ov_select"), ["min", "max"], "min", "apc_ov_sel", format_func=lambda x: T("ov_" + x),
                  help=T("h_ov_select")) or "min"
        step_def, lim_def = aov.defaults(a, b, sel)
        step_a = num(T("ov_step", n=a["name"], u=a["u_pv"] or "PV"), f"apc_ov_step|{sel}", step_def, format="%.4g",
                     help=T("h_ov_step"))
        lim = num(T("ov_limit", n=b["name"], u=b["u_pv"] or "PV"), f"apc_ov_lim|{b['name']}|{sel}", lim_def,
                  format="%.4g", help=T("h_ov_limit"))
        reset_button(st, "apc_ov", [(f"apc_ov_step|{sel}", step_def), (f"apc_ov_lim|{b['name']}|{sel}", lim_def)])
        kbox = st.container()
    with guide_ph:
        guide.render("override", checks, T("g_impl_override", a=a["name"], b=b["name"], s=T("ov_" + sel),
                                           lim=f"{lim:.4g}", u=b["u_pv"] or ""))
    tt, o, o0 = aov.simulate(a, b, step_a, lim, sel, override_sim_c)
    n = len(tt)
    EA, EB, M = eng(a["pv_rng"]), eng(b["pv_rng"]), eng(a["mv_rng"])

    m1, m2, m3 = kbox, kbox, kbox
    k_ = aov.kpis(a, b, o, o0, sel)
    m1.metric(T("ov_peak", n=b["name"]), f"{k_['peak']:.4g}",
              delta=f"{k_['peak_without'] - lim:+.3g} {T('ov_without')}", delta_color="off")
    m2.metric(T("ov_time_b"), f"{100 * k_['share']:.0f} %")
    m3.metric(T("ov_switches"), k_["switches"])

    f = mkfig(3, [0.36, 0.36, 0.28])
    f.add_trace(tr(tt, EA(o["SP_A"]), f"SP {a['name']}", C_SP, 1.3, "dash", "hv"), 1, 1)
    f.add_trace(tr(tt, EA(o0["PV_A"]), T("ov_without"), C_REF, 1.3, "dot", group="ref"), 1, 1)
    f.add_trace(tr(tt, EA(o["PV_A"]), f"PV {a['name']}", C_PV, 2.0), 1, 1)
    f.add_trace(tr(tt, EB(o["SP_B"]), T("ov_limit_short"), "#dc2626", 1.3, "dash"), 2, 1)
    f.add_trace(tr(tt, EB(o0["PV_B"]), T("ov_without"), C_REF, 1.3, "dot", show=False, group="ref"), 2, 1)
    f.add_trace(tr(tt, EB(o["PV_B"]), f"PV {b['name']}", C_B, 2.0), 2, 1)
    f.add_trace(tr(tt, M(o["U_A"]), T("ov_out", n=a["name"]), C_PV, 1.1, "dot"), 3, 1)
    f.add_trace(tr(tt, M(o["U_B"]), T("ov_out", n=b["name"]), C_B, 1.1, "dot"), 3, 1)
    f.add_trace(tr(tt, M(o["MV"]), "MV", C_MV, 2.0), 3, 1)
    for s_, e_ in aov.active_spans(o["ACT"]):  # úseky, kdy řídí omezující regulátor
        for r in (1, 2, 3):
            f.add_vrect(x0=tt[s_], x1=tt[min(e_, n - 1)], fillcolor=C_B, opacity=0.08, line_width=0, row=r, col=1)
    with ws.main:
        show(style(f, ctx.H + 120, [lab(a["name"], a["u_pv"]), lab(b["name"], b["u_pv"]), lab("MV", a["u_mv"])],
                   ctx.lab_t, rev="apc_ov"), key="chart_apc_ov", fname="override", report=T("apc_override"))
        st.caption(T("ov_sim_help", b=b["name"]))
