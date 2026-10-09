"""Záložka Model: identifikace (neměřené poruchy, znaménko, stikce), úprava a fixace parametrů, hodnocení, ověření, nejistota."""
import html

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from ...core import (DIST_PARAMS, MODELS, bootstrap_models, dyn_scale, model_metrics, predict,
                     step_response)
from ...i18n import T
from .. import cache
from ..cache import pidconl_sim
from ..charts import REPORT, mkfig, show, style, tr
from ..theme import C_MODEL, C_MV, C_PV, C_SET1, C_SET2, C_SP, _c_edit
from ..widgets import model_name, num, seg, sld
from ...app import closedloop as cl_mod
from ...app import model as mdl
from ...app.loop import set_ctrl

ss = st.session_state

def _rescale_fit_state(old_key, new_key, c_d):
    """
    Přepočet uložených modelů (a ručních úprav, nejistoty) na nové rozsahy NormPV / NormMV. Model v reálných
    jednotkách je stejný – mění se jen K v %/%, Kd a stikce v %; časy zůstávají.
    """
    ss.fit["res"], (fK, fKd, fS) = mdl.rescale_results(ss.fit["res"], old_key[mdl.NORM], new_key[mdl.NORM])
    for c in list(ss.fit["res"]):
        if f"ed|{c}|0" in ss:
            ss[f"ed|{c}|0"] = float(ss[f"ed|{c}|0"]) * fK
        for j in range(len(c_d)):
            if f"ed|{c}|d{j}|0" in ss:
                ss[f"ed|{c}|d{j}|0"] = float(ss[f"ed|{c}|d{j}|0"]) * fKd
        if f"ed|{c}|stic" in ss:
            ss[f"ed|{c}|stic"] = float(ss[f"ed|{c}|stic"] or 0.0) * fS
    ss.fit["key"] = new_key
    unc = ss.get("unc")
    if unc and unc.get("key") == old_key:
        ss.unc = dict(unc, key=new_key, ps=[[q[0] * fK] + list(q[1:]) for q in unc["ps"]])


def _estimate_set1(sp, pv, mv, h):
    """Callback: Set 1 = PI regulátor odhadnutý ze záznamu (úsek identifikace)."""
    est = cl_mod.estimate_ctrl(sp, pv, mv, h)
    if not est["ok"]:
        ss["idm_est_msg"] = ("warning", T("idm_est_fail"))
        return
    ss["set1_gain"], ss["set1_td"] = float(est["gain"]), 0.0
    ss["set1_ti"] = float(est["ti"]) if np.isfinite(est["ti"]) else 1e9
    ss["idm_est_msg"] = ("info", T("idm_est_done", g=f"{est['gain']:.4g}", ti=f"{est['ti']:.4g}", r=f"{est['r2']:.2f}"))


def _set1_check(ctx, ts_id, pv_id, mv_id, d_id, Ts, sel_mask):
    """Režim „smyčka v AUTO“: sedí Set 1 s regulátorem v záznamu? + tlačítko odhadu Set 1 ze záznamu."""
    sp_id = ctx.sp[sel_mask]
    fit = ss.get("fit") or {}
    mc = ss.get("mcode")
    if mc in fit.get("res", {}):
        r = fit["res"][mc]
        ctrl = set_ctrl(ctx.base_ctrl, ss.get("set1_gain", 1.0), ss.get("set1_ti", 100.0), ss.get("set1_td", 0.0))
        chk = cl_mod.check_set1(mc, r["p"], r["pdl"], ts_id, sp_id, pv_id, mv_id, d_id, Ts, ctrl, pidconl_sim)
        if not chk["ok"]:
            st.warning(T("idm_set1_bad", f=f"{chk['fit_pv']:.0f}") if chk["stable"] else T("idm_set1_unstable"),
                       icon=":material/rule:")
        else:
            st.caption("✅ " + T("idm_set1_ok", f=f"{chk['fit_pv']:.0f}"))
    st.button(T("idm_est_btn"), key="g_idm_est", icon=":material/auto_fix_high:", help=T("h_idm_est"),
              width="stretch", on_click=_estimate_set1, args=(sp_id, pv_id, mv_id, Ts))
    msg = ss.pop("idm_est_msg", None)
    if msg:
        (st.info if msg[0] == "info" else st.warning)(msg[1])


def render(ctx):
    """Záložka Model (rozložení jako desktop): vlevo záznam, tabulka modelů a grafy, vpravo identifikace a model."""
    Ts, c_d, c_mv, c_pv, d_id, dists, fname, long_fmt, model, model_Th, model_level, model_stic, mv, mv_hi, mv_id, mv_lo, pv, pv_hi, pv_id, pv_lo, rng, sel_mask, t, ts_id, u_mv, u_pv = ctx.Ts, ctx.c_d, ctx.c_mv, ctx.c_pv, ctx.d_id, ctx.dists, ctx.fname, ctx.long_fmt, ctx.model, ctx.model_Th, ctx.model_level, ctx.model_stic, ctx.mv, ctx.mv_hi, ctx.mv_id, ctx.mv_lo, ctx.pv, ctx.pv_hi, ctx.pv_id, ctx.pv_lo, ctx.rng, ctx.sel_mask, ctx.t, ctx.ts_id, ctx.u_mv, ctx.u_pv
    MR, PR, lab_pv, lab_t = ctx.MR, ctx.PR, ctx.lab_pv, ctx.lab_t
    ws = ctx.mws

    def reset_edits(code):
        r = ss.fit["res"][code]
        for i, v in enumerate(r["p"]):
            ss[f"ed|{code}|{i}"] = float(v)
        for j, pd_ in enumerate(r["pdl"]):
            for i, v in enumerate(pd_):
                ss[f"ed|{code}|d{j}|{i}"] = float(v)
        ss[f"ed|{code}|stic"] = float(r.get("stic", 0.0) or 0.0)

    model = None
    sigma_pv = 0.0
    model_stic, model_level, model_Th = 0.0, "none", None
    seg_extra, seg_resid = [], None
    with ctx.tabs["model"]:
        # ---- 2 · identifikace (panel)
        with ws.ident:
            if "chosen" not in ss:
                ss["chosen"] = list(MODELS)
            id_mode = seg(st, T("idm"), ["open", "cl"], "open", "id_mode", format_func=lambda x: T("idm_" + x),
                          help=T("h_idm")) or "open"
            closed = id_mode == "cl" and ctx.has_sp
            if id_mode == "cl":
                if not ctx.has_sp:
                    st.warning(T("idm_need_sp"), icon=":material/warning:")
                else:
                    ex_ = cl_mod.excitation(ctx.sp[sel_mask], pv_id, mv_id)
                    st.caption(T("idm_cl_note", g=f"{ss.get('set1_gain', 1.0):.4g}", ti=f"{ss.get('set1_ti', 100.0):.4g}",
                                 td=f"{ss.get('set1_td', 0.0):.4g}"))
                    if not ex_["ok"]:
                        st.warning(T("idm_low_exc"), icon=":material/warning:")
                    _set1_check(ctx, ts_id, pv_id, mv_id, d_id, Ts, sel_mask)
            chosen = st.multiselect(T("models"), list(MODELS), format_func=model_name, key="chosen",
                                    placeholder=T("ms_placeholder"), help=T("h_models"))
            th_max = num(T("thmax"), "thmax", round(0.4 * ts_id[-1], 1), min_value=0.0, help=T("thmax_help"))
            dist_level = seg(st, T("dist_level"), ["none", "medium", "high"], "none", "dist_level",
                             format_func=lambda x: T("dl_" + x), help=T("h_dist_level")) or "none"
            st.caption(T("dl_desc_" + dist_level))
            dist_strength = sld(st, T("dist_strength"), 1, 10, 4, "dist_strength", help=T("h_dist_strength"),
                                disabled=dist_level == "none")
            gain_sign = seg(st, T("gain_sign"), ["auto", "pos", "neg"], "auto", "gain_sign",
                            format_func=lambda x: T("gsg_" + x), help=T("h_gain_sign")) or "auto"
            id_stic = st.toggle(T("id_stic"), key="id_stic", help=T("h_id_stic"))
            win = ctx.win_mode == "inputs"
            dkinds, dsigns = [], []
            if win:                               # přenosy poruch: typ a znaménko zvlášť pro každou poruchu
                for dn in c_d:
                    st.markdown(f"<span class='pid-big'>{T('dist_model')}: <b>{html.escape(str(dn))}</b></span>",
                                unsafe_allow_html=True)
                    k1, k2 = st.columns(2)
                    dkinds.append(k1.selectbox(T("dkind"), ["pv", "auto", "self", "integ"], key=f"dkind|{dn}",
                                               format_func=lambda x: T("dkind_" + x), help=T("h_dkind")))
                    dsigns.append(mdl.SIGN[seg(k2, T("gain_sign"), ["auto", "pos", "neg"], "auto", f"dsign|{dn}",
                                               format_func=lambda x: T("gsg_" + x), help=T("h_dsign")) or "auto"])
                if closed:
                    st.warning(T("win_no_cl"), icon=":material/warning:")
                    closed = False
        with ws.top:
            run_fit = st.button(T("run_fit"), type="primary", icon=":material/play_arrow:", width="stretch")
        sets = mdl.IdSettings(tuple(chosen), th_max, dist_level, dist_strength, gain_sign, id_stic)
        fit_key = mdl.fit_key(fname, rng, sets, (pv_lo, pv_hi, mv_lo, mv_hi), Ts, c_pv, c_mv, c_d, long_fmt)
        if win:
            fit_key = fit_key + ("win", tuple(ctx.win_idx), ctx.excl_key, tuple(dkinds), tuple(dsigns))

        def do_fit(c, fixed=None, stic_fixed=None):
            """Fit jednoho modelu podle nastavení (neměřené poruchy, znaménko, stikce, zafixované parametry)."""
            if win:
                return mdl.identify_windows(c, t, pv, mv, Ts, dists, ctx.win_idx, ctx.valid, sets, dkinds, dsigns,
                                            fixed, fn=cache.fit_windows)
            return mdl.identify(c, ts_id, pv_id, mv_id, Ts, d_id, sets, fixed, stic_fixed, fn=cache.identify)

        if run_fit and win:
            if not ctx.win_idx:
                ws.top.error(T("err_no_windows"))
            else:
                prog = ws.top.progress(0.0, text=T("fitting"))
                res, errs = mdl.identify_windows_all(
                    t, pv, mv, Ts, dists, ctx.win_idx, ctx.valid, sets, dkinds, dsigns, fn=cache.fit_windows,
                    progress=lambda i, c: prog.progress(i / max(len(chosen), 1),
                                                        text=f"{T('fitting')} {model_name(c)} ({i + 1}/{len(chosen)})"))
                prog.empty()
                for c, ex in errs:
                    ws.top.error(f"{model_name(c)}: {T(ex)}")
                if res:
                    ss.fit = dict(key=fit_key, res=res, dnames=list(c_d))
                    for c in res:
                        reset_edits(c)
        elif run_fit:
            if len(ts_id) < 20:
                ws.top.error(T("err_short"))
            else:
                n_ = max(len(chosen), 1) * (2 if closed else 1)
                prog = ws.top.progress(0.0, text=T("fitting"))
                res, errs = mdl.identify_all(
                    ts_id, pv_id, mv_id, Ts, d_id, sets, fn=cache.identify,
                    progress=lambda i, c: prog.progress(i / n_, text=f"{T('fitting')} {model_name(c)} ({i + 1}/{n_})"))
                if res and closed:
                    ctrl_ = {k: v for k, v in ctx.set_ctrl(1).items() if k not in ("FF", "FF_LL")}
                    m0 = len(res)
                    res, e2 = mdl.identify_cl_all(
                        res, ts_id, ctx.sp[sel_mask], pv_id, mv_id, Ts, d_id, ctrl_, sets, fn=cache.identify_cl,
                        progress=lambda i, c: prog.progress((m0 + i) / n_, text=f"{T('idm_cl')}: {model_name(c)}"))
                    errs = errs + e2
                prog.empty()
                for c, ex in errs:
                    ws.top.error(f"{model_name(c)}: {T(ex)}")
                if res:
                    ss.fit = dict(key=fit_key, res=res, dnames=list(c_d))
                    for c in res:
                        reset_edits(c)

        # dofitování volných parametrů (požadavek z tlačítka v minulém běhu – před vykreslením polí)
        if "refit_req" in ss and "fit" in ss:
            rc_ = ss.pop("refit_req")
            if rc_ in ss.fit["res"]:
                names_ = MODELS[rc_]["params"]
                fixed_ = {f"p{i}": float(ss[f"ed|{rc_}|{i}"]) for i in range(len(names_)) if ss.get(f"fx|{rc_}|{i}")}
                for j in range(len(c_d)):
                    for i in range(3):
                        if ss.get(f"fx|{rc_}|d{j}|{i}"):
                            fixed_[f"d{j}_{i}"] = float(ss[f"ed|{rc_}|d{j}|{i}"])
                sfix = float(ss.get(f"ed|{rc_}|stic", 0.0)) if (ss.get(f"fx|{rc_}|stic") or not id_stic) else None
                try:
                    with ws.top, st.spinner(T("fitting")):
                        ss.fit["res"][rc_] = do_fit(rc_, fixed_, sfix)
                    reset_edits(rc_)
                    ss.refit_msg = T("refit_done", n=len(fixed_))
                except Exception as ex:
                    ss.refit_msg = f"{model_name(rc_)}: {T(str(ex))}"

        res = {}
        if "fit" not in ss:
            ws.m_res.info(T("info_fit"), icon=":material/play_circle:")
        else:
            if ss.fit["key"] == "__restore__":  # model obnovený z projektu
                ss.fit["key"] = fit_key
            if mdl.only_norm_changed(ss.fit["key"], fit_key):   # jiný rozsah regulátoru → přepočet, ne nová identifikace
                _rescale_fit_state(ss.fit["key"], fit_key, list(c_d))
                st.toast(T("norm_rescaled"), icon=":material/straighten:")
            res = ss.fit["res"]
            if ss.fit["key"] != fit_key:
                ws.top.warning(T("warn_stale"), icon=":material/update:")
            if ss.fit["dnames"] != list(c_d):
                ws.top.warning(T("warn_dists_changed"), icon=":material/update:")
                res = {}

        if res:
            rows = []
            lvl_fit = next(iter(res.values())).get("level", "none")
            any_stic = any(rr_.get("stic") for rr_ in res.values()) or id_stic
            any_cl = any(rr_.get("method") == "cl" for rr_ in res.values())
            for q in mdl.summary(res, ts_id, pv_id, mv_id, d_id, Ts):
                c = q["code"]
                row = {T("col_model"): model_name(c), "FIT [%]": round(q["FIT"], 1), "NRMSE [%]": round(q["NRMSE"], 2),
                       T("col_status"): T(f"st_{q['status']}")}
                if any_cl:
                    r_ = res[c]
                    row[T("idm_fit_cl")] = (f"PV {r_['fit_cl_pv']:.1f} / MV {r_['fit_cl_mv']:.1f}"
                                            if r_.get("fit_cl_pv") is not None else "—")
                row.update({n: float(f"{v:.4g}") for n, v in zip(MODELS[c]["params"], q["p"])})
                for j, pd_ in enumerate(q["pdl"]):
                    row.update({f"{n} ({c_d[j]})": float(f"{v:.4g}") for n, v in zip(DIST_PARAMS, pd_)})
                if any_stic:
                    row[T("col_stic", u=u_mv or "MV")] = float(f"{q['stic'] * MR / 100:.3g}")
                if lvl_fit != "none":
                    row[T("col_rawfit")] = round(q["fit_raw"], 1)
                if res[c].get("method") == "win":      # úseky podle vstupů: shoda přes úseky a v každém úseku
                    yw_ = cache.predict_windows(c, res[c]["p"], res[c]["pdl"], t, pv, mv, Ts, dists, ctx.win_idx,
                                                ctx.valid)[0]
                    mw_ = np.isfinite(yw_) & (ctx.valid if ctx.valid is not None else True)
                    if mw_.sum() > 20:
                        mq_ = model_metrics(pv[mw_], yw_[mw_], mv[mw_], Ts, dyn_scale(c, res[c]["p"]))
                        row["NRMSE [%]"], row[T("col_status")] = round(mq_["NRMSE"], 2), T(f"st_{mq_['status']}")
                    row["FIT [%]"] = round(res[c]["fit"], 1)
                    for k_, (lab_, f_) in enumerate(zip(_win_labels(ctx), res[c].get("fits", []))):
                        row[lab_] = round(f_, 1)
                    kinds_ = [T("dkind_short_" + ("integ" if mdl_integ_d(c, d_) else "self")) for d_ in res[c]["pdl"]]
                    if kinds_:
                        row[T("dkind")] = ", ".join(kinds_)
                rows.append(row)
            with ws.m_res:
                st.dataframe(pd.DataFrame(rows).set_index(T("col_model")), width="stretch",
                             column_config={"FIT [%]": st.column_config.ProgressColumn("FIT [%]", min_value=0,
                                                                                      max_value=100, format="%.1f")})
                st.caption(T("units_note") + (" " + T("fit_eff_note") if lvl_fit != "none" else "")
                           + (" " + T("idm_table_note") if any_cl else ""))
                for wk, c in mdl.warnings(res, ts_id[-1], th_max):
                    st.warning(T(wk, m=model_name(c)), icon=":material/trending_up:" if wk == "warn_long_T"
                               else ":material/warning:")

            # ---- 3 · model pro ladění (panel)
            best = mdl.best(res)
            with ws.model:
                if ss.get("mcode") not in res:
                    ss["mcode"] = best
                mcode = st.selectbox(T("model_for_tuning"), list(res),
                                     format_func=lambda c: f"{model_name(c)} ({res[c]['fit']:.1f} %)", key="mcode",
                                     help=T("h_model_for_tuning"))
                names = MODELS[mcode]["params"]
                need = [f"ed|{mcode}|{i}" for i in range(len(names))] + [
                    f"ed|{mcode}|d{j}|{i}" for j in range(len(c_d)) for i in range(len(DIST_PARAMS))] + [
                    f"ed|{mcode}|stic"]
                if any(k not in ss for k in need):
                    reset_edits(mcode)
                st.caption(T("fix_help"))
                p_ed = []
                for i, n in enumerate(names):           # parametry pod sebou: hodnota | zafixovat
                    c1_, c2_ = st.columns([3, 1], vertical_alignment="bottom")
                    p_ed.append(c1_.number_input(n, key=f"ed|{mcode}|{i}", min_value=None if i == 0 else 0.0,
                                                 format="%.5g", help=T("help_" + ("gain" if i == 0 else "theta" if i == len(names) - 1 else "T")),
                                                 step=max(abs(ss[f"ed|{mcode}|{i}"]) * 0.05, 1e-6)))
                    c2_.checkbox(T("fix"), key=f"fx|{mcode}|{i}", help=T("h_fix"))
                pdl_ed = []
                for j, dn in enumerate(c_d):
                    st.markdown(f"<span class='pid-big'>{T('dist_model')}: <b>{html.escape(str(dn))}</b></span>",
                                unsafe_allow_html=True)
                    row_ = []
                    for i, n in enumerate(DIST_PARAMS):
                        c1_, c2_ = st.columns([3, 1], vertical_alignment="bottom")
                        row_.append(c1_.number_input(n, key=f"ed|{mcode}|d{j}|{i}", min_value=None if i == 0 else 0.0,
                                                     format="%.5g", help=T("h_dist_" + str(i)),
                                                     step=max(abs(ss[f"ed|{mcode}|d{j}|{i}"]) * 0.05, 1e-6)))
                        c2_.checkbox(T("fix"), key=f"fx|{mcode}|d{j}|{i}", help=T("h_fix"))
                    pdl_ed.append(row_)
                if id_stic or res[mcode].get("stic"):
                    sc1, sc2 = st.columns([2, 1], vertical_alignment="bottom")
                    sc1.number_input(T("stic_param", u="% MV"), key=f"ed|{mcode}|stic", min_value=0.0, format="%.4g",
                                     help=T("h_stic_param"))
                    sc2.checkbox(T("fix"), key=f"fx|{mcode}|stic", help=T("h_fix"))
                b1, b2 = st.columns(2)
                if b1.button(T("refit"), icon=":material/model_training:", help=T("h_refit"), width="stretch"):
                    ss.refit_req = mcode
                    st.rerun()
                b2.button(T("reset_fit"), on_click=reset_edits, args=(mcode,), icon=":material/restart_alt:",
                          width="stretch")
                if ss.get("refit_msg"):
                    st.caption(ss.pop("refit_msg"))
                if res[mcode].get("method") == "cl" and res[mcode].get("p_open"):
                    st.caption(T("idm_open_model", p=", ".join(f"{n} = {v:.4g}" for n, v in
                                                                 zip(names, res[mcode]["p_open"]))))
                fit_box = st.container()
            rp = res[mcode]
            p_c, pdl_c = mdl.clamp(p_ed, pdl_ed)
            model = (mcode, p_c, [d + list(rp["pdl"][j][3:]) for j, d in enumerate(pdl_c)])   # + typ přenosu poruchy
            model_stic = float(ss.get(f"ed|{mcode}|stic", 0.0) or 0.0)
            model_level, model_Th = rp.get("level", "none"), rp.get("Th")
            edited = mdl.is_edited(model[1], model[2], model_stic, rp)
            ev_fit = mdl.evaluate(mcode, rp["p"], rp["pdl"], rp.get("stic", 0.0), model_level, model_Th,
                                  ts_id, pv_id, mv_id, d_id, Ts)
            ev_ed = mdl.evaluate(mcode, model[1], model[2], model_stic, model_level, model_Th, ts_id, pv_id, mv_id, d_id, Ts)
            pf_ed = ev_ed["pf"]
            f_fit, f_ed = ev_fit["fit"], ev_ed["fit"]
            y_fit, y_ed = ev_fit["y_plot"], ev_ed["y_plot"]
            sigma_pv = ev_ed["sigma_pv"]
            mm = ev_ed["metrics"]
            if rp.get("method") == "win":             # shoda a průběh modelu jen v úsecích (každý s vlastním posunem)
                yf_, _, f_fit = cache.predict_windows(mcode, rp["p"], rp["pdl"], t, pv, mv, Ts, dists, ctx.win_idx,
                                                      ctx.valid)
                ye_, _, f_ed = cache.predict_windows(mcode, model[1], model[2], t, pv, mv, Ts, dists, ctx.win_idx,
                                                     ctx.valid)
                y_fit, y_ed = yf_[sel_mask], ye_[sel_mask]
                mw_ = np.isfinite(ye_) & (ctx.valid if ctx.valid is not None else True)
                if mw_.sum() > 20:                       # hodnocení na vzorcích úseků (bez vyřazených)
                    mm = model_metrics(pv[mw_], ye_[mw_], mv[mw_], Ts, dyn_scale(mcode, model[1]))
                    sigma_pv = float(np.std(np.diff(pv[mw_] - ye_[mw_])) / np.sqrt(2))
            ctx.PROG["model"] = 1 if ss.fit["key"] != fit_key else (0 if mm["status"] <= 1 else 1 if mm["status"] <= 3 else 2)
            ctx.PROG["model_stale"] = ss.fit["key"] != fit_key
            m1, m2 = fit_box.columns(2)
            m1.metric(T("fit_fit"), f"{f_fit:.1f} %")
            m2.metric(T("fit_edit"), f"{f_ed:.1f} %", delta=f"{f_ed - f_fit:+.1f} %" if edited else None)

            # ---- grafy modelu (pod-záložky jako v desktopu)
            # model vs. data se kreslí do hlavního grafu záznamu (ctx.seg_chart na konci) – jedna sada grafů
            with ws.model:
                if "show_resid" not in ss:
                    ss["show_resid"] = True
                show_res = st.toggle(T("show_resid"), key="show_resid", help=T("h_resid"))
            seg_extra = [(f"{mcode} {T('fit')}", y_fit, C_MODEL[mcode], None)]
            if edited:
                seg_extra.append((f"{mcode} {T('edited')}", y_ed, _c_edit(), "dash"))
            if model_level == "high" and pf_ed.get("raw") is not None:
                seg_extra.append((T("model_wo_dist"), pf_ed["raw"], "#94a3b8", "dot"))
            seg_resid = True if show_res else None
            labels = [T("step_title"), T("compare_all"), T("eval_title"), T("val_title")]
            if model_level != "none":
                labels.append(T("dk_unmeasured"))
            with ws.m_tabs:
                tabs_ = st.tabs(labels, key="mod_view2", on_change="rerun")
            t_step, t_all, t_eval, t_val = tabs_[:4]
            REPORT["tables"].append((T("rep_tab_models"), pd.DataFrame(rows).set_index(T("col_model"))))

            with t_step:
                ts_a, ya = step_response(mcode, rp["p"])
                ts_b, yb = step_response(mcode, model[1], horizon=ts_a[-1])
                f = go.Figure()
                f.add_trace(tr(ts_a, ya * PR / 100, T("fit"), C_MODEL[mcode], 2.2))
                if edited:
                    f.add_trace(tr(ts_b, yb * PR / 100, T("edited"), _c_edit(), 2.0, "dash"))
                if rp.get("method") == "cl" and rp.get("p_open"):
                    ts_o, yo = step_response(mcode, rp["p_open"], horizon=ts_a[-1])
                    f.add_trace(tr(ts_o, yo * PR / 100, T("idm_open_curve"), "#94a3b8", 1.6, "dot"))
                f.add_vline(x=model[1][-1], line=dict(color="#94a3b8", dash="dot", width=1),
                            annotation_text="θ", annotation_position="top")
                style(f, 420, xtitle=lab_t, rev=f"step|{mcode}")
                f.update_layout(yaxis_title=f"Δ{lab_pv}")
                show(f, key=f"step|{mcode}", fname="step_response", report=T("step_title"))

            with t_all:
                if win:
                    ex = [(f"{c} ({r['fit']:.1f} %)", cache.predict_windows(c, r["p"], r["pdl"], t, pv, mv, Ts, dists,
                                                                             ctx.win_idx, ctx.valid)[0][sel_mask],
                           C_MODEL[c], None) for c, r in res.items()]
                else:
                    ex = [(f"{c} ({r['fit']:.1f} %)", predict(c, r["p"], r["pdl"], ts_id, pv_id, mv_id, d_id, Ts,
                                                               r.get("stic", 0.0))[0], C_MODEL[c], None)
                          for c, r in res.items()]
                show(ctx.data_fig(ts_id, sel_mask, ex), key="chart_all", fname="models")

            # ---- neměřené poruchy: co s daty udělalo potlačení
            if model_level != "none":
                with tabs_[4]:
                    fd = mkfig(1)
                    if model_level == "high":
                        fd.add_trace(tr(ts_id, pf_ed["dist"] * PR / 100, T("dl_est"), "#7c3aed", 2.0), 1, 1)
                    else:
                        fd.add_trace(tr(ts_id, pf_ed["pv"] * PR / 100, T("dl_filtered_pv"), C_PV, 1.3), 1, 1)
                        fd.add_trace(tr(ts_id, pf_ed["yhat"] * PR / 100, T("dl_filtered_model"), C_MODEL[mcode], 2.0), 1, 1)
                    style(fd, 360, [f"Δ{lab_pv}"], lab_t, rev="dl")
                    st.caption(T("dl_view", th=f"{(model_Th or 0):.0f}"))
                    show(fd, key="chart_dl", fname="unmeasured")
                    st.caption(T("dl_view_help_" + model_level))

            # ---- podrobné hodnocení modelu
            with t_eval:
                vkey_ = f"rng_val|{fname}|{t[-1]:.0f}"
                rv_ = ss.get(vkey_)
                segs_eval = [(T("eval_id"), sel_mask, mm)]
                if rv_ and tuple(rv_) != tuple(rng):
                    sv_, tv_ = mdl.segment(t, rv_)
                    if sv_.sum() > 50:
                        ev_v = mdl.evaluate(mcode, model[1], model[2], model_stic, model_level, model_Th, tv_, pv[sv_],
                                            mv[sv_], [d[sv_] for d in dists], Ts)
                        segs_eval.append((T("eval_val"), sv_, ev_v["metrics"]))
                etab = pd.DataFrame({nm_: {
                    "FIT [%]": f"{m_['FIT']:.1f}", "NRMSE [%]": f"{m_['NRMSE']:.2f}",
                    T("eval_iae", u=u_pv or "PV"): f"{m_['IAE'] * PR / 100:.3g}", "R²": f"{m_['R2']:.3f}",
                    T("eval_white"): f"{100 * m_['frac_acf']:.0f} %", T("eval_ccf"): f"{100 * m_['frac_ccf']:.0f} %",
                    T("col_status"): T(f"st_{m_['status']}")} for nm_, _, m_ in segs_eval})
                e1, e2 = st.columns([1, 1.6], gap="large")
                with e1:
                    st.dataframe(etab, width="stretch")
                    REPORT["tables"].append((T("eval_title"), etab))
                    msgs = [T("eval_st_" + str(mm["status"]))]
                    if mm["frac_ccf"] > 0.2:
                        msgs.append(T("eval_ccf_bad"))
                    elif mm["frac_acf"] > 0.5:
                        msgs.append(T("eval_acf_bad"))
                    else:
                        msgs.append(T("eval_res_ok"))
                    if len(segs_eval) == 1:
                        msgs.append(T("eval_no_val"))
                    st.markdown("  \n".join(msgs))
                with e2:
                    fr = make_subplots(rows=1, cols=2, subplot_titles=(T("eval_acf_t"), T("eval_ccf_t")))
                    lags_a = np.arange(1, len(mm["acf"]) + 1) * mm["lag_step"]
                    lags_c = np.arange(0, len(mm["ccf"])) * mm["lag_step"]
                    cola = ["#dc2626" if abs(v) > mm["bound"] else "#1f5fa8" for v in mm["acf"]]
                    colc = ["#dc2626" if abs(v) > mm["bound"] else "#1f5fa8" for v in mm["ccf"]]
                    fr.add_trace(go.Bar(x=lags_a, y=mm["acf"], marker_color=cola, name="ACF", showlegend=False), 1, 1)
                    fr.add_trace(go.Bar(x=lags_c, y=mm["ccf"], marker_color=colc, name="CCF", showlegend=False), 1, 2)
                    for cix in (1, 2):
                        for sg_ in (1, -1):
                            fr.add_hline(y=sg_ * mm["bound"], line=dict(color="#94a3b8", dash="dot", width=1), row=1, col=cix)
                    fr.update_layout(height=300, margin=dict(l=8, r=8, t=30, b=8), hovermode="closest", uirevision="res")
                    fr.update_xaxes(title_text=T("lag_s"))
                    show(fr, key="chart_restest", fname="residual_tests")
                st.caption(T("eval_help"))

            with t_val:
                _validation(ctx, model, model_stic)

            with ws.unc:
                st.caption(T("unc_help"))
                n_bs = int(num(T("unc_n"), "unc_n", 15, min_value=5.0, max_value=50.0, step=1.0, format="%.0f",
                               help=T("h_unc_n")))
                if st.button(T("unc_run"), icon=":material/casino:", width="stretch"):
                    k = int(np.ceil(len(ts_id) / 1500))
                    prog = st.progress(0.0, text=T("unc_running"))
                    bs = bootstrap_models(mcode, ts_id[::k], pv_id[::k], mv_id[::k], Ts * k, [d[::k] for d in d_id],
                                          th_max, {"p": model[1], "pdl": model[2]}, n=n_bs,
                                          progress=lambda f_: prog.progress(f_, text=T("unc_running")))
                    prog.empty()
                    ss.unc = dict(code=mcode, key=fit_key, ps=[b["p"] for b in bs])
                if ss.get("unc") and ss.unc["code"] == mcode and ss.unc["ps"]:
                    un = mdl.uncertainty(ss.unc["ps"], model[1])
                    utab = pd.DataFrame({
                        T("unc_nominal"): [float(f"{v:.4g}") for v in model[1]],
                        T("unc_p05"): [float(f"{v:.4g}") for v in un["p05"]],
                        T("unc_p95"): [float(f"{v:.4g}") for v in un["p95"]],
                        T("unc_rel"): [f"± {v:.0f} %" for v in un["rel"]]},
                        index=MODELS[mcode]["params"])
                    st.dataframe(utab, width="stretch")
                    REPORT["tables"].append((T("unc_title"), utab))
                    fu = go.Figure()
                    hz_ = step_response(mcode, model[1])[0][-1]
                    for i_, pp in enumerate(ss.unc["ps"]):
                        tu, yu = step_response(mcode, pp, horizon=hz_)
                        fu.add_trace(tr(tu, yu * PR / 100, T("unc_variants"), "#94a3b8", 1.0, show=i_ == 0,
                                        group="bs", opacity=0.6))
                    tn, yn = step_response(mcode, model[1], horizon=hz_)
                    fu.add_trace(tr(tn, yn * PR / 100, T("unc_nominal"), C_MODEL[mcode], 2.4))
                    style(fu, 260, xtitle=lab_t, rev="unc")
                    fu.update_layout(yaxis_title=f"Δ{lab_pv}", showlegend=False)
                    show(fu, key="chart_unc", fname="uncertainty", report=T("unc_title"))
                    st.caption(T("unc_after"))

        ctx.seg_chart(seg_extra, seg_resid)     # záznam s úsekem (+ model, rezidua, poruchy) – jedna sada grafů
    unc_models = (ss.unc["ps"] if (model is not None and ss.get("unc") and ss.unc["code"] == model[0]) else [])
    ctx.model = model
    ctx.model_Th = model_Th
    ctx.model_level = model_level
    ctx.model_stic = model_stic
    ctx.sigma_pv = sigma_pv
    ctx.unc_models = unc_models


def mdl_integ_d(code, pd_):
    """Je přenos poruchy integrační (podle typu poruchy, jinak podle modelu MV)?"""
    from ...core import dist_integ
    return dist_integ(MODELS[code]["integ"], pd_)


def _win_labels(ctx):
    """Popisky úseků ve stejném pořadí jako v identifikaci (úseky se sloučí, pokud se překrývají)."""
    from ...core import merge_windows
    owner = []
    for x, ws_ in ctx.wins_s.items():
        for a, b in ws_:
            owner.append((int(np.searchsorted(ctx.t, a)), x))
    out = []
    for a, b in merge_windows(ctx.win_idx, len(ctx.t)):
        names = sorted({x for i_, x in owner if a <= i_ < b})
        out.append(T("win_col", n="+".join(names) or "?", a=f"{ctx.t[a] / 60:.0f}"))
    return out


def _validation(ctx, model, stic):
    """Ověření modelu na jiném úseku: predikce PV z naměřené MV, nebo simulace smyčky se sadou 1/2 na záznamu."""
    t, Ts, pv, mv, sp, dists, rng = ctx.t, ctx.Ts, ctx.pv, ctx.mv, ctx.sp, ctx.dists, ctx.rng
    mcode, p, pdl = model
    st.markdown(T("val_intro"))
    vkey = f"rng_val|{ctx.fname}|{t[-1]:.0f}"
    if "pending_rngv" in ss:
        ss[vkey] = ss.pop("pending_rngv")
    if vkey not in ss:
        ss[vkey] = (0.0, float(t[-1]))
    c1, c2 = st.columns([3, 1.3])
    rv = c1.slider(T("seg_val"), 0.0, float(t[-1]), step=float(max(Ts, t[-1] / 1000)), key=vkey,
                   help=T("h_seg_val"))
    mode = seg(c2, T("val_mode"), ["pred", "cl"], "pred", "val_mode",
               format_func=lambda x: T("val_" + x), help=T("val_mode_help")) or "pred"
    sv, tv = mdl.segment(t, rv)
    if len(tv) < 20:
        st.warning(T("err_short"))
        return
    if mode == "pred":
        yv, fv = predict(mcode, p, pdl, tv, pv[sv], mv[sv], [d[sv] for d in dists], Ts, stic)
        st.metric(T("fit_pred"), f"{fv:.1f} %")
        REPORT["val"] = T("rep_val_pred", f=f"{fv:.1f}")
        ov_ = mdl.overlap(rv, rng)
        ctx.PROG["val"] = 1 if ov_ > 0.5 else (0 if fv >= 70 else 2)
        ctx.PROG["val_same"] = ov_ > 0.5
        show(ctx.data_fig(tv, sv, [(f"{mcode} {T('prediction')}", yv, C_MODEL[mcode], None)]),
             key="chart_val_pred", fname="validation", report=T("rep_fig_val"))
        return
    if not ctx.has_sp:
        st.warning(T("need_sp"))
        return
    which = seg(st, T("val_params"), ["cur", "new"], "cur", "val_which",
                format_func=lambda x: T("val_" + x), help=T("h_val_which")) or "cur"
    ctrl = ctx.set_ctrl(1 if which == "cur" else 2)
    ctrl.update(Stic=stic, ValveChar=ss.get("vchar_last"))
    vr = mdl.validate_cl(mcode, p, pdl, ctrl, tv, sp[sv], pv[sv], mv[sv], [d[sv] for d in dists], Ts, ctx.samp,
                         sim=pidconl_sim)
    if not vr["stable"]:
        st.error(T("err_sim_unstable", n=T("val_" + which)))
        return
    tt, Pv, Mv = vr["t"], vr["PV"], vr["MV"]
    if which == "cur":
        m1, m2 = st.columns(2)
        m1.metric(T("fit_pv"), f"{vr['fit_pv']:.1f} %")
        m2.metric(T("fit_mv"), f"{vr['fit_mv']:.1f} %")
        ctx.PROG["val"] = 0 if vr["fit_pv"] >= 60 else 2
        st.caption(T("val_cl_help"))
    col = C_SET2 if which == "new" else C_SET1
    fig = mkfig(2, [0.62, 0.38])
    fig.add_trace(tr(tv, ctx.EP(sp[sv]), "SP", C_SP, 1.4, "dash"), 1, 1)
    fig.add_trace(tr(tv, ctx.EP(pv[sv]), T("measured"), C_PV, 1.3, group="meas"), 1, 1)
    fig.add_trace(tr(tt, ctx.EP(Pv), T("simulated"), col, 2.2, group="sim"), 1, 1)
    fig.add_trace(tr(tv, ctx.EM(mv[sv]), f"MV {T('measured')}", C_MV, 1.4, group="meas", show=False), 2, 1)
    fig.add_trace(tr(tt, ctx.EM(Mv), f"MV {T('simulated')}", col, 2.2, group="sim", show=False), 2, 1)
    show(style(fig, ctx.H, [ctx.lab_pv, ctx.lab_mv], ctx.lab_t, rev="val"), key="chart_val_cl",
         fname="validation_loop", report=T("rep_fig_val"))
