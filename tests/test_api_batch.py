"""
API – hromadné akce nad smyčkami projektu (FEATURE-007): souhrn smyček (`/loops/overview`), úloha `/batch`
(identifikace, návrh ladění, převzetí návrhů do Setu 2) a hromadný export sad.
Projekt se třemi smyčkami nad syntetickými daty: FIC1 a FIC2 jsou použitelné, FIC3 má konstantní MV (bez buzení).
"""
import io
import os
import sys
import time

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from pidtools.api import create_app  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from test_api_apc_loops import _two_frame  # noqa: E402


def _frame():
    df = _two_frame()
    df["FIC3.PV"] = df["FIC1.PV"].to_numpy() + 1.0
    df["FIC3.MV"] = 50.0                                 # smyčka bez buzení MV
    return df


def _wait(c, jid, t=300):
    t0 = time.time()
    while time.time() - t0 < t:
        st = c.get(f"/api/v1/jobs/{jid}").json()
        if st["state"] not in ("queued", "running"):
            return st
        time.sleep(0.1)
    raise AssertionError("job timeout")


def _project(c):
    wid = c.post("/api/v1/workspaces").json()["id"]
    u = f"/api/v1/workspaces/{wid}"
    buf = io.StringIO()
    _frame().to_csv(buf, index=False)
    assert c.post(f"{u}/data/file", params={"name": "three.csv"}, content=buf.getvalue().encode(),
                  headers={"content-type": "application/octet-stream"}).status_code == 200
    c.put(f"{u}/columns", json={"pv": "FIC1.PV", "mv": "FIC1.MV"})
    c.patch(f"{u}/settings", json={"loop_tag": "FIC1", "chosen": ["P1D"]})
    for nm in ("FIC2", "FIC3"):
        assert c.post(f"{u}/loops", json={"name": nm, "pv": f"{nm}.PV", "mv": f"{nm}.MV"}).status_code == 200
    c.put(f"{u}/loops/active", json={"index": 0})
    for i in (1, 2):                                      # jen jeden model, ať je test rychlý
        c.put(f"{u}/loops/active", json={"index": i})
        c.patch(f"{u}/settings", json={"chosen": ["P1D"]})
    c.put(f"{u}/loops/active", json={"index": 0})
    return wid, u


def _rows(c, u):
    return {r["index"]: r for r in c.get(f"{u}/loops/overview").json()["loops"]}


@pytest.fixture(scope="module")
def env():
    with TestClient(create_app()) as c:
        wid, u = _project(c)
        yield c, wid, u


def test_overview_stage_before_identify(env):
    c, _, u = env
    rows = _rows(c, u)
    assert [rows[i]["stage"] for i in range(3)] == ["data", "data", "data"]
    for r in rows.values():
        assert r["fit"] is None and r["ms"] is None and r["set2_defined"] is False and r["change_pct"] is None


def test_overview_fit_ms_change_stage():
    """FIT, Ms a změna Gain se berou z existujících výpočtů (model smyčky, tabulka robustnosti v Ladění)."""
    with TestClient(create_app()) as c:
        _, u = _project(c)
        j = c.post(f"{u}/identify").json()
        assert _wait(c, j["id"])["state"] == "done"
        m = c.get(f"{u}/model").json()
        r = _rows(c, u)[0]
        assert r["stage"] == "model" and r["fit"] == pytest.approx(next(x for x in m["results"] if x["code"] == m["selected"])["fit"])
        assert r["ms"] is None and r["change_pct"] is None            # Set 1 je zástupný, Set 2 není zadán
        c.put(f"{u}/tuning/sets/1", json={"Kc": 0.8, "Ti": 40.0, "Td": 0.0})
        ms1 = c.post(f"{u}/tuning/robustness").json()[0]["Ms"]
        assert _rows(c, u)[0]["ms"] == pytest.approx(ms1)
        c.put(f"{u}/tuning/sets/2", json={"Kc": 1.2, "Ti": 30.0, "Td": 0.0})
        r = _rows(c, u)[0]
        ms2 = c.post(f"{u}/tuning/robustness").json()[1]["Ms"]
        assert r["stage"] == "set2" and r["set2_defined"] and r["ms"] == pytest.approx(ms2)
        assert r["change_pct"] == pytest.approx(50.0)
        assert _rows(c, u)[1]["stage"] == "data"
