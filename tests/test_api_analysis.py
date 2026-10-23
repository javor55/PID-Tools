"""API – diagnostika, doporučení APC, protokol, jazyk odpovědí a OPC UA (M11)."""
import datetime as dt
import os
import sys
import time

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from pidtools.api import create_app  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
import golden  # noqa: E402


def _wait(c, job, t=300):
    t0 = time.time()
    while time.time() - t0 < t:
        st = c.get(f"/jobs/{job['id']}").json()
        if st["state"] not in ("queued", "running"):
            assert st["state"] == "done", st
            return st
        time.sleep(0.2)
    raise AssertionError("job timeout")


def _null(x):
    """Zlaté případy ukládají NaN / ∞ jako text, JSON z API jako null."""
    if isinstance(x, dict):
        return {k: _null(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_null(v) for v in x]
    return None if x in ("nan", "inf", "-inf") else x


def _sub(ref, got):
    """Jen klíče, které zlatý případ ukládá (dlouhá pole vynechává), i ve vnořených slovnících."""
    if isinstance(ref, dict) and isinstance(got, dict):
        return {k: _sub(ref[k], got.get(k)) for k in ref}
    return got


@pytest.fixture(scope="module")
def ws():
    with TestClient(create_app()) as c:
        wid = c.post("/workspaces").json()["id"]
        c.post(f"/workspaces/{wid}/data/demo")
        c.patch(f"/workspaces/{wid}/settings", json={"chosen": ["P1D", "I1D"]})
        _wait(c, c.post(f"/workspaces/{wid}/identify").json())
        yield c, wid


def test_diagnostics_like_golden(ws):
    c, wid = ws
    d = c.get(f"/workspaces/{wid}/diagnostics").json()
    ref = _null(golden.load("demo_common")["diag"])
    assert golden.compare(ref["kpis"], _sub(ref["kpis"], d["kpis"])) == []
    assert golden.compare(ref["valve"], _sub(ref["valve"], d["valve"])) == []
    assert d["valve"].get("verdict") == ref["valve"].get("verdict")
    assert d["nonlinearity"]["spread"] == pytest.approx(ref["nonlinearity"]["spread"], rel=0.02)
    assert c.get(f"/workspaces/{wid}/diagnostics", params={"a": 0, "b": 10}).status_code == 422


def test_recommendations_language(ws):
    c, wid = ws
    en = c.get(f"/workspaces/{wid}/apc/recommend").json()
    cs = c.get(f"/workspaces/{wid}/apc/recommend", headers={"Accept-Language": "cs-CZ,cs;q=0.9"}).json()
    assert [x["kind"] for x in en] == [x["kind"] for x in cs] and "ff" in [x["kind"] for x in en]
    assert en[0]["text"] != cs[0]["text"]
    assert c.get(f"/workspaces/{wid}/apc/recommend", params={"lang": "cs"}).json()[0]["text"] == cs[0]["text"]


def test_report_html(ws):
    c, wid = ws
    r = c.post(f"/workspaces/{wid}/report", json={"meta": {"plant": "Test", "author": "API"},
                                                  "sections": ["model", "tuning"], "chart_mode": "cdn"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    assert "<html" in r.text.lower() and "Test" in r.text
    assert c.post(f"/workspaces/{wid}/report", json={"sections": ["xx"]}).status_code == 422


def test_opc_history_to_workspace():
    pytest.importorskip("asyncua")
    from pidtools.app import opc
    url, stop = opc.test_server(port=48431, n=300)
    try:
        with TestClient(create_app()) as c:
            assert c.get("/opc/available").json() is True
            found = c.post("/opc/find", json={"url": url, "text": "FIC101"}).json()
            nodes = {n["node_id"]: n["path"] for n in found if n["is_var"]}
            assert {"FIC101.PV", "FIC101.MV"} <= set(nodes.values())
            top = c.post("/opc/browse", json={"url": url}).json()
            assert any(n["name"] == "FIC101" for n in top)
            wid = c.post("/workspaces").json()["id"]
            now = dt.datetime.now(dt.timezone.utc)
            job = c.post(f"/workspaces/{wid}/opc/history", json={
                "url": url, "nodes": nodes, "start": (now - dt.timedelta(hours=1)).isoformat(),
                "end": now.isoformat()}).json()
            _wait(c, job)
            w = c.get(f"/workspaces/{wid}").json()
            assert w["has_data"] and w["fname"] == "OPC UA" and w["n"] > 100
            assert c.post("/opc/browse", json={"url": "opc.tcp://127.0.0.1:1/x", "timeout": 1}).status_code == 502
    finally:
        stop()
