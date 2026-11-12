"""
Test použitelnosti regulátoru (R5, docs/cs/regulatory.md § 7): 12 kontrol profilu simulací proti standardním procesům
a celkové hodnocení.

Hodnocení (`verdict`): `suitable` (Vhodný pro ladění – pravidla i optimalizace), `optimisation_only` (Jen optimalizací –
nelineární regulátor nebo mapování na kanonický PID není přesné), `unsuitable` (Nevhodný – selhala kritická kontrola).
Každá kontrola má stav `ok` / `warn` / `fail`, závažnost (`critical` – selhání = Nevhodný, `mapping` – selhání =
Jen optimalizací, `info`) a zprávu jako dvojici (klíč textu `ctl_m_*`, argumenty); texty jsou v i18n (cs, en).
Shodu interpretů Python / JS (kontrola 2) hlídají testy aplikace; zde se ověřuje determinismus Pythonu.
"""
import math
import time

import numpy as np

from .. import core
from ..controllers import canonical_to_profile, profile_to_canonical, validate_profile
from ..core.controller import Controller, Profile, make_profile, nonlinear_parts, preset_profile
from ..core.program import ProgramProfile
from ..core.simulation import pidconl_sim_full

__all__ = ["CHECKS", "run_check"]

TS = 1.0
CANON = dict(Kc=1.5, Ti=20.0, Td=3.0, b=1.0, c=1.0, N=8.0)       # Ti ≥ 4·Td: proveditelné i v sériové formě
REF_PROFILE = "pcs7_pidconl"
# referenční procesy [%/%]: (kód modelu, parametry, popisek); setrvačný, vyvážený, s převahou zpoždění, SOPDT, integrační
PROCESSES = (("P1D", [1.0, 40.0, 2.0], "lag"), ("P1D", [1.0, 10.0, 5.0], "balanced"), ("P1D", [1.0, 2.0, 10.0], "delay"),
             ("P2D", [1.0, 20.0, 5.0, 3.0], "sopdt"), ("I0D", [0.05, 5.0], "integrating"))


def _num(x):
    return float(x) if math.isfinite(x) else 1e12


def _fill(prof, vals, ts=TS, lo=0.0, hi=100.0):
    """Doplní Ts a meze výstupu (podle rolí) a povinné parametry bez hodnoty."""
    vals = dict(vals)
    for p in prof.data["params"]:
        key, role = p["key"], p["role"]
        if role == "Ts":
            vals[key] = ts
        elif role == "mv_lo":
            vals[key] = lo
        elif role == "mv_hi":
            vals[key] = hi
        elif key not in vals and p.get("required"):
            vals[key] = 1.0
    if getattr(prof, "is_program", False):          # program: meze výstupu jsou vstupy MV_LO / MV_HI (klíče jako u PIDConL)
        vals["MV_Lo"], vals["MV_Hi"] = lo, hi
    return vals


def _vals(prof, canon, **kw):
    m = canonical_to_profile(prof.data, canon)
    return _fill(prof, m["values"], **kw), m["warnings"]


def _ref(prof, canon, ts=TS, lo=0.0, hi=100.0):
    """Referenční ideální regulátor (PIDConL) s kanonickými hodnotami `canon`."""
    n = canon["N"]
    c = dict(Gain=canon["Kc"], TI=canon["Ti"] if (canon["Ti"] and math.isfinite(canon["Ti"])) else math.inf,
             TD=canon["Td"], DiffGain=_num(n) if n and n > 0 else 1e12, PropFacSP=canon["b"], DiffFbk=canon["c"] < 0.5,
             SampleTime=ts, MV_Lo=lo, MV_Hi=hi)
    return Controller(preset_profile(REF_PROFILE), c, ts)


def _signal(n=300):
    k = np.arange(n)
    pv = 50 + 3 * np.sin(k / 9.0) + np.where(k > 120, 4.0, 0.0)
    sp = np.where(k < 40, 50.0, 56.0)
    return sp, pv


def _drive(c, sp, pv, u0=50.0):
    c.init(float(sp[0]), float(pv[0]), u0)
    return np.array([c.step(float(s), float(y)) for s, y in zip(sp, pv)])


def _loop(prof, vals, code, p, sp, pv0=50.0, mv0=50.0, h=TS):
    r = pidconl_sim_full(code, p, [], h, sp, pv0, mv0, vals, profile=prof)
    return r["PV"], r["MV"]


def _step_sp(n, k0=10, a=10.0, pv0=50.0):
    sp = np.full(n, pv0)
    sp[k0:] = pv0 + a
    return sp


def _res(status, key, args=None, severity="info", **extra):
    return dict(status=status, severity=severity, msg=[key, args or {}], **extra)


# ================================================================ kontroly
def c_translation(X):
    bad = validate_profile(X["data"])
    if bad:
        return _res("fail", "ctl_m_invalid", dict(problems="; ".join(f"{b['path']} {b['message']}" for b in bad)), "critical")
    prof = X["prof"]
    need = prof.tuning_roles if getattr(prof, "is_program", False) else (*prof.tuning_roles, "Ts")
    missing = [r for r in need if r not in {p["role"] for p in prof.data["params"]}]
    if missing:
        return _res("fail", "ctl_m_missing_roles", dict(roles=", ".join(missing)), "critical")
    if X["nomap"]:
        return _res("warn", "ctl_m_prog_nomap", severity="info")
    if (prof.data.get("verification") or {}).get("status") != "verified":
        return _res("warn", "ctl_m_unverified", severity="info")
    return _res("ok", "ctl_m_ok_translation")


def c_determinism(X):
    sp, pv = _signal()
    a = _drive(Controller(X["prof"], X["vals"], TS), sp, pv)
    b = _drive(Controller(X["prof"], X["vals"], TS), sp, pv)
    if not np.array_equal(a, b) or not np.all(np.isfinite(a)):
        return _res("fail", "ctl_m_det_diff", severity="critical")
    return _res("ok", "ctl_m_det_ok")


def c_rest(X):
    c = Controller(X["prof"], X["vals"], TS)
    c.init(50.0, 50.0, 40.0)
    u = np.array([c.step(50.0, 50.0) for _ in range(300)])
    drift = float(np.max(np.abs(u - 40.0)))
    if not np.all(np.isfinite(u)) or drift > 1e-6:
        return _res("fail", "ctl_m_rest_drift", dict(drift=drift), "critical")
    return _res("ok", "ctl_m_rest_ok")


def _skip(X):
    """Kontrola potřebuje mapování na kanonický PID; program bez `map` / `unmap` ji přeskočí (upozornění)."""
    return _res("warn", "ctl_m_nomap_skip") if X["nomap"] else None


def c_direction(X):
    if _skip(X):
        return _skip(X)
    c = Controller(X["prof"], X["vals"], TS)
    c.init(50.0, 50.0, 50.0)
    u = [c.step(60.0, 50.0) for _ in range(5)]
    if not (u[-1] - 50.0) * CANON["Kc"] > 0:
        return _res("fail", "ctl_m_dir_bad", severity="critical")
    return _res("ok", "ctl_m_dir_ok")


def c_steady(X):
    if _skip(X):
        return _skip(X)
    code, p = "P1D", [1.0, 10.0, 2.0]
    sp = _step_sp(900)
    pv, _ = _loop(X["prof"], X["vals"], code, p, sp)
    e = float(abs(pv[-1] - sp[-1]))
    if CANON["Ti"] <= 0 or not math.isfinite(X["eff"]["Ti"]):
        return _res("warn", "ctl_m_ss_noi", dict(e=e))
    if not math.isfinite(e) or e > 0.05:
        return _res("fail", "ctl_m_ss_bad", dict(e=e), "critical")
    return _res("ok", "ctl_m_ss_ok", dict(e=e))


def c_equivalent(X):
    if X["nomap"]:
        return _res("fail", "ctl_m_prog_nomap", severity="mapping")
    prof, ranges_ok = X["prof"], True
    sp, pv = _signal()
    worst = 0.0
    inexact = []
    points = [CANON]
    if any(p["role"] == "b" for p in prof.data["params"]):
        points.append(dict(CANON, b=0.5))
    if any(p["role"] == "d_on_pv" for p in prof.data["params"]) or prof.data["structure"].get("d", {}).get("source") == "pv":
        points.append(dict(CANON, c=0.0))
    for k, canon in enumerate(points):
        vals, warn = _vals(prof, canon, lo=-1e9, hi=1e9)          # bez nasycení: porovnává se lineární část
        eff = profile_to_canonical(prof.data, vals)
        if k == 0:
            for f in ("Kc", "Ti", "Td"):
                a, b = canon[f], eff[f]
                if abs(a - b) > 1e-9 * max(1.0, abs(a)):
                    ranges_ok = False
            ref = _ref(prof, eff, lo=-1e9, hi=1e9)
            d = np.max(np.abs(_drive(Controller(prof, vals, TS), sp, pv) - _drive(ref, sp, pv)))
            worst = max(worst, float(d))
        else:
            d = np.max(np.abs(_drive(Controller(prof, vals, TS), sp, pv) - _drive(_ref(prof, eff, lo=-1e9, hi=1e9), sp, pv)))
            worst = max(worst, float(d))
        inexact += [w[0] for w in warn]
    if not ranges_ok or worst > 1e-6:
        return _res("fail", "ctl_m_eq_bad", dict(diff=worst), "mapping", diff=worst)
    if inexact:
        return _res("warn", "ctl_m_eq_inexact", dict(warnings=", ".join(sorted(set(inexact)))), "info", diff=worst)
    return _res("ok", "ctl_m_eq_ok", dict(diff=worst), diff=worst)


def _gain_at(prof, vals, amp, period=40):
    """Zesílení regulátoru (|ΔMV| / |ΔPV|) na kmitočtu 2π/period při amplitudě PV `amp` (široké meze výstupu)."""
    c = Controller(prof, vals, TS)
    n = period * 8
    k = np.arange(n)
    y = 50 + amp * np.sin(2 * np.pi * k / period)
    c.init(50.0, 50.0, 50.0)
    u = np.array([c.step(50.0, float(v)) for v in y])
    ks = k[period * 4:]
    s, co = np.sin(2 * np.pi * ks / period), np.cos(2 * np.pi * ks / period)
    uu = u[period * 4:] - u[period * 4:].mean()
    return float(np.hypot(2 * np.mean(uu * s), 2 * np.mean(uu * co))) / amp


def c_linearity(X):
    prof = X["prof"]
    parts = nonlinear_parts(prof)
    if parts:                       # strukturní nelinearity (gap, nelineární zesílení, 3-step / PWM na středním výstupu)
        return _res("fail", "ctl_m_lin_parts", dict(parts=", ".join(parts)), "mapping", parts=parts)
    vals = _fill(prof, X["vals0"], lo=-1e6, hi=1e6)
    dev = 0.0
    for per in (20, 60):
        g1, g2 = _gain_at(prof, vals, 0.3, per), _gain_at(prof, vals, 4.0, per)
        dev = max(dev, abs(g1 - g2) / max(g1, 1e-12))
    if dev > 0.02:
        return _res("fail", "ctl_m_lin_bad", dict(dev=100 * dev), "mapping", dev=dev)
    return _res("ok", "ctl_m_lin_ok", dict(dev=100 * dev), dev=dev)


def c_processes(X):
    if _skip(X):
        return _skip(X)
    prof = X["prof"]
    rows, warn, bad = [], [], []
    for code, p, name in PROCESSES:
        tc = core.default_tc(code, p, TS, "SIMC", "PI", CANON["N"])
        r = core.tune(code, p, "SIMC", tc, "PI", TS)
        canon = dict(CANON, Kc=r["Kc"], Ti=r["Ti"] if r["Ti"] > 0 else math.inf, Td=0.0)
        vals, _ = _vals(prof, canon)
        T = (p[1] if code in ("P1D", "P2D") else 0) + (p[2] if code == "P2D" else 0) + p[-1]
        n = int(min(max(60 * (T + 10), 600), 6000))
        sp = _step_sp(n, 10, 10.0)
        pv, mv = _loop(prof, vals, code, p, sp)
        ok = bool(np.all(np.isfinite(pv))) and float(np.max(np.abs(pv - 50))) < 50
        ovs = 100 * float(max(pv.max() - 60.0, 0.0)) / 10.0 if ok else float("inf")
        tail = float(np.max(np.abs(pv[-n // 10:] - 60.0))) if ok else float("inf")
        rows.append(dict(process=name, overshoot=ovs, tail=tail))
        if not ok or tail > 1.0 or ovs > 60:
            bad.append(name)
        elif ovs > 30:
            warn.append(name)
    if bad:
        return _res("fail", "ctl_m_proc_bad", dict(names=", ".join(bad)), "critical", rows=rows)
    if warn:
        return _res("warn", "ctl_m_proc_warn", dict(names=", ".join(warn)), rows=rows)
    return _res("ok", "ctl_m_proc_ok", dict(n=len(rows)), rows=rows)


def c_antiwindup(X):
    if _skip(X):
        return _skip(X)
    prof = X["prof"]
    code, p = "P1D", [1.0, 10.0, 2.0]
    n = 700
    sp = np.full(n, 50.0)
    sp[10:200] = 90.0                         # nedosažitelné (MV je omezené na 60 %)
    sp[200:] = 55.0
    vals = _fill(prof, X["vals0"], hi=60.0)
    pv, _ = _loop(prof, vals, code, p, sp)
    # referenční chování: totéž s PIDConL (podmíněná integrace)
    rc = dict(Gain=X["eff"]["Kc"], TI=X["eff"]["Ti"], TD=X["eff"]["Td"], DiffGain=_num(X["eff"]["N"]), SampleTime=TS,
              MV_Lo=0.0, MV_Hi=60.0, PropFacSP=X["eff"]["b"], DiffFbk=X["eff"]["c"] < 0.5)
    pv_r, _ = _loop(preset_profile(REF_PROFILE), rc, code, p, sp)
    dev = float(np.max(np.abs(pv[260:] - 55.0)))
    dev_r = float(np.max(np.abs(pv_r[260:] - 55.0)))
    if not np.all(np.isfinite(pv)) or dev > 2 * dev_r + 3.0:
        return _res("fail", "ctl_m_aw_bad", dict(dev=dev, ref=dev_r), "critical")
    return _res("ok", "ctl_m_aw_ok", dict(dev=dev, ref=dev_r))


def c_switching(X):
    c = Controller(X["prof"], X["vals"], TS)
    c.init(50.0, 50.0, 50.0)
    for k in range(30):
        last = c.track(50.0 + 0.1 * k, 50.0 + 0.1 * k, 70.0)       # u_man; s výstupním stupněm jeho ekvivalent
    jump = abs(c.step(52.9, 52.9) - last)
    if not math.isfinite(jump) or jump > 1.0:
        return _res("fail", "ctl_m_sw_bad", dict(jump=jump), "critical")
    return _res("ok", "ctl_m_sw_ok", dict(jump=jump))


def c_numerics(X):
    prof = X["prof"]

    def vals_for(canon, **kw):
        return _fill(prof, X["vals0"], **kw) if X["nomap"] else _vals(prof, canon, **kw)[0]
    rng = np.random.default_rng(1)
    problems = []
    for ts in (0.1, 1.0, 10.0):
        for scale in (1.0, 1e6):
            vals = vals_for(CANON, ts=ts, lo=-1e12, hi=1e12)
            try:
                c = Controller(prof, vals, ts)
                c.init(50.0, 50.0, 50.0)
                u = [c.step(50.0 + scale * rng.normal(), 50.0 + scale * rng.normal()) for _ in range(200)]
                if not np.all(np.isfinite(u)):
                    problems.append(f"Ts={ts}, ×{scale:g}")
            except Exception as ex:                # noqa: BLE001 – kontrola hlásí jakoukoli chybu
                problems.append(f"Ts={ts}: {type(ex).__name__}")
    for canon in (dict(CANON, Ti=1e-6), dict(CANON, Td=1e6), dict(CANON, Ti=math.inf, Td=0.0), dict(CANON, Kc=-1.5)):
        try:
            vals = vals_for(canon)
            c = Controller(prof, vals, TS)
            c.init(50.0, 50.0, 50.0)
            u = [c.step(60.0, 50.0) for _ in range(50)]
            if not np.all(np.isfinite(u)):
                problems.append("extrém")
        except Exception as ex:                    # noqa: BLE001
            problems.append(f"extrém: {type(ex).__name__}")
    if problems:
        return _res("fail", "ctl_m_num_bad", dict(detail="; ".join(problems[:4])), "critical")
    return _res("ok", "ctl_m_num_ok")


def c_performance(X):
    c = Controller(X["prof"], X["vals"], TS)
    c.init(50.0, 50.0, 50.0)
    n = 20000
    ys = (50 + np.sin(np.arange(n) / 50.0)).tolist()
    t0 = time.perf_counter()
    for y in ys:
        c.step(50.0, y)
    us = (time.perf_counter() - t0) / n * 1e6
    if us > 50:
        return _res("warn", "ctl_m_perf_slow", dict(us=us), us=us)
    return _res("ok", "ctl_m_perf_ok", dict(us=us), us=us)


CHECKS = (("translation", c_translation), ("determinism", c_determinism), ("rest", c_rest), ("direction", c_direction),
          ("steady", c_steady), ("equivalent", c_equivalent), ("linearity", c_linearity), ("processes", c_processes),
          ("antiwindup", c_antiwindup), ("switching", c_switching), ("numerics", c_numerics),
          ("performance", c_performance))


def run_check(profile, only=None):
    """
    Test použitelnosti profilu (dict nebo `Profile`). Vrací dict(verdict, checks=[{id, status, severity, msg}],
    reasons=[id selhaných kontrol]). `only` = seznam id kontrol (rychlý běh); bez něj všech 12.
    """
    data = profile.data if isinstance(profile, (Profile, ProgramProfile)) else profile
    out = []
    try:
        prof = make_profile(profile)
        data = prof.data
        try:
            vals0, _ = _vals(prof, CANON)
            X = dict(data=data, prof=prof, vals=vals0, vals0=vals0, eff=profile_to_canonical(data, vals0), nomap=False)
        except ValueError:
            if not getattr(prof, "is_program", False):
                raise
            vals0 = _fill(prof, {})                 # program bez mapování: parametry s výchozími hodnotami
            X = dict(data=data, prof=prof, vals=vals0, vals0=vals0, eff=None, nomap=True)
        compile_err = None
    except Exception as ex:                         # noqa: BLE001 – neplatný profil: jen kontrola 1 s hláškou
        X, compile_err = dict(data=data), ex
    for cid, fn in CHECKS:
        if only and cid not in only:
            continue
        if compile_err is not None and cid != "translation":
            r = _res("fail", "ctl_m_skipped", severity="critical")
        elif compile_err is not None:
            r = _res("fail", "ctl_m_invalid", dict(problems=str(compile_err)), "critical")
        else:
            try:
                r = fn(X)
            except Exception as ex:                 # noqa: BLE001
                r = _res("fail", "ctl_m_error", dict(error=f"{type(ex).__name__}: {ex}"), "critical")
        out.append(dict(r, id=cid))
    bad = [c for c in out if c["status"] == "fail"]
    if any(c["severity"] == "critical" for c in bad):
        verdict = "unsuitable"
    elif bad:
        verdict = "optimisation_only"
    else:
        verdict = "suitable"
    return dict(verdict=verdict, checks=out, reasons=[c["id"] for c in bad])
