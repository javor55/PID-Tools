"""Týmový web (M26): ověření JWT z Cloudflare Access s lokálním klíčem a falešným JWKS (bez sítě), uživatelé, limity, logy."""
import logging
import time

import pytest

pytest.importorskip("fastapi")
jwt = pytest.importorskip("jwt")
from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from pidtools.api import create_app  # noqa: E402
from pidtools.api.deploy import CF_HEADER, CloudflareVerifier, DeployConfig, app_from_env  # noqa: E402
from pidtools.api.store import LimitError, WorkspaceStore  # noqa: E402

TEAM, AUD = "acme", "aud-tag-123"
ISS = "https://acme.cloudflareaccess.com"


def _keypair():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption())
    jwk = jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key(), as_dict=True)
    return pem, jwk


PEM, JWK = _keypair()
PEM_OTHER, JWK_OTHER = _keypair()


class FakeJwks:
    """Falešný JWKS týmu: počítá stažení, jde ho přepnout na rotované klíče nebo na chybu sítě."""

    def __init__(self, *jwks_with_kid):
        self.keys = [dict(j, kid=k, alg="RS256", use="sig") for k, j in jwks_with_kid]
        self.calls, self.fail = 0, False

    def __call__(self, url):
        assert url == f"{ISS}/cdn-cgi/access/certs"
        self.calls += 1
        if self.fail:
            raise OSError("network down")
        return {"keys": self.keys, "public_cert": {}, "public_certs": []}


def make_token(email="alice@acme.com", pem=PEM, kid="k1", aud=AUD, iss=ISS, exp=300, **extra):
    now = int(time.time())
    claims = {"aud": [aud], "iss": iss, "iat": now, "exp": now + exp, "email": email, "type": "app", **extra}
    return jwt.encode(claims, pem, algorithm="RS256", headers={"kid": kid})


def hdr(user="alice@acme.com", **kw):
    return {CF_HEADER: make_token(user, **kw)}


def cf_cfg(**kw):
    return DeployConfig(auth="cloudflare", cf_team=TEAM, cf_aud=AUD, **kw)


@pytest.fixture
def jwks():
    return FakeJwks(("k1", JWK))


def team_client(cfg, jwks=None, **vkw):
    verifier = CloudflareVerifier(TEAM, AUD, fetch=jwks, **vkw) if cfg.auth == "cloudflare" else None
    return TestClient(create_app(team=cfg, verifier=verifier))


# ---- ověření JWT
def test_cloudflare_valid_token_and_cached_keys(jwks):
    with team_client(cf_cfg(), jwks) as c:
        assert c.get("/health").status_code == 200                       # zdraví bez přihlášení
        assert c.post("/workspaces").status_code == 401                  # chybí hlavička
        for _ in range(3):
            assert c.post("/workspaces", headers=hdr()).status_code == 200
    assert jwks.calls == 1                                               # klíče se stáhly jednou


@pytest.mark.parametrize("bad", [
    dict(aud="other-app"), dict(iss="https://evil.cloudflareaccess.com"), dict(exp=-3600),
    dict(pem=PEM_OTHER), dict(kid="nope"),
], ids=["audience", "issuer", "expired", "foreign-signature", "unknown-kid"])
def test_cloudflare_rejects_invalid_token(jwks, bad):
    with team_client(cf_cfg(), jwks, min_refresh=3600) as c:
        assert c.post("/workspaces", headers=hdr(**bad)).status_code == 401
        assert c.get("/workspaces/x", headers=hdr(**bad)).status_code == 401
        assert c.post("/workspaces", headers=hdr()).status_code == 200   # platný dál projde


def test_cloudflare_rejects_garbage_and_wrong_algorithm(jwks):
    with team_client(cf_cfg(), jwks) as c:
        assert c.post("/workspaces", headers={CF_HEADER: "not-a-jwt"}).status_code == 401
        hs = jwt.encode({"aud": [AUD], "iss": ISS, "exp": int(time.time()) + 99, "email": "a@b.cz"}, "s" * 32,
                        algorithm="HS256", headers={"kid": "k1"})
        assert c.post("/workspaces", headers={CF_HEADER: hs}).status_code == 401
        none = jwt.encode({"aud": [AUD], "iss": ISS, "exp": int(time.time()) + 99, "email": "a@b.cz"}, None,
                          algorithm="none", headers={"kid": "k1"})
        assert c.post("/workspaces", headers={CF_HEADER: none}).status_code == 401
        # hlavička uživatele se v režimu cloudflare nebere
        assert c.post("/workspaces", headers={"X-Forwarded-Email": "alice@acme.com"}).status_code == 401


def test_cloudflare_key_rotation_and_outage(jwks):
    with team_client(cf_cfg(), jwks, min_refresh=0) as c:
        assert c.post("/workspaces", headers=hdr()).status_code == 200
        jwks.keys = [dict(JWK_OTHER, kid="k2", alg="RS256", use="sig")]            # Cloudflare rotoval klíč
        assert c.post("/workspaces", headers=hdr(pem=PEM_OTHER, kid="k2")).status_code == 200
        assert jwks.calls == 2
    down = FakeJwks(("k1", JWK))
    down.fail = True
    with team_client(cf_cfg(), down) as c:                                         # klíče nejdou stáhnout
        assert c.post("/workspaces", headers=hdr()).status_code == 503
        assert c.post("/workspaces", headers=hdr()).status_code == 503
    assert down.calls == 1                                                         # výpadek nezahlcuje JWKS


def test_service_token_identity(jwks):
    """Servisní token Cloudflare nemá e-mail: uživatelem je common_name."""
    tok = make_token(email=None, common_name="ci-client.access")
    with team_client(cf_cfg(), jwks) as c:
        assert c.post("/workspaces", headers={CF_HEADER: tok}).status_code == 200


# ---- izolace uživatelů
def test_user_isolation_workspaces_and_jobs(jwks):
    alice, bob = hdr("alice@acme.com"), hdr("bob@acme.com")
    with team_client(cf_cfg(), jwks) as c:
        wid = c.post("/workspaces", headers=alice).json()["id"]
        assert c.post(f"/workspaces/{wid}/data/demo", headers=alice).status_code == 200
        for method, url in [("get", f"/workspaces/{wid}"), ("delete", f"/workspaces/{wid}"),
                            ("post", f"/workspaces/{wid}/data/demo"), ("post", f"/workspaces/{wid}/identify"),
                            ("get", f"/workspaces/{wid}/layout")]:
            assert getattr(c, method)(url, headers=bob).status_code == 404, url
        assert c.get(f"/workspaces/{wid}", headers=alice).json()["has_data"] is True
        jid = c.post(f"/workspaces/{wid}/identify", headers=alice).json()["id"]
        for method, url in [("get", f"/jobs/{jid}"), ("post", f"/jobs/{jid}/cancel"), ("get", f"/jobs/{jid}/result"),
                            ("get", f"/jobs/{jid}/events")]:
            assert getattr(c, method)(url, headers=bob).status_code == 404, url
        assert c.get(f"/jobs/{jid}", headers=alice).status_code == 200
        c.post(f"/jobs/{jid}/cancel", headers=alice)
        assert c.delete(f"/workspaces/{wid}", headers=alice).status_code == 204


def test_store_owner():
    st = WorkspaceStore(3600, 10)
    wid, _ = st.create(owner="a", max_per_owner=1)
    with pytest.raises(LimitError):
        st.create(owner="a", max_per_owner=1)
    st.create(owner="b", max_per_owner=1)
    with pytest.raises(KeyError):
        st.get(wid, owner="b")
    assert st.get(wid, owner="a") is st.get(wid)                     # bez vlastníka (desktop) bez omezení
    assert not st.delete(wid, owner="b") and st.delete(wid, owner="a") and st.count("a") == 0


# ---- limity
def test_limit_workspaces_per_user_and_total(jwks):
    cfg = cf_cfg(max_workspaces_user=2, max_workspaces=3)
    with team_client(cfg, jwks) as c:
        a = [c.post("/workspaces", headers=hdr("a@x.cz")) for _ in range(3)]
        assert [r.status_code for r in a] == [200, 200, 429]
        assert c.post("/workspaces", headers=hdr("b@x.cz")).status_code == 200      # jiný uživatel není dotčen
        assert c.delete(f"/workspaces/{a[0].json()['id']}", headers=hdr("a@x.cz")).status_code == 204
        assert c.post("/workspaces", headers=hdr("a@x.cz")).status_code == 200      # po smazání zase jde
        assert len(c.app.state.store) <= 3                                          # celkový strop drží


def test_limit_jobs_per_user(jwks):
    cfg = cf_cfg(max_jobs_user=1)
    with team_client(cfg, jwks) as c:
        ids = {}
        for u in ("a@x.cz", "b@x.cz"):
            wid = c.post("/workspaces", headers=hdr(u)).json()["id"]
            c.post(f"/workspaces/{wid}/data/demo", headers=hdr(u))
            ids[u] = wid
        first = c.post(f"/workspaces/{ids['a@x.cz']}/identify", headers=hdr("a@x.cz"))
        assert first.status_code == 200
        assert c.post(f"/workspaces/{ids['a@x.cz']}/identify", headers=hdr("a@x.cz")).status_code == 429
        other = c.post(f"/workspaces/{ids['b@x.cz']}/identify", headers=hdr("b@x.cz"))
        assert other.status_code == 200                                             # fronta jiného uživatele
        for u, r in (("a@x.cz", first), ("b@x.cz", other)):
            c.post(f"/jobs/{r.json()['id']}/cancel", headers=hdr(u))
        assert c.post(f"/workspaces/{ids['a@x.cz']}/identify", headers=hdr("a@x.cz")).status_code == 200


def test_upload_limit_configurable(jwks):
    cfg = cf_cfg(max_upload_mb=0.001)                                               # ~1 kB
    with team_client(cfg, jwks) as c:
        wid = c.post("/workspaces", headers=hdr()).json()["id"]
        r = c.post(f"/workspaces/{wid}/data/file", params={"name": "x.csv"}, content=b"t,y\n" * 1000, headers=hdr())
        assert r.status_code == 413
        r = c.post(f"/workspaces/{wid}/data/file", params={"name": "x.csv"}, content=b"t,y\n1,2\n", headers=hdr())
        assert r.status_code != 413


def test_idle_expiry_configurable(jwks):
    with team_client(cf_cfg(ttl=0.2), jwks) as c:
        wid = c.post("/workspaces", headers=hdr()).json()["id"]
        assert c.get(f"/workspaces/{wid}", headers=hdr()).status_code == 200
        time.sleep(0.4)
        assert c.get(f"/workspaces/{wid}", headers=hdr()).status_code == 404


# ---- režim hlavičky od proxy
def test_header_mode_needs_explicit_opt_in():
    with pytest.raises(ValueError, match="TRUST_USER_HEADER"):
        DeployConfig.from_env({"PIDTOOLS_AUTH": "header"})
    cfg = DeployConfig.from_env({"PIDTOOLS_AUTH": "header", "PIDTOOLS_TRUST_USER_HEADER": "1",
                                 "PIDTOOLS_USER_HEADER": "X-Auth-Request-Email"})
    with team_client(cfg) as c:
        assert c.post("/workspaces").status_code == 401
        assert c.post("/workspaces", headers={"X-Forwarded-Email": "a@x.cz"}).status_code == 401     # jiná hlavička
        assert c.post("/workspaces", headers={"X-Auth-Request-Email": "bad user\n"}).status_code == 401
        ha, hb = {"X-Auth-Request-Email": "A@x.cz"}, {"X-Auth-Request-Email": "b@x.cz"}
        wid = c.post("/workspaces", headers=ha).json()["id"]
        assert c.get(f"/workspaces/{wid}", headers={"X-Auth-Request-Email": "a@x.cz"}).status_code == 200   # malá písmena
        assert c.get(f"/workspaces/{wid}", headers=hb).status_code == 404


# ---- nastavení z prostředí, desktop beze změny
def test_config_from_env():
    cfg = DeployConfig.from_env({
        "PIDTOOLS_AUTH": "cloudflare", "PIDTOOLS_CF_TEAM": "acme", "PIDTOOLS_CF_AUD": "x", "PIDTOOLS_WORKSPACE_TTL": "600",
        "PIDTOOLS_MAX_WORKSPACES": "40", "PIDTOOLS_MAX_WORKSPACES_USER": "3", "PIDTOOLS_MAX_JOBS": "4",
        "PIDTOOLS_MAX_JOBS_USER": "1", "PIDTOOLS_MAX_UPLOAD_MB": "25", "PIDTOOLS_LOG_LEVEL": "debug"})
    assert (cfg.ttl, cfg.max_workspaces, cfg.max_workspaces_user, cfg.max_jobs, cfg.max_jobs_user) == (600, 40, 3, 4, 1)
    assert cfg.max_upload == 25 * 2 ** 20 and cfg.log_level == "DEBUG" and cfg.team
    for env, msg in [({"PIDTOOLS_AUTH": "cloudflare"}, "CF_TEAM"), ({"PIDTOOLS_AUTH": "sso"}, "unknown mode"),
                     ({}, "PIDTOOLS_TOKEN"), ({"PIDTOOLS_AUTH": "token", "PIDTOOLS_TOKEN": "t", "PIDTOOLS_MAX_JOBS": "x"},
                                              "invalid number"),
                     ({"PIDTOOLS_TOKEN": "t", "PIDTOOLS_LOG_LEVEL": "loud"}, "LOG_LEVEL")]:
        with pytest.raises(ValueError, match=msg):
            DeployConfig.from_env(env)


def test_desktop_mode_unchanged():
    app = app_from_env({"PIDTOOLS_TOKEN": "t0k"})
    with TestClient(app) as c:
        assert c.post("/workspaces").status_code == 401
        h = {"Authorization": "Bearer t0k"}
        wid = c.post("/workspaces", headers=h).json()["id"]
        assert c.get(f"/workspaces/{wid}", headers={"X-PID-Token": "t0k"}).status_code == 200
        assert c.get(f"/workspaces/{wid}", headers={CF_HEADER: make_token()}).status_code == 401     # JWT nic neznamená
        for _ in range(8):                                                       # žádný limit na uživatele
            assert c.post("/workspaces", headers=h).status_code == 200
    plain = create_app(token="t")
    assert type(plain.state.jobs).__name__ == "JobManager"
    assert not any(m.cls.__name__ == "AccessLog" for m in plain.user_middleware)


# ---- logy
def test_logs_contain_user(jwks, caplog):
    caplog.set_level(logging.DEBUG, logger="pidtools")
    with team_client(cf_cfg(), jwks) as c:
        wid = c.post("/workspaces", headers=hdr("alice@acme.com")).json()["id"]
        c.get(f"/workspaces/{wid}", headers=hdr("bob@acme.com"))
        c.post("/workspaces", headers={CF_HEADER: "junk"})
        c.get("/health")
        c.post(f"/workspaces/{wid}/data/demo", headers=hdr("alice@acme.com"))
        jid = c.post(f"/workspaces/{wid}/identify", headers=hdr("alice@acme.com")).json()["id"]
        c.post(f"/jobs/{jid}/cancel", headers=hdr("alice@acme.com"))
        deadline = time.time() + 20
        while time.time() < deadline and not any("job end" in r.getMessage() for r in caplog.records):
            time.sleep(0.05)
    lines = [r.getMessage() for r in caplog.records]
    assert "user=alice@acme.com method=POST path=/workspaces status=200" in " ".join(lines)
    assert any(ln.startswith("user=bob@acme.com method=GET path=/workspaces/") and "status=404" in ln for ln in lines)
    assert any(ln.startswith("user=- method=POST path=/workspaces status=401") for ln in lines)
    assert any(ln.startswith("user=- method=GET path=/health status=200") for ln in lines)        # jen na úrovni DEBUG
    assert all("ms=" in ln for ln in lines if ln.startswith("user="))
    assert any(f"job submit id={jid} user=alice@acme.com" in ln for ln in lines)
    assert any(f"job start id={jid} user=alice@acme.com" in ln for ln in lines)
    assert any(f"job end id={jid} user=alice@acme.com state=cancelled" in ln for ln in lines)


def test_health_not_logged_at_info(jwks, caplog):
    caplog.set_level(logging.INFO, logger="pidtools")
    with team_client(cf_cfg(), jwks) as c:
        c.get("/health")
    assert not any("/health" in r.getMessage() for r in caplog.records)
