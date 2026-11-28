"""
Kompaktní vložené grafy (Model › Identifikace, Data › Diagnostika): lišta má jeden řádek, seznam signálů je ve výchozím stavu
skrytý a graf je přes celou šířku; přepínač „Nástroje grafu“ zanikl (nahradily ho rozbalovací nabídky, jejich chování je
v test_frontend_chartmenus.py). Kolečko a kurzory fungují se zavřenými nabídkami, zapnuté kurzory ukazuje tlačítko Kurzory,
rozložení uložená před zavedením skrytého seznamu se načtou beze změny chování. Data › Trendy zůstávají nekompaktní
(seznam signálů vidět hned). Potřebuje sestavené UI (cd frontend && npm run build).
"""
import json
import os

import pytest

pytest.importorskip("playwright.sync_api")
import test_frontend as _tf  # noqa: E402
from test_frontend_diagchart import D, _open_diag  # noqa: E402
from test_frontend_modelchart import B, M, _call, _list, _menu, _open_model, _until  # noqa: E402

server, page = _tf.server, _tf.page                      # fixtury serveru a prohlížeče
ONE_ROW = 48                                             # nejvýše tolik px: jeden řádek lišty (8 + řádek + 8)
SHOT = os.environ.get("CHARTTOOLS_SHOT")                 # složka pro snímky obrazovky (jen ruční kontrola)


@pytest.fixture(scope="module")
def chart(page, server):
    """Demo a identifikovaný model; otevřený Model › Identifikace."""
    page.locator('[data-tab="data"]').click()
    page.locator('[data-sub="sources"]').click()
    page.locator('[data-testid="src-demo"]').click()
    page.wait_for_function("() => (document.querySelector('[data-testid=\"data-info\"]')||{}).innerText?.includes('demo')")
    _call(server, page, "PATCH", B + "/settings", {"chosen": ["P1D", "I1D"], "win_mode": "common"})
    j = _call(server, page, "POST", B + "/identify", {})
    _until(lambda: _call(server, page, "GET", f"/api/v1/jobs/{j['id']}")["state"] not in ("queued", "running"), 120)
    page.reload(wait_until="networkidle")
    page.wait_for_selector('[data-testid="api-ok"]', timeout=20000)
    _open_model(page)
    return page


def _reload_to(pg, opener):
    pg.reload(wait_until="networkidle")
    pg.wait_for_selector('[data-testid="api-ok"]', timeout=20000)
    opener(pg)


def _bar_h(pg, root):
    return pg.evaluate("s => document.querySelector(s + ' .pidv-bar').getBoundingClientRect().height", root)


def _default_checks(pg, root):
    """Výchozí stav kompaktního grafu: jeden řádek, žádný přepínač nástrojů, seznam signálů skrytý, všechny nabídky zavřené."""
    for tid in ("vw-tools", "vw-tools-panel", "vw-active"):
        assert pg.locator(f'{root} [data-testid="{tid}"]').count() == 0, tid       # přepínač nástrojů zanikl
    assert pg.locator(f'{root} .pidv-bar [data-testid^="vw-m-"][aria-expanded="true"]').count() == 0
    assert pg.locator(f'{root} [data-testid="vw-menu"]').count() == 0
    assert pg.locator(f"{root} .pidv-list").count() == 0                          # seznam signálů je skrytý
    assert _bar_h(pg, root) <= ONE_ROW, _bar_h(pg, root)                          # lišta má jeden řádek


def test_model_row_and_full_width(chart, server):
    _default_checks(chart, M)
    bar = chart.locator(f"{M} .pidv-bar")
    assert bar.locator('[data-testid="mw-mode"]').is_visible() and bar.locator('[data-testid="mw-zoom-win"]').is_visible()
    assert bar.locator('[data-testid="mw-resid"]').count() == 0                    # rezidua jsou až v nabídce Zobrazení
    assert chart.locator(f'{M} [data-testid="mw-model"]').count() == 0             # části modelu až v nabídce
    pl = chart.locator(f"{M} .pidv-plots").bounding_box()
    body = chart.locator(f"{M} .pidv-body").bounding_box()
    assert abs(pl["width"] - body["width"]) < 2                                    # graf přes celou šířku (bez sloupce seznamu)
    if SHOT:
        chart.locator(M).screenshot(path=os.path.join(SHOT, "charttools-model-row.png"))


def test_model_wheel_and_cursors_with_menus_closed(chart, server):
    """Kolečko přibližuje a Shift+klik nastaví kurzor B se zavřenými nabídkami; zapnuté kurzory ukazuje tlačítko Kurzory."""
    v0 = chart.evaluate("() => window.__pidView.model_view.state().view")
    chart.evaluate("s => document.querySelector(s)?.scrollIntoView({block: 'center'})", f"{M} .pidv-panel canvas")
    chart.wait_for_timeout(200)
    cv = chart.locator(f"{M} .pidv-panel").first.locator("canvas").nth(1).bounding_box()
    chart.mouse.move(cv["x"] + cv["width"] / 2, cv["y"] + cv["height"] / 2)
    chart.mouse.wheel(0, -300)
    chart.wait_for_function("v0 => { const v = window.__pidView.model_view.state().view; return v[1] - v[0] < v0[1] - v0[0]; }", arg=v0)
    btn = chart.locator(f'{M} [data-testid="vw-m-cur"]')
    assert btn.inner_text().strip().startswith("Cursors") and "A/B" not in btn.inner_text() and "on" not in (btn.get_attribute("class") or "").split()
    _menu(chart, M, "cur")
    chart.locator(f'{M} [data-a="cur"]').click()
    chart.locator(f'{M} [data-a="hcur"]').click()
    _menu(chart, M, "cur", False)
    assert btn.inner_text().replace(" ▾", "").strip() == "Cursors · A/B · Y₁/Y₂" and "on" in btn.get_attribute("class").split()
    assert _bar_h(chart, M) <= ONE_ROW
    cv = chart.locator(f"{M} .pidv-panel").first.locator("canvas").nth(1).bounding_box()
    chart.mouse.click(cv["x"] + cv["width"] * 0.35, cv["y"] + cv["height"] / 2)
    chart.keyboard.down("Shift")
    chart.mouse.click(cv["x"] + cv["width"] * 0.6, cv["y"] + cv["height"] / 2)
    chart.keyboard.up("Shift")
    st = chart.evaluate("() => window.__pidView.model_view.state().cur")
    assert st["on"] and st["a"] is not None and st["b"] is not None
    _menu(chart, M, "cur")
    chart.locator(f'{M} [data-a="cur"]').click()
    chart.locator(f'{M} [data-a="hcur"]').click()
    _menu(chart, M, "cur", False)
    st = chart.evaluate("() => window.__pidView.model_view.state()")
    assert not st["cur"]["on"] and not st["hc"]["on"]
    assert btn.inner_text().replace(" ▾", "").strip() == "Cursors" and "on" not in btn.get_attribute("class").split()


def test_model_state_survives_reload(chart, server):
    """Starý uložený stav s „tools“ se načte (klíč se nepoužívá); výchozí řádek zůstává jeden."""
    _call(server, chart, "PATCH", B + "/settings", {"mview": json.dumps({"v": 1, "panels": [], "list": False, "tools": True})})
    _reload_to(chart, _open_model)
    _default_checks(chart, M)
    _call(server, chart, "PATCH", B + "/settings", {"mview": None})
    _reload_to(chart, _open_model)
    _default_checks(chart, M)


def test_model_list_default_and_old_layouts(chart, server):
    """Seznam signálů položkou nabídky Zobrazení; starý uložený rozložení se seznamem (bez „tools“) se bere jako výchozí = skrytý,
    rozložení uložené po zavedení skrytého seznamu volbu zachová."""
    _list(chart, M)
    assert chart.locator(f"{M} .pidv-list .pidv-sig").count() >= 3
    pl = chart.locator(f"{M} .pidv-plots").bounding_box()
    body = chart.locator(f"{M} .pidv-body").bounding_box()
    assert body["width"] - pl["width"] > 200                                       # sloupec seznamu ubírá šířku
    _call(server, chart, "PATCH", B + "/settings", {"mview": json.dumps({"v": 1, "panels": [], "list": True})})
    _reload_to(chart, _open_model)
    assert chart.locator(f"{M} .pidv-list").count() == 0                           # starý stav seznam nezapíná
    _call(server, chart, "PATCH", B + "/settings", {"mview": json.dumps({"v": 1, "panels": [], "list": True, "tools": False})})
    _reload_to(chart, _open_model)
    assert chart.locator(f"{M} .pidv-list").count() == 1                           # výslovná volba se zachová
    _menu(chart, M, "view")
    assert chart.locator(f'{M} [data-a="list"]').get_attribute("aria-checked") == "true"
    _call(server, chart, "PATCH", B + "/settings", {"mview": None})
    _reload_to(chart, _open_model)
    _default_checks(chart, M)


def test_diag_row_and_old_layouts(chart, server):
    _reload_to(chart, _open_diag)
    _default_checks(chart, D)
    bar = chart.locator(f"{D} .pidv-bar")
    assert bar.locator('[data-testid="ab-zoom-win"]').is_visible()
    assert chart.locator(f'{D} [data-testid="mw-mode-grp"]').count() == 0
    if SHOT:
        chart.locator(D).screenshot(path=os.path.join(SHOT, "charttools-diag-row.png"))
    _list(chart, D)
    assert chart.locator(f"{D} .pidv-list .pidv-sig").count() >= 2
    _call(server, chart, "PATCH", B + "/settings", {"diagview": json.dumps({"v": 1, "panels": [], "list": True})})
    _reload_to(chart, _open_diag)
    assert chart.locator(f"{D} .pidv-list").count() == 0                           # starý stav seznam nezapíná
    _call(server, chart, "PATCH", B + "/settings", {"diagview": json.dumps({"v": 1, "panels": [], "list": True, "tools": False})})
    _reload_to(chart, _open_diag)
    assert chart.locator(f"{D} .pidv-list").count() == 1                           # výslovná volba se zachová
    _call(server, chart, "PATCH", B + "/settings", {"diagview": None})
    _reload_to(chart, _open_diag)
    _default_checks(chart, D)


def test_trends_toolbar_not_compact(chart, server):
    """Data › Trendy (samostatný nástroj) nejsou kompaktní: seznam signálů je vidět hned, události jsou v nabídce tažení myší."""
    chart.locator('[data-tab="data"]').click()
    chart.locator('[data-sub="trends"]').click()
    V = '[data-testid="trd-viewer"]'
    chart.wait_for_selector(f"{V} .pidv-panel canvas", timeout=30000)
    assert chart.locator(f'{V} [data-testid="vw-tools"]').count() == 0
    for a in ("back", "fwd", "full"):
        assert chart.locator(f'{V} .pidv-bar [data-a="{a}"]').count() == 1
    for n in ("mode", "view", "cur", "exp"):
        assert chart.locator(f'{V} .pidv-bar [data-testid="vw-m-{n}"]').count() == 1
    assert _bar_h(chart, V) <= ONE_ROW
    _menu(chart, V, "mode")
    assert chart.locator(f'{V} [data-g="mode"] [role="menuitemradio"]').count() == 4
    assert chart.locator(f'{V} [data-a="evp"]').count() == 1 and chart.locator(f'{V} [data-a="evn"]').count() == 1
    _menu(chart, V, "mode", False)
    assert chart.locator('[data-testid="trd-tree"] .pidv-list').count() >= 1
