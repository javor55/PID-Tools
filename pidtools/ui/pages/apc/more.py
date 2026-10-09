"""
APC › další struktury (web, stejně jako desktop): split range, regulace polohy ventilu (VPC), poměrová regulace
s křížovým omezením a interakce N×N (RGA). Rozložení: vlevo graf a ukazatele, vpravo nastavení.
Výpočty v pidtools.app.apc (splitrange, vpc, ratio, rgan).
"""
import numpy as np
import pandas as pd
import streamlit as st

from ....app import guides as app_guides
from ....app.apc import ratio as aratio
from ....app.apc import rgan
from ....app.apc import splitrange as asr
from ....app.apc import vpc as avpc
from ....core import MODELS
from ....i18n import T
from ... import loops
from ...charts import mkfig, show, style, tr
from ...layout import section, workspace
from ...theme import C_MV, C_SET1, C_SET2, C_SP
from ...widgets import num, reset_button, seg
from . import guide
from .common import active_model
from .recommend import rec_a
from ...table import table

ss = st.session_state


def _model_inputs(key, code, p0):
    """Parametry modelu druhého akčního členu (klíče podle modelu smyčky – změna modelu = nové výchozí hodnoty)."""
    names = MODELS[code]["params"]
    cc = st.columns(len(names))
    out, items = [], []
    for i, (n, v) in enumerate(zip(names, p0)):
        k = f"{key}|{code}|{p0[0]:.4g}|{i}"
        out.append(num(n, k, float(v), cc[i], min_value=None if i == 0 else 0.0, format="%.4g"))
        items.append((k, float(v)))
    reset_button(st, key, items)
    return code, out


def _pv(ctx, x):
    return ctx.EP(np.asarray(x, float))


def split_render(ctx):
    a = active_model(ctx)
    ws = workspace()
    with section(ws.side, T("sr_setup"), "apc_sr_setup"):
        mode = seg(st, T("sr_mode"), ["opposite", "sequence"], "opposite", "apc_sr_mode",
                   format_func=lambda x: T("sr_" + x)) or "opposite"
        b0 = num(T("sr_b0"), "apc_sr_b0", 50.0, min_value=1.0, max_value=99.0, help=T("h_sr_b0"))
        gap = num(T("sr_gap"), "apc_sr_gap", 0.0, min_value=-20.0, max_value=20.0, help=T("h_sr_gap"))
        reset_button(st, "apc_sr", [("apc_sr_b0", 50.0), ("apc_sr_gap", 0.0)])
    gb = asr.valve_b(ctx.model, b0)
    with section(ws.side, T("sr_valve_a"), "apc_sr_a"):
        ga = _model_inputs(f"apc_sr_a|{mode}", *asr.default_a(gb, mode))
    bstar = asr.balanced(ga[1][0], gb[1][0])
    ctrl = ctx.set2_ctrl
    lo0, up0 = asr.eff_gains(ga[1][0], gb[1][0], b0, mode)
    _, up1 = asr.eff_gains(ga[1][0], gb[1][0], bstar, mode)
    with section(ws.side, T("dk_sec_about"), "apc_sr_about", expanded=False):
        st.markdown(T("apc_intro_split"))
    h0, h1 = asr.halves(ga, gb, ctrl, b0, mode), asr.halves(ga, gb, ctrl, bstar, mode)
    runs, _ = asr.simulate(ga, gb, ctrl, b0, bstar, mode, gap, ctx.samp)
    with ws.main:
        guide.render("split", app_guides.apc_actuators(rec_a(ctx), "split"), T("g_impl_split", b=f"{bstar:.1f}",
                                                                                g=f"{gap:.3g}"))
        st.markdown(T("sr_result", b=f"{bstar:.1f}", lo=f"{lo0:.3g}", up=f"{up0:.3g}", k=f"{up1:.3g}",
                      f=f"{ctx.model[1][0] / up1 if up1 else 1.0:.3g}"))
        table(pd.DataFrame({T("sr_lower"): [f"K {k:.3g} · Ms {m:.2f}" + ("" if s_ else " ⚠") for k, m, s_ in (h0[0], h1[0])],
                                   T("sr_upper"): [f"K {k:.3g} · Ms {m:.2f}" + ("" if s_ else " ⚠") for k, m, s_ in (h0[1], h1[1])]},
                                  index=[f"{T('sr_now')} (b = {b0:.0f} %)", f"{T('sr_new')} (b = {bstar:.0f} %)"]),
                     width="stretch")
        fig = mkfig(3, [0.45, 0.27, 0.28])
        (t0, o0), (t1, o1) = runs["now"], runs["new"]
        fig.add_trace(tr(t1, _pv(ctx, o1["SP"]), "SP", C_SP, 1.3, "dash", "hv"), 1, 1)
        fig.add_trace(tr(t0, _pv(ctx, o0["PV"]), T("sr_now"), C_SET1, 1.6, "dot"), 1, 1)
        fig.add_trace(tr(t1, _pv(ctx, o1["PV"]), T("sr_new"), C_SET2, 2.0), 1, 1)
        fig.add_trace(tr(t0, o0["U"], T("sr_now"), C_SET1, 1.3, "dot", show=False), 2, 1)
        fig.add_trace(tr(t1, o1["U"], T("sr_new"), C_SET2, 1.6, show=False), 2, 1)
        fig.add_trace(tr(t1, o1["VA"], T("sr_va"), "#0891b2", 1.6), 3, 1)
        fig.add_trace(tr(t1, o1["VB"], T("sr_vb"), C_MV, 1.6), 3, 1)
        show(style(fig, ctx.H, [ctx.lab_pv, T("sr_u"), T("sr_valves")], ctx.lab_t, rev="split"), key="chart_split",
             fname="split_range")
        kp = {nm: asr.kpis(runs[k], ctx.PR) for k, nm in (("now", T("sr_now")), ("new", T("sr_new")))}
        table(pd.DataFrame({f"IAE [{a['u_pv'] or 'PV'}·s]": {n: f"{k['iae']:.4g}" for n, k in kp.items()},
                                   T("kpi_maxdev", u=a["u_pv"] or "PV"): {n: f"{k['maxdev']:.4g}" for n, k in kp.items()},
                                   T("kpi_rev"): {n: k["rev"] for n, k in kp.items()}}), width="stretch")


def vpc_render(ctx):
    ws = workspace()
    g1 = (ctx.model[0], list(ctx.model[1]))
    with section(ws.side, T("vpc_mv2"), "apc_vpc_mv2"):
        g2 = _model_inputs("apc_vpc_mv2", *avpc.default_mv2(g1))
    with section(ws.side, T("vpc_setup"), "apc_vpc_setup"):
        sp_vpc = num(T("vpc_sp"), "apc_vpc_sp", 50.0, min_value=5.0, max_value=95.0, help=T("h_vpc_sp"))
        factor = num(T("vpc_factor"), "apc_vpc_f", 5.0, min_value=1.0, max_value=30.0, help=T("h_vpc_factor"))
        d = num(T("vpc_d"), "apc_vpc_d", 35.0, min_value=-100.0, max_value=100.0, help=T("h_vpc_d"))
        reset_button(st, "apc_vpc", [("apc_vpc_sp", 50.0), ("apc_vpc_f", 5.0), ("apc_vpc_d", 35.0)])
    with section(ws.side, T("dk_sec_about"), "apc_vpc_about", expanded=False):
        st.markdown(T("apc_intro_vpc"))
    ctrl1 = ctx.set2_ctrl
    cv, p, tc = avpc.tune_vpc(g1, g2, ctrl1, ctx.base_ctrl, factor)
    runs = avpc.simulate(g1, g2, ctrl1, cv, d, sp_vpc, ctx.samp)
    with ws.main:
        guide.render("vpc", app_guides.apc_actuators(rec_a(ctx), "vpc"),
                     T("g_impl_vpc", sp=f"{sp_vpc:.3g}", g=f"{cv['Gain']:.4g}", ti=f"{cv['TI']:.4g}"))
        st.markdown(T("vpc_result", g=f"{cv['Gain']:.4g}", ti=f"{cv['TI']:.4g}", k=f"{p[0]:.3g}", t=f"{p[1]:.4g}",
                      th=f"{p[2]:.4g}", tc=f"{tc:.4g}"))
        fig = mkfig(3, [0.4, 0.3, 0.3])
        (t0, o0), (t1, o1) = runs["off"], runs["on"]
        fig.add_trace(tr(t1, _pv(ctx, o1["SP"]), "SP", C_SP, 1.3, "dash", "hv"), 1, 1)
        fig.add_trace(tr(t0, _pv(ctx, o0["PV"]), T("vpc_off"), C_SET1, 1.6, "dot"), 1, 1)
        fig.add_trace(tr(t1, _pv(ctx, o1["PV"]), T("vpc_on"), C_SET2, 2.0), 1, 1)
        fig.add_trace(tr(t0, o0["MV1"], T("vpc_off"), C_SET1, 1.3, "dot", show=False), 2, 1)
        fig.add_trace(tr(t1, o1["MV1"], "MV1", C_MV, 1.8), 2, 1)
        fig.add_hline(y=sp_vpc, line=dict(color="#9aa5b1", dash="dash", width=1), row=2, col=1)
        fig.add_trace(tr(t1, o1["MV2"], "MV2", "#7c3aed", 1.8), 3, 1)
        show(style(fig, ctx.H, [ctx.lab_pv, "MV1 [%]", "MV2 [%]"], ctx.lab_t, rev="vpc"), key="chart_vpc", fname="vpc")
        kp = {nm: avpc.kpis(runs[k], ctx.PR) for k, nm in (("off", T("vpc_off")), ("on", T("vpc_on")))}
        table(pd.DataFrame({f"IAE [{ctx.u_pv or 'PV'}·s]": {n: f"{k['iae']:.4g}" for n, k in kp.items()},
                                   T("vpc_at_lim"): {n: f"{k['at_lim']:.1f}" for n, k in kp.items()},
                                   T("vpc_reserve"): {n: f"{k['reserve']:.1f}" for n, k in kp.items()}}), width="stretch")


def ratio_render(ctx):
    ws = workspace()
    gf = (ctx.model[0], list(ctx.model[1]))
    others = [i for i in loops.ids() if i != loops.active() and loops.model_of(i) is not None]
    with section(ws.side, T("ra_air"), "apc_ra_air"):
        opts = [None] + others
        src = st.selectbox(T("ra_src"), opts, format_func=lambda i: T("ra_manual") if i is None else loops.name(i),
                           key="apc_ra_src")
        if src is None:
            ga = _model_inputs("apc_ra_air", *aratio.default_air(gf))
            ctrl_a = ctx.set2_ctrl
        else:
            b = loops.loop_data(src, ctx.fname)
            ga = (b["model"][0], list(b["model"][1]))
            ctrl_a = b["ctrl"]
            st.caption(", ".join(f"{n} = {v:.4g}" for n, v in zip(MODELS[ga[0]]["params"], ga[1])))
    with section(ws.side, T("ra_setup"), "apc_ra_setup"):
        R = num(T("ra_R"), "apc_ra_R", 1.2, min_value=0.01, max_value=100.0, format="%.4g", help=T("h_ra_R"))
        step = num(T("ra_step"), "apc_ra_step", 15.0, min_value=-50.0, max_value=50.0, help=T("h_ra_step"))
        reset_button(st, "apc_ra", [("apc_ra_R", 1.2), ("apc_ra_step", 15.0)])
    with section(ws.side, T("dk_sec_about"), "apc_ra_about", expanded=False):
        st.markdown(T("apc_intro_ratio"))
    runs = aratio.simulate(gf, ga, ctx.set2_ctrl, ctrl_a, R, step, ctx.samp)
    with ws.main:
        guide.render("ratio", app_guides.apc_ratio(rec_a(ctx), len(others)), T("g_impl_ratio", r=f"{R:.4g}"))
        kc, kp = aratio.kpis(runs["cross"], ctx.PR), aratio.kpis(runs["plain"], ctx.PR)
        st.markdown(T("ra_result", a=f"{kp['lam_min']:.3f}", b=f"{kc['lam_min']:.3f}"))
        fig = mkfig(2, [0.62, 0.38])
        (tc, oc), (tp, op) = runs["cross"], runs["plain"]
        fig.add_trace(tr(tc, oc["D"], T("ra_demand"), C_SP, 1.3, "dash", "hv"), 1, 1)
        fig.add_trace(tr(tc, oc["PVF"], T("ra_fuel"), C_MV, 2.0), 1, 1)
        fig.add_trace(tr(tc, oc["PVA"] / R, T("ra_air_r"), "#0891b2", 2.0), 1, 1)
        fig.add_trace(tr(tp, op["PVA"] / R, f"{T('ra_air_r')} – {T('ra_plain')}", "#9aa5b1", 1.3, "dot"), 1, 1)
        fig.add_trace(tr(tc, oc["LAM"], T("ra_cross"), C_SET2, 2.0), 2, 1)
        fig.add_trace(tr(tp, op["LAM"], T("ra_plain"), C_SET1, 1.4, "dot"), 2, 1)
        fig.add_hline(y=1.0, line=dict(color="#dc2626", dash="dash", width=1), row=2, col=1)
        show(style(fig, ctx.H, [T("ra_flows"), "λ"], ctx.lab_t, rev="ratio"), key="chart_ratio", fname="ratio")
        table(pd.DataFrame({T("ra_lam_min"): [f"{kp['lam_min']:.3f}", f"{kc['lam_min']:.3f}"],
                                   T("ra_t_rich"): [f"{kp['t_rich']:.0f}", f"{kc['t_rich']:.0f}"],
                                   T("ra_iae"): [f"{kp['iae']:.4g}", f"{kc['iae']:.4g}"]},
                                  index=[T("ra_plain"), T("ra_cross")]), width="stretch")


def rga_render(ctx):
    a = active_model(ctx)
    recs = [a] + [loops.loop_data(i, ctx.fname) for i in loops.ids() if i != loops.active()
                  and loops.model_of(i) is not None]
    n_cross = int(rgan.matrix(recs)[1].sum() - len(recs)) if len(recs) > 1 else 0
    guide.render("rga", app_guides.apc_rga(rec_a(ctx), len(recs), n_cross), T("g_impl_rga"))
    st.markdown(T("apc_intro_rga"))
    if len(recs) < 2:
        st.info(T("apc_need_loop"), icon=":material/add:")
        return
    r = rgan.analyse(recs)
    cols = [f"{T('rga_mv')} {mv}" for mv in r["mvs"]]
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"**{T('rga_k')}**")
        table(pd.DataFrame([[("" if r["known"][i, j] else "? ") + f"{r['K'][i, j]:.3g}" for j in range(len(recs))]
                                   for i in range(len(recs))], index=r["names"], columns=cols), width="stretch")
    with c2:
        st.markdown(f"**{T('rga_l')}**")
        table(pd.DataFrame(np.round(r["L"], 3), index=r["names"], columns=cols), width="stretch")
    lines = [f"**NI = {r['NI']:.3g}**"] if np.isfinite(r["NI"]) else []
    if r["pairing"] is not None:
        lines.append(T("rga_pairing") + ": " + ", ".join(f"{n} ← {r['mvs'][j]}" for n, j in zip(r["names"], r["pairing"])))
    lines += [T(k) for k in r["advice"]]
    st.markdown("  \n".join(lines))
