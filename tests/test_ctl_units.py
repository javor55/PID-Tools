"""Jednotky parametrů a mapování kanonického PID na profil (controllers.units / controllers.mapping)."""
import copy
import math

import numpy as np
import pytest

from pidtools import controllers
from pidtools.controllers import units
from pidtools.core.controller import Controller, Profile

CTX = dict(K=2.5, Td=12.0, pv_range=(0.0, 200.0), mv_range=(0.0, 100.0))


@pytest.mark.parametrize("kind,rep,v", [
    ("gain", "K", 2.5), ("gain", "PB", 2.5), ("gain", "K_eng", 2.5),
    ("integral", "s", 30.0), ("integral", "min", 30.0), ("integral", "ms", 30.0), ("integral", "rep_min", 30.0),
    ("integral", "s_rep", 30.0), ("integral", "Ki", 30.0), ("integral", "Ki_min", 30.0),
    ("derivative", "s", 4.0), ("derivative", "min", 4.0), ("derivative", "ms", 4.0), ("derivative", "Kd", 4.0),
    ("filter", "N", 8.0), ("filter", "inv_N", 8.0), ("filter", "alpha", 8.0), ("filter", "Tf", 8.0),
])
def test_round_trip(kind, rep, v):
    shown = units.from_canon(kind, rep, v, CTX)
    assert units.to_canon(kind, rep, shown, CTX) == pytest.approx(v, rel=1e-12)


def test_known_values():
    assert units.from_canon("gain", "PB", 4.0) == 25.0 and units.to_canon("gain", "PB", 50.0) == 2.0
    assert units.from_canon("gain", "K_eng", 2.0, CTX) == pytest.approx(1.0)          # MV 100, PV 200: K·100/200
    assert units.from_canon("integral", "min", 90.0) == 1.5
    assert units.from_canon("integral", "rep_min", 30.0) == 2.0 and units.to_canon("integral", "rep_min", 4.0) == 15.0
    assert units.from_canon("integral", "Ki", 20.0, dict(K=2.0)) == pytest.approx(0.1)   # Ki = K / Ti
    assert units.from_canon("derivative", "Kd", 3.0, dict(K=2.0)) == 6.0                # Kd = K·Td
    assert units.from_canon("filter", "Tf", 10.0, dict(Td=5.0)) == 0.5                  # Tf = Td / N
    assert units.from_canon("filter", "alpha", 10.0) == pytest.approx(0.1)


def test_no_integral_and_no_filter():
    assert units.from_canon("integral", "rep_min", math.inf) == 0.0 and units.to_canon("integral", "rep_min", 0) == math.inf
    assert units.from_canon("integral", "Ki", math.inf, dict(K=1.0)) == 0.0 and units.to_canon("integral", "Ki", 0, dict(K=1.0)) == math.inf
    assert units.from_canon("filter", "Tf", math.inf, dict(Td=5.0)) == 0.0 and units.to_canon("filter", "Tf", 0, dict(Td=5.0)) == math.inf
    assert units.to_canon("gain", "PB", 0) == math.inf


def test_errors():
    with pytest.raises(ValueError, match="neznámá varianta"):
        units.to_canon("gain", "XX", 1.0)
    with pytest.raises(ValueError, match="potřebuje 'K'"):
        units.to_canon("integral", "Ki", 1.0)
    with pytest.raises(ValueError, match="potřebuje 'mv_range'"):
        units.from_canon("gain", "K_eng", 1.0)


# ---- mapování
CANONS = [dict(Kc=2.0, Ti=30.0, Td=4.0, b=1.0, c=1.0, N=8.0), dict(Kc=0.7, Ti=100.0, Td=0.0, b=1.0, c=1.0, N=5.0),
          dict(Kc=3.0, Ti=float("inf"), Td=2.0, b=1.0, c=1.0, N=10.0)]


@pytest.mark.parametrize("pid", controllers.presets())
@pytest.mark.parametrize("canon", CANONS)
def test_preset_round_trip_and_controller(pid, canon):
    prof = controllers.load_preset(pid)
    m = controllers.canonical_to_profile(prof, canon)
    assert not [w for w in m["warnings"] if w[0] != "ctl_w_no_filter"]
    back = controllers.profile_to_canonical(prof, m["values"])
    for f in ("Kc", "Ti", "Td", "b", "c"):
        assert back[f] == pytest.approx(canon[f], rel=1e-9), (pid, f)
    # regulátor sestavený z hodnot profilu má ideální Kc, Ti, Td z kanonických
    vals = dict(m["values"])
    for p in prof["params"]:
        if p["role"] == "Ts":
            vals[p["key"]] = 1.0
    c = Controller(prof, vals, 1.0)
    assert c.Kc == pytest.approx(canon["Kc"], rel=1e-9)
    assert (c.Td if canon["Td"] > 0 else 0.0) == pytest.approx(canon["Td"], rel=1e-9)
    if math.isfinite(canon["Ti"]):
        assert c.Ti == pytest.approx(canon["Ti"], rel=1e-9)
    else:
        assert not c.use_i


def test_series_limit_warning_and_nearest():
    prof = controllers.load_preset("isa_series")
    m = controllers.canonical_to_profile(prof, dict(Kc=2.0, Ti=10.0, Td=5.0, b=1.0, c=1.0, N=10.0))
    assert [w[0] for w in m["warnings"]] == ["ctl_w_series_limit"]
    back = controllers.profile_to_canonical(prof, m["values"])
    assert back["Ti"] == pytest.approx(10.0) and back["Td"] == pytest.approx(2.5) and back["Kc"] == pytest.approx(2.0)
    # na hranici Ti = 4·Td se převod provede beze varování
    m = controllers.canonical_to_profile(prof, dict(Kc=2.0, Ti=20.0, Td=5.0, b=1.0, c=1.0, N=10.0))
    assert not m["warnings"]


def test_parallel_values():
    m = controllers.canonical_to_profile(controllers.load_preset("isa_parallel"),
                                         dict(Kc=2.0, Ti=20.0, Td=3.0, b=1.0, c=1.0, N=10.0))["values"]
    assert (m["Kp"], m["Ki"], m["Kd"]) == (2.0, 0.1, 6.0)


def test_unrepresentable_features_warn():
    prof = controllers.load_preset("siemens_cont_c")             # bez váhy b, D vždy z odchylky, pevný filtr Tf
    m = controllers.canonical_to_profile(prof, dict(Kc=1.0, Ti=10.0, Td=2.0, b=0.5, c=0.0, N=8.0))
    assert {w[0] for w in m["warnings"]} == {"ctl_w_fixed_b", "ctl_w_fixed_c"}
    assert m["values"]["TM_LAG"] == pytest.approx(0.25)
    isa = controllers.load_preset("isa_ideal")
    assert [w[0] for w in controllers.canonical_to_profile(isa, dict(Kc=1.0, Ti=10.0, Td=2.0, b=1.0, c=0.4, N=8.0))["warnings"]] == ["ctl_w_c_binary"]


def test_unit_variants_in_profile():
    """PB, Ti v minutách a Td v ms v profilu: regulátor dostane kanonické hodnoty."""
    prof = copy.deepcopy(controllers.load_preset("isa_ideal"))
    for p in prof["params"]:
        p["repr"] = {"Kc": "PB", "Ti": "min", "Td": "ms", "N": "alpha"}.get(p["role"], p.get("repr"))
    assert not controllers.validate_profile(prof)
    canon = dict(Kc=2.0, Ti=90.0, Td=4.0, b=1.0, c=1.0, N=8.0)
    m = controllers.canonical_to_profile(prof, canon)
    assert m["values"]["Kc"] == 50.0 and m["values"]["Ti"] == 1.5 and m["values"]["Td"] == 4000.0
    assert m["values"]["N"] == pytest.approx(0.125)
    back = controllers.profile_to_canonical(prof, m["values"])
    assert all(back[f] == pytest.approx(canon[f]) for f in canon)
    vals = dict(m["values"], SampleTime=1.0)
    c = Controller(prof, vals, 1.0)
    assert (c.Kc, c.Ti, c.Td) == pytest.approx((2.0, 90.0, 4.0)) and c.Tf == pytest.approx(0.5)


def test_engineering_gain_needs_ranges():
    prof = copy.deepcopy(controllers.load_preset("isa_ideal"))
    next(p for p in prof["params"] if p["role"] == "Kc")["repr"] = "K_eng"
    rg = dict(pv_range=(0.0, 200.0), mv_range=(0.0, 100.0))
    m = controllers.canonical_to_profile(prof, CANONS[0], rg)
    assert m["values"]["Kc"] == pytest.approx(1.0)
    c = Controller(prof, dict(m["values"], SampleTime=1.0, _ranges=rg), 1.0)
    assert c.Kc == pytest.approx(2.0)


def test_ts_and_series_pid_equivalent_response():
    """Hodnoty z mapování dávají stejnou odezvu ve všech formách."""
    canon = CANONS[0]
    outs = []
    for pid in ("isa_ideal", "isa_parallel", "isa_series", "pcs7_pidconl"):
        prof = controllers.load_preset(pid)
        vals = controllers.canonical_to_profile(prof, canon)["values"]
        vals.update({p["key"]: 1.0 for p in prof["params"] if p["role"] == "Ts"})
        c = Controller(prof, vals, 1.0)
        c.init(50.0, 50.0, 50.0)
        outs.append(np.array([c.step(50.0 if k < 10 else 60.0, 50.0 + np.sin(k / 7)) for k in range(120)]))
    for o in outs[1:]:
        assert np.allclose(o, outs[0], atol=1e-9)
    assert Profile(controllers.load_preset("isa_series")).form == "series"
