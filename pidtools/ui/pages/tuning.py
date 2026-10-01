"""Záložka Ladění: konfigurace bloku PIDConL, doporučení D, metody ladění, sady parametrů, porovnání metod, FF, simulace scénáře."""
from contextlib import nullcontext

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from ...core import (DIST_PARAMS, MODELS, closed_loop_steps, d_advice, default_tc, iae, integ_gain, mv_noise, overshoot_ratio, tune)
from ...core.util import lag
from ...i18n import T, TEXTS
from .. import cache
from .. import ff as ffmod
from ..cache import pidconl_sim_full, robustness
from ..charts import REPORT, mkfig, show, style, tr
from ..theme import C_MV, C_SET1, C_SET2, C_SP, _c_dist
from ..widgets import fmt, model_name, notes_text, num, seg, sel, sld
from . import apc

ss = st.session_state


def render_block(ctx):
    """Konfigurace bloku PIDConL (horní rozbalovací sekce záložky Ladění) → ctx.base_ctrl a souhrn bloku."""
    with ctx.tabs["tuning"]:
        ctx.gph["tuning"] = st.container()
        with st.expander(T("blk_title"), expanded=True, icon=":material/tune:"):
            _norm_section(ctx)
            st.markdown(f"**{T('sb_block')}**")
            q = st.columns(4)
            ctx.samp = num(T("sampletime"), "samp", 1.0, q[0], min_value=0.001, help=T("sampletime_help"))
            ctx.diffgain = num("DiffGain", "diffgain", 5.0, q[1], min_value=0.1, help=T("diffgain_help"))
            db_e = num(T("deadband"), "db", 0.0, q[2], min_value=0.0, help=T("h_deadband"))
            db_mode = q[3].selectbox(T("db_mode"), ["cont", "step"], format_func=lambda x: T("db_" + x),
                                     help=T("db_mode_help"), key="db_mode")
            q = st.columns(4, vertical_alignment="bottom")
            ctx.mvl_lo = num("MV_LoLim", "mvl_lo", ctx.mv_lo, q[0], help=T("h_mvlim"))
            ctx.mvl_hi = num("MV_HiLim", "mvl_hi", ctx.mv_hi, q[1], help=T("h_mvlim"))
            ctx.pfb = q[2].toggle(T("pfb"), key="pfb", help=T("pfb_help"))
            if "dfb" not in ss:
                ss["dfb"] = True
            ctx.dfb = q[3].toggle(T("dfb"), key="dfb", help=T("h_dfb"))
            st.markdown(f"**{T('blk_elems')}**", help=T("h_blk_elems"))
            q = st.columns(4)
            ctx.pvfilt = num(T("pvfilt"), "pvfilt", 0.0, q[0], min_value=0.0, help=T("h_pvfilt"))
            mvrate_e = num(T("mvrate", u=ctx.u_mv or "MV"), "mvrate", 0.0, q[1], min_value=0.0, format="%.4g",
                           help=T("h_mvrate"))
            sprate_e = num(T("sprate", u=ctx.u_pv or "PV"), "sprate", 0.0, q[2], min_value=0.0, format="%.4g",
                           help=T("h_sprate"))
    ctx.base_ctrl = dict(SampleTime=ctx.samp, DiffGain=ctx.diffgain, PropFbk=ctx.pfb, DiffFbk=ctx.dfb,
                         DeadBand=db_e / ctx.PR * 100, DbMode="spojité" if db_mode == "cont" else "skokové",
                         MV_Lo=float(ctx.M(ctx.mvl_lo)), MV_Hi=float(ctx.M(ctx.mvl_hi)), PVFilt=ctx.pvfilt,
                         MVRate=mvrate_e / ctx.MR * 100, SPRate=sprate_e / ctx.PR * 100)
    ctx.block_summary = T("blk_summary", s=f"{ctx.samp:g}", dg=f"{ctx.diffgain:g}", p="✓" if ctx.pfb else "✗",
                          d="✓" if ctx.dfb else "✗", g=f"{ss.get('set1_gain', 1.0):.4g}",
                          ti=f"{ss.get('set1_ti', 100.0):.4g}", td=f"{ss.get('set1_td', 0.0):.4g}")


def _nice(x):
    """Zaokrouhlení nahoru na „hezké“ číslo (1, 1,5, 2, 3, 5, 7,5 × 10^n)."""
    if not np.isfinite(x) or x <= 0:
        return x
    e = 10 ** np.floor(np.log10(x))
    return float(next(m * e for m in (1, 1.5, 2, 3, 5, 7.5, 10) if m * e >= x * 0.999))


def auto_sim_length(mcode, p, ctrls, T_char, samp, ts_id):
    """
    Délka simulace scénáře podle dynamiky: 4× nejdelší doba ustálení uzavřené smyčky (sada 1 a 2; skok SP i porucha),
    aby se mezi událostmi (5 %, 40 %, 70 % délky) smyčka vždy ustálila. Když se žádná sada neustálí (nestabilní),
    podle modelu procesu (20× charakteristický čas), nejméně délka úseku identifikace. Vrací (délka [s], zdroj).
    """
    st_ = [cache.settling_time(mcode, tuple(p), {k: v for k, v in c.items() if k not in ("FF", "FF_LL")})
           for c in ctrls if c is not None]
    st_ = [x for x in st_ if x]
    if st_:
        return _nice(max(4 * max(st_), 50 * samp)), "cl"
    t_data = float(ts_id[-1]) if ts_id is not None and len(ts_id) else 0.0
    t_mod = max(20 * T_char, 50 * samp)
    if t_data > 0:      # nevěrohodně pomalý model (časová konstanta ≫ záznam) nesmí dát simulaci na dny
        t_mod = min(t_mod, 20 * t_data)
    return _nice(max(t_mod, t_data)), ("data" if t_data >= t_mod else "model")


def _norm_section(ctx):
    """
    Rozsah regulátoru NormPV / NormMV – nastavení bloku PIDConL (Gain je bezrozměrný: odchylka v % NormPV, MV v % NormMV).
    Data zůstávají v reálných jednotkách; rozsah se zadává podle bloku, ne podle dat. Hodnoty už použila záložka Data
    (přečetla je ze session state), tady jsou pole a kontroly.
    """
    st.markdown(f"**{T('sb_norm')}**", help=T("h_norm"))
    n = st.columns(4)
    num("NormPV Low", "pv_lo", 0.0, n[0], help=T("h_normpv"))
    num("NormPV High", "pv_hi", 100.0, n[1], help=T("h_normpv"))
    num("NormMV Low", "mv_lo", 0.0, n[2], help=T("h_normmv"))
    num("NormMV High", "mv_hi", 100.0, n[3], help=T("h_normmv"))
    if not ctx.norm_ok:
        st.error(T("err_range"), icon=":material/error:")
        return
    pmin, pmax = float(np.nanmin(ctx.pv_e)), float(np.nanmax(ctx.pv_e))
    mmin, mmax = float(np.nanmin(ctx.mv_e)), float(np.nanmax(ctx.mv_e))
    if pmin < ctx.pv_lo or pmax > ctx.pv_hi or mmin < ctx.mv_lo or mmax > ctx.mv_hi:
        st.warning(T("norm_out", pv=f"{pmin:.4g}–{pmax:.4g}", mv=f"{mmin:.4g}–{mmax:.4g}"), icon=":material/warning:")
    elif (ctx.pv_lo, ctx.pv_hi) == (0.0, 100.0):
        st.info(T("norm_pv_default", pv=f"{pmin:.4g}–{pmax:.4g}"), icon=":material/straighten:")
    else:
        st.caption(T("norm_help"))


def render(ctx):
    """Záložka Ladění: doporučení D, metody, sady parametrů, porovnání metod, dopředná vazba, scénář a simulace."""
    H, base_ctrl, c_d, d_id, dfb, diffgain, dists, has_sp, model, model_stic, mv_hi, mv_id, mv_lo, pfb, plant, pv_hi, pv_id, pv_lo, pvfilt, samp, sel_mask, set1_ctrl, set2_ctrl, sigma_pv, sp, ts_id, u_mv, u_pv, unc_models = ctx.H, ctx.base_ctrl, ctx.c_d, ctx.d_id, ctx.dfb, ctx.diffgain, ctx.dists, ctx.has_sp, ctx.model, ctx.model_stic, ctx.mv_hi, ctx.mv_id, ctx.mv_lo, ctx.pfb, ctx.plant, ctx.pv_hi, ctx.pv_id, ctx.pv_lo, ctx.pvfilt, ctx.samp, ctx.sel_mask, ctx.set1_ctrl, ctx.set2_ctrl, ctx.sigma_pv, ctx.sp, ctx.ts_id, ctx.u_mv, ctx.u_pv, ctx.unc_models
    EM, EP, MR, PR, lab_mv, lab_pv, lab_t = ctx.EM, ctx.EP, ctx.MR, ctx.PR, ctx.lab_mv, ctx.lab_pv, ctx.lab_t
    with ctx.tabs["tuning"]:
        if model is None:
            st.info(T("need_model"), icon=":material/arrow_back:")
        else:
            mcode, p, pdl = model
            st.caption(f"{model_name(mcode)} · " + ", ".join(f"{n} = {v:.4g}" for n, v in zip(MODELS[mcode]["params"], p))
                       + " · " + T("samp_note", s=f"{samp:g}", h=f"{samp / 2:g}"))
            apc.tuning_hint(ctx)   # odkaz na záložku APC, když by smyčce pomohla pokročilá struktura
            p_eff = list(p[:-1]) + [p[-1] + samp / 2]
            methods = (["SIMC"] + (["iSIMC"] if mcode in ("P1D", "P2D") else []) + ["Lambda", "AMIGO", "OPT"]
                       + (["AVG"] if integ_gain(mcode, p) is not None and mcode != "P0D" else []))
            mkey = f"method|{mcode}"
            if "pending_tune" in ss:
                m_, c_, cr_ = ss.pop("pending_tune")
                if m_ in methods:
                    ss[mkey], ss["ctype"] = m_, c_
                    if cr_:
                        ss["opt_crit"] = cr_

            # ---- doporučení D složky
            adv = d_advice(mcode, p_eff)
            with st.container(border=True):
                a1, a2 = st.columns([1, 3.2], vertical_alignment="center")
                if adv.get("tau") is not None:
                    a1.metric(T("tau_label"), f"{adv['tau']:.2f}", help=T("tau_help"))
                elif adv.get("ratio") is not None:
                    a1.metric(T("ratio_label"), f"{adv['ratio']:.2f}", help=T("ratio_help"))
                else:
                    a1.metric(T("tau_label"), "—")
                a2.markdown(f"**{T('d_title')}: {adv['rec']}** — {T(adv['key'])}")
                if sigma_pv > 0:
                    a2.caption(T("noise_note", s=f"{sigma_pv * PR / 100:.3g}", u=u_pv or "PV"))

            def corner_models():
                out_ = []
                for kf in (0.8, 1.2):
                    for tf_ in (0.8, 1.3):
                        q = list(p)
                        q[0] *= kf
                        q[-1] *= tf_
                        out_.append(tuple(q))
                return out_

            robust_set = ()
            if ss.get("opt_robust"):
                robust_set = tuple(tuple(q) for q in unc_models[:15]) if unc_models else tuple(corner_models())

            def get_sug(meth, ct, tc_=None, avg_=None, ms_=1.6, hf_=None, crit_="MIGO", tgt_="both", ovs_=0.02):
                if meth == "OPT":
                    starts = []
                    for m0 in ("SIMC", "AMIGO"):
                        r0 = tune(mcode, p, m0, default_tc(mcode, p, samp, m0, ct, diffgain), ct, samp)
                        starts.append((r0["Kc"], r0["Ti"], r0["Td"]))
                    mg = cache.opt_migo(mcode, tuple(p), ct, samp, diffgain, ms_, hf_, tuple(starts), robust_set, pvfilt)
                    if crit_ == "MIGO":
                        return mg
                    starts.append((mg["Kc"], mg["Ti"], mg["Td"]))
                    sb = ss.get("scen_built") if (ss.get("scen_built") or {}).get("mcode") == mcode else None
                    sp_amp, d_amp = (sb["sp_amp"], sb["d_amp"]) if sb else (5.0, 5.0)
                    tg_lin = "both" if tgt_ == "scen" else tgt_
                    lin = cache.opt_time(mcode, tuple(p), ct, samp, diffgain, crit_, tg_lin, ms_, hf_, tuple(starts), robust_set,
                                      ovs_, pfb, dfb, pvfilt, base_ctrl["MVRate"], sp_amp, d_amp)
                    if tgt_ != "scen":
                        return lin
                    if sb is None:
                        return dict(lin, notes=lin["notes"] + [("note_scen_missing", {})])
                    starts.append((lin["Kc"], lin["Ti"], lin["Td"]))
                    cb = dict(base_ctrl, **sb["plant"])
                    return cache.opt_scenario(mcode, tuple(p), tuple(tuple(d) for d in pdl), ct, cb, crit_, sb["h"], sb["sp"],
                                       sb["pv0"], sb["mv0"], tuple(sb["dmeas"]), sb["dmv"], sb["dpv"], ms_, hf_,
                                       tuple(starts), robust_set, ovs_)
                return tune(mcode, p, meth, tc_ if tc_ else default_tc(mcode, p, samp, meth, ct, diffgain), ct, samp, avg_)

            with st.container(border=True):
                c1, c2 = st.columns([2.6, 1])
                method = seg(c1, T("method"), methods, "SIMC", mkey,
                                              format_func=lambda x: T("m_" + x), help=T("method_help")) or "SIMC"
                ctype = seg(c2, T("ctrl_type"), ["PI", "PID"], "PI", "ctype",
                                             help=T("h_ctype")) or "PI"
                avg, tc, ms_max, hf_max = None, None, 1.6, None
                crit, tgt = ss.get("opt_crit") or "MIGO", ss.get("opt_target") or "both"
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
                    crit = seg(st, T("opt_crit"), ["MIGO", "IAE", "ISE", "ITAE", "OVS"], "MIGO", "opt_crit",
                               format_func=lambda x: T("crit_" + x), help=T("h_opt_crit")) or "MIGO"
                    st.caption(T("cdesc_" + crit))
                    if crit != "MIGO":
                        t1_, t2_ = st.columns([1.4, 1])
                        tgt = seg(t1_, T("opt_target"), ["dist", "sp", "both", "scen"], "both", "opt_target",
                                  format_func=lambda x: T("tgt_" + x), help=T("h_opt_target")) or "both"
                        if crit == "OVS":
                            ovs_lim = (seg(t2_, T("opt_ovs"), [0, 2, 5, 10], 2, "opt_ovs", format_func=lambda x: f"{x} %",
                                           help=T("h_opt_ovs")) or 0) / 100
                    o1, o2 = st.columns(2)
                    ms_max = seg(o1, T("opt_ms"), [1.4, 1.6, 1.8, 2.0], 1.6, "opt_ms",
                                                  format_func=lambda x: f"{x:.1f}", help=T("opt_ms_help")) or 1.6
                    if ctype == "PID":
                        num(T("opt_noise", u=u_mv or "MV"), "opt_noise", round(0.01 * MR, 4), o2, min_value=0.0,
                            format="%.4g", help=T("opt_noise_help"))
                    o2.toggle(T("opt_robust"), key="opt_robust",
                              help=T("h_opt_robust_bs") if unc_models else T("h_opt_robust_corner"))
                elif method in ("SIMC", "iSIMC", "Lambda"):
                    tc0 = default_tc(mcode, p, samp, method, ctype, diffgain)
                    tc = sld(st, T("tc"), float(max(0.05 * tc0, 1e-3)), float(10 * tc0), float(tc0),
                             f"tc|{mcode}|{method}|{ctype}", help=T("tc_help"))
            nmax = ss.get("opt_noise", 0.01 * MR)
            hf_max = (nmax / MR * 100) / sigma_pv if (nmax and sigma_pv > 0) else None  # omezení šumu MV (jen PID)
            try:
                with st.spinner(T("optimizing")) if method == "OPT" else nullcontext():
                    sug = get_sug(method, ctype, tc, avg, ms_max, hf_max, crit, tgt, ovs_lim)
            except Exception as ex:
                st.error(T(str(ex)))
                sug = dict(Kc=ss.get("set1_gain", 1.0), Ti=ss.get("set1_ti", 100.0), Td=ss.get("set1_td", 0.0), notes=[])

            st.markdown(f"#### {T('calc_title')}")
            with st.container(border=True):
                r1, r2, r3, r4, r5 = st.columns([1, 1, 1, 1.3, 1.3], vertical_alignment="center")
                r1.metric("Gain", f"{sug['Kc']:.4g}")
                r2.metric("TI", f"{sug['Ti']:.4g} s")
                r3.metric("TD", f"{sug['Td']:.4g} s")
                if r4.button(T("write_s1"), width="stretch", icon=":material/arrow_downward:"):
                    ss["set1_gain"], ss["set1_ti"], ss["set1_td"] = sug["Kc"], sug["Ti"], sug["Td"]
                    st.rerun()
                if r5.button(T("write_s2"), width="stretch", icon=":material/arrow_downward:"):
                    ss["set2_gain"], ss["set2_ti"], ss["set2_td"] = sug["Kc"], sug["Ti"], sug["Td"]
                    st.rerun()
            if sug["notes"]:
                st.info(notes_text(sug["notes"]), icon=":material/lightbulb:")
            if sug["Kc"] < 0:
                st.warning(T("warn_neg_gain"), icon=":material/swap_vert:")
            if "fit" in ss and mcode in ss.fit["res"] and ss.fit["res"][mcode]["fit"] < 70:
                st.warning(T("warn_low_fit"), icon=":material/warning:")
            with st.expander(T("cmp_title"), expanded=False, icon=":material/leaderboard:", key="cmp_open",
                             on_change="rerun") as cmp_exp:
                if cmp_exp.open:  # porovnání (vč. optimalizací) se počítá až po rozbalení
                    T_c = p_eff[-1] + (p[1] if mcode in ("P1D", "P2D", "I1D") else 0) + samp
                    T_cmp = max(25 * T_c, 100 * samp)
                    h_c = max(samp, T_cmp / 6000)
                    n_c = int(T_cmp / h_c) + 1
                    rows, keys = [], []
                    variants = []
                    for m_ in methods:
                        if m_ == "OPT":
                            variants += [("OPT", c_) for c_ in ("MIGO", "IAE", "ISE", "ITAE", "OVS")]
                        else:
                            variants.append((m_, None))
                    with st.spinner(T("optimizing")):
                        for m_, cr_ in variants:
                            if m_ == "AVG" and "avg_dpv" not in ss:
                                continue
                            avg_ = (ss.get("avg_dpv", 1) / PR * 100, ss.get("avg_dmv", 1) / MR * 100) if m_ == "AVG" else None
                            for ct_ in ("PI", "PID"):
                                try:
                                    tg_ = ss.get("opt_target") or "both"
                                    if tg_ == "scen":
                                        tg_ = "both"  # optimalizace na scénáři jen pro vybranou metodu (je pomalejší)
                                    if cr_ == "OVS" and tg_ == "dist":
                                        tg_ = "sp"  # překmit má smysl hlavně u změny SP
                                    s_ = get_sug(m_, ct_, None, avg_, ss.get("opt_ms") or 1.6, hf_max, cr_ or "MIGO", tg_,
                                                 (ss.get("opt_ovs") if ss.get("opt_ovs") is not None else 2) / 100
                                                 if cr_ == "OVS" else 0.02)
                                except Exception:
                                    continue
                                if ct_ == "PID" and s_["Td"] <= 0:
                                    continue  # PID by byl shodný s PI
                                ctrl_ = dict(base_ctrl, Gain=s_["Kc"], TI=s_["Ti"], TD=s_["Td"], FF=[], DeadBand=0.0,
                                             MV_Lo=-1e12, MV_Hi=1e12)
                                rb_ = robustness(mcode, p, ctrl_)
                                label = T("m_" + m_) + (f" · {T('crit_' + cr_)}" if cr_ else "")
                                row = {T("col_method"): label, T("ctrl_type"): ct_, "Gain": float(f"{s_['Kc']:.4g}"),
                                       "TI [s]": float(f"{s_['Ti']:.4g}"), "TD [s]": float(f"{s_['Td']:.4g}"),
                                       "Ms": round(rb_["Ms"], 2) if rb_["stable"] else None}
                                e_sp, e_d = closed_loop_steps(mcode, p, ctrl_, h_c, n_c)
                                ok_ = rb_["stable"] and np.all(np.isfinite(e_sp)) and np.abs(e_sp).max() < 1e3
                                row[T("iae_load")] = float(f"{np.sum(np.abs(e_d)) * h_c:.4g}") if ok_ else None
                                row[T("iae_sp")] = float(f"{np.sum(np.abs(e_sp)) * h_c:.4g}") if ok_ else None
                                row[T("ovs_col")] = round(100 * overshoot_ratio(e_sp), 1) if ok_ else None
                                row[T("noise_col", u=u_mv or "MV")] = (float(f"{mv_noise(ctrl_, sigma_pv) * MR / 100:.3g}")
                                                                       if sigma_pv > 0 else None)
                                row[T("use_col")] = T("use_" + (cr_ or m_))
                                rows.append(row)
                                keys.append((m_, ct_, cr_))
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

            st.markdown(f"#### {T('sets_title')}")
            with st.container(border=True):
                p1, p2 = st.columns(2, gap="large")
                with p1:
                    st.markdown(f"**{T('set_1')}**", help=T("h_set_1"))
                    set1_gain = num("Gain", "set1_gain", ss.get("set1_gain", 1.0), format="%.5g", help=T("h_gain"))
                    q1 = st.columns(2)
                    set1_ti = num("TI [s]", "set1_ti", ss.get("set1_ti", 100.0), q1[0], min_value=0.0, format="%.5g", help=T("h_ti"))
                    set1_td = num("TD [s]", "set1_td", ss.get("set1_td", 0.0), q1[1], min_value=0.0, format="%.5g", help=T("h_td"))
                with p2:
                    st.markdown(f"**{T('set_2')}**", help=T("h_set_2"))
                    set2_gain = num("Gain", "set2_gain", sug["Kc"], format="%.5g", help=T("h_gain"))
                    q2 = st.columns(2)
                    set2_ti = num("TI [s]", "set2_ti", sug["Ti"], q2[0], min_value=0.0, format="%.5g", help=T("h_ti"))
                    set2_td = num("TD [s]", "set2_td", sug["Td"], q2[1], min_value=0.0, format="%.5g", help=T("h_td"))
                
                set1_ctrl = dict(base_ctrl, Gain=set1_gain, TI=set1_ti if set1_ti > 0 else np.inf, TD=set1_td, FF=[])
                set2_ctrl = dict(base_ctrl, Gain=set2_gain, TI=set2_ti if set2_ti > 0 else np.inf, TD=set2_td, FF=[])
            
                rc, rn = robustness(mcode, p, set1_ctrl), robustness(mcode, p, set2_ctrl)
                ctx.PROG["tune"] = 2 if not rn["stable"] else (0 if rn["Ms"] <= 2.0 else 1)
                tbl = pd.DataFrame({
                    T("set_1"): [fmt(set1_gain), fmt(set1_ctrl["TI"]), fmt(set1_td), fmt(rc["Ms"], 3), fmt(rc["GM"], 3),
                                   fmt(rc["PM"], 3), fmt(mv_noise(set1_ctrl, sigma_pv) * MR / 100, 3)],
                    T("set_2"): [fmt(set2_gain), fmt(set2_ctrl["TI"]), fmt(set2_td), fmt(rn["Ms"], 3), fmt(rn["GM"], 3),
                               fmt(rn["PM"], 3), fmt(mv_noise(set2_ctrl, sigma_pv) * MR / 100, 3)]},
                    index=["Gain", "TI [s]", "TD [s]", T("ms"), T("gm"), T("pm"), T("noise_col", u=u_mv or "MV")])
                if unc_models:
                    worst = lambda c_: max(robustness(mcode, q, c_)["Ms"] for q in unc_models)
                    tbl.loc[T("ms_worst")] = [fmt(worst(set1_ctrl), 3), fmt(worst(set2_ctrl), 3)]
            
                st.markdown(f"**{T('robust_title')}**")
                st.dataframe(tbl, width="stretch")
                REPORT["tables"].append((T("rep_tab_tuning"), tbl))
                set1_placeholder = (set1_ctrl["Gain"], set1_ctrl["TI"], set1_ctrl.get("TD", 0.0)) == (1.0, 100.0, 0.0)
                for nm, r in ((T("set_1"), rc), (T("set_2"), rn)):
                    if not r["stable"]:
                        if nm == T("set_1") and set1_placeholder:    # výchozí zástupné hodnoty, ne skutečné nastavení
                            st.info(T("set1_placeholder"), icon=":material/edit:")
                        else:
                            st.error(T("err_unstable", n=nm), icon=":material/error:")
                    
            # dopředná vazba se nastavuje v APC › Dopředná vazba; tady jen stav a promítnutí do simulací
            ffd = ffmod.design(mcode, p, pdl)
            ffmod.save_state(ffd)
            ff, ffll = ffmod.to_ctrl(ffd)
            if pdl:
                on = [f"{dn} ({T('ff_dyn_s') if d['dyn'] else T('ff_static_s')})" for dn, d in zip(c_d, ffd) if d["use"]]
                r_ = st.columns([0.78, 0.22], vertical_alignment="center")
                r_[0].caption(":material/fast_forward: " + (T("ff_status_on", l=", ".join(on)) if on
                                                            else T("ff_status_off")))
                r_[1].button(T("ff_open"), key="g_ff_open", on_click=apc.guide.goto,
                             kwargs=dict(tab="apc", kind="ff"), type="tertiary")
            set1_ctrl["FF"], set1_ctrl["FF_LL"] = ff, ffll
            set2_ctrl["FF"], set2_ctrl["FF_LL"] = ff, ffll
            ss.set2_ctrl = set2_ctrl
            with st.container(border=True):
                scen_opts = ["custom"] + (["replay"] if dists else [])
                scen = seg(st, T("scenario"), scen_opts, "custom", "scen2",
                           format_func=lambda x: T("scen_" + x), help=T("h_scenario")) or "custom"
                T_char = p[-1] + (p[1] if mcode in ("P1D", "P2D", "I1D") else 0) + (tc or 0) + samp
                if scen == "custom":
                    sim_l1, sim_l2, sim_l3 = st.columns([2, 1, 1], vertical_alignment="bottom")
                    T_end_unit = sel(sim_l2, T("time_unit"), ["s", "min", "h"], 0, "sim_len_u")
                    mult = {"s": 1.0, "min": 60.0, "h": 3600.0}[T_end_unit]
                    if "sim_len_auto" not in ss:
                        ss["sim_len_auto"] = True
                    auto_len = sim_l3.toggle(T("sim_len_auto"), key="sim_len_auto", help=T("h_sim_len_auto"))
                    # i návrh (sady mohou mít ještě výchozí hodnoty) – SIMC, ne zvolená metoda: optimalizace na scénáři
                    # závisí na délce simulace a délka na jejím výsledku by se navzájem posouvaly (optimalizace stále znovu)
                    r_ = tune(mcode, p, "SIMC", default_tc(mcode, p, samp, "SIMC", ctype, diffgain), ctype, samp)
                    prop_ctrl = dict(base_ctrl, Gain=r_["Kc"], TI=r_["Ti"] if r_["Ti"] > 0 else np.inf, TD=r_["Td"])
                    t_auto, auto_src = auto_sim_length(mcode, p, (set1_ctrl, set2_ctrl, prop_ctrl), T_char, samp, ts_id)
                    tend_key = f"tend_r|{mcode}"
                    if auto_len or tend_key not in ss:
                        ss[tend_key] = float(f"{t_auto / mult:.4g}")
                    T_end_raw = num(T("sim_len"), tend_key, t_auto / mult, sim_l1, min_value=samp * 10 / mult,
                                    help=T("h_sim_len"), disabled=auto_len)
                    T_end = T_end_raw * mult
                    if auto_len:
                        st.caption(T("sim_len_src_" + auto_src))
                    sdf_key = f"scen_df|{mcode}|{len(c_d)}"
                    edkey = f"scen_ed|{sdf_key}|{ss.lang}"
                    # jiná délka simulace → časy událostí scénáře se poměrně přepočítají (zůstanou na stejném místě)
                    tk_ = f"{sdf_key}|tend"
                    t_prev = ss.get(tk_)
                    ss[tk_] = T_end
                    if sdf_key in ss and t_prev and abs(T_end / t_prev - 1) > 0.02:
                        f_ = T_end / t_prev
                        rows_ = [list(r_) for r_ in ss.get(f"{sdf_key}|last", ss[sdf_key])]
                        for r_ in rows_:
                            for i_ in (4, 5):
                                if r_[i_] is not None:
                                    r_[i_] = round(float(r_[i_]) * f_, 6)
                        ss[sdf_key] = rows_
                        for k_ in (edkey, f"{edkey}|init", f"{sdf_key}|last"):
                            ss.pop(k_, None)
                        st.rerun()
                    # žádaná hodnota simulace „z → na“ v jednotkách PV (výchozí: SP úseku identifikace, +5 % rozsahu)
                    sp_data = float(EP(np.nanmedian(sp[sel_mask]) if has_sp else pv_id[0]))
                    f1_, f2_ = st.columns(2)
                    sp_from = num(T("sim_sp_from", u=u_pv or "PV"), f"sim_sp0|{ctx.fname}", float(f"{sp_data:.5g}"), f1_,
                                  format="%.5g", help=T("h_sim_sp_from"))
                    sp_to = num(T("sim_sp_to", u=u_pv or "PV"), f"sim_sp1|{ctx.fname}",
                                float(f"{sp_data + 0.05 * PR:.5g}"), f2_, format="%.5g", help=T("h_sim_sp_to"))
                    sp_amp_e = float(sp_to - sp_from)
                    ctx.sim_sp0 = sp_from
                    ft_key = f"{sdf_key}|spft"
                    if sdf_key in ss and ss.get(ft_key) not in (None, (sp_from, sp_to)):
                        # změna „z → na“: přepsat skoky SP v tabulce scénáře (amplituda = na − z)
                        rows_ = [list(r_) for r_ in ss.get(f"{sdf_key}|last", ss[sdf_key])]
                        hit = False
                        for r_ in rows_:
                            if r_[1] == "SP" and r_[2] == "step" and not hit:
                                r_[3], hit = round(sp_amp_e, 6), True
                        if hit:
                            ss[ft_key] = (sp_from, sp_to)
                            ss[sdf_key] = rows_
                            for k_ in (edkey, f"{edkey}|init", f"{sdf_key}|last"):
                                ss.pop(k_, None)
                            st.rerun()
                    ss[ft_key] = (sp_from, sp_to)
                    st.markdown(f"**{T('quick_scen')}**")
                    ps1, ps2, ps3 = st.columns(3)
                    if ps1.button(T("sp_step_base"), width="stretch"):
                        ss[sdf_key] = [[True, "SP", "step", round(sp_amp_e, 6), round(0.05 * T_end), None, None, None]]
                        ss.pop(edkey, None); ss.pop(f"{edkey}|init", None); ss.pop(f"{sdf_key}|last", None)
                        st.rerun()
                    if ps2.button(T("sp_step_dist"), width="stretch"):
                        ss[sdf_key] = [[True, "SP", "step", round(sp_amp_e, 6), round(0.05 * T_end), None, None, None],
                                       [True, "IN", "step", round(0.05 * MR, 4), round(0.4 * T_end), None, None, None]]
                        ss.pop(edkey, None); ss.pop(f"{edkey}|init", None); ss.pop(f"{sdf_key}|last", None)
                        st.rerun()
                    if ps3.button(T("pv_noise_real"), width="stretch"):
                        ss[sdf_key] = [[True, "SP", "step", round(sp_amp_e, 6), round(0.05 * T_end), None, None, None],
                                       [True, "PV", "noise", round(sigma_pv * PR / 100, 4), 0.0, None, None, None]]
                        ss.pop(edkey, None); ss.pop(f"{edkey}|init", None); ss.pop(f"{sdf_key}|last", None)
                        st.rerun()
                else:
                    T_end = float(ts_id[-1])
                    st.caption(T("replay_help"))
                s1_, s2_, s3_ = st.columns(3)
                robust_on = s1_.toggle(T("robust_on"), key="robust_on", help=T("h_robust_on"))
                spread_on = s2_.toggle(T("spread_on"), key="spread_on", help=T("h_spread_on"),
                                       disabled=not unc_models) and bool(unc_models)
                if "ff_cmp" not in ss:
                    ss["ff_cmp"] = True
                ff_cmp = s3_.toggle(T("ff_cmp"), key="ff_cmp", help=T("h_ff_cmp"), disabled=not any(ff)) and any(ff)

            # ---- definice scénáře (tabulka událostí)
            tg_codes = ["SP", "IN", "PV"] + [f"M{j}" for j in range(len(c_d))]
            ty_codes = ["step", "ramp", "sine", "pulse", "rpulse", "noise"]

            def tg_label(c_, lang=None):
                tx = TEXTS[lang or ss.lang]
                return tx["tg_" + c_] if c_[0] != "M" else f"{tx['tg_M']}: {c_d[int(c_[1:])]}"

            tg_map = {tg_label(c_, lg): c_ for c_ in tg_codes for lg in ("cs", "en")}
            ty_map = {TEXTS[lg]["ty_" + c_]: c_ for c_ in ty_codes for lg in ("cs", "en")}
            if scen == "custom":
                with st.expander(T("scen_title"), expanded=True, icon=":material/timeline:"):
                    sdf_key = f"scen_df|{mcode}|{len(c_d)}"
                    if sdf_key not in ss:
                        rows_ = [[True, "SP", "step", round(sp_amp_e, 6), round(0.05 * T_end), None, None, None],
                                 [True, "IN", "step", round(0.05 * MR, 4), round(0.4 * T_end), None, None, None]]
                        rows_ += [[True, f"M{j}", "step", 1.0, round((0.7 + 0.05 * j) * T_end), None, None, None]
                                  for j in range(len(c_d))]
                        ss[sdf_key] = rows_
                    edkey = f"scen_ed|{sdf_key}|{ss.lang}"
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
                    last_ = []
                    for _, row in sdf.iterrows():
                        tgc_, tyc_ = tg_map.get(str(row.get("target"))), ty_map.get(str(row.get("type")))
                        if tgc_ and tyc_:
                            last_.append([bool(row.get("on", True)), tgc_, tyc_] +
                                         [None if pd.isna(row.get(c_)) else float(row.get(c_))
                                          for c_ in ("amp", "start", "end", "period", "tau")])
                    ss[f"{sdf_key}|last"] = last_
            # ---- proces a ventil v simulaci
            with st.expander(T("plant_title"), icon=":material/water_drop:"):
                st.caption(T("plant_help"))
                v1, v2, v3 = st.columns(3)
                S_def = model_stic * MR / 100
                S_e = num(T("sim_stic", u=u_mv or "MV"), f"sim_S|{mcode}|{S_def:.4g}", S_def, v1, min_value=0.0,
                          format="%.4g", help=T("h_sim_stic"))
                J_pct = num(T("sim_slip"), "sim_J", 100.0, v2, min_value=0.0, max_value=100.0, help=T("h_sim_slip"))
                noise_e = num(T("sim_noise", u=u_pv or "PV"), "sim_noise", 0.0, v3, min_value=0.0, format="%.4g",
                              help=T("h_sim_noise", s=f"{sigma_pv * PR / 100:.3g}"))
                st.markdown(f"**{T('vchar_title')}**", help=T("h_vchar"))
                if "vchar_init" not in ss:
                    ss["vchar_init"] = [1.0] * 10
                vc1, vc2 = st.columns([1, 1.6])
                vdf = vc1.data_editor(
                    pd.DataFrame({"band": [f"{10 * i}–{10 * i + 10}" for i in range(10)], "gain": ss["vchar_init"]}),
                    key="vchar_ed", hide_index=True, width="stretch", disabled=["band"],
                    column_config={"band": st.column_config.TextColumn(T("vchar_band", u=u_mv or "MV")),
                                   "gain": st.column_config.NumberColumn(T("vchar_gain"), min_value=0.0, format="%.3g")})
                try:
                    vgains = [float(x) if not pd.isna(x) else 1.0 for x in vdf["gain"].tolist()]
                except Exception:
                    vgains = [1.0] * 10
                ss["vchar_last"] = vgains
                xs_ = np.linspace(0, 100, 101)
                cum_ = np.r_[0.0, np.cumsum(np.array(vgains) * 10.0)]
                ys_ = [cum_[min(int(x_ // 10), 9)] + vgains[min(int(x_ // 10), 9)] * (x_ - 10 * min(int(x_ // 10), 9))
                       for x_ in xs_]
                fvc = go.Figure(go.Scatter(x=xs_, y=ys_, mode="lines", line=dict(color=C_MV, width=2)))
                fvc.add_trace(go.Scatter(x=[0, 100], y=[0, 100], mode="lines", line=dict(color="#94a3b8", dash="dot")))
                style(fvc, 260, rev="vchar")
                fvc.update_layout(showlegend=False, xaxis_title=T("vchar_x"), yaxis_title=T("vchar_y"), hovermode="closest")
                with vc2:
                    show(fvc, key="chart_vchar", fname="valve_characteristic")
            plant = dict(Stic=S_e / MR * 100, SticJ=S_e / MR * 100 * J_pct / 100, Noise=noise_e / PR * 100,
                         ValveChar=vgains, Seed=7)

            m_sub = max(1, min(10, int(20000 * samp / T_end)))
            h = samp / m_sub
            n = int(T_end / h) + 1
            ts_sim = np.arange(n) * h
            pv0 = float(np.nanmedian(sp[sel_mask])) if has_sp else float(pv_id[0])
            if scen == "custom":
                pv0 = float(ctx.P(ctx.sim_sp0))     # počáteční SP (a PV) simulace = „SP z“
            mv0 = float(mv_id[0])
            if not (base_ctrl["MV_Lo"] - 1e-9 <= mv0 <= base_ctrl["MV_Hi"] + 1e-9):
                st.warning(T("sim_mv0_out", m=f"{EM(mv0):.4g}", lo=f"{ctx.mvl_lo:g}", hi=f"{ctx.mvl_hi:g}",
                             u=u_mv or "MV"), icon=":material/warning:")
            spv = np.full(n, pv0)
            dmv_arr, dpv_arr = np.zeros(n), np.zeros(n)
            dmeas = [np.zeros(n) for _ in c_d]
            sp_amp = d_amp = 0.0
            if scen == "custom":
                for ri, row in sdf.iterrows():
                    if not bool(row.get("on", True)) or pd.isna(row.get("amp")):
                        continue
                    tgc = tg_map.get(str(row.get("target")))
                    tyc = ty_map.get(str(row.get("type")))
                    if tgc is None or tyc is None:
                        continue
                    amp = float(row["amp"])
                    t0_ = float(row["start"]) if not pd.isna(row.get("start")) else 0.0
                    t1_ = float(row["end"]) if not pd.isna(row.get("end")) and float(row["end"]) > t0_ else np.inf
                    per = float(row["period"]) if not pd.isna(row.get("period")) and float(row["period"]) > 0 else \
                        max((min(t1_, T_end) - t0_) / 4, 10 * h)
                    tau = float(row["tau"]) if not pd.isna(row.get("tau")) else 0.0
                    act = (ts_sim >= t0_) & (ts_sim < t1_)
                    sig_ = np.zeros(n)
                    if tyc == "step":
                        sig_[act] = amp
                    elif tyc == "ramp":
                        dur = (t1_ - t0_) if np.isfinite(t1_) else per
                        sig_ = amp * np.clip((ts_sim - t0_) / max(dur, h), 0, 1)
                    elif tyc == "sine":
                        sig_[act] = amp * np.sin(2 * np.pi * (ts_sim[act] - t0_) / per)
                    elif tyc == "pulse":
                        sig_[act] = amp * (((ts_sim[act] - t0_) % per) < per / 2)
                    elif tyc == "rpulse":
                        rg = np.random.default_rng(100 + ri)
                        tp = t0_
                        while tp < min(t1_, T_end):
                            tp += rg.exponential(per)
                            w_ = (ts_sim >= tp) & (ts_sim < tp + per / 2) & act
                            sig_[w_] = amp * rg.choice([-1.0, 1.0])
                            tp += per / 2
                    elif tyc == "noise":
                        sig_[act] = np.random.default_rng(200 + ri).normal(0, abs(amp), act.sum())
                    if tau > 0:
                        sig_ = lag(sig_, tau, h)
                    if tgc == "SP":
                        spv = spv + sig_ / PR * 100
                        sp_amp = max(sp_amp, abs(amp) / PR * 100)
                    elif tgc == "IN":
                        dmv_arr = dmv_arr + sig_ / MR * 100
                        d_amp = max(d_amp, abs(amp) / MR * 100)
                    elif tgc == "PV":
                        dpv_arr = dpv_arr + sig_ / PR * 100
                    else:
                        dmeas[int(tgc[1:])] = dmeas[int(tgc[1:])] + sig_
            else:
                dmeas = [np.interp(ts_sim, ts_id, d - d[0]) for d in d_id]
            ss["scen_built"] = dict(mcode=mcode, h=h, sp=spv, pv0=pv0, mv0=mv0, dmeas=dmeas, dmv=dmv_arr, dpv=dpv_arr,
                                    plant=plant, sp_amp=sp_amp or 5.0, d_amp=d_amp or 5.0)

            def run(ctrl, pp=p):
                return pidconl_sim_full(mcode, pp, pdl, h, spv, pv0, mv0, dict(ctrl, **plant), dmeas, dmv_arr, dpv_arr)

            sims = {T("set_1"): (run(set1_ctrl), C_SET1, "dot"), T("set_2"): (run(set2_ctrl), C_SET2, None)}
            if robust_on:
                pp = list(p)
                pp[0] *= 1.3
                pp[-1] *= 1.5
                sims[T("new_err")] = (run(set2_ctrl, pp), C_SET2, "dash")
            ff_moves = any(g and np.any(d != 0) for g, d in zip(ff, dmeas))
            if ff_cmp and ff_moves:      # stejná sada 2 bez dopředné vazby – rozdíl = přínos FF
                sims[T("set2_noff")] = (run(dict(set2_ctrl, FF=[0.0] * len(ff), FF_LL=[(0.0, 0.0, 0.0)] * len(ff))),
                                        "#9aa5b1", "dashdot")
            elif ff_cmp and not ff_moves:
                st.caption(T("ff_cmp_nodist"))

            has_d = any(np.any(d != 0) for d in dmeas) or np.any(dmv_arr != 0) or np.any(dpv_arr != 0)
            nr = 3 if has_d else 2
            fig = mkfig(nr, [0.55, 0.25, 0.2] if nr == 3 else [0.62, 0.38])
            if spread_on:
                for i_, q in enumerate(unc_models[:10]):
                    rq = run(set2_ctrl, list(q))
                    if np.all(np.isfinite(rq["PV"])) and np.abs(rq["PV"]).max() < 1e5:
                        fig.add_trace(tr(rq["t"], EP(rq["PV"]), T("unc_variants"), "#86efac", 1.0, show=i_ == 0, group="spread",
                                         opacity=0.7), 1, 1)
                        fig.add_trace(tr(rq["t"], EM(rq["MV"]), T("unc_variants"), "#86efac", 1.0, show=False, group="spread",
                                         opacity=0.7), 2, 1)
            fig.add_trace(tr(ts_sim, EP(spv), "SP", C_SP, 1.4, "dash", "hv"), 1, 1)
            kp = []
            for nm, (rs_, col, dash) in sims.items():
                Pv, Mv, S_ = rs_["PV"], rs_["MV"], rs_["SPr"]
                if not (np.all(np.isfinite(Pv)) and np.abs(Pv).max() < 1e5):
                    st.error(T("err_sim_unstable", n=nm), icon=":material/error:")
                    continue
                fig.add_trace(tr(rs_["t"], EP(Pv), f"{nm}", col, 2.0, dash, group=nm), 1, 1)
                fig.add_trace(tr(rs_["t"], EM(Mv), f"MV {nm}", col, 2.0, dash, show=False, group=nm), 2, 1)
                if plant["Stic"] > 0:
                    fig.add_trace(tr(rs_["t"], EM(rs_["V"]), f"{T('valve_pos')} {nm}", col, 1.0, "dot", shape="hv",
                                     show=False, group=nm, opacity=0.8), 2, 1)
                kp.append({T("setting"): nm, "IAE [%·s]": f"{iae(rs_['t'], S_, Pv):.4g}",
                           T("kpi_maxdev", u=u_pv or "PV"): f"{np.abs(Pv - S_).max() * PR / 100:.4g}",
                           T("kpi_mvrange", u=u_mv or "MV"): f"{(Mv.max() - Mv.min()) * MR / 100:.4g}",
                           T("kpi_mvtravel", u=u_mv or "MV"): f"{np.abs(np.diff(Mv)).sum() * MR / 100:.4g}",
                           T("kpi_rev"): int(np.sum(np.diff(np.sign(np.diff(rs_["V"])[np.abs(np.diff(rs_["V"])) > 1e-9])) != 0))})
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
            show(style(fig, H, ytit, lab_t, rev=f"sim|{scen}"), key="chart_sim", fname="simulation",
                 report=T("rep_fig_sim"))
            if kp:
                st.dataframe(pd.DataFrame(kp).set_index(T("setting")), width="stretch")
                REPORT["tables"].append((T("rep_tab_kpi"), pd.DataFrame(kp).set_index(T("setting"))))
                st.caption(T("kpi_help"))
            REPORT["tuning"] = dict(model=model_name(mcode), params=dict(zip(MODELS[mcode]["params"], p)),
                                    method=T("m_" + method) + (f" · {T('crit_' + crit)}" if method == "OPT" else ""),
                                    ctype=ctype, notes=notes_text(sug["notes"]), adv=f"{adv['rec']} — {T(adv['key'])}")

            out = {"model": mcode, **{f"model_{n_}": v for n_, v in zip(MODELS[mcode]["params"], p)},
                   "method": method, "controller": ctype, "tc": tc,
                   "NormPV": f"{pv_lo}..{pv_hi}", "NormMV": f"{mv_lo}..{mv_hi}", "SampleTime": samp,
                   "Gain": set2_gain, "TI": set2_ti, "TD": set2_td, "DiffGain": diffgain,
                   "Ms": rn["Ms"], "GM": rn["GM"], "PM": rn["PM"],
                   "Gain_old": set1_gain, "TI_old": set1_ti, "TD_old": set1_td}
            for j, dn in enumerate(c_d):
                out.update({f"{n_}_{dn}": v for n_, v in zip(DIST_PARAMS, pdl[j])})
                out[f"FF_{dn}"] = ff[j] if ff else 0.0
            st.download_button(T("download"), pd.DataFrame([out]).to_csv(index=False, sep=";", decimal=","),
                               "pidconl_tuning.csv", "text/csv", icon=":material/download:")
    ctx.plant = plant
    ctx.set1_ctrl = set1_ctrl
    ctx.set2_ctrl = set2_ctrl
