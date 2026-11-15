"""API (pidtools.api, M6): token, CORS, pracovní prostory, úlohy s průběhem (SSE), popis rozhraní, spuštění."""
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from pidtools.api import create_app  # noqa: E402
from pidtools.api.store import WorkspaceStore  # noqa: E402
from tests import _jobs_fns as f  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOKEN = "t0ken"
H = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture(scope="module")
def client():
    app = create_app(token=TOKEN, cors_origins=["http://tauri.localhost"])
    with TestClient(app) as c:
        yield c


def test_health_without_token(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_token_required(client):
    assert client.get("/api/v1/i18n/en").status_code == 401
    assert client.get("/api/v1/i18n/en", headers={"Authorization": "Bearer wrong"}).status_code == 401
    r = client.get("/api/v1/i18n/cs", headers={"X-PID-Token": TOKEN})
    assert r.status_code == 200 and r.json()["set_1"]
    assert client.get("/api/v1/i18n/xx", headers=H).status_code == 404


def test_cors_only_for_app_window(client):
    ok = client.get("/health", headers={"Origin": "http://tauri.localhost"})
    assert ok.headers.get("access-control-allow-origin") == "http://tauri.localhost"
    bad = client.get("/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in bad.headers


def test_workspace_lifecycle(client):
    r = client.post("/api/v1/workspaces", headers=H)
    assert r.status_code == 200
    w = r.json()
    assert w["has_data"] is False and w["id"]
    assert client.get(f"/api/v1/workspaces/{w['id']}", headers=H).json()["id"] == w["id"]
    assert client.delete(f"/api/v1/workspaces/{w['id']}", headers=H).status_code == 204
    assert client.get(f"/api/v1/workspaces/{w['id']}", headers=H).status_code == 404


def test_store_expiry_and_limit():
    st = WorkspaceStore(ttl_s=0.2, max_count=2)
    a, _ = st.create()
    b, _ = st.create()
    c, _ = st.create()                       # plné úložiště: uvolní nejdéle nepoužitý (a)
    with pytest.raises(KeyError):
        st.get(a)
    st.get(b)
    time.sleep(0.3)
    with pytest.raises(KeyError):
        st.get(c)                            # vypršel po nečinnosti
    assert len(st) == 0


def test_job_status_cancel_and_events(client):
    jobs = client.app.state.jobs
    jid = jobs.submit(f.slow, 10, 0.05)
    with client.stream("GET", f"/api/v1/jobs/{jid}/events", headers=H) as r:
        assert r.headers["content-type"].startswith("text/event-stream")
        events = [json.loads(line[6:]) for line in r.iter_lines() if line.startswith("data: ")]
    assert events[-1]["state"] == "done" and events[-1]["progress"] == 1.0
    assert any(0 < e["progress"] < 1 for e in events)
    assert client.get(f"/api/v1/jobs/{jid}", headers=H).json()["state"] == "done"
    jid2 = jobs.submit(f.slow, 1000, 0.05)
    time.sleep(0.5)
    r = client.post(f"/api/v1/jobs/{jid2}/cancel", headers=H)
    assert r.json()["state"] == "cancelled"
    assert client.get("/api/v1/jobs/nope", headers=H).status_code == 404


def test_openapi_file_is_current():
    """openapi.json v repozitáři odpovídá kódu (po změně API: python -m pidtools.api --openapi pidtools/api/openapi.json)."""
    from pidtools.api.__main__ import openapi_json
    with open(os.path.join(ROOT, "pidtools", "api", "openapi.json"), encoding="utf-8") as fh:
        assert fh.read() == openapi_json()


def test_frontend_types_match_openapi():
    """frontend/src/api/schema.d.ts je z aktuálního openapi.json (po změně API: cd frontend && npm run api-types)."""
    import re
    with open(os.path.join(ROOT, "pidtools", "api", "openapi.json"), encoding="utf-8") as fh:
        spec = json.load(fh)
    with open(os.path.join(ROOT, "frontend", "src", "api", "schema.d.ts"), encoding="utf-8") as fh:
        ts = fh.read()
    paths = set(re.findall(r'^    "(/[^"]*)": \{', ts, flags=re.M))
    assert paths == set(spec["paths"])
    assert all(p.startswith("/api/v1/") for p in paths)                             # v OpenAPI jen stabilní cesty
    body = ts.split("schemas: {", 1)[1].split("responses:", 1)[0]
    assert set(re.findall(r"^        (\w+): \{", body, flags=re.M)) == set(spec["components"]["schemas"])


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_cli_server_localhost_with_token():
    port = _free_port()
    p = subprocess.Popen([sys.executable, "-m", "pidtools.api", "--port", str(port)], cwd=ROOT,
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    try:
        token = p.stdout.readline().split()[-1]              # bez --token se vygeneruje a vypíše
        url = f"http://127.0.0.1:{port}"
        for _ in range(100):
            try:
                urllib.request.urlopen(url + "/health", timeout=1)
                break
            except Exception:
                time.sleep(0.1)
        req = urllib.request.Request(url + "/api/v1/i18n/en", headers={"X-PID-Token": token})
        assert json.loads(urllib.request.urlopen(req, timeout=5).read())["set_1"]
        with pytest.raises(urllib.error.HTTPError):
            urllib.request.urlopen(url + "/api/v1/i18n/en", timeout=5)
    finally:
        p.terminate()
        p.wait(10)


def test_workspace_locks_are_released():
    """Zámky serializace požadavků nezůstávají po smazaných ani neznámých prostorech (TICKET-012)."""
    from pidtools.api import create_app
    app = create_app()
    with TestClient(app) as c:
        ids = [c.post("/api/v1/workspaces").json()["id"] for _ in range(20)]
        live = ids.pop()
        for w in ids:
            assert c.get(f"/api/v1/workspaces/{w}/settings").status_code == 200
            assert c.delete(f"/api/v1/workspaces/{w}").status_code == 204
            assert c.get(f"/api/v1/workspaces/{w}/settings").status_code == 404
        for i in range(30):
            assert c.get(f"/api/v1/workspaces/unknown{i}/settings").status_code == 404
        assert c.get(f"/api/v1/workspaces/{live}/settings").status_code == 200
        keys = {k for d in app.state.ws_locks.values() for k in d}
        assert keys <= {live}


@pytest.fixture(scope="module")
def ident_ws():
    """Prostor s ukázkovými daty a identifikací (jako test_api_tuning)."""
    with TestClient(create_app()) as c:
        wid = c.post("/api/v1/workspaces").json()["id"]
        base = f"/api/v1/workspaces/{wid}"
        assert c.post(f"{base}/data/demo").status_code == 200
        assert c.patch(f"{base}/settings", json={"chosen": ["P1D", "I1D"]}).status_code == 200
        job = c.post(f"{base}/identify").json()
        t0 = time.time()
        while time.time() - t0 < 600:
            st = c.get(f"/api/v1/jobs/{job['id']}").json()
            if st["state"] not in ("queued", "running"):
                assert st["state"] == "done", st
                break
            time.sleep(0.2)
        else:
            raise AssertionError("job timeout")
        yield c, base


@pytest.mark.parametrize("raw", [
    '{"samp": "abc"}', '{"set2_gain": null}', '{"samp": 0}', '{"samp": -1}', '{"pv_lo": 50, "pv_hi": 50}',
    '{"mv_lo": 100, "mv_hi": 0}', '{"chosen": "x"}', '{"ctype": [1]}', '{"set2_gain": NaN}',
    '{"opt_ms": 5}', '{"dfb": "yes"}', '{"gain_sign": "up"}', '{"set1_ti": -1}'])
def test_patch_settings_rejects_bad_values(ident_ws, raw):
    """Špatná hodnota nastavení = 422 a stav se nezmění; výpočty dál vracejí 200 (TICKET-001)."""
    c, base = ident_ws
    before = c.get(f"{base}/settings").json()
    r = c.patch(f"{base}/settings", content=raw, headers={"Content-Type": "application/json"})
    assert r.status_code == 422, r.text
    assert ":" in r.json()["detail"]
    assert c.get(f"{base}/settings").json() == before
    assert c.get(f"{base}/tuning").status_code == 200
    assert c.post(f"{base}/simulate", json={}).status_code == 200


def test_patch_settings_accepts_valid_values(ident_ws):
    c, base = ident_ws
    ok = {"set2_gain": 2.0, "thmax": None, "ctype": "PID", "dfb": False, "chosen": ["I1D"], "pv_lo": 0, "pv_hi": 10}
    r = c.patch(f"{base}/settings", json=ok)
    assert r.status_code == 200, r.text
    assert c.patch(f"{base}/settings", json={"ctype": "PI", "dfb": True, "chosen": ["P1D", "I1D"],
                                            "pv_hi": 100}).status_code == 200


def test_upload_empty_file_is_400(client):
    wid = client.post("/api/v1/workspaces", headers=H).json()["id"]
    for body in (b"", b"\n  \n"):
        r = client.post(f"/api/v1/workspaces/{wid}/data/file?name=x.csv", content=body, headers=H)
        assert r.status_code == 400, r.text
        assert r.json()["detail"]
