"""Model `LoopSettings` (TICKET-013): klíče a výchozí hodnoty odpovídají app.project a DEFAULTS, GET i PATCH vrací vše."""
import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from pidtools.api import create_app  # noqa: E402
from pidtools.api.data import LoopSettings  # noqa: E402
from pidtools.app import project as prj  # noqa: E402
from pidtools.app.workspace import DEFAULTS  # noqa: E402

TOKEN = "t0ken"
H = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture(scope="module")
def client():
    with TestClient(create_app(token=TOKEN)) as c:
        yield c


def _new_ws(client):
    r = client.post("/api/v1/workspaces", headers=H)
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def test_model_matches_state_keys():
    assert set(LoopSettings.model_fields) == set(prj.STATE_KEYS)
    for k, v in DEFAULTS.items():
        assert LoopSettings.model_fields[k].default == v, k
    for k in set(prj.STATE_KEYS) - set(DEFAULTS):
        assert LoopSettings.model_fields[k].default is None, k
    for k in prj.ENUMS:                       # výčty z project.py jsou v modelu jako Literal
        for val in prj.ENUMS[k]:
            LoopSettings(**{k: val})
        with pytest.raises(ValueError):
            LoopSettings(**{k: "?"})


def test_get_new_workspace_has_all_keys(client):
    wid = _new_ws(client)
    d = client.get(f"/api/v1/workspaces/{wid}/settings", headers=H).json()
    assert set(prj.STATE_KEYS) <= set(d)
    for k, v in DEFAULTS.items():
        assert d[k] == v, k


def test_patch_returns_same_shape_and_prefix_key(client):
    wid = _new_ws(client)
    u = f"/api/v1/workspaces/{wid}/settings"
    before = client.get(u, headers=H).json()
    r = client.patch(u, json={"mv_hi": 80, "fx|dummy": True}, headers=H)
    assert r.status_code == 200, r.text
    d = r.json()
    assert set(d) == set(before) | {"fx|dummy"}
    assert d["mv_hi"] == 80 and d["fx|dummy"] is True
    assert client.get(u, headers=H).json() == d
    assert client.patch(u, json={"ctype": "XX"}, headers=H).status_code == 422


def test_invalid_enum_in_store_does_not_break_get(client):
    from pidtools.api.data import settings_out
    from pidtools.app.workspace import Workspace
    ws = Workspace()
    ws.settings["ctype"] = "XYZ"                  # poškozený projekt: výčet mimo povolené hodnoty
    assert settings_out(ws).ctype == DEFAULTS["ctype"]
