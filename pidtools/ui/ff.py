"""
Dopředná vazba (feedforward) z měřených poruch – stav sdílený záložkami Ladění a APC.

Nastavení se edituje v APC › Dopředná vazba (klíče widgetů ffuse|j, ffg|j|…, ffdyn|j, fftl|j|…, fftg|j|…, ffdl|j|…);
Ladění z nich jen čte zesílení a lead-lag pro simulace a scénáře. Výchozí návrh: FF = −Kd/K · (T·s + 1)/(Td·s + 1)
· e^−(θd − θ)·s, kde T jsou časové konstanty procesu (MV → PV) a Td, θd model poruchy (porucha → PV); působí-li
porucha rychleji než MV, lag se o chybějící předstih zkrátí (core.apc.ff_design).
Zesílení je v % rozsahu MV na jednotku poruchy (vstup FFwd v PIDConL chce jednotky MV – viz eng_gain).
"""
import streamlit as st

from ..core import ff_gain
from ..core.apc import ff_design

ss = st.session_state


def defaults(code, p, pd):
    """Výchozí návrh pro jednu poruchu: (zesílení, lead, lag, zpoždění) – stejný návrh jako decouplery (ff_design)."""
    d = ff_design(code, p, pd)
    return float(ff_gain(code, p, pd)), float(d["lead"]), float(d["lag"]), float(d["delay"])


def keys(j, code, p, pd):
    """Klíče widgetů poruchy j (výchozí hodnoty jsou součástí klíče → po změně modelu se nabídne nový návrh)."""
    g0, tl0, tg0, dl0 = defaults(code, p, pd)
    return dict(use=f"ffuse|{j}", gain=f"ffg|{j}|{g0:.5g}", dyn=f"ffdyn|{j}", lead=f"fftl|{j}|{tl0:.5g}",
                lag=f"fftg|{j}|{tg0:.5g}", delay=f"ffdl|{j}|{dl0:.5g}")


def _apply_override(code, p, pdl):
    """Nastavení z obnoveného projektu (ss.override_ff) → klíče widgetů."""
    ovf = ss.pop("override_ff", None)
    if not ovf:
        return
    for j, pd in enumerate(pdl):
        if j >= len(ovf):
            break
        o_, k_ = ovf[j], keys(j, code, p, pd)
        g0, tl0, tg0, dl0 = defaults(code, p, pd)
        ss[k_["use"]], ss[k_["gain"]], ss[k_["dyn"]] = bool(o_.get("use")), o_.get("gain", g0), bool(o_.get("dyn"))
        ss[k_["lead"]], ss[k_["lag"]], ss[k_["delay"]] = o_.get("lead", tl0), o_.get("lag", tg0), o_.get("delay", dl0)


def design(code, p, pdl):
    """
    Aktuální nastavení všech poruch: [{use, dyn, gain, lead, lag, delay}] (zesílení v % MV / jedn. poruchy).
    Hodnoty, které uživatel nezměnil, jsou výchozí návrh.
    """
    _apply_override(code, p, pdl)
    out = []
    for j, pd in enumerate(pdl):
        k_ = keys(j, code, p, pd)
        g0, tl0, tg0, dl0 = defaults(code, p, pd)
        out.append(dict(use=bool(ss.get(k_["use"], False)), dyn=bool(ss.get(k_["dyn"], False)),
                        gain=float(ss.get(k_["gain"], g0)), lead=float(ss.get(k_["lead"], tl0)),
                        lag=float(ss.get(k_["lag"], tg0)), delay=float(ss.get(k_["delay"], dl0))))
    return out


def lead_lag(d):
    """(lead, lag, zpoždění) pro simulaci; statická FF = (0, 0, 0). Lag aspoň lead/20 (realizovatelný člen),
    bez leadu i lagu zůstane jen zpoždění."""
    if not d["dyn"]:
        return 0.0, 0.0, 0.0
    lag = max(d["lag"], d["lead"] / 20) if d["lead"] > 0 else d["lag"]
    return (d["lead"], lag, d["delay"]) if lag > 0 else (0.0, 0.0, d["delay"])


def to_ctrl(des, only=None, dyn=None):
    """
    Seznamy FF a FF_LL pro simulaci. only = index jediné použité poruchy (None = podle zapnutí),
    dyn = vynutit statickou (False) / dynamickou (True) variantu (None = podle nastavení).
    """
    ff, ffll = [], []
    for j, d in enumerate(des):
        on = d["use"] if only is None else j == only
        dd = d if dyn is None else dict(d, dyn=dyn)
        ff.append(d["gain"] if on else 0.0)
        ffll.append(lead_lag(dd) if on else (0.0, 0.0, 0.0))
    return ff, ffll


def save_state(des):
    """Stav pro projekt (ss.ff_state)."""
    ss.ff_state = [dict(use=d["use"], gain=d["gain"], dyn=d["dyn"], lead=d["lead"], lag=d["lag"], delay=d["delay"])
                   for d in des]


def eng_gain(gain_pct, mv_range):
    """Zesílení v jednotkách MV na jednotku poruchy (pro vstup FFwd v PIDConL)."""
    return gain_pct * mv_range / 100.0
