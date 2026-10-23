"""Kombinovaná identifikace: ruční úseky MV (otevřená smyčka) + úseky v AUTO (simulace smyčky s regulátorem Set 1)."""
import numpy as np

from pidtools.app import closedloop as cl
from pidtools.app import loopmode as lm
from pidtools.app import model as mdl
from pidtools.app import windows as wn
from pidtools.core import ProcStep, fit_windows
from pidtools.core.simulation import PIDConL

CTRL = dict(Gain=1.0, TI=300.0, TD=0.0, SampleTime=1.0, MV_Lo=0, MV_Hi=100)


def mixed_record(n=21600):
    """P1D (K 1,2; T 300 s; θ 60 s): 3 h ručně (skok MV), pak AUTO se změnami SP (Gain 1, TI 300); pomalá porucha."""
    rng = np.random.default_rng(5)
    sp = np.full(n, 50.0)
    sp[12000:] = 54.0
    sp[16000:] = 48.0
    dpv = np.cumsum(rng.normal(0, 0.01, n))
    mvm = np.full(n, 40.0)
    mvm[5000:] = 46.0
    noise = rng.normal(0, 0.1, n)
    proc, pid = ProcStep("P1D", [1.2, 300.0, 60.0], 1.0), PIDConL(dict(CTRL), 1.0)
    pid.init(50, 50, 40)
    pv, mv = np.zeros(n), np.zeros(n)
    for k in range(n):
        ym = 50 + proc.output() + dpv[k] + noise[k]
        u = pid.track(sp[k], ym, mvm[k]) if k < 10800 else pid.step(sp[k], ym)
        proc.step(u - 40)
        pv[k], mv[k] = ym, u
    return np.arange(n, dtype=float), sp, pv, mv


def test_identify_mixed_core():
    t, sp, pv, mv = mixed_record()
    ow, cw = [(3000, 10800)], [(10800, len(t))]
    r0 = fit_windows("P1D", t, pv, mv, 1.0, [], ow, theta_max=1000)
    r = cl.identify_mixed("P1D", r0["p"], [], t, sp, pv, mv, [], 1.0, CTRL, ow, cw, theta_max=1000)
    K, T, th = r["p"]
    assert abs(K - 1.2) < 0.1 and abs(T - 300) < 45 and abs(th - 60) < 15, r["p"]
    assert r["fit_cl_pv"] > 70 and len(r["fits_cl"]) == 1
    # jen AUTO úsek, špatný počáteční odhad
    r = cl.identify_mixed("P1D", [0.6, 800.0, 5.0], [], t, sp, pv, mv, [], 1.0, CTRL, [], cw, theta_max=1000)
    assert abs(r["p"][0] - 1.2) < 0.2 and abs(r["p"][2] - 60) < 25, r["p"]


def test_mv_modes_and_indices():
    t, sp, pv, mv = mixed_record()
    det = lm.detect(t, mv, pv, sp)
    wmv = [[3000.0, 10700.0], [11000.0, 21500.0]]
    assert wn.mv_modes(t, wmv, det, {}, "auto") == ["man", "auto"]
    assert wn.mv_modes(t, wmv, det, {wn.mode_key(wmv[1]): "man"}, "auto") == ["man", "man"]
    assert wn.mv_modes(t, wmv, det, {}, "open") == ["man", "man"]
    assert wn.mv_modes(t, wmv, det, {}, "cl") == ["auto", "auto"]
    op, cl_, nmv = wn.mode_indices(t, {"MV": wmv}, [], 10.0, ["man", "auto"])
    assert nmv == 1 and op == [(3000, 10701)] and cl_ == [(11000, 21501)]


def test_identify_windows_all_mixed():
    t, sp, pv, mv = mixed_record()
    wins = [(3000, 10800), (11000, len(t))]
    valid = np.ones(len(t), bool)
    s = mdl.IdSettings(chosen=("P1D",), th_max=1000.0)
    mixed = dict(sp=sp, ctrl=CTRL, open=[wins[0]], closed=[wins[1]], open_mv=1)
    res, errs = mdl.identify_windows_all(t, pv, mv, 1.0, [], wins, valid, s, [], [], mixed=mixed)
    assert not errs
    r = res["P1D"]
    assert r["mixed"] and r["method"] == "win" and r["cl_wins"] and r["p_open"]
    assert abs(r["p"][0] - 1.2) < 0.1 and abs(r["p"][2] - 60) < 15, r["p"]
    assert r["p_open"][2] < r["p"][2]          # ruční úsek sám dá kratší zpoždění (porucha na začátku úseku)


def test_auto_mode_needs_real_set1():
    """Režim „automaticky“: AUTO (uzavřená smyčka) jen se skutečným Set 1, ne s výchozími zástupnými hodnotami."""
    assert lm.resolve_mode("auto", 0.9, True, True, set1_ok=True) == "cl"
    assert lm.resolve_mode("auto", 0.9, True, True, set1_ok=False) == "open"
    assert lm.resolve_mode("cl", 0.9, True, True, set1_ok=False) == "cl"           # výslovná volba platí
    t, sp, pv, mv = mixed_record()
    det = lm.detect(t, mv, pv, sp)
    wmv = [[3000.0, 10700.0], [11000.0, 21500.0]]
    assert wn.mv_modes(t, wmv, det, {}, "auto", set1_ok=False) == ["man", "man"]
    assert wn.mv_modes(t, wmv, det, {wn.mode_key(wmv[1]): "auto"}, "auto", set1_ok=False) == ["man", "auto"]
