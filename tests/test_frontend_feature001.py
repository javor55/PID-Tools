"""
FEATURE-001: klávesové zkratky a uložení projektu odkudkoli (Ctrl+S, F5, Ctrl+1…6, Alt+↑/↓, Ctrl+P, F1).
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


def _dirty(pg):
    return pg.locator('[data-testid="data-sum"]').get_attribute("data-dirty")


@pytest.fixture(scope="module")
def ready(page, server):
    page.locator('[data-tab="data"]').click()
    page.locator('[data-sub="sources"]').click()
    page.locator('[data-testid="src-demo"]').click()
    page.wait_for_function("() => (document.querySelector('[data-testid=\"data-info\"]')||{}).innerText?.includes('demo')")
    _call(server, page, "PATCH", B + "/settings", {"chosen": ["P1D", "I1D"]})
    j = _call(server, page, "POST", B + "/identify", {})
    _until(lambda: _call(server, page, "GET", f"/api/v1/jobs/{j['id']}")["state"] not in ("queued", "running"), 120)
    page.reload(wait_until="networkidle")
    page.wait_for_selector('[data-testid="api-ok"]', timeout=20000)
    page.wait_for_selector('[data-testid="data-sum"]', timeout=20000)
    return page


def test_ctrl_digits_switch_tabs(ready):
    pg = ready
    pg.keyboard.press("Control+3")
    pg.wait_for_selector('[data-testid="tab-tuning"]', timeout=20000)
    pg.keyboard.press("Control+1")
    pg.wait_for_selector('[data-testid="tab-data"]', timeout=20000)
    pg.keyboard.press("Control+6")
    pg.wait_for_selector('[data-testid="tab-project"]', timeout=20000)
    pg.keyboard.press("Control+1")
    pg.keyboard.press("Control+p")                            # Ctrl+P: záložka Projekt, protokol se nevytváří
    pg.wait_for_selector('[data-testid="tab-project"]', timeout=20000)
    assert pg.locator('[data-testid="report-frame"]').count() == 0


def test_digit_typed_into_number_field_keeps_tab(ready):
    pg = ready
    pg.keyboard.press("Control+3")
    pg.wait_for_selector('[data-testid="tab-tuning"]', timeout=20000)
    field = pg.locator('aside.side input[type="number"]').first
    field.wait_for(timeout=20000)
    field.focus()
    pg.keyboard.type("1")
    assert pg.locator('[data-testid="tab-tuning"]').count() == 1
    assert pg.locator('[data-testid="tab-data"]').count() == 0


def test_f5_runs_calculate_without_reload(ready):
    pg = ready
    pg.keyboard.press("Control+3")
    pg.wait_for_selector('[data-testid="tab-tuning"]', timeout=20000)
    pg.wait_for_selector('[data-testid="calc"]:not([disabled])', timeout=30000)
    assert "F5" in pg.locator('[data-testid="calc"]').get_attribute("title")
    wid = pg.evaluate("sessionStorage.getItem('pid.wid')")
    pg.evaluate("window.__mark = 1")
    with pg.expect_request(lambda r: r.method == "POST" and r.url.endswith("/tuning/suggest"), timeout=15000):
        pg.keyboard.press("F5")
    assert pg.evaluate("window.__mark") == 1                  # stránka se nenačetla znovu
    assert pg.evaluate("sessionStorage.getItem('pid.wid')") == wid
    pg.wait_for_selector('[data-testid="calc"]:not([disabled])', timeout=30000)
    # mimo Ladění F5 nic nespouští, ale stránku také nenačte
    pg.keyboard.press("Control+1")
    pg.wait_for_selector('[data-testid="tab-data"]', timeout=20000)
    pg.keyboard.press("F5")
    pg.wait_for_timeout(500)
    assert pg.evaluate("window.__mark") == 1


def test_ctrl_s_and_head_button_save(ready, server):
    pg = ready
    pg.keyboard.press("Control+1")
    pg.wait_for_selector('[data-testid="tab-data"]', timeout=20000)
    with pg.expect_download() as dl:                          # Ctrl+S stáhne soubor projektu a vyčistí „neuloženo“
        pg.keyboard.press("Control+s")
    assert dl.value.suggested_filename.endswith("_projekt.pidproj")
    _until(lambda: _dirty(pg) == "0", 15)
    assert "Ctrl+S" in pg.locator('[data-testid="head-save"]').get_attribute("title")
    for n, how in enumerate(("keys", "button")):
        _call(server, pg, "PATCH", B + "/settings", {"ctype": "PID" if n == 0 else "PI"})
        _until(lambda: _dirty(pg) == "1", 20)                 # stav uložení se obnovuje po 5 s
        assert "primary" in pg.locator('[data-testid="head-save"]').get_attribute("class")
        with pg.expect_download():
            if how == "keys":
                pg.keyboard.press("Control+s")
            else:
                pg.locator('[data-testid="head-save"]').click()
        _until(lambda: _dirty(pg) == "0", 15)
        assert "primary" not in pg.locator('[data-testid="head-save"]').get_attribute("class")


def test_guide_lists_shortcuts(ready):
    pg = ready
    pg.keyboard.press("F1")
    pg.wait_for_selector('[data-testid="help-dialog"][open]', timeout=10000)
    pg.locator('[data-testid="guide-tab-keys"]').click()
    txt = pg.locator('[data-testid="guide-keys"]').inner_text()
    for s in ("Ctrl+S", "Ctrl+P", "F5", "F1", "Alt"):
        assert s in txt
    assert "Ctrl+Q" not in txt and "Ctrl+O" not in txt
    pg.keyboard.press("Escape")


def test_alt_arrows_switch_loop(ready, server):
    pg = ready
    pg.keyboard.press("Control+1")
    loops = _call(server, pg, "GET", B + "/loops")
    n = len(loops["loops"])
    if n < 2:
        pytest.skip("demo má jedinou smyčku")
    _call(server, pg, "PUT", B + "/loops/active", {"index": 0})
    pg.reload(wait_until="networkidle")
    pg.wait_for_selector('[data-testid="loop-select"]', timeout=20000)
    pg.locator("body").click()
    pg.keyboard.press("Alt+ArrowUp")                          # na okraji seznamu nic
    pg.wait_for_timeout(500)
    assert _call(server, pg, "GET", B + "/loops")["active"] == 0
    pg.keyboard.press("Alt+ArrowDown")
    _until(lambda: _call(server, pg, "GET", B + "/loops")["active"] == 1, 15)
    pg.keyboard.press("Alt+ArrowUp")
    _until(lambda: _call(server, pg, "GET", B + "/loops")["active"] == 0, 15)
