"""
Záložka Data.

`render_setup` – výběr sloupců, převzorkování a normování (horní rozbalovací sekce záložky; běží před ostatními
záložkami, protože data potřebují všechny). `render` – výběr úseku, automaticky nalezené úseky a kontrola kvality.
"""
import html
from types import SimpleNamespace

import numpy as np
import pandas as pd
import streamlit as st

from ...i18n import T
from .. import loops
from ..charts import show
from ...app.dataio import (ROWS, TIME_FORMATS, detect_time_format, pair_time_columns,
                           row_time, to_num)
from ...app import segments as segs_mod
from ...app.dataset import DEMO_DISTS, default_layout, stats
from ...app.guess import guess_roles
from ...app.loop import DEFAULT_RANGE, range_for
from ...app.timefmt import dur, fmt_t, unit_for
from ..dataio import pairs_cached, pivot_cached, resample_cached, time_cached, time_columns_cached
from ..layout import section, workspace
from ..widgets import num, sel, seg

ss = st.session_state
MAX_SEG_SHADES = 40            # automaticky nalezené úseky vyznačené v grafu (tabulka ukáže všechny)


def _guess(cols, keys, default=0):
    """Index sloupce, jehož název obsahuje některé z klíčových slov."""
    for k in keys:
        for col in cols:
            if k in str(col).lower():
                return cols.index(col)
    return min(default, len(cols) - 1)


def open_workspace(ctx):
    """Záložka Data: hlavní plocha (záznam, kvalita dat, náhled) a panel (zdroj dat, signály, statistika, jednotky)."""
    with ctx.tabs["data"]:
        ctx.gph["data"] = st.container()
        ws = workspace()
        with ws.main:
            ws.m_top, ws.m_chart, ws.m_dq, ws.m_prev = st.container(), st.container(), st.container(), st.container()
        ws.src = section(ws.side, T("dk_sec_src"), "data_src", expanded=True, icon=":material/database:")
        ws.sig = section(ws.side, T("dk_sec_signals"), "data_sig", expanded=True, icon=":material/sensors:")
        ws.stats = section(ws.side, T("dk_sec_stats"), "data_stats", expanded=True, icon=":material/functions:")
        ws.units = section(ws.side, T("sb_units"), "data_units", icon=":material/straighten:")
        ctx.dws = ws


def _manual_default(df, lay_key):
    """Ruční nastavení čtení zapnuté, pokud projekt / dřívější relace něco nastavila jinak než automatika."""
    return (ss.get(lay_key, default_layout(df)) != default_layout(df) or ss.get("time_fmt", "auto") != "auto"
            or ss.get("time_unit", "s") != "s" or bool(ss.get("ts_manual")))


def render_setup(ctx):
    """Sloupce (signály, čas, dlouhý formát), převzorkování na společnou mřížku a normovací rozsahy."""
    df = ctx.df
    ws = ctx.dws
    sec_sig, sec_stats, sec_units = ws.sig, ws.stats, ws.units
    cols = list(df.columns)
    tcols = time_columns_cached(ctx.ckey, df)

    # ---- čtení souboru: automaticky (výchozí), ručně jen když automatika soubor nepřečte správně
    layouts = ["wide", "pairs", "long"]
    lay_key = f"layout|{ctx.fname}"
    if "read_manual" not in ss:
        ss["read_manual"] = _manual_default(df, lay_key)
    with ws.read_ph:
        status_box = st.container()
        manual = st.toggle(T("read_manual"), key="read_manual", help=T("h_read_manual"))
        box = st.container(border=True) if manual else None
    notes = []                                # co automatika / ruční nastavení rozpoznalo (popisek pod přepínačem)

    def pick(widget, auto):
        """Ručně: widget v panelu; automaticky: odhad bez widgetu."""
        return widget() if manual else auto

    layout = pick(lambda: seg(box, T("layout"), layouts, default_layout(df), lay_key,
                              format_func=lambda x: T("layout_" + x), help=T("h_layout")), default_layout(df)) or "wide"
    ctx.long_fmt = layout == "long"
    time_fmt = pick(lambda: sel(box, T("time_fmt"), TIME_FORMATS, 0, "time_fmt", format_func=lambda x: T("tf_" + x),
                                help=T("h_time_fmt")), "auto")
    time_unit = pick(lambda: box.selectbox(T("time_unit"), ["s", "ms", "min", "h"], help=T("time_unit_help"),
                                           key="time_unit"), "s")
    unit_mult = {"s": 1, "ms": 1e-3, "min": 60, "h": 3600}[time_unit]
    ts_manual = pick(lambda: box.toggle(T("ts_manual"), key="ts_manual", help=T("h_ts_manual")), False)
    Ts_user = num(T("ts_data"), "ts_user", 1.0, box, min_value=0.001) if ts_manual else None
    try:
        if layout == "long":
            c_tag = pick(lambda: sel(box, T("col_tag"), cols, _guess(cols, ["tag", "name", "název", "variable"]),
                                     key="c_tag"), cols[_guess(cols, ["tag", "name", "název", "variable"])])
            c_tim = pick(lambda: sel(box, T("col_time"), cols, _guess(cols, ["time", "čas", "cas", "timestamp"], 1),
                                     key="c_tim_l"), cols[_guess(cols, ["time", "čas", "cas", "timestamp"], 1)])
            c_val = pick(lambda: sel(box, T("col_value"), cols, _guess(cols, ["value", "hodnota", "val"], 2),
                                     key="c_val"), cols[_guess(cols, ["value", "hodnota", "val"], 2)])
            wide, ctx.t_origin = pivot_cached(ctx.ckey, c_tag, c_tim, c_val, unit_mult, time_fmt, df)
            time_src = [c_tim]
        elif layout == "pairs":
            if not tcols:
                raise ValueError(T("err_no_time_cols"))
            pairs = pair_time_columns(df, tcols)
            wide, ctx.t_origin = pairs_cached(ctx.ckey, tuple(pairs.items()), unit_mult, time_fmt, df)
            notes.append(T("pairs_caption", p=" · ".join(f"{c} ← {tc}" for c, tc in pairs.items())))
            time_src = list(tcols)
        else:
            opts_t = [ROWS] + cols          # ROWS = bez času: co řádek, to vzorek s ručně zadanou periodou
            auto_rows = False
            if ss.get("c_tim") not in opts_t or ss.get("c_tim_for") != ctx.ckey:   # nový soubor → odhad
                ss["c_tim_for"] = ctx.ckey
                d_ = tcols[0] if tcols else cols[_guess(cols, ["cas", "čas", "time", "datum", "date"])]
                try:
                    time_cached(ctx.ckey, d_, unit_mult, time_fmt, df[d_])
                except ValueError:
                    d_, auto_rows = ROWS, True
                ss["c_tim"] = d_
                ss["rows_auto"] = auto_rows
            c_tim = pick(lambda: box.selectbox(T("col_time"), opts_t, key="c_tim",
                                               format_func=lambda c_: T("time_rows") if c_ == ROWS else str(c_)),
                         ss["c_tim"])
            if c_tim == ROWS:
                row_dt = num(T("row_dt"), "row_dt", 1.0, box if manual else ws.read_ph, min_value=1e-6, format="%.6g",
                             help=T("h_row_dt"))
                ctx.t_all, ctx.t_origin = row_time(len(df), row_dt, unit_mult), None
                ctx.sigs = [s_ for s_ in cols if s_ not in tcols and np.isfinite(to_num(df[s_])).mean() > 0.5]
                notes.append(T("time_rows_note", dt=f"{row_dt:g}", u=time_unit))
                if ss.get("rows_auto"):
                    ws.m_top.warning(T("time_rows_auto", dt=f"{row_dt:g}", u=time_unit), icon=":material/schedule:")
            else:
                ss["rows_auto"] = False
                ctx.t_all, ctx.t_origin = time_cached(ctx.ckey, c_tim, unit_mult, time_fmt, df[c_tim])
                ctx.sigs = [s_ for s_ in cols if s_ != c_tim and s_ not in tcols]
            ctx.get = lambda s_: to_num(df[s_])
            time_src = [c_tim]
        if layout != "wide":
            ctx.t_all = wide["t"].to_numpy(float)
            ctx.sigs = [s_ for s_ in wide.columns if s_ != "t"]
            ctx.get = lambda s_: wide[s_].to_numpy(float)
        if time_src != [ROWS]:
            kinds = {detect_time_format(df[c_])[0] for c_ in time_src}
            notes.insert(0, T("read_auto_ok", lay=T("layout_" + layout).lower(), c=", ".join(map(str, time_src)),
                              f=", ".join(T("tf_" + k_) if k_ in TIME_FORMATS else str(k_)
                                          for k_ in sorted(kinds, key=str))))
        status_box.caption(" · ".join(notes))
    except Exception as ex:
        status_box.error(T("err_data", ex=ex) + ("" if manual else " " + T("read_try_manual")))
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
        pos_key = f"c_pos|{fname}"
        if g["pos"] in pos_opts or ss.get(pos_key, "—") != "—" or ss.get("pos_on"):
            ctx.c_pos = sel(r4[1], T("col_pos"), pos_opts, pos_opts.index(g["pos"]) if g["pos"] in pos_opts else 0,
                            key=pos_key, help=T("h_pos"))
        else:                             # poloha aktuátoru je nepovinná – jen malé tlačítko, dokud ji nikdo nechce
            ctx.c_pos = "—"
            r4[1].button(T("pos_add"), icon=":material/add:", type="tertiary", key="g_pos_add", help=T("h_pos"),
                         on_click=lambda: ss.update(pos_on=True))
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
            ss[f"{k_}_lo"], ss[f"{k_}_hi"] = range_for(cur_, x_, bool(ss.get(f"{k_}_rng_user")))
        except (TypeError, ValueError):
            ss[f"{k_}_lo"], ss[f"{k_}_hi"] = DEFAULT_RANGE
    rng_ = [float(ss[k_]) for k_ in ("pv_lo", "pv_hi", "mv_lo", "mv_hi")]
    ctx.norm_ok = rng_[1] > rng_[0] and rng_[3] > rng_[2]
    # neplatný rozsah: počítá se s výchozím, aby šel blok vykreslit a opravit (běh se zastaví až po něm)
    ctx.pv_lo, ctx.pv_hi, ctx.mv_lo, ctx.mv_hi = rng_ if ctx.norm_ok else (0.0, 100.0, 0.0, 100.0)
    with sec_stats:                      # min / max … veličin smyčky (jednotky PV / MV)
        st.dataframe(pd.DataFrame([dict(zip(("", "Min", "Max", T("stat_mean"), "σ"),
                                            (n, *(float(f"{v:.5g}") for v in r)))) for n, *r in
                                   stats(SimpleNamespace(pv_e=ctx.pv_e, mv_e=ctx.mv_e, sp_e=ctx.sp_e, has_sp=ctx.has_sp,
                                                         dists=ctx.dists), ctx.c_d)]).set_index(""),
                     width="stretch")
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
    ctx.tcols = tcols


def _result_frame(ctx, warn=None):
    """Data po převzorkování jako tabulka (čas, datum, PV, MV, SP, poruchy, poloha, upozornění Kvality dat)."""
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
    if warn is not None:
        out[T("prev_note")] = warn
    return pd.DataFrame(out)


def _warn_text(ctx, checks):
    """Text upozornění pro každý vzorek (sloupec Poznámka v náhledu)."""
    txt = np.full(len(ctx.t), "", dtype=object)
    for c in checks:
        if c.mask is not None and len(c.mask) == len(txt):
            lab = T(f"dq_{c.id}_name", name="")
            txt[c.mask] = np.where(txt[c.mask] == "", lab, txt[c.mask] + " · " + lab)
    return txt


def _full_preview(ctx, checks):
    """Celý náhled (okno přes stránku): plné grafy se zoomem a měřením, celá tabulka s přechodem na čas a filtrem."""
    from ...app.quality import warn_mask

    @st.dialog(T("prev_full_title", f=ctx.fname.split("|")[0]), width="large")
    def dlg():
        show(ctx.data_fig(ctx.t), key="chart_data_full", fname="data_full")
        warn = _warn_text(ctx, checks)
        res = _result_frame(ctx, warn)
        t1, t2, t3 = st.tabs([T("prev_result"), T("prev_stats"), T("prev_raw")])
        with t1:
            c1, c2, c3 = st.columns([1, 1.4, 1], vertical_alignment="bottom")
            go_t = c1.number_input(T("prev_goto"), 0.0, float(ctx.t[-1]), value=None, step=float(ctx.Ts),
                                   placeholder=T("prev_goto_ph"), key="prev_goto", help=T("h_prev_goto"))
            flt = c2.segmented_control(T("prev_filter"), ["all", "warn", "mv"], default="all", key="prev_filter",
                                       format_func=lambda x: T("prev_f_" + x))
            m = np.ones(len(res), bool)
            if flt == "warn":
                m = warn_mask(checks, len(res))
            elif flt == "mv":
                m = np.r_[False, np.abs(np.diff(ctx.mv_e)) > 1e-9]
            view = res[m]
            if go_t is not None:                         # okno kolem zvoleného času
                i = int(np.searchsorted(view[T("time_s")].to_numpy(), go_t))
                view = view.iloc[max(0, i - 20):i + 200]
            st.caption(T("prev_rows", a=len(view), n=len(res), ts=f"{ctx.Ts:.4g}"))
            st.dataframe(view, height=420, hide_index=True,
                         column_config={T("prev_datetime"): st.column_config.DatetimeColumn(format="D.M.YYYY HH:mm:ss.SSS")})
            c3.download_button(T("prev_dl"), res.to_csv(index=False, sep=";", decimal=","), "data_resampled.csv",
                               "text/csv", icon=":material/download:", width="stretch")
        with t2:
            num_ = res.drop(columns=[T("prev_datetime"), T("prev_note")], errors="ignore")
            st.dataframe(pd.DataFrame({T("prev_min"): num_.min(), T("prev_max"): num_.max(),
                                       T("prev_mean"): num_.mean(), T("prev_nan"): num_.isna().sum()}), width="stretch")
        with t3:
            df, tcols = ctx.df, ctx.tcols

            def kind(c):
                if c in tcols:
                    k_ = detect_time_format(df[c])[0]
                    return f"{T('prev_k_time')} ({T('tf_' + k_) if k_ in TIME_FORMATS else k_})"
                v = to_num(df[c])
                return T("prev_k_num") if np.isfinite(v).mean() > 0.5 else T("prev_k_text")
            st.caption(T("prev_raw_help", n=len(df), c=len(df.columns)))
            st.dataframe(pd.DataFrame({c: [kind(c), int(df[c].isna().sum())] for c in df.columns},
                                      index=[T("prev_type"), T("prev_nan")]), width="stretch")
            obj = [c for c in df.columns if df[c].dtype == object]      # smíšené typy (čas jako text i číslo)
            st.dataframe(df.astype({c: str for c in obj}) if obj else df, height=360)
    dlg()


_DQ_STYLE = {"ok": ("#2f6f3e", "rgba(34,197,94,0.13)", "rgba(34,197,94,0.45)", "✓"),
             "warn": ("#8a4b00", "rgba(245,158,11,0.16)", "rgba(245,158,11,0.5)", "!"),
             "info": ("#1f5fa8", "rgba(31,95,168,0.10)", "rgba(31,95,168,0.4)", "i")}


def _quality(ctx):
    """Kvalita dat: seznam kontrol se stavem, výsledkem a vysvětlením (sdílené kontroly z pidtools.app.quality)."""
    from ...app import quality as dq
    checks = dq.check_all(ctx.t_all, ctx.pv_raw, ctx.get(ctx.c_mv), ctx.Ts, ctx.pv_e, ctx.mv_e, ctx.dists,
                          [str(c) for c in ctx.c_d], (ctx.pv_lo, ctx.pv_hi), (ctx.mv_lo, ctx.mv_hi),
                          (float(ctx.mvl_lo), float(ctx.mvl_hi)))
    cnt, usable = dq.summary(checks)
    head = (f"<span class='pid-chip {'s0' if usable else 's1'}'>{T('dq_usable') if usable else T('dq_unusable')}</span> "
            f"<span class='pid-sub'>{T('dq_counts', **cnt)}</span>")
    rows = []
    for c in checks:
        col, bg, bd, ic = _DQ_STYLE[c.status]
        name = T(f"dq_{c.id}_name", **c.args)
        rows.append(
            f"<div class='pid-dq'><span class='pid-dq-ic' style='color:{col};background:{bg};border-color:{bd}'>{ic}</span>"
            f"<span class='pid-dq-n'>{html.escape(name)}</span><span><span class='pid-dq-r' style='color:{col}'>"
            f"{html.escape(T(c.res, **c.args))}</span><span class='pid-dq-w'>{html.escape(T(f'dq_{c.id}_why'))}</span>"
            f"</span></div>")
    with st.container(border=True, key="pid_card_dq"):
        h1, h2 = st.columns([4, 1], vertical_alignment="center")
        h1.markdown(f"**{T('dq_title')}** &nbsp; {head}", unsafe_allow_html=True, help=T("dq_help"))
        if h2.button(T("prev_full"), icon=":material/open_in_full:", key="g_prev_full", width="stretch"):
            _full_preview(ctx, checks)
        st.markdown("".join(rows), unsafe_allow_html=True)
    ctx.dq_checks = checks
    return checks


# ---- úseky podle vstupů (MV a každá měřená porucha má vlastní úseky) a vyřazení dat podle mezí
WIN_COLORS = {"MV": "#f59e0b"}
DIST_WIN_COLORS = ["#0d9488", "#7c3aed", "#db2777", "#0891b2"]


def _win_inputs(ctx):
    return ["MV"] + [str(c) for c in ctx.c_d]


def _win_color(ctx, inp):
    return WIN_COLORS.get(inp) or DIST_WIN_COLORS[_win_inputs(ctx).index(inp) % len(DIST_WIN_COLORS) - 1]


def _win_store(ctx, rng0):
    """Úseky {vstup: [[od, do] s]} této smyčky a souboru; MV začíná společným úsekem, poruchy bez úseků."""
    key = f"wins|{ctx.fname}"
    W = dict(ss.get(key) or {})
    for inp in _win_inputs(ctx):
        W.setdefault(inp, [[float(rng0[0]), float(rng0[1])]] if inp == "MV" else [])
    ss[key] = W
    return W


def _add_window(ctx, a, b):
    """Přidá úsek [a, b] vstupu, který se právě upravuje (tažení v grafu)."""
    key = f"wins|{ctx.fname}"
    W = dict(ss.get(key) or {})
    inp = ss.get("win_edit_for") or "MV"
    W[inp] = list(W.get(inp, [])) + [[float(a), float(b)]]
    ss[key] = W
    ss["wver"] = ss.get("wver", 0) + 1


def _input_windows(ctx, rng0, step, tu):
    """Úseky podle vstupů (panel): výběr vstupu, tabulka jeho úseků; vrací rozpětí všech úseků (pro další záložky)."""
    t = ctx.t
    W = _win_store(ctx, rng0)
    inputs = _win_inputs(ctx)
    st.caption(T("win_intro"))
    inp = seg(st, T("win_edit_for"), inputs, "MV", "win_edit_for", help=T("h_win_edit_for"), width="stretch") or "MV"
    U = {"s": 1.0, "min": 60.0, "h": 3600.0}[tu]
    df = pd.DataFrame([[a / U, b / U] for a, b in W[inp]], columns=[T("win_from", u=tu), T("win_to", u=tu)])
    ed = st.data_editor(df, num_rows="dynamic", hide_index=True, width="stretch",
                        key=f"wed|{ctx.fname}|{inp}|{ss.get('wver', 0)}",
                        column_config={c: st.column_config.NumberColumn(c, min_value=0.0, max_value=float(t[-1]) / U,
                                                                        format="%.4g") for c in df.columns})
    new = []
    for a, b in ed.to_numpy(float):
        if np.isfinite(a) and np.isfinite(b) and abs(b - a) * U > step:
            new.append([float(min(a, b) * U), float(max(a, b) * U)])
    if new != W[inp]:
        W[inp] = new
        ss[f"wins|{ctx.fname}"] = W
    for x in inputs:
        n = len(W[x])
        tot = sum(b - a for a, b in W[x])
        st.markdown(f"<span class='pid-chip sn' style='border-color:{_win_color(ctx, x)}'>{html.escape(x)}: "
                    f"{T('win_count', n=n, d=dur(tot))}</span>", unsafe_allow_html=True)
    st.caption(T("win_drag"))
    # indexy úseků pro identifikaci
    ctx.wins_s = {x: [tuple(w) for w in W[x]] for x in inputs}
    idx = []
    for x in inputs:
        for a, b in W[x]:
            idx.append((int(np.searchsorted(t, a)), int(np.searchsorted(t, b, side="right"))))
    ctx.win_idx = idx
    if not idx:
        return float(rng0[0]), float(rng0[1])
    return float(t[min(a for a, _ in idx)]), float(t[min(len(t), max(b for _, b in idx)) - 1])


def _exclusions(ctx):
    """Vyřazení dat: meze PV / MV / poruch (inženýrské jednotky) a tolerance → ctx.valid (vzorky do fitu)."""
    from ...app import model as mdl
    st.caption(T("excl_intro"))
    sigs = [("PV", ctx.pv_e, (ctx.pv_lo, ctx.pv_hi), True), ("MV", ctx.mv_e, (ctx.mvl_lo, ctx.mvl_hi), True)]
    for nm, d in zip(ctx.c_d, ctx.dists):
        sigs.append((str(nm), d, (float(np.nanmin(d)), float(np.nanmax(d))), False))
    h = st.columns([1.1, 1.4, 1.4, 0.7], vertical_alignment="bottom")
    h[1].caption("Min")
    h[2].caption("Max")
    h[3].caption(T("excl_on"))
    limits, signals = [], []
    for nm, x, (lo, hi), on in sigs:
        k = f"excl|{ctx.fname}|{nm}"
        c = st.columns([1.1, 1.4, 1.4, 0.7], vertical_alignment="center")
        c[0].markdown(f"**{html.escape(nm)}**")
        lo_ = num("Min", f"{k}|lo", lo, c[1], label_visibility="collapsed", format="%.5g")
        hi_ = num("Max", f"{k}|hi", hi, c[2], label_visibility="collapsed", format="%.5g")
        if f"{k}|on" not in ss:
            ss[f"{k}|on"] = on
        on_ = c[3].checkbox(T("excl_on"), key=f"{k}|on", label_visibility="collapsed")
        limits.append((on_, lo_, hi_))
        span = (hi - lo) if hi > lo else 1.0
        signals.append((x, span))
    tol = num(T("excl_tol"), f"excl|{ctx.fname}|tol", 0.5, min_value=0.0, max_value=20.0, format="%.2g",
              help=T("h_excl_tol"))
    ctx.valid = mdl.valid_mask(len(ctx.t), signals, limits, tol)
    ctx.excl_key = (tuple(limits), float(tol))
    st.caption(T("excl_count", d=dur(float((~ctx.valid).sum() * ctx.Ts)), p=f"{100 * (~ctx.valid).mean():.1f}"))


def _window_shapes(ctx, shapes, notes, n_rows):
    """Úseky vstupů (barva podle vstupu) a vyřazené vzorky (šedě) do grafu záznamu."""
    t = ctx.t
    for x, ws_ in (getattr(ctx, "wins_s", None) or {}).items():
        col = _win_color(ctx, x)
        for a, b in ws_:
            for r in range(1, n_rows + 1):
                sfx = "" if r == 1 else str(r)
                shapes.append(dict(type="rect", xref=f"x{sfx}", yref=f"y{sfx} domain", x0=a, x1=b, y0=0, y1=1,
                                   fillcolor=col, opacity=0.14, line=dict(color=col, width=1), layer="below"))
            notes.append(dict(xref="x", yref="y domain", x=a, y=1, text=x, showarrow=False, xanchor="left",
                              yanchor="top", font=dict(size=11, color=col)))
    v = getattr(ctx, "valid", None)
    if v is not None and (~v).any():
        d = np.diff(np.r_[0, (~v).astype(int), 0])
        for a, b in zip(np.where(d == 1)[0][:200], np.where(d == -1)[0][:200]):
            for r in range(1, n_rows + 1):
                sfx = "" if r == 1 else str(r)
                shapes.append(dict(type="rect", xref=f"x{sfx}", yref=f"y{sfx} domain", x0=t[a], x1=t[min(b, len(t) - 1)],
                                   y0=0, y1=1, fillcolor="#64748b", opacity=0.18, line_width=0, layer="below"))


def render(ctx):
    """
    Graf načtených dat (záložka Data) a výběr úseku pro identifikaci – posuvník, tažení v grafu, automaticky nalezené
    úseky, kontrola kvality – vykreslený na začátku záložky Model (úsek je součástí identifikace). Počítá se tady,
    protože úsek potřebují všechny další záložky.
    """
    t, Ts, pv, mv, sp, has_sp = ctx.t, ctx.Ts, ctx.pv, ctx.mv, ctx.sp, ctx.has_sp
    with ctx.tabs["data"]:
        with ctx.dws.m_chart.container(border=True, key="pid_card_rec"):
            show(ctx.data_fig(t), key=f"chart_data_all|{ctx.fname}", fname="data_all")
            st.caption(T("data_chart_help"))
        with ctx.dws.m_dq:
            _quality(ctx)
    with ctx.tabs["model"]:
        ctx.gph["model"] = st.container()      # průvodce záložky Model nahoře (vyplní se na konci běhu)
        ws = workspace()
        with ws.side:
            ws.top = st.container()            # tlačítko Identifikovat a průběh
        with ws.main:
            ws.m_bar = st.container(border=True, key="pid_card_mbar")   # lišta: úseky (společný / podle vstupů), myš
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

        segs = segs_mod.auto(t, mv, sp, Ts, has_sp, qmodel, ss.get("seg_gap"), pv)
        sec_seg = section(ws.side, T("dk_sec_segment"), "mod_seg", icon=":material/straighten:",
                          expanded=ss.get("win_mode") == "inputs")
        sec_excl = (section(ws.side, T("excl_title"), "mod_excl", icon=":material/block:")
                    if ss.get("win_mode") == "inputs" else None)
        sec_auto = section(ws.side, T("auto_title", n=len(segs)), "mod_auto", expanded=False,
                           icon=":material/auto_awesome:")
        ws.ident = section(ws.side, T("dk_sec_ident"), "mod_ident", icon=":material/model_training:")
        ws.model = section(ws.side, T("dk_sec_model"), "mod_model", icon=":material/tune:")
        ws.unc = section(ws.side, T("unc_title"), "mod_unc", expanded=False, icon=":material/scatter_plot:")

        b1_, b2_ = ws.m_bar.columns(2, vertical_alignment="center")
        win_mode = seg(b1_, T("win_mode"), ["common", "inputs"], "common", "win_mode",
                       format_func=lambda x: T("win_mode_" + x), help=T("h_win_mode")) or "common"
        ctx.win_mode = win_mode
        drag = seg(b2_, T("mouse"), ["zoom", "select"], "zoom", "drag",
                   format_func=lambda x: T("mouse_" + x), help=T("h_mouse")) or "zoom"
        with sec_seg:
            tu_ = unit_for(ss.get("chart_tunit"), float(t[-1]))
            if win_mode == "common":
                st.caption(T("seg_intro"))
                rng = st.slider(T("seg_id"), 0.0, float(t[-1]), step=step, key=rng_key, help=T("h_seg_id"))
                st.caption(T("seg_span", a=fmt_t(rng[0], tu_), b=fmt_t(rng[1], tu_), d=dur(rng[1] - rng[0])))
            else:
                rng = _input_windows(ctx, ss[rng_key], step, tu_)
            q_box = st.container()
        if win_mode == "inputs" and sec_excl is not None:
            with sec_excl:
                _exclusions(ctx)
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
                    tu_ = unit_for(ss.get("chart_tunit"), float(t[-1]))
                    rows_s.append({"#": i_ + 1, T("auto_from"): fmt_t(sg["start"], tu_), T("auto_to"): fmt_t(sg["end"], tu_),
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
            # úseky jako tvary vložené najednou: add_vrect po jednom prochází celý graf (u dlouhých záznamů se
            # stovkami úseků trvalo překreslení desítky sekund)
            n_rows = 2 + (1 if ctx.dists else 0) + (1 if resid is not None else 0)
            shapes, notes = list(fig.layout.shapes or ()), list(fig.layout.annotations or ())
            for i_, sg in enumerate(segs[:MAX_SEG_SHADES]):
                shapes.append(dict(type="rect", xref="x", yref="y domain", x0=sg["start"], x1=sg["end"], y0=0, y1=1,
                                   fillcolor="#bfdbfe", opacity=0.22, line_width=0, layer="below"))
                notes.append(dict(xref="x", yref="y domain", x=sg["start"], y=1, text=f"#{i_ + 1}", showarrow=False,
                                  xanchor="left", yanchor="top", font=dict(size=11, color="#1e40af")))
            if win_mode == "common":
                for r in range(1, n_rows + 1):
                    sfx = "" if r == 1 else str(r)
                    shapes.append(dict(type="rect", xref=f"x{sfx}", yref=f"y{sfx} domain", x0=rng[0], x1=rng[1], y0=0,
                                       y1=1, fillcolor="#fde68a", opacity=0.25, line_width=0, layer="below"))
            else:
                _window_shapes(ctx, shapes, notes, n_rows)
            fig.update_layout(shapes=shapes, annotations=notes)
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
                    if win_mode == "inputs":         # tažení přidá úsek vstupu, který se právě upravuje
                        _add_window(ctx, snap(xr[0]), snap(xr[1]))
                    else:
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
