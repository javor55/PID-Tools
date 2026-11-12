"""API – deník ladění (E10): vytvoření, seznam, detail, stav, poznámky, přílohy, porovnání, obnova, report ze snímku a sekce."""
import base64
import json
import os

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from pidtools.api import create_app  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


@pytest.fixture()
def ws():
    with TestClient(create_app()) as c:
        wid = c.post("/workspaces").json()["id"]
        text = open(os.path.join(HERE, "golden", "tic001.json"), encoding="utf-8").read()
        assert c.put(f"/workspaces/{wid}/project", content=text.encode(), headers={"Content-Type": "application/json"}).status_code == 200
        yield c, f"/workspaces/{wid}"


def test_create_list_detail(ws):
    c, w = ws
    assert c.get(f"{w}/journal").json() == {"snapshots": [], "statuses": ["draft", "deployed", "verified", "rejected"]}
    d = c.post(f"{w}/journal", json={"label": "první", "note": "poznámka"}).json()
    assert d["id"] == "j1" and d["v"] == 1 and d["status"] == "draft" and d["author"] == "local" and d["verified"] is True
    assert d["notes"][0]["text"] == "poznámka" and d["content"]["model"]["code"] and "record" not in d["content"]
    assert d["sets"]["2"]["gain"] is not None and d["results"]["2"]["Ms"] > 0
    lst = c.get(f"{w}/journal").json()["snapshots"]
    assert [s["id"] for s in lst] == ["j1"] and "content" not in lst[0]
    assert c.get(f"{w}/journal/j1").json()["sha256"] == d["sha256"]
    assert c.get(f"{w}/journal/j9").status_code == 404
    assert c.post(f"{w}/journal", json={"loop": "neexistuje"}).status_code == 404


def test_status_note_attachment(ws):
    c, w = ws
    c.post(f"{w}/journal", json={})
    r = c.patch(f"{w}/journal/j1", json={"status": "deployed", "status_note": "v PCS 7", "note": "nasazeno"}).json()
    assert r["status"] == "deployed" and [h["status"] for h in r["history"]] == ["draft", "deployed"] and r["notes"][-1]["text"] == "nasazeno"
    assert c.patch(f"{w}/journal/j1", json={"status": "nonsense"}).status_code == 422
    assert c.patch(f"{w}/journal/j1", json={}).status_code == 422
    data = base64.b64encode(b"protokol").decode()
    a = c.post(f"{w}/journal/j1/attachments", json={"name": "z.txt", "data_b64": data, "mime": "text/plain", "desc": "změna"}).json()
    assert a["size"] == 8 and "data_b64" not in a
    assert c.get(f"{w}/journal/j1/attachments/{a['id']}").json()["data_b64"] == data
    big = base64.b64encode(b"0" * 2_000_000).decode()
    assert c.post(f"{w}/journal/j1/attachments", json={"name": "b", "data_b64": big}).status_code == 422
    assert c.get(f"{w}/journal/j1").json()["verified"] is True


def test_compare_restore_roundtrip(ws):
    c, w = ws
    g0 = c.get(f"{w}/settings").json()["set2_gain"]
    c.post(f"{w}/journal", json={"label": "A"})
    c.patch(f"{w}/settings", json={"set2_gain": g0 * 2})
    c.post(f"{w}/journal", json={"label": "B"})
    cmp = c.get(f"{w}/journal/compare", params={"a": "j1", "b": "j2"}).json()
    assert [(r["section"], r["key"]) for r in cmp["rows"] if r["section"] == "sets"] == [("sets", "set2_gain")]
    assert cmp["a"]["id"] == "j1" and cmp["b"]["id"] == "j2"
    c.patch(f"{w}/settings", json={"set2_gain": 9.0})
    out = c.post(f"{w}/journal/j1/restore").json()
    assert out["autosave"]["kind"] == "restore" and out["data_changed"] == []
    assert c.get(f"{w}/settings").json()["set2_gain"] == pytest.approx(g0)
    assert c.get(f"{w}/journal/{out['autosave']['id']}").json()["content"]["sets"]["set2_gain"] == 9.0
    assert len(c.get(f"{w}/journal").json()["snapshots"]) == 3
    assert c.get(f"{w}/journal/compare", params={"a": "j1", "b": "x"}).status_code == 404
    # deník je v souboru projektu a po načtení do nového prostoru zůstane
    proj = c.get(f"{w}/project").content
    w2 = "/workspaces/" + c.post("/workspaces").json()["id"]
    assert c.put(f"{w2}/project", content=proj, headers={"Content-Type": "application/json"}).status_code == 200
    assert [s["id"] for s in c.get(f"{w2}/journal").json()["snapshots"]] == ["j3", "j2", "j1"]


def test_live_entry_and_settings_migration(ws):
    c, w = ws
    s = c.post(f"{w}/journal/live", json={"when": "2026-11-12T10:00:00.123Z", "struct": "ff", "kpi": {"1": {"iae": 2.0}, "2": {"iae": 1.0}}}).json()
    assert s["kind"] == "live" and s["live"]["kpi"]["2"]["iae"] == 1.0 and s["created"].startswith("2026-11-12T10:00:00")
    # starší projekt s live_runs v nastavení: po otevření jsou souhrny v deníku
    proj = json.loads(open(os.path.join(HERE, "golden", "tic001.json"), encoding="utf-8").read())
    proj["state"]["live_runs"] = [{"when": "2026-10-01T08:00:00", "struct": "pid", "kpi": {"1": {"iae": 3.0}}}]
    w2 = "/workspaces/" + c.post("/workspaces").json()["id"]
    assert c.put(f"{w2}/project", content=json.dumps(proj).encode(), headers={"Content-Type": "application/json"}).status_code == 200
    snaps = c.get(f"{w2}/journal").json()["snapshots"]
    assert [x["kind"] for x in snaps] == ["live_migrated"] and snaps[0]["live"]["kpi"]["1"]["iae"] == 3.0
    assert "live_runs" not in c.get(f"{w2}/settings").json()


def test_report_sections_snapshot_and_summary(ws):
    c, w = ws
    secs = c.get(f"{w}/report/sections?lang=en").json()
    assert [s["id"] for s in secs][:3] == ["model", "tuning", "response"] and {"data", "controller", "scenario", "field", "history"} <= {s["id"] for s in secs}
    assert next(s for s in secs if s["id"] == "history")["available"] is False
    assert secs[0]["title"] != c.get(f"{w}/report/sections?lang=cs").json()[0]["title"]
    c.post(f"{w}/journal", json={"label": "A"})
    c.patch(f"{w}/journal/j1", json={"status": "verified"})
    all_ids = [s["id"] for s in secs]
    h = c.post(f"{w}/journal/j1/report?lang=cs", json={"meta": {"plant": "K2"}, "sections": all_ids, "chart_mode": "cdn"})
    assert h.status_code == 200 and "Historie změn" in h.text and "b-verified" in h.text and "Ověření v provozu" in h.text
    assert "Change history" in c.post(f"{w}/journal/j1/report?lang=en", json={"sections": ["history"], "chart_mode": "cdn"}).text
    assert c.post(f"{w}/journal/j1/report", json={"sections": ["bogus"]}).status_code == 422
    assert c.post(f"{w}/journal/j7/report", json={"sections": ["model"]}).status_code == 404
    # běžný report: nové sekce a A / B z diagnostiky; výchozí sekce beze změny
    r = c.post(f"{w}/report?lang=cs", json={"sections": all_ids, "chart_mode": "cdn", "ab": {"a": [0, 600], "b": [600, 1200]}})
    assert r.status_code == 200 and "Data a signály" in r.text and "A / B" in r.text
    assert c.post(f"{w}/report", json={"sections": ["model"], "ab": {"a": "x"}}).status_code == 422
    sm = c.post(f"{w}/report/summary?lang=cs", json={"findings": [{"name": "TIC001", "finding": "stikce"}]})
    assert sm.status_code == 200 and "Souhrnný report smyček" in sm.text and "v1" in sm.text


def test_author_and_required_note_from_app_settings(ws):
    """Nastavení aplikace › Deník: autor záznamů (mimo týmový režim) a povinná poznámka při změně stavu."""
    c, w = ws
    s = c.get("/app-settings").json()
    s["journal"] = {"author": "J. Novák", "require_note": True}
    assert c.put("/app-settings", json=s).status_code == 200
    try:
        d = c.post(f"{w}/journal", json={"label": "v"}).json()
        assert d["author"] == "J. Novák"
        assert c.patch(f"{w}/journal/{d['id']}", json={"status": "deployed"}).status_code == 422
        r = c.patch(f"{w}/journal/{d['id']}", json={"status": "deployed", "status_note": "nasazeno na noční"})
        assert r.status_code == 200 and r.json()["status"] == "deployed"
    finally:
        c.delete("/app-settings")
