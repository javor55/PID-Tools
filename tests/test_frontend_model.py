"""
Záložka Model v prohlížeči (E6): ověření na jiném úseku (úsek, režim, Sada 1/2, tabulka hodnocení, verdikt), pohledy na
model (odezva na skok, porovnání modelů), Set 1 a zúžení na ruční úsek v panelu. Potřebuje sestavené UI.
Proměnná PIDTOOLS_SHOT = cesta: uloží snímek záložky Model (1440×1100).
"""
import json
import os
import time
import urllib.request

import pytest

pytest.importorskip("playwright.sync_api")
import test_frontend as _tf  # noqa: E402

TOKEN = _tf.TOKEN
server, page = _tf.server, _tf.page                      # fixtury serveru a prohlížeče


def _call(server, page, method, path, body=None):
    wid = page.evaluate("sessionStorage.getItem('pid.wid')")
    req = urllib.request.Request(server + path.format(wid=wid), method=method,
                                 data=None if body is None else json.dumps(body).encode(),
                                 headers={"X-PID-Token": TOKEN, "Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=120).read() or b"null")


@pytest.fixture(scope="module")
def ready(page, server):
    """Demo, identifikace P1D + I1D přes API, záložka Model."""
    page.set_viewport_size({"width": 1440, "height": 1100})
    page.locator('[data-tab="data"]').click()
    page.locator('[data-sub="quality"]').click()
    page.locator('[data-testid="src-seg"] [data-value="demo"]').click()
    page.wait_for_function("() => (document.querySelector('[data-testid=\"data-info\"]')||{}).innerText?.includes('demo')")
    _call(server, page, "PATCH", "/workspaces/{wid}/settings", {"chosen": ["P1D", "I1D"]})
    j = _call(server, page, "POST", "/workspaces/{wid}/identify", {})
    for _ in range(600):
        st = _call(server, page, "GET", f"/jobs/{j['id']}")
        if st["state"] not in ("queued", "running"):
            assert st["state"] == "done", st
            break
        time.sleep(0.2)
    page.locator('[data-tab="model"]').click()
    page.wait_for_selector('[data-testid="models"] tbody tr', timeout=60000)
    return True


def _fit(page, which):
    return float(page.locator(f'[data-testid="val-fit-{which}"]').inner_text())


def test_validation_range_and_rating(page, server, ready):
    page.wait_for_selector('[data-testid="val-rating"]', timeout=60000)
    assert page.locator('[data-testid="val-rating"] tbody tr').count() == 2
    assert page.locator('[data-testid="val-verdict"]').get_attribute("data-verdict") == "same"   # celý záznam = úsek id
    a = page.locator('[data-testid="val-a"]')
    a.fill("1800")
    a.press("Enter")
    page.wait_for_function("() => document.querySelector('[data-testid=\"val-a\"]').value === '1800'")
    page.wait_for_timeout(1500)
    st = _call(server, page, "GET", "/workspaces/{wid}/settings")
    assert st["val_rng"][0] == 1800
    v = _call(server, page, "GET", "/workspaces/{wid}/model/validate")
    assert v["rng"][0] == 1800
    assert abs(_fit(page, "val") - v["val"]["FIT"]) < 0.06
    assert abs(_fit(page, "id") - v["id"]["FIT"]) < 0.06
    assert int(page.locator('[data-testid="val-chart"]').get_attribute("data-n")) > 20
    # model P1D je z dema dobrý i na druhé části záznamu
    assert _fit(page, "val") > 50
    shot = os.environ.get("PIDTOOLS_SHOT")
    if shot:
        page.locator('[data-testid="val-seg"]').scroll_into_view_if_needed()
        page.screenshot(path=shot, full_page=False)


def test_validation_loop_sets_and_views(page, server, ready):
    page.locator('[data-testid="val-mode"] [data-value="cl"]').click()
    page.wait_for_selector('[data-testid="val-which"]', timeout=20000)
    page.wait_for_function("() => (document.querySelector('[data-testid=\"val-fits\"]')||{}).innerText?.includes('MV')", timeout=60000)
    page.locator('[data-testid="val-which"] [data-value="2"]').click()
    page.wait_for_function("() => document.querySelector('[data-testid=\"val-which\"] [data-value=\"2\"]').getAttribute('aria-pressed') === 'true'")
    page.wait_for_timeout(1500)
    assert page.locator('[data-testid="val-fit-pv"]').inner_text().strip().endswith("%")
    page.locator('[data-testid="val-reset"]').click()
    page.wait_for_timeout(1200)
    assert _call(server, page, "GET", "/workspaces/{wid}/settings").get("val_rng") in (None, [])
    # pohledy na model
    page.wait_for_selector('[data-testid="step-chart"]')
    assert int(page.locator('[data-testid="step-chart"]').get_attribute("data-n")) >= 1
    page.locator('[data-testid="views-seg"] [data-value="all"]').click()
    page.wait_for_selector('[data-testid="compare-chart"]')
    page.wait_for_function("() => +document.querySelector('[data-testid=\"compare-chart\"]').dataset.n === 3", timeout=30000)


def test_model_on_full_record_by_default(page, server, ready):
    """Model se ve výchozím stavu kreslí přes celý záznam; „jen v úsecích“ je volba."""
    rng = page.locator('[data-testid="model-trend"] .pidw-range')
    rng.first.wait_for(timeout=30000)
    assert rng.first.locator("button.on").get_attribute("data-v") == "full"


def test_closed_loop_panel(page, server, ready):
    page.locator('[data-testid="id-mode"]').select_option("cl")
    page.wait_for_selector('[data-testid="cl-note"]', timeout=20000)
    # regulátor v záznamu (Sada 1) se zadává přímo v Modelu, v jednotkách bloku; je to táž Sada 1 jako v Ladění
    page.wait_for_selector('[data-testid="record-set"] [data-testid="rec-Gain"]', timeout=20000)
    assert "PIDConL" in page.locator('[data-testid="record-set-ctl"]').inner_text()
    g = page.locator('[data-testid="rec-Gain"]')
    g.fill("1.25")
    g.press("Enter")
    page.wait_for_function("() => Math.abs(+document.querySelector('[data-testid=\"rec-Gain\"]').value - 1.25) < 1e-9")
    assert _call(server, page, "GET", "/workspaces/{wid}/settings")["set1_gain"] == 1.25
    page.locator('[data-testid="set1-estimate"]').click()
    page.wait_for_selector('[data-testid="set1-msg"]', timeout=30000)
    # odhad ze záznamu přepíše Sadu 1 a karta se obnoví
    page.wait_for_function("() => +document.querySelector('[data-testid=\"rec-Gain\"]').value !== 1.25", timeout=20000)
    page.locator('[data-testid="id-mode"]').select_option("auto")
    page.wait_for_timeout(800)
