"""Gain scheduling: tabulka pro blok GainSched, kontroly rozvrhu a simulace na nelineárním procesu."""
import numpy as np
import pytest

from pidtools.core import best_conzone, gs_er_table, gs_interp, gs_issues, gs_sim, gs_table, iae, pidconl_sim, settled, tune

CTRL = dict(Gain=1.0, TI=20.0, TD=0.0, DiffGain=5.0, SampleTime=0.5, MV_Lo=0.0, MV_Hi=100.0, DiffFbk=True)


def _pts(gains, T=20.0, th=4.0):
    return [dict(x=x, u=u, p=[k, T, th]) for x, u, k in zip((20.0, 50.0, 80.0), (20.0, 45.0, 60.0), gains)]


def test_interp_like_gainsched_block():
    X, G = [20.0, 50.0, 80.0], [1.0, 2.0, 5.0]
    assert gs_interp(35.0, X, G) == pytest.approx(1.5)
    assert gs_interp(0.0, X, G) == 1.0 and gs_interp(99.0, X, G) == 5.0       # mimo body konstantně


def test_table_two_points_and_order():
    rows, filled = gs_table([dict(x=80.0, gain=1.0, ti=10.0, td=0.0), dict(x=20.0, gain=3.0, ti=30.0, td=0.0)])
    assert filled and [r["x"] for r in rows] == [20.0, 50.0, 80.0]
    assert rows[1]["gain"] == pytest.approx(2.0) and rows[1]["ti"] == pytest.approx(20.0)
    rows3, filled3 = gs_table([dict(x=x, gain=1.0, ti=1.0, td=0.0) for x in (60.0, 10.0, 30.0)])
    assert not filled3 and [r["x"] for r in rows3] == [10.0, 30.0, 60.0]


def test_issues():
    assert gs_issues(_pts([1.0, 1.2, 1.5])) == []
    assert "sign" in gs_issues(_pts([1.0, -1.0, 1.0]))
    close = _pts([1.0, 1.0, 1.0])
    close[1]["x"] = 21.0
    assert "close" in gs_issues(close)
    bad = _pts([1.0, 1.0, 1.0])
    bad[2]["u"] = 10.0                          # při kladném K musí s MV růst i PV
    assert "order" in gs_issues(bad)


def test_linear_case_matches_pidconl():
    # stejný model ve všech bodech → stejné chování jako lineární simulace PIDConL
    h, n = 0.5, 1200
    sp = np.where(np.arange(n) * h >= 10, 55.0, 50.0)
    pts = [dict(x=x, u=u, p=[1.0, 20.0, 4.0]) for x, u in ((20.0, 20.0), (50.0, 50.0), (80.0, 80.0))]
    _, o = gs_sim("P1D", pts, CTRL, None, h, sp)
    _, _, pv, mv = pidconl_sim("P1D", [1.0, 20.0, 4.0], [], h, sp, 50.0, 50.0, CTRL)
    assert np.max(np.abs(o["PV"] - pv)) < 0.05
    assert np.max(np.abs(o["MV"] - mv)) < 0.05


def test_scheduling_helps_on_nonlinear_process():
    # zesílení roste 1 → 6 s pracovním bodem; pevná sada naladěná dole v horním bodě kmitá
    pts = _pts([1.0, 2.5, 6.0])
    tuned = [tune("P1D", q["p"], "SIMC", 4.0, "PI", 0.5) for q in pts]
    sched = dict(X=[q["x"] for q in pts], gain=[r["Kc"] for r in tuned], ti=[r["Ti"] for r in tuned],
                 td=[0.0] * 3)
    h, n = 0.5, 2400
    t = np.arange(n) * h
    sp = np.where(t >= 20, 85.0, 75.0)
    fixed = dict(CTRL, Gain=tuned[0]["Kc"], TI=tuned[0]["Ti"])
    _, of = gs_sim("P1D", pts, fixed, None, h, sp)
    _, os_ = gs_sim("P1D", pts, fixed, sched, h, sp)
    assert iae(t, sp, os_["PV"]) < 0.7 * iae(t, sp, of["PV"])
    assert os_["Gain"][-1] == pytest.approx(gs_interp(os_["PV"][-1], sched["X"], sched["gain"]), rel=1e-6)


def test_er_table_symmetric():
    rows = gs_er_table(5.0, 2.0, 1.5, 30.0, 0.0)
    assert [r["x"] for r in rows] == [-5.0, 0.0, 5.0]
    assert [r["gain"] for r in rows] == [3.0, 1.5, 3.0] and {r["ti"] for r in rows} == {30.0}
    X, G = [r["x"] for r in rows], [r["gain"] for r in rows]
    assert gs_interp(2.5, X, G) == pytest.approx(2.25) and gs_interp(-20.0, X, G) == 3.0


def test_er_scheduling_faster_return():
    # lineární proces (jeden bod), velká porucha: zesílení při velké odchylce zkrátí návrat
    pts = [dict(x=50.0, u=50.0, p=[1.0, 30.0, 3.0])]
    r = tune("P1D", [1.0, 30.0, 3.0], "SIMC", 12.0, "PI", 0.5)
    ctrl = dict(CTRL, Gain=r["Kc"], TI=r["Ti"])
    h, n = 0.5, 2400
    t = np.arange(n) * h
    sp = np.full(n, 50.0)
    d = np.where(t >= 50, -15.0, 0.0)
    sched = {k: [q[kq] for q in gs_er_table(3.0, 2.5, r["Kc"], r["Ti"], 0.0)]
             for k, kq in (("X", "x"), ("gain", "gain"), ("ti", "ti"), ("td", "td"))}
    _, of = gs_sim("P1D", pts, ctrl, None, h, sp, d)
    _, oe = gs_sim("P1D", pts, ctrl, sched, h, sp, d, x_src="er")
    assert iae(t, sp, oe["PV"]) < 0.85 * iae(t, sp, of["PV"])
    assert np.max(np.abs(oe["Gain"])) > 1.5 * r["Kc"]         # při velké odchylce scheduler zesílil
    assert abs(oe["PV"][-1] - 50.0) < 0.2                      # a v klidu se vrátil k SP


def test_control_zone():
    # mimo řídicí pásmo MV na limitu; úzké pásmo rozkmitá smyčku mezi limity; pomůže jen široké pásmo
    # u rychle naladěného regulátoru – u opatrného překmitne (MV po návratu do pásma zůstává u limitu)
    pts = [dict(x=50.0, u=50.0, p=[1.0, 30.0, 3.0])]
    h, n = 0.5, 2400
    t = np.arange(n) * h
    sp = np.where(t >= 20, 70.0, 50.0)
    widths = [2.0, 5.0, 10.0, 15.0, 18.0]
    fast = tune("P1D", [1.0, 30.0, 3.0], "SIMC", 12.0, "PI", 0.5)
    base = dict(CTRL, Gain=fast["Kc"], TI=fast["Ti"])
    _, oz = gs_sim("P1D", pts, dict(base, ConZone=18.0), None, h, sp)
    assert oz["MV"][int(21 / h)] == pytest.approx(100.0)
    assert settled(t, sp, oz["PV"])
    _, on = gs_sim("P1D", pts, dict(base, ConZone=2.0), None, h, sp)
    assert not settled(t, sp, on["PV"])
    w, res = best_conzone("P1D", pts, base, h, sp, np.zeros(n), widths)
    assert w == 18.0 and len(res) == len(widths)
    slow = tune("P1D", [1.0, 30.0, 3.0], "SIMC", 40.0, "PI", 0.5)
    w2, _ = best_conzone("P1D", pts, dict(CTRL, Gain=slow["Kc"], TI=slow["Ti"]), h, sp, np.zeros(n), widths)
    assert w2 is None
