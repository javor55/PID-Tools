"""Záložka Diagnostika: výkon smyčky, oscilace a stikce, nelinearita."""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from ...core import (MODELS, oscillation, stiction_ccf, valve_hysteresis)
from ...i18n import T
from ..cache import local_gains, loop_kpis
from ..charts import REPORT, show, style, tr
from ..layout import section, workspace
from ..theme import C_MV, C_PV
from ..widgets import num, tog
from .apc import guide as apc_guide
from ..table import table

ss = st.session_state

def render(ctx):
    """Záložka Diagnostika: úseky a nastavení vpravo; výkon smyčky, oscilace a grafy (CCF, MV–PV, poloha, nelinearita)
    vlevo."""
    Ts, d_id, fname, has_sp, model, mv, mv_e, mv_id, mvl_hi, mvl_lo, pos_e, pv, pv_id, samp, sp, t, ts_id, u_mv, u_pv = ctx.Ts, ctx.d_id, ctx.fname, ctx.has_sp, ctx.model, ctx.mv, ctx.mv_e, ctx.mv_id, ctx.mvl_hi, ctx.mvl_lo, ctx.pos_e, ctx.pv, ctx.pv_id, ctx.samp, ctx.sp, ctx.t, ctx.ts_id, ctx.u_mv, ctx.u_pv
    EM, M, MR, PR, lab_mv, lab_pv = ctx.EM, ctx.M, ctx.MR, ctx.PR, ctx.lab_mv, ctx.lab_pv
    with ctx.tabs["diag"]:
        ctx.gph["diag"] = True
        ws = workspace()
        integ_known = MODELS[model[0]]["integ"] if model is not None else None
        side = section(ws.side, T("dk_sec_diag_seg"), "diag_seg", expanded=True, icon=":material/date_range:")
        with ws.main:
            m_rec = st.container(border=True, key="pid_card_diagrec")
            m_perf, m_osc, m_diag = st.container(border=True), st.container(border=True), st.container()
        with side:
            st.caption(ctx.block_summary)
            st.caption(T("diag_intro"))
            dkey = f"rng_diag|{fname}|{t[-1]:.0f}"
            if dkey not in ss:
                ss[dkey] = (0.0, float(t[-1]))
            rd = st.slider(T("seg_diag"), 0.0, float(t[-1]), step=float(max(Ts, t[-1] / 1000)), key=dkey,
                           help=T("h_seg_diag"))
            integ_d = tog(st, T("diag_integ"), bool(integ_known), "diag_integ", help=T("h_diag_integ"))
            th_d = model[1][-1] if model is not None else num(T("diag_theta"), "diag_theta", 5.0, min_value=0.0,
                                                               help=T("h_diag_theta"))
        sd = (t >= rd[0]) & (t <= rd[1])

        def kpi_row(mask):
            k_ = loop_kpis(t[mask], sp[mask] if has_sp else pv[mask], pv[mask], mv[mask], Ts,
                           float(M(mvl_lo)), float(M(mvl_hi)), th_d + samp / 2, has_sp)
            return k_, {
                T("kpi_std", u=u_pv or "PV"): f"{k_['std_e'] * PR / 100:.4g}",
                T("kpi_iae_h", u=u_pv or "PV"): f"{k_['iae_h'] * PR / 100:.4g}",
                T("kpi_travel_h", u=u_mv or "MV"): f"{k_['travel_h'] * MR / 100:.4g}",
                T("kpi_rev_h"): f"{k_['rev_h']:.3g}",
                T("kpi_at_lim"): f"{k_['at_lim']:.1f} %",
                T("kpi_harris"): "—" if not np.isfinite(k_["harris"]) else f"{k_['harris']:.2f}",
                T("kpi_osc"): (T("yes_period", p=f"{k_['osc']['period']:.0f}") if k_["osc"]["osc"] else T("no")),
            }

        if sd.sum() < 100:
            side.warning(T("err_short"))
            return
        # ---- záznam s úseky A (a B)
        with side:
            compare_on = bool(ss.get("perf_compare"))
        segs_ = [(rd, "#1f5fa8", T("seg_a"))]
        if compare_on:
            rbk = f"rng_diagB|{fname}|{t[-1]:.0f}"
            if rbk in ss:
                segs_.append((ss[rbk], "#7c3aed", T("seg_b")))
        fig_ = ctx.data_fig(t)
        n_rows = 2 + (1 if ctx.dists else 0)
        shapes, notes = list(fig_.layout.shapes or ()), list(fig_.layout.annotations or ())
        for (a_, b_), col_, lab_ in segs_:
            for r in range(1, n_rows + 1):
                sfx = "" if r == 1 else str(r)
                shapes.append(dict(type="rect", xref=f"x{sfx}", yref=f"y{sfx} domain", x0=a_, x1=b_, y0=0, y1=1,
                                   fillcolor=col_, opacity=0.08, line=dict(color=col_, width=1), layer="below"))
            notes.append(dict(xref="x", yref="y domain", x=a_, y=1, text=lab_, showarrow=False, xanchor="left",
                              yanchor="top", font=dict(size=11, color=col_)))
        fig_.update_layout(shapes=shapes, annotations=notes)
        with m_rec:
            show(fig_, key="chart_diag_rec", fname="diag_record")
            st.caption(T("diag_rec_help"))

        # ---- výkon smyčky
        with side:
            compare = st.toggle(T("perf_compare"), key="perf_compare", help=T("h_perf_compare"))
            if compare:
                bkey = f"rng_diagB|{fname}|{t[-1]:.0f}"
                if bkey not in ss:
                    ss[bkey] = (float(t[-1]) / 2, float(t[-1]))
                rb2 = st.slider(T("seg_diag_b"), 0.0, float(t[-1]), step=float(max(Ts, t[-1] / 1000)), key=bkey)
        with m_perf:
            st.markdown(f"**{T('perf_title')}**")
            kA, rowA = kpi_row(sd)
            ptab = pd.DataFrame({T("seg_a"): rowA})
            if compare:
                sB = (t >= rb2[0]) & (t <= rb2[1])
                if sB.sum() >= 100:
                    kB, rowB = kpi_row(sB)
                    ptab = pd.DataFrame({T("seg_a"): rowA, T("seg_b"): rowB})
            table(ptab, width="stretch")
            REPORT["tables"].append((T("perf_title"), ptab))
            st.caption(T("perf_help"))

        # ---- oscilace a ventil (verdikt)
        with m_osc:
            st.markdown(f"**{T('osc_title')}**")
            sig = (sp[sd] - pv[sd]) if has_sp else pv[sd]
            osc = oscillation(sig, Ts)
            if not osc["osc"]:
                st.success(T("osc_none"), icon=":material/check_circle:")
            else:
                st.warning(T("osc_found", p=f"{osc['period']:.0f}", a=f"{osc['amp'] * PR / 100:.3g}", u=u_pv or "PV",
                             r=f"{osc['r']:.1f}"), icon=":material/waves:")
            sc = stiction_ccf(mv[sd], pv[sd], Ts, integ_d, osc["period"] if osc["osc"] else None)
            ratio = sc["ratio"]
            ctx.PROG["diag"] = 0 if not osc["osc"] else (2 if np.isfinite(ratio) and ratio < 0.35 else 1)
            if osc["osc"] and np.isfinite(ratio):
                if ratio < 0.35:
                    st.error(T("stic_likely", r=f"{ratio:.2f}"), icon=":material/build:")
                elif ratio > 0.7:
                    st.info(T("stic_unlikely", r=f"{ratio:.2f}"), icon=":material/tune:")
                else:
                    st.info(T("stic_unclear", r=f"{ratio:.2f}"), icon=":material/help:")
                REPORT["notes"].append(T("rep_osc", p=f"{osc['period']:.0f}", r=f"{ratio:.2f}"))
            hyst = valve_hysteresis(mv_e[sd], pos_e[sd]) if pos_e is not None else np.nan
            if pos_e is not None:
                st.metric(T("hyst"), "—" if not np.isfinite(hyst) else f"{abs(hyst):.3g} {u_mv or ''}", help=T("h_hyst"))
                if np.isfinite(hyst):
                    REPORT["notes"].append(T("rep_hyst", h=f"{abs(hyst):.3g}", u=u_mv or ""))
            else:
                st.caption(T("pos_missing"))

        # ---- grafy diagnostiky (pod záznamem)
        labels = [T("ccf_title_d") if integ_d else T("ccf_title"), T("phase_title")] + \
            ([T("pos_title")] if pos_e is not None else []) + [T("nl_title")]
        with m_diag:
            tabs_ = st.tabs(labels, key="diag_view", on_change="rerun")
        with tabs_[0]:
            fcc = go.Figure()
            fcc.add_trace(tr(sc["lags"], sc["ccf"], T("ccf"), C_PV, 2.0))
            fcc.add_vline(x=0, line=dict(color="#94a3b8", dash="dot", width=1))
            style(fcc, 360, xtitle=T("lag_s"), rev="ccf")
            fcc.update_layout(hovermode="x")
            show(fcc, key="chart_ccf", fname="ccf")
            st.caption(T("osc_help"))
        with tabs_[1]:
            yy = np.gradient(pv[sd], Ts) if integ_d else pv[sd]
            fph = go.Figure(go.Scattergl(x=EM(mv[sd]), y=yy * PR / 100, mode="markers+lines",
                                         marker=dict(size=3, color=C_PV, opacity=0.5),
                                         line=dict(width=0.6, color="#cbd5e1"), name="MV–PV"))
            style(fph, 360, rev="phase")
            fph.update_layout(hovermode="closest", xaxis_title=lab_mv, yaxis_title=("dPV/dt" if integ_d else lab_pv))
            show(fph, key="chart_phase", fname="mv_pv")
        if pos_e is not None:
            with tabs_[2]:
                fpos = go.Figure(go.Scattergl(x=mv_e[sd], y=pos_e[sd], mode="markers+lines",
                                              marker=dict(size=3, color=C_MV, opacity=0.5),
                                              line=dict(width=0.6, color="#fecaca")))
                style(fpos, 360, rev="pos")
                fpos.update_layout(xaxis_title=lab_mv, yaxis_title=T("col_pos"), hovermode="closest")
                show(fpos, key="chart_pos", fname="valve", report=T("pos_title"))

        # ---- nelinearita
        with tabs_[-1]:
            if model is None:
                st.info(T("need_model"), icon=":material/arrow_back:")
            else:
                lg = local_gains(model[0], model[1], model[2], ts_id, pv_id, mv_id, d_id, Ts)
                if len(lg) < 2:
                    st.info(T("nl_few"), icon=":material/info:")
                else:
                    gl = pd.DataFrame([{T("nl_time"): f"{g['t']:.0f}", T("nl_from"): f"{EM(g['mv_from']):.4g}",
                                        T("nl_to"): f"{EM(g['mv_to']):.4g}", T("nl_dir"): "↑" if g["dmv"] > 0 else "↓",
                                        T("nl_gain"): f"{g['gain']:.4g}", T("nl_ratio"): f"{g['ratio']:.2f}"} for g in lg])
                    n1_, n2_ = st.columns([1.2, 1])
                    table(where=n1_, data=gl, hide_index=True, width="stretch")
                    gains = np.array([g["gain"] for g in lg])
                    spread = np.max(np.abs(gains)) / max(np.min(np.abs(gains)), 1e-12)
                    fnl = go.Figure()
                    for dsign, col, nm in ((1, "#1f5fa8", "↑"), (-1, "#c2410c", "↓")):
                        xs = [EM((g["mv_from"] + g["mv_to"]) / 2) for g in lg if np.sign(g["dmv"]) == dsign]
                        ys = [g["gain"] for g in lg if np.sign(g["dmv"]) == dsign]
                        fnl.add_trace(go.Scatter(x=xs, y=ys, mode="markers", name=nm, marker=dict(size=11, color=col)))
                    fnl.add_hline(y=model[1][0], line=dict(color="#94a3b8", dash="dot"))
                    style(fnl, 300, rev="nl")
                    fnl.update_layout(xaxis_title=lab_mv, yaxis_title=MODELS[model[0]]["params"][0], hovermode="closest")
                    with n2_:
                        show(fnl, key="chart_nl", fname="nonlinearity", report=T("nl_title"))
                    ups = [g["gain"] for g in lg if g["dmv"] > 0]
                    dns = [g["gain"] for g in lg if g["dmv"] < 0]
                    if spread > 1.5:
                        ctx.PROG["diag"] = max(ctx.PROG.get("diag", 0), 1)
                        st.warning(T("nl_warn", s=f"{spread:.1f}"), icon=":material/show_chart:")
                        if not MODELS[model[0]]["integ"]:
                            st.button(T("nl_to_gs"), icon=":material/tune:", key="g_nl_gs", on_click=apc_guide.goto,
                                      kwargs=dict(tab="apc", kind="gainsched"))
                    else:
                        st.success(T("nl_ok", s=f"{spread:.2f}"), icon=":material/check_circle:")
                    if ups and dns and abs(np.mean(ups) / np.mean(dns) - 1) > 0.3:
                        st.info(T("nl_dir_warn", r=f"{np.mean(ups) / np.mean(dns):.2f}"), icon=":material/swap_vert:")
                    REPORT["notes"].append(T("rep_nl", s=f"{spread:.2f}"))
                    st.caption(T("nl_help"))
