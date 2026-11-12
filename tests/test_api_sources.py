"""API /api/v1 (plán v2, E3): prefix a alias, zdroje, společná mřížka, mapování smyček, návrh a import, signály pro Trendy."""
import io

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from pidtools.api import API_PREFIX, create_app  # noqa: E402
from pidtools.core import demo_data  # noqa: E402

V1 = API_PREFIX


@pytest.fixture(scope="module")
def client():
    with TestClient(create_app()) as c:
        yield c


def _csv(df):
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode()


def _two_files():
    t, sp, pv, mv, q = demo_data()
    t0 = pd.Timestamp("2026-03-01 08:00:00")
    a = pd.DataFrame({"Time": t0 + pd.to_timedelta(t, unit="s"), "LIC101.SP": sp, "LIC101.PV": pv, "LIC101.MV": mv})
    idx = np.arange(0, len(t), 10)
    b = pd.DataFrame({"Time": t0 + pd.to_timedelta(t[idx], unit="s") + pd.Timedelta(hours=1), "FI100.Pritok": q[idx]})
    return _csv(a), _csv(b)


def _ws(client):
    return client.post(f"{V1}/workspaces").json()["id"]


def _upload(client, wid, name, raw, **params):
    return client.post(f"{V1}/workspaces/{wid}/sources", params={"name": name, **params}, content=raw,
                       headers={"Content-Type": "application/octet-stream"})


def _setup(client):
    a, b = _two_files()
    wid = _ws(client)
    assert _upload(client, wid, "a.csv", a, timezone="UTC").status_code == 200
    assert _upload(client, wid, "b.csv", b, timezone="Europe/Prague").status_code == 200
    return wid


# ---- prefix a alias
def test_v1_prefix_and_hidden_alias(client):
    assert client.get(f"{V1}/health").json()["status"] == "ok" and client.get("/health").status_code == 200
    wid = _ws(client)
    assert client.get(f"{V1}/workspaces/{wid}").status_code == 200
    assert client.get(f"/workspaces/{wid}").status_code == 200                   # alias bez prefixu
    assert client.post(f"{V1}/workspaces/{wid}/data/demo").json()["has_data"]
    assert client.get(f"/workspaces/{wid}/loops").json()["loops"]
    paths = client.get("/openapi.json").json()["paths"]
    assert paths and all(p.startswith(V1 + "/") for p in paths)                   # v OpenAPI jen /api/v1
    assert f"{V1}/workspaces/{{wid}}/sources" in paths and f"{V1}/workspaces/{{wid}}/loops/{{index}}/mapping" in paths


def test_v1_requires_token_like_alias():
    with TestClient(create_app(token="tok")) as c:
        assert c.get(f"{V1}/health").status_code == 200
        assert c.get(f"{V1}/workspaces/x").status_code == 401 and c.get("/workspaces/x").status_code == 401
        wid = c.post(f"{V1}/workspaces", headers={"Authorization": "Bearer tok"}).json()["id"]
        assert c.get(f"{V1}/workspaces/{wid}", headers={"X-PID-Token": "tok"}).status_code == 200


# ---- zdroje
def test_sources_crud_and_common_span(client):
    wid = _setup(client)
    s = client.get(f"{V1}/workspaces/{wid}/sources").json()
    assert [x["id"] for x in s["sources"]] == ["s1", "s2"] and s["origin"] == "2026-03-01T08:00:00"
    a, b = s["sources"]
    assert a["kind"] == "csv" and a["rows"] == 3600 and a["has_clock"] and a["period"] == 1.0 and a["used_by"] == [0]
    assert b["period"] == 10.0 and b["timezone"] == "Europe/Prague" and b["columns"] == ["FI100.Pritok"]
    assert b["start"] == 0.0 and a["start"] == 0.0 and s["common"]["end"] == pytest.approx(3590.0)
    assert {k["id"] for k in s["kinds"]} == {"csv", "txt", "xlsx", "opc"} and s["time_grid"]["mode"] == "overlap"
    assert client.get(f"{V1}/workspaces/{wid}/sources/s2").json()["name"] == "b.csv"
    assert client.get(f"{V1}/workspaces/{wid}/sources/zz").status_code == 404
    assert client.delete(f"{V1}/workspaces/{wid}/sources/s2").status_code == 204        # nepoužívá ho žádná role
    assert client.delete(f"{V1}/workspaces/{wid}/sources/s2").status_code == 404
    assert client.delete(f"{V1}/workspaces/{wid}/sources/s1").status_code == 409        # používá ho smyčka


def test_upload_errors(client):
    wid = _ws(client)
    assert _upload(client, wid, "x.csv", b"", kind="nope").status_code == 422
    assert _upload(client, wid, "x.csv", b"a,b\n1,2\n").status_code == 400
    a, _b = _two_files()
    assert _upload(client, wid, "a.csv", a, timezone="Mars/Base").status_code == 400
    assert client.get(f"{V1}/workspaces/{wid}/sources").json()["sources"] == []


def test_patch_source_offset_timezone_and_grid(client):
    wid = _setup(client)
    m = client.get(f"{V1}/workspaces/{wid}/loops/0/mapping").json()
    m["roles"]["dv"] = [{"source": "s2", "column": "FI100.Pritok"}]
    assert client.put(f"{V1}/workspaces/{wid}/loops/0/mapping", json=m).status_code == 200
    w = client.get(f"{V1}/workspaces/{wid}").json()
    assert w["dists"] == ["FI100.Pritok"] and w["n"] == 3591
    r = client.patch(f"{V1}/workspaces/{wid}/sources/s2", json={"offset_s": 60.0})
    assert r.status_code == 200 and r.json()["offset_s"] == 60.0 and client.get(f"{V1}/workspaces/{wid}").json()["n"] == 3540
    assert client.patch(f"{V1}/workspaces/{wid}/sources/s2", json={"offset_s": 1e7}).status_code == 400      # bez překryvu
    assert client.get(f"{V1}/workspaces/{wid}/sources/s2").json()["offset_s"] == 60.0
    assert client.patch(f"{V1}/workspaces/{wid}/sources/s2", json={"timezone": "Nowhere/X"}).status_code == 400
    assert client.patch(f"{V1}/workspaces/{wid}/sources/s2", json={"timezone": None, "offset_s": -3600.0}).status_code == 200
    assert client.patch(f"{V1}/workspaces/{wid}/sources/s9", json={"offset_s": 1.0}).status_code == 404
    g = client.put(f"{V1}/workspaces/{wid}/time-grid", json={"mode": "overlap", "period": 5.0}).json()
    assert g["period"] == 5.0 and client.get(f"{V1}/workspaces/{wid}/time-grid").json()["period"] == 5.0
    assert client.get(f"{V1}/workspaces/{wid}").json()["Ts"] == 5.0
    assert client.put(f"{V1}/workspaces/{wid}/time-grid", json={"mode": "bad"}).status_code == 400
    assert client.put(f"{V1}/workspaces/{wid}/time-grid", json={"period": -3}).status_code == 400


def test_old_single_file_flow_is_one_source(client):
    wid = _ws(client)
    a, _b = _two_files()
    w = client.post(f"{V1}/workspaces/{wid}/data/file", params={"name": "a.csv"}, content=a,
                    headers={"Content-Type": "application/octet-stream"}).json()
    assert w["fname"] == "a.csv" and w["pv"] == "LIC101.PV"
    s = client.get(f"{V1}/workspaces/{wid}/sources").json()["sources"]
    assert [x["name"] for x in s] == ["a.csv"] and s[0]["used_by"] == [0] and s[0]["layout"] == "wide"
    m = client.get(f"{V1}/workspaces/{wid}/loops/0/mapping").json()
    assert m["roles"]["pv"] == {"source": "s1", "column": "LIC101.PV"} and m["roles"]["mv"]["column"] == "LIC101.MV"
    assert m["sources"] == ["s1"] and m["norm_pv"] is not None


# ---- mapování
def test_mapping_put_get_and_errors(client):
    wid = _setup(client)
    url = f"{V1}/workspaces/{wid}/loops/0/mapping"
    m = client.get(url).json()
    m.update(tag="LIC101", description="Reactor level", norm_pv=[0, 200], norm_mv=[0, 100], cascade_to=None)
    m["roles"]["dv"] = [{"source": "s2", "column": "FI100.Pritok"}]
    got = client.put(url, json=m).json()
    assert got["tag"] == "LIC101" and got["description"] == "Reactor level" and got["norm_pv"] == [0, 200]
    assert got["sources"] == ["s1", "s2"] and got["roles"]["dv"][0]["source"] == "s2"
    assert client.get(f"{V1}/workspaces/{wid}/loops").json()["loops"][0]["name"] == "LIC101"
    bad = dict(m, roles=dict(m["roles"], pv={"source": "s1", "column": "nope"}))
    r = client.put(url, json=bad)
    assert r.status_code == 400 and "nope" in r.json()["detail"]
    assert client.put(url, json=dict(m, roles=dict(m["roles"], mv=None))).status_code == 400
    assert client.put(url, json=dict(m, norm_pv=[1])).status_code == 422
    assert client.get(url).json()["description"] == "Reactor level"                # beze změny
    assert client.get(f"{V1}/workspaces/{wid}/loops/5/mapping").status_code == 404
    assert client.put(f"{V1}/workspaces/{wid}/loops/5/mapping", json=m).status_code == 404
    lst = client.get(f"{V1}/workspaces/{wid}/loops/mappings").json()
    assert len(lst) == 1 and lst[0]["index"] == 0


def test_suggest_by_tag_names_and_apply(client):
    t = np.arange(600.0)
    df = pd.DataFrame({"Time": t, "TIC101.PV": t % 9, "TIC101.OUT": t % 5, "TIC101.SP": 3.0 + 0 * t,
                       "FIC200/PV_Out": t % 4, "FIC200/MV": t % 6, "FIC200/SP_Out": 2.0 + 0 * t, "Ambient": t * 0.1})
    wid = _ws(client)
    assert _upload(client, wid, "x.csv", _csv(df)).status_code == 200
    url = f"{V1}/workspaces/{wid}/loops/suggest"
    r = client.post(url, json={}).json()
    assert [s["tag"] for s in r["loops"]] == ["TIC101", "FIC200"] and r["applied"] == []
    assert [s["via"] for s in r["loops"]] == ["dot", "pcs7"] and all(s["complete"] for s in r["loops"])
    assert r["loops"][1]["roles"]["pv"] == {"source": "s1", "column": "FIC200/PV_Out"}
    assert [u["column"] for u in r["unused"]] == ["Ambient"]
    assert len(client.get(f"{V1}/workspaces/{wid}/loops").json()["loops"]) == 1                      # návrh nic nemění
    r = client.post(url, json={"apply": True, "source_ids": ["s1"]}).json()
    names = [lp["name"] for lp in client.get(f"{V1}/workspaces/{wid}/loops").json()["loops"]]
    assert len(names) == 2 and set(names) == {"TIC101", "FIC200"} and r["applied"] == [1]       # smyčka 0 už je TIC101
    assert client.post(url, json={"apply": True}).json()["applied"] == []                        # podruhé nic nového


def test_import_mapping_csv(client):
    wid = _setup(client)
    csv = ("loop;role;source;column;description\nLIC101;PV;s1;LIC101.PV;Level\nLIC101;MV;a.csv;LIC101.MV;\n"
           "LIC101;SP;s1;LIC101.SP;\nLIC101;DV;b.csv;FI100.Pritok;\nLIC101;DV;s1;NOPE;\n")
    url = f"{V1}/workspaces/{wid}/loops/import"
    r = client.post(url, content=csv.encode(), headers={"Content-Type": "text/csv"}).json()
    assert [lp["tag"] for lp in r["loops"]] == ["LIC101"] and r["loops"][0]["description"] == "Level"
    assert len(r["warnings"]) == 1 and r["applied"] == []
    r = client.post(url, params={"apply": True}, content=csv.encode()).json()
    assert r["applied"] == []                                          # PV už používá smyčka 0 → jen se pojmenuje
    m = client.get(f"{V1}/workspaces/{wid}/loops/0/mapping").json()
    assert m["tag"] == "LIC101" and m["description"] == "Level"
    assert client.post(url, content=b"a,b\n1,2\n").status_code == 400


# ---- Trendy
def test_signals_trend_decimation_stats_cursors(client):
    wid = _setup(client)
    url = f"{V1}/workspaces/{wid}/signals/trend"
    r = client.get(url, params={"names": ["s1:LIC101.PV", "s2:FI100.Pritok"], "n": 100, "at": [0, 1800.5, 99999]}).json()
    assert r["origin"] == "2026-03-01T08:00:00" and r["cursors"] == [0, 1800.5, 99999]
    pv, fi = r["series"]
    assert pv["ref"] == "s1:LIC101.PV" and pv["decimated"] and len(pv["t"]) <= 200 and pv["n_raw"] == 3600
    assert fi["n_raw"] == 360 and not fi["decimated"] or len(fi["t"]) <= 200
    assert pv["stats"]["count"] == 3600 and pv["stats"]["min"] <= pv["stats"]["mean"] <= pv["stats"]["max"]
    assert pv["at"][0] is not None and pv["at"][2] is None
    assert max(pv["v"]) == pytest.approx(pv["stats"]["max"]) and min(pv["v"]) == pytest.approx(pv["stats"]["min"])
    sub = client.get(url, params={"names": ["s1:LIC101.PV"], "a": 100, "b": 200}).json()["series"][0]
    assert sub["t"][0] >= 100 and sub["t"][-1] <= 200 and sub["stats"]["count"] == 101
    assert len(client.get(url).json()["series"]) == 4                       # všechny signály všech zdrojů
    assert client.get(url, params={"names": ["s1:NOPE"]}).status_code == 404
    assert client.get(url, params={"names": ["s9:X"]}).status_code == 404
    assert client.get(url, params={"names": ["bad"]}).status_code == 422
    assert client.get(url, params={"a": 10, "b": 5}).status_code == 422
    assert client.get(f"{V1}/workspaces/{_ws(client)}/signals/trend").status_code == 409


def test_trend_aligns_sources_by_offset_and_timezone(client):
    wid = _setup(client)
    client.patch(f"{V1}/workspaces/{wid}/sources/s2", json={"offset_s": 100.0})
    r = client.get(f"{V1}/workspaces/{wid}/signals/trend", params={"names": ["s2:FI100.Pritok"]}).json()
    assert r["series"][0]["t"][0] == pytest.approx(100.0)


def test_range_from_common_axis_to_loop_time(client):
    """Úsek z Trendů (společná osa) → identifikační úsek aktivní smyčky; přepočet na čas smyčky, mimo záznam 422."""
    wid = _ws(client)
    a, _b = _two_files()
    client.post(f"{V1}/workspaces/{wid}/data/file", params={"name": "a.csv"}, content=a,
                headers={"Content-Type": "application/octet-stream"})
    base = f"{V1}/workspaces/{wid}"
    r0 = client.put(f"{base}/range/common", json={"a": 400, "b": 100}).json()   # pořadí mezí je jedno
    assert r0["b"] - r0["a"] == pytest.approx(300.0)
    assert client.get(base).json()["rng"] == pytest.approx([r0["a"], r0["b"]])
    assert client.put(f"{base}/range/common", json={"a": 1e7, "b": 2e7}).status_code == 422
    assert client.put(f"{V1}/workspaces/{_ws(client)}/range/common", json={"a": 0, "b": 1}).status_code == 409
