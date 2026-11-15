"""Nastavení aplikace (E10-B), aplikační vrstva: výchozí hodnoty, ořezání, export / import, logo, dělení po uživatelích,
výchozí hodnoty nového projektu a smyčky."""
import json
import os

import pytest

from pidtools.app import appsettings as aps
from pidtools.app import triage
from pidtools.app.workspace.loops import Project


def test_defaults_are_normalized_and_stable():
    s = aps.normalize({})
    assert s["defaults"]["controller"] == "pcs7_pidconl" and s["general"]["autosave_min"] == 1
    assert s["diagnostics"]["thresholds"] == triage.default_thresholds()
    assert aps.normalize(s) == s                                   # normalizace je idempotentní


def test_normalize_clamps_and_drops_garbage():
    s = aps.normalize({"charts": {"height": 99999, "time_unit": "years"}, "general": {"autosave_min": 7},
                       "defaults": {"controller": "../etc", "sim": {"ctype": "XX", "opt_ms": 99}},
                       "connections": {"opc": [{"name": "A", "url": "opc.tcp://h:4840"}, {"name": "B", "url": "http://x"},
                                               {"name": "A", "url": "opc.tcp://dup"}, "junk"]},
                       "report": {"logo": "../../x.png", "company": " ACME "}, "unknown": 1})
    assert s["charts"] == dict(aps.DEFAULTS["charts"], height=1000)
    assert s["general"]["autosave_min"] == 1
    assert s["defaults"]["controller"] == "pcs7_pidconl" and s["defaults"]["sim"]["opt_ms"] == 2.5
    assert s["defaults"]["sim"]["ctype"] == "PI"
    assert s["connections"]["opc"] == [{"name": "A", "url": "opc.tcp://h:4840"}]
    assert s["report"]["logo"] == "" and s["report"]["company"] == "ACME" and "unknown" not in s


def test_store_roundtrip_and_isolation_per_user(tmp_path):
    st = aps.SettingsStore(str(tmp_path))
    assert st.load() == aps.normalize({})
    s = aps.normalize({"journal": {"author": "Eva"}})
    st.save(s, "alice@acme.com")
    assert st.load("alice@acme.com")["journal"]["author"] == "Eva"
    assert st.load("bob@acme.com")["journal"]["author"] == ""
    assert st.load()["journal"]["author"] == ""                    # desktop (bez uživatele) je samostatný
    evil = aps.user_dir(str(tmp_path), "../../x")
    assert os.path.dirname(evil) == str(tmp_path / "users")        # jméno nikdy nevyleze ze složky uživatelů


def test_corrupt_file_falls_back_to_defaults(tmp_path):
    (tmp_path / "settings.json").write_text("{nonsense", encoding="utf-8")
    assert aps.SettingsStore(str(tmp_path)).load() == aps.normalize({})


def test_export_import_and_rejects_foreign_or_newer():
    s = aps.normalize({"report": {"company": "ACME"}})
    assert aps.parse_export(aps.export_text(s)) == s
    for bad in ("nope", json.dumps({"format": "other", "version": 1}), json.dumps({"format": aps.FORMAT, "version": 99})):
        with pytest.raises(ValueError):
            aps.parse_export(bad)


def test_logo_validation_and_storage(tmp_path):
    st = aps.SettingsStore(str(tmp_path))
    s = st.put_logo(b"\x89PNG", "PNG")
    assert s["report"]["logo"] == "logo.png" and st.logo_path().endswith("logo.png")
    st.put_logo(b"\xff\xd8", "jpg")                               # nové logo nahradí staré (jeden soubor)
    assert not (tmp_path / "logo.png").exists()
    for data, ext in ((b"x", "exe"), (b"", "png"), (b"x" * (aps.MAX_LOGO + 1), "png"), (b"<svg/>", "svg")):   # SVG se nepřijímá
        with pytest.raises(ValueError):
            st.put_logo(data, ext)
    assert st.drop_logo()["report"]["logo"] == "" and st.logo_path() is None


def test_new_project_takes_defaults_from_settings():
    thr = triage.default_thresholds()
    first = next(iter(thr))
    key = next(iter(thr[first]))
    s = aps.normalize({"diagnostics": {"thresholds": {first: {key: thr[first][key] * 1.2}}},
                       "defaults": {"sim": {"ctype": "PID", "opt_ms": 2.0}}})
    profile = {"id": "mine", "name": "Mine", "structure": {}, "params": []}
    p = Project(aps.new_project_defaults(s, profile))
    ws = p.state
    assert ws.controller == profile and ws.controller is not profile       # kopie, ne sdílený objekt
    assert ws.get("ctype") == "PID" and ws.get("opt_ms") == 2.0
    assert json.loads(ws.get("tri_thr"))[first][key] == pytest.approx(thr[first][key] * 1.2, rel=1e-6)
    p.load_demo()                                                   # data nahradí smyčku, výchozí hodnoty zůstanou
    assert p.state.controller == profile and p.state.get("ctype") == "PID" and p.state.get("tri_thr")
    p.add_loop()
    assert p.loops[1].controller == profile and p.loops[1].get("ctype") == "PID"


def test_default_settings_leave_new_project_untouched():
    p = Project(aps.new_project_defaults(aps.normalize({})))
    assert p.state.controller is None and p.state.get("tri_thr") is None and p.state.get("ctype") == "PI"


def test_change_counter_and_saved_marks():
    p = Project()
    p.touch()
    p.touch()
    assert p.rev == 2 and p.saved_rev == 0
    p.mark_saved()
    assert p.saved_rev == 2 and p.saved_at
    p.mark_loaded()
    p.touch()                                                       # změna způsobená samotným načtením se nepočítá
    assert p.rev == 2 and p.saved_rev == 2
    p.touch()
    assert p.rev == 3 and p.saved_rev == 2
