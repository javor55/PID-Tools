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
    assert t.kpi.rowCount() == 2 and "Gain" not in t.sug.text()   # hned scénář se sadami 1, 2; návrh až tlačítkem
    assert t.method.currentData() == "OPT" and t.crit.currentData() == "OVS" and t.target.currentData() == "both"
    t.calculate()
    _wait(app)
    assert "Gain" in t.sug.text() and t.kpi.rowCount() == 3     # sady 1, 2 a návrh
    assert t.freq.tab.rowCount() == 3                  # frekvenční analýza sad i návrhu
    t._write(2)
    _wait(app)
    assert t.rob.rowCount() == 5 and t.kpi.rowCount() == 3
    t.kind.setCurrentIndex(t.kind.findData("in"))     # porucha na vstupu → neaktuální, po výpočtu bez skoku SP
    assert "F5" in t.status.text()
    t.calculate()
    _wait(app)
    r = t._result
    assert np.ptp(r["sp"]) == 0 and r["sig"]["dmv"].any()
    t.chart.b_meas.setChecked(True)
    assert t.chart.measured() is not None and "Δt" in t.chart.readout.text()
    assert {"t"} < set(t.chart.frame().columns)
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
    s.write_set(2, s.suggest("SIMC"))
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
    apc.tabs.setCurrentIndex(0)
    apc.refresh()
    assert "apc:decouple:1" in apc.reco.text()            # doporučení s odkazem na strukturu a druhou smyčku
    apc._open("apc:decouple:1")
    assert apc.tabs.currentIndex() == 2 and apc.panels[2].other.currentData() == 1
    from pidtools.desktop.help import tab_markdown, guide_state
    from pidtools.i18n import T
    for i in range(len(apc.panels)):                        # kontrolní seznam každé struktury (sdílený s webem)
        apc.tabs.setCurrentIndex(i)
        app.processEvents()
        md = tab_markdown("apc", guide_state(w), apc.guide_extra())
        assert md.count(T("g_checklist")) == 2, apc.GUIDE_KINDS[i]
    apc.tabs.setCurrentIndex(10)                            # interakce N×N
    app.processEvents()
    rg = apc.panels[10]
    assert rg.k.rowCount() == 2 and rg.l_tab.rowCount() == 2 and "NI" in rg.res.text()
    w.do_action("loop:1:data")
    assert w.project.active == 1 and w.tabs.currentIndex() == 0
    w.switch_loop(0)
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
    mt.sub.setCurrentIndex(mt.val_index)
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


def test_live_disturbance_shapes(state):
    from pidtools.app.live import LiveSession
    s = state
    s.write_set(2, s.suggest("SIMC"))
    sets = {2: {k: v for k, v in s.set_ctrl(2).items() if k not in ("FF", "FF_LL")}}
    for kind in ("ramp", "sine", "random", "pulse"):
        ls = LiveSession(s, s.model, sets, 50.0, 50.0)
        ls.set_dist(d_in_e=5.0, kind=kind, period=100.0)
        ls.advance(300)
        assert np.ptp(ls.series(2)["MV"]) > 0.1, kind
    assert ls.to_frame().shape[1] == 4 and ls.events[-1][1] == "D"


def test_autosave_and_restore(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from pidtools.desktop.main import MainWindow
    from pidtools.desktop.project import Project
    path = tmp_path / "as" / "autosave.json"
    w = MainWindow(prefs=_prefs(tmp_path / "p.ini"), autosave=path)
    w.autosave()
    assert not path.exists()                               # bez dat se neukládá
    pr = Project()
    pr.state.load_demo()
    pr.state.identify()
    w.project = pr
    w.build()
    w.close()                                              # při zavření se uloží
    assert path.exists()
    monkeypatch.setattr(QMessageBox, "exec", lambda self: 0)
    monkeypatch.setattr(QMessageBox, "clickedButton", lambda self: self.buttons()[0])   # „Obnovit“
    w2 = MainWindow(prefs=_prefs(tmp_path / "p.ini"), autosave=path)
    assert w2.offer_restore() and w2.state.model is not None and w2.state.c_pv == "LIC101.PV"
    monkeypatch.setattr(QMessageBox, "clickedButton", lambda self: None)                # „Zahodit“
    w3 = MainWindow(prefs=_prefs(tmp_path / "p.ini"), autosave=path)
    assert not w3.offer_restore() and not path.exists()
    for x in (w2, w3):
        x.close()


def test_history_recent_and_sections(tmp_path):
    from PySide6.QtWidgets import QApplication
    from pidtools.desktop import layout
    from pidtools.desktop.main import MainWindow
    app = QApplication.instance()
    prefs = _prefs(tmp_path / "p.ini")
    w = MainWindow(prefs=prefs)
    w.open_demo()
    w.state.identify()
    w.refresh()
    t = w.pages[2]
    t.calculate()
    _wait(app)
    t._write(2)
    _wait(app)
    t = w.pages[2]
    h = w.state.history()
    assert len(h) == 1 and h[0]["set"] == 2 and h[0]["iae"] is not None and t.hist.rowCount() == 1
    w.state.set(set2_gain=-1.0)
    t.hist.selectRow(0)
    t._hist_restore(2)
    assert w.state.get("set2_gain") == pytest.approx(h[0]["Kc"])
    p = tmp_path / "proj.json"
    w.project.save(p)
    assert json.loads(p.read_text(encoding="utf-8"))["state"]["tune_hist"][0]["set"] == 2
    assert w.open_path(p) and w.recent()[0] == str(p) and len(w.state.history()) == 1
    errs = []
    w.error = errs.append                              # bez modálního okna
    assert not w.open_path(tmp_path / "missing.csv") and errs
    sec = t.hist_sec
    sec.expand(True)                                   # stav sekce se pamatuje v nastavení
    assert prefs.value("sec2/tuning/hist") == "true"
    assert layout.Section("x", key="tuning/hist").is_expanded()
    w.close()
    _wait(app)


def test_closed_loop_identification_in_desktop():
    """Režim „smyčka v AUTO“: identifikace se doladí simulací smyčky se Set 1 (nepřímá metoda)."""
    import pandas as pd
    from pidtools import core
    from pidtools.app.loop import set_ctrl
    s = LoopState()
    s.load_demo()
    t = np.arange(3000.0)
    sp = 50 + 5 * ((t > 200) & (t < 1000)) - 4 * ((t > 1600) & (t < 2300)) + 3 * (t > 2600)
    base = s.base_ctrl()
    r = core.pidconl_sim_full("P1D", [1.5, 40.0, 8.0], [], 1.0, sp, 50.0, 50.0, set_ctrl(base, 1.2, 50.0, 0.0, [], []),
                              [], None, None)
    s.load_frame(pd.DataFrame({"Time": t, "FIC1.PV": r["PV"], "FIC1.MV": r["MV"], "FIC1.SP": sp}), "cl.csv")
    s.set_columns("FIC1.PV", "FIC1.MV", "FIC1.SP", [])
    s.set(set1_gain=1.2, set1_ti=50.0, set1_td=0.0, id_mode="cl", chosen=["P1D"])
    assert s.id_closed and not s.identify()
    r = s.fit["res"]["P1D"]
    assert r["method"] == "cl" and r["fit_cl_pv"] > 98 and r["p"][1] == pytest.approx(40, rel=0.06)


def _audit_frame():
    import pandas as pd
    t = np.arange(0, 7200.0, 1.0)
    rng = np.random.default_rng(0)
    osc = 3 * np.sign(np.sin(2 * np.pi * t / 300))
    return pd.DataFrame({
        "Time": t, "FIC101.PV": 50 + 2 * np.sin(2 * np.pi * (t - 20) / 300) + rng.normal(0, 0.1, t.size),
        "FIC101.MV": 40 + osc, "FIC101.SP": 50.0,
        "TIC200.PV": 70 + 0.8 * np.sin(2 * np.pi * (t - 60) / 300) + rng.normal(0, 0.1, t.size),
        "TIC200.OP": 55 + 0.5 * np.sin(2 * np.pi * (t - 80) / 300), "TIC200.SP": 70.0,
        "LIC300.PV": 30 + rng.normal(0, 0.2, t.size), "LIC300.OUT": 20 + 0.01 * t / 72, "LIC300.SP": 30.0})


def test_audit_without_qt():
    from pidtools.app import audit
    from pidtools.app.dataset import signals
    s = signals(_audit_frame())
    loops = audit.propose(s.sigs, s.get)
    assert [(d.name, d.pv, d.mv, d.sp) for d in loops][1] == ("TIC200", "TIC200.PV", "TIC200.OP", "TIC200.SP")
    res = audit.analyse(s, loops)
    assert [r["name"] for r in res][:2] == ["FIC101", "TIC200"] and all(r["ok"] for r in res)
    assert res[-1]["score"] < res[0]["score"]
    g = audit.common_oscillations(res)
    assert len(g) == 1 and set(g[0]["loops"]) == {"FIC101", "TIC200"} and g[0]["period"] == pytest.approx(300, rel=0.05)
    assert audit.from_records(audit.to_records(loops), s.sigs)[2].mv == "LIC300.OUT"


def test_window_audit(win):
    app, w = win
    from pidtools.desktop.project import Project
    w.project = Project()
    w.project.state.load_frame(_audit_frame(), "plant.csv")
    w.build()
    a = w.pages[6]
    w.tabs.setCurrentIndex(6)
    app.processEvents()
    assert a.tab.rowCount() == 3                         # návrh smyček z názvů tagů
    a.analyse()
    _wait(app)
    assert a.rank.rowCount() == 3 and "FIC101" in a.common.text()
    assert w.state.get("audit_loops")[0]["pv"] == "FIC101.PV"
    a.tab.selectRow(1)
    a.open_as_loop()
    assert len(w.project.loops) == 2 and w.state.c_pv == "TIC200.PV" and w.state.c_mv == "TIC200.OP"


def test_window_apc_more(win):
    """Split range, regulace polohy ventilu a poměrová regulace: simulace s ukazateli bez chyb."""
    app, w = win
    from pidtools.desktop.project import Project
    w.project = Project()
    w.project.state.load_frame(_two_loops(), "two.csv")
    w.project.state.set_columns("FIC1.PV", "FIC1.MV", "—", [])
    w.project.state.identify()
    w.project.state.write_set(2, w.project.state.suggest("SIMC"))
    w.build()
    w.tabs.setCurrentIndex(4)
    apc = w.pages[4]
    for i in (7, 8, 9):
        apc.tabs.setCurrentIndex(i)
        app.processEvents()
        p = apc.panels[i]
        assert p.kpi.rowCount() == 2, apc.KINDS[i]
        assert p.impl() and "{" not in p.impl()
    sr = apc.panels[7]
    assert "b* =" in sr.res.text() and sr.halves.rowCount() == 2
    from pidtools.desktop.help import tab_markdown, guide_state
    from pidtools.i18n import T
    for i in (7, 8, 9, 10):
        apc.tabs.setCurrentIndex(i)
        app.processEvents()
        assert tab_markdown("apc", guide_state(w), apc.guide_extra()).count(T("g_checklist")) == 2


def test_opc_dialog(win):
    """OPC UA (jen čtení): připojení k testovacímu serveru, hledání tagů, historie → data projektu."""
    pytest.importorskip("asyncua")
    app, w = win
    from pidtools.app import opc
    from pidtools.desktop.opc import OpcDialog
    url, stop = opc.test_server(48441)
    try:
        dlg = OpcDialog(w)
        dlg.url.setText(url)
        dlg.connect()
        assert dlg.conn is not None and dlg.tree.topLevelItemCount() == 2
        dlg.search.setText("FIC101")
        dlg.find()
        assert dlg.tree.topLevelItemCount() == 3
        for i in range(dlg.tree.topLevelItemCount()):
            dlg._pick_item(dlg.tree.topLevelItem(i))
        assert sorted(dlg.selected().values()) == ["FIC101.MV", "FIC101.PV", "FIC101.SP"]
        from PySide6.QtCore import QDateTime
        dlg.t_from.setDateTime(QDateTime.currentDateTime().addSecs(-3600))
        dlg.t_to.setDateTime(QDateTime.currentDateTime().addSecs(60))
        dlg.read_history()
        _wait(app)
        assert dlg.df is not None and set(dlg.df["Tag"]) == {"FIC101.PV", "FIC101.MV", "FIC101.SP"}
        w.project.load_frame(dlg.df, "opc")
        w.build()
        assert w.state.c_pv == "FIC101.PV" and w.state.c_mv == "FIC101.MV" and w.state.grid.has_sp
        dlg.done(0)
    finally:
        stop()


def test_rows_as_samples_desktop(win, tmp_path):
    """Soubor s neměnným časem: co řádek, to vzorek; perioda řádku z panelu Data (i v ms)."""
    from pidtools.app.dataio import ROWS
    app, win = win
    n = 200
    p = tmp_path / "const_time.csv"
    p.write_text("Time,CV,MV1\n" + "\n".join(f"Aug-04-07 20:47:20,{50 + 0.01 * i},{10 + (i // 50) % 2}"
                                             for i in range(n)), encoding="utf-8")
    assert win.open_path(p)
    _wait(app)
    s, d = win.state, win.pages[0]
    assert s.sig.time_src == [ROWS] and s.sig.time_note == "rows_auto" and s.grid.Ts == pytest.approx(1.0)
    assert d.c_time.currentData() == ROWS and "not recognised" in d.warn.text()
    d.tunit.setCurrentIndex(d.tunit.findData("ms"))
    d.row_dt.setValue(500)
    _wait(app)
    assert s.grid.Ts == pytest.approx(0.5) and s.sig.t_all[-1] == pytest.approx(0.5 * (n - 1))
