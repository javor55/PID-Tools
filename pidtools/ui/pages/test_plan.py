"""Záložka Plán testu: návrh skokového testu."""
import numpy as np
import pandas as pd
import streamlit as st

from ...core import (step_plan)
from ...i18n import T
from ..charts import REPORT, mkfig, show, style, tr
from ..theme import C_MV, C_PV
from ..widgets import model_name, num, seg

ss = st.session_state

def render(ctx):
    """Záložka Plán testu."""
    H, model, mv_e, mvl_hi, mvl_lo, pv_e, sigma_pv, u_mv, u_pv = ctx.H, ctx.model, ctx.mv_e, ctx.mvl_hi, ctx.mvl_lo, ctx.pv_e, ctx.sigma_pv, ctx.u_mv, ctx.u_pv
    M, MR, PR, lab_mv, lab_pv, lab_t = ctx.M, ctx.MR, ctx.PR, ctx.lab_mv, ctx.lab_pv, ctx.lab_t
    with ctx.tabs["plan"]:
        with st.container(border=True):
            st.markdown(T("plan_intro"))
            src_m = seg(st, T("plan_src"), ["fit", "manual"], "fit" if model is not None else "manual", "plan_src", format_func=lambda x: T("plan_src_" + x), help=T("h_plan_src"))
            src_m = src_m or ("fit" if model is not None else "manual")
            if src_m == "fit" and model is None:
                st.info(T("need_model"))
                src_m = "manual"
            if src_m == "manual":
                q1, q2, q3, q4 = st.columns(4)
                pc = q1.selectbox(T("plan_type"), ["P1D", "P2D", "I1D"], key="plan_type", format_func=model_name)
                k_ = num("K / Ki", "plan_k", 1.0, q2, format="%.4g", help=T("h_plan_k"))
                T1_ = num("T1 [s]", "plan_t1", 60.0, q3, min_value=0.0, help=T("help_T"))
                th_ = num("θ [s]", "plan_th", 10.0, q4, min_value=0.0, help=T("help_theta"))
                pp_ = [k_, max(T1_, 1e-3), th_] if pc != "P2D" else [k_, max(T1_, 1e-3), max(T1_ / 4, 1e-3), th_]
                plan_model = (pc, pp_)
            else:
                plan_model = (model[0], model[1])
            w1, w2, w3, w4 = st.columns(4)
            dpvm = num(T("plan_dpv", u=u_pv or "PV"), "plan_dpv", round(0.05 * PR, 4), w1, min_value=1e-9,
                       help=T("h_plan_dpv"))
            sig0 = sigma_pv * PR / 100 if sigma_pv > 0 else 0.002 * PR
            sig_e = num(T("plan_sigma", u=u_pv or "PV"), f"plan_sigma|{sig0:.4g}", sig0, w2, min_value=0.0, format="%.4g",
                        help=T("h_plan_sigma"))
            snr = num(T("plan_snr"), "plan_snr", 10.0, w3, min_value=1.0, help=T("h_plan_snr"))
            mv_now = num(T("plan_mv0", u=u_mv or "MV"), "plan_mv0", float(np.round(mv_e[-1], 3)), w4, help=T("h_plan_mv0"))
        if plan_model[0] == "P0D":
            plan_model = ("P1D", [plan_model[1][0], 1e-3, plan_model[1][-1]])
        room = (float(M(mvl_lo) - M(mv_now)), float(M(mvl_hi) - M(mv_now)))
        plan = step_plan(plan_model[0], plan_model[1], sig_e / PR * 100, dpvm / PR * 100, room, snr)
        m1, m2, m3, m4 = st.columns(4)
        m1.metric(T("plan_step", u=u_mv or "MV"), f"{plan['dmv'] * MR / 100:.3g}")
        m2.metric(T("plan_hold"), f"{plan['hold']:.0f} s")
        m3.metric(T("plan_total"), f"{plan['total'] / 60:.0f} min")
        m4.metric(T("plan_snr_ach"), f"{plan['snr']:.0f}")
        if not plan["feasible"]:
            st.error(T("plan_infeasible"), icon=":material/error:")
        elif plan["snr"] < snr:
            st.warning(T("plan_low_snr"), icon=":material/warning:")
        if room[0] > -plan["dmv"] or room[1] < plan["dmv"]:
            st.warning(T("plan_room"), icon=":material/warning:")
        fpl = mkfig(2, [0.6, 0.4])
        pv_ref = float(pv_e[-1])
        fpl.add_trace(tr(plan["t"], pv_ref + plan["y"] * PR / 100, T("plan_pv"), C_PV, 2.0), 1, 1)
        for sgn in (1, -1):  # povolená odchylka PV
            fpl.add_hline(y=pv_ref + sgn * dpvm, line=dict(color="#dc2626", dash="dot", width=1), row=1, col=1)
        fpl.add_hrect(y0=pv_ref - sig_e, y1=pv_ref + sig_e, fillcolor="#cbd5e1", opacity=0.3,  # pásmo šumu
                      line_width=0, row=1, col=1)
        fpl.add_trace(tr(plan["t"], mv_now + plan["u"] * MR / 100, "MV", C_MV, 2.0, shape="hv"), 2, 1)
        show(style(fpl, H, [lab_pv, lab_mv], lab_t, rev="plan"), key="chart_plan", fname="step_test_plan",
             report=T("plan_title"))
        seq = []
        ch = np.r_[0, np.where(np.diff(plan["u"]) != 0)[0] + 1]
        for i_ in ch:
            seq.append({T("plan_at"): f"{plan['t'][i_] / 60:.1f} min", T("plan_set", u=u_mv or "MV"): f"{mv_now + plan['u'][i_] * MR / 100:.4g}"})
        stab = pd.DataFrame(seq)
        c1, c2 = st.columns([1, 2])
        c1.dataframe(stab, hide_index=True, width="stretch")
        c1.download_button(T("plan_dl"), stab.to_csv(index=False, sep=";"), "step_test_plan.csv", "text/csv",
                           icon=":material/download:")
        c2.markdown(T("plan_tips_integ") if plan["integ"] else T("plan_tips_self"))
        REPORT["tables"].append((T("plan_title"), stab))


