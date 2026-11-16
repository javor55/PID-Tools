"""
FEATURE-004: odečet hodnot a export u grafů LineChart, ověřeno v APC › Feedforward (graf `ff-pv`).
Najetí myší → tabulka odečtu, dva kliky → Δ, nabídka „Save CSV“ (sloupec na každou viditelnou řadu), skrytí řady v legendě
a rozměry grafu beze změny. Potřebuje sestavené UI (cd frontend && npm run build).
"""
import csv
import io
import json
import time
import urllib.request

import pytest

pytest.importorskip("playwright.sync_api")
import test_frontend as _tf  # noqa: E402

TOKEN = _tf.TOKEN
server, page = _tf.server, _tf.page                      # fixtury serveru a prohlížeče
B = "/api/v1/workspaces/{wid}"
CHART = '[data-testid="ff-pv"]'


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
def ff(page, server):
    """Ukázková data + identifikace, APC › Feedforward se zapnutou dynamickou dopřednou vazbou; vrací stránku."""
    page.locator('[data-tab="data"]').click()
    page.locator('[data-sub="sources"]').click()
    page.locator('[data-testid="src-demo"]').click()
    page.wait_for_function("() => (document.querySelector('[data-testid=\"data-info\"]')||{}).innerText?.includes('demo')")
    _call(server, page, "PATCH", B + "/settings", {"chosen": ["P1D", "I1D"]})
    j = _call(server, page, "POST", B + "/identify", {})
    _until(lambda: _call(server, page, "GET", f"/api/v1/jobs/{j['id']}")["state"] not in ("queued", "running"), 120)
    page.reload(wait_until="networkidle")
    page.wait_for_selector('[data-testid="api-ok"]', timeout=20000)
    page.locator('[data-tab="apc"]').click()
    page.wait_for_selector('[data-testid="apc-techs"]', timeout=20000)
    page.locator('[data-testid="apc-tech-ff"]').click()
    info = _call(server, page, "GET", B + "/apc/ff")
    if not info["dists"]:
        pytest.skip("ukázková data nemají poruchu pro dopřednou vazbu")
    page.wait_for_selector('[data-testid="ff-dist-0"]')
    page.locator('[data-testid="ff-use-0"]').click()
    page.locator('[data-testid="ff-dyn-0"] [data-value="dyn"]').click()
    page.wait_for_selector(f"{CHART} path", timeout=30000, state="attached")
    page.wait_for_selector('[data-testid="ff-kpis-dynamic-iae"]', timeout=30000)
    return page


def _plot_point(pg, frac=0.5):
    """Souřadnice na ploše grafu (střed ve vodorovném směru) v px stránky."""
    b = pg.locator(f"{CHART} svg").bounding_box()
    return b["x"] + 52 + frac * (b["width"] - 62), b["y"] + b["height"] / 2


def _csv(pg):
    pg.locator(f'{CHART} [data-testid="lc-menu"]').click()
    with pg.expect_download() as dl:
        pg.locator(f'{CHART} [role="menuitem"]', has_text="CSV").click()
    path = dl.value.path()
    assert dl.value.suggested_filename == "ff-pv.csv"
    return list(csv.reader(io.StringIO(open(path, encoding="utf-8").read())))


def test_chart_size_unchanged_by_tools(ff):
    pg = ff
    h0 = pg.evaluate("(s) => document.querySelector(s + ' svg').getBoundingClientRect().height", CHART)
    assert h0 == 220                                        # `height={220}` grafu ff-pv; nástroje výšku nemění
    pg.mouse.move(*_plot_point(pg))
    pg.wait_for_selector('[data-testid="lc-readout"]')
    assert pg.evaluate("(s) => document.querySelector(s + ' svg').getBoundingClientRect().height", CHART) == h0
    assert pg.evaluate("(s) => document.querySelector(s).getBoundingClientRect().height", CHART) >= h0
    pg.mouse.move(5, 5)


def test_readout_on_hover(ff):
    pg = ff
    pg.mouse.move(*_plot_point(pg))
    t = pg.locator(f'{CHART} [data-testid="lc-readout"]')
    t.wait_for()
    rows = pg.locator(f'{CHART} [data-testid="lc-readout"] tbody tr')
    n_leg = pg.locator(f"{CHART} figcaption button").count()
    assert rows.count() == 1 + n_leg                         # řádek x + řada za každou položku legendy
    text = t.inner_text()
    assert any(ch.isdigit() for ch in text)
    # tabulka zůstává uvnitř grafu
    bt, bf = t.bounding_box(), pg.locator(f"{CHART} svg").bounding_box()
    assert bt["x"] >= bf["x"] - 1 and bt["x"] + bt["width"] <= bf["x"] + bf["width"] + 1
    assert bt["y"] >= bf["y"] - 1 and bt["y"] + bt["height"] <= bf["y"] + bf["height"] + 1


def test_two_clicks_give_delta_and_esc_clears(ff):
    pg = ff
    pg.mouse.click(*_plot_point(pg, 0.25))
    pg.mouse.click(*_plot_point(pg, 0.6))
    pg.wait_for_selector('[data-testid="lc-dx"]')
    xa = float(pg.locator('[data-testid="lc-x-0"]').inner_text())
    xb = float(pg.locator('[data-testid="lc-x-1"]').inner_text())
    dx = float(pg.locator('[data-testid="lc-dx"]').inner_text())
    assert xb > xa and abs(dx - (xb - xa)) <= 1e-3 * max(1.0, abs(dx))
    assert pg.locator('[data-testid^="lc-dy-"]').count() >= 1
    ya, yb = (float(pg.locator('[data-testid="lc-val-0-%d"]' % i).inner_text()) for i in (0, 1))
    dy = float(pg.locator('[data-testid="lc-dy-0"]').inner_text())
    assert abs(dy - (yb - ya)) <= 2e-3 * max(1.0, abs(dy), abs(ya), abs(yb))
    pg.keyboard.press("Escape")
    pg.mouse.move(5, 5)
    pg.wait_for_selector('[data-testid="lc-readout"]', state="detached")


def test_save_csv_and_hidden_series(ff):
    pg = ff
    legend = pg.locator(f"{CHART} figcaption button")
    n = legend.count()
    assert n >= 2
    rows = _csv(pg)
    assert len(rows[0]) == 1 + n and len(rows) > 10
    assert all(len(r) == 1 + n for r in rows)
    assert float(rows[1][0]) <= float(rows[-1][0])           # x vzestupně
    hidden_name = legend.nth(1).inner_text().strip()
    legend.nth(1).click()
    assert legend.nth(1).get_attribute("aria-pressed") == "false"
    rows2 = _csv(pg)
    assert len(rows2[0]) == n and hidden_name not in rows2[0]
    assert len(rows2) > 10
    assert pg.locator(f"{CHART} svg path").count() == n - 1
    legend.nth(1).click()
    assert pg.locator(f"{CHART} svg path").count() == n


def test_save_png(ff):
    pg = ff
    pg.locator(f'{CHART} [data-testid="lc-menu"]').click()
    with pg.expect_download() as dl:
        pg.locator(f'{CHART} [role="menuitem"]', has_text="PNG").click()
    data = open(dl.value.path(), "rb").read()
    assert data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) > 2000
    assert dl.value.suggested_filename == "ff-pv.png"
