"""
Formát projektu (JSON) společný pro webovou a desktopovou aplikaci.

Projekt = záznam aktivní smyčky nahoře (čitelný i starší verzí) a při více smyčkách seznam „loops“ a „active“.
Záznam smyčky: tag, state (nastavení – klíče STATE_KEYS a s prefixy STATE_PREFIX), map (sloupce PV, MV, SP,
poruchy, poloha), ranges (úsek identifikace „id“ a validace „val“), windows (úseky podle vstupů {vstup: [[od, do] s]}
a vyřazení dat {signál: [zap, min, max]} + tolerance), ff (dopředné vazby), fit (nafitované modely).
Volitelně data: {"cols": {název: hodnoty}} na společné časové mřížce „t_s“.

Verze 3 (app.domain, `format` = "pidtools.project") přidává `sources` (zdroje dat s uloženými daty `sources[i].data`),
`time_grid` a u každé smyčky `spec` (mapování rolí na `zdroj › sloupec`, rozsahy, popis, kaskáda). Záznam smyčky a klíče
výše zůstávají (starší verze aplikace je čtou), jen `data` na nejvyšší úrovni už se nepíše. Starší verze (1, 2) se při
otevření převedou řetězcem migrací `app.domain.migrate`. `PROJECT_VERSION` je verze záznamu smyčky (`Workspace.to_project`).
"""
import hashlib
import json

import numpy as np

PROJECT_VERSION = 2
EXT = ".pidproj"                      # výchozí přípona souboru projektu (obsah je JSON, stejný jako dřív)
OPEN_EXTS = (EXT, ".json")            # otevřít jde i starší projekt `.json`


def is_project_path(path):
    """Soubor vypadá jako projekt (přípona `.pidproj` nebo starší `.json`)."""
    return str(path).lower().endswith(OPEN_EXTS)


def project_name(base):
    """Název souboru ke stažení / uložení: `<base>_projekt.pidproj`."""
    return f"{base}_projekt{EXT}"

STATE_KEYS = [
    "lang", "loop_tag", "u_pv", "u_mv", "pv_lo", "pv_hi", "mv_lo", "mv_hi", "pv_rng_user", "mv_rng_user", "plot_h", "chart_tunit",
    # blok PIDConL a sady parametrů
    "samp", "diffgain", "pfb", "propfac", "dfb", "db", "db_mode", "mvl_lo", "mvl_hi", "pvfilt", "mvrate", "sprate",
    "set1_gain", "set1_ti", "set1_td", "set2_gain", "set2_ti", "set2_td", "set2_defined",
    # identifikace
    "thmax", "chosen", "mcode", "mtype", "mtype0", "proc_type", "dist_level", "dist_strength", "gain_sign", "id_stic", "win_mode",
    "read_manual",
    # ladění a simulace
    "ctype", "opt_ms", "opt_noise", "opt_robust", "opt_crit", "opt_target", "opt_ovs", "avg_dpv", "avg_dmv",
    "scen_kind", "scen_d_in", "scen_d_pv", "tune_hist", "id_mode", "audit_loops", "tri_thr", "diag_theta",
    "val_rng", "scen2", "sim_len_u", "sim_len_u_set", "sim_J", "sim_noise", "vchar_last",
    # plán testu, kaskáda, diagnostika
    "plan_dpv", "plan_snr", "cas_src", "cas_k", "cas_t1", "cas_t2", "cas_th", "cas_im", "cas_om", "cas_oct",
    "cas_samp", "cas_tci", "cas_tco", "diag_integ",
    # hlavička reportu
    "rep_plant", "rep_author", "rep_status", "rep_comment", "live_runs",
    # prohlížeč záznamu (záložka Data): rozložení panelů, barvy, měřítka, kurzory – text JSON
    "dview",
    # graf Modelu (Identifikace): vlastní rozložení panelů smyčky, nezávislé na Trendech – text JSON
    "mview",
    # graf Diagnostiky (provozní data): vlastní rozložení panelů smyčky – text JSON
    "diagview",
]
STATE_PREFIX = ("ed|", "method|", "tc|", "tend_r|", "fx|", "idf|", "sim_S|", "scen_df|", "gs_", "apc_sm_", "dkind|",
                "dsign|", "dsel|", "wmode|", "batch_sug|")


def is_state_key(k):
    return k in STATE_KEYS or str(k).startswith(STATE_PREFIX)


# typy hodnot nastavení (kontrola při načtení projektu – poškozený nebo upravený soubor nesmí shodit aplikaci)
NUM_KEYS = {"pv_lo", "pv_hi", "mv_lo", "mv_hi", "plot_h", "samp", "diffgain", "propfac", "db", "mvl_lo", "mvl_hi",
            "pvfilt", "mvrate", "sprate", "set1_gain", "set1_ti", "set1_td", "set2_gain", "set2_ti", "set2_td",
            "thmax", "dist_strength", "opt_ms", "opt_noise", "opt_ovs", "avg_dpv", "avg_dmv", "scen_d_in",
            "scen_d_pv", "sim_J", "sim_noise", "plan_dpv", "plan_snr", "cas_k", "cas_t1", "cas_t2", "cas_th",
            "cas_samp", "cas_tci", "cas_tco", "diag_theta"}
BOOL_KEYS = {"pv_rng_user", "mv_rng_user", "pfb", "dfb", "id_stic", "read_manual", "opt_robust", "sim_len_u_set",
             "diag_integ", "set2_defined"}
LIST_KEYS = {"chosen", "tune_hist", "audit_loops", "vchar_last", "live_runs"}
NUM_PREFIX = ("ed|", "tc|", "tend_r|", "sim_S|")
BOOL_PREFIX = ("fx|", "idf|")
SUG_PREFIX = "batch_sug|"        # návrh hromadného ladění (app.batch): [Kc, Ti, Td, metoda] pro model v názvu klíče


def sug_ok(v):
    """Návrh hromadného ladění: [Kc > 0, Ti ≥ 0, Td ≥ 0, metoda] – konečná čísla a neprázdný název metody."""
    return (isinstance(v, list) and len(v) == 4 and all(_num(x) for x in v[:3]) and v[0] > 0 and v[1] >= 0
            and v[2] >= 0 and isinstance(v[3], str) and bool(v[3]))


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and np.isfinite(v)


def _typed_ok(k, v):
    """
    Hodnota odpovídá typu klíče (NUM_KEYS / BOOL_KEYS / LIST_KEYS a prefixy); klíč bez předepsaného typu → None.
    Jediné místo logiky typů: používá ji načtení projektu (`clean_state`) i kontrola změny (`validate_settings`).
    """
    if k in NUM_KEYS or k.startswith(NUM_PREFIX):
        return _num(v)
    if k in BOOL_KEYS or k.startswith(BOOL_PREFIX):
        return isinstance(v, bool)
    if k in LIST_KEYS:
        return isinstance(v, list)
    if k.startswith(SUG_PREFIX):
        return sug_ok(v)
    return None


def clean_state(state):
    """
    Nastavení z projektu jen s povolenými klíči a hodnotami správného typu (ostatní se vynechají).
    Vrací (čistý stav, počet vynechaných položek).
    """
    out, bad = {}, 0
    for k, v in (state or {}).items():
        k = str(k)
        if not is_state_key(k):
            bad += 1
            continue
        ok = _typed_ok(k, v)
        if ok is None:
            ok = isinstance(v, (str, int, float, bool, list)) or v is None
        if ok and k in ENUMS and v not in ENUMS[k]:     # neplatná hodnota výčtu (poškozený soubor) → výchozí
            ok = False
        if ok:
            out[k] = v
        else:
            bad += 1
    return out, bad


# meze číselných nastavení: klíč → (dolní, horní, dolní mez včetně?, horní mez včetně?, popis)
RANGES = {
    "samp": (0, None, False, True, "must be > 0"),
    "diffgain": (0, None, False, True, "must be > 0"),
    "opt_ms": (1.0, 3.0, True, True, "must be between 1.0 and 3.0"),
    **{k: (0, None, True, True, "must be >= 0")
       for k in ("set1_ti", "set2_ti", "set1_td", "set2_td", "pvfilt", "mvrate", "sprate", "db")},
}
# výčty textových nastavení (hodnoty skutečně používané v kódu)
ENUMS = {
    "ctype": ("PI", "PID", "PD"),                 # app.appsettings.SIM_CTYPES
    "gain_sign": ("auto", "pos", "neg"),          # app.model.SIGN
    "dist_level": ("none", "medium", "high"),     # core.identification
    "db_mode": ("cont", "step"),                  # app.loop.block_ctrl, volba v TuningProfile.tsx
    "sim_len_u": ("s", "min", "h"),               # jednotka délky simulace (násobky 1 / 60 / 3600 s)
}


def validate_settings(patch, current=None):
    """
    Zkontroluje změnu nastavení před zápisem. Vrací seznam chyb ve tvaru "<klíč>: <důvod>" (prázdný = v pořádku).
    Typy jen u klíčů z NUM_KEYS / BOOL_KEYS / LIST_KEYS (ostatní klíče a prefixy se typově nekontrolují);
    `None` smí číselný klíč, jehož výchozí hodnota je None nebo který nemá výchozí hodnotu. `current` = stávající
    nastavení, se kterým se změna sloučí pro křížové kontroly (pv_hi != pv_lo, mv_hi != mv_lo).
    """
    from .workspace import DEFAULTS                     # až za běhu: workspace importuje tento modul
    errs = []
    for k, v in (patch or {}).items():
        k = str(k)
        if k in NUM_KEYS:
            if v is None:
                if k in DEFAULTS and DEFAULTS[k] is not None:
                    errs.append(f"{k}: must be a number (null is not allowed)")
                continue
            if not _typed_ok(k, v):
                errs.append(f"{k}: must be a finite number")
                continue
            if k in RANGES:
                lo, hi, lo_in, hi_in, why = RANGES[k]
                if (lo is not None and (v < lo or (v == lo and not lo_in))) or \
                        (hi is not None and (v > hi or (v == hi and not hi_in))):
                    errs.append(f"{k}: {why}")
        elif k in BOOL_KEYS or k in LIST_KEYS:
            if not _typed_ok(k, v):
                errs.append(f"{k}: must be {'a boolean' if k in BOOL_KEYS else 'a list'}")
        elif k.startswith(SUG_PREFIX) and not sug_ok(v):
            errs.append(f"{k}: must be [Kc > 0, Ti >= 0, Td >= 0, method]")
        if k in ENUMS and v not in ENUMS[k]:
            errs.append(f"{k}: must be one of {', '.join(ENUMS[k])}")
    if errs:
        return errs
    merged = {**DEFAULTS, **(current or {}), **(patch or {})}
    for lo_k, hi_k in (("pv_lo", "pv_hi"), ("mv_lo", "mv_hi")):
        if (lo_k in patch or hi_k in patch) and _num(merged.get(lo_k)) and _num(merged.get(hi_k)) \
                and merged[hi_k] == merged[lo_k]:        # nulový rozsah = dělení nulou; obrácený rozsah se dovoluje,
            errs.append(f"{hi_k}: must differ from {lo_k}")   # aby šly meze měnit po jedné (0–100 → 200–300)
    return errs


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
        if r.get("dv_cmp"):                  # porovnání struktur přenosu poruch (výběr typu v kartě poruchy)
            res[code]["dv_cmp"] = {str(j): [[st_, None if f is None else float(f), list(pd) if f is not None else str(pd),
                                              None if nr is None else float(nr), None if stt is None else int(stt)]
                                             for st_, f, pd, nr, stt in (tuple(x) + (None,) * (5 - len(x)) for x in v)]
                                            for j, v in r["dv_cmp"].items()}
        if r.get("method") == "win":          # identifikace z úseků podle vstupů
            res[code].update(method="win", fits=[float(x) for x in r.get("fits", [])],
                             wins=[[int(a), int(b)] for a, b in r.get("wins", [])])
        if r.get("mixed"):                    # kombinovaná identifikace (úseky MV v AUTO)
            res[code].update(mixed=True, p_open=[float(x) for x in r.get("p_open", [])],
                             cl_wins=[[int(a), int(b)] for a, b in r.get("cl_wins", [])],
                             fit_cl_pv=None if r.get("fit_cl_pv") is None else float(r["fit_cl_pv"]),
                             fit_cl_mv=None if r.get("fit_cl_mv") is None else float(r["fit_cl_mv"]))
    return dict(res=res, dnames=list(fit["dnames"]))


def migrate_state(state):
    """Nastavení ze starších verzí → aktuální klíče (P ve zpětné vazbě ano/ne → PropFacSP 0 / 1)."""
    state = dict(state)
    for k in [k for k in state if str(k).startswith("idf|")]:      # „Identifikovat“ (idf|, Streamlit) → „zafixovat“ (fx|)
        state.setdefault("fx|" + k[4:], not bool(state[k]))
    if "propfac" not in state and "pfb" in state:
        state["propfac"] = 0.0 if state["pfb"] else 1.0
    if "set2_defined" not in state:                  # projekty do beta 4: „Set 2 zadán“ = hodnoty jiné než výchozí 1 / 100 / 0
        from . import tuning as tun
        g, ti, td = (state.get(f"set2_{k}", d) for k, d in (("gain", 1.0), ("ti", 100.0), ("td", 0.0)))
        try:
            state["set2_defined"] = not tun.is_placeholder(float(g), float(ti), float(td))
        except (TypeError, ValueError):             # poškozená hodnota: clean_state ji stejně vynechá → Set 2 nezadán
            state["set2_defined"] = False
    return state


def mark_set2_defined(patch):
    """Změna nastavení s hodnotou Setu 2 (a bez výslovného `set2_defined`) → doplní `set2_defined = True`."""
    if "set2_defined" not in patch and any(k in patch for k in ("set2_gain", "set2_ti", "set2_td")):
        return dict(patch, set2_defined=True)
    return patch


def loop_records(proj):
    """Záznamy smyček projektu (jednosmyčkový projekt → jeden záznam) a index aktivní smyčky (od 0)."""
    recs = proj.get("loops") or []
    if len(recs) < 2:
        return [proj], 0
    recs = [{**proj, **rec, "fname_tag": proj.get("tag", "")} for rec in recs]
    for r in recs:
        r.pop("loops", None)
    return recs, min(max(int(proj.get("active", 1)), 1), len(recs)) - 1


def _round_cols(cols, time_key=None):
    """Pole dat → seznamy zaokrouhlené na 6 platných číslic (čas zdroje na 10: dlouhý záznam by jinak ztratil krok)."""
    def r(a, digits):
        return [None if not np.isfinite(x) else float(f"{x:.{digits}g}") for x in np.asarray(a, float)]
    return {k: r(v, 10 if k == time_key else 6) for k, v in cols.items()}


def serialize_project(proj):
    """Projekt → JSON text; pole dat zaokrouhlená na 6 platných číslic (data zdrojů verze 3 s otiskem SHA-256)."""
    proj = dict(proj)
    if "data" in proj:
        proj["data"] = {"cols": _round_cols(proj["data"]["cols"])}
    if proj.get("sources"):
        srcs = []
        for s in proj["sources"]:
            if s.get("data"):
                cols = _round_cols(s["data"]["cols"], "t_s")
                digest = hashlib.sha256(json.dumps(cols, separators=(",", ":")).encode("utf-8")).hexdigest()
                s = dict(s, data=dict(s["data"], cols=cols), data_ref=dict(s.get("data_ref") or {}, sha256=digest))
            srcs.append(s)
        proj["sources"] = srcs
    return json.dumps(proj, ensure_ascii=False)


def load_project(text):
    """JSON text → projekt (slovník); data jako pole numpy (None → NaN)."""
    proj = json.loads(text)

    def arrays(data):
        data = dict(data)
        data["cols"] = {k: np.array([np.nan if x is None else x for x in v], float) for k, v in data["cols"].items()}
        return data
    if "data" in proj:
        proj["data"] = arrays(proj["data"])
    if "sources" in proj:
        proj["sources"] = [dict(s, data=arrays(s["data"])) if s.get("data") else s for s in proj["sources"]]
    return proj
