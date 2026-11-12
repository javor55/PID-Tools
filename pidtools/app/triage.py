"""
Triáž smyček (E5): dávková diagnostika všech smyček projektu a verdikt pro každou z nich.

Metriky jedné smyčky (`loop_metrics`): podíl AUTO, Harrisův index (zpoždění z modelu, zadané uživatelem, jinak z dat),
oscilace, stikce a hystereze, nelinearita, kvalita dat. Verdikt určují pravidla v registru `RULES` (id, popisek v i18n,
schéma prahů, funkce, test v tests/test_triage.py); první pravidlo v pořadí, které platí, vyhrává. Každé pravidlo je čistá
funkce `fn(metriky, prahy, kontext) -> seznam důkazů | None`, důkaz = {metric, value, threshold, text (klíč i18n)}.
Kontext nese podřazenou smyčku kaskády a zdroj společné oscilace.
"""
from dataclasses import dataclass

import numpy as np

from . import audit
from .loopmode import detect

PERIOD_TOL = 0.10                 # společná oscilace: stejná perioda ± 10 %


@dataclass
class Thr:
    """Jeden práh pravidla: výchozí hodnota, meze a jednotka pro formulář v nastavení."""
    default: float
    lo: float
    hi: float
    unit: str = ""
    label: str = ""               # klíč i18n


@dataclass
class Rule:
    id: str
    label: str                    # klíč i18n popisku verdiktu
    severity: int                 # 0 v pořádku … 3 nejzávažnější
    thresholds: dict              # {název: Thr}
    fn: object                    # fn(m, thr, ctx) -> [důkaz] | None
    doc: str = ""


def ev(metric, value, threshold, text):
    return dict(metric=metric, value=None if value is None else float(value),
                threshold=None if threshold is None else float(threshold), text=text)


# ---- pravidla ---------------------------------------------------------------------------------------------------------
def _low_auto(m, thr, ctx):
    out = []
    if m["auto_pct"] < thr["min_auto_pct"]:
        out.append(ev("auto_pct", m["auto_pct"], thr["min_auto_pct"], "tri_ev_low_auto"))
    if m["frozen_pct"] > thr["max_frozen_pct"]:
        out.append(ev("frozen_pct", m["frozen_pct"], thr["max_frozen_pct"], "tri_ev_frozen"))
    if m["nan_pct"] > thr["max_nan_pct"]:
        out.append(ev("nan_pct", m["nan_pct"], thr["max_nan_pct"], "tri_ev_nan"))
    return out or None


def _foreign(m, thr, ctx):
    f = ctx.get("foreign")
    if m["osc"] and f and f["source"] != m["name"] and m["stic"] != "likely":
        return [ev("period", m["period"], f["period"], "tri_ev_foreign")]
    return None


def _cascade(m, thr, ctx):
    s = ctx.get("slave")
    if s is None:
        return None
    low = s["harris"] is not None and s["harris"] < thr["slave_harris"]
    if not (s["osc"] or s["stic"] == "likely" or low):
        return None
    if not (m["osc"] or (m["harris"] is not None and m["harris"] < thr["slave_harris"])):
        return None
    if s["harris"] is not None:
        return [ev("slave_harris", s["harris"], thr["slave_harris"], "tri_ev_cascade")]
    return [ev("slave_osc", 1.0 if s["osc"] else 0.0, None, "tri_ev_cascade")]


def _valve(m, thr, ctx):
    out = []
    if m["stic"] == "likely":
        out.append(ev("stic_ratio", m["stic_ratio"], 0.35, "tri_ev_stic"))
    if m["hyst_pct"] is not None and m["hyst_pct"] > thr["hyst_pct"]:
        out.append(ev("hyst_pct", m["hyst_pct"], thr["hyst_pct"], "tri_ev_hyst"))
    return out or None


def _nonlinear(m, thr, ctx):
    if m["nonlin"] is not None and m["nonlin"] > thr["nonlin_ratio"]:
        return [ev("nonlin", m["nonlin"], thr["nonlin_ratio"], "tri_ev_nonlin")]
    return None


def _tune(m, thr, ctx):
    out = []
    if m["osc"]:
        out.append(ev("period", m["period"], None, "tri_ev_osc"))
    if m["harris"] is not None and m["harris"] < thr["harris_min"]:
        out.append(ev("harris", m["harris"], thr["harris_min"], "tri_ev_harris"))
    return out or None


def _ok(m, thr, ctx):
    if m["harris"] is not None:
        return [ev("harris", m["harris"], None, "tri_ev_ok")]
    return [ev("std_e_pct", m["std_e_pct"], None, "tri_ev_ok_noh")]


RULES = [
    Rule("low_auto", "tri_v_low_auto", 1, {
        "min_auto_pct": Thr(30, 0, 100, "%", "tri_t_min_auto"),
        "max_frozen_pct": Thr(90, 50, 100, "%", "tri_t_frozen"),
        "max_nan_pct": Thr(50, 5, 100, "%", "tri_t_nan")}, _low_auto,
        "Smyčka je většinu záznamu ručně nebo data nejsou použitelná."),
    Rule("foreign", "tri_v_foreign", 1, {}, _foreign, "Kmitá se stejnou periodou jako jiná smyčka – příčinu hledej tam."),
    Rule("cascade", "tri_v_cascade", 2, {"slave_harris": Thr(0.5, 0.05, 1, "", "tri_t_slave_harris")}, _cascade,
         "Řídicí smyčka kaskády je špatná kvůli podřazené – ladit nejdřív podřazenou."),
    Rule("valve", "tri_v_valve", 3, {"hyst_pct": Thr(2, 0.1, 20, "%", "tri_t_hyst")}, _valve,
         "Stikce nebo hystereze ventilu – ladění regulátoru nepomůže."),
    Rule("nonlinear", "tri_v_nonlinear", 2, {"nonlin_ratio": Thr(3, 1.2, 20, "×", "tri_t_nonlin")}, _nonlinear,
         "Zesílení procesu se výrazně mění s pracovním bodem."),
    Rule("tune", "tri_v_tune", 2, {"harris_min": Thr(0.5, 0.05, 1, "", "tri_t_harris")}, _tune,
         "Kmitání nebo výkon pod hranicí možností při zdravém ventilu – ladit."),
    Rule("ok", "tri_v_ok", 0, {}, _ok, "Bez nálezu."),
]
BY_ID = {r.id: r for r in RULES}


def default_thresholds():
    """Výchozí prahy {pravidlo: {název: hodnota}}."""
    return {r.id: {k: t.default for k, t in r.thresholds.items()} for r in RULES}


def merge_thresholds(user):
    """Prahy z nastavení doplněné výchozími; neznámé a nečíselné hodnoty se vynechají, hodnoty se ořežou na meze."""
    out = default_thresholds()
    for rid, d in (user or {}).items():
        if rid not in out or not isinstance(d, dict):
            continue
        for k, v in d.items():
            t = BY_ID[rid].thresholds.get(k)
            if t is not None and isinstance(v, (int, float)) and not isinstance(v, bool) and np.isfinite(v):
                out[rid][k] = float(min(max(v, t.lo), t.hi))
    return out


def evaluate(m, thr, ctx=None):
    """Verdikt jedné smyčky z metrik: (id, závažnost, důkazy)."""
    ctx = ctx or {}
    for r in RULES:
        e = r.fn(m, thr[r.id], ctx)
        if e:
            return r.id, r.severity, e
    return "ok", 0, []


# ---- metriky ----------------------------------------------------------------------------------------------------------
def loop_metrics(sig, d, ts_user=None, hyst_pct=None, nonlin=None, theta_model=None, theta_user=None):
    """
    Metriky jedné smyčky z dat (audit.analyse_loop + podíl AUTO + kvalita). Zpoždění: model > zadané > odhad z dat.
    Vrací dict (ok False + err při chybě).
    """
    theta, src = (theta_model, "model") if theta_model is not None else (
        (theta_user, "user") if theta_user else (None, None))
    d.extra = dict(d.extra or {})
    if theta is not None:
        d.extra["theta"] = float(theta)
    r = audit.analyse_loop(sig, d, ts_user)
    m = dict(name=d.name, ok=bool(r["ok"]), err=r["err"])
    if not r["ok"]:
        return m
    k = r["kpis"]
    det = detect(r["t"], r["mv"], r["pv"], r["sp"])
    raw = np.asarray(sig.get(d.pv), float)
    if theta is None and k["theta"] is not None:
        src = "data"
    m.update(auto_pct=float(det["frac"] * 100), harris=k["harris"], theta=k["theta"], theta_src=src, osc=k["osc"],
             period=k["period"], amp=k["amp"], stic=k["stic"], stic_ratio=k["stic_ratio"], hyst_pct=hyst_pct,
             nonlin=nonlin, frozen_pct=k["frozen"], nan_pct=float(np.mean(~np.isfinite(raw)) * 100),
             at_lim=k["at_lim"], std_e_pct=k["std_e_pct"], iae_h=k["iae_h"], travel_h=k["travel_h"], rev_h=k["rev_h"])
    return m


def common_periods(ms, tol=PERIOD_TOL):
    """Skupiny kmitajících smyček se stejnou periodou ± tol: [dict(period, loops [indexy], source [index], by_stiction)]."""
    idx = sorted([i for i, m in enumerate(ms) if m.get("ok") and m["osc"]], key=lambda i: ms[i]["period"])
    groups = []
    for i in idx:
        p = ms[i]["period"]
        for g in groups:
            if abs(p - g["period"]) <= tol * g["period"]:
                g["loops"].append(i)
                g["period"] = float(np.mean([ms[j]["period"] for j in g["loops"]]))
                break
        else:
            groups.append(dict(period=p, loops=[i]))
    out = []
    for g in groups:
        if len(g["loops"]) < 2:
            continue
        st = [i for i in g["loops"] if ms[i]["stic"] == "likely"]
        src = (st or sorted(g["loops"], key=lambda i: -ms[i]["std_e_pct"]))[0]
        out.append(dict(period=g["period"], loops=g["loops"], source=src, by_stiction=bool(st)))
    return out


def verdicts(ms, links=None, thr=None):
    """
    Verdikty všech smyček. ms = metriky (v pořadí smyček), links = {index řídicí smyčky: index podřazené},
    thr = prahy uživatele. Vrací (seznam dict(verdict, severity, evidence), společné oscilace).
    """
    thr = merge_thresholds(thr)
    links = links or {}
    com = common_periods(ms)
    out = []
    for i, m in enumerate(ms):
        if not m.get("ok"):
            out.append(dict(verdict="low_auto", severity=1, evidence=[ev("err", None, None, "tri_ev_err")]))
            continue
        ctx = {}
        s = links.get(i)
        if s is not None and ms[s].get("ok"):
            ctx["slave"] = ms[s]
        for g in com:
            if i in g["loops"] and g["source"] != i:
                ctx["foreign"] = dict(source=ms[g["source"]]["name"], period=g["period"])
        v, sev, e = evaluate(m, thr, ctx)
        out.append(dict(verdict=v, severity=sev, evidence=e))
    return out, com


def start_order(rows):
    """„Kde začít“: smyčky s nálezem – ventil a podřazené smyčky před laděním, pak podle odchylky."""
    prio = {"valve": 0, "cascade": 1, "nonlinear": 2, "tune": 3, "low_auto": 4, "foreign": 5}
    slaves = {r["slave"] for r in rows if r.get("slave") is not None}
    bad = [r for r in rows if r["verdict"] in prio]
    return sorted(bad, key=lambda r: (prio[r["verdict"]], r["index"] not in slaves,
                                      -(r["metrics"].get("std_e_pct") or 0)))


# ---- dávka (úloha na pozadí) -------------------------------------------------------------------------------------------
class Packed:
    """Přenositelné (pickle) signály jedné smyčky: stejné rozhraní jako dataset.Signals (t_all, sigs, get)."""

    def __init__(self, t_all, cols):
        self.t_all, self.cols, self.sigs = np.asarray(t_all, float), cols, list(cols)

    def get(self, c):
        return self.cols[c]


def run(inputs, thr=None, links=None, progress=None):
    """
    Triáž všech smyček (běží v procesu úlohy, app.jobs). inputs = [dict(tag, pv, mv, sp, pos, integ, ts_user, t_all,
    cols, hyst_pct, nonlin, theta_model, theta_user)]. Vrací dict(rows, common, start, thresholds).
    """
    ms = []
    for i, x in enumerate(inputs):
        if progress:
            progress((i + 0.5) / max(len(inputs), 1), str(x["tag"]))
        d = audit.LoopDef(name=x["tag"], pv=x["pv"], mv=x["mv"], sp=x.get("sp"), pos=x.get("pos"),
                          integ=bool(x.get("integ")))
        try:
            m = loop_metrics(Packed(x["t_all"], x["cols"]), d, x.get("ts_user"), x.get("hyst_pct"), x.get("nonlin"),
                             x.get("theta_model"), x.get("theta_user"))
        except Exception as ex:                 # jedna vadná smyčka nesmí zastavit dávku
            m = dict(name=x["tag"], ok=False, err=str(ex))
        ms.append(m)
    vs, com = verdicts(ms, links, thr)
    rows = []
    for i, v in enumerate(vs):
        met = {k: val for k, val in ms[i].items() if k not in ("name", "ok", "err")}
        rows.append(dict(index=i, tag=str(inputs[i]["tag"]), verdict=v["verdict"], severity=v["severity"],
                         evidence=v["evidence"], metrics=met, err=ms[i].get("err"), slave=(links or {}).get(i)))
    start = [r["index"] for r in start_order(rows)]
    common = [dict(period=g["period"], loops=g["loops"], source=g["source"], by_stiction=g["by_stiction"]) for g in com]
    return dict(rows=rows, common=common, start=start, thresholds=merge_thresholds(thr))
