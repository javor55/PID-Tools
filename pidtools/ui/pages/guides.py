"""
Průvodci záložek: k čemu záložka je, postup, kterou metodu / model kdy zvolit, tipy z praxe a kontrolní seznam
podle skutečného stavu projektu (s tlačítky, která rovnou přepnou záložku nebo smyčku).

Záložka se přihlásí v ctx.gph[klíč]; průvodce aktivní záložky se vykreslí do nápovědy „?“ v hlavičce na konci běhu
(`render_all`), kdy jsou známé výsledky – kvalita dat, model, robustnost sad. Texty (tg_<klíč>_what / _choose / _tips)
a kontroly jsou sdílené s desktopem v pidtools.app.guides; zde je jen vykreslení a tlačítka.
"""
import streamlit as st

from ...app import guides
from ...i18n import T
from .. import loops
from .apc import guide as apc_guide

ss = st.session_state
goto = apc_guide.goto


def _render(key, checks):
    with st.container(key="pid_guide"):
        st.markdown(f"**{T('tg_title', m=T('tg_name_' + key))}**")
        text = {k: T(f"tg_{key}_{k}") for k in ("what", "choose", "tips") if guides.has(f"tg_{key}_{k}")}
        wide = "|---" in text.get("choose", "")                               # tabulka potřebuje celou šířku
        cols = [st.container()] * 2 if wide else st.columns(2, gap="large")
        for col, k in zip(cols, ("what", "choose")):
            if k in text:
                col.markdown(f"##### {T('tg_tab_' + k)}")
                col.markdown(text[k])
        if "tips" in text:
            st.markdown(f"##### {T('tg_tab_tips')}")
            st.markdown(text["tips"])
        if checks:
            st.markdown(f"**{T('g_checklist')}**")
            for n, (ok, text, action) in enumerate(checks):
                r = st.columns([0.05, 0.7, 0.25], vertical_alignment="center")
                r[0].markdown(":material/check_circle:" if ok else (":material/radio_button_unchecked:" if ok is False
                                                                     else ":material/info:"))
                r[1].markdown(text)
                if action and ok is not True:
                    label, cb, kw = action
                    r[2].button(label, on_click=cb, kwargs=kw, key=f"tg_act|{key}|{n}", width="stretch",
                                icon=":material/arrow_forward:")


def _state(ctx):
    """Stav pro sdílené kontroly průvodců (pidtools.app.guides)."""
    fit = (ss.get("fit") or {}).get("res", {}).get(ctx.model[0], {}).get("fit") if ctx.model is not None else None
    return guides.GuideState(
        loop_name=loops.name(loops.active()), n_samples=len(ctx.t) if ctx.t is not None else 0, Ts=ctx.Ts or 0.0,
        c_pv=ctx.c_pv, c_mv=ctx.c_mv, norm=(ctx.pv_lo, ctx.pv_hi, ctx.mv_lo, ctx.mv_hi), dq=ctx.dq or {},
        model=ctx.model, fit=fit, stale=bool(ctx.PROG.get("model_stale")),
        t_seg=float(ctx.ts_id[-1]) if ctx.ts_id is not None and len(ctx.ts_id) else 0.0, val_status=ctx.PROG.get("val"),
        set1=(ss.get("set1_gain", 1.0), ss.get("set1_ti", 100.0), ss.get("set1_td", 0.0)),
        set2=(ss.get("set2_gain"), ss.get("set2_ti"), ss.get("set2_td")), set2_ctrl=ctx.set2_ctrl,
        n_loops=len(loops.ids()), report=bool(ss.get("report_html")),
        plant_meta=bool(ss.get("rep_plant")))


def _action(a):
    """Identifikátor akce ze sdílených kontrol → (popisek, callback, argumenty) tlačítka."""
    if a is None:
        return None
    if a == "add_loop":
        return T("loop_add"), apc_guide.add_loop_and_go, {}
    tab = a.split(":", 1)[1]
    return T({"model": "g_btn_model", "tuning": "tgb_tuning", "live": "tgb_live"}.get(tab, "tgb_tuning")), goto, dict(tab=tab)


def render_all(ctx):
    """Průvodce aktivní záložky do nápovědy „?“ v hlavičce (volá se na konci běhu, kdy jsou známé výsledky)."""
    key = {"cascade": "apc"}.get(ctx.active_tab, ctx.active_tab)
    if key not in ctx.gph or key not in guides.CHECKS or ctx.help_ph is None:
        return
    checks = [(ok, txt, _action(a)) for ok, txt, a in guides.checks(key, _state(ctx))]
    with ctx.help_ph:
        _render(key, checks)
