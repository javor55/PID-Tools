"""
TICKET-006: změna nastavení v Ladění zneplatní jen dotčené dotazy. Sonda: přepnutí „Robustness Ms“ (opt_ms) vyvolá
nejvýš 9 požadavků na API a žádný na nesouvisející části (zdroje, třídění, mapování); graf se přesto přepočítá.
Potřebuje sestavené UI (cd frontend && npm run build).
"""
import json
import time
import urllib.request

import pytest

pytest.importorskip("playwright.sync_api")
import test_frontend as _tf  # noqa: E402

TOKEN = _tf.TOKEN
server, page = _tf.server, _tf.page                      # fixtury serveru a prohlížeče
B = "/api/v1/workspaces/{wid}"
MAX_REQ = 9
FORBIDDEN = ("/sources", "/triage", "/loops/mappings")


def _call(server, page, method, path, body=None):
    wid = page.evaluate("sessionStorage.getItem('pid.wid')")
    req = urllib.request.Request(server + path.format(wid=wid), method=method,
                                 data=None if body is None else json.dumps(body).encode(),
                                 headers={"X-PID-Token": TOKEN, "Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=120).read() or b"null")


def _until(fn, timeout=30.0):
    end = time.time() + timeout
    while time.time() < end:
        v = fn()
        if v:
            return v
        time.sleep(0.2)
    raise AssertionError("timeout")


def test_opt_ms_cilene_zneplatneni(page, server):
    page.locator('[data-tab="data"]').click()
    page.locator('[data-sub="sources"]').click()
    page.locator('[data-testid="src-demo"]').click()
    page.wait_for_function("() => (document.querySelector('[data-testid=\"data-info\"]')||{}).innerText?.includes('demo')")
    _call(server, page, "PATCH", B + "/settings", {"chosen": ["P1D", "I1D"]})
    j = _call(server, page, "POST", B + "/identify", {})
    _until(lambda: _call(server, page, "GET", f"/api/v1/jobs/{j['id']}")["state"] not in ("queued", "running"), 120)
    page.reload(wait_until="networkidle")
    page.wait_for_selector('[data-testid="api-ok"]', timeout=20000)
    page.locator('[data-tab="tuning"]').click()
    page.wait_for_selector('[data-testid="response"] svg path', timeout=30000, state="attached")

    # klid: 2 s bez požadavků
    last = [time.time()]
    page.on("request", lambda r: last.__setitem__(0, time.time()) if "/api/v1/" in r.url else None)
    _until(lambda: time.time() - last[0] > 2.0, 60)

    reqs = []

    def _rec(r):
        u = r.url
        if "/api/v1/" in u and "save-state" not in u and "/health" not in u:
            reqs.append((r.method, u.split("/api/v1/", 1)[1].split("?")[0]))
    page.on("request", _rec)
    btn = page.locator('[data-testid="set-opt_ms"] button[data-value="1.8"]')
    assert btn.get_attribute("aria-pressed") == "false"
    btn.click()
    page.wait_for_timeout(5000)
    page.remove_listener("request", _rec)

    assert _call(server, page, "GET", B + "/settings")["opt_ms"] == 1.8
    assert len(reqs) <= MAX_REQ, reqs
    bad = [r for r in reqs if any(r[1].endswith(f) for f in FORBIDDEN)]
    assert not bad, (bad, reqs)
    assert any(m == "POST" and p.endswith("/simulate") for m, p in reqs), reqs      # graf / ukazatele se přepočítaly
