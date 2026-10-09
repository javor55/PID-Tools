"""Kontroly kvality dat (pidtools.app.quality)."""
import numpy as np

from pidtools.app.quality import check_all, summary, warn_mask


def _by_id(checks):
    return {c.id: c for c in checks}


def test_quality_flags_range_limit_and_excitation():
    n = 3000
    t = np.arange(n) * 1.0
    mv = np.where(t < 1000, 50.0, np.where(t < 1500, 100.0, 60.0))       # 500 s na horní mezi MV
    pv = 10 + np.cumsum(np.random.default_rng(0).normal(0, 0.01, n))
    pv[200:260] = -1.0                                                      # pod rozsahem měření
    dv = 20 + np.where((t > 2000) & (t < 2400), 5.0, 0.0)
    c = _by_id(check_all(t, pv, mv, 1.0, pv, mv, [dv], ["Q"], (0.0, 25.0), (0.0, 100.0)))
    assert c["samp"].status == "ok" and c["gaps"].status == "ok"
    assert c["pvrng"].status == "warn" and c["pvrng"].mask.sum() == 60
    assert c["mvlim"].status == "warn" and c["mvlim"].mask.sum() >= 500
    assert c["mvexc"].status == "info" and c["mvexc"].args["n"] >= 2
    assert c["dvexc"].status == "info" and c["indep"].status == "ok"
    checks = check_all(t, pv, mv, 1.0, pv, mv, [dv], ["Q"], (0.0, 25.0), (0.0, 100.0))
    cnt, usable = summary(checks)
    assert usable and cnt["warn"] >= 2 and warn_mask(checks, n).sum() >= 560


def test_quality_detects_compression_and_gaps():
    t = np.r_[np.arange(1000), np.arange(1500, 2500)] * 1.0
    pv = np.round(np.sin(t / 200) * 2, 0)                                   # schody (komprese / hrubé rozlišení)
    mv = np.full(t.size, 40.0)
    c = _by_id(check_all(t, pv, mv, 1.0, pv, mv))
    assert c["gaps"].status == "warn" and c["comp"].status == "warn"
    assert c["mvexc"].status == "warn"
