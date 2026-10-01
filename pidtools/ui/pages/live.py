"""
Záložka Živá simulace: smyčka běží přímo v prohlížeči (JavaScript, ~60 snímků/s) – posuvníky SP, ruční MV
a poruchy reagují okamžitě, bez čekání na server. Výpočet je přepis jádra `pidtools.core.simulation`
(`static/live_engine.js`, shoda s Pythonem ověřena testem), včetně prvků smyčky a ventilu ze záložky Ladění.
"""
import json
import os

import numpy as np
import streamlit as st

from ...i18n import T
from ..theme import C_MV, C_PV, C_SET1, C_SET2, C_SP, FONT

ss = st.session_state
SPEEDS = [1, 5, 20, 100, 500]
_STATIC = os.path.join(os.path.dirname(__file__), "..", "static")


def _asset(name):
    with open(os.path.join(_STATIC, name), encoding="utf-8") as f:
        return f.read()


def _ctrl_js(c):
    """Parametry regulátoru pro JS (nekonečno → null, jen potřebné klíče)."""
    keys = ("Gain", "TI", "TD", "DiffGain", "SampleTime", "PropFbk", "DiffFbk", "DeadBand", "DbMode", "MV_Lo",
            "MV_Hi", "PVFilt", "MVRate", "SPRate")
    out = {}
    for k in keys:
        if k in c:
            v = c[k]
            out[k] = None if isinstance(v, float) and not np.isfinite(v) else (float(v) if isinstance(v, (int, float, np.floating)) and not isinstance(v, bool) else v)
    return out


_CSS = """
:root { --text:%(text)s; --muted:%(muted)s; --line:%(line)s; --chip:%(chip)s; --acc:%(acc)s; }
* { box-sizing:border-box; }
body { margin:0; font-family:%(font)s; font-size:13px; color:var(--text); background:transparent; }
.row { display:flex; flex-wrap:wrap; gap:14px 22px; align-items:flex-end; margin-bottom:10px; }
.grp { display:flex; flex-direction:column; gap:4px; }
.lab { font-size:12px; color:var(--muted); }
.segs { display:inline-flex; border:1px solid var(--line); border-radius:8px; overflow:hidden; }
button { font:inherit; color:var(--text); background:transparent; border:1px solid var(--line); border-radius:8px;
         padding:5px 12px; cursor:pointer; }
button:hover { border-color:var(--acc); }
button.primary { background:var(--acc); border-color:var(--acc); color:#fff; }
.segs button { border:none; border-radius:0; border-right:1px solid var(--line); }
.segs button:last-child { border-right:none; }
.segs button.on { background:var(--chip); color:var(--acc); font-weight:600; }
.sliders { display:grid; grid-template-columns:repeat(3, minmax(0,1fr)); gap:10px 24px; padding:10px 12px;
           border:1px solid var(--line); border-radius:10px; margin-bottom:8px; }
.sl { display:flex; flex-direction:column; gap:2px; }
.sl .top { display:flex; justify-content:space-between; gap:8px; }
.sl .val { font-variant-numeric:tabular-nums; font-weight:600; }
.sl.dis { opacity:.45; }
input[type=range] { width:100%%; accent-color:var(--acc); }
#d0 { padding:0 6px; font-size:11px; border-radius:6px; }
#read { color:var(--muted); font-variant-numeric:tabular-nums; margin:2px 0 4px; }
canvas { width:100%%; display:block; }
@media (max-width:640px) { .sliders { grid-template-columns:1fr; } }
"""

_HTML = """<!doctype html><html><head><meta charset="utf-8"><style>%(css)s</style></head><body>
<div class="row">
  <div class="grp"><div class="lab">&nbsp;</div><div style="display:flex;gap:8px">
    <button id="run" class="primary"></button><button id="reset"></button></div></div>
  <div class="grp"><div class="lab" id="lspeed"></div><div class="segs" id="speed"></div></div>
  <div class="grp"><div class="lab" id="lset"></div><div class="segs" id="set"></div></div>
  <div class="grp"><div class="lab" id="lmode"></div><div class="segs" id="mode"></div></div>
</div>
<div class="sliders">
  <div class="sl"><div class="top"><span class="lab" id="lsp"></span><span class="val" id="spv"></span></div>
    <input type="range" id="sps"></div>
  <div class="sl" id="mvbox"><div class="top"><span class="lab" id="lmv"></span><span class="val" id="mvv"></span></div>
    <input type="range" id="mvs"></div>
  <div class="sl"><div class="top"><span class="lab" id="ld"></span><span><span class="val" id="dv"></span>
    <button id="d0">0</button></span></div><input type="range" id="ds"></div>
</div>
<div id="read"></div>
<canvas id="cv" style="height:%(ch)spx"></canvas>
<script>%(engine)s</script>
<script>const CFG = %(cfg)s;</script>
<script>%(ui)s</script>
</body></html>"""


def render(ctx):
    with ctx.tabs["live"]:
        st.caption(ctx.block_summary)
        if ctx.model is None or ctx.set1_ctrl is None:
            st.info(T("need_model"), icon=":material/arrow_back:")
            return
        st.markdown(f"#### {T('live_sim_title')}")
        st.caption(T("live_sim_desc"))
        if ctx.tabs["live"].open is False:   # simulace běží v prohlížeči jen na viditelné záložce
            return
        mcode, p, _ = ctx.model
        pv0 = float(np.nanmedian(ctx.sp[ctx.sel_mask])) if ctx.has_sp else float(ctx.pv_id[0])
        mv0 = float(ctx.mv_id[0])
        lags = (p[1] if mcode in ("P1D", "P2D", "I1D") else 0.0) + (p[2] if mcode == "P2D" else 0.0)
        window = float(np.clip(12 * (p[-1] + lags + ctx.samp), 60.0, 7200.0))
        dark = getattr(st.context.theme, "type", None) == "dark"
        colors = dict(pv=C_PV if not dark else "#60a5fa", sp=C_SP, mv=C_MV, set1=C_SET1 if not dark else "#94a3b8",
                      set2=C_SET2 if not dark else "#4ade80",
                      text="#e2e8f0" if dark else "#1f2933", muted="#94a3b8" if dark else "#6b7280",
                      grid="rgba(148,163,184,0.18)" if dark else "rgba(100,116,139,0.15)")
        plant = {k: (float(v) if isinstance(v, (int, float, np.floating)) else v)
                 for k, v in (ctx.plant or {}).items() if k in ("Stic", "SticJ", "ValveChar", "Noise")}
        cfg = dict(code=mcode, p=[float(v) for v in p], h=float(min(ctx.samp, max(0.05, ctx.samp / 5))),
                   pv0=pv0, mv0=mv0, plant=plant, window=window, speeds=SPEEDS,
                   speed0=next((v for v in SPEEDS if v >= window / 90), SPEEDS[-1]),  # okno za ~1,5 min
                   sets={"1": _ctrl_js(ctx.set1_ctrl), "2": _ctrl_js(ctx.set2_ctrl)},
                   pv_lo=float(ctx.pv_lo), pv_hi=float(ctx.pv_hi), mv_lo=float(ctx.mv_lo), mv_hi=float(ctx.mv_hi),
                   u_pv=ctx.u_pv or "", u_mv=ctx.u_mv or "", lab_pv=ctx.lab_pv, lab_mv=ctx.lab_mv, font=FONT,
                   colors=colors,
                   labels=dict(start=T("live_start"), pause=T("live_pause"), reset=T("live_reset"),
                               lspeed=T("live_speed"), lset=T("live_active"), lmode=T("live_mode"),
                               set1=T("set_1"), set2=T("set_2"), lsp=T("live_sp", u=ctx.u_pv or "PV"),
                               lmv=T("live_mv", u=ctx.u_mv or "MV"), ld=T("live_dist", u=ctx.u_mv or "MV"),
                               d0=T("live_d0"), valve=T("valve_pos"), time=T("time_s"), read=T("live_read")))
        ch = int(ctx.H)
        css = _CSS % dict(text=colors["text"], muted=colors["muted"], line="rgba(128,128,128,0.35)",
                          chip="rgba(31,95,168,0.12)" if not dark else "rgba(96,165,250,0.18)",
                          acc="#1f5fa8" if not dark else "#60a5fa", font=FONT)
        html = _HTML % dict(css=css, ch=ch, engine=_asset("live_engine.js"), ui=_asset("live_ui.js"),
                            cfg=json.dumps(cfg, ensure_ascii=False).replace("</", "<\\/"))  # názvy sloupců nesmí ukončit <script>
        st.iframe(html, height="content")
        st.caption(T("live_help"))
