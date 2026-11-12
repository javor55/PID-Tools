"""
Ladění s obecným regulátorem (R2, docs/cs/regulatory.md § 6): pravidla i optimalizace počítají v kanonickém ideálním
2DOF PID (Kc, Ti, Td, b, c, N); výsledek se převede na parametry a jednotky profilu a zpět.

Omezení: optimalizace pracuje nad kanonickými hodnotami a převádí se až výsledek (ne přímo nad parametry profilu);
tam, kde profil kanonický tvar nepokrývá přesně (sériová forma pro Ti < 4·Td, chybějící váha b, filtr D, D jen z PV),
vrací převod nejbližší proveditelný návrh, varování a robustnost skutečně použitelné sady (`Ms_mapped`).
U nelineárních profilů (R3: gap, nelineární zesílení, 3-step, PWM) se robustnost počítá na linearizované části a návrh
má příznak `approximate`; pravidla pak dávají jen výchozí bod a rozhoduje simulace / optimalizace.
"""
import json
import math
from functools import lru_cache

from .. import core
from ..controllers import canonical_to_profile, load_preset, profile_to_canonical
from ..core.controller import make_profile, nonlinear_parts
from .tuning import suggest

__all__ = ["block_params", "canon_of_ctrl", "canonical_ctrl", "compiled", "loop_ctrl", "profile_robustness", "profile_robustness_fn",
           "profile_values", "suggest_for_profile", "to_canonical", "tuning_params", "DEFAULT_ID"]

DEFAULT_ID = "pcs7_pidconl"
# role bloku → klíč konfigurace PIDConL (app.loop.block_ctrl); parametry profilu těchto rolí se doplní do simulace
_BLOCK_ROLES = dict(Ts="SampleTime", deadband="DeadBand", deadband_mode="DbMode", mv_lo="MV_Lo", mv_hi="MV_Hi",
                    pv_filter="PVFilt", mv_rate="MVRate", sp_rate="SPRate")
_PIDCONL_KEYS = {"Gain", "TI", "TD", "DiffGain", "PropFacSP", "DiffFbk", "SampleTime", "DeadBand", "DbMode", "MV_Lo",
                 "MV_Hi", "PVFilt", "MVRate", "SPRate", "ConZone"}


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
    v jeho jednotkách), `profile_warnings`, `Ms_mapped` (robustnost sady po převodu na profil a zpět) a `approximate`
    (nelineární profil: Ms z linearizované části).
    """
    r = suggest(code, p, pdl, base_ctrl, req, **kw)
    m = profile_values(profile, r, base_ctrl.get("DiffGain", 5.0), ranges)
    ctrl = canonical_ctrl(profile, base_ctrl, m["values"], ranges)
    rb = core.robustness(code, p, ctrl)
    return dict(r, profile=m["values"], profile_warnings=m["warnings"], Ms_mapped=rb["Ms"] if rb["stable"] else None,
                effective=m["effective"], approximate=bool(nonlinear_parts(profile)))


def profile_robustness(profile, code, p, values, base=None, ranges=None):
    """Robustnost (Ms, GM, PM, stabilita) smyčky s regulátorem daného profilu a hodnotami jeho parametrů."""
    ctrl = dict(base or {}, **values, _ranges=ranges)
    return core.robustness_for(profile)(code, p, ctrl)



def profile_data(profile):
    """Profil smyčky jako dict (None = výchozí PIDConL)."""
    return profile or load_preset(DEFAULT_ID)


@lru_cache(maxsize=16)
def _compiled(text):
    return make_profile(json.loads(text))


def compiled(profile):
    """Přeložený profil (s pamětí – překlad se pro stejný obsah nedělá znovu)."""
    return _compiled(json.dumps(profile_data(profile), sort_keys=True))


def tuning_params(profile):
    """Parametry profilu, které tvoří sadu ladění (Gain / TI / TD u PIDConL; Kp / Ki / Kd u paralelní formy …)."""
    roles = set(compiled(profile).tuning_roles)
    return [p for p in profile_data(profile)["params"] if p["role"] in roles]


def block_params(profile):
    """Ostatní parametry profilu = nastavení bloku (vzorkování, meze, filtry, rychlosti, mrtvé pásmo …)."""
    roles = set(compiled(profile).tuning_roles)
    return [p for p in profile_data(profile)["params"] if p["role"] not in roles]


def canon_of_ctrl(ctrl):
    """Konfigurace PIDConL (Gain, TI, TD, DiffGain, PropFacSP, DiffFbk) → kanonický PID {Kc, Ti, Td, b, c, N}."""
    ti = ctrl.get("TI")
    return dict(Kc=ctrl["Gain"], Ti=ti if ti and ti > 0 else math.inf, Td=ctrl["TD"], b=ctrl.get("PropFacSP", 1.0),
                c=0.0 if ctrl.get("DiffFbk", True) else 1.0, N=ctrl.get("DiffGain", 5.0))


def loop_ctrl(profile, ctrl, ranges=None):
    """
    Konfigurace PIDConL (sada + blok + prvky simulace) → slovník v názvech parametrů profilu pro `Controller`
    (`pidconl_sim_full(..., profile=)`, `profile_robustness`). Ladění se převede přes mapování, ostatní role bloku
    (vzorkování, meze, filtr PV, rychlosti, mrtvé pásmo) se doplní podle klíčů profilu; klíče mimo blok (FF, Stic,
    ValveChar, Noise …) se předají beze změny.
    """
    data = profile_data(profile)
    out = dict(canonical_to_profile(data, canon_of_ctrl(ctrl), ranges)["values"])
    for p in data["params"]:
        src = _BLOCK_ROLES.get(p["role"])
        if p["key"] not in out and src in ctrl:
            out[p["key"]] = ctrl[src]
    out.update({k: v for k, v in ctrl.items() if k not in _PIDCONL_KEYS})
    if ranges:
        out["_ranges"] = ranges
    return out


def profile_robustness_fn(profile):
    """`robustness_fn(code, p, ctrl)` pro `app.tuning.set_metrics`: ctrl v názvech parametrů profilu."""
    return core.robustness_for(profile_data(profile))
