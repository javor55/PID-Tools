"""Testy výpočetního jádra: konzistence simulací, identifikace, ladění, diagnostika."""
import numpy as np
import pytest

from pidtools import core
from pidtools.core import MODELS

CASES = {"P0D": [1.0, 5.0], "P1D": [1.2, 50.0, 8.0], "P2D": [1.0, 50.0, 20.0, 5.0], "I0D": [0.01, 10.0],
         "I1D": [0.01, 20.0, 8.0]}


def _ctrl(code, **kw):
    g = 0.3 if code == "P0D" else 1.5 if code[0] == "P" else 5.0
    return dict(Gain=g, TI=60.0, TD=4.0, DiffGain=5, SampleTime=1.0, MV_Lo=-1e9, MV_Hi=1e9, **kw)


@pytest.mark.parametrize("code", ["P1D", "P2D", "I0D", "I1D"])
@pytest.mark.parametrize("pvf", [0.0, 6.0])
def test_linear_loop_equals_simulation(code, pvf):
    """Lineární odezvy (použité v optimalizaci) = kroková simulace PIDConL."""
    p, n = CASES[code], 600
    ctrl = _ctrl(code, PVFilt=pvf, DiffFbk=True)
    e_sp, e_d, u_sp, u_d = core.closed_loop_steps(code, p, ctrl, 1.0, n, with_u=True)
    sp = np.ones(n + 1)
    sp[0] = 0
    r = core.pidconl_sim_full(code, p, [], 1.0, sp, 0, 0, ctrl)
    r2 = core.pidconl_sim_full(code, p, [], 1.0, np.zeros(n), 0, 0, ctrl, (), np.ones(n))
    assert np.allclose(1 - r["PV"][1:], e_sp, atol=1e-8)
    assert np.allclose(r["MV"][1:], u_sp, atol=1e-7)
    assert np.allclose(-r2["PV"], e_d, atol=1e-8)
    assert np.allclose(r2["MV"], u_d, atol=1e-7)


def test_live_loop_equals_batch_simulation():
    """Živá simulace používá stejný engine jako dávková."""
    code, p, h, n = "P1D", CASES["P1D"], 0.5, 400
    plant = dict(Stic=1.0, ValveChar=[1] * 7 + [0.5, 0.25, 0.1])
    ctrl = dict(_ctrl(code, PVFilt=2.0, MVRate=0.5), MV_Lo=0, MV_Hi=100)
    sp = np.full(n, 55.0)
    batch = core.pidconl_sim_full(code, p, [], h, np.r_[50.0, sp[1:]], 50, 50, dict(ctrl, **plant))
    loop = core.LiveLoop(code, p, ctrl, h, 50.0, 50.0, plant)
    loop.pid.step(50.0, 50.0)       # první krok se SP = pracovní bod (jako dávka)
    loop.valve.step(loop.pid.u)
    loop.proc.step(0.0)
    loop.advance((n - 1) * h, 55.0)
    assert np.allclose(np.asarray(loop.hist["PV"]), batch["PV"][1:], atol=1e-9)


def test_live_loop_bumpless_manual_to_auto():
    loop = core.LiveLoop("P1D", CASES["P1D"], dict(_ctrl("P1D"), MV_Lo=0, MV_Hi=100), 0.5, 50.0, 50.0)
    loop.advance(20, 50.0, auto=False, u_man=60.0)
    u_man = loop.hist["MV"][-1]
    loop.advance(0.5, 50.0, auto=True)          # stejné SP → výstup naváže bez skoku (jen malá změna PV)
    assert abs(loop.hist["MV"][-1] - u_man) < 1.0   # jen vliv pohybu PV (P, D), žádný ráz


def test_identification_recovers_demo_model():
    t, sp, pv, mv, q = core.demo_data()
    r = core.fit_model("I1D", t[::2], pv[::2], mv[::2], 2.0, [q[::2]])
    assert r["fit"] > 98
    assert r["p"][0] == pytest.approx(-0.004, rel=0.1)
    assert 15 < r["p"][1] + r["p"][2] < 30          # T1 + θ (skutečně 23 s)


def test_fixed_parameter_is_kept():
    t, sp, pv, mv, q = core.demo_data()
    r = core.fit_model("I1D", t[::2], pv[::2], mv[::2], 2.0, [q[::2]], fixed={"p2": 8.0})
    assert r["p"][2] == 8.0 and r["fit"] > 98


def test_unmeasured_disturbance_suppression_improves_model():
    rng = np.random.default_rng(5)
    t = np.arange(0, 6000, 2.0)
    m = np.full_like(t, 50.0)
    for t0, v in [(500, 55), (1100, 50), (1700, 45), (2300, 50), (2900, 57), (3500, 50), (4100, 44), (4700, 50)]:
        m[t >= t0] = v
    dist = np.cumsum(rng.normal(0, 0.05, len(t))) + 3 * np.sin(2 * np.pi * t / 4000)
    y = 40 + core.simulate("P1D", [1.5, 80, 20], t, m - 50, 2.0) + dist + rng.normal(0, 0.2, len(t))
    err = lambda r: abs(r["p"][0] - 1.5) + abs(r["p"][2] - 20) / 20
    assert err(core.fit_model("P1D", t, y, m, 2.0, level="high")) < err(core.fit_model("P1D", t, y, m, 2.0))


def test_stiction_identification():
    p, n = [1.2, 60.0, 8.0], 4000
    sp = np.full(n, 50.0)
    for t0, v in [(300, 54), (1300, 48), (2300, 52), (3200, 50)]:
        sp[t0:] = v
    ctrl = dict(Gain=1.5, TI=60.0, TD=0, DiffGain=5, SampleTime=1.0, MV_Lo=0, MV_Hi=100, Stic=2.0, Noise=0.1, Seed=4)
    drift = np.cumsum(np.random.default_rng(3).normal(0, 0.01, n))  # pomalá porucha rozhýbe ventil
    r = core.pidconl_sim_full("P1D", p, [], 1.0, sp, 50, 50, ctrl, (), drift)
    fit = core.fit_with_stiction("P1D", r["t"], r["PVm"], r["MV"], 1.0, k=2)
    assert fit["stic"] == pytest.approx(2.0, abs=0.6)


@pytest.mark.parametrize("code", list(CASES))
@pytest.mark.parametrize("method", ["SIMC", "iSIMC", "Lambda", "AMIGO"])
def test_tuning_rules_give_stable_loop(code, method):
    p = CASES[code]
    r = core.tune(code, p, method, core.default_tc(code, p, 1.0, method), "PI", 1.0)
    rb = core.robustness(code, p, dict(Gain=r["Kc"], TI=r["Ti"], TD=r["Td"], DiffGain=5, SampleTime=1.0))
    assert rb["stable"] and rb["Ms"] < 3.5


@pytest.mark.parametrize("crit", ["IAE", "ISE", "ITAE", "OVS"])
def test_optimization_respects_ms(crit):
    code, p = "P1D", CASES["P1D"]
    starts = [(r["Kc"], r["Ti"], r["Td"]) for r in [core.tune(code, p, m, core.default_tc(code, p, 1.0, m), "PI", 1.0)
                                                     for m in ("SIMC", "AMIGO")]]
    o = core.optimize_time(code, p, "PI", 1.0, 5, crit, "both", 1.6, None, starts)
    rb = core.robustness(code, p, dict(Gain=o["Kc"], TI=o["Ti"], TD=0, DiffGain=5, SampleTime=1.0))
    assert rb["stable"] and rb["Ms"] < 1.7


def test_migo_and_instability_detection():
    code, p = "I0D", CASES["I0D"]
    o = core.optimize_migo(code, p, "PI", 1.0, 5, 1.6, None, [(5.0, 100.0, 0.0)])
    assert core.robustness(code, p, dict(Gain=o["Kc"], TI=o["Ti"], TD=0, DiffGain=5, SampleTime=1.0))["Ms"] < 1.7
    assert not core.robustness(code, p, dict(Gain=5, TI=5, TD=0, DiffGain=5, SampleTime=1.0))["stable"]


def test_diagnostics():
    h, t = 1.0, np.arange(3000.0)
    x = np.sin(2 * np.pi * t / 120) + 0.3 * np.random.default_rng(0).normal(size=3000)
    assert core.oscillation(x, h)["osc"]
    assert not core.oscillation(np.random.default_rng(1).normal(size=3000), h)["osc"]
    _, sp, pv, mv, _ = core.demo_data()
    segs = core.find_segments(np.arange(len(mv)) * 1.0, mv, sp, 1.0, True)
    assert len(segs) == 1 and segs[0]["n_mv"] == 6


def test_models_table_consistent():
    for code, m in MODELS.items():
        assert core.n_free(code) == len(m["params"]) - 1
