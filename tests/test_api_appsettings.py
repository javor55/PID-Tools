"""API nastavení aplikace (E10-B): čtení a změna, export / import, logo, výchozí hodnoty nové smyčky a nového prostoru,
dělení po uživatelích v týmovém režimu."""
import json

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from pidtools.api import create_app  # noqa: E402
from pidtools.api.deploy import DeployConfig  # noqa: E402

V = "/api/v1"


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(config_dir=str(tmp_path / "c"), data_dir=str(tmp_path / "d"),
                               controllers_dir=str(tmp_path / "ctl"))) as c:
        yield c


def test_get_defaults_put_and_clamp(client):
    s = client.get(f"{V}/app-settings").json()
    assert s["defaults"]["controller"] == "pcs7_pidconl" and s["general"]["autosave_min"] == 1
    s["charts"]["height"] = 420
    s["journal"]["author"] = "Eva"
    s["connections"]["opc"] = [{"name": "Reaktor", "url": "opc.tcp://plc:4840"}, {"name": "x", "url": "http://bad"}]
    got = client.put(f"{V}/app-settings", json=s).json()
    assert got["charts"]["height"] == 420 and got["journal"]["author"] == "Eva"
    assert got["connections"]["opc"] == [{"name": "Reaktor", "url": "opc.tcp://plc:4840"}]      # nesmyslná adresa se zahodí
    assert client.get(f"{V}/app-settings").json() == got                                       # přežije načtení ze souboru
    bad = dict(s, charts=dict(s["charts"], height=5))
    assert client.put(f"{V}/app-settings", json=bad).status_code == 422
    assert client.delete(f"{V}/app-settings").json()["journal"]["author"] == ""


def test_export_import_roundtrip_and_errors(client):
    s = client.get(f"{V}/app-settings").json()
    s["report"]["company"] = "ACME"
    client.put(f"{V}/app-settings", json=s)
    r = client.get(f"{V}/app-settings/export")
    assert "attachment" in r.headers["content-disposition"]
    file = r.json()
    assert file["format"] == "pidtools.settings" and file["settings"]["report"]["company"] == "ACME"
    client.delete(f"{V}/app-settings")
    got = client.post(f"{V}/app-settings/import", content=r.content).json()
    assert got["report"]["company"] == "ACME"
    assert client.post(f"{V}/app-settings/import", content=b"nope").status_code == 400
    assert client.post(f"{V}/app-settings/import", content=json.dumps({"format": "x", "version": 1})).status_code == 400
    future = dict(file, version=99)
    assert client.post(f"{V}/app-settings/import", content=json.dumps(future)).status_code == 400


def test_logo_upload_get_delete_and_kept_by_put(client):
    assert client.get(f"{V}/app-settings/logo").status_code == 404
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 20
    s = client.post(f"{V}/app-settings/logo?name=firma.PNG", content=png).json()
    assert s["report"]["logo"] == "logo.png"
    r = client.get(f"{V}/app-settings/logo")
    assert r.content == png and r.headers["content-type"] == "image/png"
    s["report"]["logo"] = ""                                                  # PUT název loga nepřepíše (nahrává se zvlášť)
    assert client.put(f"{V}/app-settings", json=s).json()["report"]["logo"] == "logo.png"
    assert client.post(f"{V}/app-settings/logo?name=a.exe", content=b"x").status_code == 422
    assert client.post(f"{V}/app-settings/logo?name=a.png", content=b"x" * 1_100_000).status_code == 422
    assert client.delete(f"{V}/app-settings/logo").json()["report"]["logo"] == ""
    assert client.get(f"{V}/app-settings/logo").status_code == 404


def test_diagnostics_schema_lists_thresholds(client):
    items = client.get(f"{V}/app-settings/diagnostics-schema").json()
    assert len(items) >= 4 and all(i["lo"] <= i["default"] <= i["hi"] for i in items)


def test_defaults_applied_to_new_workspace_and_new_loop(client, tmp_path):
    # vlastní regulátor z knihovny jako výchozí + prahy diagnostiky + volby simulace
    prof = client.post(f"{V}/controllers", json={"from_id": "isa_ideal", "name": "Moje PID"}).json()
    s = client.get(f"{V}/app-settings").json()
    items = client.get(f"{V}/app-settings/diagnostics-schema").json()
    it = items[0]
    s["diagnostics"]["thresholds"] = {it["rule"]: {it["name"]: it["hi"]}}
    s["defaults"]["controller"] = prof["id"]
    s["defaults"]["sim"].update(ctype="PID", opt_ms=2.0)
    client.put(f"{V}/app-settings", json=s)
    wid = client.post(f"{V}/workspaces").json()["id"]
    w = f"{V}/workspaces/{wid}"
    assert client.get(f"{w}/controller").json()["profile"]["id"] == prof["id"]
    thr = client.get(f"{w}/triage/thresholds").json()["values"]
    assert thr[it["rule"]][it["name"]] == it["hi"]
    client.post(f"{w}/data/demo")                                              # načtení dat výchozí hodnoty nezahodí
    assert client.get(f"{w}/controller").json()["profile"]["id"] == prof["id"]
    assert client.get(f"{w}/settings").json()["ctype"] == "PID"
    client.post(f"{w}/loops", json={})
    assert client.get(f"{w}/controller").json()["profile"]["id"] == prof["id"]   # i nová smyčka v existujícím projektu
    # výchozí regulátor, který zmizel z knihovny, nic nerozbije
    s["defaults"]["controller"] = "smazany_profil"
    client.put(f"{V}/app-settings", json=s)
    w2 = f"{V}/workspaces/{client.post(f'{V}/workspaces').json()['id']}"
    assert client.get(f"{w2}/controller").json()["is_default"]


def test_default_settings_keep_new_workspace_as_before(client):
    w = f"{V}/workspaces/{client.post(f'{V}/workspaces').json()['id']}"
    assert client.get(f"{w}/controller").json()["is_default"]
    thr = client.get(f"{w}/triage/thresholds").json()
    assert all(i["value"] == i["default"] for i in thr["items"])


def test_team_mode_settings_isolated_per_user(tmp_path):
    cfg = DeployConfig(auth="header", trust_header=True)
    with TestClient(create_app(team=cfg, config_dir=str(tmp_path / "c"), data_dir=str(tmp_path / "d"))) as c:
        a, b = {"X-Forwarded-Email": "alice@acme.com"}, {"X-Forwarded-Email": "bob@acme.com"}
        s = c.get(f"{V}/app-settings", headers=a).json()
        s["journal"]["author"] = "Alice"
        c.put(f"{V}/app-settings", json=s, headers=a)
        c.post(f"{V}/app-settings/logo?name=l.svg", content=b"<svg/>", headers=a)
        assert c.get(f"{V}/app-settings", headers=b).json()["journal"]["author"] == ""
        assert c.get(f"{V}/app-settings/logo", headers=b).status_code == 404
        assert c.get(f"{V}/app-settings/logo", headers=a).status_code == 200
        assert c.get(f"{V}/app-settings").status_code == 401                    # bez přihlášení nic
        # záchranná kopie a nedávné projekty také po uživatelích
        wa = f"{V}/workspaces/{c.post(f'{V}/workspaces', headers=a).json()['id']}"
        c.post(f"{wa}/data/demo", headers=a)
        assert c.post(f"{wa}/autosave", headers=a).status_code == 200
        assert c.get(f"{V}/autosave/latest", headers=a).json()["available"]
        assert not c.get(f"{V}/autosave/latest", headers=b).json()["available"]
        c.get(f"{wa}/project", headers=a)
        assert len(c.get(f"{V}/recent", headers=a).json()) == 1 and c.get(f"{V}/recent", headers=b).json() == []
        wb = f"{V}/workspaces/{c.post(f'{V}/workspaces', headers=b).json()['id']}"
        assert c.post(f"{wb}/autosave/restore", headers=b).status_code == 404
        # cizí nastavení výchozího regulátoru neovlivní prostor druhého uživatele
        assert c.get(f"{wb}/controller", headers=b).json()["is_default"]
