"""
Prohlížeč záznamu (záložka Data) – komponenta static/viewer.js: všechny signály ze souboru v nepřevzorkované podobě,
panely pod sebou se společnou časovou osou, v panelu každý signál s vlastní osou Y, nezávislý zoom X / Y, kurzory
jako na osciloskopu (Δt, hodnoty, ΔY, min / max / průměr mezi kurzory), tabulka hodnot synchronní s grafem a export.

Data jdou do prohlížeče binárně (časy Float64, hodnoty Float32): velký záznam jako soubor přes media endpoint
Streamlitu (prohlížeč ho stáhne jednou – další běhy aplikace posílají jen adresu), malý přímo v datech komponenty.
Rozložení (panely, barvy, jednotky, měřítka, kurzory, výřez) posílá komponenta zpět jako text JSON → ss["dview"]
(ukládá se do projektu).
"""
import base64
import hashlib
import json

import numpy as np
import streamlit as st

from ..app.colors import C_DIST, C_MV, C_PV, C_SP
from ..i18n import T
from .widgets import static_asset, v2_component

ss = st.session_state
CAP = 6_000_000          # nejvýš hodnot všech signálů v prohlížeči (víc → min / max po skupinách)
INLINE_MAX = 1_500_000   # menší data (bajty) přímo v datech komponenty, větší přes media endpoint
LAYOUT_MAX = 65_536      # nejdelší uložené rozložení (znaky JSON)
OTHER = ["#2563eb", "#dc2626", "#059669", "#d97706", "#7c3aed", "#db2777", "#0891b2", "#65a30d", "#9333ea", "#ea580c",
         "#0f766e", "#b91c1c", "#4f46e5", "#a16207"]

_CSS = """
.pidv { position: relative; display: flex; flex-direction: column; gap: 10px; font-family: inherit; outline: none;
  color: var(--pv-text); --pv-text: #1f2933; --pv-muted: #52606d; --pv-line: #d7dde5; --pv-card: #ffffff;
  --pv-grid: #e8ecf1; --pv-axis: #c3ccd6; --pv-btn: #ffffff; --pv-hl: #eef4fb; --pv-acc: #1f5fa8; --pv-sel: #dbe8f7; }
.pidv.dark { --pv-text: #e2e8f0; --pv-muted: #94a3b8; --pv-line: #26324a; --pv-card: #111a2e; --pv-grid: #1c2740;
  --pv-axis: #334155; --pv-btn: #0f172a; --pv-hl: #16223a; --pv-acc: #60a5fa; --pv-sel: #1e3a5f; }
.pidv-card { background: var(--pv-card); border: 1px solid var(--pv-line); border-radius: 10px; }
.pidv-bar { display: flex; flex-wrap: wrap; gap: 8px 14px; align-items: center; padding: 8px 12px; }
.pidv-grp { display: inline-flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.pidv-lab { font-size: 12px; color: var(--pv-muted); }
.pidv-seg { display: inline-flex; border: 1px solid var(--pv-axis); border-radius: 8px; overflow: hidden; }
.pidv-seg button, .pidv-btn { font: inherit; font-size: 12px; padding: 4px 9px; border: 0; background: var(--pv-btn);
  color: var(--pv-text); cursor: pointer; white-space: nowrap; }
.pidv-btn { border: 1px solid var(--pv-axis); border-radius: 8px; }
.pidv-seg button + button { border-left: 1px solid var(--pv-axis); }
.pidv-seg button.on, .pidv-btn.on { background: var(--pv-acc); color: #fff; }
.pidv-btn:disabled, .pidv-seg button:disabled { opacity: .45; cursor: default; }
.pidv-help { width: 20px; height: 20px; border-radius: 50%; border: 1px solid #9aa5b1; color: var(--pv-muted);
  font-size: 11px; font-weight: 600; display: inline-flex; align-items: center; justify-content: center; cursor: help; }
.pidv-body { display: grid; grid-template-columns: 250px minmax(0, 1fr); gap: 10px; align-items: start; }
.pidv-body.nolist { grid-template-columns: minmax(0, 1fr); }
@media (max-width: 760px) { .pidv-body { grid-template-columns: minmax(0, 1fr); } }
.pidv-list { padding: 8px; display: flex; flex-direction: column; gap: 4px; max-height: 760px; overflow: auto; }
.pidv-list input[type=search] { font: inherit; font-size: 12px; padding: 4px 8px; border: 1px solid var(--pv-axis);
  border-radius: 6px; background: var(--pv-btn); color: var(--pv-text); width: 100%; box-sizing: border-box; }
.pidv-sig { display: grid; grid-template-columns: 16px 14px minmax(0, 1fr) auto auto; gap: 6px; align-items: center;
  font-size: 12px; padding: 3px 4px; border-radius: 6px; }
.pidv-sig:hover { background: var(--pv-hl); }
.pidv-sig.act { background: var(--pv-sel); }
.pidv-sig .nm { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; cursor: pointer; }
.pidv-sig .role { font-size: 10px; color: var(--pv-muted); margin-left: 4px; }
.pidv-dot { width: 12px; height: 12px; border-radius: 3px; border: 0; padding: 0; cursor: pointer; }
.pidv-sig select, .pidv-more input, .pidv-more select { font: inherit; font-size: 11px; padding: 1px 2px; border: 1px solid var(--pv-axis);
  border-radius: 4px; background: var(--pv-btn); color: var(--pv-text); }
.pidv-x { font: inherit; font-size: 11px; border: 0; background: none; color: var(--pv-muted); cursor: pointer; padding: 0 2px; }
.pidv-more { grid-column: 1 / -1; display: grid; grid-template-columns: auto 1fr; gap: 4px 8px; align-items: center;
  padding: 4px 6px 6px 36px; font-size: 11px; color: var(--pv-muted); }
.pidv-more input { width: 100%; box-sizing: border-box; }
.pidv-more .row { display: flex; gap: 6px; align-items: center; }
.pidv-plots { display: flex; flex-direction: column; gap: 0; min-width: 0; }
.pidv-panel { position: relative; padding: 6px 10px 0 6px; margin-bottom: 8px; }
.pidv-ph { display: flex; flex-wrap: wrap; gap: 4px 12px; align-items: center; font-size: 12px; margin: 0 0 4px 4px; min-height: 20px; }
.pidv-chip { display: inline-flex; align-items: center; gap: 5px; font-weight: 600; cursor: pointer; }
.pidv-chip i { display: inline-block; width: 14px; height: 0; border-top: 2px solid; }
.pidv-chip.act { text-decoration: underline; }
.pidv-ph .sp { flex: 1; }
.pidv-cv { display: block; touch-action: none; }
.pidv-rs { height: 7px; cursor: ns-resize; margin: 0 -10px 0 -6px; border-radius: 0 0 10px 10px; }
.pidv-rs:hover { background: var(--pv-hl); }
.pidv-xcard { padding: 0 10px 6px 6px; position: sticky; bottom: 0; z-index: 3; box-shadow: 0 -2px 6px rgba(0,0,0,.06); }
.pidv-bar { position: sticky; top: 0; z-index: 4; }
.pidv-xax { display: block; }
.pidv-nav { display: block; cursor: grab; touch-action: none; margin-top: 2px; }
.pidv-tip { position: absolute; display: none; pointer-events: none; z-index: 5; font-family: 'IBM Plex Mono', monospace;
  font-size: 11px; padding: 5px 8px; border-radius: 6px; border: 1px solid var(--pv-line); background: var(--pv-card);
  box-shadow: 0 2px 8px rgba(0,0,0,.14); white-space: nowrap; color: var(--pv-text); line-height: 1.45; }
.pidv-tip b { font-weight: 600; }
.pidv-read { padding: 8px 10px; overflow-x: auto; }
.pidv-tbl { border-collapse: collapse; font-size: 12px; width: 100%; }
.pidv-tbl th, .pidv-tbl td { padding: 3px 8px; text-align: right; white-space: nowrap; border-bottom: 1px solid var(--pv-grid);
  font-family: 'IBM Plex Mono', monospace; font-variant-numeric: tabular-nums; }
.pidv-tbl th { font-family: inherit; font-weight: 600; color: var(--pv-muted); position: sticky; top: 0; background: var(--pv-card); z-index: 1; }
.pidv-tbl td:first-child, .pidv-tbl th:first-child { text-align: left; font-family: inherit; }
.pidv-tbl tr.sel td { background: var(--pv-sel); }
.pidv-tbl tbody tr { cursor: pointer; }
.pidv-tbl tbody tr:hover td { background: var(--pv-hl); }
.pidv-rhead { display: flex; flex-wrap: wrap; gap: 4px 18px; align-items: baseline; font-size: 12px; margin-bottom: 6px; }
.pidv-rhead b { font-family: 'IBM Plex Mono', monospace; font-weight: 600; }
.pidv-dtab { position: relative; overflow: auto; height: 280px; }
.pidv-note { font-size: 11px; color: var(--pv-muted); }
.pidv-err { padding: 14px; color: #b91c1c; font-size: 13px; }
.pidv-an { padding: 8px 12px; }
.pidv-antabs { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
.pidv-antabs .sp { flex: 1; }
.pidv-tabb { font: inherit; font-size: 12px; padding: 4px 10px; border: 1px solid var(--pv-axis); border-radius: 999px;
  background: var(--pv-btn); color: var(--pv-text); cursor: pointer; }
.pidv-tabb.on { background: var(--pv-acc); border-color: var(--pv-acc); color: #fff; }
.pidv-anbody { margin-top: 10px; display: flex; flex-direction: column; gap: 8px; }
.pidv-row { display: flex; flex-wrap: wrap; gap: 6px 12px; align-items: center; font-size: 12px; }
.pidv-row select, .pidv-row input:not([type=checkbox]) { font: inherit; font-size: 12px; padding: 2px 4px; border: 1px solid var(--pv-axis);
  border-radius: 4px; background: var(--pv-btn); color: var(--pv-text); max-width: 220px; }
.pidv-chk { display: inline-flex; align-items: center; gap: 5px; font-size: 12px; cursor: pointer; }
.pidv-chk i { display: inline-block; width: 10px; height: 10px; border-radius: 2px; }
.pidv-mini { display: block; }
.pidv-kv { width: auto; }
.pidv-kv td:first-child { color: var(--pv-muted); padding-right: 18px; }
.pidv-kv td { text-align: left !important; }
.pidv-bar2 { display: inline-block; height: 8px; border-radius: 2px; vertical-align: middle; }
.pidv-segchip { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; padding: 2px 6px; border: 1px solid var(--pv-axis);
  border-radius: 6px; font-family: 'IBM Plex Mono', monospace; }
.pidv-segchip i { display: inline-block; width: 12px; height: 3px; }
.pidv-add { font: inherit; font-size: 12px; margin-top: 6px; padding: 4px 8px; border: 1px dashed var(--pv-axis); background: var(--pv-btn);
  color: var(--pv-muted); border-radius: 6px; cursor: pointer; width: 100%; }
.pidv-calc { display: flex; flex-direction: column; gap: 4px; padding: 6px; margin: 2px 0 6px; border: 1px solid var(--pv-axis); border-radius: 6px; }
.pidv-calc input, .pidv-calc textarea { font: inherit; font-size: 12px; padding: 3px 6px; border: 1px solid var(--pv-axis); border-radius: 4px;
  background: var(--pv-btn); color: var(--pv-text); }
.pidv-calc textarea { font-family: 'IBM Plex Mono', monospace; resize: vertical; }
.pidv-calc .row { display: flex; gap: 6px; flex-wrap: wrap; }
.pidv-tbl.pidv-left td, .pidv-tbl.pidv-left th { text-align: left; }
.pidv-cerr { font-size: 11px; color: #b91c1c; padding: 0 4px; }
"""

TXT = ("pan", "zoom_box", "zoom_x", "zoom_y", "back", "fwd", "full", "cur", "hcur", "yauto", "ya_view", "ya_all",
       "table", "csv_view", "csv_cur", "list", "search", "panel", "new_panel", "unit", "ymin", "ymax", "auto",
       "shared", "up", "down", "remove", "help", "drag", "loading", "load_err", "retry", "signal", "mean", "min",
       "max", "slope", "rows", "rows_more", "nearest", "step", "line", "interp", "decim", "time", "no_sig",
       "color", "more", "reset", "hide", "c_hint", "h_hint", "ylock", "close",
       # analýza a vypočtené signály
       "an", "an_ev", "an_step", "an_corr", "an_xy", "an_cmp", "ev_prev", "ev_next", "ev_mv", "ev_sp", "ev_dv", "ev_state",
       "ev_sat", "ev_flat", "ev_gap", "ev_hint", "ev_none", "ev_kind", "ev_detail", "st_in", "st_out", "st_find", "st_hint",
       "st_need_cur", "st_few", "st_no_step", "st_c1_late", "st_c2_early", "st_du", "st_dy", "st_k", "st_ki", "st_th",
       "st_t", "st_tr", "st_ovs", "st_set", "st_noset", "st_integ", "st_model", "cor_target", "cor_incr", "cor_incr_h", "cor_int", "cor_int_h", "cor_vals_h", "cor_auto", "cor_auto_h", "cor_used",
       "cor_vals", "cor_lag", "cor_run", "cor_hint", "cor_lagc", "cor_mean", "cor_weak", "cor_leads", "cor_lags", "cor_same",
       "rng_cur", "rng_view", "xy_line", "xy_hint", "xy_fit", "xy_time", "cmp_sigs", "cmp_add_view", "cmp_add_cur",
       "cmp_rel", "cmp_go", "cmp_hint", "calc_add", "calc_name", "calc_ph", "calc_help", "calc_save", "calc_cancel",
       "calc_del", "calc_badname", "e_pos", "e_empty", "e_too_long", "e_bad_number", "e_unclosed", "e_bad_char",
       "e_expected", "e_unknown_sig", "e_unknown_fn", "e_bad_args", "e_unexpected", "e_unexpected_end", "e_need_number",
       "e_empty_res")


def _blob_key(vkey):
    return hashlib.md5(json.dumps([str(x) for x in vkey]).encode()).hexdigest()[:16]


@st.cache_data(max_entries=2, show_spinner=False)
def _payload(key, names, _t_all, _get):
    """
    Binární data prohlížeče: [časy Float64…][hodnoty Float32…] + popis signálů {name, ti, off, n}, časů {off, n}.
    Signál bez platných vzorků se vynechá; stejné časy (široký formát) se sdílejí.
    """
    t = np.asarray(_t_all, float)
    ok_t = np.isfinite(t)
    order = np.argsort(np.where(ok_t, t, np.inf), kind="stable")
    t = t[order]
    tmin = float(t[np.isfinite(t)][0]) if np.isfinite(t).any() else 0.0
    vals = []
    for nm in names:
        try:
            v = np.asarray(_get(nm), float)[order]
        except Exception:
            continue
        m = np.isfinite(v) & np.isfinite(t)
        if m.sum() >= 2:
            vals.append((nm, v, m))
    total = sum(int(m.sum()) for _, _, m in vals)
    g = int(np.ceil(total / CAP)) if total > CAP else 1
    times, tkeys, sigs, vparts = [], {}, [], []
    for nm, v, m in vals:
        tt, vv = t[m] - tmin, v[m]
        if g > 1:                                  # min / max po skupinách g vzorků (tvar a špičky zůstanou)
            idx = _minmax_idx(vv, 2 * g)
            tt, vv = tt[idx], vv[idx]
            key_t = None
        else:
            key_t = hashlib.md5(np.packbits(m).tobytes()).hexdigest()
        if key_t is not None and key_t in tkeys:
            ti = tkeys[key_t]
        else:
            ti = len(times)
            times.append(tt.astype(np.float64))
            if key_t is not None:
                tkeys[key_t] = ti
        sigs.append(dict(name=str(nm), ti=ti, n=int(len(vv))))
        vparts.append(vv.astype(np.float32))
    off, tdesc = 0, []
    for a in times:
        tdesc.append(dict(off=off, n=int(len(a))))
        off += a.nbytes
    for s_, a in zip(sigs, vparts):
        s_["off"] = off
        off += a.nbytes
    blob = b"".join([a.tobytes() for a in times] + [a.tobytes() for a in vparts])
    T_end = max((float(a[-1]) for a in times if len(a)), default=1.0)
    return dict(blob=blob, sigs=sigs, times=tdesc, tmin=tmin, T=max(T_end, 1e-9), decim=g,
                hash=hashlib.md5(blob).hexdigest()[:16])


def _minmax_idx(v, g):
    """Indexy min a max v každé skupině g vzorků (seřazené)."""
    n = len(v)
    if n <= g:
        return np.arange(n)
    m = int(np.ceil(n / g)) * g
    a = np.full(m, np.nan)
    a[:n] = v
    a = a.reshape(-1, g)
    base = np.arange(a.shape[0]) * g
    imin = base + np.nanargmin(np.where(np.isfinite(a), a, np.inf), axis=1)
    imax = base + np.nanargmax(np.where(np.isfinite(a), a, -np.inf), axis=1)
    idx = np.unique(np.concatenate([imin, imax]))
    return idx[idx < n]


def _media_url(blob, key):
    """Data jako soubor přes media endpoint Streamlitu (adresa), nebo None (např. v testech bez běžícího serveru)."""
    try:
        from streamlit import runtime
        if not runtime.exists():
            return None
        url = runtime.get_instance().media_file_mgr.add(blob, "application/octet-stream", f"pidviewer.{key}")
        return url
    except Exception:
        return None


def roles(ctx):
    """Role signálů smyčky {název: (role, barva, jednotka)} – PV, SP, MV, poruchy, poloha ventilu."""
    out = {}
    if getattr(ctx, "c_pv", None) is not None:
        out[str(ctx.c_pv)] = ("PV", C_PV, ctx.u_pv or "")
    if getattr(ctx, "has_sp", False):
        out[str(ctx.c_sp)] = ("SP", C_SP, ctx.u_pv or "")
    if getattr(ctx, "c_mv", None) is not None:
        out[str(ctx.c_mv)] = ("MV", C_MV, ctx.u_mv or "")
    for j, d in enumerate(getattr(ctx, "c_d", []) or []):
        out.setdefault(str(d), ("DV", C_DIST[j % len(C_DIST)], ""))
    pos = getattr(ctx, "c_pos", "—")
    if pos not in (None, "—"):
        out.setdefault(str(pos), ("POS", "#7c3aed", "%"))
    return out


def _on_layout(key):
    v = ss.get(key)
    lay = getattr(v, "layout", None) if not isinstance(v, dict) else v.get("layout")
    if isinstance(lay, str) and len(lay) <= LAYOUT_MAX:
        try:
            json.loads(lay)
        except ValueError:
            return
        ss["dview"] = lay


def render(ctx, key="data_view", height_hint=None):
    """Prohlížeč záznamu (jen na aktivní záložce). Vrací None."""
    from .charts import visible
    from .theme import palette
    from .trend import clock_ms
    if not visible():
        return None
    names = [str(s_) for s_ in ctx.sigs]
    vkey = getattr(ctx, "vkey", None) or (ctx.fname, len(ctx.t_all))
    bkey = _blob_key(vkey)
    pl = _payload(bkey, tuple(names), ctx.t_all, ctx.get)
    rl = roles(ctx)
    sigs, k_other = [], 0
    for s_ in pl["sigs"]:
        role, col, unit = rl.get(s_["name"], ("", None, ""))
        if col is None:
            col = OTHER[k_other % len(OTHER)]
            k_other += 1
        sigs.append(dict(s_, role=role, color=col, unit=unit))
    clock = None
    if ctx.t_origin is not None and (ss.get("chart_tunit") or "auto") == "auto":
        try:
            import pandas as pd
            clock = float((pd.Timestamp(ctx.t_origin) + pd.to_timedelta(pl["tmin"], unit="s")).value / 1e6)
        except Exception:
            clock = clock_ms(ctx)
    data = dict(key=key, view_key=f"{ctx.fname}|{bkey}", sigs=sigs, times=pl["times"], T=pl["T"], decim=pl["decim"],
                hash=pl["hash"], clock=clock, tunit=ss.get("chart_tunit") or "auto",
                dec="," if ss.get("lang", "cs") == "cs" else ".", dark=palette()["bg"] != "#eef1f5",
                txt={k: T("vw_" + k) for k in TXT}, fname=str(ctx.fname).split("|")[0])
    url = _media_url(pl["blob"], key) if len(pl["blob"]) > INLINE_MAX else None
    if url is not None:
        base = (st.get_option("server.baseUrlPath") or "").strip("/")
        data["url"], data["base"] = url, base
    else:
        data["b64"] = base64.b64encode(pl["blob"]).decode("ascii")
    data["sig"] = hashlib.md5(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()
    lay = ss.get("dview")
    data["layout"] = lay if isinstance(lay, str) and len(lay) <= LAYOUT_MAX else None
    comp = v2_component("pidtools_viewer", css=_CSS, js=static_asset("viewer_an.js") + "\n" + static_asset("viewer.js"))
    return comp(key=key, data=data, on_layout_change=lambda: _on_layout(key))
