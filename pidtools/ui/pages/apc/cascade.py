"""Záložka Kaskáda: ladění vnitřní a vnější smyčky a simulace kaskády."""
import numpy as np
import streamlit as st

from ....core import (MODELS, default_tc)
from ....i18n import T
from ... import cache, loops
from ...cache import cascade_sim, fit_model, pidconl_sim
from ...charts import mkfig, show, style, tr
from ...theme import C_MV, C_PV, C_SET2, C_SP
from ...layout import section, workspace
from ...widgets import model_name, num, seg, sld
from ....app.apc import cascade as acas

ss = st.session_state

def render_body(ctx):
    """Kaskáda (v záložce APC)."""
    H, Ts, base_ctrl, diffgain, fname, model, samp, sel_mask, sigs, ts_id = ctx.H, ctx.Ts, ctx.base_ctrl, ctx.diffgain, ctx.fname, ctx.model, ctx.samp, ctx.sel_mask, ctx.sigs, ctx.ts_id
    EP, M, lab_pv, lab_t = ctx.EP, ctx.M, ctx.lab_pv, ctx.lab_t
    ws = workspace()
    with section(ws.side, T("dk_sec_about"), "apc_cas_about", expanded=False):
        st.markdown(T("cas_intro"))
    with ws.main:
        if model is None:
            st.info(T("need_model"), icon=":material/arrow_back:")
        else:
            with section(ws.side, T("cas_inner"), "apc_cas_inner", icon=":material/input:"):
                other = [i for i in loops.ids() if i != loops.active()]
                src_opts = (["loop"] if other else []) + ["data", "manual"]
                isrc = seg(st, T("cas_src"), src_opts, src_opts[0] if other else "manual", "cas_src",
                           format_func=lambda x: T("cas_src_" + x), help=T("h_cas_src")) or src_opts[0]
                inner = None
                if isrc == "loop":
                    names = {i: loops.name(i) for i in other}
                    li = st.selectbox(T("cas_iloop"), other, format_func=names.get, key="cas_iloop",
                                      help=T("h_cas_iloop", o=loops.name(loops.active())))
                    m_i = loops.model_of(li)
                    if m_i is None:
                        st.info(T("cas_loop_nomodel", n=loops.name(li)), icon=":material/info:")
                    else:
                        inner = (m_i[0], list(m_i[1]))
                        st.caption(T("cas_loop_model", n=loops.name(li), m=model_name(inner[0]),
                                     p=", ".join(f"{n} = {v:.4g}" for n, v in zip(MODELS[inner[0]]["params"], inner[1]))))
                elif isrc == "data":
                    i1, i2 = st.columns(2)
                    i3, i4 = st.columns(2)
                    c_ipv = i1.selectbox(T("cas_ipv"), sigs, key=f"cas_ipv|{fname}", help=T("h_cas_ipv"))
                    c_imv = i2.selectbox(T("cas_imv"), sigs, key=f"cas_imv|{fname}", help=T("h_cas_imv"))
                    ipv_raw = ctx.on_grid(c_ipv)
                    ilo = num(T("cas_ilo"), f"cas_ilo|{c_ipv}", float(np.floor(np.nanmin(ipv_raw))), i3, help=T("h_cas_irange"))
                    ihi = num(T("cas_ihi"), f"cas_ihi|{c_ipv}", float(np.ceil(np.nanmax(ipv_raw))), i4, help=T("h_cas_irange"))
                    if st.button(T("cas_fit"), icon=":material/play_arrow:"):
                        ipv = (ipv_raw[sel_mask] - ilo) / max(ihi - ilo, 1e-9) * 100
                        imv = M(ctx.on_grid(c_imv, zoh=True)[sel_mask])
                        best_i, errs_ = acas.fit_inner(ts_id, ipv, imv, Ts, fit_model)
                        for ex in errs_:
                            st.error(T(ex))
                        if best_i:
                            ss.inner_fit = best_i
                    if ss.get("inner_fit"):
                        inner = (ss.inner_fit["code"], ss.inner_fit["p"])
                        st.caption(T("cas_inner_fit", m=model_name(inner[0]), f=f"{ss.inner_fit['fit']:.1f}",
                                     p=", ".join(f"{n} = {v:.4g}" for n, v in zip(MODELS[inner[0]]["params"], inner[1]))))
                else:
                    i1, i2 = st.columns(2)
                    i3, i4 = st.columns(2)
                    k_i = num("K", "cas_k", 1.0, i1, format="%.4g", help=T("h_cas_k"))
                    t1_i = num("T1 [s]", "cas_t1", 5.0, i2, min_value=1e-3, help=T("help_T"))
                    t2_i = num("T2 [s]", "cas_t2", 0.0, i3, min_value=0.0, help=T("help_T"))
                    th_i = num("θ [s]", "cas_th", 1.0, i4, min_value=0.0, help=T("help_theta"))
                    inner = acas.manual_inner(k_i, t1_i, t2_i, th_i)
            if inner is None:
                ws.side.info(T("cas_need_inner"))
            else:
                ci_, p_i = inner
                with section(ws.side, T("cas_inner_tune"), "apc_cas_itune", icon=":material/tune:"):
                    j1 = j2 = j3 = st
                    im = seg(j1, T("method"), ["SIMC", "AMIGO", "OPT"], "SIMC", "cas_im",
                                              format_func=lambda x: T("m_" + x)) or "SIMC"
                    samp_i = num(T("cas_samp"), "cas_samp", samp, j2, min_value=0.001, help=T("sampletime_help"))
                    tci = None
                    if im == "SIMC":
                        tci0 = default_tc(ci_, p_i, samp_i)
                        tci = sld(j3, T("tc"), float(max(0.05 * tci0, 1e-3)), float(10 * tci0), float(tci0), "cas_tci",
                                  help=T("tc_help"))
                    si = acas.tune_loop(ci_, p_i, im, "PI", samp_i, diffgain, tci, cache.opt_migo)
                    st.caption(T("mdesc_" + im) + (f" {T('cdesc_MIGO')}" if im == "OPT" else ""))
                    ictrl = acas.inner_ctrl(si, diffgain, samp_i)
                    # efektivní časová konstanta uzavřené vnitřní smyčky ze simulace skoku SP
                    t63, tci_eff = acas.inner_response(ci_, p_i, ictrl, samp_i, pidconl_sim)
                    k1, k2, k3 = st.columns(3)
                    k1.metric("Gain", f"{si['Kc']:.4g}")
                    k2.metric("TI [s]", f"{si['Ti']:.4g}")
                    k3.metric(T("cas_t63"), f"{t63:.3g} s", help=T("h_cas_t63"))
                with section(ws.side, T("cas_outer_tune"), "apc_cas_otune", icon=":material/tune:"):
                    co_, p_o = acas.outer_model(model, tci_eff, p_i[-1])
                    st.caption(T("cas_outer_model", m=model_name(co_),
                                 p=", ".join(f"{n} = {v:.4g}" for n, v in zip(MODELS[co_]["params"], p_o))))
                    l1 = l2 = l3 = st
                    om = seg(l1, T("method"), ["SIMC", "AMIGO", "OPT"], "SIMC", "cas_om",
                                              format_func=lambda x: T("m_" + x)) or "SIMC"
                    oct_ = seg(l2, T("ctrl_type"), ["PI", "PID"], "PI", "cas_oct") or "PI"
                    tco = None
                    if om == "SIMC":
                        tco0 = default_tc(co_, p_o, samp, "SIMC", oct_, diffgain)
                        tco = sld(l3, T("tc"), float(max(0.05 * tco0, 1e-3)), float(10 * tco0), float(tco0), "cas_tco",
                                  help=T("tc_help"))
                    so = acas.tune_loop(co_, p_o, om, oct_, samp, diffgain, tco, cache.opt_migo)
                    st.caption(T("mdesc_" + om) + (f" {T('cdesc_MIGO')}" if om == "OPT" else ""))
                    octrl = dict(base_ctrl, Gain=so["Kc"], TI=so["Ti"], TD=so["Td"], MV_Lo=0.0, MV_Hi=100.0)
                    o1, o2 = st.columns(2)
                    o3, o4 = st.columns(2)
                    o1.metric("Gain", f"{so['Kc']:.4g}")
                    o2.metric("TI [s]", f"{so['Ti']:.4g}")
                    o3.metric("TD [s]", f"{so['Td']:.4g}")
                    ratio_sep = acas.separation(tco, so, t63)
                    o4.metric(T("cas_sep"), f"{ratio_sep:.1f}×", help=T("h_cas_sep"))
                    if ratio_sep < 4:
                        st.warning(T("cas_sep_warn"), icon=":material/warning:")
                # simulace kaskády
                tcs, oc, ok_ = acas.simulate((ci_, p_i), ictrl, (model[0], model[1]), octrl, samp, samp_i, p_o, co_, tco,
                                             cascade_sim)
                if ok_:
                    fc = mkfig(3, [0.45, 0.3, 0.25])
                    fc.add_trace(tr(tcs, EP(oc[:, 0]), "SP", C_SP, 1.4, "dash", "hv"), 1, 1)
                    fc.add_trace(tr(tcs, EP(oc[:, 1]), T("cas_pv_o"), C_PV, 2.0), 1, 1)
                    fc.add_trace(tr(tcs, oc[:, 2], T("cas_sp_i"), C_SP, 1.4, "dash"), 2, 1)
                    fc.add_trace(tr(tcs, oc[:, 3], T("cas_pv_i"), C_SET2, 2.0), 2, 1)
                    fc.add_trace(tr(tcs, oc[:, 4], T("cas_valve"), C_MV, 1.8), 3, 1)
                    show(style(fc, H + 80, [lab_pv, T("cas_inner_pct"), T("cas_valve_pct")], lab_t, rev="cas"),
                         key="chart_cas", fname="cascade", report=T("tab7"))
                    st.caption(T("cas_sim_help"))
                else:
                    st.error(T("err_sim_unstable", n=T("tab7")))


