"""
Projekt smyčky (JSON) a HTML report.

Projekt obsahuje stav widgetů (klíče ze STATE_KEYS a s prefixy STATE_PREFIX), mapování sloupců, úseky,
nafitované modely, parametry sad a dopředné vazby a volitelně převzorkovaná data.
Obnova (`apply_project`) jen zapíše hodnoty do session state – widgety si je převezmou při dalším vykreslení.
"""
import datetime as _dt
import json

import numpy as np
import plotly.graph_objects as go
import streamlit as st

from ..i18n import T
from . import loops
from .charts import REPORT
from .theme import report_template

ss = st.session_state

PROJECT_VERSION = 2
STATE_KEYS = [
    "lang", "loop_tag", "u_pv", "u_mv", "pv_lo", "pv_hi", "mv_lo", "mv_hi", "plot_h",
    # blok PIDConL a sady parametrů
    "samp", "diffgain", "pfb", "dfb", "db", "db_mode", "mvl_lo", "mvl_hi", "pvfilt", "mvrate", "sprate",
    "set1_gain", "set1_ti", "set1_td", "set2_gain", "set2_ti", "set2_td",
    # identifikace
    "thmax", "chosen", "mcode", "dist_level", "dist_strength", "gain_sign", "id_stic",
    # ladění a simulace
    "ctype", "opt_ms", "opt_noise", "opt_robust", "opt_crit", "opt_target", "opt_ovs", "avg_dpv", "avg_dmv",
    "scen2", "sim_len_u", "sim_J", "sim_noise", "vchar_last",
    # plán testu, kaskáda, diagnostika
    "plan_dpv", "plan_snr", "cas_src", "cas_k", "cas_t1", "cas_t2", "cas_th", "cas_im", "cas_om", "cas_oct",
    "cas_samp", "cas_tci", "cas_tco", "diag_integ",
]
STATE_PREFIX = ("ed|", "method|", "tc|", "tend_r|", "fx|", "sim_S|", "scen_df|")


def _jsonable(v):
    if isinstance(v, (np.floating, float)):
        return float(v)
    if isinstance(v, (np.integer, int, bool, str)) or v is None:
        return v.item() if isinstance(v, np.generic) else v
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    return None


def apply_project(proj):
    """
    Obnoví stav aplikace z projektu (volá se před vykreslením widgetů – z callbacku nahrání souboru).
    Projekt s více smyčkami má v „loops“ záznam každé smyčky (stejný tvar jako jednosmyčkový projekt);
    smyčky se obnoví jedna po druhé a uloží jako snímky, nakonec se přepne na tu, která byla aktivní.
    """
    recs = proj.get("loops") or []
    if len(recs) < 2:
        loops.reset(1)
        loops.clear()
        _apply_one(proj)
        return
    loops.reset(len(recs))
    st_ = ss["loops"]
    for i, rec in enumerate(recs, start=1):
        st_["active"] = i
        loops.clear()
        _apply_one({**proj, **rec, "fname_tag": proj.get("tag", "")})
        st_["info"][i] = {"name": rec.get("tag", "")}
        if i < len(recs):
            st_["snap"][i] = loops.snapshot()
    loops.switch(min(max(int(proj.get("active", 1)), 1), len(recs)))


def _apply_one(proj):
    """Obnova jedné smyčky (a společného stavu) do session state."""
    ss.proj = proj
    state = proj.get("state", {})
    for k_, v_ in state.items():
        ss[k_] = v_
    fnames = [proj.get("fname", "")]
    if proj.get("data"):
        n_ = len(next(iter(proj["data"]["cols"].values())))
        fnames.append(f"project|{proj.get('fname_tag', proj.get('tag', ''))}|{n_}")
        ss["src"] = "project"
        ss["c_tim"], ss["ts_manual"], ss["time_unit"], ss["time_fmt"] = "t_s", False, "s", "auto"
        ss[f"layout|{fnames[-1]}"] = "wide"  # uložená data jsou už na společné mřížce (sloupec t_s)
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
    if "vchar_last" in state:
        ss["vchar_init"] = state["vchar_last"]
    for k_ in [k_ for k_ in list(ss.keys()) if str(k_).startswith("scen_ed|")]:
        del ss[k_]
    new = proj.get("new")  # projekty verze 1: nové parametry → sada 2
    if new and "set2_gain" not in state:
        ss["set2_gain"], ss["set2_ti"], ss["set2_td"] = new["Gain"], new["TI"], new["TD"]
    ss["override_ff"] = proj.get("ff")
    ss["loop_tag"] = proj.get("tag", "")


def load_project_file():
    """Callback nahrání projektu: načte JSON jen jednou (podle obsahu)."""
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


def _record(c, snap, active):
    """Záznam jedné smyčky v projektu ze snímku jejích klíčů (aktivní smyčka bere sloupce a úsek z běhu c)."""
    fn = c.fname
    get = lambda k, d=None: snap.get(k, ss.get(k, d)) if loops._is_loop_key(k) else ss.get(k, d)  # noqa: E731
    state = {}
    for k in set(snap) | set(ss.keys()):
        if k in STATE_KEYS or str(k).startswith(STATE_PREFIX):
            if str(k).startswith(STATE_PREFIX) and loops._is_loop_key(k) and k not in snap:
                continue
            v = _jsonable(get(k))
            if v is not None:
                state[k] = v
    if active:
        mp = {"c_pv": c.c_pv, "c_mv": c.c_mv, "c_sp": c.c_sp, "c_d": list(c.c_d), "c_pos": c.c_pos}
        rng = list(c.rng)
    else:
        mp = {k: snap.get(f"{k}|{fn}") for k in ("c_pv", "c_mv", "c_sp", "c_d", "c_pos") if f"{k}|{fn}" in snap}
        rng = next((list(v) for k, v in snap.items() if str(k).startswith(f"rng_id|{fn}|")), None)
    rv = next((list(v) for k, v in snap.items() if str(k).startswith(f"rng_val|{fn}|")), rng)
    rec = dict(tag=get("loop_tag", ""), state=state, map=mp, ranges={"id": rng, "val": rv}, ff=get("ff_state", []))
    fit = get("fit")
    if fit and fit.get("res"):
        res = {}
        for code, r in fit["res"].items():
            res[code] = dict(code=code, p=[float(x) for x in r["p"]], pdl=[[float(x) for x in d] for d in r["pdl"]],
                             fit=float(r["fit"]), level=r.get("level", "none"),
                             Th=None if r.get("Th") is None else float(r["Th"]), stic=float(r.get("stic") or 0.0))
        rec["fit"] = dict(res=res, dnames=list(fit["dnames"]))
    return rec


def build_project(c, include_data):
    """
    Projekt jako JSON text (c = Ctx aktuálního běhu). Nahoře je záznam aktivní smyčky (čitelný i starší verzí),
    při více smyčkách navíc „loops“ se záznamy všech smyček a „active“ (pořadí aktivní smyčky od 1).
    """
    recs = loops.all_records()
    act = loops.active()
    rec_of = {i: _record(c, snap, i == act) for i, snap in recs}
    proj = dict(version=PROJECT_VERSION, created=_dt.datetime.now().isoformat(timespec="seconds"), fname=c.fname,
                **rec_of[act])
    if len(recs) > 1:
        proj["loops"] = [rec_of[i] for i, _ in recs]
        proj["active"] = [i for i, _ in recs].index(act) + 1
    if include_data:
        r6 = lambda a: [None if not np.isfinite(x) else float(f"{x:.6g}") for x in np.asarray(a, float)]  # noqa: E731
        cols_ = {"t_s": r6(c.t), str(c.c_pv): r6(c.pv_e), str(c.c_mv): r6(c.mv_e)}
        if c.has_sp:
            cols_[str(c.c_sp)] = r6(c.sp_e)
        for nm, d in zip(c.c_d, c.dists):
            cols_[str(nm)] = r6(d)
        if c.pos_e is not None:
            cols_[str(c.c_pos)] = r6(c.pos_e)
        for r in rec_of.values():  # sloupce ostatních smyček na časové mřížce aktivní smyčky
            for v in r["map"].values():
                for col in (v if isinstance(v, list) else [v]):
                    if col and col != "—" and str(col) not in cols_ and col in c.sigs:
                        cols_[str(col)] = r6(c.on_grid(col))
        proj["data"] = {"cols": cols_}
    return json.dumps(proj, ensure_ascii=False)



_REPORT_CSS = (
    "body{font-family:Inter,'Segoe UI',Roboto,Arial,sans-serif;max-width:1100px;margin:32px auto;color:#1f2937;"
    "padding:0 20px}h1{font-weight:650}h2{margin-top:32px;border-bottom:1px solid #e5e7eb;padding-bottom:4px;"
    "font-size:1.15rem}.meta{color:#6b7280}.note{background:#f9fafb;border-left:4px solid #1f5fa8;padding:10px 14px}"
    "table.tbl{border-collapse:collapse;font-size:.9rem}table.tbl td,table.tbl th{border:1px solid #e5e7eb;"
    "padding:4px 10px;text-align:right}table.tbl th{background:#f9fafb}@media print{h2{break-before:auto}}")


def build_report(c, author, comment):
    """Samostatný HTML report (grafy interaktivní i offline, Plotly vložené jednou)."""
    tag = ss.get("loop_tag", "") or "—"
    parts = [f"<h1>{T('rep_title')} – {tag}</h1>",
             f"<p class='meta'>{_dt.datetime.now():%Y-%m-%d %H:%M} · {T('rep_author')}: {author or '—'}</p>"]
    if comment:
        parts.append(f"<div class='note'>{comment}</div>")
    status = T("status", n=len(c.t), ts=f"{c.Ts:.3g}", dur=f"{c.t[-1]:.0f}", pvr=f"{c.pv_lo:g}–{c.pv_hi:g}",
               mvr=f"{c.mv_lo:g}–{c.mv_hi:g}")
    parts.append(f"<h2>{T('rep_sec_data')}</h2><ul><li>{status}</li>"
                 f"<li>PV: {c.c_pv} · MV: {c.c_mv} · SP: {c.c_sp} · {T('col_dist')}: {', '.join(map(str, c.c_d)) or '—'}</li>"
                 f"<li>{T('seg_id')}: {c.rng[0]:.0f}–{c.rng[1]:.0f} s</li>"
                 f"<li>{c.block_summary}</li></ul>")
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
        f2.layout.template = report_template()
        for tr_ in f2.data:  # zředění dlouhých průběhů kvůli velikosti souboru
            if tr_.x is not None and len(tr_.x) > 2500:
                k_ = int(np.ceil(len(tr_.x) / 2500))
                tr_.x, tr_.y = tr_.x[::k_], tr_.y[::k_]
        f2.update_layout(height=max(320, fg.layout.height or 420), width=None)
        parts.append(f"<h2>{title}</h2>" + f2.to_html(full_html=False, include_plotlyjs=True if first else False,
                                                    config={"displaylogo": False}))
        first = False
    return (f"<!doctype html><html lang='{ss.get('lang', 'en')}'><head><meta charset='utf-8'>"
            f"<title>{T('rep_title')} {tag}</title><style>{_REPORT_CSS}</style></head><body>{''.join(parts)}</body></html>")
