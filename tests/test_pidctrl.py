"""Formát .pidctrl: kontrola, uložení a načtení, migrace, knihovna (předvolby + vlastní), robustnost podle profilu."""
import copy
import json

import numpy as np
import pytest

from pidtools import controllers, core
from pidtools.controllers import Library, ProfileError, loader
from pidtools.core.controller import Profile, ideal_ctrl


def _preset(pid="isa_ideal"):
    return copy.deepcopy(controllers.load_preset(pid))


@pytest.mark.parametrize("pid", controllers.presets())
def test_presets_are_valid_and_compile(pid):
    p = controllers.load_preset(pid)
    assert controllers.validate_profile(p) == []
    Profile(p)
    if p["verification"]["status"] != "verified":
        assert "neověřeno" in p["verification"]["note"] or pid == "pcs7_pidconl"


def test_expected_presets():
    ids = set(controllers.presets())
    assert {"pcs7_pidconl", "isa_ideal", "isa_parallel", "isa_series", "siemens_cont_c", "siemens_pid_compact"} <= ids
    assert controllers.load_preset("isa_ideal")["verification"]["status"] == "verified"
    assert controllers.load_preset("siemens_cont_c")["verification"]["status"] == "unverified"


@pytest.mark.parametrize("mutate,path", [
    (lambda p: p.update(id="Má Mezeru"), "id"),
    (lambda p: p.update(name=""), "name"),
    (lambda p: p["verification"].update(status="asi"), "verification.status"),
    (lambda p: p["params"][0].update(range=[5, 1]), "params[0].range"),
    (lambda p: p["params"][0].update(repr="zzz"), "params[0].repr"),
    (lambda p: p["params"].append(dict(key="Kc", role="Xx")), "params"),
    (lambda p: p["params"].append("x"), "params["),
])
def test_validation_reports_path(mutate, path):
    p = _preset()
    mutate(p)
    bad = controllers.validate_profile(p)
    assert bad and any(path in b["path"] for b in bad), bad
    with pytest.raises(ProfileError):
        controllers.library.check(p)


def test_validation_header_errors():
    assert "není profil" in controllers.validate_profile({})[0]["message"]
    assert "novější" in controllers.validate_profile(dict(_preset(), version=99))[0]["message"]


def test_save_load_round_trip(tmp_path):
    p = _preset("pcs7_pidconl")
    f = tmp_path / "x.pidctrl"
    f.write_text(controllers.dumps(p), encoding="utf-8")
    assert controllers.load_profile(f) == p
    assert json.loads(f.read_text(encoding="utf-8"))["format"] == "pidctrl"


def test_migration_hook(monkeypatch):
    """Starší verze se převedou řetězcem MIGRATIONS na aktuální."""
    monkeypatch.setattr(loader, "VERSION", 2)
    monkeypatch.setitem(loader.MIGRATIONS, 1, lambda d: dict(d, version=2, migrated=True))
    out = controllers.parse_profile(_preset())
    assert out["version"] == 2 and out["migrated"] is True


# ---- knihovna
def test_library_lifecycle(tmp_path):
    lib = Library(str(tmp_path))
    assert {s["tag"] for s in lib.list()} == {"preset"}
    c = lib.create_custom("pcs7_pidconl", "Můj PID")
    assert c["id"] == "custom_muj_pid" and c["derived_from"] == "pcs7_pidconl"
    assert c["verification"]["status"] == "unverified"
    assert next(s for s in lib.list() if s["id"] == c["id"])["tag"] == "custom"
    assert (tmp_path / "custom_muj_pid.pidctrl").exists()
    assert lib.create_custom("pcs7_pidconl", "Můj PID")["id"] == "custom_muj_pid_2"
    c["name"] = "Přejmenovaný"
    assert lib.update(c["id"], c)["name"] == "Přejmenovaný" and lib.get(c["id"])["name"] == "Přejmenovaný"
    lib.delete(c["id"])
    with pytest.raises(KeyError):
        lib.get(c["id"])


def test_library_presets_read_only(tmp_path):
    lib = Library(str(tmp_path))
    with pytest.raises(PermissionError):
        lib.update("isa_ideal", _preset())
    with pytest.raises(PermissionError):
        lib.delete("isa_ideal")
    with pytest.raises(KeyError):
        lib.get("neexistuje")
    p = lib.get("isa_ideal")
    p["name"] = "změna kopie"
    assert controllers.load_preset("isa_ideal")["name"] != "změna kopie"       # kopie, předvolba zůstává


def test_library_import_export(tmp_path):
    lib = Library(str(tmp_path))
    text = lib.export_profile("isa_parallel")
    data = json.loads(text)
    assert data["format"] == "pidctrl" and data["id"] == "isa_parallel"
    imp = lib.import_profile(data)                                   # id koliduje s předvolbou → nové
    assert imp["id"].startswith("custom_") and lib.get(imp["id"])["params"] == data["params"]
    with pytest.raises(ProfileError):
        lib.import_profile({"format": "pidctrl", "version": 1, "id": "x", "structure": {}, "params": [{"key": 1}]})


def test_library_survives_broken_file(tmp_path):
    (tmp_path / "rozbity.pidctrl").write_text("{nesmysl", encoding="utf-8")
    assert all(s["tag"] == "preset" for s in Library(str(tmp_path)).list())


def test_default_dir_env(monkeypatch, tmp_path):
    monkeypatch.setenv("PIDTOOLS_CONTROLLERS_DIR", str(tmp_path))
    assert controllers.default_dir() == str(tmp_path) and Library().folder == str(tmp_path)


# ---- robustnost podle profilu
CTRL = dict(Gain=1.2, TI=30.0, TD=4.0, DiffGain=5.0, SampleTime=1.0, MV_Lo=0.0, MV_Hi=100.0, PVFilt=1.5)
MODEL = ("P1D", [1.0, 20.0, 4.0])


def test_robustness_for_pidconl_is_identical():
    fn = core.robustness_for(controllers.load_preset("pcs7_pidconl"))
    for ctrl in (CTRL, dict(CTRL, TI=np.inf), dict(CTRL, TD=0.0, PVFilt=0.0), dict(CTRL, Gain=3.0, DiffGain=12.0)):
        assert fn(*MODEL, ctrl) == core.robustness(*MODEL, ctrl)
    assert ideal_ctrl(controllers.load_preset("pcs7_pidconl"), CTRL)["DiffGain"] == 5.0


def test_robustness_for_other_forms_matches_ideal():
    """Paralelní, sériová i jednotky (PB, min) dávají stejné Ms jako ekvivalentní ideální PIDConL."""
    canon = dict(Kc=1.2, Ti=30.0, Td=4.0, b=1.0, c=1.0, N=5.0)
    for pid in ("isa_ideal", "isa_parallel", "isa_series", "siemens_pid_compact", "siemens_cont_c"):
        prof = controllers.load_preset(pid)
        vals = controllers.canonical_to_profile(prof, canon)["values"]
        vals.update({p["key"]: 1.0 for p in prof["params"] if p["role"] == "Ts"})
        vals.update({p["key"]: 1.5 for p in prof["params"] if p["role"] == "pv_filter"})
        ref = core.robustness(*MODEL, dict(CTRL, PVFilt=1.5 if "pv_filter" in {p["role"] for p in prof["params"]} else 0.0))
        rb = core.robustness_for(prof)(*MODEL, vals)
        assert rb["Ms"] == pytest.approx(ref["Ms"], rel=1e-6), pid
        assert rb["stable"] == ref["stable"] and rb["PM"] == pytest.approx(ref["PM"], rel=1e-6), pid


def test_robustness_with_gain_in_pb():
    prof = copy.deepcopy(controllers.load_preset("isa_ideal"))
    next(p for p in prof["params"] if p["role"] == "Kc")["repr"] = "PB"
    vals = dict(Kc=100 / 1.2, Ti=30.0, Td=4.0, N=5.0, SampleTime=1.0, pv=None)
    vals.pop("pv")
    vals["PVFilt"] = 1.5
    rb = core.robustness_for(prof)(*MODEL, vals)
    assert rb["Ms"] == pytest.approx(core.robustness(*MODEL, CTRL)["Ms"], rel=1e-6)
