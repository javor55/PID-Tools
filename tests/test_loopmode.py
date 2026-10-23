"""Rozpoznání ruční / automatické smyčky v záznamu a kontroly věrohodnosti modelu a ladění (pidtools.app.loopmode)."""
import numpy as np

from pidtools.app import loopmode as lm
from pidtools.core import pidconl_sim_full


def _record():
    """3 h ručně (skok MV), 3 h v AUTO (změny SP, šum), 2 h ručně – proces 1. řádu se zpožděním."""
    h = 1.0
    sp = np.full(28800, 50.0)
    sp[12000:] = 54.0
    sp[16000:] = 48.0
    rng = np.random.default_rng(5)
    d = np.cumsum(rng.normal(0, 0.01, len(sp)))
    r = pidconl_sim_full("P1D", [1.2, 300.0, 60.0], [], h, sp, 50.0, 40.0,
                         dict(Gain=1.0, TI=300.0, TD=0.0, SampleTime=1.0, MV_Lo=0, MV_Hi=100, Noise=0.1), dist_pv=d)
    mv, pv = r["MV"].copy(), r["PVm"].copy()
    mv[:10800] = 40.0                                         # ručně: MV drží, jeden skok
    mv[5000:10800] = 46.0
    mv[21600:] = mv[21599]
    return np.arange(len(sp)) * h, mv, pv, sp


def test_detect_manual_and_auto():
    t, mv, pv, sp = _record()
    det = lm.detect(t, mv, pv, sp)
    kinds = [(round(a / 3600, 1), round(b / 3600, 1), k) for a, b, k in det["runs"]]
    assert [k for *_, k in kinds] == ["man", "auto", "man"], kinds
    assert abs(kinds[0][1] - 3.0) < 0.3 and abs(kinds[1][1] - 6.0) < 0.3
    assert 0.3 < det["frac"] < 0.45
    assert lm.frac_in(det, t, 0, 10000) == 0.0 and lm.frac_in(det, t, 12000, 20000) == 1.0
    span = lm.manual_span(det, t, mv, 0, t[-1])                 # ruční úsek se skokem MV
    assert span and span[0] < 5000 < span[1] <= 3.3 * 3600


def test_detect_without_sp_and_manual_demo():
    from pidtools.app.dataset import demo_frame
    df = demo_frame()
    t = np.arange(len(df), dtype=float)
    det = lm.detect(t, df["LIC101.MV"].to_numpy(float))
    assert det["frac"] == 0.0 and det["runs"][0][2] == "man"


def test_resolve_mode():
    assert lm.resolve_mode("auto", 0.8, True, True) == "cl"
    assert lm.resolve_mode("auto", 0.8, False, True) == "open"
    assert lm.resolve_mode("auto", 0.2, True, True) == "open"
    assert lm.resolve_mode("open", 0.9, True, True) == "open"
    assert lm.resolve_mode("cl", 0.0, True, True) == "cl"


def test_model_and_tuning_checks():
    # pomalý proces bez dopravního zpoždění (typická chyba identifikace z dat v AUTO)
    assert [k for k, _ in lm.model_checks("P2D", [0.1, 4460.0, 4.6, 0.0], 2.9)] == ["chk_no_delay"]
    assert lm.model_checks("P1D", [0.07, 2560.0, 630.0], 2.9) == []
    assert lm.model_checks("P1D", [2.0, 5.0, 0.0], 1.0) == []          # rychlý průtok: bez zpoždění je v pořádku
    keys = [k for k, _ in lm.tuning_checks("P2D", [0.1, 4460.0, 4.6, 0.0], 487.0, 2.9, 0.5)]
    assert keys == ["chk_no_delay", "chk_loop_gain", "chk_vs_set1"]
    assert lm.tuning_checks("P1D", [0.07, 2560.0, 630.0], 8.0, 2.9, 5.0) == []
