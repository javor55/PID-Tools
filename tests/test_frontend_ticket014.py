"""
TICKET-014 v prohlížeči: při zavření stránky (pagehide) se hned zapíše záchranná kopie a při neuložených změnách
`beforeunload` vyvolá dotaz (defaultPrevented). Tlačítko v kartě chyby pokrývá Vitest (frontend/tests/autosave.test.ts).
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


def _call(server, path, method="GET", body=None):
    req = urllib.request.Request(server + path, method=method,
                                 data=None if body is None else json.dumps(body).encode(),
                                 headers={"X-PID-Token": TOKEN, "Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=60).read() or b"null")


def _until(fn, timeout=20.0):
    end = time.time() + timeout
    while time.time() < end:
        v = fn()
        if v:
            return v
        time.sleep(0.1)
    raise AssertionError("timeout")


@pytest.fixture(scope="module")
def wid(page, server):
    page.locator('[data-tab="data"]').click()
    page.locator('[data-sub="sources"]').click()
    page.locator('[data-testid="src-demo"]').click()
    page.wait_for_function("() => (document.querySelector('[data-testid=\"data-info\"]')||{}).innerText?.includes('demo')")
    return page.evaluate("sessionStorage.getItem('pid.wid')")


def _dirty(pg):
    return pg.locator('[data-testid="data-sum"]').get_attribute("data-dirty")


def test_pagehide_flushes_recovery_copy(page, server, wid):
    base = f"/api/v1/workspaces/{wid}"
    t0 = time.time()
    _call(server, base + "/settings", "PATCH", {"ctype": "PID"})
    assert _call(server, base + "/save-state")["autosave_pending"] is True
    # Změna šla přes API mimo stránku: stránka si stav obnovuje po 5 s, počkej na další dotaz (do 8 s klidu zbývá čas).
    n = len(page.requested)
    for _ in range(70):
        if any(m == "GET" and u.endswith(f"{base}/save-state") for m, u in page.requested[n:]):
            break
        page.wait_for_timeout(100)                     # událost požadavku se doručí jen při volání Playwrightu
    else:
        raise AssertionError("stránka si stav uložení neobnovila")
    page.wait_for_timeout(300)
    page.evaluate("() => window.dispatchEvent(new Event('pagehide'))")
    # Do 8 s klidu a bez minutového limitu: kopie musí vzniknout hned
    _until(lambda: _call(server, "/api/v1/autosave/latest")["available"], 3)
    latest = _call(server, "/api/v1/autosave/latest")
    assert latest["at"] >= t0
    assert _call(server, base + "/save-state")["autosave_pending"] is False
    # Opakované zavření pro stejný rev nic nepošle
    n = len(page.requested)
    page.evaluate("() => window.dispatchEvent(new Event('pagehide'))")
    page.wait_for_timeout(500)
    assert not [1 for m, u in page.requested[n:] if m == "POST" and u.endswith("/autosave")]


def test_beforeunload_asks_only_when_dirty(page, server, wid):
    base = f"/api/v1/workspaces/{wid}"
    probe = "() => { const e = new Event('beforeunload', {cancelable: true}); window.dispatchEvent(e); return e.defaultPrevented; }"
    _call(server, base + "/settings", "PATCH", {"ctype": "PI"})
    _until(lambda: _dirty(page) == "1", 20)
    assert page.evaluate(probe) is True
    page.locator('[data-tab="data"]').click()
    with page.expect_download():
        page.keyboard.press("Control+s")
    _until(lambda: _dirty(page) == "0", 15)
    assert page.evaluate(probe) is False
