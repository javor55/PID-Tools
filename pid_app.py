"""
Identifikace procesu a ladění PIDConL (SIMATIC PCS 7 APL).
Spuštění / Run:  streamlit run pid_app.py
"""
import io
from contextlib import nullcontext
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import json
import datetime as _dt
from pid_core import (MODELS, DIST_PARAMS, fit_model, predict, tune, default_tc, integ_gain, ff_gain,
                      pidconl_sim, robustness, iae, step_response, demo_data, d_advice, optimize_migo, mv_noise,
                      simulate, oscillation, stiction_ccf, valve_hysteresis, loop_kpis, local_gains,
                      bootstrap_models, step_plan, cascade_sim, outer_with_inner, data_quality, find_segments,
                      optimize_time, closed_loop_steps, overshoot_ratio, predict_full, model_metrics, dyn_scale,
                      fit_with_stiction, stiction_valve, pidconl_sim_full, optimize_scenario)
from i18n import TEXTS

# ---- rychlost: výsledky náročných výpočtů se ukládají do cache (stejné vstupy = okamžitý výsledek)
_cache = st.cache_data(show_spinner=False, max_entries=256)
pidconl_sim = _cache(pidconl_sim)
robustness = _cache(robustness)
cascade_sim = _cache(cascade_sim)
loop_kpis = _cache(loop_kpis)
local_gains = _cache(local_gains)
fit_model = _cache(fit_model)

st.set_page_config(page_title="PIDConL Tuner", page_icon="🎛️", layout="wide")
ss = st.session_state
if "lang" not in ss:
    ss.lang = "cs"


def T(key, **kw):
    s = TEXTS[ss.lang].get(key, TEXTS["cs"].get(key, key))
    return s.format(**kw) if kw else s


# ================================================================ vzhled
st.markdown("""
<style>
.block-container {padding-top: 1.6rem; padding-bottom: 3rem; max-width: 1500px;}
h1 {font-weight: 650; letter-spacing: -0.01em; margin-bottom: 0.1rem;}
h4 {margin-top: 0.4rem; font-weight: 600;}
[data-testid="stMetric"] {background: #f4f7fb; border: 1px solid #e2e8f0; border-radius: 10px;
                          padding: 0.55rem 0.9rem;}
[data-testid="stMetricLabel"] p {font-size: 0.82rem; color: #52606d;}
[data-testid="stMetricValue"] {font-size: 1.45rem; font-variant-numeric: tabular-nums;}
.stTabs [data-baseweb="tab-list"] {gap: 0.4rem;}
.stTabs [data-baseweb="tab"] {padding: 0.45rem 0.9rem; border-radius: 8px 8px 0 0;}
section[data-testid="stSidebar"] h3 {font-size: 1.0rem; margin-top: 0.6rem;}
.pid-status {color: #52606d; font-size: 0.9rem; margin-bottom: 0.6rem;}
.pid-big {font-size: 0.8rem; color: #52606d;}
.pid-prog {display: flex; flex-wrap: wrap; gap: 0.4rem; align-items: center; margin: 0.2rem 0 0.3rem 0;}
.pid-chip {border-radius: 999px; padding: 0.18rem 0.7rem; font-size: 0.85rem; border: 1px solid; white-space: nowrap;}
.pid-chip.s0 {background: #ecfdf3; color: #166534; border-color: #bbf7d0;}
.pid-chip.s1 {background: #fffbeb; color: #92400e; border-color: #fde68a;}
.pid-chip.s2 {background: #fef2f2; color: #991b1b; border-color: #fecaca;}
.pid-chip.sn {background: #f8fafc; color: #64748b; border-color: #e2e8f0;}
.pid-arrow {color: #cbd5e1;}
.pid-next {color: #334155; font-size: 0.9rem; margin-bottom: 0.4rem;}
.pid-q {font-size: 0.9rem; line-height: 1.55;}
</style>""", unsafe_allow_html=True)

C_PV, C_SP, C_MV = "#1f5fa8", "#9aa5b1", "#c2410c"
C_DIST = ["#0f766e", "#7c3aed", "#a16207", "#334155"]
C_MODEL = {"P0D": "#94a3b8", "P1D": "#ea580c", "P2D": "#16a34a", "I0D": "#9333ea", "I1D": "#db2777"}
C_CUR, C_NEW, C_EDIT = "#64748b", "#15803d", "#111827"
FONT = "Inter, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"


# ================================================================ pomocné funkce – data
@st.cache_data(show_spinner=False, max_entries=4)
def load_table(cache_key, name, _raw):
    """Načtení souboru – jen jednou pro daný soubor (klíč = název, velikost, id nahrání)."""
    return read_table(name, _raw)


@st.cache_data(show_spinner=False, max_entries=8)
def time_cached(cache_key, col, unit_mult, _series):
    return to_seconds(_series, unit_mult)


@st.cache_data(show_spinner=False, max_entries=4)
def pivot_cached(cache_key, c_tag, c_tim, c_val, unit_mult, _df):
    tmp = pd.DataFrame({"tag": _df[c_tag].astype(str), "t": to_seconds(_df[c_tim], unit_mult), "v": to_num(_df[c_val])})
    wide = tmp.pivot_table(index="t", columns="tag", values="v", aggfunc="mean").reset_index()
    wide.columns.name = None
    return wide


@st.cache_data(show_spinner=False, max_entries=8)
def resample_cached(cache_key, _t_all, _cols, Ts_user):
    return resample(_t_all, _cols, zoh={1}, Ts_user=Ts_user, ref=0)


def read_table(name, raw_bytes):
    if name.lower().endswith((".xlsx", ".xls")):
        return pd.read_excel(io.BytesIO(raw_bytes))
    raw = raw_bytes.decode("utf-8", errors="replace")
    n_num = lambda d: sum(pd.api.types.is_numeric_dtype(d[c]) for c in d.columns)
    df = pd.read_csv(io.StringIO(raw), sep=None, engine="python")
    try:
        df2 = pd.read_csv(io.StringIO(raw), sep=None, engine="python", decimal=",")
        if n_num(df2) > n_num(df):
            df = df2
    except Exception:
        pass
    return df


def to_seconds(col, unit_mult=1.0):
    if pd.api.types.is_numeric_dtype(col):
        v = col.astype(float).to_numpy() * unit_mult
        return v - np.nanmin(v)
    ts = pd.to_datetime(col, dayfirst=True, errors="coerce")
    if ts.isna().mean() > 0.5:
        raise ValueError(T("err_time"))
    return (ts - ts.min()).dt.total_seconds().to_numpy()


def to_num(col):
    if pd.api.types.is_numeric_dtype(col):
        return col.to_numpy(float)
    return pd.to_numeric(col.astype(str).str.replace(",", ".", regex=False).str.strip(),
                         errors="coerce").to_numpy(float)


def resample(t, cols, zoh, Ts_user=None, ref=0):
    valid = []
    for c in cols:
        m = np.isfinite(t) & np.isfinite(c)
        tv, cv = t[m], c[m]
        o = np.argsort(tv, kind="stable")
        tv, cv = tv[o], cv[o]
        tv, idx = np.unique(tv, return_index=True)
        valid.append((tv, cv[idx]))
    if any(len(v[0]) < 5 for v in valid):
        raise ValueError(T("err_few"))
    t0 = max(v[0][0] for v in valid)
    t1 = (min(v[0][-1] for i, v in enumerate(valid) if i not in zoh) if len(zoh) < len(valid)
          else max(v[0][-1] for v in valid))
    Ts = Ts_user if Ts_user else float(np.median(np.diff(valid[ref][0])))
    n = int((t1 - t0) / Ts) + 1
    if n > 30000:
        Ts = (t1 - t0) / 30000
        n = 30001
    tg = t0 + np.arange(n) * Ts
    out = []
    for i, (tv, cv) in enumerate(valid):
        if i in zoh:
            j = np.clip(np.searchsorted(tv, tg, side="right") - 1, 0, len(tv) - 1)
            out.append(cv[j])
        else:
            out.append(np.interp(tg, tv, cv))
    return tg - t0, Ts, out, t0


def compression_warnings(t, v, name):
    m = np.isfinite(t) & np.isfinite(v)
    t, v = t[m], v[m]
    o = np.argsort(t)
    t, v = t[o], v[o]
    w = []
    dt = np.diff(t)
    dt = dt[dt > 0]
    if len(dt) > 10 and np.std(dt) / np.median(dt) > 1.0:
        w.append(T("warn_irregular", name=name))
    if len(v) > 20 and np.mean(np.diff(v) == 0) > 0.5:
        w.append(T("warn_repeated", name=name))
    return w


def _lag_ui(x, T_, h_):
    a_ = np.exp(-h_ / max(T_, 1e-9))
    from scipy.signal import lfilter as _lf
    return _lf([1 - a_], [1, -a_], x)


def num(label, key, default, container=st, **kw):
    if key not in ss:
        ss[key] = float(default)
    return container.number_input(label, key=key, **kw)


def sel(cont, label, opts, idx, key, **kw):
    """selectbox s výchozím indexem bez konfliktu se session state."""
    if ss.get(key) not in opts:
        ss[key] = opts[idx]
    return cont.selectbox(label, opts, key=key, **kw)


def seg(cont, label, opts, default, key, **kw):
    if key not in ss or ss[key] not in opts:
        ss[key] = default
    return cont.segmented_control(label, opts, key=key, **kw)


def sld(cont, label, lo, hi, default, key, **kw):
    v = ss.get(key)
    if v is None or not isinstance(v, (int, float)) or not (lo <= v <= hi):
        ss[key] = default
    return cont.slider(label, lo, hi, key=key, **kw)


def tog(cont, label, default, key, **kw):
    if key not in ss:
        ss[key] = bool(default)
    return cont.toggle(label, key=key, **kw)


def fmt(v, d=4):
    return "∞" if v is None or not np.isfinite(v) else f"{v:.{d}g}"


def notes_text(notes):
    return " ".join(T(k, **a) for k, a in notes)


def model_name(c):
    return T("model_" + c)


@st.cache_data(show_spinner=False, max_entries=64)
def opt_cached(code, p, ctype, samp_, dg, ms, hf, starts, extra=(), pvf=0.0):
    return optimize_migo(code, list(p), ctype, samp_, dg, ms, hf, starts, [list(e) for e in extra], pvf)


@st.cache_data(show_spinner=False, max_entries=128)
def topt_cached(code, p, ctype, samp_, dg, crit, target, ms, hf, starts, extra=(), ovs=0.02, pfb=False, dfb=True,
                pvf=0.0, rate=0.0, sp_amp=1.0, d_amp=1.0):
    return optimize_time(code, list(p), ctype, samp_, dg, crit, target, ms, hf, starts, [list(e) for e in extra], ovs,
                         pfb, dfb, pvf, rate, sp_amp, d_amp)


@st.cache_data(show_spinner=False, max_entries=32)
def sopt_cached(code, p, pdl, ctype, ctrl_base, crit, h, sp, pv0, mv0, dmeas, dist_mv, dist_pv, ms, hf, starts,
                extra=(), ovs=0.02):
    return optimize_scenario(code, list(p), [list(d) for d in pdl], ctype, dict(ctrl_base), crit, h, np.asarray(sp),
                             pv0, mv0, [np.asarray(d) for d in dmeas], np.asarray(dist_mv), np.asarray(dist_pv), ms, hf,
                             starts, [list(e) for e in extra], ovs)


REPORT = {"figs": [], "tables": [], "notes": []}


# ================================================================ pomocné funkce – grafy
def mkfig(n_rows, heights=None):
    return make_subplots(rows=n_rows, cols=1, shared_xaxes=True, vertical_spacing=0.035,
                         row_heights=heights or [1 / n_rows] * n_rows)


def _decim(x, y, n=4000):
    """Min-max zředění pro vykreslení: max. ~n bodů, špičky zůstanou zachované."""
    x, y = np.asarray(x), np.asarray(y, float)
    if len(x) <= n or not np.all(np.isfinite(y)):
        return x, y
    k = int(np.ceil(len(x) / (n / 2)))
    m = len(x) // k * k
    xr, yr = x[:m].reshape(-1, k), y[:m].reshape(-1, k)
    rows = np.arange(len(xr))
    i1, i2 = np.argmin(yr, 1), np.argmax(yr, 1)
    a, b = np.minimum(i1, i2), np.maximum(i1, i2)
    xs = np.column_stack([xr[rows, a], xr[rows, b]]).ravel()
    ys = np.column_stack([yr[rows, a], yr[rows, b]]).ravel()
    return np.r_[xs, x[m:]], np.r_[ys, y[m:]]


def tr(x, y, name, color, width=1.6, dash=None, shape=None, show=True, group=None, opacity=1.0):
    x, y = _decim(x, y)
    cls = go.Scattergl if len(x) > 4000 else go.Scatter
    return cls(x=x, y=y, name=name, mode="lines", opacity=opacity, showlegend=show,
               legendgroup=group or name,
               line=dict(color=color, width=width, dash=dash, shape=shape or "linear"))


def _make_template():
    """Vlastní šablona grafů – nastaví se jednou (rychlejší než stylovat každý graf zvlášť)."""
    import plotly.io as pio
    if "pidtuner" not in pio.templates:
        tpl = go.layout.Template(pio.templates["plotly_white"])
        tpl.layout.update(font=dict(family=FONT, size=12, color="#1f2933"), margin=dict(l=8, r=8, t=36, b=8),
                          hovermode="x unified", hoversubplots="axis", hoverlabel=dict(font=dict(family=FONT)),
                          legend=dict(orientation="h", yanchor="bottom", y=1.01, x=0, bgcolor="rgba(0,0,0,0)"))
        tpl.layout.xaxis.update(showspikes=True, spikemode="across", spikesnap="cursor", spikethickness=1,
                                spikecolor="#94a3b8", gridcolor="#eef2f6", zeroline=False)
        tpl.layout.yaxis.update(gridcolor="#eef2f6", zeroline=False)
        pio.templates["pidtuner"] = tpl
    if pio.templates.default != "pidtuner":
        pio.templates.default = "pidtuner"


_make_template()


def style(fig, height, ytitles=(), xtitle=None, rev="keep"):
    fig.update_layout(height=height, uirevision=rev)
    for i, t in enumerate(ytitles):
        fig.update_yaxes(title_text=t, row=i + 1, col=1)
    if xtitle and ytitles:
        fig.update_xaxes(title_text=xtitle, row=len(ytitles), col=1)
    elif xtitle:
        fig.update_xaxes(title_text=xtitle)
    return fig


def show(fig, key=None, fname="graf", select=False, report=None):
    if report:
        REPORT["figs"].append((report, fig))
    cfg = {"displaylogo": False, "modeBarButtonsToRemove": ["lasso2d", "autoScale2d"],
           "toImageButtonOptions": {"format": "png", "scale": 2, "filename": fname}}
    if select:
        return st.plotly_chart(fig, width="stretch", config=cfg, key=key, on_select="rerun",
                               selection_mode="box")
    return st.plotly_chart(fig, width="stretch", config=cfg, key=key)


def apply_project(proj):
    """Obnoví stav aplikace z projektu (před vykreslením widgetů)."""
    ss.proj = proj
    for k_, v_ in proj.get("state", {}).items():
        ss[k_] = v_
    fnames = [proj.get("fname", "")]
    if proj.get("data"):
        n_ = len(next(iter(proj["data"]["cols"].values())))
        fnames.append(f"project|{proj.get('tag', '')}|{n_}")
        ss["src"] = "project"
        ss["c_tim"], ss["long_fmt"], ss["ts_manual"], ss["time_unit"] = "t_s", False, False, "s"
    for fn_ in fnames:
        for k_, v_ in proj.get("map", {}).items():
            ss[f"{k_}|{fn_}"] = v_
    rg = proj.get("ranges", {})
    if rg.get("id"):
        ss["pending_rng"] = tuple(rg["id"])
    if rg.get("val"):
        ss["pending_rngv"] = tuple(rg["val"])
    if "fit" in proj:
        ss.fit = dict(key="__restore__", res=proj["fit"]["res"], dnames=proj["fit"]["dnames"])
    if "vchar_last" in proj.get("state", {}):
        ss["vchar_init"] = proj["state"]["vchar_last"]
    for k_ in [k_ for k_ in list(ss.keys()) if str(k_).startswith("scen_ed|")]:
        del ss[k_]
    ss["override_new"] = proj.get("new")
    ss["override_ff"] = proj.get("ff")
    ss["loop_tag"] = proj.get("tag", "")


# ================================================================ horní panel
def load_project_file():
    pf = ss.get("proj_up")
    if pf is None:
        return
    raw_p = pf.getvalue()
    hsh = hash(raw_p)
    if ss.get("proj_hash") != hsh:
        try:
            apply_project(json.loads(raw_p.decode("utf-8")))
            ss.proj_hash = hsh
        except Exception as ex:
            ss.proj_err = str(ex)


hc1, hc2 = st.columns([3, 1.6], vertical_alignment="center")
hc1.title(T("title"))
with hc2:
    b1, b2, b3 = st.columns(3)
    with b1.popover(T("tb_project"), icon=":material/folder_open:", width="stretch"):
        st.text_input(T("loop_tag"), key="loop_tag", placeholder="LIC101", help=T("h_loop_tag"))
        st.file_uploader(T("proj_load"), type=["json"], key="proj_up", help=T("h_proj_load"),
                         on_change=load_project_file)
        if ss.get("proj_err"):
            st.error(T("err_proj", ex=ss.pop("proj_err")))
        st.caption(T("proj_help"))
    with b2.popover(T("tb_help"), icon=":material/help:", width="stretch"):
        st.markdown(f"**{T('guide_title')}**")
        st.markdown(T("guide_body"))
        st.divider()
        st.markdown(f"**{T('gloss_title')}**")
        st.markdown(T("gloss_body"))
    with b3.popover(T("tb_settings"), icon=":material/settings:", width="stretch"):
        st.radio("Jazyk / Language", ["cs", "en"], key="lang", horizontal=True,
                 format_func=lambda x: {"cs": "Čeština", "en": "English"}[x])
        H = sld(st, T("plot_height"), 300, 900, 460, "plot_h", step=20, help=T("h_plot_h"))

# ---- datová lišta: zdroj, soubor, souhrn
with st.container(border=True):
    d1, d2, d3 = st.columns([1.5, 1.6, 3.4], vertical_alignment="center")
    src_opts = ["file", "demo"] + (["project"] if ss.get("proj", {}).get("data") else [])
    if ss.get("src") not in src_opts:
        ss["src"] = "file"
    src = seg(d1, T("source"), src_opts, "file", "src", format_func=lambda x: T("src_" + x), help=T("h_source"),
              label_visibility="collapsed") or "file"
    df, fname, ckey = None, "demo", "demo"
    if src == "project":
        pdat = ss.proj["data"]
        df = pd.DataFrame(pdat["cols"])
        fname = f"project|{ss.proj.get('tag', '')}|{len(df)}"
        ckey = f"{fname}|{ss.get('proj_hash')}"
        d2.caption(T("proj_data_caption", n=len(df)))
    elif src == "file":
        cur_f = ss.get("up_file")
        with d2.popover(cur_f.name if cur_f is not None else T("tb_choose_file"), icon=":material/upload_file:",
                        width="stretch", type="secondary" if cur_f is not None else "primary"):
            f = st.file_uploader(T("upload"), type=["csv", "txt", "xlsx", "xls"], key="up_file")
        if f is not None:
            fname = f"{f.name}|{f.size}"
            ckey = f"{fname}|{f.file_id}"
            try:
                with st.spinner(T("loading")):
                    df = load_table(ckey, f.name, f.getvalue())
            except Exception as ex:
                st.error(T("err_read", ex=ex))
    else:
        t_, sp_, pv_, mv_, q_ = demo_data()
        df = pd.DataFrame({"Cas": t_, "LIC101.SP": sp_, "LIC101.PV": pv_, "LIC101.MV": mv_, "FI100.Pritok": q_})
        d2.download_button(T("demo_dl"), df.to_csv(index=False, sep=";", decimal=","), "demo_level.csv", "text/csv",
                           icon=":material/download:", help=T("demo_desc"), width="stretch")
    status_ph = d3.empty()

if df is None:
    status_ph.caption(T("empty"))
    st.info(T("empty"), icon=":material/upload_file:")
    st.stop()

prog_ph = st.empty()
PROG = {}

tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs(
    [T("tab1"), T("tab2"), T("tab3"), T("tab4"), T("tab5"), T("tab6"), T("tab7"), T("tab8")])

# ---- záložka Data: sloupce a normování (nahoře)
with tab1:
    cols_exp = st.expander(T("cols_title"), expanded="fit" not in ss, icon=":material/table_chart:")
    mc1, mc2 = cols_exp.columns([2.2, 1], gap="large")

cols = list(df.columns)


def guess(keys, default=0, among=None):
    among = among or cols
    for k in keys:
        for c in among:
            if k in str(c).lower():
                return among.index(c)
    return min(default, len(among) - 1)


with mc1:
    st.markdown(f"**{T('cols_signals')}**")
    r1 = st.columns(4, vertical_alignment="bottom")
    long_fmt = r1[0].toggle(T("long_fmt"), key="long_fmt", help=T("long_fmt_help"))
    time_unit = r1[1].selectbox(T("time_unit"), ["s", "ms", "min", "h"], help=T("time_unit_help"), key="time_unit")
    unit_mult = {"s": 1, "ms": 1e-3, "min": 60, "h": 3600}[time_unit]
    ts_manual = r1[2].toggle(T("ts_manual"), key="ts_manual", help=T("h_ts_manual"))
    Ts_user = num(T("ts_data"), "ts_user", 1.0, r1[3], min_value=0.001) if ts_manual else None
    try:
        if long_fmt:
            r2 = st.columns(3)
            c_tag = sel(r2[0], T("col_tag"), cols, guess(["tag", "name", "název", "variable"]), key="c_tag")
            c_tim = sel(r2[1], T("col_time"), cols, guess(["time", "čas", "cas", "timestamp"], 1), key="c_tim_l")
            c_val = sel(r2[2], T("col_value"), cols, guess(["value", "hodnota", "val"], 2), key="c_val")
            wide = pivot_cached(ckey, c_tag, c_tim, c_val, unit_mult, df)
            t_all = wide["t"].to_numpy(float)
            sigs = [c for c in wide.columns if c != "t"]
            get = lambda c: wide[c].to_numpy(float)
        else:
            c_tim = sel(st, T("col_time"), cols, guess(["cas", "čas", "time", "datum", "date"]), key="c_tim")
            t_all = time_cached(ckey, c_tim, unit_mult, df[c_tim])
            sigs = [c for c in cols if c != c_tim]
            get = lambda c: to_num(df[c])
    except Exception as ex:
        st.error(T("err_data", ex=ex))
        st.stop()
    r3 = st.columns(3)
    c_pv = sel(r3[0], "PV", sigs, guess([".pv", "pv", "meren", "meas"], 1, sigs), key=f"c_pv|{fname}", help=T("h_pv"))
    c_mv = sel(r3[1], "MV", sigs, guess([".mv", "mv", "out", "ventil", "valve"], 2, sigs), key=f"c_mv|{fname}",
               help=T("h_mv"))
    sp_opts = ["—"] + sigs
    c_sp = sel(r3[2], T("col_sp"), sp_opts, guess([".sp", "sp", "setpoint"], 0, sp_opts), key=f"c_sp|{fname}",
               help=T("h_sp"))
    r4 = st.columns([2, 1])
    d_opts = [c for c in sigs if c not in (c_pv, c_mv, c_sp)]
    c_d = r4[0].multiselect(T("col_dist"), d_opts, help=T("col_dist_help"), key=f"c_d|{fname}")
    pos_opts = ["—"] + [c for c in sigs if c not in (c_pv, c_mv, c_sp) and c not in c_d]
    c_pos = r4[1].selectbox(T("col_pos"), pos_opts, key=f"c_pos|{fname}", help=T("h_pos"))

# ================================================================ příprava dat
try:
    pv_raw, mv_raw = get(c_pv), get(c_mv)
    raw_cols = [pv_raw, mv_raw] + [get(c) for c in c_d]
    has_sp = c_sp != "—"
    if has_sp:
        raw_cols.append(get(c_sp))
    rkey = (ckey, long_fmt, unit_mult, str(c_pv), str(c_mv), str(c_sp), tuple(map(str, c_d)),
            str(ss.get("c_tag")), str(ss.get("c_tim") if not long_fmt else ss.get("c_tim_l")), str(ss.get("c_val")))
    t, Ts, rs, T0 = resample_cached(rkey, t_all, raw_cols, Ts_user)
    pv_e, mv_e = rs[0], rs[1]
    dists = rs[2:2 + len(c_d)]
    sp_e = rs[-1] if has_sp else np.full_like(pv_e, np.nan)
except Exception as ex:
    with tab1:
        st.error(T("err_data", ex=ex))
    st.stop()


def on_grid(col, zoh=False):
    """Libovolný sloupec převzorkovaný na společnou časovou mřížku t."""
    v = get(col)
    m = np.isfinite(t_all) & np.isfinite(v)
    tv, cv = t_all[m], v[m]
    o = np.argsort(tv)
    tv, cv = tv[o], cv[o]
    if len(tv) < 2:
        return np.full_like(t, np.nan)
    if zoh:
        j = np.clip(np.searchsorted(tv, t + T0, side="right") - 1, 0, len(tv) - 1)
        return cv[j]
    return np.interp(t + T0, tv, cv)


pos_e = on_grid(c_pos) if c_pos != "—" else None

with mc2:
    st.markdown(f"**{T('sb_norm')}**")
    n1, n2 = st.columns(2)
    pv_lo = num("NormPV Low", "pv_lo", float(np.floor(np.nanmin(pv_e))), n1, help=T("h_normpv"))
    pv_hi = num("NormPV High", "pv_hi", float(np.ceil(np.nanmax(pv_e))), n2, help=T("h_normpv"))
    mv_lo = num("NormMV Low", "mv_lo", 0.0, n1, help=T("h_normmv"))
    mv_hi = num("NormMV High", "mv_hi", 100.0, n2, help=T("h_normmv"))
    if "u_mv" not in ss:
        ss["u_mv"] = "%"
    u_pv = n1.text_input(T("unit_pv"), key="u_pv", placeholder="m, °C, bar…", help=T("h_unit"))
    u_mv = n2.text_input(T("unit_mv"), key="u_mv", help=T("h_unit"))
    st.caption(T("norm_help"))
if pv_hi <= pv_lo or mv_hi <= mv_lo:
    with tab1:
        st.error(T("err_range"))
    st.stop()

# ---- záložka Ladění: konfigurace bloku a současné parametry (nahoře)
with tab3:
    with st.expander(T("blk_title"), expanded=True, icon=":material/tune:"):
        k1, k2 = st.columns([2.2, 1], gap="large")
        with k1:
            st.markdown(f"**{T('sb_block')}**")
            q = st.columns(3)
            samp = num(T("sampletime"), "samp", 1.0, q[0], min_value=0.001, help=T("sampletime_help"))
            diffgain = num("DiffGain", "diffgain", 5.0, q[1], min_value=0.1, help=T("diffgain_help"))
            db_e = num(T("deadband"), "db", 0.0, q[2], min_value=0.0, help=T("h_deadband"))
            q = st.columns(3, vertical_alignment="bottom")
            mvl_lo = num("MV_LoLim", "mvl_lo", mv_lo, q[0], help=T("h_mvlim"))
            mvl_hi = num("MV_HiLim", "mvl_hi", mv_hi, q[1], help=T("h_mvlim"))
            db_mode = q[2].selectbox(T("db_mode"), ["cont", "step"], format_func=lambda x: T("db_" + x),
                                     help=T("db_mode_help"), key="db_mode")
            q = st.columns(2)
            pfb = q[0].toggle(T("pfb"), key="pfb", help=T("pfb_help"))
            if "dfb" not in ss:
                ss["dfb"] = True
            dfb = q[1].toggle(T("dfb"), key="dfb", help=T("h_dfb"))
            st.markdown(f"**{T('blk_elems')}**", help=T("h_blk_elems"))
            q = st.columns(3)
            pvfilt = num(T("pvfilt"), "pvfilt", 0.0, q[0], min_value=0.0, help=T("h_pvfilt"))
            mvrate_e = num(T("mvrate", u=ss.get("u_mv") or "MV"), "mvrate", 0.0, q[1], min_value=0.0, format="%.4g",
                           help=T("h_mvrate"))
            sprate_e = num(T("sprate", u=ss.get("u_pv") or "PV"), "sprate", 0.0, q[2], min_value=0.0, format="%.4g",
                           help=T("h_sprate"))
        with k2:
            st.markdown(f"**{T('sb_current')}**", help=T("h_current"))
            cur_gain = num("Gain", "cur_gain", 1.0, format="%.5g", help=T("h_gain"))
            q = st.columns(2)
            cur_ti = num(T("ti_zero"), "cur_ti", 100.0, q[0], min_value=0.0, format="%.5g", help=T("h_ti"))
            cur_td = num("TD [s]", "cur_td", 0.0, q[1], min_value=0.0, format="%.5g", help=T("h_td"))

PR, MR = pv_hi - pv_lo, mv_hi - mv_lo
P = lambda x: (np.asarray(x, float) - pv_lo) / PR * 100
M = lambda x: (np.asarray(x, float) - mv_lo) / MR * 100
EP = lambda x: pv_lo + np.asarray(x, float) * PR / 100
EM = lambda x: mv_lo + np.asarray(x, float) * MR / 100
pv, mv, sp = P(pv_e), M(mv_e), P(sp_e)
lab_pv = f"PV [{u_pv}]" if u_pv else "PV"
lab_mv = f"MV [{u_mv}]" if u_mv else "MV"
lab_t = T("time_s")

base_ctrl = dict(SampleTime=samp, DiffGain=diffgain, PropFbk=pfb, DiffFbk=dfb,
                 DeadBand=db_e / PR * 100, DbMode="spojité" if db_mode == "cont" else "skokové",
                 MV_Lo=float(M(mvl_lo)), MV_Hi=float(M(mvl_hi)), PVFilt=pvfilt,
                 MVRate=mvrate_e / MR * 100, SPRate=sprate_e / PR * 100)
cur_ctrl = dict(base_ctrl, Gain=cur_gain, TI=cur_ti if cur_ti > 0 else np.inf, TD=cur_td, FF=[])
BLOCK_SUMMARY = T("blk_summary", s=f"{samp:g}", dg=f"{diffgain:g}", p="✓" if pfb else "✗", d="✓" if dfb else "✗",
                  g=f"{cur_gain:.4g}", ti=f"{cur_ti:.4g}", td=f"{cur_td:.4g}")

tag_txt = ss.get("loop_tag") or ""
status_ph.markdown(
    f"<div class='pid-status' style='margin:0'>{('<b>' + tag_txt + '</b> · ') if tag_txt else ''}"
    f"{T('status', n=len(t), ts=f'{Ts:.3g}', dur=f'{t[-1]:.0f}', pvr=f'{pv_lo:g}–{pv_hi:g}', mvr=f'{mv_lo:g}–{mv_hi:g}')}"
    f"</div>", unsafe_allow_html=True)


def data_fig(ts, sel=None, extra_pv=(), resid=None, height=None):
    nr = 2 + (1 if dists else 0) + (1 if resid is not None else 0)
    hs = {2: [0.64, 0.36], 3: [0.5, 0.25, 0.25], 4: [0.44, 0.16, 0.2, 0.2]}[nr]
    f = mkfig(nr, hs)
    g = (lambda a: a[sel]) if sel is not None else (lambda a: a)
    if has_sp:
        f.add_trace(tr(ts, EP(g(sp)), "SP", C_SP, 1.4, "dash"), 1, 1)
    f.add_trace(tr(ts, EP(g(pv)), "PV", C_PV, 1.3), 1, 1)
    for name, y, col, dash in extra_pv:
        f.add_trace(tr(ts, EP(y), name, col, 2.2, dash), 1, 1)
    row = 2
    ytit = [lab_pv]
    if resid is not None:
        for name, y, col, dash in extra_pv:
            f.add_trace(tr(ts, (g(pv) - y) * PR / 100, f"{T('resid')} {name}", col, 1.2, dash, show=False,
                           group=name), row, 1)
        ytit.append(T("resid"))
        row += 1
    f.add_trace(tr(ts, EM(g(mv)), "MV", C_MV, 1.6, shape="hv"), row, 1)
    ytit.append(lab_mv)
    row += 1
    for i, (nm, d) in enumerate(zip(c_d, dists)):
        f.add_trace(tr(ts, g(d), str(nm), C_DIST[i % 4], 1.4), row, 1)
    if dists:
        ytit.append(T("dists"))
    return style(f, height or (H + (90 if dists else 0) + (80 if resid is not None else 0)), ytit, lab_t)


# ================================================================ 1) DATA
with tab1:
    for w in compression_warnings(t_all, pv_raw, "PV"):
        st.warning(w, icon=":material/compress:")
    rng_key = f"rng_id|{fname}|{t[-1]:.0f}"
    step = float(max(Ts, t[-1] / 1000))
    if "pending_rng" in ss:
        ss[rng_key] = ss.pop("pending_rng")
    if rng_key not in ss:
        ss[rng_key] = (0.0, float(t[-1]))

    with st.container(border=True):
        st.markdown(T("seg_intro"))
        c1, c2 = st.columns([3, 1.3])
        rng = c1.slider(T("seg_id"), 0.0, float(t[-1]), step=step, key=rng_key, help=T("h_seg_id"))
        drag = seg(c2, T("mouse"), ["zoom", "select"], "zoom", "drag",
                                    format_func=lambda x: T("mouse_" + x), help=T("h_mouse")) or "zoom"
    sel = (t >= rng[0]) & (t <= rng[1])

    # model pro hodnocení dat (pokud už existuje)
    qmodel = None
    if "fit" in ss and ss.get("mcode") in ss.fit.get("res", {}):
        mc_ = ss.mcode
        qmodel = (mc_, [float(ss.get(f"ed|{mc_}|{i}", v)) for i, v in enumerate(ss.fit["res"][mc_]["p"])])
    snap = lambda v: float(np.clip(round(v / step) * step, 0.0, float(t[-1])))

    def rep_frac(a, b):
        m_ = (t_all >= a + T0) & (t_all <= b + T0) & np.isfinite(pv_raw)
        v_ = pv_raw[m_]
        return float(np.mean(np.diff(v_) == 0)) if len(v_) > 20 else None

    def quality(a, b):
        m_ = (t >= a) & (t <= b)
        if m_.sum() < 20:
            return dict(level=2, checks=[("q_short", 2, {})], snr=0.0, sigma=0.0, n_steps=0)
        return data_quality(t[m_], pv[m_], mv[m_], sp[m_] if has_sp else np.zeros(m_.sum()), Ts, has_sp,
                            float(M(mvl_lo)), float(M(mvl_hi)), rep_frac(a, b), qmodel)

    # automaticky nalezené úseky
    settle = None
    if qmodel:
        pq = qmodel[1]
        settle = pq[-1] + 4 * ((pq[1] if qmodel[0] in ("P1D", "P2D", "I1D") else 0) + (pq[2] if qmodel[0] == "P2D" else 0))
    segs = find_segments(t, mv, sp if has_sp else np.zeros_like(mv), Ts, has_sp,
                         max_gap=ss.get("seg_gap") or None, settle=settle)
    with st.expander(T("auto_title", n=len(segs)), expanded=bool(segs) and rng == (0.0, float(t[-1])),
                     icon=":material/auto_awesome:"):
        if not segs:
            st.info(T("auto_none"), icon=":material/search_off:")
        else:
            rows_s = []
            for i_, sg in enumerate(segs):
                q_ = quality(sg["start"], sg["end"])
                rows_s.append({"#": i_ + 1, T("auto_from"): f"{sg['start']:.0f}", T("auto_to"): f"{sg['end']:.0f}",
                               T("auto_len"): f"{(sg['end'] - sg['start']) / 60:.1f}",
                               T("auto_steps"): f"{sg['n_mv']} / {sg['n_sp']}", T("auto_dirs"): f"{sg['up']}↑ {sg['down']}↓",
                               "SNR": f"{q_['snr']:.0f}" if np.isfinite(q_["snr"]) else "∞",
                               T("auto_quality"): ["✓ ", "⚠ ", "✗ "][q_["level"]] + T(f"q_level{q_['level']}")})
            ev_s = st.dataframe(pd.DataFrame(rows_s), hide_index=True, width="stretch", on_select="rerun",
                                selection_mode="single-row", key=f"segtab|{fname}")
            chosen_s = None
            try:
                if ev_s.selection.rows:
                    chosen_s = segs[ev_s.selection.rows[0]]
            except AttributeError:
                pass
            b1, b2, b3 = st.columns([1, 1, 1.2], vertical_alignment="bottom")
            if b1.button(T("auto_use_id"), icon=":material/model_training:", disabled=chosen_s is None):
                ss.pending_rng = (snap(chosen_s["start"]), snap(chosen_s["end"]))
                st.rerun()
            if b2.button(T("auto_use_val"), icon=":material/fact_check:", disabled=chosen_s is None):
                ss.pending_rngv = (snap(chosen_s["start"]), snap(chosen_s["end"]))
                st.rerun()
            st.caption(T("auto_help"))
        num(T("auto_gap"), "seg_gap", 0.0, min_value=0.0, help=T("h_auto_gap"))

    fig = data_fig(t)
    for i_, sg in enumerate(segs):
        fig.add_vrect(x0=sg["start"], x1=sg["end"], fillcolor="#bfdbfe", opacity=0.22, line_width=0, row=1, col=1,
                      annotation_text=f"#{i_ + 1}", annotation_position="top left",
                      annotation_font=dict(size=11, color="#1e40af"))
    for r in range(1, (3 if dists else 2) + 1):
        fig.add_vrect(x0=rng[0], x1=rng[1], fillcolor="#fde68a", opacity=0.25, line_width=0, row=r, col=1)
    fig.update_layout(dragmode="select" if drag == "select" else "zoom", selectdirection="h")
    ev = show(fig, key=f"chart_data|{fname}", fname="data", select=True, report=T("rep_fig_data"))
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
            snap = lambda v: float(np.clip(round(v / step) * step, 0.0, float(t[-1])))
            ss.pending_rng = (snap(xr[0]), snap(xr[1]))
            st.rerun()
    except Exception:
        pass

    # kontrola kvality vybraného úseku
    dq = quality(rng[0], rng[1])
    PROG["data"] = dq["level"]
    icons = ["✓", "⚠", "✗"]
    lv_ = dq["level"]
    box = [st.success, st.warning, st.error][lv_]
    fmt_a = lambda ar: {a_: ((f"{v_:.0f}" if abs(v_) >= 100 else f"{v_:.3g}") if isinstance(v_, float) else v_)
                        for a_, v_ in ar.items()}
    lines = "  \n".join(f"{icons[lv]} {T(k_, **fmt_a(ar))}" for k_, lv, ar in sorted(dq["checks"], key=lambda c_: -c_[1]))
    box(f"**{T('q_title')}: {T('q_level' + str(lv_))}**  \n{lines}",
        icon=[":material/verified:", ":material/rule:", ":material/block:"][lv_])
    if has_sp and np.nanmax(sp[sel]) - np.nanmin(sp[sel]) > 1e-6:
        st.caption(T("info_auto"))

# ================================================================ 2) MODEL
ts_id = t[sel] - t[sel][0]
pv_id, mv_id = pv[sel], mv[sel]
d_id = [d[sel] for d in dists]


def reset_edits(code):
    r = ss.fit["res"][code]
    for i, v in enumerate(r["p"]):
        ss[f"ed|{code}|{i}"] = float(v)
    for j, pd_ in enumerate(r["pdl"]):
        for i, v in enumerate(pd_):
            ss[f"ed|{code}|d{j}|{i}"] = float(v)
    ss[f"ed|{code}|stic"] = float(r.get("stic", 0.0) or 0.0)


fit_cached = _cache(fit_with_stiction)

model = None
sigma_pv = 0.0
model_stic, model_level, model_Th = 0.0, "none", None
with tab2:
    with st.container(border=True):
        c1, c2, c3 = st.columns([3, 1, 1], vertical_alignment="bottom")
        if "chosen" not in ss:
            ss["chosen"] = list(MODELS)
        chosen = c1.multiselect(T("models"), list(MODELS), format_func=model_name, key="chosen",
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

    def do_fit(c, fixed=None, stic_fixed=None):
        """Fit jednoho modelu podle nastavení (neměřené poruchy, znaménko, stikce, zafixované parametry)."""
        Th_ = None
        if stic_fixed is not None or not id_stic:
            S_ = stic_fixed or 0.0
            v_ = stiction_valve(mv_id, S_) if S_ else mv_id
            r_ = fit_model(c, ts_id[::k_dec], pv_id[::k_dec], v_[::k_dec], Ts * k_dec, [d[::k_dec] for d in d_id],
                           th_max, 20, fixed, dist_level, Th_, float(dist_strength), 0.0, sign_v)
            r_["stic"] = float(S_)
        else:
            r_ = fit_cached(c, ts_id, pv_id, mv_id, Ts, d_id, th_max, fixed, dist_level, Th_, float(dist_strength),
                            None, 13, sign_v, k_dec)
        pf_ = predict_full(c, r_["p"], r_["pdl"], ts_id, pv_id, mv_id, d_id, Ts, r_["stic"], dist_level, r_["Th"])
        r_["fit"] = pf_["fit"]
        r_["fit_raw"] = predict(c, r_["p"], r_["pdl"], ts_id, pv_id, mv_id, d_id, Ts, r_["stic"])[1]
        return r_

    if run_fit:
        if len(ts_id) < 20:
            st.error(T("err_short"))
        else:
            res = {}
            prog = st.progress(0.0, text=T("fitting"))
            for i, c in enumerate(chosen):
                prog.progress(i / max(len(chosen), 1), text=f"{T('fitting')} {model_name(c)}")
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
        PROG["model"] = 1 if ss.fit["key"] != fit_key else (0 if mm["status"] <= 1 else 1 if mm["status"] <= 3 else 2)
        PROG["model_stale"] = ss.fit["key"] != fit_key

        with c2:
            m1, m2 = st.columns(2)
            m1.metric(T("fit_fit"), f"{f_fit:.1f} %")
            m2.metric(T("fit_edit"), f"{f_ed:.1f} %", delta=f"{f_ed - f_fit:+.1f} %" if edited else None)
            ts_a, ya = step_response(mcode, rp["p"])
            ts_b, yb = step_response(mcode, model[1], horizon=ts_a[-1])
            f = go.Figure()
            f.add_trace(tr(ts_a, ya * PR / 100, T("fit"), C_MODEL[mcode], 2.2))
            if edited:
                f.add_trace(tr(ts_b, yb * PR / 100, T("edited"), C_EDIT, 2.0, "dash"))
            f.add_vline(x=model[1][-1], line=dict(color="#94a3b8", dash="dot", width=1),
                        annotation_text="θ", annotation_position="top")
            style(f, 250, xtitle=lab_t, rev=f"step|{mcode}")
            f.update_layout(title=dict(text=T("step_title"), font=dict(size=13), x=0, y=0.98),
                            yaxis_title=f"Δ{lab_pv}", margin=dict(t=48))
            show(f, key=f"step|{mcode}", fname="step_response", report=T("step_title"))

        show_res = st.toggle(T("show_resid"), key="show_resid", help=T("h_resid"))
        extra = [(f"{mcode} {T('fit')}", y_fit, C_MODEL[mcode], None)]
        if edited:
            extra.append((f"{mcode} {T('edited')}", y_ed, C_EDIT, "dash"))
        if model_level == "high" and pf_ed.get("raw") is not None:
            extra.append((T("model_wo_dist"), pf_ed["raw"], "#94a3b8", "dot"))
        show(data_fig(ts_id, sel, extra, resid=True if show_res else None), key="chart_model", fname="model",
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
            segs_eval = [(T("eval_id"), sel, mm)]
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

        if st.toggle(T("compare_all"), key="cmp_all_models"):
            ex = [(f"{c} ({r['fit']:.1f} %)", predict(c, r["p"], r["pdl"], ts_id, pv_id, mv_id, d_id, Ts,
                                                       r.get("stic", 0.0))[0], C_MODEL[c], None) for c, r in res.items()]
            show(data_fig(ts_id, sel, ex), key="chart_all", fname="models")

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

# ================================================================ 3) LADĚNÍ
with tab3:
    if model is None:
        st.info(T("need_model"), icon=":material/arrow_back:")
    else:
        mcode, p, pdl = model
        st.caption(f"{model_name(mcode)} · " + ", ".join(f"{n} = {v:.4g}" for n, v in zip(MODELS[mcode]["params"], p))
                   + " · " + T("samp_note", s=f"{samp:g}", h=f"{samp / 2:g}"))
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
                    r0 = tune(mcode, p, m0, default_tc(mcode, p, samp, m0), ct, samp)
                    starts.append((r0["Kc"], r0["Ti"], r0["Td"]))
                mg = opt_cached(mcode, tuple(p), ct, samp, diffgain, ms_, hf_, tuple(starts), robust_set, pvfilt)
                if crit_ == "MIGO":
                    return mg
                starts.append((mg["Kc"], mg["Ti"], mg["Td"]))
                sb = ss.get("scen_built") if (ss.get("scen_built") or {}).get("mcode") == mcode else None
                sp_amp, d_amp = (sb["sp_amp"], sb["d_amp"]) if sb else (5.0, 5.0)
                tg_lin = "both" if tgt_ == "scen" else tgt_
                lin = topt_cached(mcode, tuple(p), ct, samp, diffgain, crit_, tg_lin, ms_, hf_, tuple(starts), robust_set,
                                  ovs_, pfb, dfb, pvfilt, base_ctrl["MVRate"], sp_amp, d_amp)
                if tgt_ != "scen":
                    return lin
                if sb is None:
                    return dict(lin, notes=lin["notes"] + [("note_scen_missing", {})])
                starts.append((lin["Kc"], lin["Ti"], lin["Td"]))
                cb = dict(base_ctrl, **sb["plant"])
                return sopt_cached(mcode, tuple(p), tuple(tuple(d) for d in pdl), ct, cb, crit_, sb["h"], sb["sp"],
                                   sb["pv0"], sb["mv0"], tuple(sb["dmeas"]), sb["dmv"], sb["dpv"], ms_, hf_,
                                   tuple(starts), robust_set, ovs_)
            return tune(mcode, p, meth, tc_ if tc_ else default_tc(mcode, p, samp, meth), ct, samp, avg_)

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
                tc0 = default_tc(mcode, p, samp, method)
                tc = sld(st, T("tc"), float(max(0.05 * tc0, 1e-3)), float(10 * tc0), float(tc0),
                         f"tc|{mcode}|{method}", help=T("tc_help"))
        nmax = ss.get("opt_noise", 0.01 * MR)
        hf_max = (nmax / MR * 100) / sigma_pv if (nmax and sigma_pv > 0) else None  # omezení šumu MV (jen PID)
        try:
            with st.spinner(T("optimizing")) if method == "OPT" else nullcontext():
                sug = get_sug(method, ctype, tc, avg, ms_max, hf_max, crit, tgt, ovs_lim)
        except Exception as ex:
            st.error(T(str(ex)))
            sug = dict(Kc=cur_gain, Ti=cur_ti, Td=cur_td, notes=[])

        st.markdown(f"#### {T('params_title')}")
        skey = f"{sug['Kc']:.5g}|{sug['Ti']:.5g}|{sug['Td']:.5g}"
        ov = ss.pop("override_new", None)
        if ov:
            ss[f"ng|{skey}"], ss[f"nti|{skey}"], ss[f"ntd|{skey}"] = ov["Gain"], ov["TI"], ov["TD"]
        with st.container(border=True):
            n1, n2, n3, n4 = st.columns(4)
            new_gain = num("Gain", f"ng|{skey}", sug["Kc"], n1, format="%.5g", help=T("h_new_gain"))
            new_ti = num("TI [s]", f"nti|{skey}", sug["Ti"], n2, min_value=0.0, format="%.5g", help=T("h_ti"))
            new_td = num("TD [s]", f"ntd|{skey}", sug["Td"], n3, min_value=0.0, format="%.5g", help=T("h_td"))
            n4.metric("DiffGain", f"{diffgain:g}")
            st.caption(T("params_help"))
        if sug["notes"]:
            st.info(notes_text(sug["notes"]), icon=":material/lightbulb:")
        if new_gain < 0:
            st.warning(T("warn_neg_gain"), icon=":material/swap_vert:")
        if "fit" in ss and mcode in ss.fit["res"] and ss.fit["res"][mcode]["fit"] < 70:
            st.warning(T("warn_low_fit"), icon=":material/warning:")

        with st.expander(T("cmp_title"), expanded=False, icon=":material/leaderboard:"):
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
            ev_c = st.dataframe(cdf, hide_index=True, width="stretch", on_select="rerun",
                                selection_mode="single-row", key=f"cmp|{mcode}",
                                column_config={"Ms": st.column_config.NumberColumn(format="%.2f"),
                                               T("use_col"): st.column_config.TextColumn(width="large")})
            st.caption(T("cmp_help"))
            try:
                sel_rows = ev_c.selection.rows
                if sel_rows:
                    k_ = keys[sel_rows[0]]
                    if k_ != ss.get("last_cmp") and k_ != (method, ctype, crit if method == "OPT" else None):
                        ss.last_cmp = k_
                        ss.pending_tune = k_
                        st.rerun()
            except AttributeError:
                pass

        ff, ffll = [], []
        ovf = ss.pop("override_ff", None)
        if pdl:
            with st.expander(T("ff_title"), expanded=False, icon=":material/fast_forward:"):
                for j, dn in enumerate(c_d):
                    g0 = ff_gain(mcode, p, pdl[j])
                    tl0 = (p[1] if mcode in ("P1D", "P2D", "I1D") else 0.0) + (p[2] if mcode == "P2D" else 0.0)
                    tg0 = pdl[j][1]
                    dl0 = max(0.0, pdl[j][2] - p[-1])
                    if ovf and j < len(ovf):
                        o_ = ovf[j]
                        ss[f"ffuse|{j}"] = bool(o_.get("use"))
                        ss[f"ffg|{j}|{g0:.5g}"] = o_.get("gain", g0)
                        ss[f"ffdyn|{j}"] = bool(o_.get("dyn"))
                        ss[f"fftl|{j}|{tl0:.5g}"], ss[f"fftg|{j}|{tg0:.5g}"], ss[f"ffdl|{j}|{dl0:.5g}"] = \
                            o_.get("lead", tl0), o_.get("lag", tg0), o_.get("delay", dl0)
                    f1, f2 = st.columns([1, 2], vertical_alignment="bottom")
                    use = f1.toggle(T("ff_use", d=dn), key=f"ffuse|{j}", help=T("h_ff_use"))
                    g = num(T("ff_gain", d=dn), f"ffg|{j}|{g0:.5g}", g0, f2, format="%.5g", help=T("h_ff_gain"))
                    dyn = st.toggle(T("ff_dyn"), key=f"ffdyn|{j}", help=T("h_ff_dyn"))
                    ll = (0.0, 0.0, 0.0)
                    if dyn:
                        l1, l2, l3 = st.columns(3)
                        tld = num(T("ff_lead"), f"fftl|{j}|{tl0:.5g}", tl0, l1, min_value=0.0, format="%.4g",
                                  help=T("h_ff_lead"))
                        tlg = num(T("ff_lag"), f"fftg|{j}|{tg0:.5g}", tg0, l2, min_value=0.0, format="%.4g",
                                  help=T("h_ff_lag"))
                        tdl = num(T("ff_delay"), f"ffdl|{j}|{dl0:.5g}", dl0, l3, min_value=0.0, format="%.4g",
                                  help=T("h_ff_delay"))
                        ll = (tld, max(tlg, tld / 20, 1e-6), tdl)
                    ff.append(g if use else 0.0)
                    ffll.append(ll)
                    if use and pdl[j][2] < p[-1]:
                        st.caption(T("ff_faster", d=dn, td=f"{pdl[j][2]:.3g}", t=f"{p[-1]:.3g}"))
                    if j < len(c_d) - 1:
                        st.divider()
                st.caption(T("ff_help"))

        new_ctrl = dict(base_ctrl, Gain=new_gain, TI=new_ti if new_ti > 0 else np.inf, TD=new_td, FF=ff, FF_LL=ffll)
        ss.new_ctrl = new_ctrl
        ss.ff_state = [dict(use=bool(ss.get(f"ffuse|{j}")), gain=float(ff[j]) if ff[j] else float(ff_gain(mcode, p, pdl[j])),
                            dyn=bool(ss.get(f"ffdyn|{j}")), lead=ffll[j][0], lag=ffll[j][1], delay=ffll[j][2])
                       for j in range(len(ff))]

        rc, rn = robustness(mcode, p, cur_ctrl), robustness(mcode, p, new_ctrl)
        PROG["tune"] = 2 if not rn["stable"] else (0 if rn["Ms"] <= 2.0 else 1)
        st.markdown(f"#### {T('compare_title')}")
        cA, cB = st.columns([1, 1.6], gap="large")
        with cA:
            tbl = pd.DataFrame({
                T("current"): [fmt(cur_gain), fmt(cur_ctrl["TI"]), fmt(cur_td), fmt(rc["Ms"], 3), fmt(rc["GM"], 3),
                               fmt(rc["PM"], 3), fmt(mv_noise(cur_ctrl, sigma_pv) * MR / 100, 3)],
                T("new"): [fmt(new_gain), fmt(new_ctrl["TI"]), fmt(new_td), fmt(rn["Ms"], 3), fmt(rn["GM"], 3),
                           fmt(rn["PM"], 3), fmt(mv_noise(new_ctrl, sigma_pv) * MR / 100, 3)]},
                index=["Gain", "TI [s]", "TD [s]", T("ms"), T("gm"), T("pm"), T("noise_col", u=u_mv or "MV")])
            if unc_models:
                worst = lambda c_: max(robustness(mcode, q, c_)["Ms"] for q in unc_models)
                tbl.loc[T("ms_worst")] = [fmt(worst(cur_ctrl), 3), fmt(worst(new_ctrl), 3)]
            st.dataframe(tbl, width="stretch")
            REPORT["tables"].append((T("rep_tab_tuning"), tbl))
            for nm, r in ((T("current"), rc), (T("new"), rn)):
                if not r["stable"]:
                    st.error(T("err_unstable", n=nm), icon=":material/error:")
            st.caption(T("robust_help"))
        with cB:
            with st.container(border=True):
                scen_opts = ["custom"] + (["replay"] if dists else [])
                scen = seg(st, T("scenario"), scen_opts, "custom", "scen2",
                           format_func=lambda x: T("scen_" + x), help=T("h_scenario")) or "custom"
                T_char = p[-1] + (p[1] if mcode in ("P1D", "P2D", "I1D") else 0) + (tc or 0) + samp
                if scen == "custom":
                    T_end = num(T("sim_len"), f"tend|{mcode}", round(max(20 * T_char, 50 * samp), 0), min_value=samp * 10,
                                help=T("h_sim_len"))
                else:
                    T_end = float(ts_id[-1])
                    st.caption(T("replay_help"))
                s1_, s2_ = st.columns(2)
                robust_on = s1_.toggle(T("robust_on"), key="robust_on", help=T("h_robust_on"))
                spread_on = s2_.toggle(T("spread_on"), key="spread_on", help=T("h_spread_on"),
                                       disabled=not unc_models) and bool(unc_models)

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
                    rows_ = [[True, "SP", "step", round(0.05 * PR, 4), round(0.05 * T_end), None, None, None],
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
        pv0 = float(np.nanmedian(sp[sel])) if has_sp else float(pv_id[0])
        mv0 = float(mv_id[0])
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
                    sig_ = _lag_ui(sig_, tau, h)
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

        sims = {T("current"): (run(cur_ctrl), C_CUR, "dot"), T("new"): (run(new_ctrl), C_NEW, None)}
        if robust_on:
            pp = list(p)
            pp[0] *= 1.3
            pp[-1] *= 1.5
            sims[T("new_err")] = (run(new_ctrl, pp), C_NEW, "dash")

        has_d = any(np.any(d != 0) for d in dmeas) or np.any(dmv_arr != 0) or np.any(dpv_arr != 0)
        nr = 3 if has_d else 2
        fig = mkfig(nr, [0.55, 0.25, 0.2] if nr == 3 else [0.62, 0.38])
        if spread_on:
            for i_, q in enumerate(unc_models[:10]):
                rq = run(new_ctrl, list(q))
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
                    fig.add_trace(tr(ts_sim, d, str(nm), C_DIST[i % 4], 1.4), 3, 1)
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
               "Gain": new_gain, "TI": new_ti, "TD": new_td, "DiffGain": diffgain,
               "Ms": rn["Ms"], "GM": rn["GM"], "PM": rn["PM"],
               "Gain_old": cur_gain, "TI_old": cur_ti, "TD_old": cur_td}
        for j, dn in enumerate(c_d):
            out.update({f"{n_}_{dn}": v for n_, v in zip(DIST_PARAMS, pdl[j])})
            out[f"FF_{dn}"] = ff[j] if ff else 0.0
        st.download_button(T("download"), pd.DataFrame([out]).to_csv(index=False, sep=";", decimal=","),
                           "pidconl_tuning.csv", "text/csv", icon=":material/download:")

# ================================================================ 4) OVĚŘENÍ
with tab4:
    st.caption(BLOCK_SUMMARY)
    if model is None:
        st.info(T("need_model"), icon=":material/arrow_back:")
    else:
        mcode, p, pdl = model
        with st.container(border=True):
            st.markdown(T("val_intro"))
            vkey = f"rng_val|{fname}|{t[-1]:.0f}"
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
        elif mode == "pred":
            yv, fv = predict(mcode, p, pdl, tv, pv[sv], mv[sv], [d[sv] for d in dists], Ts)
            st.metric(T("fit_pred"), f"{fv:.1f} %")
            REPORT["val"] = T("rep_val_pred", f=f"{fv:.1f}")
            ov_ = max(0.0, min(rv[1], rng[1]) - max(rv[0], rng[0])) / max(rv[1] - rv[0], 1e-9)
            PROG["val"] = 1 if ov_ > 0.5 else (0 if fv >= 70 else 2)
            PROG["val_same"] = ov_ > 0.5
            show(data_fig(tv, sv, [(f"{mcode} {T('prediction')}", yv, C_MODEL[mcode], None)]),
                 key="chart_val_pred", fname="validation", report=T("rep_fig_val"))
        elif not has_sp:
            st.warning(T("need_sp"))
        else:
            which = seg(st, T("val_params"), ["cur", "new"], "cur", "val_which",
                                         format_func=lambda x: T("val_" + x), help=T("h_val_which")) or "cur"
            ctrl = cur_ctrl if which == "cur" else ss.get("new_ctrl", cur_ctrl)
            h = min(Ts, samp)
            n = int(tv[-1] / h) + 1
            tg = np.arange(n) * h
            spg = np.interp(tg, tv, sp[sv])
            dg = [np.interp(tg, tv, d[sv] - d[sv][0]) for d in dists]
            tt, S, Pv, Mv = pidconl_sim(mcode, p, pdl, h, spg, float(pv[sv][0]), float(mv[sv][0]),
                                        dict(ctrl, **dict(plant, Noise=0.0)), dg)
            if not (np.all(np.isfinite(Pv)) and np.abs(Pv).max() < 1e5):
                st.error(T("err_sim_unstable", n=T("val_" + which)))
            else:
                if which == "cur":
                    pv_i, mv_i = np.interp(tv, tt, Pv), np.interp(tv, tt, Mv)
                    nf = lambda a, b: 100 * (1 - np.linalg.norm(a - b) / max(np.linalg.norm(a - a.mean()), 1e-12))
                    c1, c2 = st.columns(2)
                    c1.metric(T("fit_pv"), f"{nf(pv[sv], pv_i):.1f} %")
                    PROG["val"] = 0 if nf(pv[sv], pv_i) >= 60 else 2
                    c2.metric(T("fit_mv"), f"{nf(mv[sv], mv_i):.1f} %")
                    st.caption(T("val_cl_help"))
                col = C_NEW if which == "new" else C_CUR
                fig = mkfig(2, [0.62, 0.38])
                fig.add_trace(tr(tv, EP(sp[sv]), "SP", C_SP, 1.4, "dash"), 1, 1)
                fig.add_trace(tr(tv, EP(pv[sv]), T("measured"), C_PV, 1.3, group="meas"), 1, 1)
                fig.add_trace(tr(tt, EP(Pv), T("simulated"), col, 2.2, group="sim"), 1, 1)
                fig.add_trace(tr(tv, EM(mv[sv]), f"MV {T('measured')}", C_MV, 1.4, group="meas", show=False), 2, 1)
                fig.add_trace(tr(tt, EM(Mv), f"MV {T('simulated')}", col, 2.2, group="sim", show=False), 2, 1)
                show(style(fig, H, [lab_pv, lab_mv], lab_t, rev="val"), key="chart_val_cl", fname="validation_loop",
                     report=T("rep_fig_val"))

# ================================================================ 5) DIAGNOSTIKA
with tab5:
    st.caption(BLOCK_SUMMARY)
    integ_known = MODELS[model[0]]["integ"] if model is not None else None
    with st.container(border=True):
        st.markdown(T("diag_intro"))
        dkey = f"rng_diag|{fname}|{t[-1]:.0f}"
        if dkey not in ss:
            ss[dkey] = (0.0, float(t[-1]))
        c1, c2 = st.columns([3, 1.3], vertical_alignment="bottom")
        rd = c1.slider(T("seg_diag"), 0.0, float(t[-1]), step=float(max(Ts, t[-1] / 1000)), key=dkey, help=T("h_seg_diag"))
        integ_d = tog(c2, T("diag_integ"), bool(integ_known), "diag_integ", help=T("h_diag_integ"))
        th_d = model[1][-1] if model is not None else num(T("diag_theta"), "diag_theta", 5.0, c2, min_value=0.0,
                                                           help=T("h_diag_theta"))
    sd = (t >= rd[0]) & (t <= rd[1])

    def kpi_row(mask):
        k_ = loop_kpis(t[mask], sp[mask] if has_sp else pv[mask], pv[mask], mv[mask], Ts,
                       float(M(mvl_lo)), float(M(mvl_hi)), th_d + samp / 2, has_sp)
        return k_, {
            T("kpi_std", u=u_pv or "PV"): f"{k_['std_e'] * PR / 100:.4g}",
            T("kpi_iae_h", u=u_pv or "PV"): f"{k_['iae_h'] * PR / 100:.4g}",
            T("kpi_travel_h", u=u_mv or "MV"): f"{k_['travel_h'] * MR / 100:.4g}",
            T("kpi_rev_h"): f"{k_['rev_h']:.3g}",
            T("kpi_at_lim"): f"{k_['at_lim']:.1f} %",
            T("kpi_harris"): "—" if not np.isfinite(k_["harris"]) else f"{k_['harris']:.2f}",
            T("kpi_osc"): (T("yes_period", p=f"{k_['osc']['period']:.0f}") if k_["osc"]["osc"] else T("no")),
        }

    if sd.sum() < 100:
        st.warning(T("err_short"))
    else:
        # ---- výkon smyčky
        st.markdown(f"#### {T('perf_title')}")
        kA, rowA = kpi_row(sd)
        compare = st.toggle(T("perf_compare"), key="perf_compare", help=T("h_perf_compare"))
        if compare:
            bkey = f"rng_diagB|{fname}|{t[-1]:.0f}"
            if bkey not in ss:
                ss[bkey] = (float(t[-1]) / 2, float(t[-1]))
            rb2 = st.slider(T("seg_diag_b"), 0.0, float(t[-1]), step=float(max(Ts, t[-1] / 1000)), key=bkey)
            sB = (t >= rb2[0]) & (t <= rb2[1])
            if sB.sum() >= 100:
                kB, rowB = kpi_row(sB)
                ptab = pd.DataFrame({T("seg_a"): rowA, T("seg_b"): rowB})
            else:
                ptab = pd.DataFrame({T("seg_a"): rowA})
        else:
            ptab = pd.DataFrame({T("seg_a"): rowA})
        st.dataframe(ptab, width="stretch")
        REPORT["tables"].append((T("perf_title"), ptab))
        st.caption(T("perf_help"))

        # ---- oscilace a ventil
        st.markdown(f"#### {T('osc_title')}")
        sig = (sp[sd] - pv[sd]) if has_sp else pv[sd]
        osc = oscillation(sig, Ts)
        if not osc["osc"]:
            st.success(T("osc_none"), icon=":material/check_circle:")
        else:
            st.warning(T("osc_found", p=f"{osc['period']:.0f}", a=f"{osc['amp'] * PR / 100:.3g}", u=u_pv or "PV",
                         r=f"{osc['r']:.1f}"), icon=":material/waves:")
        sc = stiction_ccf(mv[sd], pv[sd], Ts, integ_d, osc["period"] if osc["osc"] else None)
        ratio = sc["ratio"]
        PROG["diag"] = 0 if not osc["osc"] else (2 if np.isfinite(ratio) and ratio < 0.35 else 1)
        if osc["osc"] and np.isfinite(ratio):
            if ratio < 0.35:
                st.error(T("stic_likely", r=f"{ratio:.2f}"), icon=":material/build:")
            elif ratio > 0.7:
                st.info(T("stic_unlikely", r=f"{ratio:.2f}"), icon=":material/tune:")
            else:
                st.info(T("stic_unclear", r=f"{ratio:.2f}"), icon=":material/help:")
            REPORT["notes"].append(T("rep_osc", p=f"{osc['period']:.0f}", r=f"{ratio:.2f}"))
        cc1, cc2 = st.columns(2)
        with cc1:
            fcc = go.Figure()
            fcc.add_trace(tr(sc["lags"], sc["ccf"], T("ccf"), C_PV, 2.0))
            fcc.add_vline(x=0, line=dict(color="#94a3b8", dash="dot", width=1))
            style(fcc, 300, xtitle=T("lag_s"), rev="ccf")
            fcc.update_layout(title=dict(text=T("ccf_title_d") if integ_d else T("ccf_title"), font=dict(size=13), x=0),
                              hovermode="x")
            show(fcc, key="chart_ccf", fname="ccf")
        with cc2:
            yy = np.gradient(pv[sd], Ts) if integ_d else pv[sd]
            fph = go.Figure(go.Scattergl(x=EM(mv[sd]), y=yy * PR / 100 if not integ_d else yy * PR / 100,
                                         mode="markers+lines", marker=dict(size=3, color=C_PV, opacity=0.5),
                                         line=dict(width=0.6, color="#cbd5e1"), name="MV–PV"))
            style(fph, 300, rev="phase")
            fph.update_layout(title=dict(text=T("phase_title"), font=dict(size=13), x=0), hovermode="closest",
                              xaxis_title=lab_mv, yaxis_title=("dPV/dt" if integ_d else lab_pv))
            show(fph, key="chart_phase", fname="mv_pv")
        st.caption(T("osc_help"))
        if pos_e is not None:
            hyst = valve_hysteresis(mv_e[sd], pos_e[sd])
            st.metric(T("hyst"), "—" if not np.isfinite(hyst) else f"{abs(hyst):.3g} {u_mv or ''}", help=T("h_hyst"))
            fpos = go.Figure(go.Scattergl(x=mv_e[sd], y=pos_e[sd], mode="markers+lines",
                                          marker=dict(size=3, color=C_MV, opacity=0.5),
                                          line=dict(width=0.6, color="#fecaca")))
            style(fpos, 300, rev="pos")
            fpos.update_layout(xaxis_title=lab_mv, yaxis_title=T("col_pos"), hovermode="closest",
                               title=dict(text=T("pos_title"), font=dict(size=13), x=0))
            show(fpos, key="chart_pos", fname="valve", report=T("pos_title"))
            if np.isfinite(hyst):
                REPORT["notes"].append(T("rep_hyst", h=f"{abs(hyst):.3g}", u=u_mv or ""))
        else:
            st.caption(T("pos_missing"))

        # ---- nelinearita
        st.markdown(f"#### {T('nl_title')}")
        if model is None:
            st.info(T("need_model"), icon=":material/arrow_back:")
        else:
            lg = local_gains(model[0], model[1], model[2], ts_id, pv_id, mv_id, d_id, Ts)
            if len(lg) < 2:
                st.info(T("nl_few"), icon=":material/info:")
            else:
                gl = pd.DataFrame([{T("nl_time"): f"{g['t']:.0f}", T("nl_from"): f"{EM(g['mv_from']):.4g}",
                                    T("nl_to"): f"{EM(g['mv_to']):.4g}", T("nl_dir"): "↑" if g["dmv"] > 0 else "↓",
                                    T("nl_gain"): f"{g['gain']:.4g}", T("nl_ratio"): f"{g['ratio']:.2f}"} for g in lg])
                n1_, n2_ = st.columns([1.2, 1])
                n1_.dataframe(gl, hide_index=True, width="stretch")
                gains = np.array([g["gain"] for g in lg])
                spread = np.max(np.abs(gains)) / max(np.min(np.abs(gains)), 1e-12)
                fnl = go.Figure()
                for dsign, col, nm in ((1, "#1f5fa8", "↑"), (-1, "#c2410c", "↓")):
                    xs = [EM((g["mv_from"] + g["mv_to"]) / 2) for g in lg if np.sign(g["dmv"]) == dsign]
                    ys = [g["gain"] for g in lg if np.sign(g["dmv"]) == dsign]
                    fnl.add_trace(go.Scatter(x=xs, y=ys, mode="markers", name=nm, marker=dict(size=11, color=col)))
                fnl.add_hline(y=model[1][0], line=dict(color="#94a3b8", dash="dot"))
                style(fnl, 300, rev="nl")
                fnl.update_layout(xaxis_title=lab_mv, yaxis_title=MODELS[model[0]]["params"][0], hovermode="closest")
                with n2_:
                    show(fnl, key="chart_nl", fname="nonlinearity", report=T("nl_title"))
                ups = [g["gain"] for g in lg if g["dmv"] > 0]
                dns = [g["gain"] for g in lg if g["dmv"] < 0]
                if spread > 1.5:
                    PROG["diag"] = max(PROG.get("diag", 0), 1)
                    st.warning(T("nl_warn", s=f"{spread:.1f}"), icon=":material/show_chart:")
                else:
                    st.success(T("nl_ok", s=f"{spread:.2f}"), icon=":material/check_circle:")
                if ups and dns and abs(np.mean(ups) / np.mean(dns) - 1) > 0.3:
                    st.info(T("nl_dir_warn", r=f"{np.mean(ups) / np.mean(dns):.2f}"), icon=":material/swap_vert:")
                REPORT["notes"].append(T("rep_nl", s=f"{spread:.2f}"))
                st.caption(T("nl_help"))

# ================================================================ 6) PLÁN TESTU
with tab6:
    with st.container(border=True):
        st.markdown(T("plan_intro"))
        src_m = seg(st, T("plan_src"), ["fit", "manual"], "fit" if model is not None else "manual", "plan_src", format_func=lambda x: T("plan_src_" + x), help=T("h_plan_src"))
        src_m = src_m or ("fit" if model is not None else "manual")
        if src_m == "fit" and model is None:
            st.info(T("need_model"))
            src_m = "manual"
        if src_m == "manual":
            q1, q2, q3, q4 = st.columns(4)
            pc = q1.selectbox(T("plan_type"), ["P1D", "P2D", "I1D"], key="plan_type", format_func=model_name)
            k_ = num("K / Ki", "plan_k", 1.0, q2, format="%.4g", help=T("h_plan_k"))
            T1_ = num("T1 [s]", "plan_t1", 60.0, q3, min_value=0.0, help=T("help_T"))
            th_ = num("θ [s]", "plan_th", 10.0, q4, min_value=0.0, help=T("help_theta"))
            pp_ = [k_, max(T1_, 1e-3), th_] if pc != "P2D" else [k_, max(T1_, 1e-3), max(T1_ / 4, 1e-3), th_]
            plan_model = (pc, pp_)
        else:
            plan_model = (model[0], model[1])
        w1, w2, w3, w4 = st.columns(4)
        dpvm = num(T("plan_dpv", u=u_pv or "PV"), "plan_dpv", round(0.05 * PR, 4), w1, min_value=1e-9,
                   help=T("h_plan_dpv"))
        sig0 = sigma_pv * PR / 100 if sigma_pv > 0 else 0.002 * PR
        sig_e = num(T("plan_sigma", u=u_pv or "PV"), f"plan_sigma|{sig0:.4g}", sig0, w2, min_value=0.0, format="%.4g",
                    help=T("h_plan_sigma"))
        snr = num(T("plan_snr"), "plan_snr", 10.0, w3, min_value=1.0, help=T("h_plan_snr"))
        mv_now = num(T("plan_mv0", u=u_mv or "MV"), "plan_mv0", float(np.round(mv_e[-1], 3)), w4, help=T("h_plan_mv0"))
    if plan_model[0] == "P0D":
        plan_model = ("P1D", [plan_model[1][0], 1e-3, plan_model[1][-1]])
    room = (float(M(mvl_lo) - M(mv_now)), float(M(mvl_hi) - M(mv_now)))
    plan = step_plan(plan_model[0], plan_model[1], sig_e / PR * 100, dpvm / PR * 100, room, snr)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric(T("plan_step", u=u_mv or "MV"), f"{plan['dmv'] * MR / 100:.3g}")
    m2.metric(T("plan_hold"), f"{plan['hold']:.0f} s")
    m3.metric(T("plan_total"), f"{plan['total'] / 60:.0f} min")
    m4.metric(T("plan_snr_ach"), f"{plan['snr']:.0f}")
    if not plan["feasible"]:
        st.error(T("plan_infeasible"), icon=":material/error:")
    elif plan["snr"] < snr:
        st.warning(T("plan_low_snr"), icon=":material/warning:")
    if room[0] > -plan["dmv"] or room[1] < plan["dmv"]:
        st.warning(T("plan_room"), icon=":material/warning:")
    fpl = mkfig(2, [0.6, 0.4])
    pv_ref = float(pv_e[-1])
    fpl.add_trace(tr(plan["t"], pv_ref + plan["y"] * PR / 100, T("plan_pv"), C_PV, 2.0), 1, 1)
    for sgn in (1, -1):
        fpl.add_hline(y=pv_ref + sgn * dpvm, line=dict(color="#dc2626", dash="dot", width=1), row=1, col=1)
        fpl.add_hrect(y0=pv_ref - snr * sig_e * 0 - sig_e, y1=pv_ref + sig_e, fillcolor="#cbd5e1", opacity=0.3,
                      line_width=0, row=1, col=1) if sgn == 1 else None
    fpl.add_trace(tr(plan["t"], mv_now + plan["u"] * MR / 100, "MV", C_MV, 2.0, shape="hv"), 2, 1)
    show(style(fpl, H, [lab_pv, lab_mv], lab_t, rev="plan"), key="chart_plan", fname="step_test_plan",
         report=T("plan_title"))
    seq, t0_ = [], 0.0
    ch = np.r_[0, np.where(np.diff(plan["u"]) != 0)[0] + 1]
    for i_ in ch:
        seq.append({T("plan_at"): f"{plan['t'][i_] / 60:.1f} min", T("plan_set", u=u_mv or "MV"): f"{mv_now + plan['u'][i_] * MR / 100:.4g}"})
    stab = pd.DataFrame(seq)
    c1, c2 = st.columns([1, 2])
    c1.dataframe(stab, hide_index=True, width="stretch")
    c1.download_button(T("plan_dl"), stab.to_csv(index=False, sep=";"), "step_test_plan.csv", "text/csv",
                       icon=":material/download:")
    c2.markdown(T("plan_tips_integ") if plan["integ"] else T("plan_tips_self"))
    REPORT["tables"].append((T("plan_title"), stab))

# ================================================================ 7) KASKÁDA
with tab7:
    st.caption(BLOCK_SUMMARY)
    st.markdown(T("cas_intro"))
    if model is None:
        st.info(T("need_model"), icon=":material/arrow_back:")
    else:
        with st.container(border=True):
            st.markdown(f"**{T('cas_inner')}**")
            isrc = seg(st, T("cas_src"), ["data", "manual"], "manual", "cas_src",
                                        format_func=lambda x: T("cas_src_" + x), help=T("h_cas_src")) or "manual"
            inner = None
            if isrc == "data":
                i1, i2, i3, i4 = st.columns(4)
                c_ipv = i1.selectbox(T("cas_ipv"), sigs, key=f"cas_ipv|{fname}", help=T("h_cas_ipv"))
                c_imv = i2.selectbox(T("cas_imv"), sigs, key=f"cas_imv|{fname}", help=T("h_cas_imv"))
                ipv_raw = on_grid(c_ipv)
                ilo = num(T("cas_ilo"), f"cas_ilo|{c_ipv}", float(np.floor(np.nanmin(ipv_raw))), i3, help=T("h_cas_irange"))
                ihi = num(T("cas_ihi"), f"cas_ihi|{c_ipv}", float(np.ceil(np.nanmax(ipv_raw))), i4, help=T("h_cas_irange"))
                if st.button(T("cas_fit"), icon=":material/play_arrow:"):
                    ipv = (ipv_raw[sel] - ilo) / max(ihi - ilo, 1e-9) * 100
                    imv = M(on_grid(c_imv, zoh=True)[sel])
                    k = int(np.ceil(len(ts_id) / 2500))
                    best_i = None
                    for cc_ in ("P1D", "P2D"):
                        try:
                            r_ = fit_model(cc_, ts_id[::k], ipv[::k], imv[::k], Ts * k)
                            r_["fit"] = predict(cc_, r_["p"], [], ts_id, ipv, imv, [], Ts)[1]
                            if best_i is None or r_["fit"] > best_i["fit"] + 0.5:
                                best_i = r_
                        except Exception as ex:
                            st.error(T(str(ex)))
                    if best_i:
                        ss.inner_fit = best_i
                if ss.get("inner_fit"):
                    inner = (ss.inner_fit["code"], ss.inner_fit["p"])
                    st.caption(T("cas_inner_fit", m=model_name(inner[0]), f=f"{ss.inner_fit['fit']:.1f}",
                                 p=", ".join(f"{n} = {v:.4g}" for n, v in zip(MODELS[inner[0]]["params"], inner[1]))))
            else:
                i1, i2, i3, i4 = st.columns(4)
                k_i = num("K", "cas_k", 1.0, i1, format="%.4g", help=T("h_cas_k"))
                t1_i = num("T1 [s]", "cas_t1", 5.0, i2, min_value=1e-3, help=T("help_T"))
                t2_i = num("T2 [s]", "cas_t2", 0.0, i3, min_value=0.0, help=T("help_T"))
                th_i = num("θ [s]", "cas_th", 1.0, i4, min_value=0.0, help=T("help_theta"))
                inner = ("P2D", [k_i, max(t1_i, t2_i), max(min(t1_i, t2_i), 1e-3), th_i]) if t2_i > 0 else \
                    ("P1D", [k_i, t1_i, th_i])
        if inner is None:
            st.info(T("cas_need_inner"))
        else:
            ci_, p_i = inner
            with st.container(border=True):
                st.markdown(f"**{T('cas_inner_tune')}**")
                j1, j2, j3 = st.columns([1.3, 1, 2])
                im = seg(j1, T("method"), ["SIMC", "AMIGO", "OPT"], "SIMC", "cas_im",
                                          format_func=lambda x: T("m_" + x)) or "SIMC"
                samp_i = num(T("cas_samp"), "cas_samp", samp, j2, min_value=0.001, help=T("sampletime_help"))
                if im == "SIMC":
                    tci0 = default_tc(ci_, p_i, samp_i)
                    tci = sld(j3, T("tc"), float(max(0.05 * tci0, 1e-3)), float(10 * tci0), float(tci0), "cas_tci",
                              help=T("tc_help"))
                    si = tune(ci_, p_i, "SIMC", tci, "PI", samp_i)
                elif im == "AMIGO":
                    si = tune(ci_, p_i, "AMIGO", None, "PI", samp_i)
                else:
                    r0 = tune(ci_, p_i, "SIMC", default_tc(ci_, p_i, samp_i), "PI", samp_i)
                    si = opt_cached(ci_, tuple(p_i), "PI", samp_i, diffgain, 1.6, None, ((r0["Kc"], r0["Ti"], 0.0),))
                st.caption(T("mdesc_" + im) + (f" {T('cdesc_MIGO')}" if im == "OPT" else ""))
                ictrl = dict(Gain=si["Kc"], TI=si["Ti"], TD=0.0, DiffGain=diffgain, SampleTime=samp_i, MV_Lo=0.0,
                             MV_Hi=100.0, PropFbk=False, DiffFbk=True)
                # efektivní časová konstanta uzavřené vnitřní smyčky ze simulace skoku SP
                Tsim = 30 * (p_i[-1] + sum(p_i[1:-1]) + samp_i)
                hi_ = samp_i / max(1, min(10, int(6000 * samp_i / Tsim)))
                ni_ = int(Tsim / hi_) + 1
                spi_ = np.ones(ni_)
                spi_[0] = 0
                tt_i, _, P_i, _ = pidconl_sim(ci_, p_i, [], hi_, spi_, 0.0, 50.0, ictrl)
                k63 = np.argmax(P_i >= 0.632) if np.any(P_i >= 0.632) else len(P_i) - 1
                tci_eff = max(tt_i[k63] - p_i[-1], hi_)
                k1, k2, k3 = st.columns(3)
                k1.metric("Gain", f"{si['Kc']:.4g}")
                k2.metric("TI [s]", f"{si['Ti']:.4g}")
                k3.metric(T("cas_t63"), f"{tt_i[k63]:.3g} s", help=T("h_cas_t63"))
            with st.container(border=True):
                st.markdown(f"**{T('cas_outer_tune')}**")
                co_, p_o = outer_with_inner(model[0], model[1], tci_eff, p_i[-1])
                st.caption(T("cas_outer_model", m=model_name(co_),
                             p=", ".join(f"{n} = {v:.4g}" for n, v in zip(MODELS[co_]["params"], p_o))))
                l1, l2, l3 = st.columns([1.3, 0.8, 2])
                om = seg(l1, T("method"), ["SIMC", "AMIGO", "OPT"], "SIMC", "cas_om",
                                          format_func=lambda x: T("m_" + x)) or "SIMC"
                oct_ = seg(l2, T("ctrl_type"), ["PI", "PID"], "PI", "cas_oct") or "PI"
                tco = None
                if om == "SIMC":
                    tco0 = default_tc(co_, p_o, samp)
                    tco = sld(l3, T("tc"), float(max(0.05 * tco0, 1e-3)), float(10 * tco0), float(tco0), "cas_tco",
                              help=T("tc_help"))
                    so = tune(co_, p_o, "SIMC", tco, oct_, samp)
                elif om == "AMIGO":
                    so = tune(co_, p_o, "AMIGO", None, oct_, samp)
                else:
                    r0 = tune(co_, p_o, "SIMC", default_tc(co_, p_o, samp), oct_, samp)
                    so = opt_cached(co_, tuple(p_o), oct_, samp, diffgain, 1.6, None, ((r0["Kc"], r0["Ti"], r0["Td"]),))
                st.caption(T("mdesc_" + om) + (f" {T('cdesc_MIGO')}" if om == "OPT" else ""))
                octrl = dict(base_ctrl, Gain=so["Kc"], TI=so["Ti"], TD=so["Td"], MV_Lo=0.0, MV_Hi=100.0)
                o1, o2, o3, o4 = st.columns(4)
                o1.metric("Gain", f"{so['Kc']:.4g}")
                o2.metric("TI [s]", f"{so['Ti']:.4g}")
                o3.metric("TD [s]", f"{so['Td']:.4g}")
                ratio_sep = (tco or so["Ti"] / 4) / max(tt_i[k63], 1e-9)
                o4.metric(T("cas_sep"), f"{ratio_sep:.1f}×", help=T("h_cas_sep"))
                if ratio_sep < 4:
                    st.warning(T("cas_sep_warn"), icon=":material/warning:")
            # simulace kaskády
            Tc_sim = max(15 * (p_o[-1] + (p_o[1] if co_ in ("P1D", "P2D", "I1D") else 0) + (tco or 0)), 50 * samp)
            hc = min(samp, samp_i) / max(1, min(5, int(15000 * min(samp, samp_i) / Tc_sim)))
            nc = int(Tc_sim / hc) + 1
            tcs = np.arange(nc) * hc
            sp_o = np.full(nc, 50.0)
            sp_o[tcs >= 0.05 * Tc_sim] = 55.0
            d_i = np.where(tcs >= 0.4 * Tc_sim, 5.0, 0.0)
            d_o = np.where(tcs >= 0.7 * Tc_sim, 5.0, 0.0)
            tcs, oc = cascade_sim((ci_, p_i), ictrl, (model[0], model[1]), octrl, hc, sp_o, d_i, d_o)
            if np.all(np.isfinite(oc)) and np.abs(oc).max() < 1e5:
                fc = mkfig(3, [0.45, 0.3, 0.25])
                fc.add_trace(tr(tcs, EP(oc[:, 0]), "SP", C_SP, 1.4, "dash", "hv"), 1, 1)
                fc.add_trace(tr(tcs, EP(oc[:, 1]), T("cas_pv_o"), C_PV, 2.0), 1, 1)
                fc.add_trace(tr(tcs, oc[:, 2], T("cas_sp_i"), C_SP, 1.4, "dash"), 2, 1)
                fc.add_trace(tr(tcs, oc[:, 3], T("cas_pv_i"), C_NEW, 2.0), 2, 1)
                fc.add_trace(tr(tcs, oc[:, 4], T("cas_valve"), C_MV, 1.8), 3, 1)
                show(style(fc, H + 80, [lab_pv, T("cas_inner_pct"), T("cas_valve_pct")], lab_t, rev="cas"),
                     key="chart_cas", fname="cascade", report=T("tab7"))
                st.caption(T("cas_sim_help"))
            else:
                st.error(T("err_sim_unstable", n=T("tab7")))

# ================================================================ 8) PROJEKT A REPORT
STATE_KEYS = ["lang", "loop_tag", "u_pv", "u_mv", "pv_lo", "pv_hi", "mv_lo", "mv_hi", "samp", "diffgain", "pfb", "dfb", "db",
              "db_mode", "mvl_lo", "mvl_hi", "cur_gain", "cur_ti", "cur_td", "plot_h", "thmax", "chosen", "mcode", "ctype",
              "opt_ms", "opt_noise", "opt_robust", "avg_dpv", "avg_dmv", "scen", "sp_step", "dmv_step", "plan_dpv",
              "plan_snr", "cas_src", "cas_k", "cas_t1", "cas_t2", "cas_th", "cas_im", "cas_om", "cas_oct", "cas_samp",
              "cas_tci", "cas_tco", "diag_integ", "dist_level", "dist_strength", "gain_sign", "id_stic", "pvfilt",
              "mvrate", "sprate", "sim_J", "sim_noise", "scen2", "opt_crit", "opt_target", "opt_ovs", "vchar_last"]
STATE_PREFIX = ("ed|", "method|", "tc|", "tend|", "fx|", "sim_S|", "scen_df|")


def _jsonable(v):
    if isinstance(v, (np.floating, float)):
        return float(v)
    if isinstance(v, (np.integer, int, bool, str)) or v is None:
        return v.item() if isinstance(v, np.generic) else v
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    return None


def build_project(include_data):
    state = {}
    for k in list(ss.keys()):
        if k in STATE_KEYS or str(k).startswith(STATE_PREFIX):
            v = _jsonable(ss[k])
            if v is not None:
                state[k] = v
    proj = dict(version=1, created=_dt.datetime.now().isoformat(timespec="seconds"), tag=ss.get("loop_tag", ""),
                fname=fname, state=state,
                map={"c_pv": c_pv, "c_mv": c_mv, "c_sp": c_sp, "c_d": list(c_d), "c_pos": c_pos},
                ranges={"id": list(rng), "val": list(ss.get(f"rng_val|{fname}|{t[-1]:.0f}", rng))})
    if "fit" in ss and ss.fit.get("res"):
        proj["fit"] = dict(res={c: dict(code=c, p=[float(x) for x in r["p"]], pdl=[[float(x) for x in d] for d in r["pdl"]],
                                        fit=float(r["fit"])) for c, r in ss.fit["res"].items()},
                           dnames=list(ss.fit["dnames"]))
    if ss.get("new_ctrl"):
        nc_ = ss.new_ctrl
        proj["new"] = dict(Gain=float(nc_["Gain"]), TI=float(nc_["TI"]) if np.isfinite(nc_["TI"]) else 0.0,
                           TD=float(nc_["TD"]))
        proj["ff"] = ss.get("ff_state", [])
    if include_data:
        r6 = lambda a: [None if not np.isfinite(x) else float(f"{x:.6g}") for x in np.asarray(a, float)]
        cols_ = {"t_s": r6(t), str(c_pv): r6(pv_e), str(c_mv): r6(mv_e)}
        if has_sp:
            cols_[str(c_sp)] = r6(sp_e)
        for nm, d in zip(c_d, dists):
            cols_[str(nm)] = r6(d)
        if pos_e is not None:
            cols_[str(c_pos)] = r6(pos_e)
        proj["data"] = {"cols": cols_}
    return json.dumps(proj, ensure_ascii=False)


def build_report(author, comment):
    tag = ss.get("loop_tag", "") or "—"
    parts = [f"<h1>{T('rep_title')} – {tag}</h1>",
             f"<p class='meta'>{_dt.datetime.now():%Y-%m-%d %H:%M} · {T('rep_author')}: {author or '—'}</p>"]
    if comment:
        parts.append(f"<div class='note'>{comment}</div>")
    parts.append(f"<h2>{T('rep_sec_data')}</h2><ul>"
                 f"<li>{T('status', n=len(t), ts=f'{Ts:.3g}', dur=f'{t[-1]:.0f}', pvr=f'{pv_lo:g}–{pv_hi:g}', mvr=f'{mv_lo:g}–{mv_hi:g}')}</li>"
                 f"<li>PV: {c_pv} · MV: {c_mv} · SP: {c_sp} · {T('col_dist')}: {', '.join(map(str, c_d)) or '—'}</li>"
                 f"<li>{T('seg_id')}: {rng[0]:.0f}–{rng[1]:.0f} s</li>"
                 f"<li>SampleTime {samp:g} s · DiffGain {diffgain:g} · {T('pfb')}: {'✓' if pfb else '✗'} · "
                 f"{T('dfb')}: {'✓' if dfb else '✗'}</li></ul>")
    tu = REPORT.get("tuning")
    if tu:
        parts.append(f"<h2>{T('rep_sec_tuning')}</h2><ul><li>{T('model_for_tuning')}: {tu['model']} "
                     f"({', '.join(f'{k} = {v:.4g}' for k, v in tu['params'].items())})</li>"
                     f"<li>{T('method')}: {tu['method']} · {tu['ctype']}</li><li>{T('d_title')}: {tu['adv']}</li>"
                     + (f"<li>{tu['notes']}</li>" if tu["notes"] else "") + "</ul>")
    if REPORT.get("val"):
        parts.append(f"<p>{REPORT['val']}</p>")
    if REPORT["notes"]:
        parts.append(f"<h2>{T('rep_sec_diag')}</h2><ul>" + "".join(f"<li>{x}</li>" for x in REPORT["notes"]) + "</ul>")
    for title, tb in REPORT["tables"]:
        parts.append(f"<h2>{title}</h2>" + tb.to_html(classes="tbl", border=0, na_rep="—"))
    first = True
    for title, fg in REPORT["figs"]:
        f2 = go.Figure(fg)
        for tr_ in f2.data:  # zředění dlouhých průběhů kvůli velikosti souboru
            if tr_.x is not None and len(tr_.x) > 2500:
                k_ = int(np.ceil(len(tr_.x) / 2500))
                tr_.x, tr_.y = tr_.x[::k_], tr_.y[::k_]
        f2.update_layout(height=max(320, fg.layout.height or 420), width=None)
        parts.append(f"<h2>{title}</h2>" + f2.to_html(full_html=False, include_plotlyjs=True if first else False,
                                                    config={"displaylogo": False}))
        first = False
    css = ("body{font-family:Inter,'Segoe UI',Roboto,Arial,sans-serif;max-width:1100px;margin:32px auto;color:#1f2933;"
           "padding:0 20px}h1{font-weight:650}h2{margin-top:32px;border-bottom:1px solid #e2e8f0;padding-bottom:4px;"
           "font-size:1.15rem}.meta{color:#52606d}.note{background:#f4f7fb;border-left:4px solid #1f5fa8;padding:10px 14px}"
           "table.tbl{border-collapse:collapse;font-size:.9rem}table.tbl td,table.tbl th{border:1px solid #e2e8f0;"
           "padding:4px 10px;text-align:right}table.tbl th{background:#f4f7fb}@media print{h2{break-before:auto}}")
    return (f"<!doctype html><html lang='{ss.lang}'><head><meta charset='utf-8'><title>{T('rep_title')} {tag}</title>"
            f"<style>{css}</style></head><body>{''.join(parts)}</body></html>")


with tab8:
    c1, c2 = st.columns(2, gap="large")
    with c1:
        with st.container(border=True):
            st.markdown(f"#### {T('proj_title')}")
            st.caption(T("proj_save_help"))
            inc = tog(st, T("proj_include_data"), True, "proj_inc", help=T("h_proj_inc"))
            tagn = (ss.get("loop_tag") or "smycka").replace(" ", "_")
            if st.button(T("proj_build"), icon=":material/inventory_2:"):
                ss.proj_json = build_project(inc)
            if ss.get("proj_json"):
                st.download_button(T("proj_save"), ss.proj_json, f"{tagn}_pid_projekt.json", "application/json",
                                   icon=":material/save:", type="primary",
                                   on_click=lambda: ss.update(proj_saved=True))
    with c2:
        with st.container(border=True):
            st.markdown(f"#### {T('rep_title')}")
            st.caption(T("rep_help"))
            author = st.text_input(T("rep_author"), key="rep_author")
            comment = st.text_area(T("rep_comment"), key="rep_comment", height=100)
            if st.button(T("rep_build"), icon=":material/description:"):
                ss.report_html = build_report(author, comment)
            if ss.get("report_html"):
                st.download_button(T("rep_dl"), ss.report_html, f"{tagn}_report.html", "text/html",
                                   icon=":material/download:", type="primary",
                                   on_click=lambda: ss.update(proj_saved=True))

# ================================================================ ukazatel postupu (vykreslí se nahoru)
PROG["save"] = 0 if ss.get("proj_saved") else None
steps_ = [("data", "prog_data"), ("model", "prog_model"), ("val", "prog_val"), ("tune", "prog_tune"),
          ("diag", "prog_diag"), ("save", "prog_save")]
chips = []
for k_, lab_ in steps_:
    v_ = PROG.get(k_)
    cls_ = "sn" if v_ is None else f"s{v_}"
    ic_ = {None: "○", 0: "✓", 1: "⚠", 2: "✗"}[v_]
    chips.append(f"<span class='pid-chip {cls_}'>{ic_} {T(lab_)}</span>")
nxt = None
for k_, _ in steps_:
    v_ = PROG.get(k_)
    if v_ == 0:
        continue
    if k_ == "data":
        nxt = T("hint_data")
    elif k_ == "model":
        nxt = T("hint_model_none") if v_ is None else T("hint_model_stale") if PROG.get("model_stale") else T("hint_model_low")
    elif k_ == "val":
        nxt = T("hint_val_none") if v_ is None or PROG.get("val_same") else T("hint_val_bad")
    elif k_ == "tune":
        nxt = T("hint_model_none") if v_ is None else T("hint_tune_bad") if v_ == 2 else T("hint_tune")
    elif k_ == "diag":
        nxt = T("hint_diag") if v_ is not None else None
        if nxt is None:
            continue
    else:
        nxt = T("hint_save")
    break
prog_ph.markdown(f"<div class='pid-prog'>{'<span class=pid-arrow>›</span>'.join(chips)}</div>"
                 f"<div class='pid-next'>{T('hint_next')}: {nxt or T('hint_done')}</div>", unsafe_allow_html=True)
