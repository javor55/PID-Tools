"""
TICKET-009: sdílené moduly JS (frontend/src/legacy) se při odchodu ze stránky odpojí (viewer.js, trend.js vracejí
destroy()) a pole v Data › Trendy mají přístupný název. Potřebuje sestavené UI (cd frontend && npm run build).
"""
import pytest

pytest.importorskip("playwright.sync_api")
import test_frontend as _tf  # noqa: E402

server, page = _tf.server, _tf.page                      # fixtury serveru a prohlížeče

def _demo(page):
    page.locator('[data-tab="data"]').click()
    page.locator('[data-sub="sources"]').click()
    page.locator('[data-testid="src-demo"]').click()
    page.wait_for_function("() => (document.querySelector('[data-testid=\"data-info\"]')||{}).innerText?.includes('demo')")


def _viewer_state(page):
    return page.evaluate("() => ({pidv: document.querySelectorAll('.pidv').length, "
                         "reg: Object.keys(window.__pidView || {}).length})")


def test_viewer_destroy_on_tab_switch(page, server):
    """20× Data › Trendy ↔ Data › Kvalita dat: v dokumentu nejvýš jeden .pidv a v registru nejvýš jeden záznam."""
    _demo(page)
    for i in range(20):
        sub, sel = (("trends", '[data-testid="trd-viewer"] .pidv-panel canvas') if i % 2 == 0
                    else ("quality", '[data-testid="record-viewer"] .pidv-panel canvas'))
        page.locator(f'[data-sub="{sub}"]').click()
        page.wait_for_selector(sel, timeout=30000)
        st = _viewer_state(page)
        assert st["pidv"] <= 1 and st["reg"] <= 1, (i, sub, st)
    # po odchodu z prohlížeče (Zdroje) nezůstává nic
    page.locator('[data-sub="sources"]').click()
    page.wait_for_selector('[data-testid="src-demo"]', timeout=10000)
    assert _viewer_state(page) == {"pidv": 0, "reg": 0}


def test_trend_destroy_on_tab_switch(page, server):
    """10× Model ↔ Data: kořenů trend.js (.pidw) nejvýš tolik, kolik je na stránce grafů Trend, a stejně záznamů."""
    _demo(page)
    for i in range(10):
        page.locator('[data-tab="model"]').click()
        page.wait_for_selector('[data-testid="model-trend"] .pidw', timeout=20000)
        n = page.locator('[data-testid="model-trend"]').count()
        st = page.evaluate("() => ({pidw: document.querySelectorAll('.pidw').length, "
                           "reg: Object.keys(window.__pidTrend || {}).length})")
        assert st["pidw"] <= n and st["reg"] <= n, (i, n, st)
        page.locator('[data-tab="data"]').click()
        page.wait_for_selector('[data-testid="data-subtabs"]', timeout=10000)
    st = page.evaluate("() => ({pidw: document.querySelectorAll('.pidw').length, "
                       "reg: Object.keys(window.__pidTrend || {}).length})")
    assert st == {"pidw": 0, "reg": 0}, st
