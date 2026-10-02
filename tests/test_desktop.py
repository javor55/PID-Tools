"""Desktopová aplikace (Qt) bez displeje: stav smyčky a okna nad demo daty."""
import json
import os

import numpy as np
import pytest

from pidtools.app import project as prj
from pidtools.desktop.state import LoopState


@pytest.fixture(scope="module")
def state():
    s = LoopState()
    s.load_demo()
    assert not s.identify()
    return s


def test_state_workflow(state):
    s = state
    assert s.c_pv == "LIC101.PV" and s.c_d == ["FI100.Pritok"] and s.quality()["level"] == 0
    assert s.model is not None and s.evaluate()["fit"] > 95
    sug = s.suggest("SIMC")
    s.write_set(2, sug)
    m = s.set_metrics(2)
    assert m["stable"] and m["Ms"] < 2
    r = s.simulate()
    assert r["src"] == "cl" and r["kpis"][2] is not None


def test_state_range_change_rescales(state):
    s = state
    code = s.model[0]
    k0 = s.model[1][0]
    s.set(pv_hi=200.0)
    assert s.rescale_if_needed() and s.model[1][0] == pytest.approx(k0 / 2) and not s.stale
    s.set(pv_hi=100.0)
    s.rescale_if_needed()
    assert s.model[0] == code


def test_project_roundtrip_with_web_format(state, tmp_path):
    """Projekt z desktopu má formát webu (klíče nastavení, mapování sloupců, modely, data)."""
    p = tmp_path / "p.json"
    state.save_project(p)
    proj = json.loads(p.read_text(encoding="utf-8"))
    assert proj["map"]["c_pv"] == "LIC101.PV" and "fit" in proj and "t_s" in proj["data"]["cols"]
    assert all(prj.is_state_key(k) for k in proj["state"])
    s2 = LoopState()
    s2.load_project(p)
    assert s2.model[0] == state.model[0] and np.allclose(s2.model[1], state.model[1]) and not s2.stale
    html = s2.report_html(dict(plant="T"), ["model", "tuning", "response", "apc", "signoff"], "cdn")
    assert "LIC101.PV" in html


def test_web_project_opens_in_desktop(tmp_path):
    """Projekt uložený webovou aplikací (s daty) se otevře v desktopu."""
    from pidtools.app.dataset import demo_frame
    df = demo_frame()
    proj = dict(version=2, tag="LIC101", fname="demo",
                state={"pv_lo": 0.0, "pv_hi": 100.0, "samp": 2.0, "pfb": True, "set1_gain": -2.0},
                map={"c_pv": "LIC101.PV", "c_mv": "LIC101.MV", "c_sp": "LIC101.SP", "c_d": [], "c_pos": "—"},
                ranges={"id": [100.0, 3000.0]}, ff=[],
                data={"cols": {"t_s": df["Cas"].to_numpy(), "LIC101.PV": df["LIC101.PV"].to_numpy(),
                               "LIC101.MV": df["LIC101.MV"].to_numpy(), "LIC101.SP": df["LIC101.SP"].to_numpy()}})
    p = tmp_path / "web.json"
    p.write_text(prj.serialize_project(proj), encoding="utf-8")
    s = LoopState()
    s.load_project(p)
    assert s.c_pv == "LIC101.PV" and s.rng == (100.0, 3000.0) and s.get("samp") == 2.0 and s.get("propfac") == 0.0


qt = pytest.importorskip("PySide6", reason="PySide6 není nainstalované (requirements-desktop.txt)")


def _prefs(path):
    from PySide6.QtCore import QSettings
    return QSettings(str(path), QSettings.IniFormat)    # ne uživatelské nastavení počítače


@pytest.fixture(scope="module")
def win(tmp_path_factory):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
    except Exception as ex:      # chybí systémové knihovny Qt
        pytest.skip(f"Qt nelze spustit: {ex}")
    from pidtools import i18n
    from pidtools.desktop.main import MainWindow
    w = MainWindow(prefs=_prefs(tmp_path_factory.mktemp("qt") / "prefs.ini"))
    w.set_lang("en")
    w.show()
    yield app, w
    _wait(app)
    w.close()
    i18n.set_lang("en")


def _wait(app):
    from PySide6.QtCore import QThreadPool
    QThreadPool.globalInstance().waitForDone(180000)
    for _ in range(3):
        app.processEvents()


def test_window_full_flow(win):
    app, w = win
    assert not w.tabs.isTabEnabled(1)
    w.open_demo()
    assert w.tabs.isTabEnabled(1) and w.pages[0].c_pv.currentData() == "LIC101.PV"
    w.pages[1]._identify()
    _wait(app)
    assert w.state.model is not None and w.pages[1].res.rowCount() == 5
    t = w.pages[2]
    t.method.setCurrentIndex(t.method.findData("OPT"))
    _wait(app)
    assert "Gain" in t.sug.text()
    t._write(2)
    _wait(app)
    assert t.rob.rowCount() == 5 and t.kpi.rowCount() == 2
    w.set_lang("cs")
    assert w.tabs.tabText(2).startswith("3")
    _wait(app)
    w.set_lang("en")
    _wait(app)


def test_window_project_and_report(win, tmp_path):
    app, w = win
    if w.state.model is None:
        w.open_demo()
        w.state.identify()
        w.refresh()
    p = tmp_path / "w.json"
    w.state.save_project(p)
    from pidtools.desktop.main import MainWindow
    w2 = MainWindow(prefs=_prefs(tmp_path / "prefs.ini"))
    w2.state.load_project(p)
    w2.refresh()
    assert w2.pages[1].mcode.count() == 5
    html = w2.state.report_html(dict(plant="x"), ["tuning"], "cdn")
    assert "<table" in html
    w2.close()


def test_live_session_without_qt(state):
    """Živá simulace (app.live) – dvě sady, změna SP, porucha, ukazatele od poslední události."""
    from pidtools.app.live import LiveSession
    s = state
    sets = {n: {k: v for k, v in s.set_ctrl(n).items() if k not in ("FF", "FF_LL")} for n in (1, 2)}
    _, _, mv_id, _ = s.segment()
    ls = LiveSession(s, s.model, sets, 50.0, float(mv_id[0]))
    ls.advance(100)
    ls.set_sp(55.0)
    ls.advance(2000)
    d = ls.series(2)
    assert abs(d["PV"][-1] - 55.0) < 0.5 and ls.kpis(2)["iae"] > 0
    ls.set_dist(d_in_e=5.0)
    ls.advance(500)
    assert ls.kpis(1)["maxdev"] > 0
    ls.set_process(k_fac=1.5)
    assert ls.t == 0.0


def test_window_live_and_apc(win):
    app, w = win
    if w.state.model is None:
        w.open_demo()
        w.state.identify()
        w.refresh()
    w.tabs.setCurrentIndex(3)
    app.processEvents()
    lv = w.pages[3]
    for _ in range(5):
        lv.tick()
    lv.sp.setValue(55.0)
    for _ in range(5):
        lv.tick()
    assert lv.sess.t > 0 and lv.kpi.rowCount() >= 1
    w.tabs.setCurrentIndex(4)
    app.processEvents()
    apc = w.pages[4]
    for i in range(len(apc.panels)):
        apc.tabs.setCurrentIndex(i)
        app.processEvents()
    _wait(app)
    assert apc.panels[4].kpi.rowCount() == 2          # Smith: PID a prediktor
    assert apc.panels[1].kpi.rowCount() == 3          # dopředná vazba: bez, statická, dynamická


def _two_loops():
    """Dvě provázané smyčky: MV každé působí i na PV té druhé."""
    import pandas as pd
    from pidtools import core
    t = np.arange(0, 3000.0)
    rng = np.random.default_rng(1)
    mv1 = 50 + 8.0 * ((t >= 200) & (t < 800)) - 6.0 * ((t >= 1600) & (t < 2200))
    mv2 = 50 + 7.0 * ((t >= 500) & (t < 1100)) - 5.0 * ((t >= 1900) & (t < 2500))
    pv1 = 50 + core.simulate("P1D", [1.0, 30.0, 3.0], t, mv1 - 50, 1.0) + \
        core.simulate("P1D", [0.5, 40.0, 4.0], t, mv2 - 50, 1.0) + rng.normal(0, 0.05, t.size)
    pv2 = 50 + core.simulate("P1D", [0.8, 25.0, 2.0], t, mv2 - 50, 1.0) + \
        core.simulate("P1D", [0.4, 35.0, 3.0], t, mv1 - 50, 1.0) + rng.normal(0, 0.05, t.size)
    return pd.DataFrame({"Time": t, "FIC1.PV": pv1, "FIC1.MV": mv1, "FIC2.PV": pv2, "FIC2.MV": mv2})


def test_project_two_loops(tmp_path):
    from pidtools.app.apc import decouple
    from pidtools.desktop.project import Project
    pr = Project()
    pr.state.load_frame(_two_loops(), "two.csv")
    pr.state.set_columns("FIC1.PV", "FIC1.MV", "—", ["FIC2.MV"])
    assert not pr.state.identify()
    pr.add_loop()
    assert pr.active == 1 and pr.state.c_pv == "FIC2.PV"        # druhá smyčka si vybere jinou PV
    pr.state.set_columns("FIC2.PV", "FIC2.MV", "—", ["FIC1.MV"])
    assert not pr.state.identify()
    pr.active = 0
    (i, b), = pr.others()
    a = dict(pr.state.report_record(), name="FIC1")
    dz = decouple.design(a, b)
    assert dz["dab"]["gain"] == pytest.approx(-0.5, abs=0.05) and dz["lam"] == pytest.approx(1 / (1 - 0.25), rel=0.1)
    p = tmp_path / "two.json"
    pr.save(p)
    pr2 = Project()
    pr2.load(p)
    assert pr2.names() == ["FIC1.PV", "FIC2.PV"] and all(ls.model for ls in pr2.loops) and pr2.active == 0
    assert pr2.report_html({}, ["tuning"], "cdn").count("<section class='loop'>") == 2


def test_window_two_loops(win):
    app, w = win
    from pidtools.desktop.project import Project
    w.project = Project()
    w.project.state.load_frame(_two_loops(), "two.csv")
    w.project.state.set_columns("FIC1.PV", "FIC1.MV", "—", ["FIC2.MV"])
    w.project.state.identify()
    w.build()
    w.add_loop()
    assert w.loop_combo.count() == 2 and w.project.active == 1
    w.state.set_columns("FIC2.PV", "FIC2.MV", "—", ["FIC1.MV"])
    w.state.identify()
    w.switch_loop(0)
    w.tabs.setCurrentIndex(4)
    apc = w.pages[4]
    apc.tabs.setCurrentIndex(2)          # rozvazbení
    app.processEvents()
    assert apc.panels[2].kpi.rowCount() == 3
    apc.tabs.setCurrentIndex(3)          # override (stejné MV nemají – jen upozornění, simulace proběhne)
    app.processEvents()
    w.remove_loop()
    assert len(w.project.loops) == 1


def test_diagnostics_without_qt(state):
    from pidtools.app import diagnostics as dg
    s = state
    g = s.grid
    k = dg.kpis(s, s.t, s.sp, s.pv, s.mv, g.Ts, 0.0, 100.0, 10.0, g.has_sp)
    assert k["std_e"] > 0 and k["at_lim"] == 0
    v = dg.valve(s.sp, s.pv, s.mv, g.Ts, g.has_sp, True)
    assert not v["osc"]["osc"] and v["verdict"] is None
    ts, pv, mv, d = s.segment()
    lg, spread = dg.nonlinearity(s.model, ts, pv, mv, d, g.Ts)
    assert len(lg) >= 2 and spread < 1.2          # demo je lineární


def test_window_validation_and_diagnostics(win):
    app, w = win
    w.open_demo()
    w.state.rng = (0.0, 1800.0)
    w.state.identify()
    w.refresh()
    mt = w.pages[1]
    w.tabs.setCurrentIndex(1)
    mt.sub.setCurrentIndex(1)
    mt.v_from.setValue(1800.0)
    mt.v_to.setValue(3599.0)
    app.processEvents()
    assert "%" in mt.v_res.text()
    w.tabs.setCurrentIndex(5)
    app.processEvents()
    dt = w.pages[5]
    dt.cmp.setChecked(True)
    app.processEvents()
    assert dt.kpi.rowCount() == 7 and dt.kpi.columnCount() == 3 and dt.nl.rowCount() >= 2


def test_uncertainty_and_comparison(state):
    s = state
    u = s.bootstrap(6)
    assert len(u["ps"]) == 6 and len(s.unc_models()) == 6
    m = s.set_metrics(2)
    assert m["Ms_worst"] is not None and m["Ms_worst"] >= m["Ms"] - 1e-9
    rows = s.compare_methods()
    assert {r["method"] for r in rows} >= {"SIMC", "OPT"} and all(r["ctype"] in ("PI", "PID") for r in rows)


def test_scenario_editor(win):
    app, w = win
    from pidtools.desktop.tabs.tuning import ScenarioDialog
    if w.state.model is None:
        w.open_demo()
        w.state.identify()
        w.refresh()
    s = w.state
    dlg = ScenarioDialog(w.pages[2], s, s.scen_rows(1000.0), 1000.0)
    n0 = dlg.tab.rowCount()
    dlg._add(["on" == "on", "IN", "ramp", 3.0, 600.0, 800.0, None, None])
    rows = dlg.rows()
    assert len(rows) == n0 + 1 and rows[-1][1:3] == ["IN", "ramp"]
    s.set_scen_rows(rows, 1000.0)
    dlg.noise.setValue(0.2)
    dlg.apply_plant()
    r = s.simulate(1000.0)
    assert r["rows"][-1][2] == "ramp" and s.plant()["Noise"] > 0
    r2 = s.simulate(2000.0)                     # jiná délka → časy událostí se přepočtou
    assert r2["rows"][-1][4] == pytest.approx(1200.0)
    s.set_scen_rows(None, 0)
    s.set(sim_noise=0.0)


def test_shared_guides_and_help_window(win):
    """Průvodci: obsah a kontroly ze sdíleného modulu, v desktopu samostatné okno s odkazy na akce."""
    from pidtools.app import guides
    app, w = win
    assert guides.sections("tuning") and guides.checks("model", guides.GuideState(loop_name="X"))[0][0] is False
    w.open_demo()
    w.state.identify()
    w.refresh()
    for i in range(w.tabs.count()):
        w.tabs.setCurrentIndex(i)
        w.show_guide()
        assert len(w._help.view.toPlainText()) > 200
    w.do_action("tab:model")
    assert w.tabs.currentIndex() == 1
    w._help.close()
