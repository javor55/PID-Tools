"""
API – model (M9): identifikace jako úloha, výsledky shodné se zlatými případy, úseky a režim MAN / AUTO,
výběr modelu, dofitování se zafixovaným parametrem, nejistota, křížové ověření, průběhy modelu.
"""
import os
import sys
import time

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from pidtools.api import create_app  # noqa: E402
from pidtools.app import signalpack  # noqa: E402
from pidtools.app import windows as wn  # noqa: E402
from pidtools.core import DIST_FIELDS  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
import golden  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(create_app(max_jobs=2)) as c:
        yield c


def _ws(client):
    return client.post("/workspaces").json()["id"]


def _wait(client, job, t=300):
    t0 = time.time()
    while time.time() - t0 < t:
        st = client.get(f"/jobs/{job['id']}").json()
        if st["state"] in ("done", "error", "cancelled", "timeout"):
            assert st["state"] == "done", st
            return st
        time.sleep(0.2)
    raise AssertionError("job timeout")


def _models(client, wid):
    m = client.get(f"/workspaces/{wid}/model").json()
    return m, {r["code"]: r for r in m["results"]}


def _same(ref_res, got):
    """Parametry modelů jako ve zlatém případu (stejná tolerance jako tests/test_golden.py)."""
    for c, r in ref_res.items():
        assert golden.compare(r["p"], got[c]["p"], "/p") == [], (c, r["p"], got[c]["p"])
        assert golden.compare(r["fit"], got[c]["fit"]) == [], c


def test_demo_identify_like_golden(client):
    wid = _ws(client)
    client.post(f"/workspaces/{wid}/data/demo")
    client.patch(f"/workspaces/{wid}/settings", json={"chosen": ["P1D", "I1D"]})
    job = client.post(f"/workspaces/{wid}/identify").json()
    assert job["state"] in ("queued", "running", "done")
    _wait(client, job)
    m, res = _models(client, wid)
    ref = golden.load("demo_common")["model"]
    _same(ref["res"], res)
    assert m["selected"] == ref["best"] and m["current"]["code"] == ref["best"] and not m["stale"]
    # znovu se stejnými vstupy: výsledek z cache
    again = client.post(f"/workspaces/{wid}/identify").json()
    assert again["state"] == "done" and again["cached"]
    # názvy parametrů a validace
    assert res["I1D"]["names"] == ["Ki", "T1", "θ"] and res["I1D"]["dists"][0]["name"] == "FI100.Pritok"
    v = client.get(f"/workspaces/{wid}/model/validation").json()
    assert v["code"] == "I1D" and abs(v["metrics"]["FIT"] - ref["res"]["I1D"]["fit"]) < 0.5
    assert len(v["metrics"]["acf"]) > 5 and v["metrics"]["status"] in (0, 1, 2, 3)
    # průběhy modelu binárně
    meta, sig = signalpack.unframe(client.get(f"/workspaces/{wid}/model/curves").content)
    assert {"pv", "mv", "model", "residual", "full"} <= set(sig) and len(sig["model"][0]) == 3600
    # výběr modelu a dofitování se zafixovaným θ
    client.put(f"/workspaces/{wid}/model/select", json={"code": "P1D"})
    client.patch(f"/workspaces/{wid}/settings", json={"fx|P1D|2": True, "ed|P1D|2": 30.0})
    _wait(client, client.post(f"/workspaces/{wid}/model/refit", json={"code": "P1D"}).json())
    m, res = _models(client, wid)
    assert res["P1D"]["p"][2] == pytest.approx(30.0) and m["current"]["code"] == "P1D"
    # nejistota
    _wait(client, client.post(f"/workspaces/{wid}/model/uncertainty", json={"n": 3}).json())
    m, _ = _models(client, wid)
    assert m["uncertainty"]["code"] == "P1D" and len(m["uncertainty"]["ps"]) == 3
    # změna nastavení → model zastaralý
    client.patch(f"/workspaces/{wid}/settings", json={"thmax": 50.0})
    assert client.get(f"/workspaces/{wid}/model").json()["stale"]


def test_mixed_windows_like_golden(client):
    """Reálná smyčka TIC001: úseky MV ručně + AUTO, kombinovaná identifikace (zlatý případ tic001_mixed)."""
    wid = _ws(client)
    client.put(f"/workspaces/{wid}/project", content=open(os.path.join(HERE, "golden", "tic001.json"), "rb").read(),
               headers={"Content-Type": "application/json"})
    client.patch(f"/workspaces/{wid}/settings", json={"chosen": ["P1D"], "id_mode": "auto", "win_mode": "inputs"})
    w = client.put(f"/workspaces/{wid}/windows", json={
        "wins": {"MV": [[5.0 * 3600, 8.6 * 3600], [8.65 * 3600, 11.1 * 3600]]},
        "excl": {"PV": [False, 0.0, 100.0]}}).json()
    assert w["mv_modes"] == ["man", "auto"] and "TIC002_PV" in w["inputs"]
    assert client.put(f"/workspaces/{wid}/windows", json={"wins": {"XX": [[0, 1]]}}).status_code == 422
    _wait(client, client.post(f"/workspaces/{wid}/identify").json())
    m, res = _models(client, wid)
    ref = golden.load("tic001_mixed")["model"]
    _same(ref["res"], res)
    assert res["P1D"]["mixed"] and res["P1D"]["fit_cl_pv"] is not None and "chk_no_delay" in [c["key"] for c in res["P1D"]["checks"]]
    # režim úseku ručně → kombinovaná identifikace se nepoužije
    w = client.put(f"/workspaces/{wid}/windows/mode", json={"index": 1, "mode": "man"}).json()
    assert w["mv_modes"] == ["man", "man"]
    # křížové ověření po úsecích
    _wait(client, client.post(f"/workspaces/{wid}/model/crossval").json())
    assert "P1D" in client.get(f"/workspaces/{wid}/model").json()["crossval"]


def test_errors(client):
    wid = _ws(client)
    assert client.post(f"/workspaces/{wid}/identify").status_code == 409
    client.post(f"/workspaces/{wid}/data/demo")
    assert client.get(f"/workspaces/{wid}/model").json()["has_fit"] is False
    assert client.get(f"/workspaces/{wid}/model/curves").status_code == 409
    assert client.put(f"/workspaces/{wid}/model/select", json={"code": "P1D"}).status_code == 404


def test_dist_struct_compare_and_select(client):
    """Porovnání struktur poruchy (FIT) a výběr jiné struktury = přímá volání aplikační vrstvy (choose_dist)."""
    wid = _ws(client)
    client.post(f"/workspaces/{wid}/data/demo")
    client.patch(f"/workspaces/{wid}/settings", json={"chosen": ["I1D"]})
    _wait(client, client.post(f"/workspaces/{wid}/identify").json())
    ws = client.app.state.workspace(wid)
    _, res = _models(client, wid)
    d = res["I1D"]["dists"][0]
    ref = ws.fit["res"]["I1D"]["dv_cmp"][0]
    assert [c["struct"] for c in d["cmp"]] == [c[0] for c in ref] == ["P0D", "P1D", "P2D", "I0D", "I1D"]
    assert [c["fit"] for c in d["cmp"]] == pytest.approx([c[1] for c in ref])
    assert d["struct"] == d["ident"] == wn.dist_id("I1D", ws.fit["res"]["I1D"], 0)
    other = next(c["struct"] for c in d["cmp"] if c["fit"] is not None and c["struct"] != d["ident"])
    url = f"/workspaces/{wid}/model/dist"
    assert client.put(url, json={"code": "I1D", "index": 0, "struct": "XX"}).status_code == 422
    assert client.put(url, json={"code": "I1D", "index": 3, "struct": other}).status_code == 404
    m2 = client.put(url, json={"code": "I1D", "index": 0, "struct": other}).json()
    d2 = {r["code"]: r for r in m2["results"]}["I1D"]["dists"][0]
    assert d2["struct"] == other and d2["ident"] == d["ident"] and d2["fields"] == [list(f) for f in DIST_FIELDS[other]]
    assert ws.get("dsel|I1D|0") == other                      # jako ws.choose_dist v desktopu
    assert m2["current"]["pdl"] == [list(map(float, x)) for x in ws.model[2]]
    back = client.post(f"/workspaces/{wid}/model/reset", json={"code": "I1D"}).json()
    assert {r["code"]: r for r in back["results"]}["I1D"]["dists"][0]["struct"] == d["ident"]
