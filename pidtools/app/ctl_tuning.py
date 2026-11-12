"""
Ladění s obecným regulátorem (R2, docs/cs/regulatory.md § 6): pravidla i optimalizace počítají v kanonickém ideálním
2DOF PID (Kc, Ti, Td, b, c, N); výsledek se převede na parametry a jednotky profilu a zpět.

Omezení: optimalizace pracuje nad kanonickými hodnotami a převádí se až výsledek (ne přímo nad parametry profilu);
tam, kde profil kanonický tvar nepokrývá přesně (sériová forma pro Ti < 4·Td, chybějící váha b, filtr D, D jen z PV),
vrací převod nejbližší proveditelný návrh, varování a robustnost skutečně použitelné sady (`Ms_mapped`).
Přímá optimalizace nad parametry profilu (nelineární regulátory) přijde s dalšími funkcemi profilu (R3).
"""
import math

from .. import core
from ..controllers import canonical_to_profile, profile_to_canonical
from .tuning import suggest

__all__ = ["canonical_ctrl", "profile_robustness", "profile_values", "suggest_for_profile", "to_canonical"]


def profile_values(profile, rule, n=5.0, ranges=None):
    """
    Kanonický návrh `rule` (Kc, Ti, Td, volitelně b, c, N) → {"values": {klíč: hodnota}, "warnings": [(klíč, args)],
    "effective": kanonické hodnoty, které sada profilu skutečně realizuje}.
    """
    canon = dict(Kc=rule["Kc"], Ti=rule["Ti"] if rule["Ti"] and rule["Ti"] > 0 else math.inf, Td=rule.get("Td", 0.0),
                 b=rule.get("b", 1.0), c=rule.get("c", 1.0), N=rule.get("N", n))
    m = canonical_to_profile(profile, canon, ranges)
    return dict(m, effective=profile_to_canonical(profile, m["values"], ranges))


def to_canonical(profile, values, ranges=None):
    """Hodnoty parametrů profilu {klíč: hodnota} → kanonický PID {Kc, Ti, Td, b, c, N} (např. sada 1 z PLC)."""
    return profile_to_canonical(profile, values, ranges)


def canonical_ctrl(profile, base, values, ranges=None):
    """Konfigurace pro analýzu / simulaci v názvech PIDConL (Gain, TI, TD, DiffGain …) z hodnot parametrů profilu."""
    eff = profile_to_canonical(profile, values, ranges)
    return dict(base, Gain=eff["Kc"], TI=eff["Ti"], TD=eff["Td"], DiffGain=eff["N"] if math.isfinite(eff["N"]) else 1e12,
                PropFacSP=eff["b"], DiffFbk=eff["c"] < 0.5)


def suggest_for_profile(code, p, pdl, base_ctrl, req, profile, ranges=None, **kw):
    """
    Návrh jako `app.tuning.suggest` (kanonický Kc, Ti, Td, notes) rozšířený o `profile` (hodnoty parametrů profilu
    v jeho jednotkách), `profile_warnings` a `Ms_mapped` (robustnost sady po převodu na profil a zpět).
    """
    r = suggest(code, p, pdl, base_ctrl, req, **kw)
    m = profile_values(profile, r, base_ctrl.get("DiffGain", 5.0), ranges)
    ctrl = canonical_ctrl(profile, base_ctrl, m["values"], ranges)
    rb = core.robustness(code, p, ctrl)
    return dict(r, profile=m["values"], profile_warnings=m["warnings"], Ms_mapped=rb["Ms"] if rb["stable"] else None,
                effective=m["effective"])


def profile_robustness(profile, code, p, values, base=None, ranges=None):
    """Robustnost (Ms, GM, PM, stabilita) smyčky s regulátorem daného profilu a hodnotami jeho parametrů."""
    ctrl = dict(base or {}, **values, _ranges=ranges)
    return core.robustness_for(profile)(code, p, ctrl)

