"""
Data › Trendy v novém rozhraní (E4-C) v prohlížeči: strom signálů ze dvou zdrojů s různým vzorkováním a posunem, panely
(canvas), rozvržení, kurzory A / B s odečtem, přehledový pruh, vypočtený signál, export PNG / CSV a označení úseku pro
Model. Potřebuje sestavené UI (cd frontend && npm run build) a podzáložku „Trendy“ v Data (bez ní se přeskočí;
PID_TRENDS_DIRECT=1 = Trendy jsou rovnou hlavní plocha Dat, pro lokální zkoušku bez navigace).
"""
import io
import json
import os
import re
import urllib.request

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("playwright.sync_api")
import test_frontend as _tf  # noqa: E402

TOKEN = _tf.TOKEN
server, page = _tf.server, _tf.page                      # fixtury serveru a prohlížeče


def _call(server, page, method, path, body=None, raw=None):
    wid = page.evaluate("sessionStorage.getItem('pid.wid')")
    data = raw if raw is not None else (None if body is None else json.dumps(body).encode())
    req = urllib.request.Request(server + "/api/v1" + path.format(wid=wid), method=method, data=data, headers={
        "X-PID-Token": TOKEN, "Content-Type": "application/octet-stream" if raw is not None else "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=120).read() or b"null")


def _csv(df):
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode()


@pytest.fixture(scope="module")
def trends(page, server):
    """Dva zdroje: a.csv (1 s, smyčka TIC102) a b.csv (5 s, začíná o 10 min dřív, FIC205 + tlak); otevřené Trendy."""
    t = np.arange(0, 3600.0)
    sp = 80 + 5 * np.sign(np.sin(t / 900))
    pv = sp + 2 * np.sin(t / 60)
    mv = 50 + 10 * np.sin(t / 300)
    t0 = pd.Timestamp("2026-10-08 09:00:00")
    a = pd.DataFrame({"Time": t0 + pd.to_timedelta(t, unit="s"), "TIC102.PV": pv, "TIC102.SP": sp, "TIC102.MV": mv})
    t5 = np.arange(-600, 3600 + 600, 5.0)
    b = pd.DataFrame({"Time": t0 + pd.to_timedelta(t5, unit="s"), "FIC205.PV [t/h]": 45 + 3 * np.sin(t5 / 200),
                      "PI201 [bar]": 8 + 0.5 * np.sin(t5 / 700)})
    for name, df in (("a.csv", a), ("b.csv", b)):
        _call(server, page, "POST", f"/workspaces/{{wid}}/sources?name={name}&timezone=UTC", raw=_csv(df))
    _call(server, page, "POST", "/workspaces/{wid}/loops/suggest", {"apply": True})
    page.reload(wait_until="networkidle")
    page.wait_for_selector('[data-testid="api-ok"]', timeout=20000)
    page.locator('[data-tab="data"]').click()
    if not os.environ.get("PID_TRENDS_DIRECT"):
        nav = page.get_by_role("button", name=re.compile(r"^(Trendy|Trends)$")).or_(page.get_by_role("link", name=re.compile(r"^(Trendy|Trends)$")))
        if not nav.count():
            pytest.skip("podzáložka Trendy v Data není v tomto stromu (navigaci dodává E4-A)")
        nav.first.click()
    page.wait_for_selector('[data-testid="trends-main"]', timeout=20000)
    page.wait_for_selector('[data-testid="trd-panel"]', timeout=20000)
    return page


def _ink(page, i=0):
    """Počet nepřehledných (nenulová alfa) pixelů canvasu i-tého panelu."""
    return page.evaluate("""(i) => { const c = document.querySelectorAll('[data-testid="trd-canvas"]')[i];
      const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data; let n = 0;
      for (let k = 3; k < d.length; k += 4) if (d[k] > 0) n++; return n; }""", i)


def _panels(page):
    return page.evaluate("() => [...document.querySelectorAll('[data-testid=\"trd-panel\"]')].map(p => p.dataset.refs)")


def test_tree_lists_all_signals_of_all_sources(trends):
    tree = trends.locator('[data-testid="trd-tree"]')
    labels = [tree.locator("input[type=checkbox]").nth(i).get_attribute("aria-label") for i in range(tree.locator("input[type=checkbox]").count())]
    assert {"s1:TIC102.PV", "s1:TIC102.SP", "s1:TIC102.MV", "s2:FIC205.PV [t/h]", "s2:PI201 [bar]"} <= set(labels)
    trends.locator('[data-testid="trd-by"] button').nth(1).click()
    assert trends.locator('[data-testid="trd-tree"] .trd-gh').count() == 2          # a.csv, b.csv
    trends.locator('[data-testid="trd-by"] button').nth(0).click()
    trends.locator('[data-testid="trd-search"]').fill("pi201")
    assert trends.locator('[data-testid="trd-tree"] input[type=checkbox]').count() == 1
    trends.locator('[data-testid="trd-search"]').fill("")


def test_signals_render_and_layout_modes(trends):
    assert _panels(trends) and "s1:TIC102.PV" in _panels(trends)[0]
    assert _ink(trends) > 500                                                      # na canvasu jsou průběhy
    assert trends.locator("[data-testid=trd-note]").inner_text().strip() != ""
    # přidání signálu z druhého zdroje (jiné vzorkování, posun) a rozvržení
    trends.locator('[aria-label="s2:FIC205.PV [t/h]"]').check()
    trends.locator('[aria-label="s2:PI201 [bar]"]').check()
    seg = trends.locator('[data-testid="trd-layout"] button')
    seg.nth(0).click()
    trends.wait_for_function("() => document.querySelectorAll('[data-testid=\"trd-panel\"]').length === 1")
    assert len(_panels(trends)[0].split(",")) == 5
    seg.nth(2).click()                                                             # podle veličiny: °C-like T, %, t/h, bar
    trends.wait_for_function("() => document.querySelectorAll('[data-testid=\"trd-panel\"]').length >= 3")
    titles = trends.evaluate("() => [...document.querySelectorAll('[data-testid=\"trd-panel\"]')].map(p => p.dataset.title)")
    assert "[t/h]" in titles and "[bar]" in titles and "[%]" in titles
    seg.nth(1).click()                                                             # podle smyčky
    trends.wait_for_function("() => document.querySelectorAll('[data-testid=\"trd-panel\"]').length >= 2")
    assert all(_ink(trends, i) > 100 for i in range(len(_panels(trends))))


def test_cursors_readout_zoom_and_navigator(trends):
    trends.locator('[data-testid="trd-ab"]').click()
    rows = trends.locator('[data-testid="trd-readout"] tbody tr')
    rows.first.wait_for()
    cell = lambda r, c: rows.nth(r).locator(f'td[data-c="{c}"]').inner_text()          # noqa: E731
    a, b, d = (float(cell(0, k).replace(",", ".")) for k in "abd")
    assert d == pytest.approx(b - a, abs=0.05 + 1e-3 * abs(b))
    assert trends.locator('[data-testid="trd-mark"]').inner_text().count("→") == 1
    # klik v grafu přesune kurzor A, readout se přepočítá
    box = trends.locator('[data-testid="trd-canvas"]').first.bounding_box()
    trends.mouse.click(box["x"] + box["width"] * 0.2, box["y"] + box["height"] / 2)
    trends.wait_for_function("(a) => document.querySelector('[data-testid=\"trd-readout\"] td[data-c=\"a\"]').innerText !== a", arg=cell(0, "a"))
    # zoom na výběr A–B zúží okno zoomu v přehledovém pruhu
    full = trends.locator('[data-testid="trd-nwin"]').bounding_box()["width"]
    trends.locator('[data-testid="trd-zoom"] button').nth(1).click()
    trends.wait_for_function("(w) => document.querySelector('[data-testid=\"trd-nwin\"]').getBoundingClientRect().width < w * 0.9", arg=full)
    trends.locator('[data-testid="trd-zoom"] button').nth(0).click()
    trends.wait_for_function("(w) => document.querySelector('[data-testid=\"trd-nwin\"]').getBoundingClientRect().width > w * 0.95", arg=full)
    # kolečko zoomuje
    trends.mouse.move(box["x"] + box["width"] / 2, box["y"] + 40)
    trends.mouse.wheel(0, -400)
    trends.wait_for_function("(w) => document.querySelector('[data-testid=\"trd-nwin\"]').getBoundingClientRect().width < w * 0.9", arg=full)
    trends.locator('[data-testid="trd-zoom"] button').nth(0).click()


def test_computed_signal(trends):
    trends.locator('[data-testid="trd-calc-open"]').click()
    trends.locator('[data-testid="trd-calc-expr"]').fill("[s1:TIC102.SP] - [s1:NOPE]")
    assert trends.locator('[data-testid="trd-calc-err"]').is_visible()
    assert trends.locator('[data-testid="trd-calc-add"]').is_disabled()
    trends.locator('[data-testid="trd-calc-expr"]').fill("[s1:TIC102.SP] - [s1:TIC102.PV]")
    trends.locator('[data-testid="trd-calc-add"]').click()
    trends.wait_for_selector('[data-testid="trd-calc-row"]')
    trends.wait_for_function("() => [...document.querySelectorAll('[data-testid=\"trd-readout\"] tbody tr')].some(r => r.dataset.ref.startsWith('calc:'))")
    row = trends.locator('[data-testid="trd-readout"] tbody tr[data-ref^="calc:"]')
    assert row.locator('td[data-c="a"]').inner_text() not in ("", "–")


def test_exports_csv_and_png(trends):
    with trends.expect_download() as dl:
        trends.locator('[data-testid="trd-csv"]').click()
    text = open(dl.value.path(), encoding="utf-8-sig").read()
    head = text.split("\n")[0]
    assert head.startswith("t [s];clock;") and "s1:TIC102.PV" in head and "e" in head.split(";")
    assert len(text.split("\n")) > 100
    with trends.expect_download() as dl:
        trends.locator('[data-testid="trd-png"]').click()
    assert open(dl.value.path(), "rb").read(8) == b"\x89PNG\r\n\x1a\n"


def test_mark_range_for_model(trends, server):
    wid = trends.evaluate("sessionStorage.getItem('pid.wid')")
    before = _call(server, trends, "GET", "/workspaces/{wid}")["rng"]
    trends.locator('[data-testid="trd-mark-model"]').click()
    trends.wait_for_selector('[data-testid="trd-mark-msg"]')
    after = _call(server, trends, "GET", "/workspaces/{wid}")["rng"]
    assert wid and after != before and 0 <= after[0] < after[1]
    assert trends.locator('[data-testid="trd-mark-diag"]').is_enabled()


def test_every_control_has_help(trends):
    """Každý ovládací prvek s popiskem v Trendech má „?“ nebo title."""
    missing = trends.evaluate("""() => [...document.querySelectorAll('[data-testid=trd-tools] .trd-tg, [data-testid=trd-tools] label.trd-chk')]
      .filter(g => !g.querySelector('button.qm') && !g.title).map(g => g.innerText)""")
    assert missing == []
