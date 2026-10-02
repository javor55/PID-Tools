"""
APC – override: hlavní a omezující regulátor na jednom ventilu, výběr MIN/MAX s externím resetem.
"""
import numpy as np
import streamlit as st

from ....core import (MODELS)
from ....i18n import T
from ...charts import mkfig, show, style, tr
from ...theme import C_MV, C_PV, C_SP
from ...widgets import model_name, num, seg
from . import guide
from .recommend import chk_model_a
from .common import C_B, C_REF, active_model, clean, eng, grid, lab, override_sim_c, tchar


# ---------------------------------------------------------------- override
def override_render(ctx, bi, b):
    a = active_model(ctx)
    same = b["c_mv"] == a["c_mv"]
    checks = [chk_model_a(ctx), (True, T("g_chk_model_ok", n=b["name"], m=model_name(b["model"][0])), None),
              (same, T("g_chk_same_mv", a=a["name"], b=b["name"], mv=a["c_mv"]),
               (T("g_btn_data", n=b["name"]), guide.goto, (bi, "data"))),
              (None, T("g_chk_ov_dir", b=b["name"]), None), (None, T("g_chk_tuned"), None)]
    guide_ph = st.container()   # průvodce nahoře, vyplní se až se známou mezí
    if not same:
        st.warning(T("ov_mv_differs", a=a["name"], b=b["name"], mva=a["c_mv"], mvb=b["c_mv"]), icon=":material/warning:")
    ga, gb = (a["model"][0], list(a["model"][1])), (b["model"][0], list(b["model"][1]))
    ka, kb = ga[1][0], gb[1][0]
    c1, c2, c3 = st.columns([1.2, 1, 1], vertical_alignment="bottom")
    sel = seg(c1, T("ov_select"), ["min", "max"], "min", "apc_ov_sel", format_func=lambda x: T("ov_" + x),
              help=T("h_ov_select")) or "min"
    # výchozí scénář: změna SP hlavní smyčky žene MV směrem, který omezení hlídá; mez v půlce očekávané změny PV_B
    dir_mv = 1.0 if sel == "min" else -1.0
    PRa = a["pv_rng"][1] - a["pv_rng"][0]
    PRb = b["pv_rng"][1] - b["pv_rng"][0]
    step_def = round(dir_mv * np.sign(ka) * 0.2 * PRa, 4)
    dmv = 20.0 if MODELS[ga[0]]["integ"] else min(abs(0.2 * 100 / ka), 40.0)
    dpvb = 10.0 * np.sign(kb) * dir_mv if MODELS[gb[0]]["integ"] else kb * dir_mv * dmv
    lim_def = round(b["pv_rng"][0] + PRb / 2 + 0.5 * np.clip(dpvb, -45, 45) * PRb / 100, 4)
    step_a = num(T("ov_step", n=a["name"], u=a["u_pv"] or "PV"), f"apc_ov_step|{sel}", step_def, c2, format="%.4g",
                 help=T("h_ov_step"))
    lim = num(T("ov_limit", n=b["name"], u=b["u_pv"] or "PV"), f"apc_ov_lim|{b['name']}|{sel}", lim_def, c3,
              format="%.4g", help=T("h_ov_limit"))
    with guide_ph:
        guide.render("override", checks, T("g_impl_override", a=a["name"], b=b["name"], s=T("ov_" + sel),
                                           lim=f"{lim:.4g}", u=b["u_pv"] or ""))
    ctrl_a, ctrl_b = clean(a["ctrl"]), clean(b["ctrl"])
    t_end = 14 * max(tchar(ga), tchar(gb)) + 200 * max(ctrl_a["SampleTime"], ctrl_b["SampleTime"])
    h, n, t = grid(t_end, min(ctrl_a["SampleTime"], ctrl_b["SampleTime"]))
    sp_a = np.where(t >= 0.05 * t_end, 50.0 + step_a / PRa * 100, 50.0)
    sp_a[t >= 0.6 * t_end] = 50.0
    sp_b = np.full(n, (lim - b["pv_rng"][0]) / PRb * 100)
    tt, o = override_sim_c(ga, gb, ctrl_a, ctrl_b, h, sp_a, sp_b, sel, True)
    _, o0 = override_sim_c(ga, gb, ctrl_a, ctrl_b, h, sp_a, sp_b, sel, False)
    EA, EB, M = eng(a["pv_rng"]), eng(b["pv_rng"]), eng(a["mv_rng"])

    m1, m2, m3 = st.columns(3)
    worst = (np.max if np.sign(kb) * dir_mv > 0 else np.min)
    m1.metric(T("ov_peak", n=b["name"]), f"{EB(worst(o['PV_B'])):.4g}",
              delta=f"{EB(worst(o0['PV_B'])) - lim:+.3g} {T('ov_without')}", delta_color="off")
    m2.metric(T("ov_time_b"), f"{100 * np.mean(o['ACT']):.0f} %")
    m3.metric(T("ov_switches"), int(np.abs(np.diff(o["ACT"])).sum()))

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
    act = np.r_[0, o["ACT"], 0]
    starts, ends = np.where(np.diff(act) == 1)[0], np.where(np.diff(act) == -1)[0]
    for s_, e_ in list(zip(starts, ends))[:50]:  # úseky, kdy řídí omezující regulátor
        for r in (1, 2, 3):
            f.add_vrect(x0=tt[s_], x1=tt[min(e_, n - 1)], fillcolor=C_B, opacity=0.08, line_width=0, row=r, col=1)
    show(style(f, ctx.H + 120, [lab(a["name"], a["u_pv"]), lab(b["name"], b["u_pv"]), lab("MV", a["u_mv"])],
               ctx.lab_t, rev="apc_ov"), key="chart_apc_ov", fname="override", report=T("apc_override"))
    st.caption(T("ov_sim_help", b=b["name"]))
