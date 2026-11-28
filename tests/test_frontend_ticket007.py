"""
TICKET-007: viditelný přepočet. Při zpožděné odpovědi /simulate má karta odezvy aria-busy="true" a stavový řádek
text „Recalculating…“; po dokončení obojí zmizí. V klidu (pravidelný dotaz save-state) se text neobjeví.
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


def _until(fn, timeout=30.0):
    end = time.time() + timeout
    while time.time() < end:
        v = fn()
        if v:
            return v
        time.sleep(0.2)
    raise AssertionError("timeout")


@pytest.fixture(scope="module")
def tuning(page, server):
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
    page.wait_for_selector('[data-testid="scen-kind"]', timeout=30000)
    page.wait_for_selector('[data-testid="response"] svg path', timeout=30000, state="attached")
    page.wait_for_timeout(1000)
    return page


def test_delayed_simulate_marks_card_busy(tuning, server):
    pg = tuning
    resp = pg.locator('[data-testid="response"]')

    def slow(route):
        time.sleep(1.5)                                      # synchronní prodleva v obsluze routy
        route.continue_()

    pg.route("**/simulate", slow)
    pg.route("**/simulate/curves", slow)
    try:
        kinds = _call(server, pg, "GET", B + "/scenario")["kinds"]
        cur = pg.locator('[data-testid="scen-kind"]').input_value()
        pg.locator('[data-testid="scen-kind"]').select_option(next(k for k in kinds if k != cur))
        pg.wait_for_selector('[data-testid="response"][aria-busy="true"]', timeout=5000)
        assert "is-busy" in (resp.get_attribute("class") or "")
        pg.wait_for_selector('[data-testid="recalc"]', timeout=5000)
        assert "Recalculating" in pg.locator('[data-testid="recalc"]').inner_text()
    finally:
        pg.unroute("**/simulate", slow)
        pg.unroute("**/simulate/curves", slow)
    pg.wait_for_function("() => document.querySelector('[data-testid=\"response\"]').getAttribute('aria-busy') !== 'true'",
                         timeout=30000)
    pg.wait_for_selector('[data-testid="recalc"]', state="detached", timeout=10000)


def test_idle_never_shows_recalc(tuning):
    pg = tuning
    pg.wait_for_timeout(1500)                                # doznění předchozího přepočtu
    seen = 0
    for _ in range(20):                                      # 5 s, překryje i pravidelný dotaz save-state (5 s)
        seen += pg.locator('[data-testid="recalc"]').count()
        pg.wait_for_timeout(250)
    assert seen == 0
