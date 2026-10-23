"""API – projekt a smyčky (M8): načtení a uložení beze změny obsahu, starý formát, projekt bez dat, víc smyček."""
import json
import os
import sys

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from pidtools.api import create_app  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
import golden  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(create_app()) as c:
        yield c


def _ws(client):
    return client.post("/workspaces").json()["id"]


def _put(client, wid, text):
    return client.put(f"/workspaces/{wid}/project", content=text.encode("utf-8"),
                      headers={"Content-Type": "application/json"})


@pytest.mark.parametrize("src", ["golden/tic001.json", "data/project_v1.json"])
def test_roundtrip_unchanged(client, src):
    """Projekt → API → projekt → nový prostor → projekt: obsah se nezmění (i u staršího formátu)."""
    text = open(os.path.join(HERE, src), encoding="utf-8").read()
    a = _ws(client)
    assert _put(client, a, text).status_code == 200
    p1 = client.get(f"/workspaces/{a}/project").json()
    b = _ws(client)
    _put(client, b, json.dumps(p1))
    p2 = client.get(f"/workspaces/{b}/project").json()
    for p in (p1, p2):
        p.pop("created", None)
    assert golden.compare(p1, p2, rtol=1e-9, atol=1e-12) == []


def test_project_values(client):
    wid = _ws(client)
    w = _put(client, wid, open(os.path.join(HERE, "golden", "tic001.json"), encoding="utf-8").read()).json()
    assert w["pv"] == "TIC001_PV" and w["dists"] == ["TIC002_PV"] and w["has_data"]
    st = client.get(f"/workspaces/{wid}/settings").json()
    assert st["set1_gain"] == 0.5 and st["set1_ti"] == 210.0
    p = client.get(f"/workspaces/{wid}/project", params={"data": False}).json()
    assert "data" not in p and p["fit"]["res"]["P1D"]["p"]


def test_project_without_data_uses_loaded_data(client):
    wid = _ws(client)
    client.post(f"/workspaces/{wid}/data/demo")
    client.patch(f"/workspaces/{wid}/settings", json={"set1_gain": -3.0})
    p = client.get(f"/workspaces/{wid}/project", params={"data": False}).json()
    other = _ws(client)
    client.post(f"/workspaces/{other}/data/demo")
    w = _put(client, other, json.dumps(p)).json()
    assert w["has_data"] and w["pv"] == "LIC101.PV"
    assert client.get(f"/workspaces/{other}/settings").json()["set1_gain"] == -3.0


def test_loops(client):
    wid = _ws(client)
    client.post(f"/workspaces/{wid}/data/demo")
    lp = client.post(f"/workspaces/{wid}/loops", json={"name": "FIC100", "pv": "FI100.Pritok",
                                                        "mv": "LIC101.MV"}).json()
    assert lp["active"] == 1 and [x["name"] for x in lp["loops"]] == ["LIC101.PV", "FIC100"]
    assert client.get(f"/workspaces/{wid}").json()["pv"] == "FI100.Pritok"        # aktivní smyčka
    proj = client.get(f"/workspaces/{wid}/project").json()
    assert len(proj["loops"]) == 2 and proj["active"] == 2
    other = _ws(client)
    _put(client, other, json.dumps(proj))
    assert [x["name"] for x in client.get(f"/workspaces/{other}/loops").json()["loops"]] == ["LIC101.PV", "FIC100"]
    assert client.put(f"/workspaces/{wid}/loops/active", json={"index": 0}).json()["active"] == 0
    assert client.get(f"/workspaces/{wid}").json()["pv"] == "LIC101.PV"
    assert len(client.delete(f"/workspaces/{wid}/loops/1").json()["loops"]) == 1
    assert client.delete(f"/workspaces/{wid}/loops/0").status_code == 409            # poslední smyčka zůstane
    assert client.post(f"/workspaces/{wid}/loops", json={"pv": "X", "mv": "Y"}).status_code == 422


def test_invalid_project(client):
    wid = _ws(client)
    assert _put(client, wid, "{not json").status_code == 400
