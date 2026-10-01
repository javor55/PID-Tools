"""Jádro APC: RGA, decouplery, override s external reset feedback, Smithův prediktor."""
import numpy as np
import pytest

from pidtools.core import default_tc, iae, pidconl_sim, tune
from pidtools.core.apc import ff_design, mimo2_sim, no_delay, override_sim, rga2, rga_advice, smith_sim

H = 0.5


def _ctrl(model):
    r = tune(*model, "SIMC", default_tc(*model, 1.0), "PI", 1.0)
    return dict(Gain=r["Kc"], TI=r["Ti"], TD=r["Td"], DiffGain=5.0, SampleTime=1.0, MV_Lo=0.0, MV_Hi=100.0)


def test_rga():
    assert rga2(1, 0, 0, 1) == pytest.approx(1.0)
    assert rga2(1.0, 0.6, 0.5, 0.8) == pytest.approx(1.6)
    assert rga_advice(rga2(1, 2, 2, 1)) == "rga_swap"
    assert rga_advice(1.0) == "rga_weak" and rga_advice(1.6) == "rga_moderate" and rga_advice(3.0) == "rga_strong"
    assert rga_advice(rga2(1, 1, 1, 1)) == "rga_singular"


def test_decoupler_reduces_interaction():
    ga, gb = ("P1D", [1.0, 50, 5]), ("P1D", [0.8, 30, 3])
    xab, xba = [0.6, 40, 6], [0.5, 25, 4]
    t = np.arange(4000) * H
    sp_a, sp_b = np.where(t > 50, 55.0, 50.0), np.full(len(t), 50.0)
    dab, dba = ff_design(*ga, xab), ff_design(*gb, xba)
    assert dab["gain"] == pytest.approx(-0.6) and dab["delay"] == pytest.approx(1.0)
    res = {}
    for name, d1, d2, dyn in (("none", None, None, True), ("static", dab, dba, False), ("dyn", dab, dba, True)):
        tt, o = mimo2_sim(ga, gb, xab, xba, _ctrl(ga), _ctrl(gb), H, sp_a, sp_b, d1, d2, dyn)
        res[name] = iae(tt, o["SP_B"], o["PV_B"])
        assert o["PV_A"][-1] == pytest.approx(55.0, abs=0.05)
    assert res["static"] < 0.4 * res["none"] and res["dyn"] < 0.4 * res["none"]


def test_override_holds_limit_and_releases():
    ga, gb = ("P1D", [1.0, 20, 2]), ("P1D", [0.5, 60, 5])
    t = np.arange(4000) * H
    sp_a = np.where(t > 50, 70.0, 50.0)
    sp_a[t > 1000] = 52.0
    sp_b = np.full(len(t), 55.0)
    _, free = override_sim(ga, gb, _ctrl(ga), _ctrl(gb), H, sp_a, sp_b, "min", enabled=False)
    _, o = override_sim(ga, gb, _ctrl(ga), _ctrl(gb), H, sp_a, sp_b, "min")
    assert free["PV_B"].max() > 59.0                       # bez override by mez byla překročena
    assert o["PV_B"].max() < 56.0                           # s override drží (malý překmit při převzetí)
    assert o["PV_A"][int(990 / H)] == pytest.approx(60.0, abs=0.2)   # hlavní smyčka omezena
    assert o["PV_A"][-1] == pytest.approx(52.0, abs=0.05) and o["ACT"][-1] == 0   # po uvolnění zpět
    assert np.abs(np.diff(o["ACT"])).sum() == 2             # bez kmitání mezi regulátory


def test_smith_predictor():
    code, p = "P1D", [1.0, 20.0, 40.0]
    t = np.arange(3000) * H
    sp, d = np.where(t > 20, 55.0, 50.0), np.where(t > 700, 5.0, 0.0)
    tt, _, pv, _ = pidconl_sim(code, p, [], H, sp, 50.0, 50.0, _ctrl((code, p)), [], d)
    r = tune(code, no_delay(p), "SIMC", 10.0, "PI", 1.0)
    cs = dict(Gain=r["Kc"], TI=r["Ti"], TD=0.0, DiffGain=5.0, SampleTime=1.0, MV_Lo=0.0, MV_Hi=100.0)
    _, o = smith_sim(code, p, p, cs, H, sp, d)
    assert iae(tt, sp, o["PV"]) < 0.7 * iae(tt, sp, pv)
    assert o["PV"][-1] == pytest.approx(55.0, abs=0.05)
    p_err = [1.0, 20.0, 48.0]                               # skutečné zpoždění o 20 % delší než model
    _, o2 = smith_sim(code, p_err, p, cs, H, sp, d)
    assert o2["PV"][-1] == pytest.approx(55.0, abs=0.1)
