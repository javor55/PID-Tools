"""
FEATURE-005: záložka Model ve třech podzáložkách (Identifikace, Validace, Rezidua a nejistota). Ověřuje výšku obsahu
každé podzáložky při 1 440 × 900, zachování podzáložky po znovunačtení, stálý pruh se souhrnem modelu a přepnutí
podzáložky akcí průvodce. Potřebuje sestavené UI (cd frontend && npm run build).
"""
import json
import time
import urllib.request

import pytest

pytest.importorskip("playwright.sync_api")
import test_frontend as _tf  # noqa: E402

TOKEN = _tf.TOKEN
server, page = _tf.server, _tf.page                      # fixtury serveru a prohlížeče
SUBS = ("ident", "validate", "residuals")
# po otevření podzáložky se čeká na prvek, který ukazuje, že je obsah vykreslený
READY = {"ident": "models", "validate": "val-chart", "residuals": "resid-chart"}


def _call(server, page, method, path, body=None):
    wid = page.evaluate("sessionStorage.getItem('pid.wid')")
    req = urllib.request.Request(server + path.format(wid=wid), method=method,
                                 data=None if body is None else json.dumps(body).encode(),
                                 headers={"X-PID-Token": TOKEN, "Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=120).read() or b"null")


def _sub(page, sub):
    page.locator(f'[data-testid="model-subtabs"] [data-sub="{sub}"]').click()
    page.wait_for_selector(f'[data-testid="{READY[sub]}"]', timeout=60000)
    page.wait_for_timeout(500)                           # dotažení grafů a karet


@pytest.fixture(scope="module")
def ready(page, server):
    """Demo, identifikace P1D + I1D přes API, záložka Model."""
    page.set_viewport_size({"width": 1440, "height": 900})
    page.locator('[data-tab="data"]').click()
    page.locator('[data-sub="sources"]').click()
    page.locator('[data-testid="src-demo"]').click()
    page.wait_for_function("() => (document.querySelector('[data-testid=\"data-info\"]')||{}).innerText?.includes('demo')")
    _call(server, page, "PATCH", "/api/v1/workspaces/{wid}/settings", {"chosen": ["P1D", "I1D"]})
    j = _call(server, page, "POST", "/api/v1/workspaces/{wid}/identify", {})
    for _ in range(600):
        st = _call(server, page, "GET", f"/api/v1/jobs/{j['id']}")
        if st["state"] not in ("queued", "running"):
            assert st["state"] == "done", st
            break
        time.sleep(0.2)
    page.locator('[data-tab="model"]').click()
    _sub(page, "ident")
    return True


def test_subtab_content_height(page, ready):
    """Výška hlavní plochy žádné podzáložky nepřesáhne dvě obrazovky; ve viditelné podzáložce jsou jen její karty."""
    tabs = page.locator('[data-testid="model-subtabs"] [role="tab"]')
    assert tabs.count() == 3
    heights = {}
    for sub in SUBS:
        _sub(page, sub)
        assert page.locator(f'[data-testid="model-subtabs"] [data-sub="{sub}"]').get_attribute("aria-selected") == "true"
        heights[sub] = page.evaluate("document.querySelector('.main').scrollHeight")
    print("výška .main [px]:", heights)
    assert max(heights.values()) <= 2 * 900, heights
    # rozdělení karet
    _sub(page, "ident")
    assert page.locator('[data-testid="model-trend"]').count() == 1 and page.locator('[data-testid="val-seg"]').count() == 0
    _sub(page, "validate")
    assert page.locator('[data-testid="val-seg"]').count() == 1 and page.locator('[data-testid="model-views"]').count() == 1
    assert page.locator('[data-testid="residuals"]').count() == 0
    _sub(page, "residuals")
    for t in ("validation", "uncertainty", "residuals"):
        assert page.locator(f'[data-testid="{t}"]').count() == 1
    assert page.locator('[data-testid="val-seg"]').count() == 0


def test_summary_strip_in_all_subtabs(page, ready):
    for sub in SUBS:
        _sub(page, sub)
        s = page.locator('[data-testid="model-summary"]')
        assert s.is_visible()
        assert "FIT" in s.inner_text()
        assert float(page.locator('[data-testid="msum-fit"]').inner_text().replace("%", "")) > 0


def test_side_cards_collapse_outside_ident(page, ready):
    def open_of(tid):
        return page.locator(f'[data-testid="{tid}"]').evaluate("e => e.open")
    _sub(page, "ident")
    assert open_of("side-idm") and open_of("params")
    _sub(page, "validate")
    assert not open_of("side-idm") and not open_of("params") and not open_of("side-models")
    assert open_of("side-validation")                    # „Model validation“ s tlačítkem „Use the model for tuning“
    _sub(page, "residuals")
    assert not open_of("side-idm") and open_of("side-validation")
    _sub(page, "ident")
    assert open_of("side-idm")


def test_subtab_survives_reload_and_model(page, server, ready):
    _sub(page, "residuals")
    before = _call(server, page, "GET", "/api/v1/workspaces/{wid}/model")["selected"]
    page.reload(wait_until="networkidle")
    page.wait_for_selector('[data-testid="model-subtabs"]', timeout=30000)
    page.wait_for_selector('[data-testid="residuals"]', timeout=60000)
    assert page.locator('[data-testid="model-subtabs"] [data-sub="residuals"]').get_attribute("aria-selected") == "true"
    assert page.evaluate("localStorage.getItem('pid.msub')") == '"residuals"'
    # přepínání podzáložek nemění vybraný model
    _sub(page, "ident")
    _sub(page, "validate")
    assert _call(server, page, "GET", "/api/v1/workspaces/{wid}/model")["selected"] == before


def test_guide_action_switches_subtab(page, ready):
    """Akce průvodce s cílem v podzáložce Validace přepne podzáložku a prvek se zvýrazní.
    Průvodce Modelu dnes žádné akce s cílem nemá (guides.py), proto se odpověď průvodce upraví: kontrola s akcí na `val-seg`."""
    def patched(route):
        resp = route.fetch()
        body = resp.json()
        body["checklist"] = [{"ok": "warn", "text": "Validate the model",
                              "action": {"tab": "model", "target": "val-seg", "label": "Validate"}}]
        route.fulfill(response=resp, json=body)
    page.route("**/guide/model*", patched)
    try:
        _sub(page, "ident")
        page.locator('[data-testid="help-btn"]').click()
        page.locator('[data-testid="guide-tab-checklist"]').click()
        page.locator('[data-testid="guide-action"]').click()
        page.wait_for_function("() => document.querySelector('[data-testid=\"val-seg\"]')?.classList.contains('guide-pulse')", timeout=10000)
        assert page.locator('[data-testid="model-subtabs"] [data-sub="validate"]').get_attribute("aria-selected") == "true"
    finally:
        page.unroute("**/guide/model*")
