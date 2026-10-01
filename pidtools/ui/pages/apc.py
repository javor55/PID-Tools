"""
Záložka APC: výběr regulační struktury – kaskáda, rozvazbení 2×2 (RGA, decouplery), override (výběr MIN/MAX)
a Smithův prediktor. Hlavní (vnější) smyčka je vždy aktivní smyčka projektu; druhá smyčka se vybírá z ostatních.
"""
import numpy as np
import pandas as pd
import streamlit as st

from ...core import MODELS, iae, pidconl_sim, tune
from ...core.apc import ff_design, mimo2_sim, no_delay, override_sim, rga2, rga_advice, smith_sim
from ...i18n import T
from .. import loops
from ..charts import mkfig, show, style, tr
from ..theme import C_MV, C_PV, C_SET1, C_SET2, C_SP
from ..widgets import model_name, num, seg, sld
from . import cascade

ss = st.session_state
KINDS = ["cascade", "decouple", "override", "smith"]
C_B = "#7c3aed"          # druhá smyčka
C_REF = "#9aa5b1"        # srovnání (bez struktury)

_mimo = st.cache_data(show_spinner=False, max_entries=32)(mimo2_sim)
_override = st.cache_data(show_spinner=False, max_entries=32)(override_sim)
_smith = st.cache_data(show_spinner=False, max_entries=32)(smith_sim)


def render(ctx):
    with ctx.tabs["cascade"]:
        st.caption(ctx.block_summary)
        kind = seg(st, T("apc_kind"), KINDS, "cascade", "apc_kind", format_func=lambda x: T("apc_" + x),
                   help=T("h_apc_kind")) or "cascade"
        if kind == "cascade":
            cascade.render_body(ctx)
            return
        st.markdown(T("apc_intro_" + kind))
        if ctx.model is None or ctx.set2_ctrl is None:
            st.info(T("need_model"), icon=":material/arrow_back:")
            return
        if kind == "smith":
            _smith_page(ctx)
            return
        b = _pick_other(ctx, kind)
        if b is None:
            return
        (_decouple_page if kind == "decouple" else _override_page)(ctx, b)


# ---------------------------------------------------------------- společné
def _active(ctx):
    """Aktivní smyčka ve stejném tvaru jako loops.loop_data."""
    return dict(name=loops.name(loops.active()), model=ctx.model, ctrl=ctx.set2_ctrl, c_mv=ctx.c_mv, c_pv=ctx.c_pv,
                c_d=list(ctx.c_d), pv_rng=(ctx.pv_lo, ctx.pv_hi), mv_rng=(ctx.mv_lo, ctx.mv_hi), u_pv=ctx.u_pv,
                u_mv=ctx.u_mv)


def _pick_other(ctx, kind):
    """Výběr druhé smyčky projektu (s modelem); bez ní návod, jak ji přidat."""
    other = [i for i in loops.ids() if i != loops.active()]
    if not other:
        st.info(T("apc_need_loop"), icon=":material/add:")
        return None
    names = {i: loops.name(i) for i in other}
    i = st.selectbox(T(f"apc_{kind}_b"), other, format_func=names.get, key=f"apc_{kind}_b",
                     help=T(f"h_apc_{kind}_b", a=loops.name(loops.active())))
    b = loops.loop_data(i, ctx.fname)
    if b["model"] is None:
        st.info(T("cas_loop_nomodel", n=b["name"]), icon=":material/info:")
        return None
    return b


def _eng(rng):
    lo, hi = rng
    return lambda x: lo + np.asarray(x, float) * (hi - lo) / 100


def _tchar(model):
    code, p = model[0], model[1]
    return p[-1] + (p[1] if code in ("P1D", "P2D", "I1D") else 0.0) + (p[2] if code == "P2D" else 0.0)


def _grid(t_end, samp):
    h = float(min(samp, max(t_end / 6000, samp / 10)))
    n = int(t_end / h) + 1
    return h, n, np.arange(n) * h


def _lab(name, rng_u):
    return f"{name} [{rng_u}]" if rng_u else name


def _clean(ctrl):
    return {k: v for k, v in ctrl.items() if k not in ("FF", "FF_LL")}


# ---------------------------------------------------------------- rozvazbení 2×2
def _cross_model(x, y):
    """Model vlivu MV smyčky y na PV smyčky x [%PV_x / %MV_y] – z modelu měřené poruchy (sloupec MV_y)."""
    if y["c_mv"] in x["c_d"]:
        j = x["c_d"].index(y["c_mv"])
        if j < len(x["model"][2]):
            pd_ = list(x["model"][2][j])
            pd_[0] *= (y["mv_rng"][1] - y["mv_rng"][0]) / 100   # Kd je v %PV na jednotku MV_y
            return pd_
    return None


def _decouple_page(ctx, b):
    a = _active(ctx)
    xab, xba = _cross_model(a, b), _cross_model(b, a)
    if xab is None and xba is None:
        st.warning(T("dec_need_cross", a=a["name"], b=b["name"], mva=a["c_mv"], mvb=b["c_mv"]),
                   icon=":material/link_off:")
        return
    if xab is None or xba is None:
        st.caption(T("dec_one_way", x=a["name"] if xab is None else b["name"],
                     mv=b["c_mv"] if xab is None else a["c_mv"]))
    ga, gb = (a["model"][0], list(a["model"][1])), (b["model"][0], list(b["model"][1]))

    # ---- RGA
    lam = rga2(ga[1][0], xab[0] if xab else 0.0, xba[0] if xba else 0.0, gb[1][0])
    with st.container(border=True):
        r1, r2 = st.columns([1, 3], vertical_alignment="center")
        r1.metric("RGA λ₁₁", "∞" if not np.isfinite(lam) else f"{lam:.2f}", help=T("h_rga"))
        r2.markdown(T(rga_advice(lam), a=a["name"], b=b["name"], mva=a["c_mv"], mvb=b["c_mv"]))

    # ---- decouplery a scénář
    dab = ff_design(*ga, xab) if xab else None
    dba = ff_design(*gb, xba) if xba else None
    c1, c2, c3 = st.columns([1.4, 1, 1], vertical_alignment="bottom")
    dtype = seg(c1, T("dec_type"), ["static", "dyn"], "dyn", "apc_dec_type", format_func=lambda x: T("dec_" + x),
                help=T("h_dec_type")) or "dyn"
    amp_a = num(T("dec_step", n=a["name"]), "apc_dec_spa", 5.0, c2, format="%.4g", help=T("h_dec_step"))
    amp_b = num(T("dec_step", n=b["name"]), "apc_dec_spb", 5.0, c3, format="%.4g", help=T("h_dec_step"))
    ctrl_a, ctrl_b = _clean(a["ctrl"]), _clean(b["ctrl"])
    t_end = 14 * max(_tchar(ga), _tchar(gb)) + 200 * max(ctrl_a["SampleTime"], ctrl_b["SampleTime"])
    h, n, t = _grid(t_end, min(ctrl_a["SampleTime"], ctrl_b["SampleTime"]))
    sp_a = np.where(t >= 0.05 * t_end, 50.0 + amp_a, 50.0)
    sp_b = np.where(t >= 0.5 * t_end, 50.0 + amp_b, 50.0)
    runs = {}
    for v_ in ("none", "static", "dyn"):
        on = v_ != "none"
        runs[v_] = _mimo(ga, gb, xab, xba, ctrl_a, ctrl_b, h, sp_a, sp_b, dab if on else None, dba if on else None,
                         v_ == "dyn")
    EA, EB = _eng(a["pv_rng"]), _eng(b["pv_rng"])
    MA, MB = _eng(a["mv_rng"]), _eng(b["mv_rng"])
    tt, o_ref = runs["none"]
    _, o = runs[dtype]
    f = mkfig(3, [0.36, 0.36, 0.28])
    f.add_trace(tr(tt, EA(o["SP_A"]), f"SP {a['name']}", C_SP, 1.3, "dash", "hv"), 1, 1)
    f.add_trace(tr(tt, EA(o_ref["PV_A"]), T("dec_without"), C_REF, 1.3, "dot", group="ref"), 1, 1)
    f.add_trace(tr(tt, EA(o["PV_A"]), f"PV {a['name']}", C_PV, 2.0), 1, 1)
    f.add_trace(tr(tt, EB(o["SP_B"]), f"SP {b['name']}", C_SP, 1.3, "dash", "hv", show=False), 2, 1)
    f.add_trace(tr(tt, EB(o_ref["PV_B"]), T("dec_without"), C_REF, 1.3, "dot", show=False, group="ref"), 2, 1)
    f.add_trace(tr(tt, EB(o["PV_B"]), f"PV {b['name']}", C_B, 2.0), 2, 1)
    f.add_trace(tr(tt, MA(o["MV_A"]), f"MV {a['name']}", C_MV, 1.6), 3, 1)
    f.add_trace(tr(tt, MB(o["MV_B"]), f"MV {b['name']}", C_SET2, 1.6), 3, 1)
    show(style(f, ctx.H + 120, [_lab(a["name"], a["u_pv"]), _lab(b["name"], b["u_pv"]), "MV"], ctx.lab_t,
               rev="apc_dec"), key="chart_apc_dec", fname="decoupling", report=T("apc_decouple"))
    st.caption(T("dec_sim_help"))

    rows = []
    for v_ in ("none", "static", "dyn"):
        tt_, oo = runs[v_]
        rows.append({T("dec_variant"): T("dec_" + v_),
                     f"IAE {a['name']}": round(iae(tt_, oo["SP_A"], oo["PV_A"]) * (a["pv_rng"][1] - a["pv_rng"][0]) / 100, 4),
                     f"IAE {b['name']}": round(iae(tt_, oo["SP_B"], oo["PV_B"]) * (b["pv_rng"][1] - b["pv_rng"][0]) / 100, 4)})
    st.dataframe(pd.DataFrame(rows), hide_index=True)

    # ---- parametry pro implementaci (dopředná vazba z MV druhé smyčky)
    prm = []
    for d_, src, dst in ((dab, b, a), (dba, a, b)):
        if d_ is None:
            continue
        g_eng = d_["gain"] * (dst["mv_rng"][1] - dst["mv_rng"][0]) / (src["mv_rng"][1] - src["mv_rng"][0])
        prm.append({T("dec_path"): f"{src['c_mv']} → MV {dst['name']}", T("dec_gain_pct"): round(d_["gain"], 4),
                    T("dec_gain_eng"): round(g_eng, 4), "Lead [s]": round(d_["lead"], 3), "Lag [s]": round(d_["lag"], 3),
                    T("ff_delay"): round(d_["delay"], 3)})
    st.markdown(f"**{T('dec_params')}**")
    st.dataframe(pd.DataFrame(prm), hide_index=True)
    st.caption(T("dec_params_help"))


# ---------------------------------------------------------------- override
def _override_page(ctx, b):
    a = _active(ctx)
    if b["c_mv"] != a["c_mv"]:
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
    ctrl_a, ctrl_b = _clean(a["ctrl"]), _clean(b["ctrl"])
    t_end = 14 * max(_tchar(ga), _tchar(gb)) + 200 * max(ctrl_a["SampleTime"], ctrl_b["SampleTime"])
    h, n, t = _grid(t_end, min(ctrl_a["SampleTime"], ctrl_b["SampleTime"]))
    sp_a = np.where(t >= 0.05 * t_end, 50.0 + step_a / PRa * 100, 50.0)
    sp_a[t >= 0.6 * t_end] = 50.0
    sp_b = np.full(n, (lim - b["pv_rng"][0]) / PRb * 100)
    tt, o = _override(ga, gb, ctrl_a, ctrl_b, h, sp_a, sp_b, sel, True)
    _, o0 = _override(ga, gb, ctrl_a, ctrl_b, h, sp_a, sp_b, sel, False)
    EA, EB, M = _eng(a["pv_rng"]), _eng(b["pv_rng"]), _eng(a["mv_rng"])

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
    show(style(f, ctx.H + 120, [_lab(a["name"], a["u_pv"]), _lab(b["name"], b["u_pv"]), _lab("MV", a["u_mv"])],
               ctx.lab_t, rev="apc_ov"), key="chart_apc_ov", fname="override", report=T("apc_override"))
    st.caption(T("ov_sim_help", b=b["name"]))


# ---------------------------------------------------------------- Smithův prediktor
def _smith_page(ctx):
    code, p, _ = ctx.model
    samp = ctx.samp
    if MODELS[code]["integ"]:
        st.warning(T("sm_integ"), icon=":material/warning:")
    lags = _tchar((code, p)) - p[-1]
    st.caption(T("sm_ratio", r=f"{p[-1] / max(p[-1] + lags, 1e-9):.2f}"))
    c1, c2, c3 = st.columns([1, 1.2, 2], vertical_alignment="bottom")
    ctype = seg(c1, T("ctrl_type"), ["PI", "PID"], "PI", "apc_sm_ct") or "PI"
    tc0 = float(max(p[-1], 2 * samp, 0.05 * lags))   # τc = θ: rychlost jako SIMC, ale bez penalizace za zpoždění
    tc = sld(c3, T("sm_tc"), float(max(0.05 * tc0, 1e-3)), float(10 * tc0), tc0, f"apc_sm_tc|{code}|{p[-1]:.4g}",
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
    ctrl_s = dict(_clean(ctx.base_ctrl), Gain=r["Kc"], TI=r["Ti"] if r["Ti"] > 0 else np.inf, TD=r["Td"])
    k1, k2, k3 = c2.columns(3)
    k1.metric("Gain", f"{r['Kc']:.4g}")
    k2.metric("TI", f"{r['Ti']:.4g}")
    k3.metric("TD", f"{r['Td']:.3g}")

    t_end = 30 * (p[-1] + lags) + 200 * samp
    h, n, t = _grid(t_end, samp)
    sp = np.where(t >= 0.05 * t_end, 55.0, 50.0)
    d = np.where(t >= 0.5 * t_end, 5.0, 0.0)
    tt, o = _smith(code, plant, list(p), ctrl_s, h, sp, d)
    tb, _, PVb, MVb = pidconl_sim(code, plant, [], h, sp, 50.0, 50.0, _clean(ctx.set2_ctrl), [], d)
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
