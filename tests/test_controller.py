"""Obecný regulátor (core.controller) a profily (pidtools.controllers): načtení, formy, anti-windup, registry, rychlost."""
import copy
import json
import time

import numpy as np
import pytest

from pidtools import controllers
from pidtools.core import PIDConL
from pidtools.core.controller import REGISTRIES, Controller, Profile, controller_from_preset, preset_profile

BASE = dict(Gain=1.2, TI=30.0, TD=4.0, DiffGain=5.0, SampleTime=1.0, MV_Lo=0.0, MV_Hi=100.0)


def _prof(**structure):
    p = copy.deepcopy(controllers.load_preset("pcs7_pidconl"))
    p["structure"].update(structure)
    return p


def _drive(c, n=300, sp_step=60.0):
    c.init(50.0, 50.0, 50.0)
    return np.array([c.step(50.0 if k < 20 else sp_step, 50.0 + 3 * np.sin(k / 9.0)) for k in range(n)])


# ---- profil a načtení
def test_preset_loads_with_format_and_version():
    p = controllers.load_preset("pcs7_pidconl")
    assert p["format"] == controllers.FORMAT == "pidctrl" and p["version"] == controllers.VERSION == 1
    assert "pcs7_pidconl" in controllers.presets()
    assert p["verification"]["status"] == "unverified"          # předvolba bez ověření proti manuálu je označená
    json.dumps(p)                                              # čistý JSON (stejný soubor čte i ctrl_engine.js)


@pytest.mark.parametrize("bad,msg", [
    ({"format": "x", "version": 1}, "není profil"),
    ({"format": "pidctrl", "version": 99, "id": "a", "structure": {}, "params": []}, "novější"),
    ({"format": "pidctrl", "version": 0, "id": "a", "structure": {}, "params": []}, "verzi"),
    ({"format": "pidctrl", "version": 1, "id": "a", "structure": {}}, "params"),
])
def test_profile_validation(bad, msg):
    with pytest.raises(ValueError, match=msg):
        controllers.parse_profile(bad)


def test_unique_roles_required():
    p = _prof()
    p["params"].append(dict(p["params"][0], key="Gain2"))
    with pytest.raises(ValueError, match="jedinečné"):
        controllers.parse_profile(p)


def test_pidconl_is_thin_wrapper():
    c = PIDConL(BASE, 0.5)
    assert isinstance(c, Controller) and c.profile is preset_profile("pcs7_pidconl")
    assert c.m == 2 and c.Tc == 1.0
    with pytest.raises(KeyError):
        PIDConL(dict(BASE, Gain=None), 1.0)
    with pytest.raises(KeyError):
        PIDConL({k: v for k, v in BASE.items() if k != "SampleTime"}, 1.0)
    # starý klíč PropFbk (P jen z PV) odpovídá PropFacSP = 0
    a, b = PIDConL(dict(BASE, PropFbk=True), 1.0), PIDConL(dict(BASE, PropFacSP=0.0), 1.0)
    assert np.allclose(_drive(a), _drive(b))
    # TI = None / inf = bez I složky
    assert not PIDConL(dict(BASE, TI=None), 1.0).use_i and not PIDConL(dict(BASE, TI=np.inf), 1.0).use_i


def test_unknown_deadband_mode_acts_as_step():
    a = PIDConL(dict(BASE, DeadBand=2.0, DbMode="cokoli"), 1.0)
    b = PIDConL(dict(BASE, DeadBand=2.0, DbMode="skokové"), 1.0)
    assert np.array_equal(_drive(a), _drive(b))


# ---- formy
def test_parallel_form_equals_ideal():
    ideal = Controller(_prof(), BASE, 1.0)
    p = _prof(form="parallel")
    p["params"] = [x for x in p["params"] if x["key"] not in ("Gain", "TI", "TD")] + [
        {"key": "Kp", "role": "Kp", "required": True}, {"key": "Ki", "role": "Ki", "required": True, "nullable": True},
        {"key": "Kd", "role": "Kd", "required": True}]
    par = Controller(p, dict(BASE, Kp=1.2, Ki=1.2 / 30.0, Kd=1.2 * 4.0), 1.0)
    assert np.allclose(_drive(ideal), _drive(par), atol=1e-12)
    assert par.Td == pytest.approx(4.0) and par.Ti == pytest.approx(30.0)


def test_series_form_converts_to_ideal():
    Kc, Ti, Td = 1.2, 30.0, 4.0
    ser = Controller(_prof(form="series"), dict(BASE, Gain=Kc, TI=Ti, TD=Td), 1.0)
    assert ser.Kc == pytest.approx(Kc * (1 + Td / Ti)) and ser.Ti == pytest.approx(Ti + Td)
    assert ser.Td == pytest.approx(Ti * Td / (Ti + Td))


# ---- anti-windup
def _saturated_I(aw):
    p = _prof(antiwindup=aw)
    p["params"] = p["params"] + [dict(key="Tt", role="Tt", default=10.0)]
    c = Controller(p, dict(BASE, MV_Lo=40.0, MV_Hi=60.0, TD=0.0), 1.0)
    c.init(50.0, 50.0, 50.0)
    for _ in range(2000):
        c.step(80.0, 50.0)                                     # trvalá odchylka 30 % → výstup na mezi
    return c.I


def test_antiwindup_variants():
    I_clamp, I_bc, I_none = _saturated_I("clamp_conditional"), _saturated_I("back_calculation"), _saturated_I("none")
    assert I_none > 10 * abs(I_clamp)                         # bez ochrany integrál roste donekonečna
    assert abs(I_clamp) < 100 and abs(I_bc) < 100               # obě ochrany ho drží omezený


# ---- registry
def test_registries_and_planned_items():
    assert {"ideal", "parallel", "series"} <= set(REGISTRIES["forms"].items)
    with pytest.raises(ValueError, match="neznámá položka"):
        Profile(_prof(form="nesmysl"))
    with pytest.raises(NotImplementedError, match="engineering"):
        Profile(_prof(normalisation={"kind": "engineering"}))


def test_controller_from_preset():
    a = controller_from_preset("pcs7_pidconl", BASE, 1.0)
    assert np.array_equal(_drive(a), _drive(PIDConL(BASE, 1.0)))


# ---- rychlost kroku (cíl < 2 µs; jen se vypíše, test na čas nepadá)
@pytest.mark.parametrize("name,extra", [("PID", {}), ("vše zapnuto", dict(
    PropFacSP=0.5, DeadBand=0.2, DbMode="spojité", PVFilt=2.0, MVRate=2.0, SPRate=1.0, DiffFbk=True, ConZone=30.0))])
def test_step_benchmark(name, extra, capsys, record_property):
    c = PIDConL(dict(BASE, **extra), 1.0)
    c.init(50.0, 50.0, 50.0)
    n = 100000
    ys = (50 + np.sin(np.arange(n) / 50.0)).tolist()
    best = 1e9
    for _ in range(3):
        t0 = time.perf_counter()
        for y in ys:
            c.step(50.0, y, 0.0)
        best = min(best, (time.perf_counter() - t0) / n * 1e6)
    record_property("step_us", round(best, 3))
    with capsys.disabled():
        print(f"\n[benchmark] PIDConL.step ({name}): {best:.2f} µs/krok (cíl < 2 µs)")
    assert best < 50          # jen hrubá pojistka proti omylu, ne měřítko výkonu
