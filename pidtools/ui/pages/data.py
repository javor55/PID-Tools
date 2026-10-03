"""
Záložka Data.

`render_setup` – výběr sloupců, převzorkování a normování (horní rozbalovací sekce záložky; běží před ostatními
záložkami, protože data potřebují všechny). `render` – výběr úseku, automaticky nalezené úseky a kontrola kvality.
"""
import numpy as np
import pandas as pd
import streamlit as st

from ...i18n import T
from .. import loops
from ..charts import show
from ...app.dataio import TIME_FORMATS, compression_warnings, detect_time_format, pair_time_columns, to_num
from ...app import segments as segs_mod
from ...app.dataset import DEMO_DISTS, default_layout
from ...app.guess import guess_roles
from ...app.loop import DEFAULT_RANGE, range_for
from ..dataio import pairs_cached, pivot_cached, resample_cached, time_cached, time_columns_cached
from ..layout import section, workspace
from ..widgets import num, sel, seg

ss = st.session_state


def _guess(cols, keys, default=0):
    """Index sloupce, jehož název obsahuje některé z klíčových slov."""
    for k in keys:
        for col in cols:
            if k in str(col).lower():
                return cols.index(col)
    return min(default, len(cols) - 1)


def render_setup(ctx):
    """Sloupce (signály, čas, dlouhý formát), převzorkování na společnou mřížku a normovací rozsahy."""
    df = ctx.df
    with ctx.tabs["data"]:
        ctx.gph["data"] = st.container()
        ws = workspace()
        with ws.main:
            ws.m_top, ws.m_chart, ws.m_prev, ws.m_diag = st.container(), st.container(), st.container(), st.container()
        sec_sig = section(ws.side, T("dk_sec_signals"), "data_sig", icon=":material/sensors:")
        sec_units = section(ws.side, T("sb_units"), "data_units", icon=":material/straighten:")
        sec_file = section(ws.side, T("dk_sec_file"), "data_file", expanded=False, icon=":material/table_chart:")
        ws.diag = section(ws.side, T("dk_diag_tab").split("·")[-1].strip(), "data_diag", icon=":material/monitor_heart:")
        ctx.dws = ws
    cols = list(df.columns)
    tcols = time_columns_cached(ctx.ckey, df)

    with sec_file:
        layouts = ["wide", "pairs", "long"]
        layout = seg(st, T("layout"), layouts, default_layout(df), f"layout|{ctx.fname}",
                     format_func=lambda x: T("layout_" + x), help=T("h_layout")) or "wide"
        ctx.long_fmt = layout == "long"
        r1 = st.columns(2, vertical_alignment="bottom")
        time_fmt = sel(r1[0], T("time_fmt"), TIME_FORMATS, 0, "time_fmt", format_func=lambda x: T("tf_" + x),
                       help=T("h_time_fmt"))
        time_unit = r1[1].selectbox(T("time_unit"), ["s", "ms", "min", "h"], help=T("time_unit_help"), key="time_unit")
        unit_mult = {"s": 1, "ms": 1e-3, "min": 60, "h": 3600}[time_unit]
        r1b = st.columns(2, vertical_alignment="bottom")
        ts_manual = r1b[0].toggle(T("ts_manual"), key="ts_manual", help=T("h_ts_manual"))
        Ts_user = num(T("ts_data"), "ts_user", 1.0, r1b[1], min_value=0.001) if ts_manual else None
        try:
            if layout == "long":
                r2 = st.columns(1) * 3
                c_tag = sel(r2[0], T("col_tag"), cols, _guess(cols, ["tag", "name", "název", "variable"]), key="c_tag")
                c_tim = sel(r2[1], T("col_time"), cols, _guess(cols, ["time", "čas", "cas", "timestamp"], 1),
                            key="c_tim_l")
                c_val = sel(r2[2], T("col_value"), cols, _guess(cols, ["value", "hodnota", "val"], 2), key="c_val")
                wide, ctx.t_origin = pivot_cached(ctx.ckey, c_tag, c_tim, c_val, unit_mult, time_fmt, df)
                time_src = [c_tim]
            elif layout == "pairs":
                if not tcols:
                    raise ValueError(T("err_no_time_cols"))
                pairs = pair_time_columns(df, tcols)
                wide, ctx.t_origin = pairs_cached(ctx.ckey, tuple(pairs.items()), unit_mult, time_fmt, df)
                st.caption(T("pairs_caption", p=" · ".join(f"{c} ← {tc}" for c, tc in pairs.items())))
                time_src = list(tcols)
            else:
                c_tim = sel(st, T("col_time"), cols, cols.index(tcols[0]) if tcols else
                            _guess(cols, ["cas", "čas", "time", "datum", "date"]), key="c_tim")
                ctx.t_all, ctx.t_origin = time_cached(ctx.ckey, c_tim, unit_mult, time_fmt, df[c_tim])
                ctx.sigs = [s_ for s_ in cols if s_ != c_tim and s_ not in tcols]
                ctx.get = lambda s_: to_num(df[s_])
                time_src = [c_tim]
            if layout != "wide":
                ctx.t_all = wide["t"].to_numpy(float)
                ctx.sigs = [s_ for s_ in wide.columns if s_ != "t"]
                ctx.get = lambda s_: wide[s_].to_numpy(float)
            kinds = {detect_time_format(df[c_])[0] for c_ in time_src}
            st.caption(T("time_detected", f=", ".join(T("tf_" + k_) if k_ in TIME_FORMATS else str(k_)
                                                      for k_ in sorted(kinds, key=str))))
        except Exception as ex:
            st.error(T("err_data", ex=ex))
            st.stop()
    with sec_sig:
        sigs, fname = ctx.sigs, ctx.fname
        if not sigs:
            st.error(T("err_data", ex=T("err_no_signals")))
            st.stop()
        g = guess_roles(sigs, ctx.get, loops.other_pvs())
        r3 = st.columns(1) * 3
        ctx.c_pv = sel(r3[0], "PV", sigs, sigs.index(g["pv"]), key=f"c_pv|{fname}", help=T("h_pv"))
        ctx.c_mv = sel(r3[1], "MV", sigs, sigs.index(g["mv"]), key=f"c_mv|{fname}", help=T("h_mv"))
        sp_opts = ["—"] + sigs
        ctx.c_sp = sel(r3[2], T("col_sp"), sp_opts, sp_opts.index(g["sp"]) if g["sp"] else 0, key=f"c_sp|{fname}",
                       help=T("h_sp"))
        r4 = st.columns(1) * 2
        d_opts = [s_ for s_ in sigs if s_ not in (ctx.c_pv, ctx.c_mv, ctx.c_sp)]
        if fname == "demo" and f"c_d|{fname}" not in ss:      # ukázka: měřený přítok jako porucha (jako desktop)
            ss[f"c_d|{fname}"] = [d_ for d_ in DEMO_DISTS if d_ in d_opts]
        ctx.c_d = r4[0].multiselect(T("col_dist"), d_opts, help=T("col_dist_help"), key=f"c_d|{fname}",
                                    placeholder=T("ms_placeholder"))
        pos_opts = ["—"] + [s_ for s_ in d_opts if s_ not in ctx.c_d]
        ctx.c_pos = sel(r4[1], T("col_pos"), pos_opts, pos_opts.index(g["pos"]) if g["pos"] in pos_opts else 0,
                        key=f"c_pos|{fname}", help=T("h_pos"))
        st.caption(T("guess_note"))

    # ---- převzorkování na společnou mřížku
    try:
        ctx.pv_raw, mv_raw = ctx.get(ctx.c_pv), ctx.get(ctx.c_mv)
        raw_cols = [ctx.pv_raw, mv_raw] + [ctx.get(s_) for s_ in ctx.c_d]
        ctx.has_sp = ctx.c_sp != "—"
        if ctx.has_sp:
            raw_cols.append(ctx.get(ctx.c_sp))
        rkey = (ctx.ckey, layout, time_fmt, unit_mult, str(ctx.c_pv), str(ctx.c_mv), str(ctx.c_sp), tuple(map(str, ctx.c_d)),
                str(ss.get("c_tag")), str(ss.get("c_tim") if not ctx.long_fmt else ss.get("c_tim_l")), str(ss.get("c_val")))
        ctx.t, ctx.Ts, rs, ctx.T0 = resample_cached(rkey, ctx.t_all, raw_cols, Ts_user)
        ctx.pv_e, ctx.mv_e = rs[0], rs[1]
        ctx.dists = rs[2:2 + len(ctx.c_d)]
        ctx.sp_e = rs[-1] if ctx.has_sp else np.full_like(ctx.pv_e, np.nan)
    except Exception as ex:
        with ctx.tabs["data"]:
            st.error(T("err_data", ex=ex))
        st.stop()
    ctx.pos_e = ctx.on_grid(ctx.c_pos) if ctx.c_pos != "—" else None

    # ---- jednotky; rozsah regulátoru (NormPV, NormMV) se zadává v Ladění › Blok PIDConL – tady se jen použije
    for k_, x_ in (("pv", ctx.pv_e), ("mv", ctx.mv_e)):      # rozsah PIDConL podle dat, dokud ho nikdo nezadal
        cur_ = (ss.get(f"{k_}_lo", 0.0), ss.get(f"{k_}_hi", 100.0))
        try:
            ss[f"{k_}_lo"], ss[f"{k_}_hi"] = range_for(cur_, x_)
        except (TypeError, ValueError):
            ss[f"{k_}_lo"], ss[f"{k_}_hi"] = DEFAULT_RANGE
    rng_ = [float(ss[k_]) for k_ in ("pv_lo", "pv_hi", "mv_lo", "mv_hi")]
    ctx.norm_ok = rng_[1] > rng_[0] and rng_[3] > rng_[2]
    # neplatný rozsah: počítá se s výchozím, aby šel blok vykreslit a opravit (běh se zastaví až po něm)
    ctx.pv_lo, ctx.pv_hi, ctx.mv_lo, ctx.mv_hi = rng_ if ctx.norm_ok else (0.0, 100.0, 0.0, 100.0)
    with sec_units:
        n1, n2 = st.columns(2)
        if "u_mv" not in ss:
            ss["u_mv"] = "%"
        ctx.u_pv = n1.text_input(T("unit_pv"), key="u_pv", placeholder="m, °C, bar…", help=T("h_unit"))
        ctx.u_mv = n2.text_input(T("unit_mv"), key="u_mv", help=T("h_unit"))
        st.caption(T("norm_where", pv=f"{rng_[0]:g}–{rng_[1]:g}", mv=f"{rng_[2]:g}–{rng_[3]:g}"))
    if not ctx.norm_ok:
        with ctx.tabs["data"]:
            st.error(T("err_range_blk"), icon=":material/error:")
    ctx.pv, ctx.mv, ctx.sp = ctx.P(ctx.pv_e), ctx.M(ctx.mv_e), ctx.P(ctx.sp_e)
    with ctx.tabs["data"], ctx.dws.m_prev:
        _preview(ctx, df, tcols)


def _preview(ctx, df, tcols):
    """Rozbalovací náhled: výsledná tabulka po převzorkování, statistika a původní soubor s rozpoznanými typy."""
    exp = st.expander(T("prev_title"), icon=":material/table_view:", key="prev_open", on_change="rerun")
    if not exp.open:  # tabulka se posílá do prohlížeče jen v rozbaleném stavu
        return
    with exp:
        out = {T("time_s"): ctx.t}
        if ctx.t_origin is not None:
            out[T("prev_datetime")] = ctx.t_origin + pd.to_timedelta(ctx.t + ctx.T0, unit="s")
        out[f"PV · {ctx.c_pv}"] = ctx.pv_e
        out[f"MV · {ctx.c_mv}"] = ctx.mv_e
        if ctx.has_sp:
            out[f"SP · {ctx.c_sp}"] = ctx.sp_e
        for nm, d in zip(ctx.c_d, ctx.dists):
            out[f"{T('prev_dist')} · {nm}"] = d
        if ctx.pos_e is not None:
            out[f"{T('prev_pos')} · {ctx.c_pos}"] = ctx.pos_e
        res = pd.DataFrame(out)
        t1, t2, t3 = st.tabs([T("prev_result"), T("prev_stats"), T("prev_raw")])
        with t1:
            st.caption(T("prev_result_help", n=len(res), ts=f"{ctx.Ts:.4g}"))
            st.dataframe(res, height=360, hide_index=True,
                         column_config={T("prev_datetime"): st.column_config.DatetimeColumn(format="D.M.YYYY HH:mm:ss.SSS")})
            st.download_button(T("prev_dl"), res.to_csv(index=False, sep=";", decimal=","), "data_resampled.csv",
                               "text/csv", icon=":material/download:")
        with t2:
            num_ = res.drop(columns=[T("prev_datetime")], errors="ignore")
            stats = pd.DataFrame({T("prev_min"): num_.min(), T("prev_max"): num_.max(), T("prev_mean"): num_.mean(),
                                  T("prev_nan"): num_.isna().sum()})
            st.dataframe(stats, width="stretch")
        with t3:
            def kind(c):
                if c in tcols:
                    k_ = detect_time_format(df[c])[0]
                    return f"{T('prev_k_time')} ({T('tf_' + k_) if k_ in TIME_FORMATS else k_})"
                v = to_num(df[c])
                return T("prev_k_num") if np.isfinite(v).mean() > 0.5 else T("prev_k_text")
            st.caption(T("prev_raw_help", n=len(df), c=len(df.columns)))
            st.dataframe(pd.DataFrame({c: [kind(c), int(df[c].isna().sum())] for c in df.columns},
                                      index=[T("prev_type"), T("prev_nan")]), width="stretch")
            st.dataframe(df.head(200), height=300)


def render(ctx):
    """
    Graf načtených dat (záložka Data) a výběr úseku pro identifikaci – posuvník, tažení v grafu, automaticky nalezené
    úseky, kontrola kvality – vykreslený na začátku záložky Model (úsek je součástí identifikace). Počítá se tady,
    protože úsek potřebují všechny další záložky.
    """
    t, Ts, pv, mv, sp, has_sp = ctx.t, ctx.Ts, ctx.pv, ctx.mv, ctx.sp, ctx.has_sp
    with ctx.tabs["data"]:
        for w in compression_warnings(ctx.t_all, ctx.pv_raw, "PV"):
            ctx.dws.m_top.warning(w, icon=":material/compress:")
        with ctx.dws.m_chart:
            show(ctx.data_fig(t), key=f"chart_data_all|{ctx.fname}", fname="data_all")
            st.caption(T("data_chart_help"))
    with ctx.tabs["model"]:
        ctx.gph["model"] = st.container()      # průvodce záložky Model nahoře (vyplní se na konci běhu)
        ws = workspace()
        with ws.side:
            ws.top = st.container()            # tlačítko Identifikovat a průběh
        with ws.main:
            ws.m_seg = st.container()
            ws.m_res = st.container()
            ws.m_tabs = st.container()
        ctx.mws = ws
        rng_key = f"rng_id|{ctx.fname}|{t[-1]:.0f}"
        step = float(max(Ts, t[-1] / 1000))
        if "pending_rng" in ss:
            ss[rng_key] = ss.pop("pending_rng")
        if rng_key not in ss:
            ss[rng_key] = (0.0, float(t[-1]))

        def snap(v):
            return float(np.clip(round(v / step) * step, 0.0, float(t[-1])))

        # model pro hodnocení dat (pokud už existuje)
        qmodel = None
        if "fit" in ss and ss.get("mcode") in ss.fit.get("res", {}):
            mc_ = ss.mcode
            qmodel = (mc_, [float(ss.get(f"ed|{mc_}|{i}", v)) for i, v in enumerate(ss.fit["res"][mc_]["p"])])

        def quality(a, b):
            return segs_mod.quality(t, pv, mv, sp, Ts, has_sp, float(ctx.M(ctx.mvl_lo)), float(ctx.M(ctx.mvl_hi)), a, b,
                                    segs_mod.rep_frac(ctx.t_all, ctx.pv_raw, ctx.T0, a, b), qmodel)

        segs = segs_mod.auto(t, mv, sp, Ts, has_sp, qmodel, ss.get("seg_gap"))
        sec_seg = section(ws.side, T("dk_sec_segment"), "mod_seg", icon=":material/straighten:")
        sec_auto = section(ws.side, T("auto_title", n=len(segs)), "mod_auto", expanded=False,
                           icon=":material/auto_awesome:")
        ws.ident = section(ws.side, T("dk_sec_ident"), "mod_ident", icon=":material/model_training:")
        ws.model = section(ws.side, T("dk_sec_model"), "mod_model", icon=":material/tune:")
        ws.unc = section(ws.side, T("unc_title"), "mod_unc", expanded=False, icon=":material/scatter_plot:")

        with sec_seg:
            st.caption(T("seg_intro"))
            rng = st.slider(T("seg_id"), 0.0, float(t[-1]), step=step, key=rng_key, help=T("h_seg_id"))
            drag = seg(st, T("mouse"), ["zoom", "select"], "zoom", "drag",
                       format_func=lambda x: T("mouse_" + x), help=T("h_mouse")) or "zoom"
            q_box = st.container()
        ctx.rng = rng
        ctx.sel_mask = (t >= rng[0]) & (t <= rng[1])

        # ---- automaticky nalezené úseky
        with sec_auto:
            if not segs:
                st.info(T("auto_none"), icon=":material/search_off:")
            else:
                rows_s = []
                for i_, sg in enumerate(segs):
                    q_ = quality(sg["start"], sg["end"])
                    rows_s.append({"#": i_ + 1, T("auto_from"): f"{sg['start']:.0f}", T("auto_to"): f"{sg['end']:.0f}",
                                   T("auto_steps"): f"{sg['n_mv']} / {sg['n_sp']}",
                                   T("auto_quality"): ["✓ ", "⚠ ", "✗ "][q_["level"]] + T(f"q_level{q_['level']}")})
                ev_s = st.dataframe(pd.DataFrame(rows_s), hide_index=True, width="stretch", on_select="rerun",
                                    selection_mode="single-row", key=f"segtab|{ctx.fname}")
                chosen_s = None
                try:
                    if ev_s.selection.rows:
                        chosen_s = segs[ev_s.selection.rows[0]]
                except AttributeError:
                    pass
                b1, b2 = st.columns(2)
                if b1.button(T("auto_use_id"), icon=":material/model_training:", disabled=chosen_s is None,
                             width="stretch"):
                    ss.pending_rng = (snap(chosen_s["start"]), snap(chosen_s["end"]))
                    st.rerun()
                if b2.button(T("auto_use_val"), icon=":material/fact_check:", disabled=chosen_s is None,
                             width="stretch"):
                    ss.pending_rngv = (snap(chosen_s["start"]), snap(chosen_s["end"]))
                    st.rerun()
                st.caption(T("auto_help"))
            num(T("auto_gap"), "seg_gap", 0.0, min_value=0.0, help=T("h_auto_gap"))

        # ---- graf dat s úseky – kreslí ho záložka Model (ctx.seg_chart), aby v něm byl i model (jedna sada grafů)
        def seg_chart(extra=(), resid=None):
            """extra = [(název, y na úseku v %, barva, čára)] – model přes vybraný úsek; resid = řádek reziduí."""
            full = []
            for name_, y_, col_, dash_ in extra:
                yy = np.full(len(t), np.nan)
                yy[ctx.sel_mask] = y_
                full.append((name_, yy, col_, dash_))
            fig = ctx.data_fig(t, None, full, resid=resid)
            for i_, sg in enumerate(segs):
                fig.add_vrect(x0=sg["start"], x1=sg["end"], fillcolor="#bfdbfe", opacity=0.22, line_width=0, row=1,
                              col=1, annotation_text=f"#{i_ + 1}", annotation_position="top left",
                              annotation_font=dict(size=11, color="#1e40af"))
            n_rows = 2 + (1 if ctx.dists else 0) + (1 if resid is not None else 0)
            for r in range(1, n_rows + 1):
                fig.add_vrect(x0=rng[0], x1=rng[1], fillcolor="#fde68a", opacity=0.25, line_width=0, row=r, col=1)
            fig.update_layout(dragmode="select" if drag == "select" else "zoom", selectdirection="h")
            with ws.m_seg:
                ev = show(fig, key=f"chart_data|{ctx.fname}", fname="model" if extra else "data", select=True,
                          report=T("rep_fig_model" if extra else "rep_fig_data"))
                st.caption(T("seg_tip"))

            # výběr úseku tažením v grafu
            try:
                box = ev.selection.box if ev and ev.selection else []
                pts = ev.selection.points if ev and ev.selection else []
                xr = None
                if box:
                    xr = sorted(float(v) for v in box[0]["x"][:2])
                elif pts:
                    xs = [float(p_["x"]) for p_ in pts if "x" in p_]
                    xr = [min(xs), max(xs)] if xs else None
                if xr and xr[1] - xr[0] > step and tuple(xr) != ss.get("last_box"):
                    ss.last_box = tuple(xr)
                    ss.pending_rng = (snap(xr[0]), snap(xr[1]))
                    st.rerun()
            except Exception:
                pass
        ctx.seg_chart = seg_chart

        # ---- kontrola kvality vybraného úseku
        dq = quality(rng[0], rng[1])
        ctx.dq = dq
        ctx.PROG["data"] = dq["level"]
        icons = ["✓", "⚠", "✗"]
        lv_ = dq["level"]
        box_fn = [q_box.success, q_box.warning, q_box.error][lv_]
        lines = "  \n".join(f"{icons[lv]} {T(k_, **segs_mod.format_args(ar))}"
                            for k_, lv, ar in sorted(dq["checks"], key=lambda c_: -c_[1]))
        box_fn(f"**{T('q_title')}: {T('q_level' + str(lv_))}**  \n{lines}",
               icon=[":material/verified:", ":material/rule:", ":material/block:"][lv_])
        if has_sp and np.nanmax(sp[ctx.sel_mask]) - np.nanmin(sp[ctx.sel_mask]) > 1e-6:
            q_box.caption(T("info_auto"))

    # data úseku identifikace pro další záložky
    ctx.ts_id = t[ctx.sel_mask] - t[ctx.sel_mask][0]
    ctx.pv_id, ctx.mv_id = pv[ctx.sel_mask], mv[ctx.sel_mask]
    ctx.d_id = [d[ctx.sel_mask] for d in ctx.dists]
