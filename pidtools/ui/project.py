"""
Projekt (JSON): uložení a obnova celé práce – všech smyček, modelů, ladění a volitelně dat.

Projekt obsahuje stav widgetů (klíče ze STATE_KEYS a s prefixy STATE_PREFIX), mapování sloupců, úseky,
nafitované modely, parametry sad a dopředné vazby a volitelně převzorkovaná data.
Obnova (`apply_project`) jen zapíše hodnoty do session state – widgety si je převezmou při dalším vykreslení.
"""
import datetime as _dt
import json

import numpy as np
import streamlit as st

from . import loops

ss = st.session_state

PROJECT_VERSION = 2
STATE_KEYS = [
    "lang", "loop_tag", "u_pv", "u_mv", "pv_lo", "pv_hi", "mv_lo", "mv_hi", "plot_h",
    # blok PIDConL a sady parametrů
    "samp", "diffgain", "pfb", "propfac", "dfb", "db", "db_mode", "mvl_lo", "mvl_hi", "pvfilt", "mvrate", "sprate",
    "set1_gain", "set1_ti", "set1_td", "set2_gain", "set2_ti", "set2_td",
    # identifikace
    "thmax", "chosen", "mcode", "dist_level", "dist_strength", "gain_sign", "id_stic",
    # ladění a simulace
    "ctype", "opt_ms", "opt_noise", "opt_robust", "opt_crit", "opt_target", "opt_ovs", "avg_dpv", "avg_dmv",
    "scen2", "sim_len_u", "sim_J", "sim_noise", "vchar_last",
    # plán testu, kaskáda, diagnostika
    "plan_dpv", "plan_snr", "cas_src", "cas_k", "cas_t1", "cas_t2", "cas_th", "cas_im", "cas_om", "cas_oct",
    "cas_samp", "cas_tci", "cas_tco", "diag_integ",
    # hlavička reportu
    "rep_plant", "rep_author", "rep_status", "rep_comment",
]
STATE_PREFIX = ("ed|", "method|", "tc|", "tend_r|", "fx|", "sim_S|", "scen_df|", "gs_")


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
    if "propfac" not in state and "pfb" in state:   # starší projekty: přepínač P ve zpětné vazbě → PropFacSP
        ss["propfac"] = 0.0 if state["pfb"] else 1.0
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


def gather_project(c, include_data):
    """
    Obsah projektu jako slovník (rychlé – volá se při vykreslení). Data zůstávají jako pole numpy;
    převod na JSON dělá `serialize_project` (až při stažení, mimo hlavní vlákno, bez přístupu k session state).
    Nahoře je záznam aktivní smyčky (čitelný i starší verzí), při více smyčkách navíc „loops“ a „active“.
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
        cols_ = {"t_s": c.t, str(c.c_pv): c.pv_e, str(c.c_mv): c.mv_e}
        if c.has_sp:
            cols_[str(c.c_sp)] = c.sp_e
        for nm, d in zip(c.c_d, c.dists):
            cols_[str(nm)] = d
        if c.pos_e is not None:
            cols_[str(c.c_pos)] = c.pos_e
        for r in rec_of.values():  # sloupce ostatních smyček na časové mřížce aktivní smyčky
            for v in r["map"].values():
                for col in (v if isinstance(v, list) else [v]):
                    if col and col != "—" and str(col) not in cols_ and col in c.sigs:
                        cols_[str(col)] = c.on_grid(col)
        proj["data"] = {"cols": cols_}
    return proj


def serialize_project(proj):
    """Projekt (z `gather_project`) → JSON text; pole dat zaokrouhlená na 6 platných číslic."""
    proj = dict(proj)
    if "data" in proj:
        r6 = lambda a: [None if not np.isfinite(x) else float(f"{x:.6g}") for x in np.asarray(a, float)]  # noqa: E731
        proj["data"] = {"cols": {k: r6(v) for k, v in proj["data"]["cols"].items()}}
    return json.dumps(proj, ensure_ascii=False)


def build_project(c, include_data):
    """Projekt jako JSON text (c = Ctx aktuálního běhu)."""
    return serialize_project(gather_project(c, include_data))
