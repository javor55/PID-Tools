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
    assert client.get("/i18n/en").status_code == 401
    assert client.get("/i18n/en", headers={"Authorization": "Bearer wrong"}).status_code == 401
    r = client.get("/i18n/cs", headers={"X-PID-Token": TOKEN})
    assert r.status_code == 200 and r.json()["set_1"]
    assert client.get("/i18n/xx", headers=H).status_code == 404


def test_cors_only_for_app_window(client):
    ok = client.get("/health", headers={"Origin": "http://tauri.localhost"})
    assert ok.headers.get("access-control-allow-origin") == "http://tauri.localhost"
    bad = client.get("/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in bad.headers


def test_workspace_lifecycle(client):
    r = client.post("/workspaces", headers=H)
    assert r.status_code == 200
    w = r.json()
    assert w["has_data"] is False and w["id"]
    assert client.get(f"/workspaces/{w['id']}", headers=H).json()["id"] == w["id"]
    assert client.delete(f"/workspaces/{w['id']}", headers=H).status_code == 204
    assert client.get(f"/workspaces/{w['id']}", headers=H).status_code == 404


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
    with client.stream("GET", f"/jobs/{jid}/events", headers=H) as r:
        assert r.headers["content-type"].startswith("text/event-stream")
        events = [json.loads(line[6:]) for line in r.iter_lines() if line.startswith("data: ")]
    assert events[-1]["state"] == "done" and events[-1]["progress"] == 1.0
    assert any(0 < e["progress"] < 1 for e in events)
    assert client.get(f"/jobs/{jid}", headers=H).json()["state"] == "done"
    jid2 = jobs.submit(f.slow, 1000, 0.05)
    time.sleep(0.5)
    r = client.post(f"/jobs/{jid2}/cancel", headers=H)
    assert r.json()["state"] == "cancelled"
    assert client.get("/jobs/nope", headers=H).status_code == 404


def test_openapi_file_is_current():
    """openapi.json v repozitáři odpovídá kódu (po změně API: python -m pidtools.api --openapi pidtools/api/openapi.json)."""
    from pidtools.api.__main__ import openapi_json
    with open(os.path.join(ROOT, "pidtools", "api", "openapi.json"), encoding="utf-8") as fh:
        assert fh.read() == openapi_json()


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
        req = urllib.request.Request(url + "/i18n/en", headers={"X-PID-Token": token})
        assert json.loads(urllib.request.urlopen(req, timeout=5).read())["set_1"]
        with pytest.raises(urllib.error.HTTPError):
            urllib.request.urlopen(url + "/i18n/en", timeout=5)
    finally:
        p.terminate()
        p.wait(10)
