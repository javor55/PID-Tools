"""Záložka Model: identifikace (neměřené poruchy, znaménko, stikce), úprava a fixace parametrů, hodnocení, ověření, nejistota."""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from ...core import (DIST_PARAMS, MODELS, bootstrap_models, dyn_scale, model_metrics, norm_factors, predict,
                     predict_full, rescale_fit, step_response)
from ...i18n import T
from .. import cache
from ..cache import pidconl_sim
from ..charts import REPORT, mkfig, show, style, tr
from ..theme import C_MODEL, C_MV, C_PV, C_SET1, C_SET2, C_SP, _c_edit
from ..widgets import model_name, num, seg, sld

ss = st.session_state

_NORM = slice(4, 8)   # pozice pv_lo, pv_hi, mv_lo, mv_hi v klíči identifikace (fit_key)


def _only_norm_changed(old, new):
    """Klíč identifikace se liší jen normovacími rozsahy (data, úsek i nastavení stejné)."""
    return (isinstance(old, tuple) and len(old) == len(new) and old != new
            and old[:_NORM.start] == new[:_NORM.start] and old[_NORM.stop:] == new[_NORM.stop:])


def _rescale_fit_state(old_key, new_key, c_d):
    """
    Přepočet uložených modelů (a ručních úprav, nejistoty) na nové rozsahy NormPV / NormMV. Model v reálných
    jednotkách je stejný – mění se jen K v %/%, Kd a stikce v %; časy zůstávají.
    """
    old, new = old_key[_NORM], new_key[_NORM]
    fK, fKd, fS = norm_factors(old, new)
    for c in list(ss.fit["res"]):
        ss.fit["res"][c] = rescale_fit(ss.fit["res"][c], old, new)
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


def render(ctx):
    """Záložka Model."""
    Ts, c_d, c_mv, c_pv, d_id, dists, fname, long_fmt, model, model_Th, model_level, model_stic, mv, mv_hi, mv_id, mv_lo, pv, pv_hi, pv_id, pv_lo, rng, sel_mask, t, ts_id, u_mv, u_pv = ctx.Ts, ctx.c_d, ctx.c_mv, ctx.c_pv, ctx.d_id, ctx.dists, ctx.fname, ctx.long_fmt, ctx.model, ctx.model_Th, ctx.model_level, ctx.model_stic, ctx.mv, ctx.mv_hi, ctx.mv_id, ctx.mv_lo, ctx.pv, ctx.pv_hi, ctx.pv_id, ctx.pv_lo, ctx.rng, ctx.sel_mask, ctx.t, ctx.ts_id, ctx.u_mv, ctx.u_pv
    MR, PR, lab_pv, lab_t = ctx.MR, ctx.PR, ctx.lab_pv, ctx.lab_t


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
    with ctx.tabs["model"]:
        st.markdown(f"#### {T('id_title')}")
        with st.container(border=True):
            c1, c2, c3 = st.columns([3, 1, 1], vertical_alignment="bottom")
            if "chosen" not in ss:
                ss["chosen"] = list(MODELS)
            chosen = c1.multiselect(T("models"), list(MODELS), format_func=model_name, key="chosen",
                                    placeholder=T("ms_placeholder"),
                                    help=T("h_models"))
            th_max = num(T("thmax"), "thmax", round(0.4 * ts_id[-1], 1), c2, min_value=0.0, help=T("thmax_help"))
            run_fit = c3.button(T("run_fit"), type="primary", icon=":material/play_arrow:", width="stretch")
            o1, o2, o3, o4 = st.columns([1.6, 1.1, 1.0, 1.2], vertical_alignment="bottom")
            dist_level = seg(o1, T("dist_level"), ["none", "medium", "high"], "none", "dist_level",
                             format_func=lambda x: T("dl_" + x), help=T("h_dist_level")) or "none"
            dist_strength = sld(o2, T("dist_strength"), 1, 10, 4, "dist_strength", help=T("h_dist_strength"),
                                disabled=dist_level == "none")
            gain_sign = seg(o3, T("gain_sign"), ["auto", "pos", "neg"], "auto", "gain_sign",
                            format_func=lambda x: T("gs_" + x), help=T("h_gain_sign")) or "auto"
            id_stic = o4.toggle(T("id_stic"), key="id_stic", help=T("h_id_stic"))
            st.caption(T("dl_desc_" + dist_level))
        sign_v = {"auto": 0, "pos": 1, "neg": -1}[gain_sign]
        fit_key = (fname, rng, tuple(chosen), th_max, pv_lo, pv_hi, mv_lo, mv_hi, Ts, c_pv, c_mv, tuple(c_d), long_fmt,
                   dist_level, dist_strength, gain_sign, id_stic)
        k_dec = int(np.ceil(len(ts_id) / 2500))

        fit_args = (ts_id, pv_id, mv_id, Ts, d_id, th_max)
        fit_kw = dict(level=dist_level, strength=float(dist_strength), sign=sign_v, id_stic=id_stic, k=k_dec)

        def do_fit(c, fixed=None, stic_fixed=None):
            """Fit jednoho modelu podle nastavení (neměřené poruchy, znaménko, stikce, zafixované parametry)."""
            return cache.identify(c, *fit_args, fixed=fixed, stic_fixed=stic_fixed, **fit_kw)

        if run_fit:
            if len(ts_id) < 20:
                st.error(T("err_short"))
            else:
                res = {}
                prog = st.progress(0.0, text=T("fitting"))
                for i, c in enumerate(chosen):
                    prog.progress(i / max(len(chosen), 1), text=f"{T('fitting')} {model_name(c)} ({i + 1}/{len(chosen)})")
                    try:
                        res[c] = do_fit(c)
                    except Exception as ex:
                        st.error(f"{model_name(c)}: {T(str(ex))}")
                prog.empty()
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
                    with st.spinner(T("fitting")):
                        ss.fit["res"][rc_] = do_fit(rc_, fixed_, sfix)
                    reset_edits(rc_)
                    ss.refit_msg = T("refit_done", n=len(fixed_))
                except Exception as ex:
                    ss.refit_msg = f"{model_name(rc_)}: {T(str(ex))}"

        res = {}
        if "fit" not in ss:
            st.info(T("info_fit"), icon=":material/play_circle:")
        else:
            if ss.fit["key"] == "__restore__":  # model obnovený z projektu
                ss.fit["key"] = fit_key
            if _only_norm_changed(ss.fit["key"], fit_key):   # jiný rozsah regulátoru → přepočet, ne nová identifikace
                _rescale_fit_state(ss.fit["key"], fit_key, list(c_d))
                st.toast(T("norm_rescaled"), icon=":material/straighten:")
            res = ss.fit["res"]
            if ss.fit["key"] != fit_key:
                st.warning(T("warn_stale"), icon=":material/update:")
            if ss.fit["dnames"] != list(c_d):
                st.warning(T("warn_dists_changed"), icon=":material/update:")
                res = {}

        if res:
            rows = []
            lvl_fit = next(iter(res.values())).get("level", "none")
            for c, r in res.items():
                pf_ = predict_full(c, r["p"], r["pdl"], ts_id, pv_id, mv_id, d_id, Ts, r.get("stic", 0.0),
                                   r.get("level", "none"), r.get("Th"))
                mm_ = model_metrics(pf_["pv"], pf_["yhat"], mv_id, Ts, dyn_scale(c, r["p"]))
                row = {T("col_model"): model_name(c), "FIT [%]": round(mm_["FIT"], 1), "NRMSE [%]": round(mm_["NRMSE"], 2),
                       T("col_status"): T(f"st_{mm_['status']}")}
                row.update({n: float(f"{v:.4g}") for n, v in zip(MODELS[c]["params"], r["p"])})
                for j, pd_ in enumerate(r["pdl"]):
                    row.update({f"{n} ({c_d[j]})": float(f"{v:.4g}") for n, v in zip(DIST_PARAMS, pd_)})
                if any(rr_.get("stic") for rr_ in res.values()) or id_stic:
                    row[T("col_stic", u=u_mv or "MV")] = float(f"{(r.get('stic') or 0.0) * MR / 100:.3g}")
                if lvl_fit != "none":
                    row[T("col_rawfit")] = round(r.get("fit_raw", r["fit"]), 1)
                rows.append(row)
            st.dataframe(pd.DataFrame(rows).set_index(T("col_model")), width="stretch",
                         column_config={"FIT [%]": st.column_config.ProgressColumn("FIT [%]", min_value=0, max_value=100,
                                                                                  format="%.1f")})
            st.caption(T("units_note") + (" " + T("fit_eff_note") if lvl_fit != "none" else ""))
            for c, r in res.items():
                if c in ("P1D", "P2D") and r["p"][1] > ts_id[-1]:
                    st.warning(T("warn_long_T", m=model_name(c)), icon=":material/trending_up:")
                if r["p"][-1] >= 0.98 * th_max and "p" + str(len(r["p"]) - 1) not in r.get("fixed", []):
                    st.warning(T("warn_theta_max", m=model_name(c)), icon=":material/warning:")

            st.markdown(f"#### {T('edit_title')}")
            best = max(res, key=lambda c: res[c]["fit"])
            c1, c2 = st.columns([1.15, 1], gap="large")
            with c1:
                with st.container(border=True):
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
                    cc = st.columns(len(names))
                    p_ed = []
                    for i, n in enumerate(names):
                        p_ed.append(cc[i].number_input(n, key=f"ed|{mcode}|{i}", min_value=None if i == 0 else 0.0,
                                                       format="%.5g", help=T("help_" + ("gain" if i == 0 else "theta" if i == len(names) - 1 else "T")),
                                                       step=max(abs(ss[f"ed|{mcode}|{i}"]) * 0.05, 1e-6)))
                        cc[i].checkbox(T("fix"), key=f"fx|{mcode}|{i}", help=T("h_fix"))
                    pdl_ed = []
                    for j, dn in enumerate(c_d):
                        st.markdown(f"<span class='pid-big'>{T('dist_model')}: <b>{dn}</b></span>", unsafe_allow_html=True)
                        cc = st.columns(len(DIST_PARAMS))
                        row_ = []
                        for i, n in enumerate(DIST_PARAMS):
                            row_.append(cc[i].number_input(n, key=f"ed|{mcode}|d{j}|{i}", min_value=None if i == 0 else 0.0,
                                                           format="%.5g", help=T("h_dist_" + str(i)),
                                                           step=max(abs(ss[f"ed|{mcode}|d{j}|{i}"]) * 0.05, 1e-6)))
                            cc[i].checkbox(T("fix"), key=f"fx|{mcode}|d{j}|{i}", help=T("h_fix"))
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
            for i in range(1, len(p_ed)):
                p_ed[i] = max(p_ed[i], 1e-6) if i < len(p_ed) - 1 else max(p_ed[i], 0.0)
            for pd_ in pdl_ed:
                pd_[1] = max(pd_[1], 1e-6)
            model = (mcode, [float(v) for v in p_ed], [[float(v) for v in d] for d in pdl_ed])
            rp = res[mcode]
            model_stic = float(ss.get(f"ed|{mcode}|stic", 0.0) or 0.0)
            model_level, model_Th = rp.get("level", "none"), rp.get("Th")
            edited = not np.allclose(model[1], rp["p"]) or (
                bool(rp["pdl"]) and not np.allclose(np.ravel(model[2]), np.ravel(rp["pdl"]))) or \
                abs(model_stic - (rp.get("stic") or 0.0)) > 1e-9

            pf_fit = predict_full(mcode, rp["p"], rp["pdl"], ts_id, pv_id, mv_id, d_id, Ts, rp.get("stic", 0.0),
                                  model_level, model_Th)
            pf_ed = predict_full(mcode, model[1], model[2], ts_id, pv_id, mv_id, d_id, Ts, model_stic, model_level, model_Th)
            f_fit, f_ed = pf_fit["fit"], pf_ed["fit"]
            # pro graf v jednotkách PV: u „medium“ se kreslí surová data a model s optimálním posunem
            y_fit = pf_fit["yhat"] if model_level != "medium" else predict(mcode, rp["p"], rp["pdl"], ts_id, pv_id, mv_id,
                                                                          d_id, Ts, rp.get("stic", 0.0))[0]
            y_ed = pf_ed["yhat"] if model_level != "medium" else predict(mcode, model[1], model[2], ts_id, pv_id, mv_id,
                                                                        d_id, Ts, model_stic)[0]
            sigma_pv = float(np.std(np.diff(pf_ed["pv"] - pf_ed["yhat"])) / np.sqrt(2))  # bílý šum PV [%] z reziduí
            mm = model_metrics(pf_ed["pv"], pf_ed["yhat"], mv_id, Ts, dyn_scale(mcode, model[1]))
            ctx.PROG["model"] = 1 if ss.fit["key"] != fit_key else (0 if mm["status"] <= 1 else 1 if mm["status"] <= 3 else 2)
            ctx.PROG["model_stale"] = ss.fit["key"] != fit_key

            with c2:
                m1, m2 = st.columns(2)
                m1.metric(T("fit_fit"), f"{f_fit:.1f} %")
                m2.metric(T("fit_edit"), f"{f_ed:.1f} %", delta=f"{f_ed - f_fit:+.1f} %" if edited else None)
                ts_a, ya = step_response(mcode, rp["p"])
                ts_b, yb = step_response(mcode, model[1], horizon=ts_a[-1])
                f = go.Figure()
                f.add_trace(tr(ts_a, ya * PR / 100, T("fit"), C_MODEL[mcode], 2.2))
                if edited:
                    f.add_trace(tr(ts_b, yb * PR / 100, T("edited"), _c_edit(), 2.0, "dash"))
                f.add_vline(x=model[1][-1], line=dict(color="#94a3b8", dash="dot", width=1),
                            annotation_text="θ", annotation_position="top")
                style(f, 250, xtitle=lab_t, rev=f"step|{mcode}")
                f.update_layout(title=dict(text=T("step_title"), font=dict(size=13), x=0, y=0.98),
                                yaxis_title=f"Δ{lab_pv}", margin=dict(t=48))
                show(f, key=f"step|{mcode}", fname="step_response", report=T("step_title"))

            show_res = st.toggle(T("show_resid"), key="show_resid", help=T("h_resid"))
            extra = [(f"{mcode} {T('fit')}", y_fit, C_MODEL[mcode], None)]
            if edited:
                extra.append((f"{mcode} {T('edited')}", y_ed, _c_edit(), "dash"))
            if model_level == "high" and pf_ed.get("raw") is not None:
                extra.append((T("model_wo_dist"), pf_ed["raw"], "#94a3b8", "dot"))
            show(ctx.data_fig(ts_id, sel_mask, extra, resid=True if show_res else None), key="chart_model", fname="model",
                 report=T("rep_fig_model"))
            REPORT["tables"].append((T("rep_tab_models"), pd.DataFrame(rows).set_index(T("col_model"))))

            # ---- neměřené poruchy: co s daty udělalo potlačení
            if model_level != "none":
                with st.expander(T("dl_view", th=f"{(model_Th or 0):.0f}"), icon=":material/radar:"):
                    fd = mkfig(1)
                    if model_level == "high":
                        fd.add_trace(tr(ts_id, pf_ed["dist"] * PR / 100, T("dl_est"), "#7c3aed", 2.0), 1, 1)
                        style(fd, 280, [f"Δ{lab_pv}"], lab_t, rev="dl")
                    else:
                        fd.add_trace(tr(ts_id, pf_ed["pv"] * PR / 100, T("dl_filtered_pv"), C_PV, 1.3), 1, 1)
                        fd.add_trace(tr(ts_id, pf_ed["yhat"] * PR / 100, T("dl_filtered_model"), C_MODEL[mcode], 2.0), 1, 1)
                        style(fd, 280, [f"Δ{lab_pv}"], lab_t, rev="dl")
                    show(fd, key="chart_dl", fname="unmeasured")
                    st.caption(T("dl_view_help_" + model_level))

            # ---- podrobné hodnocení modelu
            st.markdown(f"#### {T('eval_title')}")
            with st.container(border=True):
                vkey_ = f"rng_val|{fname}|{t[-1]:.0f}"
                rv_ = ss.get(vkey_)
                segs_eval = [(T("eval_id"), sel_mask, mm)]
                if rv_ and tuple(rv_) != tuple(rng):
                    sv_ = (t >= rv_[0]) & (t <= rv_[1])
                    if sv_.sum() > 50:
                        tv_ = t[sv_] - t[sv_][0]
                        pfv = predict_full(mcode, model[1], model[2], tv_, pv[sv_], mv[sv_], [d[sv_] for d in dists], Ts,
                                           model_stic, model_level, model_Th)
                        segs_eval.append((T("eval_val"), sv_, model_metrics(pfv["pv"], pfv["yhat"], mv[sv_], Ts,
                                                                            dyn_scale(mcode, model[1]))))
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
                    fr.update_layout(height=260, margin=dict(l=8, r=8, t=30, b=8), hovermode="closest", uirevision="res")
                    fr.update_xaxes(title_text=T("lag_s"))
                    show(fr, key="chart_restest", fname="residual_tests")
                st.caption(T("eval_help"))

            _validation(ctx, model, model_stic)

            if st.toggle(T("compare_all"), key="cmp_all_models"):
                ex = [(f"{c} ({r['fit']:.1f} %)", predict(c, r["p"], r["pdl"], ts_id, pv_id, mv_id, d_id, Ts,
                                                           r.get("stic", 0.0))[0], C_MODEL[c], None) for c, r in res.items()]
                show(ctx.data_fig(ts_id, sel_mask, ex), key="chart_all", fname="models")

            with st.expander(T("unc_title"), icon=":material/scatter_plot:"):
                st.caption(T("unc_help"))
                u1, u2 = st.columns([1, 2], vertical_alignment="bottom")
                n_bs = int(num(T("unc_n"), "unc_n", 15, u1, min_value=5.0, max_value=50.0, step=1.0, format="%.0f",
                               help=T("h_unc_n")))
                if u2.button(T("unc_run"), icon=":material/casino:"):
                    k = int(np.ceil(len(ts_id) / 1500))
                    prog = st.progress(0.0, text=T("unc_running"))
                    bs = bootstrap_models(mcode, ts_id[::k], pv_id[::k], mv_id[::k], Ts * k, [d[::k] for d in d_id],
                                          th_max, {"p": model[1], "pdl": model[2]}, n=n_bs,
                                          progress=lambda f_: prog.progress(f_, text=T("unc_running")))
                    prog.empty()
                    ss.unc = dict(code=mcode, key=fit_key, ps=[b["p"] for b in bs])
                if ss.get("unc") and ss.unc["code"] == mcode and ss.unc["ps"]:
                    arr = np.array(ss.unc["ps"])
                    utab = pd.DataFrame({
                        T("unc_nominal"): [float(f"{v:.4g}") for v in model[1]],
                        T("unc_p05"): [float(f"{v:.4g}") for v in np.percentile(arr, 5, axis=0)],
                        T("unc_p95"): [float(f"{v:.4g}") for v in np.percentile(arr, 95, axis=0)],
                        T("unc_rel"): [f"± {100 * (np.percentile(arr[:, i], 95) - np.percentile(arr[:, i], 5)) / 2 / max(abs(model[1][i]), 1e-12):.0f} %"
                                       for i in range(arr.shape[1])]},
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
                    style(fu, 300, xtitle=lab_t, rev="unc")
                    fu.update_layout(yaxis_title=f"Δ{lab_pv}", title=dict(text=T("step_title"), font=dict(size=13), x=0))
                    show(fu, key="chart_unc", fname="uncertainty", report=T("unc_title"))
                    st.caption(T("unc_after"))

    unc_models = (ss.unc["ps"] if (model is not None and ss.get("unc") and ss.unc["code"] == model[0]) else [])
    ctx.model = model
    ctx.model_Th = model_Th
    ctx.model_level = model_level
    ctx.model_stic = model_stic
    ctx.sigma_pv = sigma_pv
    ctx.unc_models = unc_models


def _validation(ctx, model, stic):
    """Ověření modelu na jiném úseku: predikce PV z naměřené MV, nebo simulace smyčky se sadou 1/2 na záznamu."""
    t, Ts, pv, mv, sp, dists, rng = ctx.t, ctx.Ts, ctx.pv, ctx.mv, ctx.sp, ctx.dists, ctx.rng
    mcode, p, pdl = model
    st.markdown(f"#### {T('val_title')}")
    with st.container(border=True):
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
        sv = (t >= rv[0]) & (t <= rv[1])
        tv = t[sv] - t[sv][0]
        if len(tv) < 20:
            st.warning(T("err_short"))
            return
        if mode == "pred":
            yv, fv = predict(mcode, p, pdl, tv, pv[sv], mv[sv], [d[sv] for d in dists], Ts, stic)
            st.metric(T("fit_pred"), f"{fv:.1f} %")
            REPORT["val"] = T("rep_val_pred", f=f"{fv:.1f}")
            ov_ = max(0.0, min(rv[1], rng[1]) - max(rv[0], rng[0])) / max(rv[1] - rv[0], 1e-9)
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
        h = min(Ts, ctx.samp)
        n = int(tv[-1] / h) + 1
        tg = np.arange(n) * h
        spg = np.interp(tg, tv, sp[sv])
        dg = [np.interp(tg, tv, d[sv] - d[sv][0]) for d in dists]
        tt, _, Pv, Mv = pidconl_sim(mcode, p, pdl, h, spg, float(pv[sv][0]), float(mv[sv][0]), ctrl, dg)
        if not (np.all(np.isfinite(Pv)) and np.abs(Pv).max() < 1e5):
            st.error(T("err_sim_unstable", n=T("val_" + which)))
            return
        if which == "cur":
            pv_i, mv_i = np.interp(tv, tt, Pv), np.interp(tv, tt, Mv)
            nf = lambda a, b: 100 * (1 - np.linalg.norm(a - b) / max(np.linalg.norm(a - a.mean()), 1e-12))
            m1, m2 = st.columns(2)
            m1.metric(T("fit_pv"), f"{nf(pv[sv], pv_i):.1f} %")
            m2.metric(T("fit_mv"), f"{nf(mv[sv], mv_i):.1f} %")
            ctx.PROG["val"] = 0 if nf(pv[sv], pv_i) >= 60 else 2
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
