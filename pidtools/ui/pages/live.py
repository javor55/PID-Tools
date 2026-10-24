"""
Záložka Živá simulace: smyčka běží přímo v prohlížeči (komponenta st.components.v2, ~60 snímků/s) – SP, ruční MV,
poruchy, šum, filtr PV i ladění reagují okamžitě, bez čekání na server; stav přežije přepnutí záložky.
Výpočet je přepis jádra `pidtools.core.simulation` (`static/live_engine.js`, shoda s Pythonem ověřena testem),
včetně prvků smyčky a ventilu ze záložky Ladění. Ladění sady 2 jde ze simulace zapsat zpět (trigger „apply“).
Konfigurace komponenty je `app.live.web_config` (sdílí ji nové rozhraní), vzhled `static/live.css`.
"""
import numpy as np
import streamlit as st

from ...app.live import web_config
from ...i18n import T
from .. import loops
from ..widgets import static_asset, v2_component

ss = st.session_state


def _component():
    """Komponenta simulace (JS = jádro simulace + rozhraní)."""
    return v2_component("pidtools_live_sim", css=static_asset("live.css"),
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
        pv0 = float(np.nanmedian(ctx.sp[ctx.sel_mask])) if ctx.has_sp else float(ctx.pv_id[0])
        cfg = web_config(model=ctx.model, samp=ctx.samp, pv0=pv0, mv0=float(ctx.mv_id[0]), set1=ctx.set1_ctrl,
                         set2=ctx.set2_ctrl, plant=ctx.plant, pv_rng=(ctx.pv_lo, ctx.pv_hi),
                         mv_rng=(ctx.mv_lo, ctx.mv_hi), u_pv=ctx.u_pv, u_mv=ctx.u_mv, pvfilt=ctx.pvfilt,
                         height=ctx.H, scope=f"{ctx.fname}|{loops.active()}", summary=ctx.block_summary,
                         lang=ss.get("lang", "cs"))
        if ss.pop("live_applied", False):
            st.toast(T("lv_applied_toast"), icon=":material/check:")
        _component()(key="live_sim", data=cfg, on_apply_change=_apply_tuning)
