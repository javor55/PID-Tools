"""Veřejný režim webu (PIDTOOLS_AUTH=public): anonymní relace v cookie, izolace, limity, vypnuté funkce, nic na disk."""
import os
import time

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from pidtools.api import create_app  # noqa: E402
from pidtools.api.deploy import DeployConfig  # noqa: E402
from pidtools.api.public import COOKIE, RateLimiter, SessionLimitError, Sessions, client_ip  # noqa: E402

V1 = "/api/v1"
CSV = b"t,y,u\n" + b"".join(f"{i},{i % 7},{i % 3}\n".encode() for i in range(200))


def cfg(**kw):
    kw.setdefault("cookie_secure", False)             # TestClient jede přes http: cookie Secure by se neposlala
    return DeployConfig(auth="public", **kw)


def pair(**kw):
    """Aplikace a dva různé „prohlížeče“ (každý má vlastní cookie)."""
    app = create_app(team=cfg(**kw))
    return app, TestClient(app), TestClient(app)


def mk(c, demo=False):
    wid = c.post(f"{V1}/workspaces").json()["id"]
    if demo:
        assert c.post(f"{V1}/workspaces/{wid}/data/demo").status_code == 200
    return wid


# ---- konfigurace
def test_env_defaults_and_validation():
    c = DeployConfig.from_env({"PIDTOOLS_AUTH": "public"})
    assert c.public and c.team and c.mode == "public" and c.cookie_secure and not c.trust_cf_ip
    assert c.max_upload_mb == 20 and c.max_workspaces_user == 3 and c.max_jobs_user == 2 and c.max_jobs >= 1
    assert c.session_ttl == 7200 and c.max_sessions == 200 and c.rate_limit > 0 and c.rate_upload > 0
    c = DeployConfig.from_env({"PIDTOOLS_AUTH": "public", "PIDTOOLS_COOKIE_SECURE": "0", "PIDTOOLS_TRUST_CF_IP": "1",
                               "PIDTOOLS_SESSION_TTL": "60", "PIDTOOLS_MAX_SESSIONS": "5", "PIDTOOLS_MAX_QUEUE": "1",
                               "PIDTOOLS_RATE_LIMIT": "30", "PIDTOOLS_RATE_UPLOAD": "3", "PIDTOOLS_MAX_UPLOAD_MB": "2"})
    assert (c.cookie_secure, c.trust_cf_ip, c.session_ttl, c.max_sessions, c.max_queue, c.rate_limit, c.rate_upload,
            c.max_upload_mb) == (False, True, 60, 5, 1, 30, 3, 2)
    with pytest.raises(ValueError, match="positive"):
        DeployConfig.from_env({"PIDTOOLS_AUTH": "public", "PIDTOOLS_MAX_SESSIONS": "0"})


def test_client_ip_source():
    scope = {"headers": [(b"cf-connecting-ip", b"203.0.113.7")], "client": ("10.0.0.2", 5000)}
    assert client_ip(scope, False) == "10.0.0.2"                    # bez souhlasu se hlavička ignoruje
    assert client_ip(scope, True) == "203.0.113.7"
    bad = {"headers": [(b"cf-connecting-ip", b"x; DROP")], "client": ("10.0.0.2", 1)}
    assert client_ip(bad, True) == "10.0.0.2"


def test_rate_limiter_unit():
    t = [0.0]
    rl = RateLimiter(60, burst=2, clock=lambda: t[0])
    assert rl.allow("a") and rl.allow("a") and not rl.allow("a") and rl.allow("b")
    t[0] += 1.0                                                      # 1 token za sekundu
    assert rl.allow("a") and not rl.allow("a")


def test_sessions_unit():
    t, gone = [100.0], []
    s = Sessions(ttl_s=10, max_count=2, on_expire=gone.append, clock=lambda: t[0])
    a, b = s.create(), s.create()
    assert a != b and len(a) >= 43                                   # 256 bitů
    with pytest.raises(SessionLimitError):
        s.create()
    t[0] += 11
    assert not s.touch(a) and sorted(gone) == sorted([a, b])
    assert len(s) == 0 and s.create()


# ---- relace
def test_cookie_flags_and_reuse():
    app = create_app(team=cfg(cookie_secure=True))
    with TestClient(app, base_url="https://testserver") as c:
        r = c.get(f"{V1}/config")
        ck = r.headers["set-cookie"]
        assert r.json()["mode"] == "public"
        assert all(f in ck for f in ("HttpOnly", "Secure", "SameSite=Strict", "Path=/")) and ck.startswith(COOKIE + "=")
        sid = c.cookies.get(COOKIE)
        assert len(sid) >= 43
        assert "set-cookie" not in c.get(f"{V1}/config").headers      # platná relace se nevydává znovu
        assert c.cookies.get(COOKIE) == sid
        assert "max-age=31536000" in c.get(f"{V1}/config").headers["strict-transport-security"]
    app2 = create_app(team=cfg(cookie_secure=False))
    with TestClient(app2) as c:
        assert "Secure" not in c.get(f"{V1}/config").headers["set-cookie"]


def test_forged_session_id_is_replaced():
    app = create_app(team=cfg())
    with TestClient(app) as c:
        forged = "A" * 43
        r = c.get(f"{V1}/config", headers={"Cookie": f"{COOKIE}={forged}"})
        assert COOKIE + "=" in r.headers["set-cookie"] and forged not in r.headers["set-cookie"]
        assert c.get(f"{V1}/config", headers={"Cookie": f"{COOKIE}=short"}).headers.get("set-cookie")


def test_isolation_of_workspaces_and_jobs():
    app, a, b = pair()
    with a, b:
        wa = mk(a, demo=True)
        wb = mk(b)
        assert a.get(f"{V1}/workspaces/{wa}").status_code == 200
        for r in (b.get(f"{V1}/workspaces/{wa}"), b.delete(f"{V1}/workspaces/{wa}"),
                  b.post(f"{V1}/workspaces/{wa}/data/demo"), b.get(f"{V1}/workspaces/{wa}/project")):
            assert r.status_code == 404
        assert a.get(f"{V1}/workspaces/{wb}").status_code == 404
        jid = a.post(f"{V1}/workspaces/{wa}/identify").json()["id"]
        assert b.get(f"{V1}/jobs/{jid}").status_code == 404
        assert b.post(f"{V1}/jobs/{jid}/cancel").status_code == 404
        assert b.get(f"{V1}/jobs/{jid}/result").status_code == 404
        assert a.get(f"{V1}/jobs/{jid}").status_code == 200
        a.post(f"{V1}/jobs/{jid}/cancel")
        # nastavení aplikace po relacích (v paměti)
        s = a.get(f"{V1}/app-settings").json()
        s["report"]["company"] = "ACME"
        assert a.put(f"{V1}/app-settings", json=s).json()["report"]["company"] == "ACME"
        assert a.get(f"{V1}/app-settings").json()["report"]["company"] == "ACME"
        assert b.get(f"{V1}/app-settings").json()["report"]["company"] == ""


def test_session_expiry_frees_everything():
    app = create_app(team=cfg(session_ttl=2.0))
    with TestClient(app) as c:
        wid = mk(c, demo=True)
        sid = c.cookies.get(COOKIE)
        c.put(f"{V1}/app-settings", json={**c.get(f"{V1}/app-settings").json(), "journal": {"author": "me", "require_note": False}})
        jid = c.post(f"{V1}/workspaces/{wid}/identify").json()["id"]
        assert app.state.store.count(sid) == 1
        time.sleep(3.0)
        r = c.get(f"{V1}/workspaces/{wid}")                         # vypršelá relace: dostane novou, prostor je pryč
        assert r.status_code == 404 and c.cookies.get(COOKIE) != sid
        assert app.state.store.count(sid) == 0
        assert app.state.jobs.status(jid)["state"] == "cancelled"
        assert sid not in app.state.sessions._d
        assert c.get(f"{V1}/app-settings").json()["journal"]["author"] == ""


def test_unprefixed_alias_needs_session_too():
    app = create_app(team=cfg())
    with TestClient(app) as c:
        assert c.post("/workspaces").status_code == 200              # alias také dostane relaci
        assert COOKIE in c.cookies


def test_cross_origin_writes_rejected():
    app = create_app(team=cfg())
    with TestClient(app) as c:
        c.get(f"{V1}/config")
        assert c.post(f"{V1}/workspaces", headers={"Origin": "https://evil.example"}).status_code == 403
        assert c.post(f"{V1}/workspaces", headers={"Origin": "null"}).status_code == 403
        assert c.post(f"{V1}/workspaces", headers={"Origin": "http://testserver"}).status_code == 200
        assert c.get(f"{V1}/workspaces/x", headers={"Origin": "https://evil.example"}).status_code == 404   # čtení nic nemění


# ---- limity
def test_limit_workspaces_per_session():
    app, a, b = pair(max_workspaces_user=2)
    with a, b:
        ids = [mk(a) for _ in range(3)]
        assert a.get(f"{V1}/workspaces/{ids[0]}").status_code == 404      # nejstarší se uvolnil
        assert a.get(f"{V1}/workspaces/{ids[2]}").status_code == 200
        assert mk(b)


def test_limit_jobs_per_session_and_global_cap():
    app, a, b = pair(max_jobs=1, max_queue=0, max_jobs_user=1)
    with a, b:
        wa, wb = mk(a, True), mk(b, True)
        first = a.post(f"{V1}/workspaces/{wa}/identify")
        assert first.status_code == 200
        assert a.post(f"{V1}/workspaces/{wa}/identify").status_code == 429        # limit na relaci
        busy = b.post(f"{V1}/workspaces/{wb}/identify")
        assert busy.status_code == 503 and busy.headers["retry-after"]            # celkový strop serveru
        a.post(f"{V1}/jobs/{first.json()['id']}/cancel")
        assert b.post(f"{V1}/workspaces/{wb}/identify").status_code == 200


def test_job_submit_rate_limit():
    app = create_app(team=cfg(rate_upload=2, max_jobs=4, max_jobs_user=4, max_queue=8))
    with TestClient(app) as c:
        w = mk(c, True)
        codes = []
        for _ in range(4):
            r = c.post(f"{V1}/workspaces/{w}/identify")
            codes.append(r.status_code)
            if r.status_code == 200:
                c.post(f"{V1}/jobs/{r.json()['id']}/cancel")
        assert codes[0] == 200 and 429 in codes


def test_limit_total_sessions():
    app = create_app(team=cfg(max_sessions=2))
    with TestClient(app) as a, TestClient(app) as b, TestClient(app) as c:
        assert a.get(f"{V1}/config").status_code == 200 and b.get(f"{V1}/config").status_code == 200
        r = c.get(f"{V1}/config")
        assert r.status_code == 503 and "set-cookie" not in r.headers
        assert a.get(f"{V1}/config").status_code == 200                # existující relace dál funguje
        assert c.get(f"{V1}/health").status_code == 200                # zdraví bez relace


def test_rate_limit_per_ip_and_trust_header():
    app = create_app(team=cfg(rate_limit=12))                          # rázem 2 požadavky, pak 1 za 5 s
    with TestClient(app) as c:
        codes = [c.get(f"{V1}/config").status_code for _ in range(4)]
        assert codes[:2] == [200, 200] and 429 in codes
        assert c.get(f"{V1}/health").status_code == 200                # health se nelimituje (kontrola kontejneru)
        r = c.get(f"{V1}/config")
        assert r.status_code == 429 and r.headers["retry-after"]
        # bez PIDTOOLS_TRUST_CF_IP se hlavička ignoruje (nešlo by obejít limit podvrhem)
        assert c.get(f"{V1}/config", headers={"CF-Connecting-IP": "1.2.3.4"}).status_code == 429
    app = create_app(team=cfg(rate_limit=12, trust_cf_ip=True))
    with TestClient(app) as c:
        for _ in range(4):
            c.get(f"{V1}/config", headers={"CF-Connecting-IP": "1.2.3.4"})
        assert c.get(f"{V1}/config", headers={"CF-Connecting-IP": "1.2.3.4"}).status_code == 429
        assert c.get(f"{V1}/config", headers={"CF-Connecting-IP": "5.6.7.8"}).status_code == 200


def test_upload_size_and_rate_limits():
    app = create_app(team=cfg(max_upload_mb=1, rate_upload=2))
    with TestClient(app) as c:
        w = mk(c)
        big = b"t,y\n" + b"1,2\n" * 300_000                              # > 1 MB
        r = c.post(f"{V1}/workspaces/{w}/data/file", params={"name": "x.csv"}, content=big)
        assert r.status_code == 413
        mid = b"t,y\n" + b"1,2\n" * 70_000                               # ≈ 280 kB: projde, ale počítá se do přísného limitu
        codes = [c.post(f"{V1}/workspaces/{w}/data/file", params={"name": "x.csv"}, content=mid).status_code
                 for _ in range(3)]
        assert 429 in codes and codes[0] != 413
        assert c.put(f"{V1}/workspaces/{w}/project", content=big).status_code == 413      # i projekt má strop upload


def test_chunked_body_without_length_rejected():
    app = create_app(team=cfg())
    with TestClient(app) as c:
        w = mk(c)

        def gen():
            yield b"t,y\n1,2\n"
        r = c.post(f"{V1}/workspaces/{w}/data/file", params={"name": "x.csv"}, content=gen())
        assert r.status_code == 411


# ---- vypnuté funkce
def test_disabled_endpoints():
    app = create_app(team=cfg())
    with TestClient(app) as c:
        w = mk(c, True)
        assert c.get(f"{V1}/opc/available").json() is False
        srv = {"url": "opc.tcp://127.0.0.1:4840"}
        assert c.post(f"{V1}/opc/browse", json=srv).status_code == 403
        assert c.post(f"{V1}/opc/find", json={**srv, "text": "x"}).status_code == 403
        assert c.post(f"{V1}/workspaces/{w}/opc/history", json={
            **srv, "nodes": {"ns=1;i=1": "T"}, "start": "2024-01-01T00:00:00", "end": "2024-01-02T00:00:00"}).status_code == 403
        assert c.post(f"{V1}/app-settings/logo", params={"name": "l.png"}, content=b"\x89PNG").status_code == 403
        assert c.get(f"{V1}/app-settings/logo").status_code == 404
        assert c.post(f"{V1}/workspaces/{w}/autosave").status_code == 403
        assert c.get(f"{V1}/autosave/latest").json()["available"] is False
        assert c.get(f"{V1}/recent").json() == []
        assert c.post(f"{V1}/controllers", json={"from_id": "pcs7_pidconl", "name": "x"}).status_code == 403          # knihovna jen ke čtení
        assert c.get(f"{V1}/controllers").status_code == 200
        assert c.get("/openapi.json").status_code == 404 and c.get("/docs").status_code == 404
        # připojení k OPC / historianům se nikdy neuloží
        s = c.get(f"{V1}/app-settings").json()
        s["connections"]["opc"] = [{"name": "x", "url": "opc.tcp://10.0.0.1:4840"}]
        s["connections"]["historians"]["pi"] = "https://pi.example"
        out = c.put(f"{V1}/app-settings", json=s).json()
        assert out["connections"]["opc"] == [] and out["connections"]["historians"]["pi"] == ""


def test_journal_attachments_disabled():
    app = create_app(team=cfg())
    with TestClient(app) as c:
        w = mk(c, True)
        r = c.post(f"{V1}/workspaces/{w}/journal/s1/attachments", json={"name": "a.txt", "data_b64": "AAAA"})
        assert r.status_code == 403


# ---- bezpečnostní hlavičky
def test_security_headers_everywhere():
    app = create_app(team=cfg())
    with TestClient(app) as c:
        for path in (f"{V1}/health", f"{V1}/config", "/", "/nonexistent"):
            h = c.get(path).headers
            assert "default-src 'self'" in h["content-security-policy"] and "frame-ancestors 'none'" in h["content-security-policy"]
            assert "script-src 'self'" in h["content-security-policy"] and "base-uri 'none'" in h["content-security-policy"]
            assert h["x-content-type-options"] == "nosniff" and h["referrer-policy"] == "no-referrer"
            assert h["x-frame-options"] == "DENY" and h["cross-origin-opener-policy"] == "same-origin"
            assert "camera=()" in h["permissions-policy"]
        assert c.get(f"{V1}/config").headers["cache-control"] == "no-store"


def test_no_stack_traces_or_paths(tmp_path):
    app = create_app(team=cfg())
    with TestClient(app, raise_server_exceptions=False) as c:
        w = mk(c)
        r = c.post(f"{V1}/workspaces/{w}/data/file", params={"name": "bad.xlsx"}, content=b"PK\x03\x04 not a workbook")
        assert r.status_code == 400 and r.json()["detail"] == "data_bad_xlsx"
        r = c.put(f"{V1}/workspaces/{w}/project", content=b"[" * 200_000)       # přehnaně hluboký JSON
        assert r.status_code == 400 and "Traceback" not in r.text and "/" not in r.json()["detail"].replace("invalid project: ", "")
        r = c.put(f"{V1}/workspaces/{w}/project", content=b"{not json")
        assert r.status_code == 400 and "Traceback" not in r.text and ".py" not in r.text


# ---- nic na disk
def test_nothing_written_to_disk(tmp_path, monkeypatch):
    """Typické postupy ve veřejném režimu nezapíšou nic do složek nastavení, dat ani knihovny regulátorů."""
    cfgd, datad, ctld = tmp_path / "cfg", tmp_path / "data", tmp_path / "ctl"
    home = tmp_path / "home"
    home.mkdir()
    work = tmp_path / "cwd"
    work.mkdir()
    for k, v in (("PIDTOOLS_CONFIG_DIR", cfgd), ("PIDTOOLS_DATA_DIR", datad), ("PIDTOOLS_CONTROLLERS_DIR", ctld),
                 ("XDG_CONFIG_HOME", home / ".config"), ("XDG_DATA_HOME", home / ".local")):
        monkeypatch.setenv(k, str(v))
    monkeypatch.chdir(work)
    app = create_app(team=cfg())
    with TestClient(app) as c:
        w = mk(c, True)
        c.post(f"{V1}/workspaces/{w}/data/file", params={"name": "x.csv"}, content=CSV)
        s = c.get(f"{V1}/app-settings").json()
        s["charts"]["height"] = 300
        c.put(f"{V1}/app-settings", json=s)
        c.post(f"{V1}/app-settings/import", content=c.get(f"{V1}/app-settings/export").content)
        c.delete(f"{V1}/app-settings")
        c.post(f"{V1}/app-settings/logo", params={"name": "l.png"}, content=b"\x89PNG")
        c.post(f"{V1}/workspaces/{w}/autosave")
        raw = c.get(f"{V1}/workspaces/{w}/project").content                   # uložení projektu = jen stažení
        assert c.put(f"{V1}/workspaces/{w}/project", content=raw).status_code == 200
        c.get(f"{V1}/recent")
        c.get(f"{V1}/autosave/latest")
        c.post(f"{V1}/controllers", json={"from_id": "pcs7_pidconl", "name": "x"})
        jid = c.post(f"{V1}/workspaces/{w}/identify").json()["id"]
        c.post(f"{V1}/jobs/{jid}/cancel")
        c.delete(f"{V1}/workspaces/{w}")
    for d in (cfgd, datad, ctld, home / ".config", home / ".local"):
        assert not d.exists(), f"{d} byla vytvořena"
    assert list(work.iterdir()) == [] and list(home.iterdir()) == []
    assert not os.path.exists(cfgd)
