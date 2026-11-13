"""
Mapování kanonického PID na parametry profilu a zpět (docs/cs/regulatory.md § 6): čisté funkce nad slovníkem profilu.

Kanonický PID: ideální 2DOF `Kc, Ti, Td, b, c, N` (Ti = inf / None = bez I; c = 1 D z odchylky, 0 D z PV; N = ∞ bez
filtru). Profil určuje formu (ideální / paralelní / sériová), zdroj a filtr D, váhu b a převody jednotek (`units`).
`canonical_to_profile` vrací hodnoty podle klíčů parametrů bloku a varování (klíč textu `ctl_w_*`, argumenty);
`profile_to_canonical` je obrácený směr. Rozdíl obou je u přesných mapování nulový (round-trip), u nepřesných
(sériová forma pro Ti < 4·Td, chybějící váha b, filtr, D jen z PV) dostaneme nejbližší proveditelný návrh a varování.
"""
import math

from . import units

__all__ = ["KINDS", "apply_reprs", "canonical_to_profile", "native_to_ideal", "profile_to_canonical"]

INF = math.inf
N_MAX = 1000.0
KINDS = {"Kc": "gain", "Kp": "gain", "Ti": "integral", "Td": "derivative", "N": "filter"}   # role → veličina
_DEFAULT_REPR = {"gain": "K", "integral": "s", "derivative": "s", "filter": "N"}


def _inf(x):
    return INF if (x is None or not x or x <= 0 or not math.isfinite(x)) else float(x)


# ---------------------------------------------------------------- formy (nativní trojice ↔ ideální Kc, Ti, Td)
def native_to_ideal(form, a, b, c):
    """Nativní trojice formy (ideální Kc, Ti, Td | paralelní Kp, Ki, Kd | sériová Kc, Ti, Td) → ideální (Kc, Ti, Td)."""
    if form == "ideal":
        return a, _inf(b), c
    if form == "parallel":
        return a, (a / b if b and b > 0 else INF), (c / a if a else 0.0)
    if form == "series":
        ti = _inf(b)
        return (a, ti, c) if not math.isfinite(ti) else (a * (1 + c / ti), ti + c, ti * c / (ti + c) if ti + c else 0.0)
    raise ValueError(f"unknown form '{form}'")


def ideal_to_native(form, kc, ti, td):
    """Ideální (Kc, Ti, Td) → nativní trojice formy a varování (u sériové s Ti < 4·Td: nejbližší proveditelná)."""
    ti = _inf(ti)
    warn = []
    if form == "ideal":
        return (kc, ti, td), warn
    if form == "parallel":
        return (kc, kc / ti if math.isfinite(ti) else 0.0, kc * td), warn
    if form == "series":
        if not math.isfinite(ti) or td <= 0:
            return (kc, ti, td), warn
        if ti < 4 * td:
            warn.append(("ctl_w_series_limit", dict(Ti=ti, Td=td, Td_max=ti / 4)))
            td = ti / 4
        s = math.sqrt(max(1 - 4 * td / ti, 0.0))
        ti_s, td_s = ti * (1 + s) / 2, ti * (1 - s) / 2
        return (kc * (1 + s) / 2, ti_s, td_s), warn
    raise ValueError(f"unknown form '{form}'")


# ---------------------------------------------------------------- jednotky parametrů profilu
def _params(profile):
    return profile["params"]


def role_reprs(profile):
    """{role: varianta} pro parametry s jinou než kanonickou jednotkou (pole `repr` v profilu)."""
    return {p["role"]: p["repr"] for p in _params(profile) if p.get("repr") and p["role"] in KINDS
            and p["repr"] != _DEFAULT_REPR[KINDS[p["role"]]]}


def apply_reprs(vals, reprs, ranges=None, direction="to_canon"):
    """
    Převede hodnoty podle rolí (`vals`: role → hodnota) mezi zobrazením a nativním tvarem profilu. Pořadí: zesílení,
    Td, Ti, filtr (Ki, Kd, Tf závisí na K, Td). `ranges` = {"pv_range": (lo, hi), "mv_range": (lo, hi)}.
    """
    if not reprs:
        return dict(vals)
    fn = units.to_canon if direction == "to_canon" else units.from_canon
    out = dict(vals)
    ctx = dict(ranges or {})
    for role in ("Kc", "Kp", "Td", "Ti", "N"):
        if role not in vals or vals[role] is None:
            continue
        if role in reprs:
            rep = reprs[role]
            out[role] = fn(KINDS[role], rep, vals[role], ctx)
        # kontext pro závislé veličiny: nativní (kanonická) hodnota
        nat = out[role] if direction == "to_canon" else vals[role]
        if role in ("Kc", "Kp"):
            ctx["K"] = nat if nat is not None else None
        elif role == "Td":
            ctx["Td"] = nat
    return out


# ---------------------------------------------------------------- mapování
def _structure(profile):
    st = profile["structure"]
    d = st.get("d", {})
    return st.get("form", "ideal"), d.get("source", "error"), d.get("filter", "td_over_n")


def _roles(profile):
    return {p["role"]: p for p in _params(profile)}


def canonical_to_profile(profile, canon, ranges=None):
    """
    Kanonický PID {Kc, Ti, Td, b, c, N} → hodnoty parametrů profilu {klíč: hodnota} (v jednotkách profilu) a
    varování [(klíč textu, argumenty)]. `ranges`: pv_range / mv_range pro zesílení v inženýrských jednotkách.
    """
    if profile.get("kind") == "program":
        from . import program as prg
        return dict(values=prg.canonical_to_program(profile["program"], canon), warnings=[])
    form, dsrc, dfil = _structure(profile)
    roles = _roles(profile)
    warn = []
    kc, ti, td = float(canon["Kc"]), _inf(canon.get("Ti")), float(canon.get("Td", 0.0) or 0.0)
    b, c, n = float(canon.get("b", 1.0)), float(canon.get("c", 1.0)), canon.get("N", 5.0)
    (a1, a2, a3), w = ideal_to_native(form, kc, ti, td)
    warn += w
    if form == "series" and w:
        td = ti / 4
    names = ("Kp", "Ki", "Kd") if form == "parallel" else ("Kc", "Ti", "Td")
    native = dict(zip(names, (a1, a2, a3)))
    # filtr D
    if dfil == "td_over_n":
        if "N" in roles:
            native["N"] = float(n) if (n is not None and math.isfinite(n)) else N_MAX      # ∞ = prakticky bez filtru
    elif dfil == "fixed":
        if "Tf" in roles:
            native["Tf"] = (td / n if (n and math.isfinite(n) and n > 0) else 0.0) if td > 0 else 0.0
    elif td > 0 and n is not None and math.isfinite(n):
        warn.append(("ctl_w_no_filter", dict(N=n)))
    # váha b
    if "b" in roles:
        native["b"] = min(max(b, 0.0), 1.0)
    elif abs(b - 1.0) > 1e-9:
        warn.append(("ctl_w_fixed_b", dict(b=b)))
    # zdroj D (c)
    if "d_on_pv" in roles and dsrc == "error_or_pv":
        native["d_on_pv"] = c < 0.5
        if min(abs(c), abs(c - 1)) > 1e-9:
            warn.append(("ctl_w_c_binary", dict(c=c)))
    else:
        fixed_c = 0.0 if dsrc == "pv" else 1.0
        if td > 0 and abs(c - fixed_c) > 1e-9:
            warn.append(("ctl_w_fixed_c", dict(c=c, fixed=fixed_c)))
    disp = apply_reprs({k: v for k, v in native.items()}, role_reprs(profile), ranges, "from_canon")
    values = {roles[r]["key"]: v for r, v in disp.items() if r in roles}
    return dict(values=values, warnings=warn)


def profile_to_canonical(profile, values, ranges=None):
    """Hodnoty parametrů profilu {klíč: hodnota} (chybějící = výchozí z profilu) → kanonický PID {Kc, Ti, Td, b, c, N}."""
    if profile.get("kind") == "program":
        from . import program as prg
        return prg.program_to_canonical(profile["program"], values)
    form, dsrc, dfil = _structure(profile)
    by_role = {}
    for p in _params(profile):
        v = values.get(p["key"], p.get("default"))
        by_role[p["role"]] = INF if v == "inf" else v
    nat = apply_reprs(by_role, role_reprs(profile), ranges, "to_canon")
    names = ("Kp", "Ki", "Kd") if form == "parallel" else ("Kc", "Ti", "Td")
    kc, ti, td = native_to_ideal(form, nat.get(names[0], 0.0), nat.get(names[1]), nat.get(names[2], 0.0))
    if dfil == "td_over_n":
        n = nat.get("N", 5.0)
    elif dfil == "fixed":
        tf = by_role.get("Tf") or 0.0
        n = td / tf if (tf and td > 0) else INF
    else:
        n = INF
    b = by_role.get("b", 1.0)
    b = 1.0 if b is None else b
    if dsrc == "pv" or (dsrc == "error_or_pv" and by_role.get("d_on_pv")):
        c = 0.0
    else:
        c = 1.0
    return dict(Kc=kc, Ti=ti, Td=td, b=b, c=c, N=n)
