"""
TICKET-015 v prohlížeči: číselné pole nastavení (Ladění › blok) při neplatné hodnotě nechá text v poli, nastaví
`aria-invalid`, ukáže důvod a neodešle PATCH; platná hodnota se uloží a chyba zmizí.
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


def test_numeric_field_shows_error_and_sends_nothing(page, server):
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
    err = page.locator('[data-testid="set-samp-err"]')
    orig = _call(server, page, "GET", B + "/settings")["samp"]
    patches = []
    page.on("request", lambda r: patches.append(r.url) if r.method == "PATCH" and "/settings" in r.url else None)

    fld.fill("0")                                            # samp musí být > 0: zachytí místní kontrola
    fld.press("Enter")
    err.wait_for(timeout=10000)
    assert fld.get_attribute("aria-invalid") == "true"
    assert err.is_visible() and err.inner_text().strip()
    assert fld.get_attribute("aria-describedby") == err.get_attribute("id")
    assert fld.input_value() == "0"                          # text zůstane v poli
    page.wait_for_timeout(500)
    assert patches == []                                     # žádný PATCH
    assert page.locator('[data-testid="toast-err"]').count() == 0
    assert _call(server, page, "GET", B + "/settings")["samp"] == orig

    fld.fill("2")
    fld.press("Enter")
    page.wait_for_function("() => !document.querySelector('[data-testid=\"set-samp-err\"]')", timeout=10000)
    assert fld.get_attribute("aria-invalid") is None
    end = time.time() + 10
    while time.time() < end and _call(server, page, "GET", B + "/settings")["samp"] != 2:
        time.sleep(0.2)
    assert _call(server, page, "GET", B + "/settings")["samp"] == 2
    assert len(patches) == 1
