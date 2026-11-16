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


# ---- úloha /batch: identifikace → návrh → převzetí
def _batch(c, u, loops, action, params=None, t=300):
    r = c.post(f"{u}/batch", json={"loops": loops, "action": action, **({"params": params} if params else {})})
    assert r.status_code == 200, r.text
    jid = r.json()["id"]
    st = _wait(c, jid, t)
    out = c.get(f"{u}/batch/{jid}").json()
    return st, out


def _status(out):
    return [(x["loop"], x["status"]) for x in out["rows"]]


def test_batch_validation(env):
    c, _, u = env
    assert c.post(f"{u}/batch", json={"loops": [], "action": "identify"}).status_code == 422
    assert c.post(f"{u}/batch", json={"loops": [7], "action": "identify"}).status_code == 404
    assert c.post(f"{u}/batch", json={"loops": [0], "action": "delete"}).status_code == 422
    assert c.post(f"{u}/batch", json={"loops": [0], "action": "tune", "params": {"ctype": "PD"}}).status_code == 422
    assert c.get(f"{u}/batch/j999").status_code == 404


def test_batch_identify_skips_loop_without_excitation(env):
    c, _, u = env
    st, out = _batch(c, u, [0, 1, 2], "identify")
    assert st["state"] == "done" and st["progress"] == 1.0 and st["text"] == "3 / 3 · FIC3"
    assert _status(out) == [(0, "ok"), (1, "ok"), (2, "skipped")]
    assert out["rows"][2]["reason"]["key"] == "q_steps_none" and out["total"] == 3
    rows = _rows(c, u)
    assert [rows[i]["stage"] for i in range(3)] == ["model", "model", "data"]
    assert rows[0]["fit"] is not None and rows[1]["fit"] is not None and rows[2]["fit"] is None
    assert rows[0]["model"] == "P1D"


def test_batch_tune_keeps_set2_and_stores_proposal(env):
    c, _, u = env
    before = {i: (r["set2"], r["set2_defined"]) for i, r in _rows(c, u).items()}
    st, out = _batch(c, u, [0, 1, 2], "tune", {"method": "SIMC", "ctype": "PI"})
    assert st["state"] == "done"
    assert _status(out) == [(0, "ok"), (1, "ok"), (2, "skipped")]
    assert out["rows"][2]["reason"]["key"] == "batch_skip_no_model"
    rows = _rows(c, u)
    assert {i: (r["set2"], r["set2_defined"]) for i, r in rows.items()} == before     # Set 2 beze změny
    assert [rows[i]["stage"] for i in range(3)] == ["proposal", "proposal", "data"]
    c.put(f"{u}/loops/active", json={"index": 1})
    sug = c.get(f"{u}/settings").json()["batch_sug|P1D"]
    assert sug[3] == "SIMC" and sug[0] > 0
    s = c.post(f"{u}/tuning/suggest", json={"method": "SIMC"}).json()      # stejný návrh jako v Ladění
    assert sug[:3] == pytest.approx([s["Kc"], s["Ti"], s["Td"]])
    c.put(f"{u}/loops/active", json={"index": 0})
    # metoda, která pro model neexistuje, se přeskočí s důvodem
    _, out = _batch(c, u, [0], "tune", {"method": "NOPE"})
    assert out["rows"][0]["status"] == "skipped" and out["rows"][0]["reason"]["key"] == "batch_skip_method"


def test_batch_accept_writes_set2(env):
    c, _, u = env
    c.put(f"{u}/loops/active", json={"index": 1})
    sug = c.get(f"{u}/settings").json()["batch_sug|P1D"]
    c.put(f"{u}/loops/active", json={"index": 0})
    st, out = _batch(c, u, [0, 1, 2], "accept")
    assert st["state"] == "done" and _status(out) == [(0, "ok"), (1, "ok"), (2, "skipped")]
    assert out["rows"][2]["reason"]["key"] == "batch_skip_no_proposal"
    rows = _rows(c, u)
    assert [rows[i]["stage"] for i in range(3)] == ["set2", "set2", "data"]
    assert rows[2]["set2_defined"] is False
    assert [rows[1]["set2"][k] for k in ("gain", "ti", "td")] == pytest.approx(sug[:3])
    c.put(f"{u}/loops/active", json={"index": 1})
    cur = c.get(f"{u}/settings").json()
    assert "batch_sug|P1D" not in cur and cur["set2_defined"] is True and cur["tune_hist"][0]["method"] == "SIMC"
    c.put(f"{u}/loops/active", json={"index": 0})
    _, out = _batch(c, u, [0], "accept")                     # druhé převzetí: už není co převzít
    assert out["rows"][0]["status"] == "skipped"


def test_batch_proposal_survives_project_file_and_old_file_loads(env):
    c, _, u = env
    _batch(c, u, [0], "tune", {"method": "SIMC"})
    raw = c.get(f"{u}/project").content
    assert b"batch_sug|P1D" in raw
    with TestClient(create_app()) as c2:
        wid2 = c2.post("/api/v1/workspaces").json()["id"]
        u2 = f"/api/v1/workspaces/{wid2}"
        assert c2.put(f"{u2}/project", content=raw, headers={"content-type": "application/json"}).status_code == 200
        assert _rows(c2, u2)[0]["stage"] == "proposal"
        old = raw.replace(b"batch_sug|P1D", b"x_unknown_key")       # starý soubor / poškozený klíč: bez návrhu, bez chyby
        assert c2.put(f"{u2}/project", content=old, headers={"content-type": "application/json"}).status_code == 200
        assert _rows(c2, u2)[0]["stage"] == "set2"


def test_batch_rejects_bad_proposal_value(env):
    c, _, u = env
    assert c.patch(f"{u}/settings", json={"batch_sug|P1D": [0.0, 10, 0, "SIMC"]}).status_code == 422
    assert c.patch(f"{u}/settings", json={"batch_sug|P1D": "x"}).status_code == 422


def test_batch_cancel_keeps_finished_loops():
    with TestClient(create_app()) as c:
        _, u = _project(c)
        for _ in range(3):                                  # další smyčky, ať úloha trvá
            c.post(f"{u}/loops", json={"name": "FICx", "pv": "FIC2.PV", "mv": "FIC2.MV"})
        for i in range(5):                                  # všechny modely: identifikace smyčky trvá déle
            c.put(f"{u}/loops/active", json={"index": i})
            c.patch(f"{u}/settings", json={"chosen": ["P0D", "P1D", "P2D", "I1D"]})
        c.put(f"{u}/loops/active", json={"index": 0})
        jid = c.post(f"{u}/batch", json={"loops": [0, 1, 3, 4, 5], "action": "identify"}).json()["id"]
        t0 = time.time()
        while time.time() - t0 < 300:
            out = c.get(f"{u}/batch/{jid}").json()
            if out["rows"] or out["job"]["state"] not in ("queued", "running"):
                break
            time.sleep(0.05)
        assert out["rows"], out
        assert c.post(f"/api/v1/jobs/{jid}/cancel").json()["state"] in ("cancelled", "done")
        out = c.get(f"{u}/batch/{jid}").json()
        done = {x["loop"] for x in out["rows"] if x["status"] == "ok"}
        assert done and out["job"]["state"] == "cancelled" and len(out["rows"]) < 5
        stages = {i: r["stage"] for i, r in _rows(c, u).items()}
        assert all(stages[i] == ("model" if i in done else "data") for i in (0, 1, 3, 4, 5))


# ---- hromadný export
def _single(c, u, i, fmt, n):
    c.put(f"{u}/loops/active", json={"index": i})
    r = c.get(f"{u}/tuning/export", params={"fmt": fmt, "n": n})
    assert r.status_code == 200
    return r.text


@pytest.mark.parametrize("fmt", ["csv", "pcs7", "tia", "deltav"])
def test_batch_export_same_rows_as_single_export(env, fmt):
    c, _, u = env
    for n in (1, 2):
        r = c.get(f"{u}/batch/export", params={"fmt": fmt, "loops": "0,1,2", "n": n})
        assert r.status_code == 200 and r.headers["x-skipped-loops"] == "2"      # smyčka bez modelu se nevyexportuje
        assert f"tuning_set{n}_{fmt}_loops." in r.headers["content-disposition"]
        text, names = r.text, {0: "FIC1", 1: "FIC2"}
        singles = {i: _single(c, u, i, fmt, n) for i in (0, 1)}
        c.put(f"{u}/loops/active", json={"index": 0})
        lines = text.splitlines()
        if fmt == "csv":
            head = singles[0].splitlines()[0]
            assert lines[0] == "loop;" + head
            assert [x for x in lines if x.startswith("FIC3")] == []
            for i, nm in names.items():
                rows = singles[i].splitlines()[1:]
                assert [x for x in lines[1:] if x.startswith(nm + ";")] == [f"{nm};{x}" for x in rows]
        elif fmt == "deltav":
            for i, nm in names.items():
                assert [x for x in lines if x.startswith(nm + "\t")] == [f"{nm}\t{x}" for x in singles[i].splitlines()]
            assert len(lines) == sum(len(s.splitlines()) for s in singles.values())
        else:
            for i, nm in names.items():
                assert f"// ===== loop {nm} =====\n{singles[i]}" in text
            assert "FIC3" not in text


def test_batch_export_errors(env):
    c, _, u = env
    assert c.get(f"{u}/batch/export", params={"fmt": "xml", "loops": "0"}).status_code == 422
    assert c.get(f"{u}/batch/export", params={"fmt": "csv", "loops": ""}).status_code == 422
    assert c.get(f"{u}/batch/export", params={"fmt": "csv", "loops": "a"}).status_code == 422
    assert c.get(f"{u}/batch/export", params={"fmt": "csv", "loops": "9"}).status_code == 404
    assert c.get(f"{u}/batch/export", params={"fmt": "csv", "loops": "2"}).status_code == 409      # jen smyčka bez modelu
