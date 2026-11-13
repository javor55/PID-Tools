"""
API – ladění a simulace (M10): návrhy metod, robustnost sad, scénář, simulace a frekvenční charakteristiky
shodné se zlatým případem demo_common; zápis sady a historie, porovnání metod (úloha), vlastní scénář.
"""
import os
import sys
import time

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from pidtools.api import create_app  # noqa: E402
from pidtools.app import signalpack  # noqa: E402

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
            return st
        time.sleep(0.2)
    raise AssertionError("job timeout")


@pytest.fixture(scope="module")
def ws():
    with TestClient(create_app()) as c:
        wid = c.post("/workspaces").json()["id"]
        c.post(f"/workspaces/{wid}/data/demo")
        c.patch(f"/workspaces/{wid}/settings", json={"chosen": ["P1D", "I1D"]})
        _wait(c, c.post(f"/workspaces/{wid}/identify").json())
        yield c, wid


def test_suggestions_like_golden(ws):
    c, wid = ws
    info = c.get(f"/workspaces/{wid}/tuning").json()
    assert info["model"] == "I1D"
    assert set(info["methods"]) == set(REF["tuning"])
    s1 = next(s for s in info["sets"] if s["n"] == 1)
    assert golden.compare({k: v for k, v in REF["set1_metrics"].items()},
                          {k: s1["metrics"][k] for k in REF["set1_metrics"]}) == []
    for m, ref in REF["tuning"].items():
        s = c.post(f"/workspaces/{wid}/tuning/suggest", json={"method": m}).json()
        assert golden.compare({k: ref[k] for k in ("Kc", "Ti", "Td")}, {k: s[k] for k in ("Kc", "Ti", "Td")}) == [], m
        assert [n["key"] for n in s["notes"]] == ref["notes"], m
    assert c.post(f"/workspaces/{wid}/tuning/suggest", json={"method": "NOPE"}).status_code == 422


def test_simulation_and_frequency_like_golden(ws):
    c, wid = ws
    sug = c.post(f"/workspaces/{wid}/tuning/suggest", json={"method": "SIMC"}).json()
    pid = {k: sug[k] for k in ("Kc", "Ti", "Td")}
    sim = c.post(f"/workspaces/{wid}/simulate", json={"preview": pid}).json()
    assert sim["T_end"] == REF["scenario"]["T_end"]
    for name, key in (("set1", "1"), ("sug", "sug")):
        k = sim["kpis"][key]
        got = {n: k[n] for n in ("iae", "maxdev", "mv_travel", "reversals")}
        got.update({f"step_{n}": k["step"][n] for n in ("t90", "over", "settle")})
        assert golden.compare(REF["scenario"][name], got) == [], name
    meta, sig = signalpack.unframe(c.post(f"/workspaces/{wid}/simulate/curves", json={"preview": pid}).content)
    assert {"sp", "pv_1", "mv_1", "pv_2", "pv_sug", "mv_sug"} <= set(sig)
    fr = {f["name"]: f for f in c.post(f"/workspaces/{wid}/frequency", json=pid).json()}
    for name in ("set1", "sug"):
        assert golden.compare(REF["frequency"][name]["bw"], fr[name]["bw"]) == [], name
        assert golden.compare(REF["frequency"][name]["Ms"], 10 ** (max(fr[name]["S_db"]) / 20)) == [], name
    assert fr["set1"]["stable"] and len(fr["set1"]["w"]) == len(fr["set1"]["mag_db"]) > 100


def test_sets_history_scenario_compare(ws):
    c, wid = ws
    t = c.put(f"/workspaces/{wid}/tuning/sets/2", json={"Kc": -4.0, "Ti": 200.0, "Td": 0.0,
                                                         "log": {"method": "SIMC"}}).json()
    s2 = next(s for s in t["sets"] if s["n"] == 2)
    assert (s2["gain"], s2["ti"]) == (-4.0, 200.0) and s2["metrics"]["stable"]
    assert t["history"][0]["method"] == "SIMC" and t["history"][0]["set"] == 2
    sc = c.get(f"/workspaces/{wid}/scenario").json()
    assert sc["kind"] in sc["kinds"] and sc["rows"]
    sc = c.put(f"/workspaces/{wid}/scenario", json={"kind": "in"}).json()
    assert sc["kind"] == "in"
    assert c.put(f"/workspaces/{wid}/scenario", json={"kind": "xx"}).status_code == 422
    job = c.post(f"/workspaces/{wid}/tuning/compare").json()
    _wait(c, job)
    res = c.get(f"/jobs/{job['id']}/result").json()
    assert res and isinstance(res, (dict, list))


def test_live_config(ws):
    """Konfigurace živé simulace: klíče pro live_ui.js, sady shodné s laděním, jazyk textů podle požadavku."""
    c, wid = ws
    cfg = c.get(f"/workspaces/{wid}/live").json()
    assert {"code", "p", "h", "pv0", "mv0", "plant", "window", "speeds", "speed0", "sets", "pv_lo", "pv_hi", "mv_lo",
            "mv_hi", "lab_pv", "lab_mv", "font", "labels", "sim_id", "ch", "noise0", "pvf0", "pvf_max", "dist_p0",
            "dist_pmax", "decimal", "light", "dark"} <= set(cfg)
    assert cfg["code"] == "I1D" and set(cfg["sets"]) == {"1", "2"} and cfg["window"] >= 60
    assert cfg["labels"]["start"] and cfg["labels"]["apply"] and cfg["labels"]["blk"] and cfg["labels"]["set1"]
    sets = {s["n"]: s for s in c.get(f"/workspaces/{wid}/tuning").json()["sets"]}
    assert cfg["sets"]["2"]["Gain"] == pytest.approx(sets[2]["gain"])
    en = c.get(f"/workspaces/{wid}/live?lang=en").json()
    cs = c.get(f"/workspaces/{wid}/live?lang=cs").json()
    assert en["labels"]["start"] != cs["labels"]["start"] and cs["decimal"] == "," and en["decimal"] == "."
    assert {k: v for k, v in en.items() if k not in ("labels", "decimal", "lang")} == {
        k: v for k, v in cs.items() if k not in ("labels", "decimal", "lang")}


def test_record_set_without_model():
    """Sada 1 (regulátor v záznamu) jde číst a zapsat i bez modelu – identifikace v uzavřené smyčce ji potřebuje dřív
    než model; je to táž sada jako v Ladění (jednotky bloku podle profilu)."""
    with TestClient(create_app()) as c:
        wid = c.post("/workspaces").json()["id"]
        assert c.get(f"/workspaces/{wid}/tuning/record-set").status_code == 409            # bez dat
        c.post(f"/workspaces/{wid}/data/demo")
        assert c.get(f"/workspaces/{wid}/tuning").status_code == 409                       # Ladění bez modelu ne
        r = c.get(f"/workspaces/{wid}/tuning/record-set").json()
        assert r["controller"]["id"] == "pcs7_pidconl" and [q["key"] for q in r["tuning_params"]] == ["Gain", "TI", "TD"]
        assert r["set"]["n"] == 1 and r["set"]["metrics"] is None
        r = c.put(f"/workspaces/{wid}/tuning/record-set", json={"values": {"Gain": 1.5, "TI": 80, "TD": 0}}).json()
        assert r["set"]["values"]["Gain"] == pytest.approx(1.5) and r["set"]["values"]["TI"] == pytest.approx(80)
        assert not r["set"]["placeholder"]
        assert c.put(f"/workspaces/{wid}/tuning/record-set", json={}).status_code == 422
        s = c.get(f"/workspaces/{wid}/settings").json()
        assert s["set1_gain"] == pytest.approx(1.5) and s["set1_ti"] == pytest.approx(80)


def test_live_config_needs_model():
    with TestClient(create_app()) as c:
        wid = c.post("/workspaces").json()["id"]
        assert c.get(f"/workspaces/{wid}/live").status_code == 409
        c.post(f"/workspaces/{wid}/data/demo")
        assert c.get(f"/workspaces/{wid}/live").status_code == 409


def test_live_config_profile_dv_and_apc(ws):
    """E9-B: regulátor z profilu smyčky (výchozí PIDConL), měřené poruchy přes model, struktury APC, rychlosti a deník."""
    c, wid = ws
    cfg = c.get(f"/workspaces/{wid}/live").json()
    assert cfg["profile"]["id"] == "pcs7_pidconl" and cfg["speeds"] == [1, 10, 50, 200] and cfg["journal"] is True
    assert set(cfg["pctrl"]) == {"1", "2"} and cfg["pctrl"]["2"]["Gain"] == pytest.approx(cfg["sets"]["2"]["Gain"])
    assert set(cfg["apc"]) == {"ff", "cascade"} and isinstance(cfg["dvs"], list)
    for d in cfg["dvs"]:
        assert len(d["pd"]) >= 3 and d["span"] > 0 and set(d["ff"]) == {"g", "lead", "lag", "delay"}
    if cfg["apc"]["cascade"]["ok"]:
        inner = cfg["apc"]["cascade"]["inner"]
        assert inner["code"] in ("P1D", "P2D") and inner["ctrl"]["Gain"] != 0
    assert cfg["labels"]["st_cascade"] and cfg["labels"]["journal"]
    # zápis souhrnu běhu do nastavení projektu (hook pro deník E10)
    run = {"when": "2026-11-12T10:00:00", "struct": "ff", "kpi": {"1": {"iae": 1.5}, "2": {"iae": 0.9}}}
    assert c.patch(f"/workspaces/{wid}/settings", json={"live_runs": [run]}).status_code == 200
    assert c.get(f"/workspaces/{wid}/settings").json()["live_runs"] == [run]
