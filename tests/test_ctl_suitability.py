"""Test použitelnosti regulátoru (app.controller_check, 12 kontrol) a ladění s profilem (app.ctl_tuning)."""
import copy

import pytest

from pidtools import controllers, core
from pidtools.app import controller_check as cc
from pidtools.app import ctl_tuning
from pidtools.app.tuning import Request


def _p(pid="isa_ideal"):
    return copy.deepcopy(controllers.load_preset(pid))


def _by_id(res):
    return {c["id"]: c for c in res["checks"]}


@pytest.mark.parametrize("pid", controllers.presets())
def test_presets_are_suitable(pid):
    res = cc.run_check(controllers.load_preset(pid))
    assert res["verdict"] == "suitable", [(c["id"], c["msg"]) for c in res["checks"] if c["status"] == "fail"]
    assert [c["id"] for c in res["checks"]] == [k for k, _ in cc.CHECKS] and len(res["checks"]) == 12
    assert not res["reasons"]


def test_pidconl_details():
    c = _by_id(cc.run_check(controllers.load_preset("pcs7_pidconl")))
    assert c["translation"]["status"] == "warn"                       # preset zatím neověřen proti manuálu
    assert all(v["status"] == "ok" for k, v in c.items() if k != "translation")
    assert c["equivalent"]["diff"] == 0.0 and c["linearity"]["dev"] < 1e-9
    assert len(c["processes"]["rows"]) == 5 and all(r["overshoot"] < 60 for r in c["processes"]["rows"])


def test_without_antiwindup_is_unsuitable():
    p = _p()
    p["structure"]["antiwindup"] = "none"
    res = cc.run_check(p)
    assert res["verdict"] == "unsuitable" and res["reasons"] == ["antiwindup"]
    assert res["checks"][8]["severity"] == "critical"


def test_back_calculation_passes():
    p = _p()
    p["structure"]["antiwindup"] = "back_calculation"
    p["params"].append(dict(key="Tt", role="Tt", default=10.0))
    assert cc.run_check(p)["verdict"] == "suitable"


def test_missing_ts_role_is_unsuitable():
    p = _p()
    p["params"] = [x for x in p["params"] if x["role"] != "Ts"]
    res = cc.run_check(p)
    assert res["verdict"] == "unsuitable" and res["checks"][0]["msg"][0] == "ctl_m_missing_roles"
    assert len(res["checks"]) == 12


def test_untranslatable_profile_is_unsuitable():
    p = _p()
    p["structure"]["form"] = "nesmysl"
    res = cc.run_check(p)
    assert res["verdict"] == "unsuitable" and res["checks"][0]["msg"][0] == "ctl_m_invalid"
    assert all(c["msg"][0] == "ctl_m_skipped" for c in res["checks"][1:])


def test_inexact_mapping_warns_only():
    p = _p()
    p["structure"]["d"] = {"source": "error", "filter": "none"}
    c = _by_id(cc.run_check(p))
    assert c["equivalent"]["status"] == "warn" and "ctl_w_no_filter" in c["equivalent"]["msg"][1]["warnings"]


def test_verdict_levels(monkeypatch):
    """Selhání kontroly typu mapping = „Jen optimalizací“, typu critical = „Nevhodný“."""
    def fail(sev):
        return lambda X: dict(status="fail", severity=sev, msg=["ctl_m_error", {"error": "x"}])
    monkeypatch.setattr(cc, "CHECKS", (("linearity", fail("mapping")),))
    assert cc.run_check(_p())["verdict"] == "optimisation_only"
    monkeypatch.setattr(cc, "CHECKS", (("linearity", fail("mapping")), ("rest", fail("critical"))))
    assert cc.run_check(_p())["verdict"] == "unsuitable"


def test_only_runs_selected_checks():
    res = cc.run_check(_p(), only=["rest", "direction"])
    assert [c["id"] for c in res["checks"]] == ["rest", "direction"]


def test_nonlinear_profile_detected():
    """Mrtvé pásmo 1 % rozbije linearitu i ustálenou odchylku; linearita je označena jako nelineární."""
    p = _p()
    next(x for x in p["params"] if x["role"] == "deadband")["default"] = 1.0
    c = _by_id(cc.run_check(p))
    assert c["linearity"]["status"] == "fail" and c["linearity"]["severity"] == "mapping"


# ---- ladění s profilem
CODE, PM = "P1D", [1.0, 20.0, 4.0]
BASE = dict(SampleTime=1.0, DiffGain=5.0, PropFacSP=1.0, DiffFbk=False)


@pytest.mark.parametrize("pid", ["isa_ideal", "isa_parallel", "isa_series", "pcs7_pidconl", "siemens_pid_compact"])
def test_suggest_for_profile_matches_canonical(pid):
    prof = controllers.load_preset(pid)
    req = Request("SIMC", "PID")
    r = ctl_tuning.suggest_for_profile(CODE, PM, [], BASE, req, prof)
    ref = core.tune(CODE, PM, "SIMC", core.default_tc(CODE, PM, 1.0, "SIMC", "PID", 5.0), "PID", 1.0)
    assert r["Kc"] == pytest.approx(ref["Kc"]) and r["Ti"] == pytest.approx(ref["Ti"])
    eff = r["effective"]
    assert eff["Kc"] == pytest.approx(ref["Kc"]) and eff["Td"] == pytest.approx(ref["Td"])
    ctrl = ctl_tuning.canonical_ctrl(prof, BASE, r["profile"])
    assert ctrl["Gain"] == pytest.approx(ref["Kc"])
    assert r["Ms_mapped"] == pytest.approx(core.robustness(CODE, PM, dict(BASE, Gain=ref["Kc"], TI=ref["Ti"],
                                                                         TD=ref["Td"]))["Ms"], rel=1e-6)


def test_suggest_series_limit_warning():
    """SIMC návrh s Ti < 4·Td se v sériové formě upraví a řekne to."""
    ser = controllers.load_preset("isa_series")
    m = ctl_tuning.profile_values(ser, dict(Kc=2.0, Ti=8.0, Td=4.0))
    assert [w[0] for w in m["warnings"]] == ["ctl_w_series_limit"] and m["effective"]["Td"] == pytest.approx(2.0)
    assert ctl_tuning.profile_values(controllers.load_preset("isa_ideal"), dict(Kc=2.0, Ti=8.0, Td=4.0))["warnings"] == []


def test_to_canonical_and_profile_robustness():
    prof = controllers.load_preset("isa_parallel")
    vals = dict(Kp=1.2, Ki=1.2 / 30, Kd=1.2 * 4.0, N=5.0, SampleTime=1.0)
    can = ctl_tuning.to_canonical(prof, vals)
    assert (can["Kc"], can["Ti"], can["Td"]) == pytest.approx((1.2, 30.0, 4.0))
    rb = ctl_tuning.profile_robustness(prof, CODE, PM, vals)
    assert rb["Ms"] == pytest.approx(core.robustness(CODE, PM, dict(BASE, Gain=1.2, TI=30.0, TD=4.0))["Ms"], rel=1e-6)


def test_pidconl_simulation_through_profile_is_identical():
    """pidconl_sim_full s profilem pcs7_pidconl dá bit-shodnou odezvu jako bez něj."""
    import numpy as np
    ctrl = dict(Gain=1.2, TI=30.0, TD=4.0, DiffGain=5.0, SampleTime=1.0, MV_Lo=0.0, MV_Hi=100.0)
    sp = np.full(400, 50.0)
    sp[20:] = 60.0
    a = core.pidconl_sim_full(CODE, PM, [], 1.0, sp, 50.0, 50.0, ctrl)
    b = core.pidconl_sim_full(CODE, PM, [], 1.0, sp, 50.0, 50.0, ctrl, profile=controllers.load_preset("pcs7_pidconl"))
    assert np.array_equal(a["PV"], b["PV"]) and np.array_equal(a["MV"], b["MV"])
