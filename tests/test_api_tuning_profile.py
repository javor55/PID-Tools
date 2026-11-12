"""
API – ladění podle profilu regulátoru smyčky (E8-B): návrh a sady v jednotkách bloku (PIDConL shodné s dosavadními
čísly, sériová forma ISA s převodem a varováním), simulace a robustnost přes profil, tabulka robustnosti, proces a ventil,
varování a export pro řídicí systém (registr formátů s popisky v obou jazycích).
"""
import json
import os
import sys
import time

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from pidtools.api import create_app  # noqa: E402
from pidtools.app import tuning_export as tex  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
import golden  # noqa: E402

REF = golden.load("demo_common")


def _wait(client, job, t=600):
    t0 = time.time()
    while time.time() - t0 < t:
        st = client.get(f"/jobs/{job['id']}").json()
        if st["state"] not in ("queued", "running"):
            assert st["state"] == "done", st
            return
        time.sleep(0.2)
    raise AssertionError("job timeout")


@pytest.fixture()
def ws(tmp_path):
    with TestClient(create_app(controllers_dir=str(tmp_path))) as c:
        wid = c.post("/workspaces").json()["id"]
        c.post(f"/workspaces/{wid}/data/demo")
        c.patch(f"/workspaces/{wid}/settings", json={"chosen": ["P1D", "I1D"]})
        _wait(c, c.post(f"/workspaces/{wid}/identify").json())
        yield c, f"/workspaces/{wid}"


def test_pidconl_default_in_block_units(ws):
    c, w = ws
    info = c.get(f"{w}/tuning").json()
    assert info["controller"]["id"] == "pcs7_pidconl" and info["controller"]["is_default"]
    assert [p["name"] for p in info["tuning_params"]] == ["Gain", "TI", "TD"]
    assert {"SampleTime", "DiffGain", "PropFacSP", "MV_Lo"} <= {p["key"] for p in info["block_params"]} | {"DiffGain"}
    for m, ref in REF["tuning"].items():
        s = c.post(f"{w}/tuning/suggest", json={"method": m}).json()
        assert golden.compare({k: ref[k] for k in ("Kc", "Ti", "Td")}, {k: s[k] for k in ("Kc", "Ti", "Td")}) == [], m
        assert (s["values"]["Gain"], s["values"]["TI"], s["values"]["TD"]) == pytest.approx((s["Kc"], s["Ti"], s["Td"]))
        assert s["warnings"] == [] and s["robust"]["Ms"] > 1 and not s["approximate"]
    s1 = info["sets"][0]
    assert (s1["values"]["Gain"], s1["values"]["TI"]) == pytest.approx((s1["gain"], s1["ti"]))


def test_isa_series_converted_with_warning(ws):
    c, w = ws
    assert c.put(f"{w}/controller", json={"from_id": "isa_series"}).status_code == 200
    info = c.get(f"{w}/tuning").json()
    assert [p["name"] for p in info["tuning_params"]] == ["Kc", "Ti", "Td"] and info["controller"]["id"] == "isa_series"
    # kanonická sada Ti < 4·Td nemá sériový ekvivalent: nejbližší proveditelná hodnota + varování
    s = c.put(f"{w}/tuning/sets/2", json={"Kc": 2.0, "Ti": 20.0, "Td": 10.0}).json()["sets"][1]
    assert (s["gain"], s["ti"], s["td"]) == (2.0, 20.0, 10.0)           # ukládá se kanonicky
    assert s["values"]["Kc"] == pytest.approx(1.0) and s["values"]["Ti"] == pytest.approx(10.0)
    assert [x["key"] for x in s["warnings"]] == ["ctl_w_series_limit"] and s["warnings"][0]["text"]
    # sada zadaná v jednotkách bloku se uloží jako kanonická (zpětný převod)
    s = c.put(f"{w}/tuning/sets/1", json={"values": {"Kc": -1.0, "Ti": 200.0, "Td": 5.0}}).json()["sets"][0]
    assert s["values"]["Kc"] == pytest.approx(-1.0) and s["values"]["Td"] == pytest.approx(5.0)
    assert c.put(f"{w}/tuning/sets/1", json={}).status_code == 422
    t = c.post(f"{w}/tuning/suggest", json={"method": "SIMC", "tc": 77.0}).json()            # τc zadané uživatelem
    assert t["tc"] == 77.0 and c.post(f"{w}/tuning/suggest", json={"method": "SIMC"}).json()["tc"] != 77.0
    # simulace a robustnost přes profil
    kp = c.post(f"{w}/simulate", json={}).json()["kpis"]
    assert kp["1"] is not None
    rows = {r["name"]: r for r in c.post(f"{w}/tuning/robustness").json()}
    assert rows["set1"]["stable"] and {"Ms", "Mt", "GM", "PM"} <= set(rows["set1"]) and rows["set1"]["Mt"] > 0


def test_ideal_profile_equals_pidconl(ws):
    """Ideální ISA forma = kanonický tvar PIDConL: simulace i robustnost musí vyjít stejně."""
    c, w = ws
    c.put(f"{w}/tuning/sets/2", json={"Kc": -4.0, "Ti": 200.0, "Td": 0.0})
    a = c.post(f"{w}/simulate", json={}).json()["kpis"]["2"]
    ra = {r["name"]: r for r in c.post(f"{w}/tuning/robustness").json()}["set2"]
    c.put(f"{w}/controller", json={"from_id": "isa_ideal"})
    b = c.post(f"{w}/simulate", json={}).json()["kpis"]["2"]
    rb = {r["name"]: r for r in c.post(f"{w}/tuning/robustness").json()}["set2"]
    assert b["iae"] == pytest.approx(a["iae"], rel=1e-6)
    assert (rb["Ms"], rb["GM"], rb["PM"]) == pytest.approx((ra["Ms"], ra["GM"], ra["PM"]), rel=1e-6)


def test_plant_and_warnings(ws):
    c, w = ws
    p = c.get(f"{w}/tuning/plant").json()
    assert len(p["vchar"]) == 10 and p["slip"] == 100.0 and len(p["curve_x"]) == 11
    k0 = c.post(f"{w}/simulate", json={}).json()["kpis"]["1"]["mv_travel"]
    p = c.put(f"{w}/tuning/plant", json={"noise": 0.3, "stic": 0.5, "vchar": [1.0] * 9 + [2.0]}).json()
    assert p["noise"] == 0.3 and p["stic"] == 0.5 and p["vchar"][-1] == 2.0
    assert c.post(f"{w}/simulate", json={}).json()["kpis"]["1"]["mv_travel"] != k0       # proces a ventil se projeví
    assert c.put(f"{w}/tuning/plant", json={"vchar": [1.0]}).status_code == 422
    assert c.get(f"{w}/tuning/warnings").json() == []
    c.patch(f"{w}/settings", json={"pv_hi": 1.0, "pv_lo": 0.0})
    assert [x["key"] for x in c.get(f"{w}/tuning/warnings").json()][:1] == ["norm_out"]


def test_export_formats(ws):
    c, w = ws
    assert c.get(f"{w}/tuning").json()["export_formats"] == list(tex.FORMATS)
    c.put(f"{w}/controller", json={"from_id": "siemens_cont_c"})
    c.put(f"{w}/tuning/sets/2", json={"Kc": 2.0, "Ti": 50.0, "Td": 0.0})
    for fmt in tex.FORMATS:
        r = c.get(f"{w}/tuning/export", params={"fmt": fmt})
        assert r.status_code == 200 and "attachment" in r.headers["content-disposition"], fmt
        assert all(k in r.text for k in ("GAIN", "TI", "TD", "TM_LAG")), fmt                # názvy parametrů bloku
        assert "LMN_HLM" in r.text
    t = c.get(f"{w}/tuning/export", params={"fmt": "pcs7"}).text
    assert "GAIN := 2;" in t and "UNVERIFIED" in t                                           # neověřený profil
    csv = c.get(f"{w}/tuning/export", params={"fmt": "csv"}).text.splitlines()
    assert csv[0] == "parameter;unit;set_1;set_2" and any(x.startswith("Ms;") for x in csv)
    assert c.get(f"{w}/tuning/export", params={"fmt": "nope"}).status_code == 422


def test_export_registry_labels():
    root = os.path.join(os.path.dirname(HERE), "pidtools", "i18n")
    for lang in ("cs", "en"):
        tr = json.load(open(os.path.join(root, f"{lang}.json"), encoding="utf-8"))
        for fmt in tex.FORMATS:
            assert tr.get(f"tun_ui_exp_{fmt}"), (lang, fmt)
