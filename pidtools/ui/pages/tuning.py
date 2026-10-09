"""Záložka Ladění (rozložení jako desktop): vlevo scénář v grafu a frekvenční analýza, vpravo scénář → návrh → sady, blok PIDConL."""
import html
import time
from contextlib import nullcontext
from types import SimpleNamespace

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from ...core import (DIST_PARAMS, MODELS, d_advice, default_tc, pd_z, tune)
from ...app import frequency as fq
from ...app import scenario
from ...app.plots import C_SUG, freq_figs, freq_table
from ...app import tuning as tun
from ...app.loop import block_ctrl, rule_ctrl, set_ctrl
from ...app.timefmt import auto_unit, dur
from ...i18n import T, TEXTS
from .. import cache
from .. import ff as ffmod
from ..cache import pidconl_sim_full, robustness
from ..charts import REPORT, hidden, mkfig, show, style, tr
from ..theme import C_MV, C_SET1, C_SET2, C_SP, _c_dist
from ..layout import section, workspace
from ..widgets import fmt, model_name, notes_text, num, seg, sel, sld
from . import apc
from ..table import table
from ..kit import card, head, level, lrow, tiles
from ..kit import q as q_

ss = st.session_state
SCOLS = [0.8, 1.0, 1.15, 1.15]          # karta Návrh a sady: název | Návrh | Set 1 | Set 2


def render_block(ctx):
    """
    Rozložení záložky Ladění (jako desktop): vlevo graf scénáře / frekvenční analýza, vpravo panel – výpočet,
    1 scénář, 2 návrh, 3 sady, ověření, doporučení D, proces a ventil, blok PIDConL. Blok se vykreslí hned
    (ctx.base_ctrl potřebují i ostatní záložky), ostatní sekce vyplní render().
    """
    with ctx.tabs["tuning"]:
        ctx.gph["tuning"] = True
        ws = workspace()
        with ws.side:
            ws.top = st.container()
        ctx.tun = ws
        # pořadí karet panelu jako v návrhu: metoda → návrh a sady → scénář → robustnost → blok, historie …
        ws.sug = section(ws.side, T("tn_sec_method"), "tun_sug", expanded=True)
        ws.sets = section(ws.side, T("tn_sec_sets"), "tun_sets", expanded=True)
        ws.scen = section(ws.side, T("tn_sec_scen"), "tun_scen", expanded=True)
        ws.verify = section(ws.side, T("tn_sec_rob"), "tun_verify", expanded=True)
        blk = section(ws.side, T("tn_blk"), "tun_block")
        ws.hist = section(ws.side, T("dk_sec_hist"), "tun_hist")
        ws.dadv = section(ws.side, T("d_title"), "tun_d")
        ws.plant = section(ws.side, T("plant_title"), "tun_plant")
        ws.cta = ws.side.container(key="pid_cta_live")
        with blk:
            _norm_section(ctx)
            st.markdown(f"**{T('sb_block')}**")
            q = st.columns(2)
            ctx.samp = num(T("sampletime"), "samp", 1.0, q[0], min_value=0.001, help=T("sampletime_help"))
            ctx.diffgain = num("DiffGain", "diffgain", 5.0, q[1], min_value=0.1, help=T("diffgain_help"))
            q = st.columns(2)
            db_e = num(T("deadband"), "db", 0.0, q[0], min_value=0.0, help=T("h_deadband"))
            db_mode = q[1].selectbox(T("db_mode"), ["cont", "step"], format_func=lambda x: T("db_" + x),
                                     help=T("db_mode_help"), key="db_mode")
            q = st.columns(2)
            ctx.mvl_lo = num("MV_LoLim", "mvl_lo", ctx.mv_lo, q[0], help=T("h_mvlim"))
            ctx.mvl_hi = num("MV_HiLim", "mvl_hi", ctx.mv_hi, q[1], help=T("h_mvlim"))
            if "propfac" not in ss:      # starší projekty: přepínač „P ve zpětné vazbě“ → PropFacSP 0 / 1
                ss["propfac"] = 0.0 if ss.get("pfb") else 1.0
            q = st.columns(2, vertical_alignment="bottom")
            ctx.propfac = num("PropFacSP", "propfac", 1.0, q[0], min_value=0.0, max_value=1.0, step=0.1,
                              format="%.2g", help=T("pfb_help"))
            if "dfb" not in ss:
                ss["dfb"] = True
            ctx.dfb = q[1].toggle(T("dfb"), key="dfb", help=T("h_dfb"))
            st.markdown(f"**{T('blk_elems')}**", help=T("h_blk_elems"))
            ctx.pvfilt = num(T("pvfilt"), "pvfilt", 0.0, min_value=0.0, help=T("h_pvfilt"))
            q = st.columns(2)
            mvrate_e = num(T("mvrate", u=ctx.u_mv or "MV"), "mvrate", 0.0, q[0], min_value=0.0, format="%.4g",
                           help=T("h_mvrate"))
            sprate_e = num(T("sprate", u=ctx.u_pv or "PV"), "sprate", 0.0, q[1], min_value=0.0, format="%.4g",
                           help=T("h_sprate"))
        if not ctx.norm_ok:
            ws.top.error(T("err_range"), icon=":material/error:")
    ctx.base_ctrl = block_ctrl(ctx, ctx.samp, ctx.diffgain, ctx.propfac, ctx.dfb, db_e, db_mode, ctx.mvl_lo, ctx.mvl_hi,
                               ctx.pvfilt, mvrate_e, sprate_e)
    ctx.block_summary = T("blk_summary", s=f"{ctx.samp:g}", dg=f"{ctx.diffgain:g}", p=f"{ctx.propfac:g}",
                          d="✓" if ctx.dfb else "✗", g=f"{ss.get('set1_gain', 1.0):.4g}",
                          ti=f"{ss.get('set1_ti', 100.0):.4g}", td=f"{ss.get('set1_td', 0.0):.4g}")


def _reset_editor(sdf_key, edkey):
    """Po přepsání událostí scénáře (ss[sdf_key]) zahodit stav editoru, aby převzal nové řádky."""
    for k_ in (edkey, f"{edkey}|init", f"{sdf_key}|last"):
        ss.pop(k_, None)


def _range_set(k):
    """Rozsah zadal uživatel (i 0–100 podle bloku v PLC) – odhad z dat ho už nepřepíše."""
    ss[f"{k}_rng_user"] = True


def _sim_unit_set():
    """Jednotku délky simulace zvolil uživatel – dál se nemění podle délky."""
    ss["sim_len_u_set"] = True


def _step_cols(st_):
    """Sloupce odezvy na změnu SP (doba do 90 %, překmit, ustálení) – prázdné bez změny SP ve scénáři."""
    if not st_:
        return {}
    return {T("kpi_t90"): dur(st_["t90"]), T("kpi_over"): f"{st_['over']:.3g}", T("kpi_settle"): dur(st_["settle"])}


def _norm_section(ctx):
    """
    Rozsah regulátoru NormPV / NormMV – nastavení bloku PIDConL (Gain je bezrozměrný: odchylka v % NormPV, MV v % NormMV).
    Data zůstávají v reálných jednotkách; rozsah se zadává podle bloku, ne podle dat. Hodnoty už použila záložka Data
    (přečetla je ze session state), tady jsou pole a kontroly.
    """
    st.markdown(f"**{T('sb_norm')}**", help=T("h_norm"))
    n = st.columns(2) + st.columns(2)            # 2 × 2 – do úzkého panelu se čtyři pole vedle sebe nevejdou
    num("NormPV Low", "pv_lo", 0.0, n[0], help=T("h_normpv"), on_change=_range_set, args=("pv",))
    num("NormPV High", "pv_hi", 100.0, n[1], help=T("h_normpv"), on_change=_range_set, args=("pv",))
    num("NormMV Low", "mv_lo", 0.0, n[2], help=T("h_normmv"), on_change=_range_set, args=("mv",))
    num("NormMV High", "mv_hi", 100.0, n[3], help=T("h_normmv"), on_change=_range_set, args=("mv",))
    if not ctx.norm_ok:
        st.error(T("err_range"), icon=":material/error:")
        return
    pmin, pmax = float(np.nanmin(ctx.pv_e)), float(np.nanmax(ctx.pv_e))
    mmin, mmax = float(np.nanmin(ctx.mv_e)), float(np.nanmax(ctx.mv_e))
    top = ctx.tun.top            # upozornění i při sbaleném bloku
    tp, tm = 0.005 * ctx.PR, 0.005 * ctx.MR    # drobný přesah (MV −0,004 %) není chyba rozsahu
    if pmin < ctx.pv_lo - tp or pmax > ctx.pv_hi + tp or mmin < ctx.mv_lo - tm or mmax > ctx.mv_hi + tm:
        top.warning(T("norm_out", pv=f"{pmin:.4g}–{pmax:.4g}", mv=f"{mmin:.4g}–{mmax:.4g}"), icon=":material/warning:")
    else:
        st.caption(T("blk_data_note", pv=f"{pmin:.4g}–{pmax:.4g}", mv=f"{mmin:.4g}–{mmax:.4g}"))


def _sig(*parts):
    """Otisk vstupů návrhu – změna = výsledek je neaktuální."""
    def r(v):
        if isinstance(v, float):
            return float(f"{v:.6g}")
        if isinstance(v, (list, tuple)):
            return tuple(r(x) for x in v)
        if isinstance(v, dict):
            return tuple(sorted((k, r(x)) for k, x in v.items() if k not in ("FF", "FF_LL")))
        return v
    return repr(r(list(parts)))


def _scen_kind(c_d, sdf_key):
    """Druh scénáře (jako desktop): skok SP, porucha na vstupu / výstupu, SP + porucha, měřená porucha, přehrání, vlastní."""
    kinds = [k for k in scenario.PRESETS if k not in ("meas", "replay") or c_d]
    cur = scenario.preset_kind(ss.get("scen_kind"), ss.get("scen2"), sdf_key in ss, bool(c_d))
    return kinds, cur


def render(ctx):
    """
    Záložka Ladění: metoda → návrh → sady v PLC → scénář → simulace a ukazatele. Jednotlivé karty kreslí kroky
    _tn_* v tomto pořadí; mezivýsledky si předávají ve jmenném prostoru s (vstupy z ctx, výstupy kroků).
    """
    ws = ctx.tun
    plant, set1_ctrl, set2_ctrl = ctx.plant, ctx.set1_ctrl, ctx.set2_ctrl
    with ctx.tabs["tuning"]:
        if ctx.model is None:
            ws.main.info(T("need_model"), icon=":material/arrow_back:")
        else:
            s = SimpleNamespace(ctx=ctx, ws=ws, **{k: getattr(ctx, k) for k in _CTX_KEYS})
            s.mcode, s.p, s.pdl = ctx.model
            for step in _STEPS:
                # grafy a výstupy Ladění ostatní záložky nepotřebují → jen při otevřené záložce (nebo pro report)
                if step in (_tn_views, _tn_outputs) and not (ctx.full or ctx.active_tab == "tuning"):
                    continue
                step(s)
            plant, set1_ctrl, set2_ctrl = s.plant, s.set1_ctrl, s.set2_ctrl
    ctx.plant = plant
    ctx.set1_ctrl = set1_ctrl
    ctx.set2_ctrl = set2_ctrl


# vstupy kroků z kontextu běhu
_CTX_KEYS = ("EM", "EP", "H", "MR", "PR", "base_ctrl", "c_d", "d_id", "diffgain", "has_sp", "lab_mv", "lab_pv",
             "lab_t", "model_stic", "mv_hi", "mv_id", "mv_lo", "pv_hi", "pv_id", "pv_lo", "samp", "sel_mask",
             "sigma_pv", "sp", "ts_id", "u_mv", "u_pv", "unc_models")


def _tn_toolbar(s):
    """Lišta pohledu (scénář / frekvence / všechny metody), model, tip na APC; metoda převzatá z tabulky metod."""
    ctx, mcode, p, samp, ws = s.ctx, s.mcode, s.p, s.samp, s.ws
    with ws.main:
        bar = card("tun_bar")
        m_view = st.container()
        m_methods = st.container()
        m_below = st.container()
    with bar:          # pohled (scénář / frekvence / všechny metody), co se srovnává, model a tip na APC
        b1, b2 = st.columns([1.3, 1], vertical_alignment="center")
        view = seg(b1, T("tn_view"), ["time", "freq", "all"], "time", "tun_view",
                   format_func=lambda x: T("tn_view_" + x), label_visibility="collapsed") or "time"
        cmp_ph = b2.empty()
        st.caption(f"{model_name(mcode)} · " + ", ".join(f"{n} = {(0.0 if abs(v) < 1e-9 else v):.4g}"
                                                          for n, v in zip(MODELS[mcode]["params"], p))
                   + " · " + T("samp_note", s=f"{samp:g}", h=f"{samp / 2:g}"))
        apc.tuning_hint(ctx)   # odkaz na záložku APC, když by smyčce pomohla pokročilá struktura
    p_eff = tun.p_eff(p, samp)
    methods = tun.methods(mcode, p)
    mkey = f"method|{mcode}"
    if "pending_tune" in ss:
        m_, c_, cr_ = ss.pop("pending_tune")
        if m_ in methods:
            ss[mkey], ss["ctype"] = m_, c_
            if cr_:
                ss["opt_crit"] = cr_
    s.cmp_ph, s.m_below, s.m_methods, s.m_view, s.methods, s.mkey = cmp_ph, m_below, m_methods, m_view, methods, mkey
    s.p_eff, s.view = p_eff, view


def _tn_d_advice(s):
    """Doporučení D složky; modely pro robustní optimalizaci a řešiče."""
    PR, mcode, p, p_eff, sigma_pv, u_pv = s.PR, s.mcode, s.p, s.p_eff, s.sigma_pv, s.u_pv
    unc_models, ws = s.unc_models, s.ws
    # ---- doporučení D složky
    adv = d_advice(mcode, p_eff)
    with ws.dadv:
        if adv.get("tau") is not None:
            st.metric(T("tau_label"), f"{adv['tau']:.2f}", help=T("tau_help"))
        elif adv.get("ratio") is not None:
            st.metric(T("ratio_label"), f"{adv['ratio']:.2f}", help=T("ratio_help"))
        st.markdown(f"**{adv['rec']}** — {T(adv['key'])}")
        if sigma_pv > 0:
            st.caption(T("noise_note", s=f"{sigma_pv * PR / 100:.3g}", u=u_pv or "PV"))

    robust_set = tun.robust_models(p, unc_models, ss.get("opt_robust"))
    solvers = SimpleNamespace(opt_migo=cache.opt_migo, opt_time=cache.opt_time, opt_scenario=cache.opt_scenario)
    s.adv, s.robust_set, s.solvers = adv, robust_set, solvers


def _tn_method(s):
    """Karta Metoda ladění: metoda, typ regulátoru, parametry metody, výpočet návrhu (pravidla samy, optimalizace na tlačítko)."""
    MR, PR, base_ctrl, cmp_ph, diffgain, mcode = s.MR, s.PR, s.base_ctrl, s.cmp_ph, s.diffgain, s.mcode
    methods, mkey, p, pdl, robust_set, samp = s.methods, s.mkey, s.p, s.pdl, s.robust_set, s.samp
    sigma_pv, solvers, u_mv, u_pv, unc_models, ws = s.sigma_pv, s.solvers, s.u_mv, s.u_pv, s.unc_models, s.ws
    # ---- 2 · návrh (počítá se na tlačítko Vypočítat)
    with ws.sug:
        method = sel(lrow(T("method"), T("method_help")), T("method"), methods,
                     methods.index(tun.DEFAULT_METHOD) if tun.DEFAULT_METHOD in methods else 0, mkey,
                     format_func=lambda x: T("m_" + x), label_visibility="collapsed")
        ctype = seg(lrow(T("ctrl_type"), T("h_ctype")), T("ctrl_type"), ["PI", "PID"], "PI", "ctype",
                    label_visibility="collapsed") or "PI"
        avg, tc, ms_max = None, None, 1.6
        crit, tgt = ss.get("opt_crit") or tun.DEFAULT_CRIT, ss.get("opt_target") or tun.DEFAULT_TARGET
        ovs_lim = (ss.get("opt_ovs") if ss.get("opt_ovs") is not None else 2) / 100
        st.caption(T("mdesc_" + method))
        if method == "AVG":
            a1, a2 = st.columns(2)
            dpv = num(T("avg_dpv", u=u_pv or "PV"), "avg_dpv", round(0.1 * PR, 3), a1, min_value=1e-9,
                      help=T("h_avg_dpv"))
            dmv = num(T("avg_dmv", u=u_mv or "MV"), "avg_dmv", round(0.1 * MR, 3), a2, min_value=1e-9,
                      help=T("avg_dmv_help"))
            avg = (dpv / PR * 100, dmv / MR * 100)
        elif method == "OPT":
            crits_ = ["MIGO", "IAE", "ISE", "ITAE", "OVS"]
            crit = sel(lrow(T("opt_crit"), T("h_opt_crit")), T("opt_crit"), crits_, crits_.index(tun.DEFAULT_CRIT),
                       "opt_crit", format_func=lambda x: T("crit_" + x), label_visibility="collapsed")
            st.caption(T("cdesc_" + crit))
            if crit != "MIGO":
                tgts_ = ["scen", "dist", "sp", "both"]
                tgt = sel(lrow(T("opt_target"), T("h_opt_target")), T("opt_target"), tgts_,
                          tgts_.index(tun.DEFAULT_TARGET), "opt_target", format_func=lambda x: T("tgt_" + x),
                          label_visibility="collapsed")
                if crit == "OVS":
                    ovs_lim = (seg(lrow(T("opt_ovs"), T("h_opt_ovs")), T("opt_ovs"), [0, 2, 5, 10], 2, "opt_ovs",
                                   format_func=lambda x: f"{x} %", label_visibility="collapsed") or 0) / 100
            ms_max = seg(lrow(T("opt_ms"), T("opt_ms_help")), T("opt_ms"), [1.4, 1.6, 1.8, 2.0], 1.6, "opt_ms",
                         format_func=lambda x: f"{x:.1f}", label_visibility="collapsed") or 1.6
            if ctype == "PID":
                num(T("opt_noise", u=u_mv or "MV"), "opt_noise", round(0.01 * MR, 4), min_value=0.0,
                    format="%.4g", help=T("opt_noise_help"))
            st.toggle(T("opt_robust"), key="opt_robust",
                      help=T("h_opt_robust_bs") if unc_models else T("h_opt_robust_corner"))
        elif method in ("SIMC", "iSIMC", "Lambda"):
            tc0 = default_tc(mcode, p, samp, method, ctype, diffgain)
            tc = sld(st, T("tc"), float(max(0.05 * tc0, 1e-3)), float(10 * tc0), float(tc0),
                     f"tc|{mcode}|{method}|{ctype}", help=T("tc_help"))
        sug_box = st.container()
    hf_max = tun.hf_max(ss.get("opt_noise", 0.01 * MR), MR, sigma_pv)  # omezení šumu MV (jen PID)
    sb = ss.get("scen_built") if (ss.get("scen_built") or {}).get("mcode") == mcode else None
    scen_dep = method == "OPT" and crit != "MIGO" and tgt == "scen"
    req = tun.Request(method, ctype, tc, avg, ms_max, hf_max, crit, tgt, ovs_lim)
    sig_now = _sig(mcode, list(p), [list(x) for x in pdl], method, ctype, tc, avg, ms_max, hf_max, crit, tgt,
                   ovs_lim, bool(ss.get("opt_robust")), base_ctrl,
                   ss.get("scen_sig") if scen_dep else None)
    last = ss.get("sug_last") if (ss.get("sug_last") or {}).get("mcode") == mcode else None
    with ws.sug:
        calc = st.button(T("dk_calc"), key="g_calc", type="primary" if method == "OPT" else "secondary",
                         width="stretch", help=T("dk_calc_help"))
    # rychlé metody (pravidla) se přepočítají samy; optimalizace (sekundy) až na tlačítko
    auto = method != "OPT" and (last is None or last["sig"] != sig_now)
    if calc or auto or ss.pop("auto_calc", False):
        try:
            with ws.sug, st.spinner(T("optimizing")) if method == "OPT" else nullcontext():
                res_ = tun.suggest(mcode, p, pdl, base_ctrl, req, robust_set, sb, solvers)
            ss["sug_last"] = dict(sig=sig_now, sug=res_, mcode=mcode,
                                  label=T("m_" + method) + (f" · {T('crit_' + crit)}" if method == "OPT" else ""),
                                  ctype=ctype, t=time.strftime("%H:%M:%S"))
        except Exception as ex:
            ws.sug.error(T(str(ex)))
    last = ss.get("sug_last") if (ss.get("sug_last") or {}).get("mcode") == mcode else None
    sug = last["sug"] if last else None
    if last is None:
        ws.sug.caption(T("dk_calc_hint"))
    elif last["sig"] != sig_now:
        ws.sug.warning(T("web_stale"), icon=":material/update:")
    else:
        ws.sug.caption(":material/check_circle: " + T("web_calc_done", t=last["t"]))
    with sug_box:
        if sug is not None:
            if sug["notes"]:
                st.info(notes_text(sug["notes"]), icon=":material/lightbulb:")
            if sug["Kc"] < 0:
                st.warning(T("warn_neg_gain"), icon=":material/swap_vert:")
        if "fit" in ss and mcode in ss.fit["res"] and ss.fit["res"][mcode]["fit"] < 70:
            st.warning(T("warn_low_fit"), icon=":material/warning:")
    cmp_ph.markdown(f"<div class='pid-sub' style='text-align:right'>{T('tn_cmp_line', a=T('dk_suggest'), b=T('set_2'))}"
                    "</div>", unsafe_allow_html=True)
    s.crit, s.ctype, s.hf_max, s.last, s.method, s.sug = crit, ctype, hf_max, last, method, sug
    s.tc = tc


def _tn_methods(s):
    """Karta Všechny metody pro tento model (klepnutím se metoda převezme do Návrhu)."""
    MR, PR, base_ctrl, crit, ctype, hf_max = s.MR, s.PR, s.base_ctrl, s.crit, s.ctype, s.hf_max
    m_methods, mcode, method, p, pdl, robust_set = s.m_methods, s.mcode, s.method, s.p, s.pdl, s.robust_set
    sigma_pv, solvers, u_mv, view = s.sigma_pv, s.solvers, s.u_mv, s.view
    # ---- všechny metody pro tento model (karta pod grafem; optimalizace trvají → počítá se na tlačítko)
    if view in ("time", "all"):
        with m_methods, card("tun_methods"):
            head(T("tn_methods"), note=T("tn_methods_note"))
            if view == "all":
                ss["cmp_open"] = True
            if not ss.get("cmp_open"):
                st.button(T("tn_methods_run"), key="g_cmp_run", icon=":material/leaderboard:",
                          on_click=lambda: ss.__setitem__("cmp_open", True))
                st.caption(T("cmp_help"))
            else:
                avg_c = (ss.get("avg_dpv", 1) / PR * 100, ss.get("avg_dmv", 1) / MR * 100) if "avg_dpv" in ss else None
                req_c = tun.Request(ms=ss.get("opt_ms") or 1.6, hf=hf_max, target=ss.get("opt_target") or "both",
                                    ovs=(ss.get("opt_ovs") if ss.get("opt_ovs") is not None else 2) / 100)
                with st.spinner(T("optimizing")):
                    cmp_ = tun.compare(mcode, p, pdl, base_ctrl, req_c, avg_c, sigma_pv, robust_set, solvers,
                                       robustness)
                rows, cur = [], []
                for q in cmp_:
                    rows.append({T("col_method"): T("m_" + q["method"]) + (f" · {T('crit_' + q['crit'])}" if q["crit"] else ""),
                                 T("ctrl_type"): q["ctype"], "Gain": float(f"{q['Kc']:.4g}"),
                                 "TI [s]": float(f"{q['Ti']:.4g}"), "TD [s]": float(f"{q['Td']:.4g}"),
                                 "Ms": round(q["Ms"], 2) if q["Ms"] is not None else None,
                                 T("iae_load"): float(f"{q['iae_load']:.4g}") if q["iae_load"] is not None else None,
                                 T("iae_sp"): float(f"{q['iae_sp']:.4g}") if q["iae_sp"] is not None else None,
                                 T("ovs_col"): round(q["ovs"], 1) if q["ovs"] is not None else None,
                                 T("noise_col", u=u_mv or "MV"): (float(f"{q['noise'] * MR / 100:.3g}")
                                                                  if q["noise"] is not None else None),
                                 T("use_col"): T("use_" + (q["crit"] or q["method"]))})
                    cur.append("cur" if (q["method"], q["ctype"]) == (method, ctype) and
                               (method != "OPT" or q["crit"] == crit) else "")
                ev_c = table(pd.DataFrame(rows), key=f"cmp|{mcode}", select=True, row_class=cur)
                sel_rows = ev_c.selection.rows
                if sel_rows and ss.get("_cmp_last") != (mcode, sel_rows[0]):
                    ss["_cmp_last"] = (mcode, sel_rows[0])        # klepnutí = metoda do Návrhu
                    q = cmp_[sel_rows[0]]
                    ss["pending_tune"] = (q["method"], q["ctype"], q["crit"])
                    ss["auto_calc"] = True
                    st.rerun()
                st.caption(T("cmp_help"))


def _tn_sets(s):
    """Karta Návrh a sady v PLC: Gain / TI / TD pro Návrh, Set 1, Set 2; zápis návrhu do sad."""
    base_ctrl, ctx, last, mcode, p, sigma_pv = s.base_ctrl, s.ctx, s.last, s.mcode, s.p, s.sigma_pv
    sug, unc_models, ws = s.sug, s.unc_models, s.ws
    # ---- návrh a sady v PLC: řádky Gain / TI / TD, sloupce Návrh | Set 1 | Set 2
    with ws.sets:
        hc = st.columns(SCOLS, vertical_alignment="center")
        for c_, lbl_, h_ in ((hc[1], T("dk_suggest"), T("dk_calc_help")), (hc[2], T("set_1"), T("h_set_1")),
                             (hc[3], T("set_2"), T("h_set_2"))):
            c_.markdown(f"<div class='pid-plab' style='justify-content:flex-end' title='{html.escape(h_, quote=True)}'>"
                        f"{lbl_}</div>", unsafe_allow_html=True)
        vals = {}
        for lbl, k, sk, mn, hk in (("Gain", "gain", "Kc", None, "h_gain"), ("TI [s]", "ti", "Ti", 0.0, "h_ti"),
                                   ("TD [s]", "td", "Td", 0.0, "h_td")):
            c = st.columns(SCOLS, vertical_alignment="center")
            c[0].markdown(f"<div class='pid-plab'>{lbl}{q_(T(hk))}</div>", unsafe_allow_html=True)
            c[1].markdown(f"<div class='pid-big-val' style='text-align:right'>{fmt(sug[sk]) if sug else '—'}</div>",
                          unsafe_allow_html=True)
            d1 = {"gain": 1.0, "ti": 100.0, "td": 0.0}[k]
            for n_ in (1, 2):
                kw_ = {} if mn is None else dict(min_value=mn)
                vals[(n_, k)] = num(lbl, f"set{n_}_{k}", ss.get(f"set{n_}_{k}", sug[sk] if (sug and n_ == 2) else d1),
                                    c[1 + n_], format="%.5g", label_visibility="collapsed", **kw_)
        set1_gain, set1_ti, set1_td = vals[(1, "gain")], vals[(1, "ti")], vals[(1, "td")]
        set2_gain, set2_ti, set2_td = vals[(2, "gain")], vals[(2, "ti")], vals[(2, "td")]
        b1, b2 = st.columns(2)
        for n_, b_ in ((2, b1), (1, b2)):      # zápis v callbacku – pole sad jsou už vykreslená
            b_.button(T(f"tn_write_s{n_}"), key=f"g_write_s{n_}", width="stretch", disabled=sug is None,
                      type="primary" if n_ == 2 else "secondary", on_click=_write_set, args=(n_, sug, last, mcode))
        st.caption(T("tn_sets_note"))
        set1_ctrl = set_ctrl(base_ctrl, set1_gain, set1_ti, set1_td)
        set2_ctrl = set_ctrl(base_ctrl, set2_gain, set2_ti, set2_td)
        rc = tun.set_metrics(mcode, p, set1_ctrl, sigma_pv, unc_models, robustness)
        rn = tun.set_metrics(mcode, p, set2_ctrl, sigma_pv, unc_models, robustness)
        ctx.PROG["tune"] = 2 if not rn["stable"] else (0 if rn["Ms"] <= 2.0 else 1)
        set1_placeholder = tun.is_placeholder(set1_ctrl["Gain"], set1_ctrl["TI"], set1_ctrl.get("TD", 0.0))
        set2_placeholder = tun.is_placeholder(set2_ctrl["Gain"], set2_ctrl["TI"], set2_ctrl.get("TD", 0.0))
        for nm, r in ((T("set_1"), rc), (T("set_2"), rn)):
            if not r["stable"]:
                if nm == T("set_1") and set1_placeholder:    # výchozí zástupné hodnoty, ne skutečné nastavení
                    st.info(T("set1_placeholder"), icon=":material/edit:")
                elif nm == T("set_2") and set2_placeholder:
                    st.info(T("set2_placeholder"), icon=":material/calculate:")
                else:
                    st.error(T("err_unstable", n=nm), icon=":material/error:")
    s.rc, s.rn, s.set1_ctrl, s.set1_gain, s.set1_td, s.set1_ti = rc, rn, set1_ctrl, set1_gain, set1_td, set1_ti
    s.set2_ctrl, s.set2_gain, s.set2_td, s.set2_ti = set2_ctrl, set2_gain, set2_td, set2_ti


def _tn_robust(s):
    """Karta Robustnost: dlaždice Ms / GM / PM a tabulka sad."""
    MR, base_ctrl, mcode, p, rc, rn = s.MR, s.base_ctrl, s.mcode, s.p, s.rc, s.rn
    set1_ctrl, set1_gain, set1_td, set2_ctrl = s.set1_ctrl, s.set1_gain, s.set1_td, s.set2_ctrl
    set2_gain, set2_td = s.set2_gain, s.set2_td
    sigma_pv, sug, u_mv, unc_models, ws = s.sigma_pv, s.sug, s.u_mv, s.unc_models, s.ws
    # ---- robustnost: dlaždice Ms / GM / PM (Návrh, pod tím Set 2), tabulka sad
    with ws.verify:
        rs = (tun.set_metrics(mcode, p, set_ctrl(base_ctrl, sug["Kc"], sug["Ti"], sug["Td"]), sigma_pv,
                              unc_models, robustness) if sug is not None else None)
        main_, ref_, ref_n = (rs, rn, T("set_2")) if rs is not None else (rn, rc, T("set_1"))

        def _v(r_, k_, d_=2):
            return fmt(r_[k_], d_ + 1) if r_ and r_["stable"] else "—"
        tiles([("Ms", _v(main_, "Ms"), f"{ref_n}: {_v(ref_, 'Ms')}",
                level(main_["Ms"] if main_["stable"] else 99, 1.8, 2.0)),
               ("GM", _v(main_, "GM"), f"{ref_n}: {_v(ref_, 'GM')}",
                level(main_["GM"] if main_["stable"] else 0, 2.0, 1.7, lower_better=False)),
               ("PM", _v(main_, "PM") + ("°" if main_["stable"] else ""), f"{ref_n}: {_v(ref_, 'PM')}°",
                level(main_["PM"] if main_["stable"] else 0, 45, 30, lower_better=False))])
        cols_ = {T("set_1"): rc, T("set_2"): rn, **({T("dk_suggest"): rs} if rs is not None else {})}
        tbl = pd.DataFrame({n_: [fmt(r_["Ms"], 3), fmt(r_["GM"], 3), fmt(r_["PM"], 3),
                                 fmt(r_["noise"] * MR / 100, 3)] + ([fmt(r_["Ms_worst"], 3)] if unc_models else [])
                            for n_, r_ in cols_.items()},
                           index=[T("ms"), T("gm"), T("pm"), T("noise_col", u=u_mv or "MV")]
                           + ([T("ms_worst")] if unc_models else []))
        table(tbl, key="tun_rob")
        REPORT["tables"].append((T("rep_tab_tuning"), pd.concat([pd.DataFrame(
            {T("set_1"): [fmt(set1_gain), fmt(set1_ctrl["TI"]), fmt(set1_td)],
             T("set_2"): [fmt(set2_gain), fmt(set2_ctrl["TI"]), fmt(set2_td)]},
            index=["Gain", "TI [s]", "TD [s]"]), tbl[[T("set_1"), T("set_2")]]])))


def _tn_history(s):
    """Historie návrhů (klepnutím na řádek a tlačítkem zpět do sady)."""
    ws = s.ws
    # ---- historie ladění
    with ws.hist:
        hist = [e for e in (ss.get("tune_hist") or []) if isinstance(e, dict) and "Kc" in e]
        if not hist:
            st.caption(T("dk_hist_help"))
        else:
            hdf = pd.DataFrame([{T("dk_hist_time"): e.get("time"), T("dk_hist_set"): e.get("set"),
                                 T("method"): e.get("method"), "Gain": e["Kc"], "TI": e["Ti"], "TD": e["Td"]}
                                for e in hist])
            ev_h = table(hdf, hide_index=True, width="stretch", select=True,
                                selection_mode="single-row", key="hist_tab")
            rows_h = getattr(getattr(ev_h, "selection", None), "rows", [])
            if rows_h:
                e = hist[rows_h[0]]
                h1, h2 = st.columns(2)
                for n_, b_ in ((1, h1), (2, h2)):
                    b_.button(T(f"dk_hist_s{n_}"), key=f"g_hist_s{n_}", width="stretch", on_click=_hist_set,
                              args=(n_, e))


def _tn_feedforward(s):
    """Dopředná vazba z APC: stav a promítnutí do sad pro simulaci."""
    c_d, mcode, p, pdl, set1_ctrl, set2_ctrl = s.c_d, s.mcode, s.p, s.pdl, s.set1_ctrl, s.set2_ctrl
    ws = s.ws
    # dopředná vazba se nastavuje v APC › Dopředná vazba; tady jen stav a promítnutí do simulací
    ffd = ffmod.design(mcode, p, pdl)
    ffmod.save_state(ffd)
    ff, ffll = ffmod.to_ctrl(ffd)
    if pdl:
        on = [f"{dn} ({T('ff_dyn_s') if d['dyn'] else T('ff_static_s')})" for dn, d in zip(c_d, ffd) if d["use"]]
        with ws.sets:
            st.caption(":material/fast_forward: " + (T("ff_status_on", l=", ".join(on)) if on
                                                     else T("ff_status_off")))
            st.button(T("ff_open"), key="g_ff_open", on_click=apc.guide.goto,
                      kwargs=dict(tab="apc", kind="ff"), type="tertiary")
    set1_ctrl["FF"], set1_ctrl["FF_LL"] = ff, ffll
    set2_ctrl["FF"], set2_ctrl["FF_LL"] = ff, ffll
    ss.set2_ctrl = set2_ctrl
    s.ff, s.ffll = ff, ffll


def _tn_scenario(s):
    """Karta Scénář simulace: druh, délka, SP z → na, velikost poruch; přepínače ověření robustnosti."""
    EP, MR, PR, base_ctrl, c_d, ctx = s.EP, s.MR, s.PR, s.base_ctrl, s.c_d, s.ctx
    ctype, diffgain, ff, has_sp, mcode, p = s.ctype, s.diffgain, s.ff, s.has_sp, s.mcode, s.p
    pv_id, samp, sel_mask, set1_ctrl, set2_ctrl, sp = s.pv_id, s.samp, s.sel_mask, s.set1_ctrl, s.set2_ctrl, s.sp
    tc, ts_id, u_mv, u_pv, unc_models, ws = s.tc, s.ts_id, s.u_mv, s.u_pv, s.unc_models, s.ws
    # ---- 1 · scénář
    sdf_key = f"scen_df|{mcode}|{len(c_d)}"
    edkey = f"scen_ed|{sdf_key}|{ss.lang}"
    kinds, kind0 = _scen_kind(c_d, sdf_key)
    sp_amp_e, d_in, d_pv = 0.0, 0.0, 0.0          # přehrání záznamu: bez SP skoku a umělých poruch
    with ws.scen:
        kind = sel(lrow(T("dk_sc_kind"), T("dk_sc_kind_help")), T("dk_sc_kind"), kinds, kinds.index(kind0),
                   "scen_kind", format_func=lambda x: T("dk_sc_" + x), label_visibility="collapsed")
        ss["scen2"] = "replay" if kind == "replay" else "custom"
        st.caption(T("dk_sc_note_" + kind))
        with st.popover(T("sc_where_btn"), icon=":material/help:", width="stretch"):
            st.markdown(T("sc_where_help"))
        T_char = scenario.t_char(mcode, p, tc, samp)
        sp_data = float(EP(np.nanmedian(sp[sel_mask]) if has_sp else pv_id[0]))
        if kind != "replay":
            sim_l1, sim_l2 = st.columns([1.4, 1], vertical_alignment="bottom")
            # i návrh (sady mohou mít ještě výchozí hodnoty) – SIMC, ne zvolená metoda: optimalizace na scénáři
            # závisí na délce simulace a délka na jejím výsledku by se navzájem posouvaly (optimalizace stále znovu)
            r_ = tune(mcode, p, "SIMC", default_tc(mcode, p, samp, "SIMC", ctype, diffgain), ctype, samp)
            prop_ctrl = rule_ctrl(base_ctrl, r_)
            t_auto, auto_src = scenario.auto_length(mcode, p, (set1_ctrl, set2_ctrl, prop_ctrl), T_char, samp, ts_id,
                                                     settling=cache.settling_time)
            if not ss.get("sim_len_u_set"):   # dokud ji uživatel nezvolí: s u rychlých procesů, min / h u pomalých
                ss["sim_len_u"] = auto_unit(t_auto)
            T_end_unit = sel(sim_l2, T("time_unit"), ["s", "min", "h"], 0, "sim_len_u", on_change=_sim_unit_set)
            mult = {"s": 1.0, "min": 60.0, "h": 3600.0}[T_end_unit]
            if "sim_len_auto" not in ss:
                ss["sim_len_auto"] = True
            auto_len = st.toggle(T("sim_len_auto"), key="sim_len_auto", help=T("h_sim_len_auto"))
            tend_key = f"tend_r|{mcode}"
            if auto_len or tend_key not in ss:
                ss[tend_key] = float(f"{t_auto / mult:.4g}")
            T_end_raw = num(T("sim_len"), tend_key, t_auto / mult, sim_l1, min_value=samp * 10 / mult,
                            help=T("h_sim_len"), disabled=auto_len)
            T_end = T_end_raw * mult
            if auto_len:
                st.caption(T("sim_len_src_" + auto_src))
            # jiná délka simulace → časy vlastních událostí se poměrně přepočítají (zůstanou na stejném místě)
            tk_ = f"{sdf_key}|tend"
            t_prev = ss.get(tk_)
            ss[tk_] = T_end
            if kind == "custom" and sdf_key in ss and t_prev and abs(T_end / t_prev - 1) > 0.02:
                ss[sdf_key] = scenario.rescale_times(ss.get(f"{sdf_key}|last", ss[sdf_key]), T_end / t_prev)
                _reset_editor(sdf_key, edkey)
                st.rerun()
            f1_, f2_ = st.columns(2)
            sp_from = num(T("sim_sp_from", u=u_pv or "PV"), f"sim_sp0|{ctx.fname}", float(f"{sp_data:.5g}"), f1_,
                          format="%.5g", help=T("h_sim_sp_from"))
            if kind in ("sp", "sp_in", "custom"):
                sp_to = num(T("sim_sp_to", u=u_pv or "PV"), f"sim_sp1|{ctx.fname}",
                            float(f"{sp_data + 0.05 * PR:.5g}"), f2_, format="%.5g", help=T("h_sim_sp_to"))
            else:
                sp_to = ss.get(f"sim_sp1|{ctx.fname}", sp_from)
            d_in = num(T("dk_sc_d_in", u=u_mv or "MV"), "scen_d_in", round(0.05 * MR, 4), format="%.4g") \
                if kind in ("in", "sp_in") else float(ss.get("scen_d_in") or 0.05 * MR)
            d_pv = num(T("dk_sc_d_pv", u=u_pv or "PV"), "scen_d_pv", round(0.05 * PR, 4), format="%.4g") \
                if kind == "pv" else float(ss.get("scen_d_pv") or 0.05 * PR)
            sp_amp_e = float(sp_to - sp_from) if kind in ("sp", "sp_in", "custom") else 0.0
            ctx.sim_sp0 = sp_from
            ft_key = f"{sdf_key}|spft"
            if kind == "custom" and sdf_key in ss and ss.get(ft_key) not in (None, (sp_from, sp_to)):
                # změna „z → na“: přepsat skoky SP v tabulce scénáře (amplituda = na − z)
                rows_, hit = scenario.set_sp_step(ss.get(f"{sdf_key}|last", ss[sdf_key]), sp_amp_e)
                if hit:
                    ss[ft_key] = (sp_from, sp_to)
                    ss[sdf_key] = rows_
                    _reset_editor(sdf_key, edkey)
                    st.rerun()
            ss[ft_key] = (sp_from, sp_to)
        else:
            T_end = float(ts_id[-1])
            st.caption(T("replay_help"))
    with ws.verify:
        robust_on = st.toggle(T("robust_on"), key="robust_on", help=T("h_robust_on"))
        spread_on = st.toggle(T("spread_on"), key="spread_on", help=T("h_spread_on"),
                              disabled=not unc_models) and bool(unc_models)
        if "ff_cmp" not in ss:
            ss["ff_cmp"] = True
        ff_cmp = st.toggle(T("ff_cmp"), key="ff_cmp", help=T("h_ff_cmp"), disabled=not any(ff)) and any(ff)
    s.T_end, s.d_in, s.d_pv, s.edkey, s.ff_cmp, s.kind = T_end, d_in, d_pv, edkey, ff_cmp, kind
    s.robust_on, s.sdf_key, s.sp_amp_e, s.spread_on = robust_on, sdf_key, sp_amp_e, spread_on


def _tn_events(s):
    """Vlastní události scénáře (tabulka pod grafem)."""
    MR, T_end, c_d, edkey, kind, m_below = s.MR, s.T_end, s.c_d, s.edkey, s.kind, s.m_below
    sdf_key, sp_amp_e = s.sdf_key, s.sp_amp_e
    # ---- vlastní události (pod grafem – tabulka potřebuje šířku)
    tg_codes = scenario.targets(len(c_d))
    ty_codes = scenario.TYPES

    def tg_label(c_, lang=None):
        tx = TEXTS[lang or ss.lang]
        return tx["tg_" + c_] if c_[0] != "M" else f"{tx['tg_M']}: {c_d[int(c_[1:])]}"

    tg_map = {tg_label(c_, lg): c_ for c_ in tg_codes for lg in ("cs", "en")}
    ty_map = {TEXTS[lg]["ty_" + c_]: c_ for c_ in ty_codes for lg in ("cs", "en")}
    if kind == "custom":
        with m_below, card("tun_events"):
            head(T("scen_title"))
            if sdf_key not in ss:
                ss[sdf_key] = scenario.default_rows(sp_amp_e, MR, len(c_d), T_end)
            if f"{edkey}|init" not in ss:  # výchozí data editoru (při změně jazyka převezme poslední stav)
                ss[f"{edkey}|init"] = ss.get(f"{sdf_key}|last", ss[sdf_key])
            df0 = pd.DataFrame([[r_[0], tg_label(r_[1]), T("ty_" + r_[2])] + list(r_[3:])
                                for r_ in ss[f"{edkey}|init"]],
                               columns=["on", "target", "type", "amp", "start", "end", "period", "tau"])
            sdf = st.data_editor(
                df0, key=edkey, num_rows="dynamic", hide_index=True, width="stretch",
                column_config={
                    "on": st.column_config.CheckboxColumn(T("sc_on"), default=True, width="small"),
                    "target": st.column_config.SelectboxColumn(T("sc_target"), options=[tg_label(c_) for c_ in tg_codes],
                                                               required=True, help=T("h_sc_target")),
                    "type": st.column_config.SelectboxColumn(T("sc_type"), options=[T("ty_" + c_) for c_ in ty_codes],
                                                             required=True, help=T("h_sc_type")),
                    "amp": st.column_config.NumberColumn(T("sc_amp"), help=T("h_sc_amp"), format="%.4g"),
                    "start": st.column_config.NumberColumn(T("sc_start"), min_value=0.0, format="%.0f"),
                    "end": st.column_config.NumberColumn(T("sc_end"), min_value=0.0, format="%.0f",
                                                         help=T("h_sc_end")),
                    "period": st.column_config.NumberColumn(T("sc_period"), min_value=0.0, format="%.4g",
                                                            help=T("h_sc_period")),
                    "tau": st.column_config.NumberColumn(T("sc_tau"), min_value=0.0, format="%.4g",
                                                         help=T("h_sc_tau"))})
            st.caption(T("scen_help"))
            st.caption(T("sc_where_help"))
            last_ = []
            for _, row in sdf.iterrows():
                tgc_, tyc_ = tg_map.get(str(row.get("target"))), ty_map.get(str(row.get("type")))
                if tgc_ and tyc_:
                    last_.append([bool(row.get("on", True)), tgc_, tyc_] +
                                 [None if pd.isna(row.get(c_)) else float(row.get(c_))
                                  for c_ in ("amp", "start", "end", "period", "tau")])
            ss[f"{sdf_key}|last"] = last_


def _tn_plant(s):
    """Proces a ventil v simulaci; signály scénáře a simulace sad (Set 1, Set 2, Návrh, varianty)."""
    EM, MR, PR, T_end, base_ctrl, c_d = s.EM, s.MR, s.PR, s.T_end, s.base_ctrl, s.c_d
    ctx, d_id, d_in, d_pv, ff, ff_cmp = s.ctx, s.d_id, s.d_in, s.d_pv, s.ff, s.ff_cmp
    ffll, has_sp, kind, mcode, model_stic, mv_id = s.ffll, s.has_sp, s.kind, s.mcode, s.model_stic, s.mv_id
    p, pdl, pv_id, robust_on, samp, sdf_key = s.p, s.pdl, s.pv_id, s.robust_on, s.samp, s.sdf_key
    sel_mask, set1_ctrl, set2_ctrl, sigma_pv = s.sel_mask, s.set1_ctrl, s.set2_ctrl, s.sigma_pv
    sp, sp_amp_e = s.sp, s.sp_amp_e
    sug, ts_id, u_mv, u_pv, ws = s.sug, s.ts_id, s.u_mv, s.u_pv, s.ws
    # ---- proces a ventil v simulaci
    with ws.plant:
        st.caption(T("plant_help"))
        S_def = model_stic * MR / 100
        S_e = num(T("sim_stic", u=u_mv or "MV"), f"sim_S|{mcode}|{S_def:.4g}", S_def, min_value=0.0,
                  format="%.4g", help=T("h_sim_stic"))
        v2, v3 = st.columns(2)
        J_pct = num(T("sim_slip"), "sim_J", 100.0, v2, min_value=0.0, max_value=100.0, help=T("h_sim_slip"))
        noise_e = num(T("sim_noise", u=u_pv or "PV"), "sim_noise", 0.0, v3, min_value=0.0, format="%.4g",
                      help=T("h_sim_noise", s=f"{sigma_pv * PR / 100:.3g}"))
        st.markdown(f"**{T('vchar_title')}**", help=T("h_vchar"))
        if "vchar_init" not in ss:
            ss["vchar_init"] = [1.0] * 10
        vdf = st.data_editor(
            pd.DataFrame({"band": [f"{10 * i}–{10 * i + 10}" for i in range(10)], "gain": ss["vchar_init"]}),
            key="vchar_ed", hide_index=True, width="stretch", disabled=["band"],
            column_config={"band": st.column_config.TextColumn(T("vchar_band", u=u_mv or "MV")),
                           "gain": st.column_config.NumberColumn(T("vchar_gain"), min_value=0.0, format="%.3g")})
        try:
            vgains = [float(x) if not pd.isna(x) else 1.0 for x in vdf["gain"].tolist()]
        except Exception:
            vgains = [1.0] * 10
        ss["vchar_last"] = vgains
        xs_, ys_ = scenario.valve_curve(vgains)
        fvc = go.Figure(go.Scatter(x=xs_, y=ys_, mode="lines", line=dict(color=C_MV, width=2)))
        fvc.add_trace(go.Scatter(x=[0, 100], y=[0, 100], mode="lines", line=dict(color="#94a3b8", dash="dot")))
        style(fvc, 230, rev="vchar")
        fvc.update_layout(showlegend=False, xaxis_title=T("vchar_x"), yaxis_title=T("vchar_y"), hovermode="closest")
        show(fvc, key="chart_vchar", fname="valve_characteristic")
    plant = scenario.plant(S_e, J_pct, noise_e, vgains, PR, MR)
    h, ts_sim = scenario.grid(samp, T_end)
    pv0 = float(np.nanmedian(sp[sel_mask])) if has_sp else float(pv_id[0])
    if kind != "replay":
        pv0 = float(ctx.P(ctx.sim_sp0))     # počáteční SP (a PV) simulace = „SP z“
    mv0 = float(mv_id[0])
    if not (base_ctrl["MV_Lo"] - 1e-9 <= mv0 <= base_ctrl["MV_Hi"] + 1e-9):
        ws.top.warning(T("sim_mv0_out", m=f"{EM(mv0):.4g}", lo=f"{ctx.mvl_lo:g}", hi=f"{ctx.mvl_hi:g}",
                         u=u_mv or "MV"), icon=":material/warning:")
    if kind == "custom":
        rows_sc = ss.get(f"{sdf_key}|last", [])
    elif kind == "replay":
        rows_sc = []
    else:
        rows_sc = scenario.preset_rows(kind, sp_amp_e, d_in, d_pv, scenario.meas_amps(d_id), T_end)
    sig = scenario.signals(rows_sc, ts_sim, h, T_end, PR, MR, pv0, len(c_d))
    if kind == "replay":
        sig["dmeas"] = scenario.replay_dists(ts_sim, ts_id, d_id)
    spv, dmv_arr, dpv_arr, dmeas = sig["sp"], sig["dmv"], sig["dpv"], sig["dmeas"]
    sp_amp, d_amp = sig["sp_amp"], sig["d_amp"]
    ss["scen_built"] = dict(mcode=mcode, h=h, sp=spv, pv0=pv0, mv0=mv0, dmeas=dmeas, dmv=dmv_arr, dpv=dpv_arr,
                            plant=plant, sp_amp=sp_amp or 5.0, d_amp=d_amp or 5.0)
    ss["scen_sig"] = _sig(kind, rows_sc, T_end, pv0, mv0, plant, float(np.sum(np.abs(spv))),
                          [float(np.sum(np.abs(d))) for d in dmeas])

    def run(ctrl, pp=p):
        return pidconl_sim_full(mcode, pp, pdl, h, spv, pv0, mv0, dict(ctrl, **plant), dmeas, dmv_arr, dpv_arr)

    sims = {T("set_1"): (run(set1_ctrl), C_SET1, "dot"), T("set_2"): (run(set2_ctrl), C_SET2, None)}
    sug_ctrl = None
    if sug is not None:
        sug_ctrl = dict(set_ctrl(base_ctrl, sug["Kc"], sug["Ti"], sug["Td"]), FF=ff, FF_LL=ffll)
        sims[T("dk_sug_curve")] = (run(sug_ctrl), C_SUG, None)
    if robust_on:
        pp = list(p)
        pp[0] *= 1.3
        pp[-1] *= 1.5
        sims[T("new_err")] = (run(set2_ctrl, pp), C_SET2, "dash")
    ff_moves = any(g and np.any(d != 0) for g, d in zip(ff, dmeas))
    if ff_cmp and ff_moves:      # stejná sada 2 bez dopředné vazby – rozdíl = přínos FF
        sims[T("set2_noff")] = (run(dict(set2_ctrl, FF=[0.0] * len(ff), FF_LL=[(0.0, 0.0, 0.0)] * len(ff))),
                                "#9aa5b1", "dashdot")
    s.dmeas, s.dmv_arr, s.dpv_arr, s.plant, s.run, s.sims = dmeas, dmv_arr, dpv_arr, plant, run, sims
    s.spv, s.sug_ctrl, s.ts_sim = spv, sug_ctrl, ts_sim


def _tn_views(s):
    """Hlavní plocha: odezva ve scénáři s ukazateli kvality, nebo frekvenční analýza."""
    EM, EP, H, MR, PR, T_end = s.EM, s.EP, s.H, s.MR, s.PR, s.T_end
    c_d, dmeas, dmv_arr, dpv_arr, kind, lab_mv = s.c_d, s.dmeas, s.dmv_arr, s.dpv_arr, s.kind, s.lab_mv
    lab_pv, lab_t, m_view, mcode, mv_lo, p = s.lab_pv, s.lab_t, s.m_view, s.mcode, s.mv_lo, s.p
    plant, run, set1_ctrl, set2_ctrl, sims, spread_on = s.plant, s.run, s.set1_ctrl, s.set2_ctrl, s.sims, s.spread_on
    spv, sug_ctrl, ts_sim, u_mv, u_pv, unc_models = s.spv, s.sug_ctrl, s.ts_sim, s.u_mv, s.u_pv, s.unc_models
    view = s.view
    # ---- hlavní plocha: odezva ve scénáři / frekvenční analýza
    v_time = m_view.container()
    v_freq = m_view.container()
    has_d = any(np.any(d != 0) for d in dmeas) or np.any(dmv_arr != 0) or np.any(dpv_arr != 0)
    nr = 3 if has_d else 2
    fig = mkfig(nr, [0.55, 0.25, 0.2] if nr == 3 else [0.62, 0.38])
    if spread_on:
        for i_, q in enumerate(unc_models[:10]):
            rq = run(set2_ctrl, list(q))
            if scenario.stable(rq):
                fig.add_trace(tr(rq["t"], EP(rq["PV"]), T("unc_variants"), "#86efac", 1.0, show=i_ == 0, group="spread",
                                 opacity=0.7), 1, 1)
                fig.add_trace(tr(rq["t"], EM(rq["MV"]), T("unc_variants"), "#86efac", 1.0, show=False, group="spread",
                                 opacity=0.7), 2, 1)
    fig.add_trace(tr(ts_sim, EP(spv), "SP", C_SP, 1.4, "dash", "hv"), 1, 1)
    kp, unstable = [], []
    ylo, yhi = [], []
    for nm, (rs_, col, dash) in sims.items():
        Pv, Mv = rs_["PV"], rs_["MV"]
        if not scenario.stable(rs_):
            unstable.append(nm)
            continue
        fig.add_trace(tr(rs_["t"], EP(Pv), f"{nm}", col, 2.0, dash, group=nm), 1, 1)
        fig.add_trace(tr(rs_["t"], EM(Mv), f"MV {nm}", col, 2.0, dash, show=False, group=nm), 2, 1)
        ylo.append(float(np.nanmin(EP(Pv))))
        yhi.append(float(np.nanmax(EP(Pv))))
        if plant["Stic"] > 0:
            fig.add_trace(tr(rs_["t"], EM(rs_["V"]), f"{T('valve_pos')} {nm}", col, 1.0, "dot", shape="hv",
                             show=False, group=nm, opacity=0.8), 2, 1)
        k_ = scenario.kpis(rs_, PR, MR)
        if nm == T("dk_sug_curve"):
            ss["sug_iae"] = float(k_["iae"])
        kp.append({T("setting"): nm, "IAE [%·s]": f"{k_['iae']:.4g}",
                   T("kpi_maxdev", u=u_pv or "PV"): f"{k_['maxdev']:.4g}",
                   T("kpi_mvrange", u=u_mv or "MV"): f"{k_['mv_range']:.4g}",
                   T("kpi_mvtravel", u=u_mv or "MV"): f"{k_['mv_travel']:.4g}",
                   T("kpi_rev"): k_["reversals"], **_step_cols(k_.get("step"))})
    if ylo:            # ujíždějící průběh nepřebije osu (NormPV ± 25 %)
        lo_, hi_ = sorted((float(EP(-25.0)), float(EP(125.0))))
        a_, b_ = max(min(ylo + [float(np.nanmin(EP(spv)))]), lo_), min(max(yhi + [float(np.nanmax(EP(spv)))]), hi_)
        if b_ > a_:
            pad = 0.05 * (b_ - a_)
            fig.update_yaxes(range=[a_ - pad, b_ + pad], row=1, col=1)
    ytit = [lab_pv, lab_mv]
    if nr == 3:
        for i, (nm, d) in enumerate(zip(c_d, dmeas)):
            if np.any(d != 0):
                fig.add_trace(tr(ts_sim, d, str(nm), _c_dist()[i % 4], 1.4), 3, 1)
        if np.any(dmv_arr != 0):
            fig.add_trace(tr(ts_sim, EM(dmv_arr) - mv_lo, T("tg_IN"), "#a16207", 1.4), 3, 1)
        if np.any(dpv_arr != 0):
            fig.add_trace(tr(ts_sim, dpv_arr * PR / 100, T("tg_PV"), "#7c3aed", 1.4), 3, 1)
        ytit.append(T("dists"))
    with v_time, hidden(view != "time"):
        if view == "time":
            chart_card = card("tun_chart")
            head(T("tn_chart"), note=html.escape(_scen_note(kind, T_end)), cont=chart_card)
        else:
            chart_card = st.container()
        with chart_card:
            for e_ in unstable:
                st.error(T("err_sim_unstable", n=e_), icon=":material/error:")
            show(style(fig, H, ytit, lab_t, rev=f"sim|{kind}"), key="chart_sim", fname="simulation",
                 report=T("rep_fig_sim"))
        if kp:
            kdf = pd.DataFrame(kp).set_index(T("setting"))
            REPORT["tables"].append((T("rep_tab_kpi"), kdf))
            if view == "time":
                with card("tun_kpi"):
                    head(T("tn_kpi"), T("kpi_help"), note=T("tn_kpi_note"))
                    kt = kdf.T
                    table(kt, key="tun_kpi_tab", cell_class=_best_cells(kt, [T("kpi_mvrange", u=u_mv or "MV")]))
    if view == "freq":
        fsets = [(T("set_1"), set1_ctrl, C_SET1, True), (T("set_2"), set2_ctrl, C_SET2, False)]
        if sug_ctrl is not None:
            fsets.append((T("dk_sug_curve"), sug_ctrl, C_SUG, False))
        fres = fq.compare(mcode, p, {n_: c_ for n_, c_, _, _ in fsets})
        bode, nyq, sens = freq_figs(fres, [(n_, c_, d_) for n_, _, c_, d_ in fsets], H)
        with v_freq, card("tun_freq"):
            head(T("fq_bode"))
            show(bode, key="chart_bode", fname="bode")
            f1, f2 = st.columns(2)
            with f1:
                head(T("fq_nyquist"))
                show(nyq, key="chart_nyq", fname="nyquist")
            with f2:
                head(T("fq_sens"))
                show(sens, key="chart_sens", fname="sensitivity")
            ftab = pd.DataFrame([dict(zip(["", "Ms", "GM", "PM [°]", "ωc [rad/s]", "ω180 [rad/s]", T("fq_bw"),
                                           T("fq_tbw"), T("fq_stable")],
                                          [r_[0], *[fmt(x, 4) for x in r_[1:8]], T("yes") if r_[8] else T("no")]))
                                 for r_ in freq_table(fres, [n_ for n_, _, _, _ in fsets])]).set_index("")
            table(ftab, key="tun_freq_tab")
            st.caption(T("fq_help"))


def _tn_outputs(s):
    """Report, export CSV a přechod do Živé simulace."""
    adv, c_d, crit, ctype, diffgain, ff = s.adv, s.c_d, s.crit, s.ctype, s.diffgain, s.ff
    mcode, method, mv_hi, mv_lo, p, pdl = s.mcode, s.method, s.mv_hi, s.mv_lo, s.p, s.pdl
    pv_hi, pv_lo, rn, samp, set1_gain, set1_td = s.pv_hi, s.pv_lo, s.rn, s.samp, s.set1_gain, s.set1_td
    set1_ti, set2_gain, set2_td, set2_ti, sug, tc = s.set1_ti, s.set2_gain, s.set2_td, s.set2_ti, s.sug, s.tc
    ws = s.ws
    REPORT["tuning"] = dict(model=model_name(mcode), params=dict(zip(MODELS[mcode]["params"], p)),
                            method=T("m_" + method) + (f" · {T('crit_' + crit)}" if method == "OPT" else ""),
                            ctype=ctype, notes=notes_text(sug["notes"]) if sug else "",
                            adv=f"{adv['rec']} — {T(adv['key'])}")

    out = {"model": mcode, **{f"model_{n_}": v for n_, v in zip(MODELS[mcode]["params"], p)},
           "method": method, "controller": ctype, "tc": tc,
           "NormPV": f"{pv_lo}..{pv_hi}", "NormMV": f"{mv_lo}..{mv_hi}", "SampleTime": samp,
           "Gain": set2_gain, "TI": set2_ti, "TD": set2_td, "DiffGain": diffgain,
           "Ms": rn["Ms"], "GM": rn["GM"], "PM": rn["PM"],
           "Gain_old": set1_gain, "TI_old": set1_ti, "TD_old": set1_td}
    for j, dn in enumerate(c_d):
        out.update({f"{n_}_{dn}": v for n_, v in zip(DIST_PARAMS + ["Tp2"], pd_z(pdl[j]))})
        out[f"FF_{dn}"] = ff[j] if ff else 0.0
    ws.sets.download_button(T("download"), pd.DataFrame([out]).to_csv(index=False, sep=";", decimal=","),
                            "pidconl_tuning.csv", "text/csv", icon=":material/download:")
    ws.cta.button(T("tn_to_live"), key="g_tun_live", type="primary", width="stretch",
                  on_click=apc.guide.goto, kwargs=dict(tab="live"))


_STEPS = (_tn_toolbar, _tn_d_advice, _tn_method, _tn_methods, _tn_sets, _tn_robust, _tn_history, _tn_feedforward, _tn_scenario, _tn_events, _tn_plant, _tn_views, _tn_outputs)


def _scen_note(kind, T_end):
    """Poznámka k nadpisu grafu: druh scénáře a délka simulace."""
    return f"{T('dk_sc_' + kind)} · {T('sim_len')} {dur(T_end)}"


def _best_cells(kt, skip=()):
    """Třídy buněk tabulky ukazatelů (řádek = ukazatel, sloupec = sada): v řádku zvýrazněná nejlepší hodnota."""
    out = []
    for name, row in kt.iterrows():
        cls = [""] * len(row)
        if name not in skip and len(row) > 1:
            x = pd.Series([_kpi_num(v) for v in row])
            if x.notna().sum() >= 2 and x.nunique() >= 2:
                best = x.abs().min() if "over" in str(name).lower() or "překmit" in str(name).lower() else x.min()
                cls = ["best" if v == best else "" for v in x]
        out.append(cls)
    return out


def _kpi_num(v):
    """Číslo z buňky ukazatele; doby („44 s“, „2.05 min“, „1 h 05 min“) na sekundy, aby šly porovnat."""
    parts = str(v).replace(",", ".").split()
    try:
        if len(parts) == 4 and parts[1] == "h":
            return float(parts[0]) * 3600 + float(parts[2]) * 60
        x = float(parts[0])
    except (TypeError, ValueError, IndexError):
        return np.nan
    return x * {"min": 60.0, "h": 3600.0}.get(parts[1] if len(parts) > 1 else "", 1.0)


def _write_set(n, sug, last, mcode):
    """Návrh → Set n (callback tlačítka) a záznam do historie návrhů."""
    ss[f"set{n}_gain"], ss[f"set{n}_ti"], ss[f"set{n}_td"] = sug["Kc"], sug["Ti"], sug["Td"]
    ss["tune_hist"] = [dict(time=time.strftime("%Y-%m-%d %H:%M"), set=n, Kc=float(sug["Kc"]), Ti=float(sug["Ti"]),
                            Td=float(sug["Td"]), model=mcode, method=last["label"], ctype=last["ctype"],
                            scen=T("dk_sc_" + ss.get("scen_kind", "sp")), Ms=None, iae=ss.get("sug_iae"))] \
        + list(ss.get("tune_hist") or [])[:49]


def _hist_set(n, e):
    """Záznam historie → Set n (callback)."""
    ss[f"set{n}_gain"], ss[f"set{n}_ti"], ss[f"set{n}_td"] = e["Kc"], e["Ti"], e["Td"]
