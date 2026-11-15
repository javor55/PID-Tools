"""
Ladění v prohlížeči: přepínání simulačních scénářů (TICKET-020, připomínka k beta 3, bod 7). Pro každý scénář z výběru
se ověří, že se volba zapsala na server, popis a tabulka událostí odpovídají scénáři a graf odezvy se překreslil;
dále délka simulace (automaticky / ručně), stav po znovunačtení stránky a po přepnutí smyčky.
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
    page.wait_for_selector('[data-testid="response"] svg path', timeout=30000)
    return page


def _chart(pg):
    """Otisk grafu odezvy: popis os a tvar všech křivek."""
    return pg.evaluate("""() => { const s = document.querySelector('[data-testid="response"]');
      return [...s.querySelectorAll('svg path')].map(p => p.getAttribute('d') || '').join('|') + '#' +
             [...s.querySelectorAll('svg text')].map(t => t.textContent).join(','); }""")


def _state(pg):
    return dict(kind=pg.locator('[data-testid="scen-kind"]').input_value(),
                sub=pg.locator('[data-testid="response"] .tn-sub').first.inner_text(),
                note=pg.locator('[data-testid="scenario"] .tn-note').first.inner_text(),
                rows=pg.locator('[data-testid="scen-rows"] tbody tr').count(), chart=_chart(pg))


def _pick(pg, server, kind):
    before = _chart(pg)
    pg.locator('[data-testid="scen-kind"]').select_option(kind)
    _until(lambda: _call(server, pg, "GET", B + "/scenario")["kind"] == kind)
    _until(lambda: pg.locator('[data-testid="scen-kind"]').input_value() == kind)
    try:
        _until(lambda: _chart(pg) != before, 15)             # graf se překreslil pro nový scénář
    except AssertionError:
        pass                                                 # stejný otisk vyhodnotí test (uvede, který scénář)
    pg.wait_for_timeout(600)
    return _state(pg)


def test_every_scenario_switches(tuning, server):
    pg = tuning
    kinds = _call(server, pg, "GET", B + "/scenario")["kinds"]
    assert len(kinds) >= 3
    first = _call(server, pg, "GET", B + "/scenario")["kind"]
    seen = {}
    for k in [x for x in kinds if x != first] + [first]:       # každý scénář se opravdu přepne z jiného
        seen[k] = _pick(pg, server, k)
        assert seen[k]["kind"] == k, k
        assert seen[k]["sub"].strip() and seen[k]["note"].strip(), k
        assert seen[k]["rows"] >= 1 or k == "replay", k
    same = [(a, b) for i, a in enumerate(kinds) for b in kinds[i + 1:] if seen[a]["chart"] == seen[b]["chart"]]
    assert not same, f"chart did not change between scenarios: {same}"
    notes = {seen[k]["note"] for k in kinds}
    assert len(notes) == len(kinds), "scenario note is the same for two scenarios"


def test_simulation_length_manual_and_auto(tuning, server):
    pg = tuning
    kinds = _call(server, pg, "GET", B + "/scenario")["kinds"]
    _pick(pg, server, "sp" if "sp" in kinds else kinds[0])
    auto = pg.locator('[data-testid="scen-len-auto"]')
    assert auto.is_checked()
    base = _chart(pg)
    auto.uncheck()
    box = pg.locator('[data-testid="scen-len"]')
    cur = float(box.input_value().replace(",", "."))
    box.fill(str(round(cur / 2, 3)))
    box.blur()
    _until(lambda: _chart(pg) != base, 20)                     # poloviční délka = jiná časová osa
    auto.check()
    _until(lambda: _chart(pg) == base, 20)                     # zpět na automatickou délku


def test_scenario_survives_reload_and_loop_switch(tuning, server):
    pg = tuning
    kinds = _call(server, pg, "GET", B + "/scenario")["kinds"]
    k = next(x for x in kinds if x not in ("sp", "replay"))
    want = _pick(pg, server, k)
    pg.reload(wait_until="networkidle")
    pg.wait_for_selector('[data-testid="scen-kind"]', timeout=30000)
    pg.wait_for_selector('[data-testid="response"] svg path', timeout=30000)
    _until(lambda: pg.locator('[data-testid="scen-kind"]').input_value() == k)
    _until(lambda: _chart(pg) == want["chart"], 20)
    # druhá smyčka bez modelu a zpět: scénář první smyčky zůstane
    _call(server, pg, "POST", B + "/loops", {"name": "FIC100", "pv": "FI100.Pritok", "mv": "LIC101.MV"})
    n = len(_call(server, pg, "GET", B + "/loops")["loops"])
    _call(server, pg, "PUT", B + "/loops/active", {"index": n - 1})
    _call(server, pg, "PUT", B + "/loops/active", {"index": 0})
    pg.reload(wait_until="networkidle")
    pg.wait_for_selector('[data-testid="scen-kind"]', timeout=30000)
    _until(lambda: pg.locator('[data-testid="scen-kind"]').input_value() == k)
    assert _call(server, pg, "GET", B + "/scenario")["kind"] == k
