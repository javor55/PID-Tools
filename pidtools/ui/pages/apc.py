"""
Záložka APC: výběr regulační struktury – kaskáda, rozvazbení 2×2 (RGA, decouplery), override (výběr MIN/MAX),
Smithův prediktor a gain scheduling (parametry PID podle pracovního bodu). Hlavní (vnější) smyčka je vždy aktivní smyčka projektu; druhá smyčka se vybírá z ostatních.
"""
import numpy as np
import pandas as pd
import streamlit as st

from ...core import MODELS, default_tc, detect_steps, find_segments, gs_issues, gs_sim, gs_table, iae, pidconl_sim, predict, tune
from ...core.apc import ff_design, mimo2_sim, no_delay, override_sim, rga2, rga_advice, smith_apl, smith_sim
from ...i18n import T
from .. import cache, loops
from ..charts import mkfig, show, style, tr
from ..theme import C_MV, C_PV, C_SET1, C_SET2, C_SP
from ..widgets import model_name, num, seg, sld
from . import apc_guide as guide
from . import cascade

ss = st.session_state
KINDS = ["cascade", "decouple", "override", "smith", "gainsched"]
C_B = "#7c3aed"          # druhá smyčka
C_REF = "#9aa5b1"        # srovnání (bez struktury)

_mimo = st.cache_data(show_spinner=False, max_entries=32)(mimo2_sim)
_override = st.cache_data(show_spinner=False, max_entries=32)(override_sim)
_smith = st.cache_data(show_spinner=False, max_entries=32)(smith_sim)
_gs = st.cache_data(show_spinner=False, max_entries=16)(gs_sim)
C_PTS = ["#0e7490", "#b45309", "#7c3aed"]   # pracovní body 1–3


def render(ctx):
    with ctx.tabs["cascade"]:
        ctx.gph["apc"] = st.container()
        st.caption(ctx.block_summary)
        kind = seg(st, T("apc_kind"), KINDS, "cascade", "apc_kind", format_func=lambda x: T("apc_" + x),
                   help=T("h_apc_kind")) or "cascade"
        if ctx.model is not None:
            guide.recommendations(recommend(ctx))
        if kind == "cascade":
            guide.render("cascade", _checks_cascade(ctx), T("g_impl_cascade"))
            cascade.render_body(ctx)
            return
        st.markdown(T("apc_intro_" + kind))
        if ctx.model is None or ctx.set2_ctrl is None:
            guide.render(kind, [(False, T("g_chk_model", n=loops.name(loops.active())),
                                 (T("g_btn_model"), guide.goto, (None, "model")))], None)
            st.info(T("need_model"), icon=":material/arrow_back:")
            return
        if kind == "smith":
            _smith_page(ctx)
            return
        if kind == "gainsched":
            _gainsched_page(ctx)
            return
        other = [i for i in loops.ids() if i != loops.active()]
        if not other:
            guide.render(kind, [_chk_model_a(ctx), (False, T("apc_need_loop"),
                                                    (T("loop_add"), guide.add_loop_and_go, ()))], None)
            return
        names = {i: loops.name(i) for i in other}
        if ss.get(f"apc_{kind}_b") not in other:  # výchozí druhá smyčka = ta, kterou doporučení navrhuje
            pref = [it[2] for it in (recommend(ctx)) if it[0] == kind and it[2] in other]
            ss[f"apc_{kind}_b"] = pref[0] if pref else other[0]
        bi = st.selectbox(T(f"apc_{kind}_b"), other, format_func=names.get, key=f"apc_{kind}_b",
                          help=T(f"h_apc_{kind}_b", a=loops.name(loops.active())))
        b = loops.loop_data(bi, ctx.fname)
        if b["model"] is None:
            guide.render(kind, [_chk_model_a(ctx), (False, T("g_chk_model", n=b["name"]),
                                                    (T("g_btn_model"), guide.goto, (bi, "model")))], None)
            return
        (_decouple_page if kind == "decouple" else _override_page)(ctx, bi, b)


def tuning_hint(ctx):
    """Jednořádkové upozornění v záložce Ladění, když by aktivní smyčce mohla pomoct struktura APC."""
    items = recommend(ctx)
    if items:
        r = st.columns([0.8, 0.2], vertical_alignment="center")
        r[0].caption(":material/lightbulb: " + T("g_tuning_hint", m=", ".join(dict.fromkeys(T("apc_" + k)
                                                                                         for k, _, _ in items))))
        r[1].button(T("g_open", m="APC"), key="g_tuning_apc", on_click=guide.goto,
                    kwargs=dict(tab="apc", kind=items[0][0], other=items[0][2]), type="tertiary")


# ---------------------------------------------------------------- doporučení a kontroly
def recommend(ctx):
    """Struktury, které by mohly aktivní smyčce pomoct – podle modelů a vazeb mezi smyčkami projektu."""
    items = []
    code, p = ctx.model[0], ctx.model[1]
    lags = _tchar((code, p)) - p[-1]
    ratio = p[-1] / max(p[-1] + lags, 1e-9)
    if ratio >= 0.5 and not MODELS[code]["integ"]:
        items.append(("smith", T("g_reco_smith", r=f"{ratio:.2f}"), None))
    spread = nl_spread(ctx)
    if spread is not None and spread > 1.5:
        items.append(("gainsched", T("g_reco_gs", s=f"{spread:.1f}"), None))
    a = _active(ctx)
    for i in loops.ids():
        if i == loops.active():
            continue
        b = loops.loop_data(i, ctx.fname)
        if b["c_sp"] not in (None, "—") and b["c_sp"] == a["c_mv"]:
            items.append(("cascade", T("g_reco_cascade", a=a["name"], b=b["name"]), i))
        if b["c_mv"] == a["c_mv"]:
            items.append(("override", T("g_reco_override", a=a["name"], b=b["name"], mv=a["c_mv"]), i))
        if b["model"] is not None and (b["c_mv"] in a["c_d"] or a["c_mv"] in b["c_d"]):
            xab, xba = _cross_model(a, b), _cross_model(b, a)
            lam = rga2(a["model"][1][0], xab[0] if xab else 0.0, xba[0] if xba else 0.0, b["model"][1][0])
            if not np.isfinite(lam) or abs(lam - 1) > 0.2:
                items.append(("decouple", T("g_reco_decouple", a=a["name"], b=b["name"],
                                            l="∞" if not np.isfinite(lam) else f"{lam:.2f}"), i))
    seen, out = set(), []
    for it in items:
        if it[:2] not in seen:
            seen.add(it[:2])
            out.append(it)
    return out


def nl_spread(ctx):
    """Poměr největšího a nejmenšího lokálního zesílení na úseku identifikace (None = nelze určit)."""
    code, p, pdl = ctx.model[0], ctx.model[1], ctx.model[2]
    if MODELS[code]["integ"] or ctx.ts_id is None:
        return None
    try:
        lg = cache.local_gains(code, p, pdl, ctx.ts_id, ctx.pv_id, ctx.mv_id, ctx.d_id, ctx.Ts)
    except Exception:
        return None
    if len(lg) < 2:
        return None
    g = np.abs([q["gain"] for q in lg])
    return float(np.max(g) / max(np.min(g), 1e-12))


def _chk_model_a(ctx):
    return True, T("g_chk_model_ok", n=loops.name(loops.active()), m=model_name(ctx.model[0])), None


def _checks_cascade(ctx):
    if ctx.model is None:
        return [(False, T("g_chk_model", n=loops.name(loops.active())), (T("g_btn_model"), guide.goto, (None, "model")))]
    checks = [_chk_model_a(ctx)]
    others = [(i, loops.loop_data(i, ctx.fname)) for i in loops.ids() if i != loops.active()]
    with_model = [b["name"] for _, b in others if b["model"] is not None]
    if with_model:
        checks.append((True, T("g_chk_cas_inner", n=", ".join(with_model)), None))
    else:
        checks.append((None, T("g_chk_cas_noinner"), (T("loop_add"), guide.add_loop_and_go, ())))
    inner = [b["name"] for _, b in others if b["c_sp"] not in (None, "—") and b["c_sp"] == ctx.c_mv]
    checks.append((True, T("g_chk_cas_mvsp_ok", mv=ctx.c_mv, n=", ".join(inner)), None) if inner
                  else (None, T("g_chk_cas_mvsp", mv=ctx.c_mv), None))
    checks.append((None, T("g_chk_cas_speed"), None))
    return checks


# ---------------------------------------------------------------- společné
def _active(ctx):
    """Aktivní smyčka ve stejném tvaru jako loops.loop_data."""
    return dict(name=loops.name(loops.active()), model=ctx.model, ctrl=ctx.set2_ctrl, c_mv=ctx.c_mv, c_pv=ctx.c_pv,
                c_sp=ctx.c_sp,
                c_d=list(ctx.c_d), pv_rng=(ctx.pv_lo, ctx.pv_hi), mv_rng=(ctx.mv_lo, ctx.mv_hi), u_pv=ctx.u_pv,
                u_mv=ctx.u_mv)


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


def _gain_eng(d_, src, dst):
    """Zesílení decoupleru v inženýrských jednotkách: ΔMV_dst [j.] / ΔMV_src [j.]."""
    return d_["gain"] * (dst["mv_rng"][1] - dst["mv_rng"][0]) / (src["mv_rng"][1] - src["mv_rng"][0])


def _decouple_page(ctx, bi, b):
    a = _active(ctx)
    xab, xba = _cross_model(a, b), _cross_model(b, a)
    ga, gb = (a["model"][0], list(a["model"][1])), (b["model"][0], list(b["model"][1]))
    dab = ff_design(*ga, xab) if xab else None
    dba = ff_design(*gb, xba) if xba else None
    checks = [_chk_model_a(ctx), (True, T("g_chk_model_ok", n=b["name"], m=model_name(b["model"][0])), None),
              (xab is not None, T("g_chk_cross", n=a["name"], mv=b["c_mv"]),
               (T("g_btn_data", n=a["name"]), guide.goto, (loops.active(), "data"))),
              (xba is not None, T("g_chk_cross", n=b["name"], mv=a["c_mv"]),
               (T("g_btn_data", n=b["name"]), guide.goto, (bi, "data"))),
              (None, T("g_chk_tuned"), None)]
    impl = T("g_impl_decouple") + "".join(
        "\n" + T("g_impl_dec_line", src=src["c_mv"], dst=dst["name"], g=f"{_gain_eng(d_, src, dst):.4g}",
                  lead=f"{d_['lead']:.3g}", lag=f"{d_['lag']:.3g}", dt=f"{d_['delay']:.3g}")
        for d_, src, dst in ((dab, b, a), (dba, a, b)) if d_)
    guide.render("decouple", checks, impl)
    if xab is None and xba is None:
        st.warning(T("dec_need_cross", a=a["name"], b=b["name"], mva=a["c_mv"], mvb=b["c_mv"]),
                   icon=":material/link_off:")
        return
    if xab is None or xba is None:
        st.caption(T("dec_one_way", x=a["name"] if xab is None else b["name"],
                     mv=b["c_mv"] if xab is None else a["c_mv"]))

    # ---- RGA
    lam = rga2(ga[1][0], xab[0] if xab else 0.0, xba[0] if xba else 0.0, gb[1][0])
    with st.container(border=True):
        r1, r2 = st.columns([1, 3], vertical_alignment="center")
        r1.metric("RGA λ₁₁", "∞" if not np.isfinite(lam) else f"{lam:.2f}", help=T("h_rga"))
        r2.markdown(T(rga_advice(lam), a=a["name"], b=b["name"], mva=a["c_mv"], mvb=b["c_mv"]))

    # ---- decouplery a scénář
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
        g_eng = _gain_eng(d_, src, dst)
        prm.append({T("dec_path"): f"{src['c_mv']} → MV {dst['name']}", T("dec_gain_pct"): round(d_["gain"], 4),
                    T("dec_gain_eng"): round(g_eng, 4), "Lead [s]": round(d_["lead"], 3), "Lag [s]": round(d_["lag"], 3),
                    T("ff_delay"): round(d_["delay"], 3)})
    st.markdown(f"**{T('dec_params')}**")
    st.dataframe(pd.DataFrame(prm), hide_index=True)
    st.caption(T("dec_params_help"))


# ---------------------------------------------------------------- override
def _override_page(ctx, bi, b):
    a = _active(ctx)
    same = b["c_mv"] == a["c_mv"]
    checks = [_chk_model_a(ctx), (True, T("g_chk_model_ok", n=b["name"], m=model_name(b["model"][0])), None),
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


def _smith_page(ctx):
    code, p, _ = ctx.model
    samp = ctx.samp
    lags = _tchar((code, p)) - p[-1]
    ratio = p[-1] / max(p[-1] + lags, 1e-9)
    integ = MODELS[code]["integ"]
    tc_key = _sm_tc_key(code, p)
    v, r_, rows = smith_values(ctx)
    checks = [_chk_model_a(ctx), (not integ, T("g_chk_sm_integ"), None),
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


# ---------------------------------------------------------------- gain scheduling
def _gs_blocks(ctx, settle):
    """Bloky dat mezi velkými přechody MV (změna pracovního bodu); začátek bloku bez přechodového děje."""
    t = ctx.t
    try:
        st_ = detect_steps(ctx.mv, ctx.Ts)
    except Exception:
        return []
    if len(st_) < 3:
        return []
    sizes = np.abs([q["size"] for q in st_])
    big = sorted(q["i"] for q in st_ if abs(q["size"]) > 2.5 * np.median(sizes))
    edges = [0] + big + [len(t) - 1]
    out = []
    for a, b in zip(edges[:-1], edges[1:]):
        t0 = t[a] + (settle if a > 0 else 0.0)
        t1 = t[b] - ctx.Ts
        if t1 - t0 > 2 * settle:
            out.append((float(t0), float(t1)))
    return out


def _gs_auto(ctx, n=3):
    """
    Návrh úseků pro pracovní body: bloky mezi velkými přechody MV, jinak shluky skoků (find_segments);
    z kandidátů se vyberou ty na nejnižší, prostřední a nejvyšší úrovni PV. Nouzově třetiny dat.
    """
    t = ctx.t
    settle = 4 * _tchar(ctx.model)
    cands = _gs_blocks(ctx, settle)
    if len(cands) < n:
        try:
            cands = [(float(g["start"]), float(g["end"]))
                     for g in find_segments(t, ctx.mv, ctx.sp, ctx.Ts, ctx.has_sp, settle=settle)]
        except Exception:
            cands = []
    lv = []
    for a, b in cands:
        m = (t >= a) & (t <= b)
        if m.sum() > 10 and np.nanmax(ctx.mv[m]) - np.nanmin(ctx.mv[m]) > 0.2:
            lv.append((float(np.nanmean(ctx.pv[m])), (a, b)))
    lv.sort()
    if len(lv) >= n:
        pick = [lv[0], lv[len(lv) // 2], lv[-1]] if n == 3 else [lv[0], lv[-1]]
        return [r for _, r in pick]
    edges = np.linspace(t[0], t[-1], n + 1)
    return [(float(a), float(b)) for a, b in zip(edges[:-1], edges[1:])]


def _gs_ranges(ctx, n):
    """Úseky bodů ze session state (kontrola, že leží v datech), chybějící z automatického návrhu."""
    t0, t1 = float(ctx.t[0]), float(ctx.t[-1])
    auto = None
    out = []
    for i in range(n):
        v = ss.get(f"gs_r{i + 1}")
        ok = isinstance(v, (list, tuple)) and len(v) == 2 and t0 <= v[0] < v[1] <= t1
        if not ok:
            auto = auto or _gs_auto(ctx, n)
            v = auto[i]
        ss[f"gs_r{i + 1}"] = (float(v[0]), float(v[1]))
        out.append(ss[f"gs_r{i + 1}"])
    return out


def _gs_key(ctx, code, ranges):
    return [code] + [round(x, 1) for r in ranges for x in r] + [ctx.pv_lo, ctx.pv_hi, ctx.mv_lo, ctx.mv_hi]


def _gs_fit(ctx, code, ranges):
    """Identifikace modelu (typ aktivní smyčky) v každém úseku → body {x, u, fit, p} nebo chybová hláška."""
    pts = []
    for i, (a, b) in enumerate(ranges):
        m = (ctx.t >= a) & (ctx.t <= b)
        tt, pv, mv = ctx.t[m] - ctx.t[m][0], ctx.pv[m], ctx.mv[m]
        if m.sum() < 20 or np.nanmax(mv) - np.nanmin(mv) < 0.2:
            return None, T("gs_err_steps", i=i + 1)
        k = int(np.ceil(len(tt) / 2500))
        try:
            r = cache.fit_model(code, tt[::k], pv[::k], mv[::k], ctx.Ts * k)
            fit = float(predict(code, r["p"], [], tt, pv, mv, [], ctx.Ts)[1])
        except Exception as ex:
            return None, f"{T('gs_point', i=i + 1)}: {T(str(ex))}"
        pts.append([float(np.nanmean(pv)), float(np.nanmean(mv)), fit] + [float(x) for x in r["p"]])
    return pts, None


def _gs_points():
    return [dict(x=q[0], u=q[1], fit=q[2], p=list(q[3:])) for q in ss.get("gs_pts") or []]


def _gs_tune(ctx, code, p):
    """Ladění jednoho bodu zvolenou metodou (stejná agresivita ve všech bodech)."""
    ct = ss.get("gs_ct") or "PI"
    m = ss.get("gs_m") or "SIMC"
    samp = ctx.samp
    if m == "AMIGO":
        return tune(code, p, "AMIGO", None, ct, samp)
    r0 = tune(code, p, "SIMC", float(ss.get("gs_tcf") or 1.0) * default_tc(code, p, samp), ct, samp)
    if m == "SIMC":
        return r0
    return cache.opt_migo(code, tuple(p), ct, samp, ctx.diffgain, float(ss.get("gs_ms") or 1.6), None,
                          ((r0["Kc"], r0["Ti"], r0["Td"]),))


def gs_values(ctx):
    """
    Body s laděním a tabulka pro blok GainSched: (body, řádky tabulky [(vstup, hodnoty 1–3, jednotka)], doplněno)
    nebo None, pokud body ještě nejsou identifikované.
    """
    pts = _gs_points()
    if len(pts) < 2:
        return None
    code = ctx.model[0]
    for q in pts:
        r = _gs_tune(ctx, code, q["p"])
        q.update(gain=float(r["Kc"]), ti=float(r["Ti"]) if r["Ti"] > 0 else np.inf, td=float(r["Td"]))
    rows, filled = gs_table(pts)
    u_pv = ctx.u_pv or "PV"
    tab = [("X1 … X3", [float(ctx.EP(q["x"])) for q in rows], u_pv),
           ("Gain1 … Gain3", [q["gain"] for q in rows], "–"),
           ("TI1 … TI3", [q["ti"] for q in rows], "s"),
           ("TD1 … TD3", [q["td"] for q in rows], "s")]
    return pts, tab, filled


def gs_frame(tab):
    return pd.DataFrame([{T("gs_in"): name, **{T("gs_point", i=i + 1): float(f"{v:.4g}") if np.isfinite(v) else v
                                              for i, v in enumerate(vals)}, T("sm_apl_unit"): u}
                         for name, vals, u in tab])


def _gainsched_page(ctx):
    code = ctx.model[0]
    E, M_ = ctx.EP, ctx.EM
    if MODELS[code]["integ"]:
        guide.render("gainsched", [_chk_model_a(ctx), (False, T("g_chk_gs_integ"), None)], None)
        st.info(T("gs_integ"), icon=":material/info:")
        return
    spread = nl_spread(ctx)
    pts_now = _gs_points()

    # ---- 1. pracovní body: úseky dat
    with st.container(border=True):
        st.markdown(f"**{T('gs_s1')}**")
        st.caption(T("gs_s1_help"))
        a1, a2 = st.columns([1, 3], vertical_alignment="bottom")
        n = int(seg(a1, T("gs_n"), [2, 3], 3, "gs_n", help=T("h_gs_n")) or 3)
        if a2.button(T("gs_auto"), icon=":material/auto_fix_high:", help=T("h_gs_auto")):
            for i, r in enumerate(_gs_auto(ctx, n)):
                ss[f"gs_r{i + 1}"] = r
        ranges = _gs_ranges(ctx, n)
        step = float(ctx.Ts)
        cols = st.columns(n)
        for i in range(n):
            cols[i].slider(T("gs_point", i=i + 1), float(ctx.t[0]), float(ctx.t[-1]), key=f"gs_r{i + 1}", step=step,
                           format="%.0f s")
        ranges = [ss[f"gs_r{i + 1}"] for i in range(n)]
        f = mkfig(2, [0.62, 0.38])
        f.add_trace(tr(ctx.t, E(ctx.pv), "PV", C_PV, 1.2), 1, 1)
        f.add_trace(tr(ctx.t, M_(ctx.mv), "MV", C_MV, 1.1, show=False), 2, 1)
        for i, (a, b) in enumerate(ranges):
            for r in (1, 2):
                f.add_vrect(x0=a, x1=b, fillcolor=C_PTS[i], opacity=0.12, line_width=0, row=r, col=1)
            f.add_annotation(x=(a + b) / 2, y=1.0, yref="paper", text=str(i + 1), showarrow=False,
                             font=dict(color=C_PTS[i], size=14))
        show(style(f, max(ctx.H - 60, 320), [ctx.lab_pv, ctx.lab_mv], ctx.lab_t, rev="apc_gs_seg"),
             key="chart_apc_gs_seg", fname="gs_segments")
        key = _gs_key(ctx, code, ranges)
        b1, b2 = st.columns([1, 3], vertical_alignment="center")
        if b1.button(T("gs_fit"), type="primary", icon=":material/play_arrow:", width="stretch"):
            with st.spinner(T("gs_fitting")):
                pts, err = _gs_fit(ctx, code, ranges)
            if err:
                st.error(err, icon=":material/error:")
            else:
                ss["gs_pts"], ss["gs_key"] = pts, key
                pts_now = _gs_points()
        stale = bool(pts_now) and ss.get("gs_key") != key
        if stale:
            b2.warning(T("gs_stale"), icon=":material/update:")
        elif not pts_now:
            b2.caption(T("gs_need_fit"))

    pts = pts_now
    issues = gs_issues(pts) if len(pts) >= 2 else []
    fits_ok = all(q["fit"] >= 70 for q in pts) if pts else None
    checks = [_chk_model_a(ctx),
              (True if spread and spread > 1.5 else None,
               T("g_chk_gs_nl", s=f"{spread:.1f}") if spread else T("g_chk_gs_nl_unknown"), None),
              (bool(pts) and not stale, T("g_chk_gs_pts"), None),
              (fits_ok if pts else None, T("g_chk_gs_fit"), None),
              (not issues if pts else None, T("g_chk_gs_mono"), None),
              (None, T("g_chk_gs_x"), None)]
    vals = gs_values(ctx) if len(pts) >= 2 else None
    impl = None
    if vals:
        _, tab, _ = vals
        impl = T("g_impl_gainsched", u=ctx.u_pv or "PV")
    guide.render("gainsched", checks, impl)
    if spread is not None:
        (st.warning if spread > 1.5 else st.caption)(T("gs_spread", s=f"{spread:.1f}"))
    if len(pts) < 2:
        return
    for it in issues:
        st.warning(T("gs_issue_" + it), icon=":material/warning:")

    # ---- 2. modely a ladění v bodech
    with st.container(border=True):
        st.markdown(f"**{T('gs_s2')}**")
        c1, c2, c3 = st.columns([1.3, 0.8, 2], vertical_alignment="bottom")
        m = seg(c1, T("method"), ["SIMC", "AMIGO", "OPT"], "SIMC", "gs_m", format_func=lambda x: T("m_" + x)) or "SIMC"
        seg(c2, T("ctrl_type"), ["PI", "PID"], "PI", "gs_ct")
        if m == "SIMC":
            sld(c3, T("gs_tcf"), 0.3, 5.0, 1.0, "gs_tcf", step=0.1, help=T("h_gs_tcf"))
        elif m == "OPT":
            seg(c3, T("gs_ms"), [1.4, 1.6, 1.8], 1.6, "gs_ms", help=T("h_gs_ms"))
        st.caption(T("mdesc_" + m) + (f" {T('cdesc_MIGO')}" if m == "OPT" else ""))
        pts, tab, filled = gs_values(ctx)
        names = MODELS[code]["params"]
        set2 = _clean(ctx.set2_ctrl)
        rows, ms_at = [], {}
        for i, q in enumerate(pts):
            ctrl_i = dict(_clean(ctx.base_ctrl), Gain=q["gain"], TI=q["ti"], TD=q["td"])
            rb_s, rb_2 = cache.robustness(code, q["p"], ctrl_i), cache.robustness(code, q["p"], set2)
            ms = lambda rb: f"{rb['Ms']:.2f}" if rb["stable"] and np.isfinite(rb["Ms"]) else "∞"  # noqa: E731
            ms_at[q["x"]] = (ms(rb_2), ms(rb_s))
            rows.append({T("gs_pt"): i + 1, f"X [{ctx.u_pv or 'PV'}]": float(f"{E(q['x']):.4g}"),
                         f"MV [{ctx.u_mv or '%'}]": float(f"{M_(q['u']):.4g}"),
                         **{nm: float(f"{v:.4g}") for nm, v in zip(names, q["p"])},
                         "Fit %": round(q["fit"], 1), "Gain": float(f"{q['gain']:.4g}"),
                         "TI": float(f"{q['ti']:.4g}"), "TD": float(f"{q['td']:.3g}"),
                         T("gs_ms_s"): ms(rb_s), T("gs_ms_2"): ms(rb_2)})
        st.dataframe(pd.DataFrame(rows), hide_index=True)
        st.caption(T("gs_pts_help"))

    # ---- 3. hodnoty do bloku GainSched
    st.markdown(f"#### {T('gs_tab_title')}", help=T("h_gs_tab"))
    st.dataframe(gs_frame(tab), hide_index=True)
    if filled:
        st.caption(T("gs_filled"))

    # ---- 4. simulace: jedna sada vs. gain scheduling na nelineárním procesu
    st.markdown(f"#### {T('gs_sim_title')}", help=T("h_gs_sim"))
    xs = sorted(q["x"] for q in pts)
    seq = xs + [xs[0]]
    tp = max(12 * _tchar((code, q["p"])) for q in pts) + 50 * ctx.samp
    h, nn, t = _grid(tp * len(seq), ctx.samp)
    k_seg = np.minimum((t // tp).astype(int), len(seq) - 1)
    sp = np.array(seq)[k_seg]
    d = np.where((t % tp) >= 0.55 * tp, 5.0, 0.0)
    rows3 = gs_table(pts)[0]
    sched = {k: [q[kq] for q in rows3] for k, kq in (("X", "x"), ("gain", "gain"), ("ti", "ti"), ("td", "td"))}
    plant = [dict(x=q["x"], u=q["u"], p=q["p"]) for q in pts]
    tf, of = _gs(code, plant, set2, None, h, sp, d)
    ts_, os_ = _gs(code, plant, dict(_clean(ctx.base_ctrl), Gain=sched["gain"][0], TI=sched["ti"][0],
                                     TD=sched["td"][0]), sched, h, sp, d)
    f = mkfig(3, [0.5, 0.27, 0.23])
    f.add_trace(tr(t, E(sp), "SP", C_SP, 1.3, "dash", "hv"), 1, 1)
    f.add_trace(tr(tf, E(of["PV"]), T("gs_fixed"), C_SET1, 1.6, "dot"), 1, 1)
    f.add_trace(tr(ts_, E(os_["PV"]), T("gs_sched"), C_SET2, 2.0), 1, 1)
    f.add_trace(tr(tf, M_(of["MV"]), T("gs_fixed"), C_SET1, 1.4, "dot", show=False), 2, 1)
    f.add_trace(tr(ts_, M_(os_["MV"]), T("gs_sched"), C_SET2, 1.6, show=False), 2, 1)
    f.add_trace(tr(tf, of["Gain"], T("gs_fixed"), C_SET1, 1.4, "dot", show=False), 3, 1)
    f.add_trace(tr(ts_, os_["Gain"], T("gs_sched"), C_SET2, 1.6, show=False), 3, 1)
    show(style(f, ctx.H + 120, [ctx.lab_pv, ctx.lab_mv, "Gain"], ctx.lab_t, rev="apc_gs"), key="chart_apc_gs",
         fname="gainsched", report=T("apc_gainsched"))
    PR = ctx.PR / 100
    kp = []
    for i, x in enumerate(seq[1:], start=1):
        m_ = k_seg == i
        kp.append({T("gs_step"): f"{E(seq[i - 1]):.4g} → {E(x):.4g}",
                   T("gs_iae_fixed"): round(iae(t[m_], sp[m_], of["PV"][m_]) * PR, 4),
                   T("gs_iae_sched"): round(iae(t[m_], sp[m_], os_["PV"][m_]) * PR, 4),
                   T("gs_ms_fixed"): ms_at.get(x, ("—",))[0], T("gs_ms_sched"): ms_at.get(x, ("—", "—"))[1]})
    st.dataframe(pd.DataFrame(kp), hide_index=True)
    st.caption(T("gs_sim_help"))
