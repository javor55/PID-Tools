"""
TICKET-003 v prohlížeči: neplatná hodnota nastavení (PATCH /settings → 422) ukáže toast s klíčem, server ji nezměnil
a v konzoli stránky není nezachycená chyba. Od TICKET-015 zachytí `0` v poli `samp` už místní kontrola (bez PATCH),
proto se odpověď 422 vyvolá přes `page.route`; text chyby je u pole a Esc vrátí původní hodnotu.
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


def _call(server, page, method, path, body=None):
    wid = page.evaluate("sessionStorage.getItem('pid.wid')")
    req = urllib.request.Request(server + path.format(wid=wid), method=method,
                                 data=None if body is None else json.dumps(body).encode(),
                                 headers={"X-PID-Token": TOKEN, "Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=120).read() or b"null")


def test_invalid_setting_shows_toast_and_reverts(page, server):
    page.locator('[data-tab="data"]').click()
    page.locator('[data-sub="sources"]').click()
    page.locator('[data-testid="src-demo"]').click()
    page.wait_for_function("() => (document.querySelector('[data-testid=\"data-info\"]')||{}).innerText?.includes('demo')")
    _call(server, page, "PATCH", B + "/settings", {"chosen": ["P1D", "I1D"]})
    j = _call(server, page, "POST", B + "/identify", {})
    end = time.time() + 120
    while time.time() < end and _call(server, page, "GET", f"/api/v1/jobs/{j['id']}")["state"] in ("queued", "running"):
        time.sleep(0.2)
    page.reload(wait_until="networkidle")
    page.wait_for_selector('[data-testid="api-ok"]', timeout=20000)
    page.locator('[data-tab="tuning"]').click()
    page.wait_for_selector('[data-testid="sets"] tbody tr', timeout=30000)
    page.locator('[data-testid="card-block"] > summary').click()
    fld = page.locator('[data-testid="set-samp"]')
    before = fld.input_value()
    orig = _call(server, page, "GET", B + "/settings")["samp"]
    page.errors.clear()
    sent = []

    def _reject(route):                                      # server odmítne hodnotu, kterou místní kontrola pustí
        sent.append(route.request.post_data)
        route.fulfill(status=422, content_type="application/json", body=json.dumps({"detail": "samp: must be > 0"}))

    page.route("**/api/v1/workspaces/*/settings", lambda r: _reject(r) if r.request.method == "PATCH" else r.continue_())
    fld.fill("5")
    fld.press("Enter")
    toast = page.locator('[data-testid="toast-err"]')
    toast.first.wait_for(timeout=10000)
    assert "samp" in toast.first.inner_text()
    assert page.locator('[data-testid="toasts"]').get_attribute("role") == "status"
    assert len(sent) == 1
    err = page.locator('[data-testid="set-samp-err"]')
    err.wait_for(timeout=10000)
    assert "samp: must be > 0" in err.inner_text()
    assert fld.get_attribute("aria-invalid") == "true"
    assert fld.input_value() == "5"                          # text zůstane v poli, ať jde opravit
    fld.press("Escape")                                      # Esc vrátí původní hodnotu a smaže chybu
    page.wait_for_function("(v) => document.querySelector('[data-testid=\"set-samp\"]').value === v", arg=before, timeout=10000)
    assert err.count() == 0
    page.unroute("**/api/v1/workspaces/*/settings")
    assert _call(server, page, "GET", B + "/settings")["samp"] == orig
    assert toast.count() == 1                                # stejný text se neopakuje (toast z PATCH i z unhandledrejection)
    page.locator('[data-testid="toast-close"]').first.click()
    assert toast.count() == 0
    assert not [e for e in page.errors if "nhandled" in e], page.errors
