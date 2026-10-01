"""
Průvodci záložek: k čemu záložka je, postup, kterou metodu / model kdy zvolit, tipy z praxe a kontrolní seznam
podle skutečného stavu projektu (s tlačítky, která rovnou přepnou záložku nebo smyčku).

Každá záložka si na začátku vyhradí místo (ctx.gph[klíč]); obsah se vyplní na konci běhu (`render_all`), kdy jsou
známé výsledky – kvalita dat, model, robustnost sad. Texty: tg_<klíč>_what / _choose / _tips (markdown).
Průvodce je ve výchozím stavu sbalený.
"""
import numpy as np
import streamlit as st

from ...i18n import T
from .. import loops
from ..cache import robustness
from . import apc_guide

ss = st.session_state
goto = apc_guide.goto


def _render(key, checks):
    with st.expander(T("tg_title", m=T("tg_name_" + key)), expanded=False, icon=":material/menu_book:"):
        text = {k: T(f"tg_{key}_{k}") for k in ("what", "choose", "tips")}
        text = {k: v for k, v in text.items() if v != f"tg_{key}_{k}"}       # chybějící část se vynechá
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


def _has_model(ctx):
    return ctx.model is not None


def _model_check(ctx, here=False):
    if _has_model(ctx):
        return True, T("g_chk_model_ok", n=loops.name(loops.active()), m=T("model_" + ctx.model[0])), None
    return (False, T("g_chk_model", n=loops.name(loops.active())),
            None if here else (T("g_btn_model"), goto, dict(tab="model")))


# ---------------------------------------------------------------- kontroly jednotlivých záložek
def _checks_data(ctx):
    out = [(True, T("tgc_data_loaded", n=len(ctx.t), ts=f"{ctx.Ts:.3g}"), None)]
    out.append((ctx.c_pv != ctx.c_mv, T("tgc_data_cols", pv=ctx.c_pv, mv=ctx.c_mv), None))
    default_rng = (ctx.pv_lo, ctx.pv_hi, ctx.mv_lo, ctx.mv_hi) == (0.0, 100.0, 0.0, 100.0)
    out.append((None if default_rng else True, T("tgc_data_ranges"), None))
    dq = ctx.dq or {}
    if dq:
        n = int(dq.get("n_steps") or 0)
        out.append((True if n >= 2 else (None if n == 1 else False), T("tgc_data_steps", n=n), None))
        lvl = dq.get("level", 2)
        out.append((True if lvl == 0 else (None if lvl == 1 else False), T("tgc_data_quality_" + str(lvl)), None))
    return out


def _checks_model(ctx):
    out = [(True, T("tgc_data_ok"), None) if (ctx.dq or {}).get("level", 2) < 2
           else (None, T("tgc_data_weak"), (T("tgb_data"), goto, dict(tab="data")))]
    out.append(_model_check(ctx, here=True))
    if _has_model(ctx):
        fit = (ss.get("fit") or {}).get("res", {}).get(ctx.model[0], {}).get("fit")
        if fit is not None:
            out.append((True if fit >= 80 else (None if fit >= 70 else False), T("tgc_model_fit", f=f"{fit:.1f}"), None))
        if ctx.PROG.get("model_stale"):
            out.append((False, T("tgc_model_stale"), None))
        code, p = ctx.model[0], ctx.model[1]
        if code in ("P1D", "P2D") and ctx.ts_id is not None and len(ctx.ts_id) and p[1] > ctx.ts_id[-1]:
            out.append((None, T("tgc_model_long_T"), None))
        out.append((True if ctx.PROG.get("val") == 0 else None, T("tgc_model_val"), None))
    return out


def _checks_tuning(ctx):
    out = [_model_check(ctx)]
    if not _has_model(ctx) or ctx.set2_ctrl is None:
        return out
    g1, ti1 = ss.get("set1_gain", 1.0), ss.get("set1_ti", 100.0)
    out.append((None if (g1, ti1) == (1.0, 100.0) else True, T("tgc_tune_set1"), None))
    out.append((None, T("tgc_tune_block"), None))
    try:
        rb = robustness(ctx.model[0], list(ctx.model[1]), {k: v for k, v in ctx.set2_ctrl.items() if k not in ("FF", "FF_LL")})
        ms = rb["Ms"]
        ok = rb["stable"] and np.isfinite(ms)
        out.append((True if ok and ms <= 1.8 else (None if ok and ms <= 2.0 else False),
                    T("tgc_tune_ms", m=f"{ms:.2f}" if ok else "∞"), None))
    except Exception:
        pass
    same = (ss.get("set2_gain"), ss.get("set2_ti"), ss.get("set2_td")) == (g1, ti1, ss.get("set1_td", 0.0))
    out.append((None if same else True, T("tgc_tune_set2"), None))
    out.append((None, T("tgc_tune_verify"), (T("tgb_live"), goto, dict(tab="live"))))
    return out


def _checks_live(ctx):
    out = [_model_check(ctx)]
    if _has_model(ctx):
        out.append((None, T("tgc_live_sets"), (T("tgb_tuning"), goto, dict(tab="tuning"))))
        out.append((None, T("tgc_live_robust"), None))
    return out


def _checks_apc(ctx):
    out = [_model_check(ctx)]
    n = len(loops.ids())
    out.append((True if n > 1 else None, T("tgc_apc_loops", n=n), None if n > 1 else (T("loop_add"), apc_guide.add_loop_and_go, {})))
    return out


def _checks_project(ctx):
    out = [_model_check(ctx)]
    out.append((True if ss.get("autosave_on", True) else None, T("tgc_proj_autosave"), None))
    out.append((True if ss.get("report_html") else None, T("tgc_proj_report"), None))
    out.append((True if ss.get("rep_plant") else None, T("tgc_proj_meta"), None))
    return out


CHECKS = {"data": _checks_data, "model": _checks_model, "tuning": _checks_tuning, "live": _checks_live,
          "apc": _checks_apc, "project": _checks_project}


def render_all(ctx):
    """Vyplní průvodce všech záložek (volá se na konci běhu)."""
    for key, ph in ctx.gph.items():
        if key not in CHECKS:
            continue
        try:
            checks = CHECKS[key](ctx)
        except Exception:
            checks = []
        with ph:
            _render(key, checks)
