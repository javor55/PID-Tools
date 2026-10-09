"""
Formát projektu (JSON) společný pro webovou a desktopovou aplikaci.

Projekt = záznam aktivní smyčky nahoře (čitelný i starší verzí) a při více smyčkách seznam „loops“ a „active“.
Záznam smyčky: tag, state (nastavení – klíče STATE_KEYS a s prefixy STATE_PREFIX), map (sloupce PV, MV, SP,
poruchy, poloha), ranges (úsek identifikace „id“ a validace „val“), windows (úseky podle vstupů {vstup: [[od, do] s]}
a vyřazení dat {signál: [zap, min, max]} + tolerance), ff (dopředné vazby), fit (nafitované modely).
Volitelně data: {"cols": {název: hodnoty}} na společné časové mřížce „t_s“.
"""
import json

import numpy as np

PROJECT_VERSION = 2
STATE_KEYS = [
    "lang", "loop_tag", "u_pv", "u_mv", "pv_lo", "pv_hi", "mv_lo", "mv_hi", "pv_rng_user", "mv_rng_user", "plot_h", "chart_tunit",
    # blok PIDConL a sady parametrů
    "samp", "diffgain", "pfb", "propfac", "dfb", "db", "db_mode", "mvl_lo", "mvl_hi", "pvfilt", "mvrate", "sprate",
    "set1_gain", "set1_ti", "set1_td", "set2_gain", "set2_ti", "set2_td",
    # identifikace
    "thmax", "chosen", "mcode", "mtype", "proc_type", "dist_level", "dist_strength", "gain_sign", "id_stic", "win_mode",
    "read_manual",
    # ladění a simulace
    "ctype", "opt_ms", "opt_noise", "opt_robust", "opt_crit", "opt_target", "opt_ovs", "avg_dpv", "avg_dmv",
    "scen_kind", "scen_d_in", "scen_d_pv", "tune_hist", "id_mode", "audit_loops",
    "scen2", "sim_len_u", "sim_len_u_set", "sim_J", "sim_noise", "vchar_last",
    # plán testu, kaskáda, diagnostika
    "plan_dpv", "plan_snr", "cas_src", "cas_k", "cas_t1", "cas_t2", "cas_th", "cas_im", "cas_om", "cas_oct",
    "cas_samp", "cas_tci", "cas_tco", "diag_integ",
    # hlavička reportu
    "rep_plant", "rep_author", "rep_status", "rep_comment",
]
STATE_PREFIX = ("ed|", "method|", "tc|", "tend_r|", "fx|", "idf|", "sim_S|", "scen_df|", "gs_", "apc_sm_", "dkind|",
                "dsign|")


def is_state_key(k):
    return k in STATE_KEYS or str(k).startswith(STATE_PREFIX)


def jsonable(v):
    """Hodnota pro JSON (čísla numpy → Python, n-tice → seznamy); nepřevoditelné → None (neukládá se)."""
    if isinstance(v, (np.floating, float)):
        return float(v)
    if isinstance(v, (np.integer, int, bool, str)) or v is None:
        return v.item() if isinstance(v, np.generic) else v
    if isinstance(v, (list, tuple)):
        return [jsonable(x) for x in v]
    if isinstance(v, dict):
        return {str(k): jsonable(x) for k, x in v.items()}
    return None


def fit_record(fit):
    """Nafitované modely (stav identifikace: res = {kód: výsledek}, dnames) → záznam projektu, nebo None."""
    if not fit or not fit.get("res"):
        return None
    res = {}
    for code, r in fit["res"].items():
        res[code] = dict(code=code, p=[float(x) for x in r["p"]], pdl=[[float(x) for x in d] for d in r["pdl"]],
                         fit=float(r["fit"]), level=r.get("level", "none"),
                         Th=None if r.get("Th") is None else float(r["Th"]), stic=float(r.get("stic") or 0.0))
        if r.get("method") == "win":          # identifikace z úseků podle vstupů
            res[code].update(method="win", fits=[float(x) for x in r.get("fits", [])],
                             wins=[[int(a), int(b)] for a, b in r.get("wins", [])])
    return dict(res=res, dnames=list(fit["dnames"]))


def migrate_state(state):
    """Nastavení ze starších verzí → aktuální klíče (P ve zpětné vazbě ano/ne → PropFacSP 0 / 1)."""
    state = dict(state)
    if "propfac" not in state and "pfb" in state:
        state["propfac"] = 0.0 if state["pfb"] else 1.0
    return state


def loop_records(proj):
    """Záznamy smyček projektu (jednosmyčkový projekt → jeden záznam) a index aktivní smyčky (od 0)."""
    recs = proj.get("loops") or []
    if len(recs) < 2:
        return [proj], 0
    recs = [{**proj, **rec, "fname_tag": proj.get("tag", "")} for rec in recs]
    for r in recs:
        r.pop("loops", None)
    return recs, min(max(int(proj.get("active", 1)), 1), len(recs)) - 1


def serialize_project(proj):
    """Projekt → JSON text; pole dat zaokrouhlená na 6 platných číslic."""
    proj = dict(proj)
    if "data" in proj:
        def r6(a):
            return [None if not np.isfinite(x) else float(f"{x:.6g}") for x in np.asarray(a, float)]
        proj["data"] = {"cols": {k: r6(v) for k, v in proj["data"]["cols"].items()}}
    return json.dumps(proj, ensure_ascii=False)


def load_project(text):
    """JSON text → projekt (slovník); data jako pole numpy (None → NaN)."""
    proj = json.loads(text)
    if "data" in proj:
        proj["data"] = {"cols": {k: np.array([np.nan if x is None else x for x in v], float)
                                 for k, v in proj["data"]["cols"].items()}}
    return proj
