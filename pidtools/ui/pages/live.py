"""
Záložka Živá simulace: smyčka běží v reálném čase (volitelně zrychleně), SP, ruční MV, poruchu i aktivní sadu
parametrů jde měnit za běhu. Používá stejný model regulátoru, ventilu a procesu jako ostatní simulace
(`pidtools.core.LiveLoop`), včetně prvků smyčky a vlastností procesu a ventilu ze záložky Ladění.
"""
import numpy as np
import streamlit as st

from ...core import LiveLoop
from ...i18n import T
from ..charts import mkfig, show, style, tr
from ..theme import C_MV, C_PV, C_SET1, C_SET2, C_SP
from ..widgets import seg

ss = st.session_state
SPEEDS = [1, 5, 20, 100]


def _new_loop(ctx, mcode, p, ctrl, pv0, mv0):
    h = min(ctx.samp, max(0.05, ctx.samp / 5))
    loop = LiveLoop(mcode, p, ctrl, h, pv0, mv0, ctx.plant, history=int(900 / h))
    ss.live = dict(loop=loop, key=(mcode, tuple(p), ctx.samp))
    return loop


def render(ctx):
    with ctx.tabs["live"]:
        st.caption(ctx.block_summary)
        if ctx.model is None or ctx.set1_ctrl is None:
            st.info(T("need_model"), icon=":material/arrow_back:")
            return
        mcode, p, _ = ctx.model
        st.markdown(f"#### {T('live_sim_title')}")
        st.caption(T("live_sim_desc"))
        pv0 = float(np.nanmedian(ctx.sp[ctx.sel_mask])) if ctx.has_sp else float(ctx.pv_id[0])
        mv0 = float(ctx.mv_id[0])
        running = bool(ss.get("live_run"))

        @st.fragment(run_every=1.0 if running else None)
        def live_fragment():
            c1, c2, c3, c4, c5 = st.columns([1, 1.2, 1.1, 1.1, 0.8], vertical_alignment="bottom")
            run = c1.toggle(T("live_run"), key="live_run", help=T("live_run_h"))
            active = seg(c2, T("live_active"), ["1", "2"], "2", "live_set",
                         format_func=lambda x: T("set_" + x)) or "2"
            mode = seg(c3, T("live_mode"), ["AUTO", "MAN"], "AUTO", "live_mode") or "AUTO"
            speed = seg(c4, T("live_speed"), SPEEDS, 1, "live_speed", format_func=lambda x: f"{x}×",
                        help=T("h_live_speed")) or 1
            reset = c5.button(T("live_reset"), icon=":material/restart_alt:", width="stretch")
            if run != running:  # změna běhu → plný rerun (nastaví periodu fragmentu)
                st.rerun()
            ctrl = ctx.set1_ctrl if active == "1" else ctx.set2_ctrl
            live = ss.get("live")
            if reset or live is None or live["key"] != (mcode, tuple(p), ctx.samp):
                loop = _new_loop(ctx, mcode, p, ctrl, pv0, mv0)
            else:
                loop = live["loop"]
                loop.set_tuning(ctrl)

            with st.container(border=True):
                s1, s2, s3 = st.columns(3)
                sp_e = s1.slider(T("live_sp", u=ctx.u_pv or "PV"), float(ctx.pv_lo), float(ctx.pv_hi),
                                 float(ctx.EP(pv0)), key=f"live_sp|{ctx.fname}")
                mv_e = s2.slider(T("live_mv", u=ctx.u_mv or "MV"), float(ctx.mv_lo), float(ctx.mv_hi),
                                 float(ctx.EM(mv0)), key=f"live_mv|{ctx.fname}", disabled=mode == "AUTO",
                                 help=T("h_live_mv"))
                span = 0.5 * ctx.MR
                d_e = s3.slider(T("live_dist", u=ctx.u_mv or "MV"), -span, span, 0.0, key=f"live_d|{ctx.fname}",
                                help=T("h_live_dist"))
            if run:
                loop.advance(float(speed), float(ctx.P(sp_e)), mode == "AUTO", float(ctx.M(mv_e)),
                             d_e / ctx.MR * 100)
            hist = loop.hist
            if hist["t"]:
                tt = np.asarray(hist["t"])
                fig = mkfig(2, [0.65, 0.35])
                fig.add_trace(tr(tt, ctx.EP(hist["SP"]), "SP", C_SP, 1.5, "dash", "hv"), 1, 1)
                fig.add_trace(tr(tt, ctx.EP(hist["PV"]), "PV", C_PV, 2.0), 1, 1)
                col = C_SET1 if active == "1" else C_SET2
                fig.add_trace(tr(tt, ctx.EM(hist["MV"]), "MV", col, 2.0), 2, 1)
                if ctx.plant.get("Stic", 0) > 0:
                    fig.add_trace(tr(tt, ctx.EM(hist["V"]), T("valve_pos"), C_MV, 1.2, "dot", "hv"), 2, 1)
                style(fig, ctx.H, [ctx.lab_pv, ctx.lab_mv], ctx.lab_t, rev="live")
                show(fig, key="live_chart", fname="live_simulation")
                st.caption(T("live_status", t=f"{loop.t:.0f}", pv=f"{ctx.EP(hist['PV'][-1]):.4g}",
                             mv=f"{ctx.EM(hist['MV'][-1]):.4g}"))
            else:
                st.info(T("live_hint"), icon=":material/play_circle:")

        live_fragment()
