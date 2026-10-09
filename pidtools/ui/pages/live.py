"""
Záložka Živá simulace: smyčka běží přímo v prohlížeči (komponenta st.components.v2, ~60 snímků/s) – SP, ruční MV,
poruchy, šum, filtr PV i ladění reagují okamžitě, bez čekání na server; stav přežije přepnutí záložky.
Výpočet je přepis jádra `pidtools.core.simulation` (`static/live_engine.js`, shoda s Pythonem ověřena testem),
včetně prvků smyčky a ventilu ze záložky Ladění. Ladění sady 2 jde ze simulace zapsat zpět (trigger „apply“).
"""
import json

import numpy as np
import streamlit as st

from ...i18n import T
from .. import loops
from ..theme import C_MV, C_PV, C_SET1, C_SET2, C_SP, FONT
from ..widgets import static_asset, v2_component

ss = st.session_state
SPEEDS = [1, 5, 20, 100, 500]
_LV_KEYS = ("compare", "advanced", "sec_tune", "apply", "revert", "tune_hint", "gain", "sec_dist", "dist_type", "dist_loc",
            "dt_step", "dt_ramp", "dt_sine", "dt_random", "dt_pulse", "loc_in", "loc_out", "dist_amp", "dist_sigma",
            "dist_short", "pp_step", "pp_ramp", "pp_sine", "pp_random", "pp_pulse", "pulse_go", "sec_meas", "noise", "pvf",
            "meas_hint", "sec_plant", "pk", "pt", "pth", "stic", "plant_hint", "sec_view", "window", "win_auto",
            "view_hint", "zoomed", "kpi_since", "kpi_maxdev", "kpi_over", "kpi_settle", "kpi_travel", "ev_tune",
            "ev_set", "ev_dist", "ev_applied", "chart", "kpi_title", "kpi_note", "sec_mode", "both_run", "lcmp")


def _ctrl_js(c):
    """Parametry regulátoru pro JS (nekonečno → null, jen potřebné klíče)."""
    keys = ("Gain", "TI", "TD", "DiffGain", "SampleTime", "PropFacSP", "PropFbk", "DiffFbk", "DeadBand", "DbMode", "MV_Lo",
            "MV_Hi", "PVFilt", "MVRate", "SPRate")
    out = {}
    for k in keys:
        if k in c:
            v = c[k]
            out[k] = None if isinstance(v, float) and not np.isfinite(v) else (float(v) if isinstance(v, (int, float, np.floating)) and not isinstance(v, bool) else v)
    return out


_CSS = """
.pidlive { font-family:inherit; font-size:13px; color:var(--tx); --acc:#1f5fa8; --tx:#1f2933; --mut:#52606d;
           --card:#ffffff; --ln:#d7dde5; --soft:#e5e9ef; --side:#f6f8fa; --ctl:#c3ccd6; }
.pidlive.dark { --tx:#e2e8f0; --mut:#94a3b8; --card:#111a2e; --ln:#26324a; --soft:#1c2740; --side:#0f172a; --ctl:#3b4a63; }
.pidlive * { box-sizing:border-box; }
.pidlive .lvg { display:grid; grid-template-columns:minmax(0,2.7fr) minmax(0,1fr); gap:16px; align-items:stretch; }
.pidlive .lvm { min-width:0; display:flex; flex-direction:column; gap:12px; padding:0 0 32px 0; }
.pidlive .lvs { display:flex; flex-direction:column; gap:12px; background:var(--side); border-left:1px solid var(--ln);
                padding:16px 24px 32px 14px; min-height:100vh; margin-top:-16px; }
.pidlive .card { background:var(--card); border:1px solid var(--ln); border-radius:10px; padding:10px 14px; }
.pidlive .bar { display:flex; flex-wrap:wrap; align-items:center; gap:8px 14px; }
.pidlive .bar .sp { flex:1; }
.pidlive .chead { display:flex; align-items:baseline; gap:10px; flex-wrap:wrap; margin-bottom:6px; }
.pidlive .chead .t { font-size:15px; font-weight:600; }
.pidlive .chead .n, .pidlive .hint, .pidlive .lab { font-size:12px; color:var(--mut); }
.pidlive .mono, .pidlive .val, .pidlive #read { font-family:'IBM Plex Mono', ui-monospace, monospace; font-size:12px; }
.pidlive .grp { display:flex; flex-direction:column; gap:4px; }
.pidlive .lrow { display:grid; grid-template-columns:86px minmax(0,1fr); align-items:center; gap:8px; }
.pidlive .btns { display:flex; gap:8px; flex-wrap:wrap; }
.pidlive button { font:inherit; font-size:13px; color:var(--tx); background:var(--card); border:1px solid var(--ctl);
                  border-radius:6px; padding:5px 12px; cursor:pointer; }
.pidlive button:hover { border-color:var(--acc); }
.pidlive button.primary { background:var(--acc); border-color:var(--acc); color:#fff; font-weight:600; }
.pidlive button.go { background:#2f7a3f; border-color:#2f7a3f; color:#fff; font-weight:600; }
.pidlive button.mini { padding:0 6px; font-size:11px; border-radius:6px; }
.pidlive .segs { display:inline-flex; flex-wrap:wrap; }
.pidlive .segs button { border-radius:0; margin-left:-1px; padding:5px 11px; }
.pidlive .segs button:first-child { border-radius:8px 0 0 8px; margin-left:0; }
.pidlive .segs button:last-child { border-radius:0 8px 8px 0; }
.pidlive .segs button.on { background:var(--acc); border-color:var(--acc); color:#fff; font-weight:500; position:relative; }
.pidlive .chip { font-size:12px; border-radius:999px; padding:2px 10px; border:1px solid rgba(34,197,94,.45);
                 background:rgba(34,197,94,.13); color:#2f6f3e; }
.pidlive .chip.man { border-color:rgba(245,158,11,.5); background:rgba(245,158,11,.16); color:#8a4b00; }
.pidlive .chk { display:flex; align-items:center; gap:6px; padding:2px 0; cursor:pointer; }
.pidlive .chk input { accent-color:var(--acc); width:16px; height:16px; }
.pidlive .sl { display:flex; flex-direction:column; gap:2px; }
.pidlive .sl .top { display:flex; justify-content:space-between; align-items:center; gap:8px; }
.pidlive .sl.dis, .pidlive input:disabled { opacity:.45; }
.pidlive input[type=range] { width:100%%; accent-color:var(--acc); }
.pidlive input.num { width:90px; font:inherit; color:inherit; background:var(--card); text-align:right;
                     border:1px solid var(--ctl); border-radius:6px; padding:2px 6px; }
.pidlive details { background:var(--card); border:1px solid var(--ln); border-radius:10px; }
.pidlive summary { cursor:pointer; padding:12px 14px; font-size:15px; font-weight:600; list-style:none; display:flex;
                   align-items:center; gap:8px; }
.pidlive summary::before { content:"▸"; color:#9aa5b1; font-size:12px; width:12px; }
.pidlive details[open] > summary::before { content:"▾"; }
.pidlive details > section { padding:0 14px 14px; display:flex; flex-direction:column; gap:8px; }
.pidlive .tiles { display:grid; grid-template-columns:repeat(3,1fr); gap:8px; }
.pidlive .tile { border:1px solid var(--ln); border-radius:8px; padding:4px; text-align:center; background:var(--side); }
.pidlive .tile .l { font-size:11px; color:var(--mut); }
.pidlive .tile .v { font-family:'IBM Plex Mono', monospace; font-size:17px; font-weight:500; }
.pidlive .tile.mv .v, .pidlive .tile.mv .l { color:#c2410c; }
.pidlive table { border-collapse:collapse; width:100%%; font-size:13px; }
.pidlive th { text-align:right; font-weight:600; padding:6px 8px; border-bottom:1px solid var(--ln); }
.pidlive th:first-child, .pidlive td:first-child { text-align:left; }
.pidlive td { padding:5px 8px; border-bottom:1px solid var(--soft); text-align:right;
              font-family:'IBM Plex Mono', ui-monospace, monospace; font-size:12px; }
.pidlive td:first-child { font-family:inherit; font-size:13px; }
.pidlive tr:last-child td { border-bottom:0; }
.pidlive td.best { background:rgba(34,197,94,.14); }
.pidlive .dot { display:inline-block; width:9px; height:9px; border-radius:50%%; margin-right:6px; }
.pidlive .cvwrap { position:relative; }
.pidlive canvas { width:100%%; display:block; }
.pidlive #tip { position:absolute; display:none; pointer-events:none; font-size:11.5px; line-height:1.45; padding:6px 9px;
                border-radius:8px; border:1px solid var(--ln); background:var(--card); white-space:nowrap;
                box-shadow:0 2px 8px rgba(0,0,0,.08); }
"""

def _component():
    """Komponenta simulace (JS = jádro simulace + rozhraní)."""
    return v2_component("pidtools_live_sim", css=_CSS % dict(font=FONT),
                        js=static_asset("live_engine.js") + "\n" + static_asset("live_ui.js"))


def _apply_tuning():
    """„Zapsat do sady 2“ ze simulace → parametry sady 2 v záložce Ladění (callback, před vykreslením widgetů)."""
    v = ss.get("live_sim")
    v = getattr(v, "apply", None) if not isinstance(v, dict) else v.get("apply")
    if v:
        ss["set2_gain"], ss["set2_td"] = float(v["Gain"]), float(v["TD"] or 0.0)
        ss["set2_ti"] = float(v["TI"]) if v.get("TI") else 0.0
        ss["live_applied"] = True


def render(ctx):
    with ctx.tabs["live"]:
        ctx.gph["live"] = True
        if ctx.model is None or ctx.set1_ctrl is None:
            st.info(T("need_model"), icon=":material/arrow_back:")
            return
        if ctx.tabs["live"].open is False:   # mimo záložku se komponenta odpojí; stav simulace zůstává v prohlížeči
            return
        mcode, p, _ = ctx.model
        pv0 = float(np.nanmedian(ctx.sp[ctx.sel_mask])) if ctx.has_sp else float(ctx.pv_id[0])
        mv0 = float(ctx.mv_id[0])
        lags = (p[1] if mcode in ("P1D", "P2D", "I1D") else 0.0) + (p[2] if mcode == "P2D" else 0.0)
        window = float(np.clip(12 * (p[-1] + lags + ctx.samp), 60.0, 7200.0))
        plant = {k: (float(v) if isinstance(v, (int, float, np.floating)) else v)
                 for k, v in (ctx.plant or {}).items() if k in ("Stic", "SticJ", "ValveChar", "Noise")}
        cfg = dict(code=mcode, p=[float(v) for v in p], h=float(min(ctx.samp, max(0.05, ctx.samp / 5))),
                   pv0=pv0, mv0=mv0, plant=plant, window=window, speeds=SPEEDS,
                   speed0=next((v for v in SPEEDS if v >= window / 90), SPEEDS[-1]),  # okno za ~1,5 min
                   sets={"1": _ctrl_js(ctx.set1_ctrl), "2": _ctrl_js(ctx.set2_ctrl)},
                   pv_lo=float(ctx.pv_lo), pv_hi=float(ctx.pv_hi), mv_lo=float(ctx.mv_lo), mv_hi=float(ctx.mv_hi),
                   u_pv=ctx.u_pv or "", u_mv=ctx.u_mv or "", lab_pv=ctx.lab_pv, lab_mv=ctx.lab_mv, font=FONT,
                   labels=dict(start=T("live_start"), pause=T("live_pause"), reset=T("live_reset"),
                               lspeed=T("live_speed"), lset=T("live_active"), lmode=T("live_mode"),
                               set1=T("set_1"), set2=T("set_2"), lsp=T("live_sp", u=ctx.u_pv or "PV"),
                               lmv=T("live_mv", u=ctx.u_mv or "MV"), ld=T("live_dist", u=ctx.u_mv or "MV"),
                               d0=T("live_d0"), valve=T("valve_pos"), time=T("time_s"), read=T("live_read")))
        PR = ctx.pv_hi - ctx.pv_lo
        cfg.update(
            sim_id=f"{ctx.fname}|{loops.active()}|{mcode}|{[round(v, 6) for v in p]}|{cfg['h']}|{json.dumps(plant)}|"
                   f"{ctx.pv_lo}|{ctx.pv_hi}|{ctx.mv_lo}|{ctx.mv_hi}",
            ch=int(ctx.H), noise0=float(plant.get("Noise", 0.0) * PR / 100), pvf0=float(ctx.pvfilt or 0.0),
            pvf_max=float(max(10 * ctx.samp, 0.5 * (lags + p[-1]), 5.0)),
            dist_p0=float(max(4 * (lags + p[-1]), 10 * ctx.samp)), dist_pmax=float(max(40 * (lags + p[-1]), 100 * ctx.samp)),
            decimal="," if ss.get("lang", "cs") == "cs" else ".",
            light=dict(pv=C_PV, sp=C_SP, mv=C_MV, set1=C_SET1, set2=C_SET2, dist="#7c3aed", event="#b45309", acc="#1f5fa8"),
            dark=dict(pv="#60a5fa", sp="#9aa5b1", mv="#fb923c", set1="#94a3b8", set2="#4ade80", dist="#a78bfa",
                      event="#fbbf24", acc="#60a5fa"))
        cfg["labels"].update({k: T("lv_" + k) for k in _LV_KEYS})
        if ss.pop("live_applied", False):
            st.toast(T("lv_applied_toast"), icon=":material/check:")
        cfg["labels"].update(blk=ctx.block_summary, desc=T("live_sim_desc"), help=T("live_help"))
        _component()(key="live_sim", data=cfg, on_apply_change=_apply_tuning)
