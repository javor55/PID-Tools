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

import streamlit as st

from ..app import signalpack
from ..app.colors import C_DIST, C_MV, C_PV, C_SP
from ..i18n import T
from .widgets import static_asset, v2_component

ss = st.session_state
CAP = 6_000_000          # nejvýš hodnot všech signálů v prohlížeči (víc → min / max po skupinách)
INLINE_MAX = 1_500_000   # menší data (bajty) přímo v datech komponenty, větší přes media endpoint
LAYOUT_MAX = 65_536      # nejdelší uložené rozložení (znaky JSON)
OTHER = ["#2563eb", "#dc2626", "#059669", "#d97706", "#7c3aed", "#db2777", "#0891b2", "#65a30d", "#9333ea", "#ea580c",
         "#0f766e", "#b91c1c", "#4f46e5", "#a16207"]


TXT = ("pan", "zoom_box", "zoom_x", "zoom_y", "back", "fwd", "full", "cur", "hcur", "yauto", "ya_view", "ya_all",
       "table", "csv_view", "csv_cur", "list", "search", "panel", "new_panel", "unit", "ymin", "ymax", "auto",
       "shared", "up", "down", "remove", "help", "drag", "loading", "load_err", "retry", "signal", "mean", "min",
       "max", "slope", "rows", "rows_more", "nearest", "step", "line", "interp", "decim", "time", "no_sig",
       "color", "more", "reset", "hide", "c_hint", "h_hint", "ylock", "close",
       "scale", "sc_auto", "sc_view", "sc_all", "sc_fix", "sc_apply", "sc_view_s", "sc_all_s",
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
    """Binární data prohlížeče (app.signalpack.pack); key = klíč cache (soubor, výběr signálů)."""
    return signalpack.pack(names, _t_all, _get, CAP)


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
    comp = v2_component("pidtools_viewer", css=static_asset("viewer.css"), js=static_asset("viewer_an.js") + "\n" + static_asset("viewer.js"))
    return comp(key=key, data=data, on_layout_change=lambda: _on_layout(key))
