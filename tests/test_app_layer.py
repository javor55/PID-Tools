"""Aplikační vrstva pidtools.app – nezávislost na UI frameworku a výpočty pracovního postupu."""
import subprocess
import sys

import numpy as np
import pytest

from pidtools.app import feedforward, loop, project, scenario


def test_app_layer_has_no_ui_dependency():
    """Jádro, aplikační vrstva a texty se dají použít bez Streamlitu a Qt (desktopový frontend, skripty)."""
    code = ("import sys, pidtools.core, pidtools.i18n, pidtools.app.dataio, pidtools.app.guess, pidtools.app.loop, "
            "pidtools.app.scenario, pidtools.app.feedforward, pidtools.app.project, pidtools.app.model, "
            "pidtools.app.tuning, pidtools.app.apc.recommend, pidtools.app.apc.smith, pidtools.app.apc.gainsched, "
            "pidtools.app.apc.feedforward, pidtools.app.apc.decouple; "
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


def _rec(name, model, c_mv, c_sp="—", c_d=(), mv_rng=(0.0, 100.0)):
    return dict(name=name, model=model, ctrl=None, c_pv=name + ".PV", c_mv=c_mv, c_sp=c_sp, c_d=list(c_d),
                pv_rng=(0.0, 100.0), mv_rng=mv_rng, u_pv="", u_mv="")


def test_apc_recommend():
    from pidtools.app.apc import recommend
    a = _rec("TIC1", ("P1D", [1.0, 10.0, 30.0], []), "FIC2.SP")        # θ/(θ+T) = 0,75 → Smith
    b = _rec("FIC2", ("P1D", [1.0, 2.0, 0.5], []), "FV2", c_sp="FIC2.SP")
    c = _rec("PIC3", None, "FIC2.SP")
    kinds = [(k, i) for k, _, i in recommend.recommend(a, [(2, b), (3, c)], spread=2.0, ff_on=True)]
    assert ("smith", None) in kinds and ("gainsched", None) in kinds and ("override", 3) in kinds
    assert recommend.delay_ratio("P1D", [1.0, 10.0, 30.0]) == pytest.approx(0.75)


def test_apc_smith_gainsched_ff():
    from pidtools.app.apc import feedforward as aff, gainsched, smith
    sc = _Loop()
    v, r, rows = smith.values("P1D", [1.0, 20.0, 40.0], sc, 50.0, 40.0, "PI", None, 1.0, "°C", "%")
    assert v["theta"] == pytest.approx(40.0) and r["Kc"] > 0 and rows[0][0].startswith("SmithModelTimLag")
    assert smith.tc0([1.0, 20.0, 40.0], 1.0) == 40.0
    old = gainsched.key("P1D", [(0.0, 10.0)], (0.0, 100.0, 0.0, 100.0))
    new = gainsched.key("P1D", [(0.0, 10.0)], (0.0, 200.0, 0.0, 100.0))
    pts = gainsched.rescale(old, new, [[50.0, 40.0, 95.0, 2.0, 10.0, 1.0]])
    assert pts[0][0] == pytest.approx(25.0) and pts[0][3] == pytest.approx(1.0)       # Kp v %: 2 → 1
    assert gainsched.rescale(old, old, [[1, 2, 3, 4]]) is None
    ctrl = dict(Gain=1.0, TI=20.0, TD=0.0, DiffGain=5.0, SampleTime=1.0)
    tab = gainsched.er_table(5.0, 2.0, ctrl)
    assert tab[1][1][-1] == pytest.approx(2.0)
    assert gainsched.k_max("P1D", [1.0, 20.0, 2.0], ctrl) >= 1.0
    des = [dict(use=True, dyn=False, gain=-50.0, lead=0.0, lag=0.0, delay=0.0)]
    rows = aff.rows(["F1"], [np.array([0.0, 2.0])], des, 100.0, "%")
    assert rows[0][1][0][1] == pytest.approx(-50.0) and rows[0][1][-1][1] == pytest.approx(-100.0)


def test_model_workflow():
    """Identifikace, přepočet rozsahu, úpravy, hodnocení a validace na simulovaných datech P1D."""
    from pidtools import core
    from pidtools.app import model as mdl
    Ts = 1.0
    t = np.arange(0, 600.0, Ts)
    mv = 40.0 + 10.0 * (t >= 50) - 10.0 * (t >= 300)
    pv = 30.0 + core.simulate("P1D", [1.5, 20.0, 5.0], t, mv - 40.0, Ts)
    s = mdl.IdSettings(("P1D", "P0D"), 100.0)
    res, errs = mdl.identify_all(t, pv, mv, Ts, [], s)
    assert not errs and mdl.best(res) == "P1D" and res["P1D"]["p"][0] == pytest.approx(1.5, rel=0.05)
    k1 = mdl.fit_key("f", (0, 600), s, (0, 100, 0, 100), Ts, "PV", "MV", [], False)
    k2 = mdl.fit_key("f", (0, 600), s, (0, 200, 0, 100), Ts, "PV", "MV", [], False)
    assert mdl.only_norm_changed(k1, k2) and not mdl.only_norm_changed(k1, k1)
    res2, (fK, _, _) = mdl.rescale_results(res, k1[mdl.NORM], k2[mdl.NORM])
    assert fK == pytest.approx(0.5) and res2["P1D"]["p"][0] == pytest.approx(res["P1D"]["p"][0] * 0.5)
    p, pdl = mdl.clamp([1.5, -1.0, -2.0], [])
    assert p == [1.5, 1e-6, 0.0] and mdl.is_edited(p, pdl, 0.0, res["P1D"])
    ev = mdl.evaluate("P1D", res["P1D"]["p"], [], 0.0, "none", None, t, pv, mv, [], Ts)
    assert ev["fit"] > 95 and ev["sigma_pv"] < 0.1
    assert mdl.fixed_params([1.0, 2.0, 3.0], [False, False, True], [], []) == {"p2": 3.0}
    assert mdl.overlap((0, 100), (50, 300)) == pytest.approx(0.5)
    ctrl = dict(Gain=1.0, TI=20.0, TD=0.0, DiffGain=5.0, SampleTime=1.0)
    vr = mdl.validate_cl("P1D", res["P1D"]["p"], [], ctrl, t, np.full_like(t, 30.0), pv, mv, [], Ts, 1.0)
    assert vr["stable"] and len(vr["PV"]) == len(t)
    un = mdl.uncertainty([[1.0, 10.0, 2.0], [1.2, 12.0, 2.0], [0.8, 8.0, 2.0]], [1.0, 10.0, 2.0])
    assert un["rel"][2] == pytest.approx(0.0) and un["rel"][0] > 10


def test_tuning_suggest_compare_and_sets():
    from pidtools.app import tuning as tun
    p = [1.5, 30.0, 4.0]
    base = dict(SampleTime=1.0, DiffGain=5.0, PropFacSP=1.0, DiffFbk=True, PVFilt=0.0, MVRate=0.0)
    assert "iSIMC" in tun.methods("P1D", p) and "iSIMC" not in tun.methods("I0D", [0.01, 4.0])
    s = tun.suggest("P1D", p, [], base, tun.Request("SIMC", "PI"))
    assert s["Kc"] > 0 and s["Ti"] > 0
    o = tun.suggest("P1D", p, [], base, tun.Request("OPT", "PI", crit="IAE", target="dist"))
    m = tun.set_metrics("P1D", p, dict(base, Gain=o["Kc"], TI=o["Ti"], TD=o["Td"]))
    assert m["stable"] and m["Ms"] <= 1.65
    o2 = tun.suggest("P1D", p, [], base, tun.Request("OPT", "PI", crit="IAE", target="scen"))
    assert ("note_scen_missing", {}) in o2["notes"]
    rows = tun.compare("P1D", p, [], base, tun.Request())
    assert {r["method"] for r in rows} >= {"SIMC", "AMIGO", "OPT"} and all(r["Ms"] for r in rows)
    assert len(tun.robust_models(p, [], True)) == 4 and tun.robust_models(p, [], False) == ()
    assert tun.is_placeholder(1.0, 100.0, 0.0)


def test_report_without_ui():
    """Protokol se sestaví jen z dat smyček (desktop, skripty) – bez Streamlitu."""
    from pidtools.app import report
    base = dict(SampleTime=1.0, DiffGain=5.0, MV_Lo=0.0, MV_Hi=100.0)
    rec = dict(id=1, name="TIC1", active=True, model=("P1D", [1.5, 30.0, 4.0], []), fit=96.0, rng=(0.0, 100.0),
               ctrl=dict(base, Gain=0.8, TI=30.0, TD=0.0), ctrl1=dict(base, Gain=1.0, TI=100.0, TD=0.0),
               c_pv="TIC1.PV", c_mv="TIC1.MV", c_sp="—", c_d=[], pv_rng=(0.0, 200.0), mv_rng=(0.0, 100.0),
               u_pv="°C", u_mv="%")
    t = np.arange(0, 200.0)
    md = (t, 100 + 0 * t, 50 + 0 * t, [], 1.0)
    html_ = report.build_report([rec], dict(plant="Test", status="draft"), report.SECTIONS, "cdn", lambda r: md,
                                dict(items=[("smith", "Smith?", None)], smith=[("PIDConL", "Gain", 0.5, "–")]))
    assert html_.startswith("<!doctype html>") and "TIC1" in html_ and "PIDConL" in html_ and "plotly" in html_


def test_apc_cascade():
    from pidtools import core
    from pidtools.app.apc import cascade as acas
    inner = acas.manual_inner(1.0, 5.0, 0.0, 1.0)
    assert inner == ("P1D", [1.0, 5.0, 1.0])
    si = acas.tune_loop(*inner, "SIMC", "PI", 0.5, 5.0)
    ictrl = acas.inner_ctrl(si, 5.0, 0.5)
    t63, tc_eff = acas.inner_response(*inner, ictrl, 0.5)
    assert 0 < tc_eff < t63 < 60
    co, p_o = acas.outer_model(("P1D", [2.0, 120.0, 10.0]), tc_eff, inner[1][-1])
    so = acas.tune_loop(co, p_o, "OPT", "PI", 1.0, 5.0)
    octrl = dict(Gain=so["Kc"], TI=so["Ti"], TD=so["Td"], DiffGain=5.0, SampleTime=1.0, MV_Lo=0.0, MV_Hi=100.0)
    ts, oc, ok = acas.simulate(inner, ictrl, ("P1D", [2.0, 120.0, 10.0]), octrl, 1.0, 0.5, p_o, co)
    assert ok and oc.shape[1] == 5 and acas.separation(None, so, t63) > 1
    t = np.arange(0, 300.0)
    mv = 50 + 10.0 * (t >= 20)
    pv = core.simulate("P1D", [1.0, 5.0, 1.0], t, mv - 50, 1.0) + 50
    best, errs = acas.fit_inner(t, pv, mv, 1.0)
    assert best["code"] == "P1D" and best["fit"] > 95
