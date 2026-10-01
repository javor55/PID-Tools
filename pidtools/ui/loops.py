"""
Více regulačních smyček v jednom projektu (např. vnější a vnitřní smyčka kaskády ze stejného exportu dat).

Aktivní smyčka žije přímo v `st.session_state` – stránky o smyčkách nic nevědí. Neaktivní smyčky jsou uložené
jako snímek svých klíčů session state; přepnutí (callback, tedy před vykreslením widgetů) uloží snímek aktivní
smyčky a obnoví snímek vybrané. Společné jsou jen klíče zdroje dat, čtení souboru a vzhledu (GLOBAL_*);
všechno ostatní (sloupce, rozsahy, blok PIDConL, identifikace, ladění…) patří smyčce.

Stav: ss["loops"] = {"ids": [...], "active": id, "next": id, "snap": {id: {klíč: hodnota}}, "info": {id: souhrn}}
Souhrn (název, model, sady, sloupce) se ukládá na konci každého běhu – čte ho záložka Kaskáda a přepínač.
"""
import numpy as np
import streamlit as st

from ..i18n import T

ss = st.session_state

GLOBAL_KEYS = {
    "lang", "src", "up_file", "proj_up", "proj", "proj_hash", "proj_err", "proj_json", "proj_saved", "report_html",
    "rep_author", "rep_comment", "plot_h", "time_fmt", "time_unit", "ts_manual", "ts_user", "c_tim", "c_tim_l",
    "c_tag", "c_val", "main_tab", "prev_open", "drag", "inner_fit", "test_inject", "proj_inc", "loops", "loop_sel",
    "_up_keep", "_up_seen", "_src_prev", "_src_now",
}
GLOBAL_PREFIX = ("layout|", "cas_", "apc_", "autosave", "_autosave", "rep_", "live_sim", "_proj")
# widgety, jejichž hodnotu Streamlit nedovolí zapsat (tlačítka, výběr v grafu/tabulce, editory – ty se obnoví
# z uložených „…|last“ hodnot); do snímku smyčky se neukládají
SKIP_PREFIX = ("scen_ed|", "vchar_ed", "chart_data|", "cmp|", "cmp_s", "segtab|", "g_", "tg_")


def _is_loop_key(k):
    k = str(k)
    return k not in GLOBAL_KEYS and not k.startswith(GLOBAL_PREFIX)


def _state():
    if "loops" not in ss:
        ss["loops"] = {"ids": [1], "active": 1, "next": 2, "snap": {}, "info": {}}
    return ss["loops"]


def ids():
    return list(_state()["ids"])


def active():
    return _state()["active"]


def info(i):
    return _state()["info"].get(i, {})


def name(i):
    """Název smyčky: tag smyčky, jinak tag z názvu sloupce PV, jinak „Smyčka n“; stejné názvy se doplní pořadím."""
    lids = ids()
    n = lids.index(i) + 1 if i in lids else i
    nm = info(i).get("name")
    if not nm:
        return T("loop_n", n=n)
    if sum(info(j).get("name") == nm for j in lids) > 1:
        return f"{nm} · {n}"
    return nm


def _restorable(k, v):
    """Hodnota jde zapsat zpět do session state (ne tlačítko, výběr v grafu/tabulce, data editor, nahraný soubor)."""
    if str(k).startswith(SKIP_PREFIX):
        return False
    if hasattr(v, "keys") and ("selection" in v or "edited_rows" in v):
        return False
    return not hasattr(v, "getvalue")


def snapshot():
    """Klíče aktivní smyčky (bez widgetů, které nejde obnovit zápisem)."""
    return {k: v for k in list(ss.keys()) if _is_loop_key(k) and _restorable(k, v := ss[k])}


def clear():
    """Odstraní klíče aktivní smyčky (widgety pak začnou z výchozích hodnot)."""
    for k in [k for k in list(ss.keys()) if _is_loop_key(k)]:
        del ss[k]


def restore(snap):
    """Zapíše snímek smyčky do session state (klíče, které Streamlit zapsat nedovolí – tlačítka apod. – vynechá)."""
    clear()
    for k, v in snap.items():
        try:
            ss[k] = v
        except Exception:
            pass
    if "vchar_last" in snap:
        ss["vchar_init"] = snap["vchar_last"]


def switch(to):
    """Přepne aktivní smyčku (volat z callbacku – před vykreslením widgetů)."""
    s = _state()
    if to == s["active"] or to not in s["ids"]:
        return
    s["snap"][s["active"]] = snapshot()
    restore(s["snap"].pop(to, {}))
    s["active"] = to
    ss["loop_sel"] = to


def add():
    """Nová prázdná smyčka (sloupce se předvyplní – přednostně jiná PV než u ostatních smyček)."""
    s = _state()
    new = s["next"]
    s["next"] += 1
    s["ids"].append(new)
    s["snap"][s["active"]] = snapshot()
    clear()
    s["active"] = new
    ss["loop_sel"] = new


def remove(i):
    """Odstraní smyčku; z aktivní se přepne na sousední."""
    s = _state()
    if len(s["ids"]) <= 1 or i not in s["ids"]:
        return
    if i == s["active"]:
        k = s["ids"].index(i)
        switch(s["ids"][k - 1] if k > 0 else s["ids"][1])
    s["ids"].remove(i)
    s["snap"].pop(i, None)
    s["info"].pop(i, None)


def on_select():
    """Callback přepínače smyček."""
    if ss.get("loop_sel") is not None:
        switch(ss["loop_sel"])
    else:  # zrušený výběr v segmented control → zůstat na aktivní
        ss["loop_sel"] = active()


def other_pvs():
    """Sloupce PV ostatních smyček (aby nová smyčka nedostala stejnou PV)."""
    return {info(i).get("c_pv") for i in ids() if i != active()} - {None}


def save_info(ctx, tag_from_pv=""):
    """Souhrn aktivní smyčky na konci běhu (pro přepínač a záložku Kaskáda)."""
    s = _state()
    s["info"][s["active"]] = dict(
        name=(ss.get("loop_tag") or tag_from_pv or "").strip(), c_pv=ctx.c_pv, c_mv=ctx.c_mv, c_sp=ctx.c_sp,
        c_d=list(ctx.c_d),
        model=ctx.model, set1=ctx.set1_ctrl, set2=ctx.set2_ctrl, samp=ctx.samp,
        pv_rng=(ctx.pv_lo, ctx.pv_hi), mv_rng=(ctx.mv_lo, ctx.mv_hi), u_pv=ctx.u_pv, u_mv=ctx.u_mv)


def model_of(i):
    """Model smyčky (kód, parametry v %, parametry poruch) – ze souhrnu, u dosud nenavštívené smyčky ze snímku."""
    m = info(i).get("model")
    if m is not None:
        return m
    snap = snapshot() if i == active() else _state()["snap"].get(i, {})
    fit, code = snap.get("fit"), snap.get("mcode")
    if not fit or code not in fit.get("res", {}):
        return None
    r = fit["res"][code]
    return (code, [float(snap.get(f"ed|{code}|{k}", v)) for k, v in enumerate(r["p"])],
            [[float(snap.get(f"ed|{code}|d{j}|{k}", v)) for k, v in enumerate(d)] for j, d in enumerate(r["pdl"])])


def loop_data(i, fname):
    """
    Co potřebují struktury APC a report o smyčce i: název, model, FIT, úsek dat, sloupce PV/MV/SP a měřených poruch,
    rozsahy PV/MV a parametry regulátoru (sada 2 = ctrl, sada 1 = ctrl1). U navštívené smyčky ze souhrnu,
    jinak ze snímku (např. hned po načtení projektu).
    """
    inf = info(i)
    snap = snapshot() if i == active() else _state()["snap"].get(i, {})
    g = snap.get
    ti = g("set2_ti", 100.0)
    ctrl = inf.get("set2") or dict(Gain=g("set2_gain", 1.0), TI=ti if ti and ti > 0 else np.inf, TD=g("set2_td", 0.0),
                                   DiffGain=g("diffgain", 5.0), SampleTime=g("samp", 1.0), PropFbk=g("pfb", False),
                                   DiffFbk=g("dfb", True), MV_Lo=0.0, MV_Hi=100.0)
    ti1 = g("set1_ti", 100.0)
    ctrl1 = inf.get("set1") or dict(ctrl, Gain=g("set1_gain", 1.0), TI=ti1 if ti1 and ti1 > 0 else np.inf,
                                    TD=g("set1_td", 0.0))
    fit = g("fit") or {}
    code = g("mcode")
    fit_pct = fit.get("res", {}).get(code, {}).get("fit") if code else None
    rng = next((tuple(v) for k, v in snap.items() if str(k).startswith(f"rng_id|{fname}|")), None)
    return dict(name=name(i), model=model_of(i), ctrl=ctrl, ctrl1=ctrl1, fit=fit_pct, rng=rng,
                c_mv=inf.get("c_mv") or g(f"c_mv|{fname}"), c_pv=inf.get("c_pv") or g(f"c_pv|{fname}"),
                c_sp=inf.get("c_sp") or g(f"c_sp|{fname}", "—"),
                c_d=inf.get("c_d") if inf.get("c_d") is not None else list(g(f"c_d|{fname}", []) or []),
                pv_rng=inf.get("pv_rng") or (g("pv_lo", 0.0), g("pv_hi", 100.0)),
                mv_rng=inf.get("mv_rng") or (g("mv_lo", 0.0), g("mv_hi", 100.0)),
                u_pv=inf.get("u_pv", g("u_pv", "")), u_mv=inf.get("u_mv", g("u_mv", "%")))


def all_records():
    """(id, snímek) všech smyček – aktivní z aktuálního session state (pro uložení projektu)."""
    s = _state()
    return [(i, snapshot() if i == s["active"] else s["snap"].get(i, {})) for i in s["ids"]]


def reset(n=1):
    """Výchozí stav s n prázdnými smyčkami (před obnovou projektu); aktivní je první."""
    ss["loops"] = {"ids": list(range(1, n + 1)), "active": 1, "next": n + 1, "snap": {}, "info": {}}
    ss["loop_sel"] = 1
