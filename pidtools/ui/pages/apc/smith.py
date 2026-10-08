"""
APC – Smithův prediktor: volba τc, citlivost na chybu modelu, hodnoty pro šablonu SmithPredictorControl.
"""
import pandas as pd
import streamlit as st

from ....core import (MODELS, pidconl_sim)
from ....i18n import T
from ...charts import mkfig, show, style, tr
from ...theme import C_SET1, C_SET2, C_SP
from ...widgets import model_name, num, reset_button, seg, sel, sld
from . import guide
from ...layout import section, workspace
from ....app import guides as app_guides
from .recommend import rec_a
from ....app.apc import smith as app_smith
from .common import smith_sim_c, tchar, ss


# ---------------------------------------------------------------- Smithův prediktor
def _sm_tc_key(code, p, method="SIMC"):
    """Klíč τc – u SIMC stejný jako dřív (projekty), u ostatních metod zvlášť (stejně jako v desktopu)."""
    return f"apc_sm_tc|{code}|{p[-1]:.4g}" if method == "SIMC" else f"apc_sm_tc|{method}|{code}|{p[-1]:.4g}"


@st.cache_data(show_spinner=False, max_entries=16)
def _opt_c(code, p, ctype, samp, base_items):
    return app_smith.controller(code, list(p), "OPT", ctype, None, samp, dict(base_items), smith_fn=smith_sim_c)


def smith_ctrl(ctx):
    """Regulátor prediktoru podle zvolené metody (SIMC, Lambda, robustní optimalizace, ruční)."""
    code, p = ctx.model[0], ctx.model[1]
    method = ss.get("apc_sm_method") or app_smith.DEFAULT_METHOD
    ctype = ss.get("apc_sm_ct") or "PI"
    tc = ss.get(_sm_tc_key(code, p, method)) or app_smith.tc_default(p, ctx.samp, method)
    if method == "OPT":
        with st.spinner(T("sm_m_OPT") + " …"):
            r = _opt_c(code, tuple(p), ctype, ctx.samp, tuple(sorted(ctx.base_ctrl.items())))
    else:
        r = app_smith.controller(code, p, method, ctype, tc, ctx.samp, ctx.base_ctrl,
                                 (ss.get("apc_sm_mg", 1.0), ss.get("apc_sm_mti", 100.0), ss.get("apc_sm_mtd", 0.0)))
    return method, ctype, tc, r


def smith_values(ctx):
    """
    Hodnoty pro bloky šablony SmithPredictorControl: (výsledek smith_apl, regulátor, řádky tabulky).
    Pracovní bod = začátek úseku identifikace (ustálený stav před prvním skokem).
    """
    code, p = ctx.model[0], ctx.model[1]
    pv_op, mv_op = app_smith.operating_point(ctx.pv_id, ctx.mv_id)
    _, ctype, tc, r = smith_ctrl(ctx)
    return app_smith.values(code, p, ctx, pv_op, mv_op, ctype, tc, ctx.samp, ctx.u_pv or "PV", ctx.u_mv or "MV", r=r)


def smith_table(rows):
    return pd.DataFrame([{T("sm_apl_block"): b, T("sm_apl_input"): i, T("sm_apl_value"): float(f"{x:.4g}"),
                          T("sm_apl_unit"): u} for b, i, x, u in rows])


def smith_render(ctx):
    code, p, _ = ctx.model
    samp = ctx.samp
    lags = tchar((code, p)) - p[-1]
    ratio = p[-1] / max(p[-1] + lags, 1e-9)
    integ = MODELS[code]["integ"]
    v, r_, rows = smith_values(ctx)
    ws = workspace()
    checks = app_guides.apc_smith(rec_a(ctx), integ, ratio, v["th_lag"])
    with ws.main:
        guide.render("smith", checks, T("g_impl_smith", k=f"{v['k']:.4g}", u=f"{ctx.u_pv or 'PV'}/{ctx.u_mv or 'MV'}",
                                        t=f"{v['lag']:.4g}", th=f"{v['theta']:.4g}", pv0=f"{v['pv0']:.4g}",
                                        g=f"{r_['Kc']:.4g}", ti=f"{r_['Ti']:.4g}") +
                     ("\n\n" + T("g_impl_smith_p2d", t1=f"{p[1]:.4g}", t2=f"{p[2]:.4g}") if code == "P2D" else ""))
    with section(ws.side, T("apc_smith"), "apc_sm_set", icon=":material/tune:"):
        if integ:
            st.warning(T("sm_integ"), icon=":material/warning:")
        st.caption(T("sm_ratio", r=f"{ratio:.2f}"))
        method = sel(st, T("sm_method"), list(app_smith.METHODS), 0, "apc_sm_method",
                     format_func=lambda m: T("sm_m_" + m), help=T("h_sm_method"))
        ctype = seg(st, T("ctrl_type"), ["PI", "PID"], "PI", "apc_sm_ct") or "PI"
        if method in ("SIMC", "Lambda"):
            tc0 = app_smith.tc_default(p, samp, method)
            sld(st, T("sm_tc"), float(max(0.05 * tc0, 1e-3)), float(10 * tc0), tc0, _sm_tc_key(code, p, method),
                help=T("h_sm_tc"))
            reset_button(st, "apc_sm_tc", [(_sm_tc_key(code, p, method), tc0)])
        elif method == "manual":
            if "apc_sm_mg" not in ss:          # výchozí ruční hodnoty = sada 2
                ss["apc_sm_mg"], ss["apc_sm_mti"], ss["apc_sm_mtd"] = (float(ss.get(f"set2_{k}", d))
                                                                       for k, d in (("gain", 1.0), ("ti", 100.0),
                                                                                    ("td", 0.0)))
            m1, m2, m3 = st.columns(3)
            num("Gain", "apc_sm_mg", 1.0, m1, format="%.4g")
            num("TI [s]", "apc_sm_mti", 100.0, m2, min_value=0.0, format="%.4g")
            if ctype == "PID":
                num("TD [s]", "apc_sm_mtd", 0.0, m3, min_value=0.0, format="%.4g")
            reset_button(st, "apc_sm_man", [(f"apc_sm_m{k}", float(ss.get(f"set2_{n}", d)))
                                             for k, n, d in (("g", "gain", 1.0), ("ti", "ti", 100.0), ("td", "td", 0.0))])
        method, ctype, tc, r = smith_ctrl(ctx)
        mbox = st.container()
    with section(ws.side, T("sm_err"), "apc_sm_err", icon=":material/difference:"):
        st.caption(T("h_sm_err"))
        ek = sld(st, T("sm_err_k"), -50, 50, 0, "apc_sm_ek", format="%d %%")
        et = sld(st, T("sm_err_t"), -50, 50, 0, "apc_sm_et", format="%d %%")
        eth = sld(st, T("sm_err_th"), -50, 50, 0, "apc_sm_eth", format="%d %%")
        reset_button(st, "apc_sm_err", [("apc_sm_ek", 0), ("apc_sm_et", 0), ("apc_sm_eth", 0)])
    plant = app_smith.plant_error(p, ek, et, eth)
    sm = app_smith.simulate(code, p, plant, ctx.base_ctrl, ctx.set2_ctrl, ctype, tc, samp, smith_sim_c, pidconl_sim,
                            r=r)
    k1, k2, k3 = mbox.columns(3)
    k1.metric("Gain", f"{r['Kc']:.4g}")
    k2.metric("TI", f"{r['Ti']:.4g}")
    k3.metric("TD", f"{r['Td']:.3g}")
    sp = sm["sp"]
    tt, o = sm["smith"]
    tb, PVb, MVb = sm["pid"]
    E, M = ctx.EP, ctx.EM
    f = mkfig(2, [0.62, 0.38])
    f.add_trace(tr(tt, E(sp), "SP", C_SP, 1.3, "dash", "hv"), 1, 1)
    f.add_trace(tr(tb, E(PVb), T("sm_pid"), C_SET1, 1.6, "dot"), 1, 1)
    f.add_trace(tr(tt, E(o["PV"]), T("sm_smith"), C_SET2, 2.2), 1, 1)
    f.add_trace(tr(tb, M(MVb), T("sm_pid"), C_SET1, 1.4, "dot", show=False), 2, 1)
    f.add_trace(tr(tt, M(o["MV"]), T("sm_smith"), C_SET2, 1.8, show=False), 2, 1)
    with ws.main:
        show(style(f, ctx.H, [ctx.lab_pv, ctx.lab_mv], ctx.lab_t, rev="apc_sm"), key="chart_apc_sm", fname="smith",
             report=T("apc_smith"))
        PR = ctx.PR / 100
        st.dataframe(pd.DataFrame([
            {T("setting"): T("sm_" + k), T("iae_sp"): round(sm["iae"][k][0] * PR, 4),
             T("iae_load"): round(sm["iae"][k][1] * PR, 4)} for k in ("pid", "smith")]), hide_index=True)
        st.caption(T("sm_help", m=model_name(code)))
    # ---- hodnoty do šablony SmithPredictorControl (po volbě τc a typu regulátoru výše)
    if integ:
        return
    v, _, rows = smith_values(ctx)
    pv_op, mv_op = app_smith.operating_point(ctx.pv_id, ctx.mv_id)
    u_pv, u_mv = ctx.u_pv or "PV", ctx.u_mv or "MV"
    with mbox:
        st.caption(app_smith.basis_text(code, p, ctx, pv_op, mv_op, samp, u_pv, u_mv))
    with section(ws.side, T("sm_gen_title"), "apc_sm_gen", icon=":material/function:"):
        st.dataframe(pd.DataFrame([{T("sm_gen_par"): T(k), T("sm_apl_value"): float(f"{x:.4g}"), T("sm_apl_unit"): u}
                                   for k, x, u in app_smith.general_rows(code, p, ctx, pv_op, mv_op, r, tc, method,
                                                                         ctype, u_pv, u_mv)]), hide_index=True)
        st.caption(T("sm_gen_help"))
    with section(ws.side, T("sm_apl_title"), "apc_sm_apl", icon=":material/table:"):
        st.dataframe(smith_table(rows), hide_index=True)
        st.caption(T("sm_apl_note"))
        if v["th_lag"] > 3:
            st.warning(T("sm_apl_th3", r=f"{v['th_lag']:.1f}"), icon=":material/warning:")
        if v["k"] < 0:
            st.info(T("sm_apl_neg"), icon=":material/info:")
