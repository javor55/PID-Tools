"""
APC – Smithův prediktor: volba τc, citlivost na chybu modelu, hodnoty pro šablonu SmithPredictorControl.
"""
import numpy as np
import pandas as pd
import streamlit as st

from ....core import (MODELS, iae, pidconl_sim, tune)
from ....core.apc import no_delay, smith_apl
from ....i18n import T
from ...charts import mkfig, show, style, tr
from ...theme import C_SET1, C_SET2, C_SP
from ...widgets import model_name, seg, sld
from . import guide
from .recommend import chk_model_a
from .common import clean, grid, smith_sim_c, tchar, ss


# ---------------------------------------------------------------- Smithův prediktor
def _sm_tc_key(code, p):
    return f"apc_sm_tc|{code}|{p[-1]:.4g}"


def _sm_tc0(p, samp):
    lags = float(sum(p[1:-1]))
    return float(max(p[-1], 2 * samp, 0.05 * lags))   # τc = θ: rychlost jako SIMC, ale bez penalizace za zpoždění


def smith_values(ctx):
    """
    Hodnoty pro bloky šablony SmithPredictorControl: (výsledek smith_apl, regulátor, řádky tabulky).
    Pracovní bod = začátek úseku identifikace (ustálený stav před prvním skokem).
    """
    code, p = ctx.model[0], ctx.model[1]
    n0 = max(3, len(ctx.pv_id) // 20)
    pv_op = float(ctx.EP(np.nanmedian(ctx.pv_id[:n0])))
    mv_op = float(ctx.EM(np.nanmedian(ctx.mv_id[:n0])))
    v = smith_apl(p, ctx.PR, ctx.MR, pv_op, mv_op)
    ct = ss.get("apc_sm_ct") or "PI"
    r = tune(code, no_delay(p), "SIMC", ss.get(_sm_tc_key(code, p)) or _sm_tc0(p, ctx.samp), ct, ctx.samp)
    u_pv, u_mv = ctx.u_pv or "PV", ctx.u_mv or "MV"
    rows = [("SmithModelTimLag (Lag)", "LagTime", v["lag"], "s"),
            ("SmithModelGain (Mul04)", "In2", v["k"], f"{u_pv}/{u_mv}"),
            ("PV0 (Add04)", "In2", v["pv0"], u_pv),
            ("SmithModelDeadti (DeadTime)", "DeadTime", v["theta"], "s"),
            ("PIDConL", "Gain", r["Kc"], "–"),
            ("PIDConL", "TI", r["Ti"], "s")]
    if ct == "PID":
        rows.append(("PIDConL", "TD", r["Td"], "s"))
    return v, r, rows


def smith_table(rows):
    return pd.DataFrame([{T("sm_apl_block"): b, T("sm_apl_input"): i, T("sm_apl_value"): float(f"{x:.4g}"),
                          T("sm_apl_unit"): u} for b, i, x, u in rows])


def smith_render(ctx):
    code, p, _ = ctx.model
    samp = ctx.samp
    lags = tchar((code, p)) - p[-1]
    ratio = p[-1] / max(p[-1] + lags, 1e-9)
    integ = MODELS[code]["integ"]
    tc_key = _sm_tc_key(code, p)
    v, r_, rows = smith_values(ctx)
    checks = [chk_model_a(ctx), (not integ, T("g_chk_sm_integ"), None),
              (True if ratio >= 0.5 else None, T("g_chk_sm_ratio", r=f"{ratio:.2f}"), None),
              (True if v["th_lag"] <= 3 else None, T("g_chk_sm_th3", r=f"{v['th_lag']:.2f}"), None),
              (None, T("g_chk_sm_model"), None)]
    guide.render("smith", checks, T("g_impl_smith", k=f"{v['k']:.4g}", u=f"{ctx.u_pv or 'PV'}/{ctx.u_mv or 'MV'}",
                                    t=f"{v['lag']:.4g}", th=f"{v['theta']:.4g}", pv0=f"{v['pv0']:.4g}",
                                    g=f"{r_['Kc']:.4g}", ti=f"{r_['Ti']:.4g}") +
                 ("\n\n" + T("g_impl_smith_p2d", t1=f"{p[1]:.4g}", t2=f"{p[2]:.4g}") if code == "P2D" else ""))
    if integ:
        st.warning(T("sm_integ"), icon=":material/warning:")
    st.caption(T("sm_ratio", r=f"{ratio:.2f}"))
    c1, c2, c3 = st.columns([1, 1.2, 2], vertical_alignment="bottom")
    ctype = seg(c1, T("ctrl_type"), ["PI", "PID"], "PI", "apc_sm_ct") or "PI"
    tc0 = _sm_tc0(p, samp)
    tc = sld(c3, T("sm_tc"), float(max(0.05 * tc0, 1e-3)), float(10 * tc0), tc0, tc_key,
             help=T("h_sm_tc"))
    st.markdown(f"**{T('sm_err')}**", help=T("h_sm_err"))
    e1, e2, e3 = st.columns(3)
    ek = sld(e1, T("sm_err_k"), -50, 50, 0, "apc_sm_ek", format="%d %%")
    et = sld(e2, T("sm_err_t"), -50, 50, 0, "apc_sm_et", format="%d %%")
    eth = sld(e3, T("sm_err_th"), -50, 50, 0, "apc_sm_eth", format="%d %%")
    plant = list(p)
    plant[0] *= 1 + ek / 100
    for i in range(1, len(plant) - 1):
        plant[i] *= 1 + et / 100
    plant[-1] *= 1 + eth / 100

    r = tune(code, no_delay(p), "SIMC", tc, ctype, samp)
    ctrl_s = dict(clean(ctx.base_ctrl), Gain=r["Kc"], TI=r["Ti"] if r["Ti"] > 0 else np.inf, TD=r["Td"])
    k1, k2, k3 = c2.columns(3)
    k1.metric("Gain", f"{r['Kc']:.4g}")
    k2.metric("TI", f"{r['Ti']:.4g}")
    k3.metric("TD", f"{r['Td']:.3g}")

    t_end = 30 * (p[-1] + lags) + 200 * samp
    h, n, t = grid(t_end, samp)
    sp = np.where(t >= 0.05 * t_end, 55.0, 50.0)
    d = np.where(t >= 0.5 * t_end, 5.0, 0.0)
    tt, o = smith_sim_c(code, plant, list(p), ctrl_s, h, sp, d)
    tb, _, PVb, MVb = pidconl_sim(code, plant, [], h, sp, 50.0, 50.0, clean(ctx.set2_ctrl), [], d)
    E, M = ctx.EP, ctx.EM
    f = mkfig(2, [0.62, 0.38])
    f.add_trace(tr(tt, E(sp), "SP", C_SP, 1.3, "dash", "hv"), 1, 1)
    f.add_trace(tr(tb, E(PVb), T("sm_pid"), C_SET1, 1.6, "dot"), 1, 1)
    f.add_trace(tr(tt, E(o["PV"]), T("sm_smith"), C_SET2, 2.2), 1, 1)
    f.add_trace(tr(tb, M(MVb), T("sm_pid"), C_SET1, 1.4, "dot", show=False), 2, 1)
    f.add_trace(tr(tt, M(o["MV"]), T("sm_smith"), C_SET2, 1.8, show=False), 2, 1)
    show(style(f, ctx.H, [ctx.lab_pv, ctx.lab_mv], ctx.lab_t, rev="apc_sm"), key="chart_apc_sm", fname="smith",
         report=T("apc_smith"))
    half = t < 0.5 * t_end
    PR = ctx.PR / 100
    st.dataframe(pd.DataFrame([
        {T("setting"): T("sm_pid"), T("iae_sp"): round(iae(tb[half], sp[half], PVb[half]) * PR, 4),
         T("iae_load"): round(iae(tb[~half], sp[~half], PVb[~half]) * PR, 4)},
        {T("setting"): T("sm_smith"), T("iae_sp"): round(iae(tt[half], sp[half], o["PV"][half]) * PR, 4),
         T("iae_load"): round(iae(tt[~half], sp[~half], o["PV"][~half]) * PR, 4)}]), hide_index=True)
    st.caption(T("sm_help", m=model_name(code)))

    # ---- hodnoty do šablony SmithPredictorControl (po volbě τc a typu regulátoru výše)
    if integ:
        return
    v, _, rows = smith_values(ctx)
    st.markdown(f"#### {T('sm_apl_title')}", help=T("h_sm_apl"))
    st.dataframe(smith_table(rows), hide_index=True)
    st.caption(T("sm_apl_note"))
    if v["th_lag"] > 3:
        st.warning(T("sm_apl_th3", r=f"{v['th_lag']:.1f}"), icon=":material/warning:")
    if v["k"] < 0:
        st.info(T("sm_apl_neg"), icon=":material/info:")
