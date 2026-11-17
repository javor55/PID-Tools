"""
TICKET-002 v prohlížeči: po smazání pracovního prostoru na serveru za běhu aplikace se založí nový prostor,
ukáže se úvodní obrazovka s nabídkou obnovy ze záchranné kopie a toast; v konzoli není chyba.
Potřebuje sestavené UI (cd frontend && npm run build).
"""
import json
import time
import urllib.error
import urllib.request

import pytest

pytest.importorskip("playwright.sync_api")
import test_frontend as _tf  # noqa: E402

TOKEN = _tf.TOKEN
server, page = _tf.server, _tf.page                      # fixtury serveru a prohlížeče


def _call(server, path, method="GET", body=None):
    req = urllib.request.Request(server + path, method=method,
                                 data=None if body is None else json.dumps(body).encode(),
                                 headers={"X-PID-Token": TOKEN, "Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=60).read() or b"null")


def test_workspace_lost_recovers(page, server):
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.locator('[data-tab="data"]').click()
    page.locator('[data-sub="sources"]').click()
    page.locator('[data-testid="src-demo"]').click()
    page.wait_for_function("() => (document.querySelector('[data-testid=\"data-info\"]')||{}).innerText?.includes('demo')")
    old = page.evaluate("sessionStorage.getItem('pid.wid')")
    base = f"/api/v1/workspaces/{old}"
    _call(server, base + "/settings", "PATCH", {"chosen": ["P1D", "I1D"]})
    _call(server, base + "/autosave", "POST")                         # záchranná kopie existuje
    assert _call(server, "/api/v1/autosave/latest")                   # a server ji nabízí

    _call(server, base, "DELETE")                                     # prostor zmizí za běhu aplikace
    page.locator('[data-tab="model"]').click()                        # přepnutí spustí dotazy → 404

    deadline = time.time() + 10
    new = old
    while time.time() < deadline and new == old:
        new = page.evaluate("sessionStorage.getItem('pid.wid')")
        time.sleep(0.2)
    assert new and new != old
    page.wait_for_selector('[data-testid="start-screen"]', timeout=10000)
    page.wait_for_selector('[data-testid="start-recovery"]', timeout=10000)
    page.wait_for_selector('[data-testid="start-restore"]', timeout=10000)
    assert page.locator('[role="status"]', has_text="expired").count() >= 1       # toast
    assert _call(server, f"/api/v1/workspaces/{new}")["has_data"] is False
    with pytest.raises(urllib.error.HTTPError):
        _call(server, base)                                           # starý prostor se neobnovil
    assert errors == []
