"""
FEATURE-006: zpět / znovu v hlavičce a zkratkami Ctrl+Z / Ctrl+Y. Změna Set 1 Gain v Ladění, Ctrl+Z vrátí pole, hodnotu
na serveru i graf odezvy (nová simulace), tlačítko Znovu změnu obnoví; při fokusu v číselném poli Ctrl+Z neposílá
POST /undo (v poli platí vracení prohlížeče). Potřebuje sestavené UI (cd frontend && npm run build).
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
GAIN = '[data-testid="set1-Gain"]'


def _call(page, method, path, body=None):
    wid = page.evaluate("sessionStorage.getItem('pid.wid')")
    req = urllib.request.Request(page.server + path.format(wid=wid), method=method,
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


def _gain(page):
    return _call(page, "GET", B + "/settings")["set1_gain"]


def _n_requests(page, method, suffix):
    return sum(1 for m, u in page.requested if m == method and u.split("?")[0].endswith(suffix))


def _chart(page):
    """Otisk grafu odezvy: tvar všech křivek."""
    return page.evaluate("""() => { const s = document.querySelector('[data-testid="response"]');
      return [...s.querySelectorAll('svg path')].map(p => p.getAttribute('d') || '').join('|'); }""")


@pytest.fixture(scope="module")
def tuning(page, server):
    page.locator('[data-tab="data"]').click()
    page.locator('[data-sub="sources"]').click()
    page.locator('[data-testid="src-demo"]').click()
    page.wait_for_function("() => (document.querySelector('[data-testid=\"data-info\"]')||{}).innerText?.includes('demo')")
    _call(page, "PATCH", B + "/settings", {"chosen": ["P1D", "I1D"]})
    j = _call(page, "POST", B + "/identify", {})
    _until(lambda: _call(page, "GET", f"/api/v1/jobs/{j['id']}")["state"] not in ("queued", "running"), 120)
    page.reload(wait_until="networkidle")
    page.wait_for_selector('[data-testid="api-ok"]', timeout=20000)
    page.locator('[data-tab="tuning"]').click()
    page.wait_for_selector(GAIN, timeout=30000)
    page.wait_for_selector('[data-testid="response"] svg path', timeout=30000, state="attached")
    return page


def test_buttons_start_disabled(page, tuning):
    for k in ("undo", "redo"):
        b = page.locator(f'[data-testid="head-{k}"]')
        assert b.is_disabled() and b.get_attribute("aria-label") and b.get_attribute("title")


def test_ctrl_z_returns_field_server_and_chart(page, tuning):
    g0 = _gain(page)
    shown0, chart0 = page.locator(GAIN).input_value(), _chart(page)
    g1 = round(g0 + 1.5, 3)
    page.locator(GAIN).fill(str(g1))
    page.locator(GAIN).press("Enter")
    _until(lambda: _gain(page) == g1)
    _until(lambda: _chart(page) != chart0)                              # graf se přepočítal pro novou sadu
    chart1 = _chart(page)
    undo = page.locator('[data-testid="head-undo"]')
    page.wait_for_function("() => !document.querySelector('[data-testid=\"head-undo\"]').disabled", timeout=15000)
    assert "Set 1 Gain" in undo.get_attribute("title") and undo.get_attribute("title").startswith("Undo: ")
    assert undo.get_attribute("title").endswith("(Ctrl+Z)") and undo.get_attribute("aria-label") == undo.get_attribute("title")
    sims = _n_requests(page, "POST", "/simulate")
    page.locator("h1").click()                                          # fokus mimo pole
    page.keyboard.press("Control+z")
    _until(lambda: _gain(page) == g0)
    _until(lambda: float(page.locator(GAIN).input_value()) == float(shown0))   # pole ukazuje původní hodnotu
    _until(lambda: _n_requests(page, "POST", "/simulate") > sims)       # odezva se po návratu přepočítala
    _until(lambda: _chart(page) == chart0 and _chart(page) != chart1)
    page.wait_for_function("() => !document.querySelector('[data-testid=\"head-redo\"]').disabled", timeout=15000)
    assert page.locator('[data-testid="head-redo"]').get_attribute("title").startswith("Redo: ")
    assert page.locator('[data-testid="head-undo"]').is_disabled()


def test_redo_button_restores_change(page, tuning):
    g_before = _gain(page)
    page.locator('[data-testid="head-redo"]').click()
    _until(lambda: _gain(page) != g_before)
    _until(lambda: abs(float(page.locator(GAIN).input_value()) - _gain(page)) < 1e-9)
    page.wait_for_function("() => document.querySelector('[data-testid=\"head-redo\"]').disabled", timeout=15000)
    page.wait_for_function("() => !document.querySelector('[data-testid=\"head-undo\"]').disabled", timeout=15000)


def test_ctrl_y_redoes_after_undo_button(page, tuning):
    g = _gain(page)
    page.locator('[data-testid="head-undo"]').click()
    _until(lambda: _gain(page) != g)
    page.locator("h1").click()
    page.keyboard.press("Control+y")
    _until(lambda: _gain(page) == g)


def test_ctrl_z_in_number_field_does_not_call_undo(page, tuning):
    n0, r0 = _n_requests(page, "POST", "/undo"), _n_requests(page, "POST", "/redo")
    page.locator(GAIN).focus()
    page.keyboard.press("Control+z")
    page.keyboard.press("Control+y")
    page.wait_for_timeout(800)
    assert _n_requests(page, "POST", "/undo") == n0 and _n_requests(page, "POST", "/redo") == r0
    page.locator("h1").click()
    page.keyboard.press("Control+z")                                    # mimo pole se zavolá
    _until(lambda: _n_requests(page, "POST", "/undo") == n0 + 1)


def test_no_page_errors(page, tuning):
    assert page.errors == []
