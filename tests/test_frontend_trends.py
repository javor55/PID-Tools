"""
Data › Trendy na sdíleném prohlížeči (viewer.js) v prohlížeči: signály dvou zdrojů s různým vzorkováním a posunem na
společné ose, seznam signálů v pravém panelu ve skupinách podle smyček / souborů, rozvržení panelů, nezávislé časové
(A / B) a hodnotové (Y₁ / Y₂) kurzory s odečtem, export PNG / CSV a vyznačení úseku A–B pro Model.
Potřebuje sestavené UI (cd frontend && npm run build).
"""
import io
import json
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
    page.locator('[data-sub="trends"]').click()
    page.wait_for_selector('[data-testid="trends-main"]', timeout=20000)
    page.wait_for_selector('[data-testid="trd-viewer"] .pidv-panel canvas', timeout=30000)
    page.wait_for_timeout(500)
    return page


def _panels(page):
    """Signály v panelech prohlížeče (z jeho stavu)."""
    return page.evaluate("() => window.__pidView.trends_view.state().panels.map(p => p.sigs)")


def test_signals_of_both_sources_on_common_axis(trends, server):
    """Balík /signals/all: všechny sloupce obou zdrojů, b.csv začíná o 10 min dřív → společná osa od jeho začátku."""
    from pidtools.app import signalpack
    wid = trends.evaluate("sessionStorage.getItem('pid.wid')")
    req = urllib.request.Request(f"{server}/api/v1/workspaces/{wid}/signals/all", headers={"X-PID-Token": TOKEN})
    meta, out = signalpack.unframe(urllib.request.urlopen(req, timeout=60).read())
    assert set(meta["refs"].values()) >= {"s1:TIC102.PV", "s1:TIC102.SP", "s1:TIC102.MV", "s2:FIC205.PV [t/h]", "s2:PI201 [bar]"}
    t_pv, t_pi = out["TIC102.PV"][0], out["PI201 [bar]"][0]
    assert t_pi[0] == pytest.approx(0.0) and t_pv[0] == pytest.approx(600.0)       # a.csv o 10 min později
    assert np.diff(t_pi[:3]).tolist() == [5.0, 5.0] and len(t_pv) == 3600


def test_signal_list_in_side_panel_grouped(trends):
    tree = trends.locator('[data-testid="trd-tree"]')
    assert tree.locator(".pidv-list").count() == 1                                  # seznam prohlížeče je v pravém panelu
    assert trends.locator('[data-testid="trd-viewer"] .pidv-list').count() == 0
    heads = tree.locator(".pidv-ghead").all_inner_texts()
    assert any("TIC102" in h for h in heads) and any("No loop" in h for h in heads)     # smyčka a zbylé sloupce
    trends.locator('[data-testid="trd-by"] button').nth(1).click()                  # podle souborů
    trends.wait_for_function("() => [...document.querySelectorAll('[data-testid=\"trd-tree\"] .pidv-ghead')].some(h => h.innerText.includes('b.csv'))")
    trends.locator('[data-testid="trd-by"] button').nth(0).click()
    tree.locator("input[type=search]").fill("pi201")
    assert tree.locator(".pidv-sig").count() == 1
    tree.locator("input[type=search]").fill("")


def test_layout_presets(trends):
    """Panel na smyčku (výchozí), jeden panel, panel na veličinu; PV a SP stejné veličiny sdílí osu."""
    p = _panels(trends)
    assert any("TIC102.PV" in x and "TIC102.SP" in x for x in p)
    seg = trends.locator('[data-testid="trd-layout"] button')
    seg.nth(0).click()
    trends.wait_for_function("() => window.__pidView.trends_view.state().panels.length === 1")
    seg.nth(2).click()
    trends.wait_for_function("() => window.__pidView.trends_view.state().panels.length >= 2")
    seg.nth(1).click()                                                              # jedna úplná smyčka → jeden panel
    trends.wait_for_function("() => window.__pidView.trends_view.state().panels.length === 1")
    n_axes = trends.evaluate("() => document.querySelectorAll('[data-testid=\"trd-viewer\"] .pidv-panel').length")
    assert n_axes == len(_panels(trends))


def test_independent_cursors_and_readout(trends):
    bar = trends.locator('[data-testid="trd-viewer"] .pidv-bar')
    bar.locator("[data-a=cur]").click()
    trends.wait_for_selector('[data-testid="trd-viewer"] .pidv-read table')
    st = trends.evaluate("() => window.__pidView.trends_view.state()")
    assert st["cur"]["on"] and not st["hc"]["on"]
    bar.locator("[data-a=hcur]").click()
    st = trends.evaluate("() => window.__pidView.trends_view.state()")
    assert st["cur"]["on"] and st["hc"]["on"] and st["hc"]["sig"].endswith("PV")    # hodnotové kurzory u PV
    trends.wait_for_function("() => document.querySelector('[data-testid=\"trd-viewer\"] .pidv-read').innerText.includes('Y₂')")
    read = trends.locator('[data-testid="trd-viewer"] .pidv-read').first.inner_text()
    assert "Y₁" in read and "TIC102.PV" in read
    # klik = A, Shift+klik = B, Alt+klik = Y₁ (časové kurzory zapnuté)
    cv = trends.locator('[data-testid="trd-viewer"] .pidv-panel canvas').last
    box = cv.bounding_box()
    trends.mouse.click(box["x"] + box["width"] * 0.3, box["y"] + box["height"] * 0.5)
    trends.keyboard.down("Shift")
    trends.mouse.click(box["x"] + box["width"] * 0.7, box["y"] + box["height"] * 0.5)
    trends.keyboard.up("Shift")
    st = trends.evaluate("() => window.__pidView.trends_view.state()")
    assert st["cur"]["a"] < st["cur"]["b"]
    # vypnutí časových: hodnotové zůstanou
    bar.locator("[data-a=cur]").click()
    st = trends.evaluate("() => window.__pidView.trends_view.state()")
    assert not st["cur"]["on"] and st["hc"]["on"]
    bar.locator("[data-a=hcur]").click()


def test_exports_csv_and_png(trends):
    bar = trends.locator('[data-testid="trd-viewer"] .pidv-bar')
    with trends.expect_download() as dl:
        bar.locator("[data-a=csv_view]").click()
    text = open(dl.value.path(), encoding="utf-8-sig").read()
    assert "TIC102.PV" in text.split("\n")[0] and len(text.split("\n")) > 100
    with trends.expect_download() as dl:
        bar.locator("[data-a=png]").click()
    assert open(dl.value.path(), "rb").read(8) == b"\x89PNG\r\n\x1a\n"


def test_mark_range_for_model(trends, server):
    if trends.evaluate("() => window.__pidView.trends_view.state().cur.on"):          # kurzory z předchozího testu vypnout
        trends.locator('[data-testid="trd-viewer"] .pidv-bar [data-a=cur]').click()
    trends.locator('[data-testid="trd-mark-model"]').click()                      # bez kurzorů: hláška
    trends.wait_for_selector('[data-testid="trd-mark-msg"].trd-err')
    trends.locator('[data-testid="trd-viewer"] .pidv-bar [data-a=cur]').click()
    before = _call(server, trends, "GET", "/workspaces/{wid}")["rng"]
    st = trends.evaluate("() => window.__pidView.trends_view.state().cur")
    trends.locator('[data-testid="trd-mark-model"]').click()
    trends.wait_for_selector('[data-testid="trd-mark-msg"].trd-ok')
    after = _call(server, trends, "GET", "/workspaces/{wid}")["rng"]
    assert after != before and 0 <= after[0] < after[1]
    assert after[1] - after[0] == pytest.approx(abs(st["b"] - st["a"]), abs=2)
    assert trends.locator('[data-testid="trd-mark-diag"]').is_enabled()


def test_every_control_has_help(trends):
    """Každý ovládací prvek s popiskem v Trendech má „?“ nebo title."""
    missing = trends.evaluate("""() => [...document.querySelectorAll('[data-testid=trd-tools] .trd-tg, [data-testid=trends-side] label.trd-chk')]
      .filter(g => !g.querySelector('button.qm') && !g.title).map(g => g.innerText)""")
    assert missing == []
