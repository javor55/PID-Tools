"""
TICKET-008: přístupnost Ladění, Modelu a Kvality dat – pole bez přístupného názvu, kontrast `.tn-faint`,
výběr řádku „All methods“ klávesnicí a popisky grafů SVG. Potřebuje sestavené UI (cd frontend && npm run build).
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

# Pole bez přístupného názvu: bez aria-label / aria-labelledby, mimo <label> a bez label[for];
# pole ve sdílených modulech JS (.pidv, .viewer-host, .trend-host) se vynechávají (TICKET-009).
PROBE = """() => [...document.querySelectorAll('input:not([type=hidden]), select, textarea')].filter(e => {
  if (e.closest('.pidv, .viewer-host, .trend-host')) return false;
  if ((e.getAttribute('aria-label') || '').trim() || e.getAttribute('aria-labelledby')) return false;
  if (e.closest('label')) return false;
  if (e.id && document.querySelector('label[for="' + CSS.escape(e.id) + '"]')) return false;
  return true;
}).map(e => e.tagName.toLowerCase() + (e.type ? '[' + e.type + ']' : '') + ' ' + (e.dataset.testid || e.className || e.placeholder || ''))"""


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
def ready(page, server):
    """Ukázková data + identifikace, pak záložka Ladění."""
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
    return page


def _view(pg, value):
    pg.locator(f'[data-testid="tun-view"] [data-value="{value}"]').click()


CONTRAST = """() => {
  const rgb = (c) => { const m = c.match(/[\\d.]+/g).map(Number); return { c: m.slice(0, 3), a: m.length > 3 ? m[3] : 1 }; };
  const lum = (c) => { const [r, g, b] = c.map((v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; });
    return 0.2126 * r + 0.7152 * g + 0.0722 * b; };
  const bgOf = (el) => { for (let e = el; e; e = e.parentElement) { const k = rgb(getComputedStyle(e).backgroundColor);
    if (k.a > 0.99) return k.c; } return [255, 255, 255]; };
  return [...document.querySelectorAll('.tn-faint')].map((el) => {
    const a = lum(rgb(getComputedStyle(el).color).c), b = lum(bgOf(el));
    return +((Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05)).toFixed(2); });
}"""


def _nameless(pg):
    return pg.evaluate(PROBE)


def test_tuning_fields_have_names(ready):
    pg = ready
    for v in ("time", "freq", "all"):
        _view(pg, v)
        pg.wait_for_timeout(800)
        assert _nameless(pg) == [], f"Ladění / {v}"


def test_model_and_quality_fields_have_names(ready):
    pg = ready
    pg.locator('[data-tab="model"]').click()
    pg.wait_for_timeout(1200)
    assert _nameless(pg) == [], "Model"
    pg.locator('[data-tab="data"]').click()
    pg.locator('[data-sub="quality"]').click()
    pg.wait_for_selector('[data-testid="dq-segs"], [data-testid="dq-event"]', timeout=30000, state="attached")
    assert _nameless(pg) == [], "Data / Kvalita dat"


def test_faint_text_contrast(ready):
    pg = ready
    pg.locator('[data-tab="tuning"]').click()
    _view(pg, "all")
    # Na stavu tabulky nezáviset: řádky „calculated when clicked“ zmizí, když dřívější test (sdílená relace) metody
    # spočítá, a ostatní .tn-faint bývají ve sbalených kartách. Proto vlastní vzorek .tn-faint v kartě Ladění.
    pg.wait_for_selector(".tn-card", timeout=30000)
    pg.evaluate("""() => { const c = document.querySelector('.tn-card'); const e = document.createElement('span');
      e.className = 'tn-faint'; e.dataset.probe = '1'; e.textContent = 'probe'; c.appendChild(e); }""")
    for theme in ("light", "dark"):
        pg.evaluate(f"document.documentElement.dataset.theme = '{theme}'")
        ratios = pg.evaluate(CONTRAST)
        assert ratios, "žádný prvek .tn-faint"
        print("kontrast .tn-faint", theme, ratios[:3])
        assert min(ratios) >= 4.5, (theme, ratios)
    pg.evaluate("document.documentElement.dataset.theme = 'light'")
    pg.evaluate("() => document.querySelectorAll('[data-probe]').forEach((e) => e.remove())")


def test_all_methods_row_keyboard(ready):
    pg = ready
    pg.locator('[data-tab="tuning"]').click()
    _view(pg, "time")
    pg.locator('[data-testid="cmp-run"]').click()          # „Spočítat vše“ je v pohledu Scénář v čase
    pg.wait_for_selector('[data-testid="cmp-row"]', timeout=120000)
    _view(pg, "all")
    pg.wait_for_selector('[data-testid="cmp-row"]')
    rows = pg.locator('[data-testid="cmp-row"]')
    n = rows.count()
    assert n >= 3
    for k in range(n):                                       # všechny řádky jsou v pořadí Tab
        assert rows.nth(k).get_attribute("tabindex") == "0"
    k = next(i for i in range(n) if "sel" not in (rows.nth(i).get_attribute("class") or "").split())
    row = rows.nth(k)
    row.focus()
    assert pg.evaluate("document.activeElement.dataset.testid") == "cmp-row"
    assert row.get_attribute("aria-selected") == "false"
    pg.keyboard.press("Enter")                               # stejný výsledek jako klik: řádek se stane aktuálním (sel, ✓)
    pg.wait_for_function("(k) => document.querySelectorAll('[data-testid=\"cmp-row\"]')[k].classList.contains('sel')", arg=k)
    assert rows.nth(k).get_attribute("aria-selected") == "true"
    assert rows.nth(k).locator(".tn-ok").count() == 1
    assert pg.locator('[data-testid="cmp-row"].sel').count() == 1


def test_frequency_charts_have_labels(ready):
    pg = ready
    pg.locator('[data-tab="tuning"]').click()
    _view(pg, "freq")
    pg.wait_for_selector("main figure.chart svg", timeout=30000)
    info = pg.evaluate("""() => [...document.querySelectorAll('main figure.chart svg')].map((s) =>
      [s.getAttribute('role'), (s.getAttribute('aria-label') || '').trim()])""")
    assert info, "žádný graf"
    for role, label in info:
        assert role == "img" and label, info
