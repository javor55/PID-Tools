"""
Projekt (JSON): uložení a obnova celé práce – všech smyček, modelů, ladění a volitelně dat.

Projekt obsahuje stav widgetů (klíče ze STATE_KEYS a s prefixy STATE_PREFIX), mapování sloupců, úseky,
nafitované modely, parametry sad a dopředné vazby a volitelně převzorkovaná data.
Obnova (`apply_project`) jen zapíše hodnoty do session state – widgety si je převezmou při dalším vykreslení.
"""
import datetime as _dt
import json

import streamlit as st

from ..app.project import (PROJECT_VERSION, STATE_KEYS, STATE_PREFIX, fit_record, jsonable, loop_records,  # noqa: F401
                           is_state_key, clean_state, migrate_state, serialize_project)
from . import loops

ss = st.session_state

def apply_project(proj):
    """
    Obnoví stav aplikace z projektu (volá se před vykreslením widgetů – z callbacku nahrání souboru).
    Projekt s více smyčkami má v „loops“ záznam každé smyčky (stejný tvar jako jednosmyčkový projekt);
    smyčky se obnoví jedna po druhé a uloží jako snímky, nakonec se přepne na tu, která byla aktivní.
    """
    recs, act = loop_records(proj)
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
        _apply_one(rec)
        st_["info"][i] = {"name": rec.get("tag", "")}
        if i < len(recs):
            st_["snap"][i] = loops.snapshot()
    loops.switch(act + 1)


def _apply_one(proj):
    """Obnova jedné smyčky (a společného stavu) do session state."""
    ss.proj = proj
    state, bad = clean_state(migrate_state(proj.get("state", {})))
    for k_, v_ in state.items():
        ss[k_] = v_
    if bad:
        ss["proj_skipped"] = ss.get("proj_skipped", 0) + bad
    fnames = [proj.get("fname", "")]
    if proj.get("data"):
        n_ = len(next(iter(proj["data"]["cols"].values())))
        fnames.append(f"project|{proj.get('fname_tag', proj.get('tag', ''))}|{n_}")
        ss["src"] = "project"
        ss["c_tim"], ss["ts_manual"], ss["time_unit"], ss["time_fmt"] = "t_s", False, "s", "auto"
        ss[f"layout|{fnames[-1]}"] = "wide"  # uložená data jsou už na společné mřížce (sloupec t_s)
    mp = {k: v for k, v in (proj.get("map") or {}).items()       # sloupce smyčky: jen známé klíče a texty
          if k in ("c_pv", "c_mv", "c_sp", "c_pos") and isinstance(v, str)
          or k == "c_d" and isinstance(v, list) and all(isinstance(x, str) for x in v)}
    for fn_ in fnames:
        for k_, v_ in mp.items():
            ss[f"{k_}|{fn_}"] = v_
    win = proj.get("windows") or {}
    for fn_ in fnames:                         # úseky podle vstupů a vyřazení dat patří k souboru
        if isinstance(win.get("wins"), dict):
            ss[f"wins|{fn_}"] = {str(k): [[float(a), float(b)] for a, b in v] for k, v in win["wins"].items()}
        for nm, (on, lo, hi) in (win.get("excl") or {}).items():
            ss[f"excl|{fn_}|{nm}|on"], ss[f"excl|{fn_}|{nm}|lo"], ss[f"excl|{fn_}|{nm}|hi"] = bool(on), lo, hi
        if "tol" in win:
            ss[f"excl|{fn_}|tol"] = float(win["tol"])
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
        if is_state_key(k):
            if str(k).startswith(STATE_PREFIX) and loops._is_loop_key(k) and k not in snap:
                continue
            v = jsonable(get(k))
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
    wins = get(f"wins|{fn}")
    pre = f"excl|{fn}|"
    excl = {k[len(pre):-3]: [bool(get(f"{k[:-3]}|on")), get(f"{k[:-3]}|lo"), get(f"{k[:-3]}|hi")]
            for k in set(snap) | set(ss.keys()) if str(k).startswith(pre) and str(k).endswith("|on")}
    if wins or excl:
        rec["windows"] = jsonable(dict(wins=wins or {}, excl=excl, tol=get(f"excl|{fn}|tol", 0.5)))
    fit = fit_record(get("fit"))
    if fit:
        rec["fit"] = fit
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


def build_project(c, include_data):
    """Projekt jako JSON text (c = Ctx aktuálního běhu)."""
    return serialize_project(gather_project(c, include_data))
