"""Záložka Ladění (rozložení jako desktop): vlevo scénář v grafu a frekvenční analýza, vpravo scénář → návrh → sady, blok PIDConL."""
import time
from contextlib import nullcontext
from types import SimpleNamespace

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from ...core import (DIST_PARAMS, MODELS, d_advice, default_tc, tune)
from ...app import frequency as fq
from ...app import scenario
from ...app.plots import C_SUG, freq_figs, freq_table
from ...app import tuning as tun
from ...app.loop import block_ctrl, rule_ctrl, set_ctrl
from ...app.timefmt import dur
from ...i18n import T, TEXTS
from .. import cache
from .. import ff as ffmod
from ..cache import pidconl_sim_full, robustness
from ..charts import REPORT, mkfig, show, style, tr
from ..theme import C_MV, C_SET1, C_SET2, C_SP, _c_dist
from ..layout import section, workspace
from ..widgets import fmt, model_name, notes_text, num, seg, sel, sld
from . import apc

ss = st.session_state


def render_block(ctx):
    """
    Rozložení záložky Ladění (jako desktop): vlevo graf scénáře / frekvenční analýza, vpravo panel – výpočet,
    1 scénář, 2 návrh, 3 sady, ověření, doporučení D, proces a ventil, blok PIDConL. Blok se vykreslí hned
    (ctx.base_ctrl potřebují i ostatní záložky), ostatní sekce vyplní render().
    """
    with ctx.tabs["tuning"]:
        ctx.gph["tuning"] = st.container()
        ws = workspace()
        with ws.side:
            ws.top = st.container()
        ctx.tun = ws
        blk = section(ws.side, T("blk_title"), "tun_block", expanded=True, icon=":material/settings:")   # 1. – bez něj
        ws.scen = section(ws.side, T("dk_sec_scen"), "tun_scen", icon=":material/timeline:")       # výpočty nedávají smysl
        ws.sug = section(ws.side, T("dk_sec_sug"), "tun_sug", icon=":material/calculate:")
        ws.sets = section(ws.side, T("dk_sec_sets"), "tun_sets", icon=":material/tune:")
        ws.hist = section(ws.side, T("dk_sec_hist"), "tun_hist", icon=":material/history:")
        ws.verify = section(ws.side, T("dk_sec_verify"), "tun_verify", icon=":material/shield:")
        ws.dadv = section(ws.side, T("d_title"), "tun_d", icon=":material/help:")
        ws.plant = section(ws.side, T("plant_title"), "tun_plant", icon=":material/water_drop:")
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
    """Záložka Ladění: scénář → návrh parametrů (na tlačítko) → sady; graf scénáře a frekvenční analýza."""
    H, base_ctrl, c_d, d_id, diffgain, has_sp, model, model_stic, mv_hi, mv_id, mv_lo, plant, pv_hi, pv_id, pv_lo, samp, sel_mask, set1_ctrl, set2_ctrl, sigma_pv, sp, ts_id, u_mv, u_pv, unc_models = ctx.H, ctx.base_ctrl, ctx.c_d, ctx.d_id, ctx.diffgain, ctx.has_sp, ctx.model, ctx.model_stic, ctx.mv_hi, ctx.mv_id, ctx.mv_lo, ctx.plant, ctx.pv_hi, ctx.pv_id, ctx.pv_lo, ctx.samp, ctx.sel_mask, ctx.set1_ctrl, ctx.set2_ctrl, ctx.sigma_pv, ctx.sp, ctx.ts_id, ctx.u_mv, ctx.u_pv, ctx.unc_models
    EM, EP, MR, PR, lab_mv, lab_pv, lab_t = ctx.EM, ctx.EP, ctx.MR, ctx.PR, ctx.lab_mv, ctx.lab_pv, ctx.lab_t
    ws = ctx.tun
    with ctx.tabs["tuning"]:
        if model is None:
            ws.main.info(T("need_model"), icon=":material/arrow_back:")
        else:
            mcode, p, pdl = model
            with ws.main:
                st.caption(f"{model_name(mcode)} · " + ", ".join(f"{n} = {v:.4g}" for n, v in zip(MODELS[mcode]["params"], p))
                           + " · " + T("samp_note", s=f"{samp:g}", h=f"{samp / 2:g}"))
                apc.tuning_hint(ctx)   # odkaz na záložku APC, když by smyčce pomohla pokročilá struktura
                m_view = st.container()
                m_below = st.container()
            p_eff = tun.p_eff(p, samp)
            methods = tun.methods(mcode, p)
            mkey = f"method|{mcode}"
            if "pending_tune" in ss:
                m_, c_, cr_ = ss.pop("pending_tune")
                if m_ in methods:
                    ss[mkey], ss["ctype"] = m_, c_
                    if cr_:
                        ss["opt_crit"] = cr_

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

            # ---- 2 · návrh (počítá se na tlačítko Vypočítat)
            with ws.sug:
                method = seg(st, T("method"), methods, tun.DEFAULT_METHOD, mkey, format_func=lambda x: T("m_" + x),
                             help=T("method_help")) or tun.DEFAULT_METHOD
                ctype = seg(st, T("ctrl_type"), ["PI", "PID"], "PI", "ctype", help=T("h_ctype")) or "PI"
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
                    crit = seg(st, T("opt_crit"), ["MIGO", "IAE", "ISE", "ITAE", "OVS"], tun.DEFAULT_CRIT, "opt_crit",
                               format_func=lambda x: T("crit_" + x), help=T("h_opt_crit")) or tun.DEFAULT_CRIT
                    st.caption(T("cdesc_" + crit))
                    if crit != "MIGO":
                        tgt = seg(st, T("opt_target"), ["scen", "dist", "sp", "both"], tun.DEFAULT_TARGET, "opt_target",
                                  format_func=lambda x: T("tgt_" + x), help=T("h_opt_target")) or tun.DEFAULT_TARGET
                        if crit == "OVS":
                            ovs_lim = (seg(st, T("opt_ovs"), [0, 2, 5, 10], 2, "opt_ovs", format_func=lambda x: f"{x} %",
                                           help=T("h_opt_ovs")) or 0) / 100
                    ms_max = seg(st, T("opt_ms"), [1.4, 1.6, 1.8, 2.0], 1.6, "opt_ms",
                                 format_func=lambda x: f"{x:.1f}", help=T("opt_ms_help")) or 1.6
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
            with ws.top:
                calc = st.button(T("dk_calc"), key="g_calc", type="primary", width="stretch",
                                 icon=":material/play_arrow:", help=T("dk_calc_help"))
            if calc:
                try:
                    with ws.top, st.spinner(T("optimizing")) if method == "OPT" else nullcontext():
                        res_ = tun.suggest(mcode, p, pdl, base_ctrl, req, robust_set, sb, solvers)
                    ss["sug_last"] = dict(sig=sig_now, sug=res_, mcode=mcode,
                                          label=T("m_" + method) + (f" · {T('crit_' + crit)}" if method == "OPT" else ""),
                                          ctype=ctype, t=time.strftime("%H:%M:%S"))
                except Exception as ex:
                    ws.top.error(T(str(ex)))
            last = ss.get("sug_last") if (ss.get("sug_last") or {}).get("mcode") == mcode else None
            sug = last["sug"] if last else None
            if last is None:
                ws.top.info(T("dk_calc_hint"), icon=":material/info:")
            elif last["sig"] != sig_now:
                ws.top.warning(T("web_stale"), icon=":material/update:")
            else:
                ws.top.caption(":material/check_circle: " + T("web_calc_done", t=last["t"]))
            with sug_box:
                if sug is not None:
                    st.markdown(f"**{T('dk_suggest')}:** Gain = {sug['Kc']:.4g} · TI = {sug['Ti']:.4g} s · "
                                f"TD = {sug['Td']:.4g} s")
                    b1, b2 = st.columns(2)
                    for n_, b_ in ((1, b1), (2, b2)):
                        if b_.button(T(f"write_s{n_}"), width="stretch", icon=":material/arrow_downward:"):
                            ss[f"set{n_}_gain"], ss[f"set{n_}_ti"], ss[f"set{n_}_td"] = sug["Kc"], sug["Ti"], sug["Td"]
                            ss["tune_hist"] = [dict(time=time.strftime("%Y-%m-%d %H:%M"), set=n_, Kc=float(sug["Kc"]),
                                                    Ti=float(sug["Ti"]), Td=float(sug["Td"]), model=mcode,
                                                    method=last["label"], ctype=last["ctype"],
                                                    scen=T("dk_sc_" + ss.get("scen_kind", "sp")),
                                                    Ms=None, iae=ss.get("sug_iae"))] + list(ss.get("tune_hist") or [])[:49]
                            st.rerun()
                    if sug["notes"]:
                        st.info(notes_text(sug["notes"]), icon=":material/lightbulb:")
                    if sug["Kc"] < 0:
                        st.warning(T("warn_neg_gain"), icon=":material/swap_vert:")
                if "fit" in ss and mcode in ss.fit["res"] and ss.fit["res"][mcode]["fit"] < 70:
                    st.warning(T("warn_low_fit"), icon=":material/warning:")

            # ---- srovnání metod (pod grafem, široká tabulka)
            with m_below.expander(T("cmp_title"), expanded=False, icon=":material/leaderboard:", key="cmp_open",
                                  on_change="rerun") as cmp_exp:
                if cmp_exp.open:  # porovnání (vč. optimalizací) se počítá až po rozbalení
                    avg_c = (ss.get("avg_dpv", 1) / PR * 100, ss.get("avg_dmv", 1) / MR * 100) if "avg_dpv" in ss else None
                    req_c = tun.Request(ms=ss.get("opt_ms") or 1.6, hf=hf_max, target=ss.get("opt_target") or "both",
                                        ovs=(ss.get("opt_ovs") if ss.get("opt_ovs") is not None else 2) / 100)
                    with st.spinner(T("optimizing")):
                        cmp_ = tun.compare(mcode, p, pdl, base_ctrl, req_c, avg_c, sigma_pv, robust_set, solvers, robustness)
                    rows = []
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
                    cdf = pd.DataFrame(rows)
                    ev_c = st.dataframe(cdf, hide_index=True, width="stretch", on_select="rerun", selection_mode="single-row", key=f"cmp|{mcode}",
                                        column_config={"Ms": st.column_config.NumberColumn(format="%.2f"),
                                                       T("use_col"): st.column_config.TextColumn(width="large")})
                    try:
                        sel_rows = ev_c.selection.rows
                        if sel_rows:
                            selected_row = rows[sel_rows[0]]
                            st.markdown(f"**{T('sel_method')}:** {selected_row[T('col_method')]}")
                            b1, b2, _ = st.columns([1.3, 1.3, 3])
                            if b1.button(T("write_sel_s1"), key="cmp_s1", icon=":material/arrow_downward:"):
                                ss["set1_gain"], ss["set1_ti"], ss["set1_td"] = selected_row["Gain"], selected_row["TI [s]"], selected_row["TD [s]"]
                                st.rerun()
                            if b2.button(T("write_sel_s2"), key="cmp_s2", icon=":material/arrow_downward:"):
                                ss["set2_gain"], ss["set2_ti"], ss["set2_td"] = selected_row["Gain"], selected_row["TI [s]"], selected_row["TD [s]"]
                                st.rerun()
                    except AttributeError:
                        pass
                st.caption(T("cmp_help"))

            # ---- 3 · sady a robustnost
            with ws.sets:
                p1, p2 = st.columns(2)
                with p1:
                    st.markdown(f"**{T('set_1')}**", help=T("h_set_1"))
                    set1_gain = num("Gain", "set1_gain", ss.get("set1_gain", 1.0), format="%.5g", help=T("h_gain"))
                    set1_ti = num("TI [s]", "set1_ti", ss.get("set1_ti", 100.0), min_value=0.0, format="%.5g", help=T("h_ti"))
                    set1_td = num("TD [s]", "set1_td", ss.get("set1_td", 0.0), min_value=0.0, format="%.5g", help=T("h_td"))
                with p2:
                    st.markdown(f"**{T('set_2')}**", help=T("h_set_2"))
                    set2_gain = num("Gain", "set2_gain", sug["Kc"] if sug else 1.0, format="%.5g", help=T("h_gain"))
                    set2_ti = num("TI [s]", "set2_ti", sug["Ti"] if sug else 100.0, min_value=0.0, format="%.5g", help=T("h_ti"))
                    set2_td = num("TD [s]", "set2_td", sug["Td"] if sug else 0.0, min_value=0.0, format="%.5g", help=T("h_td"))
                set1_ctrl = set_ctrl(base_ctrl, set1_gain, set1_ti, set1_td)
                set2_ctrl = set_ctrl(base_ctrl, set2_gain, set2_ti, set2_td)
                rc = tun.set_metrics(mcode, p, set1_ctrl, sigma_pv, unc_models, robustness)
                rn = tun.set_metrics(mcode, p, set2_ctrl, sigma_pv, unc_models, robustness)
                ctx.PROG["tune"] = 2 if not rn["stable"] else (0 if rn["Ms"] <= 2.0 else 1)
                tbl = pd.DataFrame({
                    T("set_1"): [fmt(set1_gain), fmt(set1_ctrl["TI"]), fmt(set1_td), fmt(rc["Ms"], 3), fmt(rc["GM"], 3),
                                 fmt(rc["PM"], 3), fmt(rc["noise"] * MR / 100, 3)],
                    T("set_2"): [fmt(set2_gain), fmt(set2_ctrl["TI"]), fmt(set2_td), fmt(rn["Ms"], 3), fmt(rn["GM"], 3),
                                 fmt(rn["PM"], 3), fmt(rn["noise"] * MR / 100, 3)]},
                    index=["Gain", "TI [s]", "TD [s]", T("ms"), T("gm"), T("pm"), T("noise_col", u=u_mv or "MV")])
                if unc_models:
                    tbl.loc[T("ms_worst")] = [fmt(rc["Ms_worst"], 3), fmt(rn["Ms_worst"], 3)]
                st.dataframe(tbl, width="stretch")
                REPORT["tables"].append((T("rep_tab_tuning"), tbl))
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

            # ---- historie ladění
            with ws.hist:
                hist = [e for e in (ss.get("tune_hist") or []) if isinstance(e, dict) and "Kc" in e]
                if not hist:
                    st.caption(T("dk_hist_help"))
                else:
                    hdf = pd.DataFrame([{T("dk_hist_time"): e.get("time"), T("dk_hist_set"): e.get("set"),
                                         T("method"): e.get("method"), "Gain": e["Kc"], "TI": e["Ti"], "TD": e["Td"]}
                                        for e in hist])
                    ev_h = st.dataframe(hdf, hide_index=True, width="stretch", on_select="rerun",
                                        selection_mode="single-row", key="hist_tab")
                    rows_h = getattr(getattr(ev_h, "selection", None), "rows", [])
                    if rows_h:
                        e = hist[rows_h[0]]
                        h1, h2 = st.columns(2)
                        for n_, b_ in ((1, h1), (2, h2)):
                            if b_.button(T(f"dk_hist_s{n_}"), key=f"g_hist_s{n_}", width="stretch"):
                                ss[f"set{n_}_gain"], ss[f"set{n_}_ti"], ss[f"set{n_}_td"] = e["Kc"], e["Ti"], e["Td"]
                                st.rerun()

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

            # ---- 1 · scénář
            sdf_key = f"scen_df|{mcode}|{len(c_d)}"
            edkey = f"scen_ed|{sdf_key}|{ss.lang}"
            kinds, kind0 = _scen_kind(c_d, sdf_key)
            with ws.scen:
                kind = seg(st, T("dk_sc_kind"), kinds, kind0, "scen_kind", format_func=lambda x: T("dk_sc_" + x),
                           help=T("dk_sc_kind_help")) or kind0
                ss["scen2"] = "replay" if kind == "replay" else "custom"
                st.caption(T("dk_sc_note_" + kind))
                with st.popover(T("sc_where_btn"), icon=":material/help:", width="stretch"):
                    st.markdown(T("sc_where_help"))
                T_char = scenario.t_char(mcode, p, tc, samp)
                sp_data = float(EP(np.nanmedian(sp[sel_mask]) if has_sp else pv_id[0]))
                if kind != "replay":
                    sim_l1, sim_l2 = st.columns([1.4, 1], vertical_alignment="bottom")
                    T_end_unit = sel(sim_l2, T("time_unit"), ["s", "min", "h"], 0, "sim_len_u")
                    mult = {"s": 1.0, "min": 60.0, "h": 3600.0}[T_end_unit]
                    if "sim_len_auto" not in ss:
                        ss["sim_len_auto"] = True
                    auto_len = st.toggle(T("sim_len_auto"), key="sim_len_auto", help=T("h_sim_len_auto"))
                    # i návrh (sady mohou mít ještě výchozí hodnoty) – SIMC, ne zvolená metoda: optimalizace na scénáři
                    # závisí na délce simulace a délka na jejím výsledku by se navzájem posouvaly (optimalizace stále znovu)
                    r_ = tune(mcode, p, "SIMC", default_tc(mcode, p, samp, "SIMC", ctype, diffgain), ctype, samp)
                    prop_ctrl = rule_ctrl(base_ctrl, r_)
                    t_auto, auto_src = scenario.auto_length(mcode, p, (set1_ctrl, set2_ctrl, prop_ctrl), T_char, samp, ts_id,
                                                             settling=cache.settling_time)
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

            # ---- vlastní události (pod grafem – tabulka potřebuje šířku)
            tg_codes = scenario.targets(len(c_d))
            ty_codes = scenario.TYPES

            def tg_label(c_, lang=None):
                tx = TEXTS[lang or ss.lang]
                return tx["tg_" + c_] if c_[0] != "M" else f"{tx['tg_M']}: {c_d[int(c_[1:])]}"

            tg_map = {tg_label(c_, lg): c_ for c_ in tg_codes for lg in ("cs", "en")}
            ty_map = {TEXTS[lg]["ty_" + c_]: c_ for c_ in ty_codes for lg in ("cs", "en")}
            if kind == "custom":
                with m_below.expander(T("scen_title"), expanded=True, icon=":material/timeline:", key="sec|tun_events"):
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

            # ---- hlavní plocha: odezva ve scénáři / frekvenční analýza
            with m_view:
                v_time, v_freq = st.tabs([T("dk_view_time"), T("fq_title")], key="tun_view", on_change="rerun")
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
            kp = []
            ylo, yhi = [], []
            for nm, (rs_, col, dash) in sims.items():
                Pv, Mv = rs_["PV"], rs_["MV"]
                if not scenario.stable(rs_):
                    v_time.error(T("err_sim_unstable", n=nm), icon=":material/error:")
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
            with v_time:
                show(style(fig, H, ytit, lab_t, rev=f"sim|{kind}"), key="chart_sim", fname="simulation",
                     report=T("rep_fig_sim"))
                if kp:
                    st.dataframe(pd.DataFrame(kp).set_index(T("setting")), width="stretch")
                    REPORT["tables"].append((T("rep_tab_kpi"), pd.DataFrame(kp).set_index(T("setting"))))
                    st.caption(T("kpi_help"))
            if v_freq.open is not False:
                fsets = [(T("set_1"), set1_ctrl, C_SET1, True), (T("set_2"), set2_ctrl, C_SET2, False)]
                if sug_ctrl is not None:
                    fsets.append((T("dk_sug_curve"), sug_ctrl, C_SUG, False))
                fres = fq.compare(mcode, p, {n_: c_ for n_, c_, _, _ in fsets})
                bode, nyq, sens = freq_figs(fres, [(n_, c_, d_) for n_, _, c_, d_ in fsets], H)
                with v_freq:
                    st.markdown(f"**{T('fq_bode')}**")
                    show(bode, key="chart_bode", fname="bode")
                    f1, f2 = st.columns(2)
                    with f1:
                        st.markdown(f"**{T('fq_nyquist')}**")
                        show(nyq, key="chart_nyq", fname="nyquist")
                    with f2:
                        st.markdown(f"**{T('fq_sens')}**")
                        show(sens, key="chart_sens", fname="sensitivity")
                    ftab = pd.DataFrame([dict(zip(["", "Ms", "GM", "PM [°]", "ωc [rad/s]", "ω180 [rad/s]", T("fq_bw"),
                                                   T("fq_tbw"), T("fq_stable")],
                                                  [r_[0], *[fmt(x, 4) for x in r_[1:8]], T("yes") if r_[8] else T("no")]))
                                         for r_ in freq_table(fres, [n_ for n_, _, _, _ in fsets])]).set_index("")
                    st.dataframe(ftab, width="stretch")
                    st.caption(T("fq_help"))
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
                out.update({f"{n_}_{dn}": v for n_, v in zip(DIST_PARAMS, pdl[j])})
                out[f"FF_{dn}"] = ff[j] if ff else 0.0
            ws.sets.download_button(T("download"), pd.DataFrame([out]).to_csv(index=False, sep=";", decimal=","),
                                    "pidconl_tuning.csv", "text/csv", icon=":material/download:")
    ctx.plant = plant
    ctx.set1_ctrl = set1_ctrl
    ctx.set2_ctrl = set2_ctrl
