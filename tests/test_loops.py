"""Více smyček v projektu: přidání, samostatná identifikace a ladění, přepínání, kaskáda, uložení a obnova."""
import json
import os

import pytest
from streamlit.testing.v1 import AppTest

from pidtools.ui.project import serialize_project

WRAPPER = os.path.join(os.path.dirname(__file__), "_app_wrapper.py")
TIMEOUT = 900


def _main(at):
    """Hlavní záložky aplikace (vnořené záložky, např. pohledy v Ladění, se nepočítají)."""
    return [t for t in at.tabs if t.label[:1].isdigit()]


def _ok(at):
    exc = [x.message for x in at.exception]
    errs = [e.value for e in at.error if "Set 1" not in e.value]
    assert not exc and not errs, exc + errs


def _button(at, label):
    return next(b for b in at.button if b.label == label)


def _switcher(at):
    return next(g for g in at.get("button_group") if g.label == "Loop")


@pytest.fixture(scope="module")
def two_loops():
    at = AppTest.from_file(WRAPPER, default_timeout=TIMEOUT)
    at.run()
    at.session_state["src"] = "demo"
    at.run()
    at.session_state["c_d|demo"] = ["FI100.Pritok"]
    at.session_state["set1_gain"], at.session_state["set1_ti"] = -2.0, 200.0
    at.session_state["loop_tag"] = "LIC101"
    at.run()
    _button(at, "Identify").click().run()
    _ok(at)
    mcode1 = at.session_state["mcode"]
    # druhá smyčka: prázdný stav, vlastní identifikace a ladění
    _button(at, "Another loop").click().run()
    _ok(at)
    assert at.session_state["loops"]["ids"] == [1, 2] and at.session_state["loops"]["active"] == 2
    assert "fit" not in at.session_state and "set1_gain" not in at.session_state
    assert at.session_state["loop_tag"] == "Loop 2" and at.session_state["main_tab"].startswith("1")
    at.session_state["loop_tag"] = "FIC100"
    at.session_state["chosen"] = ["P1D"]
    at.session_state["set1_gain"] = 0.5
    at.run()
    _button(at, "Identify").click().run()
    _ok(at)
    assert at.session_state["mcode"] == "P1D"
    return at, mcode1


def test_switch_keeps_each_loop(two_loops):
    at, mcode1 = two_loops
    assert _switcher(at).options == ["LIC101", "FIC100"]
    _switcher(at).set_value(1).run()
    _ok(at)
    assert at.session_state["loops"]["active"] == 1
    assert at.session_state["mcode"] == mcode1 and at.session_state["set1_gain"] == -2.0
    assert at.session_state["loop_tag"] == "LIC101"
    _switcher(at).set_value(2).run()
    _ok(at)
    assert at.session_state["mcode"] == "P1D" and at.session_state["set1_gain"] == 0.5
    _switcher(at).set_value(1).run()


def test_cascade_inner_from_other_loop(two_loops):
    at, _ = two_loops
    assert at.session_state["loops"]["active"] == 1
    at.session_state["cas_src"] = "loop"
    at.session_state["cas_iloop"] = 2
    at.run()
    _ok(at)
    assert any("Model of loop FIC100" in c.value for c in at.caption)


def test_project_roundtrip_two_loops(two_loops):
    at, mcode1 = two_loops
    at.session_state["main_tab"] = [t.label for t in _main(at)][5]
    at.run()
    proj = json.loads(serialize_project(at.session_state["_proj_payload"]))
    _button(at, "Create report").click().run()
    _ok(at)
    rep = at.session_state["report_html"]
    assert "LIC101" in rep and "FIC100" in rep                       # report pokrývá všechny smyčky
    at.session_state["main_tab"] = [t.label for t in _main(at)][0]
    at.run()
    assert len(proj["loops"]) == 2 and proj["active"] == 1
    assert [r["tag"] for r in proj["loops"]] == ["LIC101", "FIC100"]

    at2 = AppTest.from_file(WRAPPER, default_timeout=TIMEOUT)
    at2.session_state["test_inject"] = json.dumps(proj)
    at2.run()
    at2.run()
    _ok(at2)
    assert at2.session_state["loops"]["ids"] == [1, 2]
    assert at2.session_state["mcode"] == mcode1 and at2.session_state["set1_gain"] == -2.0
    _switcher(at2).set_value(2).run()
    _ok(at2)
    assert at2.session_state["mcode"] == "P1D" and at2.session_state["set1_gain"] == 0.5


def test_apc_pages(two_loops):
    """Rozvazbení, override a Smithův prediktor se dvěma smyčkami (vazby přes měřené poruchy)."""
    at, _ = two_loops
    _switcher(at).set_value(2).run()
    at.session_state["c_mv|demo"] = "FI100.Pritok"
    at.session_state["c_d|demo"] = ["LIC101.MV"]
    at.run()
    _button(at, "Identify").click().run()
    _ok(at)
    _switcher(at).set_value(1).run()
    for kind in ("decouple", "override", "smith"):
        at.session_state["apc_kind"] = kind
        if kind != "smith":
            at.session_state[f"apc_{kind}_b"] = 2
        at.run()
        _ok(at)
    at.session_state["apc_kind"] = "decouple"
    at.run()
    assert any(m.label == "RGA λ₁₁" for m in at.metric)
    assert any("**When to use**" in m.value for m in at.markdown)                 # průvodce
    assert any("FfwdDisturbCompensat" in m.value for m in at.markdown)          # implementace v APL
    # smyčky se stejnou MV → doporučení override; tlačítko v záložce Ladění přepne na záložku APC
    at.session_state["apc_kind"] = "cascade"
    _switcher(at).set_value(2).run()
    at.session_state["c_mv|demo"], at.session_state["c_d|demo"] = "LIC101.MV", []
    at.run()
    _switcher(at).set_value(1).run()
    _ok(at)
    hint = next(b for b in at.button if b.key == "g_tuning_apc")
    hint.click().run()
    _ok(at)
    assert at.session_state["main_tab"] == "5 · APC" and at.session_state["apc_kind"] == "override"
    at.session_state["apc_kind"] = "cascade"
    at.session_state["main_tab"] = "1 · Data"
    at.run()


def test_remove_loop(two_loops):
    at, _ = two_loops
    _switcher(at).set_value(2).run()
    _button(at, "Remove loop FIC100").click().run()
    _ok(at)
    assert at.session_state["loops"]["ids"] == [1] and at.session_state["loops"]["active"] == 1
    assert at.session_state["loop_tag"] == "LIC101"
    assert any(b.label == "Another loop" for b in at.button)


def test_rename_loop_from_menu(two_loops):
    """Název smyčky z menu smyček (pole „Loop name“) přejmenuje aktivní smyčku v přepínači."""
    at, _ = two_loops
    if len(at.session_state["loops"]["ids"]) == 1:     # menu smyček je vidět od dvou smyček
        _button(at, "Another loop").click().run()
    fld = next(x for x in at.text_input if x.label == "Loop name")
    fld.set_value("TIC300").run()
    _ok(at)
    lp = at.session_state["loops"]
    assert at.session_state["loop_tag"] == "TIC300" and lp["info"][lp["active"]]["name"] == "TIC300"
