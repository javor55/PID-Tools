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
