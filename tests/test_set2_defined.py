"""TICKET-004: výslovný příznak `set2_defined` místo porovnání Setu 2 s výchozími hodnotami 1 / 100 / 0."""
import json
import os
import time

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from pidtools.api import create_app  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
V1 = "/api/v1/workspaces"


def _wait(client, job, t=600):
    t0 = time.time()
    while time.time() - t0 < t:
        st = client.get(f"/api/v1/jobs/{job['id']}").json()
        if st["state"] not in ("queued", "running"):
            assert st["state"] == "done", st
            return
        time.sleep(0.2)
    raise AssertionError("job timeout")


@pytest.fixture(scope="module")
def client():
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture()
def ws(client):
    """Nový prostor s demo daty a modelem (každý test má vlastní)."""
    wid = client.post(V1).json()["id"]
    client.post(f"{V1}/{wid}/data/demo")
    client.patch(f"{V1}/{wid}/settings", json={"chosen": ["P1D", "I1D"]})
    _wait(client, client.post(f"{V1}/{wid}/identify").json())
    return wid


def _set2(client, wid):
    return next(x for x in client.get(f"{V1}/{wid}/tuning").json()["sets"] if x["n"] == 2)


def test_new_workspace_set2_not_defined(client, ws):
    assert client.get(f"{V1}/{ws}/settings").json()["set2_defined"] is False
    assert _set2(client, ws)["placeholder"] is True
    assert client.app.state.workspace(ws).set2_empty()


def test_put_set2_with_default_values_defines_it(client, ws):
    r = client.put(f"{V1}/{ws}/tuning/sets/2", json={"Kc": 1.0, "Ti": 100.0, "Td": 0.0})
    assert r.status_code == 200, r.text
    s2 = _set2(client, ws)
    assert s2["placeholder"] is False and (s2["gain"], s2["ti"], s2["td"]) == (1.0, 100.0, 0.0)
    assert client.get(f"{V1}/{ws}/settings").json()["set2_defined"] is True
    assert not client.app.state.workspace(ws).set2_empty()
    # zápis Setu 1 příznak Setu 2 nemění
    other = client.post(V1).json()["id"]
    client.post(f"{V1}/{other}/data/demo")
    assert client.get(f"{V1}/{other}/settings").json()["set2_defined"] is False


def test_patch_set2_value_defines_and_explicit_false_resets(client, ws):
    url = f"{V1}/{ws}/settings"
    assert client.patch(url, json={"set2_gain": 1.0}).json()["set2_defined"] is True
    assert _set2(client, ws)["placeholder"] is False
    assert client.patch(url, json={"set2_defined": False}).json()["set2_defined"] is False
    assert _set2(client, ws)["placeholder"] is True
    # výslovná hodnota v témže PATCH má přednost před automatikou
    assert client.patch(url, json={"set2_gain": 2.0, "set2_defined": False}).json()["set2_defined"] is False
    assert client.patch(url, json={"set2_defined": "ano"}).status_code == 422


@pytest.mark.parametrize("vals,expected", [((1.0, 100.0, 0.0), False), ((-2.0, 200.0, 0.0), True)])
def test_project_migration_without_key(client, vals, expected):
    """Projekt z beta 4 (bez klíče `set2_defined`): Set 2 s výchozími hodnotami → nezadán, jinak zadán."""
    proj = json.loads(open(os.path.join(HERE, "golden", "tic001.json"), encoding="utf-8").read())
    st = proj["state"]
    st.pop("set2_defined", None)
    st["set2_gain"], st["set2_ti"], st["set2_td"] = vals
    wid = client.post(V1).json()["id"]
    r = client.put(f"{V1}/{wid}/project", content=json.dumps(proj).encode(), headers={"Content-Type": "application/json"})
    assert r.status_code == 200, r.text
    assert client.get(f"{V1}/{wid}/settings").json()["set2_defined"] is expected
    assert client.app.state.workspace(wid).set2_empty() is (not expected)
    # po uložení a znovunačtení zůstává (klíč je už v souboru)
    saved = client.get(f"{V1}/{wid}/project").json()
    assert saved["state"]["set2_defined"] is expected


def test_project_with_key_keeps_it(client):
    """Nový projekt: výslovné `set2_defined = true` platí i pro hodnoty 1 / 100 / 0."""
    proj = json.loads(open(os.path.join(HERE, "golden", "tic001.json"), encoding="utf-8").read())
    proj["state"].update(set2_gain=1.0, set2_ti=100.0, set2_td=0.0, set2_defined=True)
    wid = client.post(V1).json()["id"]
    assert client.put(f"{V1}/{wid}/project", content=json.dumps(proj).encode(),
                      headers={"Content-Type": "application/json"}).status_code == 200
    assert client.get(f"{V1}/{wid}/settings").json()["set2_defined"] is True


def test_ff_simulate_reports_ctrl_set(client, ws):
    url = f"{V1}/{ws}/apc/ff"
    assert client.get(url).json()["ctrl_set"] == 1
    assert client.post(f"{url}/simulate", json={"dist": 0}).json()["ctrl_set"] == 1
    client.put(f"{V1}/{ws}/tuning/sets/2", json={"Kc": 1.0, "Ti": 100.0, "Td": 0.0})
    assert client.get(url).json()["ctrl_set"] == 2
    assert client.post(f"{url}/simulate", json={"dist": 0}).json()["ctrl_set"] == 2
    for path in ("smith", "gainsched", "gainsched_er", "vpc", "ratio", "split"):
        r = client.get(f"{V1}/{ws}/apc/{path}")
        assert r.status_code == 200 and r.json()["ctrl_set"] == 2, path
