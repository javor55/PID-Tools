"""
FEATURE-003 v prohlížeči: značky stavu postupu na záložkách a řádek „Další krok“ v kontextu. Data pro záložky a
další krok dodává GET /guide/status; test porovnává zobrazení s odpovědí API.
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
def identified(page, server):
    page.locator('[data-tab="data"]').click()
    page.locator('[data-sub="sources"]').click()
    page.locator('[data-testid="src-demo"]').click()
    page.wait_for_function("() => (document.querySelector('[data-testid=\"data-info\"]')||{}).innerText?.includes('demo')")
    _call(server, page, "PATCH", B + "/settings", {"chosen": ["P1D", "I1D"]})
    j = _call(server, page, "POST", B + "/identify", {})
    _until(lambda: _call(server, page, "GET", f"/api/v1/jobs/{j['id']}")["state"] not in ("queued", "running"), 120)
    page.reload(wait_until="networkidle")
    page.wait_for_selector('[data-testid="api-ok"]', timeout=20000)
    return page


def test_next_step_in_model_context_row_opens_target(identified, server):
    pg = identified
    st = _call(server, pg, "GET", B + "/guide/status")
    nxt = st["next"]
    assert nxt and nxt["action"] and nxt["action"]["target"]          # výchozí rozsah regulátoru → akce s cílovým prvkem
    pg.locator('[data-tab="model"]').click()
    box = pg.locator('[data-testid="context-row"] [data-testid="next-step"]')
    box.wait_for(timeout=20000)
    assert box.inner_text().startswith(("Next:", "Další krok:")) and nxt["text"] in box.inner_text()
    assert nxt["text"] in box.get_attribute("title")
    # text se nezalamuje: řádek zůstane jednořádkový (výška tlačítka, ne násobek)
    assert box.bounding_box()["height"] < 40
    pg.locator('[data-testid="next-open"]').click()
    tab = nxt["action"]["tab"]
    pg.wait_for_function("t => document.querySelector(`[data-tab=\"${t}\"]`).getAttribute('aria-selected') === 'true'", arg=tab)
    pg.wait_for_function("id => document.querySelector(`[data-testid=\"${id}\"]`)?.classList.contains('guide-pulse')",
                         arg=nxt["action"]["target"], timeout=10000)


def test_tab_marks_follow_the_status(identified, server):
    pg = identified
    st = _call(server, pg, "GET", B + "/guide/status")["tabs"]
    # Model: ověření na jiném úseku zůstává `todo` → bez značky, ale se shrnutím v title / aria-label
    m = st["model"]
    tab = pg.locator('[data-tab="model"]')
    assert pg.locator('[data-testid="tab-mark-model"]').count() == 0
    assert f"{m['ok']} of {m['ok'] + m['warn'] + m['todo']} done" in tab.get_attribute("title")
    assert "Model: " in tab.get_attribute("aria-label")
    # Data: po nastavení rozsahu je vše splněno → ✓ (značka je aria-hidden, shrnutí je v aria-label)
    assert pg.locator('[data-testid="tab-mark-data"]').count() == 0
    _call(server, pg, "PATCH", B + "/settings", {"pv_hi": 250.0})
    pg.reload(wait_until="networkidle")                              # změna šla mimo UI → načíst stav znovu
    pg.wait_for_selector('[data-testid="api-ok"]', timeout=20000)
    mark = pg.locator('[data-testid="tab-mark-data"]')
    mark.wait_for(timeout=20000)
    assert mark.inner_text() == "✓" and mark.get_attribute("aria-hidden") == "true"
    assert "3 of 3 done" in pg.locator('[data-tab="data"]').get_attribute("aria-label")
    # další krok se přesunul na ověření modelu (bez akce → jen přepnutí záložky, bez cíle)
    nxt = _call(server, pg, "GET", B + "/guide/status")["next"]
    assert nxt["tab"] == "model" and nxt["action"] is None
    pg.locator('[data-tab="tuning"]').click()
    pg.locator('[data-testid="next-open"]').click()
    pg.wait_for_function("document.querySelector('[data-tab=\"model\"]').getAttribute('aria-selected') === 'true'")
