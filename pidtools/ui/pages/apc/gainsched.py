"""
APC – gain scheduling podle pracovního bodu (PV): body z úseků dat, model a ladění v bodech, blok GainSched.
"""
import numpy as np
import pandas as pd
import streamlit as st

from ....core import (MODELS, gs_issues, gs_table, iae)
from ....i18n import T
from ... import cache
from ...charts import mkfig, show, style, tr
from ...theme import C_MV, C_PV, C_SET1, C_SET2, C_SP
from ...widgets import seg, sld
from . import guide
from .recommend import chk_model_a, nl_spread
from ....app.apc import gainsched as app_gs
from .common import C_PTS, clean, gs_frame, grid, gs_sim_c, tchar, ss
from .gainsched_er import gs_er_render, gs_er_tab


# ---------------------------------------------------------------- gain scheduling



def _gs_auto(ctx, n=3):
    """Návrh úseků pro pracovní body (bloky mezi velkými přechody MV, shluky skoků, nouzově třetiny dat)."""
    return app_gs.auto_ranges(ctx.t, ctx.pv, ctx.mv, ctx.sp, ctx.Ts, ctx.has_sp, 4 * tchar(ctx.model), n)


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
    return app_gs.key(code, ranges, (ctx.pv_lo, ctx.pv_hi, ctx.mv_lo, ctx.mv_hi))


def _gs_rescale(old, new):
    """Body gain schedulingu přepočtené na nové rozsahy NormPV / NormMV (liší-li se klíč jen jimi)."""
    pts = app_gs.rescale(old, new, ss.get("gs_pts"))
    if pts is not None:
        ss["gs_pts"] = pts
        ss["gs_key"] = new


def _gs_fit(ctx, code, ranges):
    """Identifikace modelu (typ aktivní smyčky) v každém úseku → body nebo chybová hláška."""
    return app_gs.fit_points(code, ranges, ctx.t, ctx.pv, ctx.mv, ctx.Ts, cache.fit_model)


def _gs_points():
    return app_gs.points(ss.get("gs_pts"))


def _gs_tune(ctx, code, p):
    """Ladění jednoho bodu zvolenou metodou (stejná agresivita ve všech bodech)."""
    return app_gs.tune_point(code, p, ss.get("gs_m") or "SIMC", ss.get("gs_ct") or "PI", ctx.samp, ctx.diffgain,
                             float(ss.get("gs_tcf") or 1.0), float(ss.get("gs_ms") or 1.6), cache.opt_migo)


def gs_values(ctx):
    """
    Body s laděním a tabulka pro blok GainSched: (body, řádky tabulky [(vstup, hodnoty 1–3, jednotka)], doplněno)
    nebo None, pokud body ještě nejsou identifikované.
    """
    if ss.get("gs_x") == "er":
        return None, gs_er_tab(ctx), False
    pts = _gs_points()
    if len(pts) < 2:
        return None
    code = ctx.model[0]
    for q in pts:
        r = _gs_tune(ctx, code, q["p"])
        q.update(gain=float(r["Kc"]), ti=float(r["Ti"]) if r["Ti"] > 0 else np.inf, td=float(r["Td"]))
    tab, filled = app_gs.table(pts, ctx.EP, ctx.u_pv or "PV")
    return pts, tab, filled


def gainsched_render(ctx):
    code = ctx.model[0]
    E, M_ = ctx.EP, ctx.EM
    if MODELS[code]["integ"]:
        guide.render("gainsched", [chk_model_a(ctx), (False, T("g_chk_gs_integ"), None)], None)
        st.info(T("gs_integ"), icon=":material/info:")
        return
    if (seg(st, T("gs_x"), ["pv", "er"], "pv", "gs_x", format_func=lambda x: T("gs_x_" + x), help=T("h_gs_x"))
            or "pv") == "er":
        gs_er_render(ctx)
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
        _gs_rescale(ss.get("gs_key"), key)
        pts_now = _gs_points()
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
    checks = [chk_model_a(ctx),
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
        set2 = clean(ctx.set2_ctrl)
        rows, ms_at = [], {}
        for i, q in enumerate(pts):
            ctrl_i = dict(clean(ctx.base_ctrl), Gain=q["gain"], TI=q["ti"], TD=q["td"])
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
    tp = max(12 * tchar((code, q["p"])) for q in pts) + 50 * ctx.samp
    h, nn, t = grid(tp * len(seq), ctx.samp)
    k_seg = np.minimum((t // tp).astype(int), len(seq) - 1)
    sp = np.array(seq)[k_seg]
    d = np.where((t % tp) >= 0.55 * tp, 5.0, 0.0)
    rows3 = gs_table(pts)[0]
    sched = {k: [q[kq] for q in rows3] for k, kq in (("X", "x"), ("gain", "gain"), ("ti", "ti"), ("td", "td"))}
    plant = [dict(x=q["x"], u=q["u"], p=q["p"]) for q in pts]
    tf, of = gs_sim_c(code, plant, set2, None, h, sp, d)
    ts_, os_ = gs_sim_c(code, plant, dict(clean(ctx.base_ctrl), Gain=sched["gain"][0], TI=sched["ti"][0],
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
