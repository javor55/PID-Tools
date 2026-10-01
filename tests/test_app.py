"""
Testy celé aplikace přes Streamlit AppTest: průchod všemi záložkami a funkcemi, uložení a obnova projektu,
přepnutí jazyka. Běží na ukázkových datech (hladina s měřeným přítokem).
"""
import json
import os

import pytest
from streamlit.testing.v1 import AppTest

from pidtools.core import MODELS

WRAPPER = os.path.join(os.path.dirname(__file__), "_app_wrapper.py")
TIMEOUT = 900


def _errors(at):
    """Výjimky a chybová hlášení aplikace (bez očekávaného hlášení o nestabilní výchozí sadě)."""
    exc = [x.message for x in at.exception]
    errs = [e.value for e in at.error if "Set 1" not in e.value]
    return exc + errs


def _button(at, label):
    return next(b for b in at.button if b.label == label)


@pytest.fixture(scope="module")
def app():
    at = AppTest.from_file(WRAPPER, default_timeout=TIMEOUT)
    at.run()
    at.session_state["src"] = "demo"
    at.run()
    at.session_state["c_d|demo"] = ["FI100.Pritok"]
    at.session_state["set1_gain"], at.session_state["set1_ti"] = -2.0, 200.0
    at.run()
    _button(at, "Identify").click().run()
    assert not _errors(at)
    return at


def test_start_without_data():
    at = AppTest.from_file(WRAPPER, default_timeout=TIMEOUT)
    at.run()
    assert not at.exception
    assert len(at.tabs) == 0          # bez dat se záložky nezobrazí


def test_identification(app):
    assert app.session_state["mcode"] in MODELS
    fits = [float(m.value.rstrip(" %")) for m in app.metric if m.label.startswith("Fit – identified")]
    assert fits and fits[0] > 95
    assert len(app.tabs) == 6


@pytest.mark.parametrize("method", ["SIMC", "iSIMC", "Lambda", "AMIGO", "AVG", "OPT"])
def test_tuning_methods(app, method):
    app.session_state[f"method|{app.session_state['mcode']}"] = method
    app.run()
    assert not _errors(app)


@pytest.mark.parametrize("crit", ["MIGO", "IAE", "ISE", "ITAE", "OVS"])
def test_optimization_criteria(app, crit):
    app.session_state[f"method|{app.session_state['mcode']}"] = "OPT"
    app.session_state["opt_crit"] = crit
    app.run()
    assert not _errors(app)


def test_scenario_target_and_sets(app):
    app.session_state["opt_crit"], app.session_state["opt_target"], app.session_state["ctype"] = "IAE", "scen", "PID"
    app.run()
    app.run()
    assert not _errors(app)
    _button(app, "Write to Set 2").click().run()
    assert not _errors(app)
    app.session_state["pvfilt"], app.session_state["mvrate"] = 2.0, 0.5
    app.session_state["scen2"] = "replay"
    app.run()
    assert not _errors(app)
    app.session_state["scen2"] = "custom"
    app.run()


def test_validation(app):
    app.session_state["pending_rngv"] = (2000.0, 3599.0)
    app.run()
    app.run()
    pred = [float(m.value.rstrip(" %")) for m in app.metric if m.label == "PV prediction fit"]
    assert pred and pred[0] > 90
    for mode, which in (("cl", "cur"), ("cl", "new"), ("pred", "cur")):
        app.session_state["val_mode"], app.session_state["val_which"] = mode, which
        app.run()
        assert not _errors(app)


def test_live_simulation(app):
    """Živá simulace běží v prohlížeči: stránka vloží komponentu s jádrem a konfigurací obou sad."""
    tabs = [t.label for t in app.tabs]
    app.session_state["main_tab"] = tabs[3]
    app.run()
    assert not _errors(app)
    frames = app.get("iframe")
    assert len(frames) == 1
    doc = frames[0].proto.srcdoc
    assert "PIDLive" in doc and '"sets": {"1"' in doc and '"code": "' + app.session_state["mcode"] + '"' in doc
    app.session_state["main_tab"] = tabs[0]
    app.run()


def test_model_tools(app):
    mc = app.session_state["mcode"]
    app.session_state["unc_n"] = 5
    _button(app, "Compute uncertainty").click().run()
    assert not _errors(app)
    ith = len(MODELS[mc]["params"]) - 1
    app.session_state[f"fx|{mc}|{ith}"], app.session_state[f"ed|{mc}|{ith}"] = True, 8.0
    _button(app, "Refit").click().run()
    app.run()
    assert not _errors(app)
    assert app.session_state[f"ed|{mc}|{ith}"] == 8.0
    app.session_state["dist_level"], app.session_state["id_stic"], app.session_state["chosen"] = "high", True, ["I1D"]
    app.run()
    _button(app, "Identify").click().run()
    assert not _errors(app)


def test_lazy_tabs_and_comparison(app):
    """Grafy se posílají jen pro aktivní záložku; porovnání metod se počítá až po rozbalení."""
    labels = [t.label for t in app.tabs]
    n_charts = {}
    for lbl in labels:
        app.session_state["main_tab"] = lbl
        app.run()
        assert not _errors(app)
        n_charts[lbl] = len(app.get("plotly_chart"))
    assert n_charts[labels[0]] > 0 and n_charts[labels[5]] == 0   # Data má grafy, Projekt žádné
    app.session_state["main_tab"] = labels[2]
    app.run()
    n_df = len(app.dataframe)
    app.session_state["cmp_open"] = True
    app.run()
    assert not _errors(app)
    assert len(app.dataframe) == n_df + 1
    app.session_state["cmp_open"] = False
    app.session_state["main_tab"] = labels[0]
    app.run()


def test_other_tabs(app):
    for k, v in (("perf_compare", True), ("cas_om", "OPT")):
        app.session_state[k] = v
        app.run()
        assert not _errors(app)


def test_report_project_roundtrip_and_language(app):
    _button(app, "Create report").click().run()
    assert app.session_state["report_html"].startswith("<!doctype html>")
    _button(app, "Prepare project").click().run()
    proj = json.loads(app.session_state["proj_json"])
    assert proj["version"] == 2 and proj["data"] and proj["fit"]

    at2 = AppTest.from_file(WRAPPER, default_timeout=TIMEOUT)
    at2.session_state["test_inject"] = json.dumps(proj)
    at2.run()
    at2.run()
    assert not at2.exception
    assert at2.session_state["src"] == "project"
    assert at2.session_state["mcode"] == app.session_state["mcode"]
    assert at2.session_state["set2_gain"] == pytest.approx(app.session_state["set2_gain"])
    # přepnutí jazyka zachová stav (model, sady, výběr sloupců)
    at2.session_state["lang"] = "cs"
    at2.run()
    assert not at2.exception
    assert at2.session_state["mcode"] == app.session_state["mcode"]
    assert any(t.label.startswith("4 · Živá") for t in at2.tabs)


def test_legacy_project_v1():
    """Projekt ze starší verze (Set 1 v „current“, nové parametry v „new“) se načte a nové parametry jdou do Set 2."""
    path = os.path.join(os.path.dirname(__file__), "data", "project_v1.json")
    proj = json.load(open(path, encoding="utf-8"))
    at = AppTest.from_file(WRAPPER, default_timeout=TIMEOUT)
    at.session_state["test_inject"] = json.dumps(proj)
    at.run()
    at.run()
    assert not at.exception
    assert at.session_state["set2_gain"] == pytest.approx(proj["new"]["Gain"])
