"""
Dopředná vazba (feedforward) z měřených poruch: výchozí návrh, nastavení → parametry simulace.

Výchozí návrh: FF = −Kd/K · (T·s + 1)/(Td·s + 1)
· e^−(θd − θ)·s, kde T jsou časové konstanty procesu (MV → PV) a Td, θd model poruchy (porucha → PV); působí-li
porucha rychleji než MV, lag se o chybějící předstih zkrátí (core.apc.ff_design).
Zesílení je v % rozsahu MV na jednotku poruchy (vstup FFwd v PIDConL chce jednotky MV – viz eng_gain).
"""
from ..core import ff_gain
from ..core.apc import ff_design


def defaults(code, p, pd):
    """Výchozí návrh pro jednu poruchu: (zesílení, lead, lag, zpoždění) – stejný návrh jako decouplery (ff_design)."""
    d = ff_design(code, p, pd)
    return float(ff_gain(code, p, pd)), float(d["lead"]), float(d["lag"]), float(d["delay"])


def design(code, p, pdl, settings=None):
    """
    Nastavení všech poruch: [{use, dyn, gain, lead, lag, delay}] (zesílení v % MV / jedn. poruchy).
    settings: uložené nastavení (seznam slovníků, mohou být neúplné); chybějící hodnoty = výchozí návrh, FF vypnutá.
    """
    out = []
    for j, pd in enumerate(pdl):
        o = (settings[j] if settings and j < len(settings) else None) or {}
        g0, tl0, tg0, dl0 = defaults(code, p, pd)
        out.append(dict(use=bool(o.get("use", False)), dyn=bool(o.get("dyn", False)), gain=float(o.get("gain", g0)),
                        lead=float(o.get("lead", tl0)), lag=float(o.get("lag", tg0)), delay=float(o.get("delay", dl0))))
    return out


def state(des):
    """Nastavení pro projekt (seznam slovníků)."""
    return [dict(use=d["use"], gain=d["gain"], dyn=d["dyn"], lead=d["lead"], lag=d["lag"], delay=d["delay"]) for d in des]


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


def eng_gain(gain_pct, mv_range):
    """Zesílení v jednotkách MV na jednotku poruchy (pro vstup FFwd v PIDConL)."""
    return gain_pct * mv_range / 100.0
