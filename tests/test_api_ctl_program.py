"""API – katalog částí (/controllers/parts) a vlastní rovnice (/controllers/compile, uložení programu jako profilu)."""
import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from pidtools.api import create_app  # noqa: E402

V1 = "/api/v1"
SRC = '''param Ts = 1 [s]
param Kp = 2.0 "Zesílení" [-] min 0
param Ti = 30 "Integrační čas" [s] min 0.1
state I = 0 init MV0 - Kp * (SP - PV) - FF
e = SP - PV
v = Kp * e + I + FF
MV = clamp(v, MV_LO, MV_HI)
I = I + Kp / Ti * e * dt + (MV - v) * dt / Ti
map Kp = Kc
map Ti = Ti
'''


@pytest.fixture()
def client(tmp_path):
    with TestClient(create_app(controllers_dir=str(tmp_path))) as c:
        yield c


def test_parts_catalog(client):
    parts = client.get(f"{V1}/controllers/parts").json()
    by = {(p["kind"], p["id"]): p for p in parts}
    assert ("output_stages", "three_step") in by and ("antiwindups", "external_reset") in by and ("deadbands", "gap") in by
    gap = by[("deadbands", "gap")]
    assert {p["role"] for p in gap["params"]} == {"deadband", "gap_gain"} and gap["description"].startswith(("Gap", "Gap:"))
    assert all(p["description"] and not p["description"].startswith("ctl_part_") for p in parts)


def test_compile_ok_with_checks(client):
    r = client.post(f"{V1}/controllers/compile", json={"source": SRC}).json()
    assert r["ok"] and r["errors"] == [] and r["has_mapping"] and r["tuning_roles"] == ["Kp", "Ti"]
    assert [p["key"] for p in r["params"]] == ["Ts", "Kp", "Ti"] and r["params"][1]["range"][0] == 0
    assert r["program"]["format"] == "pidprog" and r["program"]["outputs"] == ["MV"]
    ids = {c["id"]: c["status"] for c in r["checks"]["checks"]}
    assert set(ids) == {"translation", "determinism", "rest", "direction", "switching", "numerics", "performance"}
    assert "fail" not in ids.values()
    assert client.post(f"{V1}/controllers/compile", json={"source": SRC, "quick": False}).json().get("checks") is None


def test_compile_errors_with_position_and_language(client):
    r = client.post(f"{V1}/controllers/compile?lang=cs", json={"source": "param a = 1\ne = a +\nMV = zzz\n"}).json()
    assert not r["ok"] and r.get("program") is None
    assert [(e["line"], e["col"], e["code"]) for e in r["errors"]] == [(2, 8, "expected"), (3, 6, "unknown_name")]
    assert "zzz" in r["errors"][1]["message"] and "Neznámý" in r["errors"][1]["message"]
    r = client.post(f"{V1}/controllers/compile?lang=en", json={"source": "MV = zzz"}).json()
    assert r["errors"][0]["message"] == 'Unknown name "zzz".'
    w = client.post(f"{V1}/controllers/compile", json={"source": "param a = 1 [s]\nparam b = 1 [%]\nMV = a + b", "quick": False}).json()
    assert w["ok"] and w["warnings"][0]["code"] == "unit_mismatch" and w["warnings"][0]["line"] == 3


def test_program_profile_saved_through_existing_endpoints(client):
    body = {"format": "pidctrl", "version": 1, "id": "prog_pi", "name": "Program PI", "kind": "program", "source": SRC}
    r = client.post(f"{V1}/controllers/import", json=body)
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["kind"] == "program" and p["source"] == SRC and p["program"]["format"] == "pidprog"
    assert [x["key"] for x in p["params"]] == ["Ts", "Kp", "Ti"]
    assert client.get(f"{V1}/controllers/prog_pi").json()["source"] == SRC
    bad = client.post(f"{V1}/controllers/import", json=dict(body, id="prog_bad", source="MV = nope"))
    assert bad.status_code == 422 and bad.json()["detail"]["problems"][0]["path"] == "source:1:6"
    # test použitelnosti a mapování fungují i pro program
    t = client.post(f"{V1}/controllers/prog_pi/test").json()
    assert t["verdict"] in ("suitable", "optimisation_only") and len(t["checks"]) == 12
    m = client.post(f"{V1}/controllers/prog_pi/map", json={"canonical": {"Kc": 3.0, "Ti": 45.0}}).json()
    assert m["values"] == {"Kp": 3.0, "Ti": 45.0} and m["effective"]["Kc"] == 3.0
    # profil smyčky
    wid = client.post(f"{V1}/workspaces").json()["id"]
    put = client.put(f"{V1}/workspaces/{wid}/controller", json={"from_id": "prog_pi"})
    assert put.status_code == 200 and put.json()["profile"]["kind"] == "program"
