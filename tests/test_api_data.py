"""API – data (M7): ukázka a soubor, sloupce, úsek, nastavení, signály binárně, kvalita, MAN / AUTO, výkon."""
import os
import time

import numpy as np
import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from pidtools.api import create_app  # noqa: E402
from pidtools.app import signalpack  # noqa: E402

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


@pytest.fixture(scope="module")
def client():
    with TestClient(create_app()) as c:
        yield c


def _ws(client):
    return client.post("/workspaces").json()["id"]


def test_demo_signals_and_quality(client):
    wid = _ws(client)
    w = client.post(f"/workspaces/{wid}/data/demo").json()
    assert w["has_data"] and w["pv"] == "LIC101.PV" and w["sp"] and w["dists"] == ["FI100.Pritok"] and w["n"] == 3600
    r = client.get(f"/workspaces/{wid}/signals")
    assert r.headers["content-type"] == "application/octet-stream"
    meta, sig = signalpack.unframe(r.content)
    assert set(w["columns"]) <= set(sig) and meta["decim"] == 1
    t, v = sig["LIC101.PV"]
    assert t.dtype == np.float64 and v.dtype == np.float32 and len(t) == len(v) > 1000
    meta, g = signalpack.unframe(client.get(f"/workspaces/{wid}/signals", params={"source": "grid"}).content)
    assert {"pv", "mv", "sp", "d0"} <= set(g) and len(g["pv"][0]) == 3600
    meta, one = signalpack.unframe(client.get(f"/workspaces/{wid}/signals",
                                              params={"names": ["LIC101.MV"]}).content)
    assert list(one) == ["LIC101.MV"]
    q = client.get(f"/workspaces/{wid}/quality").json()
    assert q["level"] == 0 and [c["key"] for c in q["checks"]] == ["q_steps_ok", "q_snr_ok"]
    lm = client.get(f"/workspaces/{wid}/loopmode").json()
    assert lm["effective"] in ("open", "cl") and lm["runs"] and 0 <= lm["frac"] <= 1


def test_file_columns_range_settings(client):
    wid = _ws(client)
    raw = open(os.path.join(DATA, "ff_example.csv"), "rb").read()
    w = client.post(f"/workspaces/{wid}/data/file", params={"name": "ff.csv"}, content=raw,
                    headers={"Content-Type": "application/octet-stream"}).json()
    assert w["fname"] == "ff.csv" and {"CV", "MV", "SP", "DV"} <= set(w["columns"])
    assert client.put(f"/workspaces/{wid}/columns", json={"pv": "CV", "mv": "NOPE"}).status_code == 422
    w = client.put(f"/workspaces/{wid}/columns", json={"pv": "CV", "mv": "MV", "sp": "SP", "dists": ["DV"]}).json()
    assert (w["pv"], w["mv"], w["sp"], w["dists"]) == ("CV", "MV", "SP", ["DV"])
    w = client.put(f"/workspaces/{wid}/range", json={"a": 100, "b": 500}).json()
    assert w["rng"] == [100.0, 500.0]
    assert client.put(f"/workspaces/{wid}/range", json={"a": 0, "b": 1e9}).status_code == 422
    s = client.patch(f"/workspaces/{wid}/settings", json={"set1_gain": 2.5, "set1_ti": 60.0}).json()
    assert s["set1_gain"] == 2.5 and s["set1_ti"] == 60.0
    assert client.patch(f"/workspaces/{wid}/settings", json={"hack": 1}).status_code == 422


def _long_csv(n=60):
    rows = ["Time,Tag,Value"]
    for i in range(n):
        for tag, v in (("FIC.PV", 50 + (i % 7)), ("FIC.MV", 40 + (i // 10))):
            rows.append(f"2024-02-13 13:{i // 60:02d}:{i % 60:02d},{tag},{v}")
    return "\n".join(rows).encode()


def test_layout_info_and_change(client):
    """GET /layout ukazuje, jak je tabulka přečtená; PUT /layout ji přečte jinak (dlouhý formát, bez času)."""
    wid = _ws(client)
    assert client.get(f"/workspaces/{wid}/layout").status_code == 409
    w = client.post(f"/workspaces/{wid}/data/file", params={"name": "h.csv"}, content=_long_csv()).json()
    assert w["layout"] == "long" and set(w["columns"]) == {"FIC.PV", "FIC.MV"}
    lay = client.get(f"/workspaces/{wid}/layout").json()
    assert lay["layout"] == lay["default_layout"] == "long" and lay["table_columns"] == ["Time", "Tag", "Value"]
    assert (lay["c_time"], lay["c_tag"], lay["c_val"]) == ("Time", "Tag", "Value") and lay["unit"] == "s"
    r = client.put(f"/workspaces/{wid}/layout", json={"layout": "wide"})       # dlouhý formát jako společný čas nejde
    assert r.status_code == 400
    assert client.get(f"/workspaces/{wid}/layout").json()["layout"] == "long"
    assert client.get(f"/workspaces/{wid}").json()["columns"] == w["columns"]
    w = client.put(f"/workspaces/{wid}/layout", json={"layout": "long", "c_tag": "Tag", "c_val": "Value"}).json()
    assert set(w["columns"]) == {"FIC.PV", "FIC.MV"}
    # bez času: co řádek, to vzorek s ručně zadanou periodou
    raw = "pv,mv\n" + "\n".join(f"{50 + i % 5},{i % 3}" for i in range(200))
    w = client.post(f"/workspaces/{wid}/data/file", params={"name": "r.csv"}, content=raw.encode()).json()
    rows = client.get(f"/workspaces/{wid}/layout").json()["rows_mark"]
    w = client.put(f"/workspaces/{wid}/layout", json={"layout": "wide", "c_time": rows}).json()
    assert set(w["columns"]) == {"pv", "mv"} and w["Ts"] == pytest.approx(1.0)
    w = client.put(f"/workspaces/{wid}/layout", json={"layout": "wide", "c_time": rows, "row_dt": 0.5,
                                                      "unit": "min"}).json()
    assert w["Ts"] == pytest.approx(30.0)
    lay = client.get(f"/workspaces/{wid}/layout").json()
    assert lay["row_dt"] == 0.5 and lay["unit"] == "min" and lay["c_time"] == rows


def test_errors(client):
    wid = _ws(client)
    assert client.get(f"/workspaces/{wid}/signals").status_code == 409          # bez dat
    r = client.post(f"/workspaces/{wid}/data/file", params={"name": "x.csv"}, content=b"\x00\x01garbage",
                    headers={"Content-Type": "application/octet-stream"})
    assert r.status_code == 400
    assert client.get("/workspaces/none/quality").status_code == 404


def test_large_record_speed(client):
    """1 mil. vzorků: nahrání CSV, převzorkování a přenos signálů v rozumném čase."""
    n = 1_000_000
    t = np.arange(n) * 0.1
    rng = np.random.default_rng(1)
    pv = 50 + np.cumsum(rng.normal(0, 0.01, n))
    mv = 40 + 5 * (np.arange(n) % 20000 > 10000)
    csv = "t,PV,MV\n" + "\n".join(f"{a:.1f},{b:.4f},{c:.1f}" for a, b, c in zip(t, pv, mv))
    wid = _ws(client)
    t0 = time.time()
    w = client.post(f"/workspaces/{wid}/data/file", params={"name": "big.csv"}, content=csv.encode(),
                    headers={"Content-Type": "application/octet-stream"}).json()
    t1 = time.time()
    r = client.get(f"/workspaces/{wid}/signals", params={"names": ["PV", "MV"]})
    t2 = time.time()
    meta, sig = signalpack.unframe(r.content)
    assert w["has_data"] and len(sig["PV"][0]) == n and meta["decim"] == 1
    print(f"load {t1 - t0:.2f} s, signals {t2 - t1:.2f} s, {len(r.content) / 2 ** 20:.1f} MB")
    assert t2 - t1 < 2.0 and t1 - t0 < 6.0      # vlastní načtení ≈ 1 s, zbytek je předání 25 MB přes TestClient
