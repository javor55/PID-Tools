"""API – triáž smyček (E5): úloha na pozadí, poslední výsledek, prahy verdiktu."""
import time

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from pidtools.api import create_app  # noqa: E402
from pidtools.app import triage  # noqa: E402


def _wait(c, job, t=300):
    t0 = time.time()
    while time.time() - t0 < t:
        st = c.get(f"/jobs/{job['id']}").json()
        if st["state"] not in ("queued", "running"):
            return st
        time.sleep(0.2)
    raise AssertionError("job timeout")


@pytest.fixture(scope="module")
def ws():
    with TestClient(create_app()) as c:
        wid = c.post("/workspaces").json()["id"]
        c.post(f"/workspaces/{wid}/data/demo")
        yield c, f"/api/v1/workspaces/{wid}"


def test_no_result_before_run(ws):
    c, w = ws
    r = c.get(w + "/triage").json()
    assert r["ready"] is False and r["loops"] == []


def test_triage_needs_data():
    with TestClient(create_app()) as c:
        wid = c.post("/workspaces").json()["id"]
        assert c.post(f"/api/v1/workspaces/{wid}/triage").status_code == 409


def test_run_and_result(ws):
    c, w = ws
    job = c.post(w + "/triage").json()
    st = _wait(c, job)
    assert st["state"] == "done", st
    r = c.get(w + "/triage").json()
    assert r["ready"] and len(r["loops"]) == 1
    row = r["loops"][0]
    assert row["index"] == 0 and row["tag"] and row["label"]
    assert row["verdict"] in triage.BY_ID and row["evidence"] and row["evidence"][0]["text"]
    assert {"auto_pct", "harris", "osc", "frozen_pct"} <= set(row["metrics"])
    assert r["counts"] == {row["verdict"]: 1}


def test_two_loops(ws):
    c, w = ws
    assert c.post(w + "/loops", json={}).status_code == 200
    _wait(c, c.post(w + "/triage").json())
    r = c.get(w + "/triage").json()
    assert [x["index"] for x in r["loops"]] == [0, 1]
    assert sum(r["counts"].values()) == 2


def test_thresholds_roundtrip_and_effect(ws):
    c, w = ws
    t = c.get(w + "/triage/thresholds").json()
    assert t["values"]["valve"]["hyst_pct"] == 2 and {i["rule"] for i in t["items"]} >= {"low_auto", "valve", "tune"}
    # min. AUTO 100 % → každá smyčka s <100 % AUTO je „málo dat v AUTO“; hodnoty se ořežou na meze
    out = c.put(w + "/triage/thresholds", json={"values": {"low_auto": {"min_auto_pct": 1000}, "bogus": {"x": 1}}}).json()
    assert out["values"]["low_auto"]["min_auto_pct"] == 100 and "bogus" not in out["values"]
    assert c.get(w + "/triage/thresholds").json()["values"]["low_auto"]["min_auto_pct"] == 100
    _wait(c, c.post(w + "/triage").json())
    r = c.get(w + "/triage").json()
    assert all(x["metrics"]["auto_pct"] >= 100 or x["verdict"] == "low_auto" for x in r["loops"])
    c.put(w + "/triage/thresholds", json={"values": {}})
    assert c.get(w + "/triage/thresholds").json()["values"]["low_auto"]["min_auto_pct"] == 30
