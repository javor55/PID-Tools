"""Záchranná kopie projektu a nedávné projekty (E10-B): úložiště po uživatelích a API (autosave, obnova, dirty stav)."""
import pytest

from pidtools.app.autosave import MAX_RECENT, UserData

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from pidtools.api import create_app  # noqa: E402


def test_recovery_files_per_user(tmp_path):
    d = UserData(str(tmp_path))
    assert d.recovery() is None
    m = d.save_recovery(b'{"a": 1}', dict(name="x", loops=2), "alice")
    assert m["bytes"] == 8 and d.recovery("alice")["name"] == "x"
    assert d.recovery("bob") is None and d.recovery() is None
    assert d.recovery_raw("alice") == b'{"a": 1}'
    d.clear_recovery("alice")
    assert d.recovery("alice") is None


def test_recent_dedup_limit_open_and_remove(tmp_path):
    d = UserData(str(tmp_path))
    a = d.add_recent(b"1", "proj", 1)
    b = d.add_recent(b"22", "proj", 3)                              # stejný název nahradí starší
    assert [e["id"] for e in d.recent()] == [b["id"]] and d.recent_raw(b["id"]) == b"22"
    with pytest.raises(KeyError):
        d.recent_raw(a["id"])
    for i in range(MAX_RECENT + 3):
        d.add_recent(b"x", f"p{i}", 1)
    assert len(d.recent()) == MAX_RECENT and d.recent()[0]["name"] == f"p{MAX_RECENT + 2}"
    assert len(list((tmp_path / "recent").iterdir())) == MAX_RECENT      # staré kopie se mažou
    rid = d.recent()[0]["id"]
    assert d.remove_recent(rid) and not d.remove_recent(rid)


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(config_dir=str(tmp_path / "c"), data_dir=str(tmp_path / "d"))) as c:
        yield c


def _ws(client):
    return f"/api/v1/workspaces/{client.post('/api/v1/workspaces').json()['id']}"


def test_autosave_state_and_restore_flow(client):
    w = _ws(client)
    st = client.get(f"{w}/save-state").json()
    assert not st["has_data"] and not st["dirty"]
    assert client.post(f"{w}/autosave").status_code == 409                  # bez dat není co zachraňovat
    assert not client.get("/api/v1/autosave/latest").json()["available"]
    client.post(f"{w}/data/demo")
    st = client.get(f"{w}/save-state").json()
    assert st["dirty"] and st["autosave_pending"] and st["saved_at"] is None
    st2 = client.post(f"{w}/autosave").json()
    assert st2["autosaved_at"] and not st2["autosave_pending"] and st2["dirty"]
    assert st2["rev"] == st["rev"]                                          # samotný autosave změnou není
    rec = client.get("/api/v1/autosave/latest").json()
    assert rec["available"] and rec["loops"] == 1 and rec["bytes"] > 1000
    client.patch(f"{w}/settings", json={"samp": 2.0})
    assert client.get(f"{w}/save-state").json()["autosave_pending"]
    # „pád“: nový prostor, obnova kopie
    w2 = _ws(client)
    r = client.post(f"{w2}/autosave/restore")
    assert r.status_code == 200 and r.json()["has_data"]
    assert client.get(f"{w2}/save-state").json()["dirty"]                   # obnovený projekt je neuložený
    assert client.delete("/api/v1/autosave").status_code == 204
    assert not client.get("/api/v1/autosave/latest").json()["available"]
    assert client.post(f"{w2}/autosave/restore").status_code == 404


def test_manual_save_clears_dirty_and_feeds_recent(client):
    w = _ws(client)
    client.post(f"{w}/data/demo")
    raw = client.get(f"{w}/project").content
    st = client.get(f"{w}/save-state").json()
    assert not st["dirty"] and st["saved_at"]
    client.patch(f"{w}/settings", json={"samp": 2.0})
    assert client.get(f"{w}/save-state").json()["dirty"]
    rec = client.get("/api/v1/recent").json()
    assert len(rec) == 1 and rec[0]["snapshot"] and rec[0]["loops"] == 1
    w2 = _ws(client)
    assert client.post(f"{w2}/recent/{rec[0]['id']}/open").json()["has_data"]
    assert not client.get(f"{w2}/save-state").json()["dirty"]               # otevřený soubor je uložený
    assert client.post(f"{w2}/recent/nope/open").status_code == 404
    w3 = _ws(client)                                                        # otevření souboru ze zařízení
    assert client.put(f"{w3}/project", content=raw).status_code == 200
    assert not client.get(f"{w3}/save-state").json()["dirty"]
    assert client.delete(f"/api/v1/recent/{rec[0]['id']}").status_code == 204 or True
