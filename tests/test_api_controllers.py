"""API – knihovna regulátorů (/controllers) a profil regulátoru smyčky (/workspaces/{wid}/controller)."""
import copy

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from pidtools import controllers  # noqa: E402
from pidtools.api import create_app  # noqa: E402

V1 = "/api/v1"


@pytest.fixture()
def client(tmp_path):
    with TestClient(create_app(controllers_dir=str(tmp_path))) as c:
        yield c


def test_list_and_get(client):
    rows = client.get(f"{V1}/controllers").json()
    by = {r["id"]: r for r in rows}
    assert {"pcs7_pidconl", "isa_ideal", "isa_parallel", "isa_series"} <= set(by)
    assert by["isa_ideal"] == dict(id="isa_ideal", vendor="Obecný", name="ISA ideální PID", tag="preset", verified=True)
    assert by["siemens_cont_c"]["verified"] is False and by["pcs7_pidconl"]["tag"] == "preset"
    p = client.get(f"{V1}/controllers/pcs7_pidconl").json()
    assert p["format"] == "pidctrl" and p["params"][0]["key"] == "Gain" and p["structure"]["form"] == "ideal"
    assert client.get(f"{V1}/controllers/nope").status_code == 404


def test_custom_lifecycle(client):
    r = client.post(f"{V1}/controllers", json={"from_id": "pcs7_pidconl", "name": "Moje smyčka"})
    assert r.status_code == 201
    c = r.json()
    assert c["id"] == "custom_moje_smycka" and c["derived_from"] == "pcs7_pidconl"
    assert any(x["id"] == c["id"] and x["tag"] == "custom" and not x["verified"] for x in client.get(f"{V1}/controllers").json())
    c["name"] = "Přejmenováno"
    c["params"][1]["default"] = 77.0
    u = client.put(f"{V1}/controllers/{c['id']}", json=c).json()
    assert u["name"] == "Přejmenováno" and client.get(f"{V1}/controllers/{c['id']}").json()["params"][1]["default"] == 77.0
    assert client.delete(f"{V1}/controllers/{c['id']}").status_code == 204
    assert client.get(f"{V1}/controllers/{c['id']}").status_code == 404
    assert client.delete(f"{V1}/controllers/{c['id']}").status_code == 404
    assert client.post(f"{V1}/controllers", json={"from_id": "nope"}).status_code == 404


def test_presets_read_only_and_validation(client):
    p = client.get(f"{V1}/controllers/isa_ideal").json()
    assert client.put(f"{V1}/controllers/isa_ideal", json=p).status_code == 403
    assert client.delete(f"{V1}/controllers/isa_ideal").status_code == 403
    c = client.post(f"{V1}/controllers", json={"from_id": "isa_ideal"}).json()
    bad = dict(c, params=[dict(c["params"][0], repr="zzz")] + c["params"][1:])
    r = client.put(f"{V1}/controllers/{c['id']}", json=bad)
    assert r.status_code == 422 and r.json()["detail"]["problems"][0]["path"] == "params[0].repr"
    bad = dict(c, structure=dict(c["structure"], form="nesmysl"))               # neznámá část registru
    r = client.put(f"{V1}/controllers/{c['id']}", json=bad)
    assert r.status_code == 422 and "nesmysl" in r.json()["detail"]["message"]


def test_import_export(client):
    r = client.get(f"{V1}/controllers/isa_parallel/export")
    assert r.status_code == 200 and 'filename="isa_parallel.pidctrl"' in r.headers["content-disposition"]
    data = r.json()
    assert data["format"] == "pidctrl" and data["id"] == "isa_parallel"
    imp = client.post(f"{V1}/controllers/import", json=data)
    assert imp.status_code == 201 and imp.json()["id"] != "isa_parallel"
    again = client.get(f"{V1}/controllers/{imp.json()['id']}/export").json()
    assert again["params"] == data["params"] and again["structure"] == data["structure"]
    assert client.post(f"{V1}/controllers/import", json={"format": "pidctrl", "version": 99, "structure": {}, "params": [],
                                                         "id": "x"}).status_code == 422
    assert client.get(f"{V1}/controllers/nope/export").status_code == 404


def test_protocol_pidconl_suitable(client):
    r = client.post(f"{V1}/controllers/pcs7_pidconl/test", headers={"Accept-Language": "cs"})
    assert r.status_code == 200
    d = r.json()
    assert d["verdict"] == "suitable" and d["verdict_text"] == "Vhodný pro ladění" and d["reasons"] == []
    assert len(d["checks"]) == 12 and d["checks"][0]["name"] == "Překlad a platnost profilu"
    assert all(c["status"] in ("ok", "warn") and c["message"] for c in d["checks"])
    en = client.post(f"{V1}/controllers/pcs7_pidconl/test?lang=en").json()
    assert en["verdict_text"] == "Suitable for tuning"
    assert client.post(f"{V1}/controllers/nope/test").status_code == 404


def test_protocol_unsuitable_custom(client):
    c = client.post(f"{V1}/controllers", json={"from_id": "isa_ideal"}).json()
    c["structure"]["antiwindup"] = "none"
    client.put(f"{V1}/controllers/{c['id']}", json=c)
    d = client.post(f"{V1}/controllers/{c['id']}/test?lang=cs").json()
    assert d["verdict"] == "unsuitable" and d["verdict_text"] == "Nevhodný" and d["reasons"] == ["antiwindup"]


def test_map_and_canonical(client):
    body = {"canonical": {"Kc": 2.0, "Ti": 20.0, "Td": 3.0, "b": 1.0, "c": 1.0, "N": 10.0}}
    m = client.post(f"{V1}/controllers/isa_parallel/map", json=body).json()
    assert m["values"]["Kp"] == 2.0 and m["values"]["Ki"] == pytest.approx(0.1) and m["values"]["Kd"] == 6.0
    assert m["warnings"] == [] and m["effective"]["Ti"] == pytest.approx(20.0)
    back = client.post(f"{V1}/controllers/isa_parallel/canonical", json={"values": m["values"]}).json()
    assert (back["Kc"], back["Ti"], back["Td"]) == pytest.approx((2.0, 20.0, 3.0))
    w = client.post(f"{V1}/controllers/isa_series/map?lang=cs",
                    json={"canonical": dict(body["canonical"], Ti=10.0, Td=5.0)}).json()
    assert w["warnings"][0]["key"] == "ctl_w_series_limit" and "Ti ≥ 4·Td" in w["warnings"][0]["text"]
    noi = client.post(f"{V1}/controllers/isa_ideal/map", json={"canonical": dict(body["canonical"], Ti=None)}).json()
    assert noi["values"]["Ti"] is None and noi["effective"]["Ti"] is None


def test_gain_in_engineering_units(client):
    c = client.post(f"{V1}/controllers", json={"from_id": "isa_ideal"}).json()
    next(p for p in c["params"] if p["role"] == "Kc")["repr"] = "K_eng"
    client.put(f"{V1}/controllers/{c['id']}", json=c)
    body = {"canonical": {"Kc": 2.0, "Ti": 20.0, "Td": 0.0}, "pv_range": [0, 200], "mv_range": [0, 100]}
    assert client.post(f"{V1}/controllers/{c['id']}/map", json=body).json()["values"]["Kc"] == pytest.approx(1.0)
    assert client.post(f"{V1}/controllers/{c['id']}/map", json={"canonical": body["canonical"]}).status_code == 422


def test_loop_controller_and_project(client, tmp_path):
    wid = client.post(f"{V1}/workspaces").json()["id"]
    g = client.get(f"{V1}/workspaces/{wid}/controller").json()
    assert g["is_default"] and g["profile"]["id"] == "pcs7_pidconl"
    put = client.put(f"{V1}/workspaces/{wid}/controller", json={"from_id": "isa_series"}).json()
    assert not put["is_default"] and put["profile"]["id"] == "isa_series" and put["checksum"] != g["checksum"]
    custom = copy.deepcopy(controllers.load_preset("isa_ideal"))
    custom["id"], custom["name"] = "moje", "Moje"
    assert client.put(f"{V1}/workspaces/{wid}/controller", json={"profile": custom, "from_id": "isa_ideal"}).status_code == 422
    bad = dict(custom, structure=dict(custom["structure"], d={"source": "x"}))
    assert client.put(f"{V1}/workspaces/{wid}/controller", json={"profile": bad}).status_code == 422
    assert client.put(f"{V1}/workspaces/{wid}/controller", json={"from_id": "nope"}).status_code == 404
    # kopie je v projektu: uloží se a po načtení do nového prostoru se obnoví
    client.put(f"{V1}/workspaces/{wid}/controller", json={"profile": custom})
    proj = client.get(f"{V1}/workspaces/{wid}/project?data=false")
    assert proj.json()["controller"]["id"] == "moje"
    wid2 = client.post(f"{V1}/workspaces").json()["id"]
    assert client.put(f"{V1}/workspaces/{wid2}/project", content=proj.content).status_code == 200
    assert client.get(f"{V1}/workspaces/{wid2}/controller").json()["profile"]["id"] == "moje"
    # návrat k výchozímu
    d = client.put(f"{V1}/workspaces/{wid}/controller", json={}).json()
    assert d["is_default"] and d["profile"]["id"] == "pcs7_pidconl"
    assert client.get(f"{V1}/workspaces/nope/controller").status_code == 404
