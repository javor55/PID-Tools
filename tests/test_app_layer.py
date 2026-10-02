"""Aplikační vrstva pidtools.app – nezávislost na UI frameworku a výpočty pracovního postupu."""
import subprocess
import sys

import numpy as np
import pytest

from pidtools.app import feedforward, loop, project, scenario


def test_app_layer_has_no_ui_dependency():
    """Jádro, aplikační vrstva a texty se dají použít bez Streamlitu a Qt (desktopový frontend, skripty)."""
    code = ("import sys, pidtools.core, pidtools.i18n, pidtools.app.dataio, pidtools.app.guess, pidtools.app.loop, "
            "pidtools.app.scenario, pidtools.app.feedforward, pidtools.app.project; "
            "bad = [m for m in ('streamlit', 'plotly', 'PySide6', 'PyQt5') if m in sys.modules]; "
            "print(','.join(bad)); sys.exit(1 if bad else 0)")
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_i18n_language_without_ui():
    from pidtools import i18n
    i18n.set_lang_provider(None)
    try:
        i18n.set_lang("cs")
        assert i18n.lang() == "cs" and i18n.T("set_1") == i18n.TEXTS["cs"]["set_1"]
        i18n.set_lang_provider(lambda: "en")
        assert i18n.T("set_1") == i18n.TEXTS["en"]["set_1"]
    finally:
        i18n.set_lang_provider(None)
        i18n.set_lang("en")


class _Loop(loop.Scaling):
    pv_lo, pv_hi, mv_lo, mv_hi = 0.0, 400.0, 0.0, 100.0


def test_scaling_and_block_ctrl():
    sc = _Loop()
    assert sc.P(100.0) == pytest.approx(25.0) and sc.EP(25.0) == pytest.approx(100.0)
    b = loop.block_ctrl(sc, 1.0, 5.0, 0.5, True, 4.0, "cont", 10.0, 90.0, 0.0, 2.0, 8.0)
    assert b["DeadBand"] == pytest.approx(1.0) and b["MV_Lo"] == 10.0 and b["SPRate"] == pytest.approx(2.0)
    s = loop.set_ctrl(b, 1.2, 0.0, 0.0)
    assert np.isinf(s["TI"]) and s["PropFacSP"] == 0.5


def test_scenario_rows_and_signals():
    rows = scenario.default_rows(20.0, 100.0, 1, 1000.0)
    assert [r[1] for r in rows] == ["SP", "IN", "M0"] and rows[1][4] == 400
    rows2, hit = scenario.set_sp_step(rows, -10.0)
    assert hit and rows2[0][3] == -10.0 and rows[0][3] == 20.0       # původní řádky beze změny
    assert scenario.rescale_times(rows, 2.0)[1][4] == 800
    h, ts = scenario.grid(1.0, 1000.0)
    sig = scenario.signals(rows, ts, h, 1000.0, 400.0, 100.0, 50.0, 1)
    k = np.searchsorted(ts, 100.0)
    assert sig["sp"][0] == 50.0 and sig["sp"][k] == pytest.approx(55.0)       # +20 jednotek PV = +5 % z 400
    assert sig["dmv"][np.searchsorted(ts, 500.0)] == pytest.approx(5.0)
    assert sig["dmeas"][0][-1] == 1.0 and sig["sp_amp"] == pytest.approx(5.0)


def test_scenario_auto_length_and_kpis():
    from pidtools import core
    p = [1.0, 20.0, 2.0]
    ctrl = dict(Gain=2.0, TI=20.0, TD=0.0, DiffGain=5.0, SampleTime=1.0)
    T_end, src = scenario.auto_length("P1D", p, [ctrl], 30.0, 1.0, np.arange(600.0))
    assert src == "cl" and 50 <= T_end <= 1000
    assert scenario.nice(130.0) == 150.0
    h, ts = scenario.grid(1.0, T_end)
    sig = scenario.signals(scenario.quick_rows("sp", 5.0, 100.0, T_end), ts, h, T_end, 100.0, 100.0, 50.0, 0)
    r = core.pidconl_sim_full("P1D", p, [], h, sig["sp"], 50.0, 50.0, dict(ctrl, MV_Lo=0.0, MV_Hi=100.0))
    k = scenario.kpis(r, 100.0, 100.0)
    assert scenario.stable(r) and k["iae"] > 0 and k["mv_range"] > 5


def test_project_format_roundtrip():
    proj = dict(version=project.PROJECT_VERSION, tag="A", state={"pfb": True, "samp": 2.0},
                loops=[dict(tag="A", state={"pfb": True}), dict(tag="B", state={})], active=2,
                data={"cols": {"t_s": np.array([0.0, 1.0]), "PV": np.array([1.23456789, np.nan])}})
    back = project.load_project(project.serialize_project(proj))
    assert back["data"]["cols"]["PV"][0] == pytest.approx(1.23457) and np.isnan(back["data"]["cols"]["PV"][1])
    recs, act = project.loop_records(back)
    assert [r["tag"] for r in recs] == ["A", "B"] and act == 1
    assert project.migrate_state(recs[0]["state"])["propfac"] == 0.0
    assert project.is_state_key("tc|P1D|SIMC|PI") and not project.is_state_key("main_tab")


def test_feedforward_design_from_settings():
    p, pd = [2.0, 30.0, 3.0], [1.0, 10.0, 1.0]
    des = feedforward.design("P1D", p, [pd, pd], [dict(use=True, gain=-0.3)])
    assert des[0]["use"] and des[0]["gain"] == -0.3 and not des[1]["use"]
    ff, ffll = feedforward.to_ctrl(des)
    assert ff == [-0.3, 0.0] and ffll[0] == (0.0, 0.0, 0.0)
    assert feedforward.state(des)[0]["gain"] == -0.3
