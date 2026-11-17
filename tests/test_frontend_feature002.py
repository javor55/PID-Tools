"""
FEATURE-002: kopírování parametrů a tabulek do schránky (Ladění). Ukázková data + identifikace přes API,
schránka se čte přes navigator.clipboard.readText(). Potřebuje sestavené UI (cd frontend && npm run build).
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
    page.context.grant_permissions(["clipboard-read", "clipboard-write"], origin=server)
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
    page.wait_for_selector('[data-testid="sets"]', timeout=30000)
    page.wait_for_selector('[data-testid="kpi-card"] table tbody tr', timeout=30000)
    return page


def _clip(pg):
    return pg.evaluate("navigator.clipboard.readText()")


def _num(x):
    return f"{float(f'{x:.6g}'):g}"


def test_copy_set1(tuning, server):
    pg = tuning
    info = _call(server, pg, "GET", B + "/tuning")
    s1 = info["sets"][0]
    assert not s1["placeholder"]
    st = _call(server, pg, "GET", B + "/settings")
    pg.evaluate("navigator.clipboard.writeText('')")
    pg.locator('[data-testid="copy-set-1"]').click()
    txt = _until(lambda: _clip(pg))
    head, params = txt.split(": ", 1)
    ws = _call(server, pg, "GET", B)
    tag = (st.get("loop_tag") or "").strip() or ws["pv"]
    assert head == f"{tag} · {info['controller']['block']}", head
    parts = dict(p.split(" = ") for p in params.split("; "))
    for q in info["tuning_params"]:
        unit = f" {q['unit']}" if q.get("unit") and q["unit"] != "-" else ""
        assert parts[q["name"]] == _num(s1["values"][q["key"]]) + unit, (parts, q)
    assert any(q["name"].upper() == "TI" and q.get("unit") == "s" for q in info["tuning_params"])
    assert "Gain" in parts and "TI" in parts and "TD" in parts and parts["TI"].endswith(" s")
    pg.wait_for_selector("text=Copied to the clipboard", timeout=5000)


def test_set2_disabled_until_entered(tuning, server):
    pg = tuning
    info = _call(server, pg, "GET", B + "/tuning")
    assert info["sets"][1]["placeholder"]
    assert pg.locator('[data-testid="copy-set-2"]').is_disabled()
    assert not pg.locator('[data-testid="copy-set-1"]').is_disabled()


def test_copy_table_kpi(tuning):
    pg = tuning
    pg.evaluate("navigator.clipboard.writeText('')")
    pg.locator('[data-testid="kpi-card"] [data-testid="copy-table"]').click()
    txt = _until(lambda: _clip(pg))
    lines = txt.split("\n")
    n = pg.evaluate("""() => { const t = document.querySelector('[data-testid="kpis"]');
      return [...t.querySelectorAll('thead tr, tbody tr')].filter(r => getComputedStyle(r).display !== 'none').length; }""")
    assert len(lines) == n and n > 2
    heads = pg.evaluate("[...document.querySelectorAll('[data-testid=\"kpis\"] thead th')].map(t => t.innerText.trim())")
    assert lines[0].split("\t") == heads
    assert all("\t" in ln for ln in lines)


def test_keyboard_and_labels(tuning):
    pg = tuning
    for tid, label in (("copy-sug", "Copy Suggestion"), ("copy-set-1", "Copy Set 1"), ("copy-set-2", "Copy Set 2")):
        assert pg.locator(f'[data-testid="{tid}"]').get_attribute("aria-label") == label
    assert pg.locator('[data-testid="kpi-card"] [data-testid="copy-table"]').get_attribute("aria-label")
    pg.evaluate("navigator.clipboard.writeText('')")
    pg.locator('[data-testid="copy-set-1"]').focus()
    assert pg.evaluate("document.activeElement.getAttribute('data-testid')") == "copy-set-1"
    pg.keyboard.press("Enter")
    txt = _until(lambda: _clip(pg))
    assert "Gain" in txt
