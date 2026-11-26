"""
Kompaktní vložené grafy (Model › Identifikace, Data › Diagnostika): lišta nástrojů má ve výchozím stavu jeden řádek (podstatné
ovládání + tlačítko „Nástroje grafu“), ostatní nástroje prohlížeče a seznam signálů jsou skryté; tlačítko je klávesnicí
dosažitelné, stav rozbalení se ukládá v rozložení (mview / diagview) a přežije znovunačtení, kolečko a kurzory fungují i při
sbaleném panelu a zapnutý kurzor je ve sbalené liště vidět. Data › Trendy zůstávají beze změny (nejsou kompaktní).
Potřebuje sestavené UI (cd frontend && npm run build).
"""
import json
import os

import pytest

pytest.importorskip("playwright.sync_api")
import test_frontend as _tf  # noqa: E402
from test_frontend_diagchart import D, _open_diag  # noqa: E402
from test_frontend_modelchart import B, M, _call, _contrast, _list, _open_model, _rgb, _tools, _until  # noqa: E402

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


def _expanded(pg, root):
    return pg.locator(f'{root} [data-testid="vw-tools"]').get_attribute("aria-expanded") == "true"


def _saved(server, pg, key, want):
    """Počká, až je v uloženém rozložení (nastavení key) tools == want (ukládá se po 1,5 s klidu)."""
    _until(lambda: json.loads(_call(server, pg, "GET", B + "/settings").get(key) or "{}").get("tools") is want, 20)


def _collapsed_checks(pg, root):
    btn = pg.locator(f'{root} [data-testid="vw-tools"]')
    assert btn.get_attribute("aria-expanded") == "false" and btn.inner_text().startswith("Chart tools")
    assert pg.locator(f'{root} [data-testid="vw-tools-panel"]').count() == 0
    assert pg.locator(f'{root} .pidv-bar [data-a="back"]').count() == 0          # ostatní nástroje prohlížeče jsou skryté
    assert pg.locator(f"{root} .pidv-list").count() == 0                          # seznam signálů je skrytý
    assert _bar_h(pg, root) <= ONE_ROW, _bar_h(pg, root)                          # lišta má jeden řádek


def test_model_collapsed_by_default(chart, server):
    _collapsed_checks(chart, M)
    bar = chart.locator(f"{M} .pidv-bar")
    assert bar.locator('[data-testid="mw-mode"]').is_visible() and bar.locator('[data-testid="mw-zoom-win"]').is_visible()
    assert bar.locator('[data-testid="mw-resid"]').is_visible()                    # podstatné: režim úseků, přiblížení, rezidua
    assert chart.locator(f'{M} [data-testid="mw-model"]').count() == 0             # části modelu až v panelu
    pl = chart.locator(f"{M} .pidv-plots").bounding_box()
    body = chart.locator(f"{M} .pidv-body").bounding_box()
    assert abs(pl["width"] - body["width"]) < 2                                    # graf přes celou šířku (bez sloupce seznamu)
    if SHOT:
        chart.locator(M).screenshot(path=os.path.join(SHOT, "charttools-model-collapsed.png"))


def test_model_toggle_shows_all_controls(chart, server):
    h0 = _bar_h(chart, M)
    chart.locator(f'{M} [data-testid="vw-tools"]').click()
    chart.wait_for_selector(f'{M} [data-testid="vw-tools-panel"]')
    assert _expanded(chart, M) and chart.locator(f'{M} [data-testid="vw-tools"]').inner_text().endswith("▴")
    panel = chart.locator(f'{M} [data-testid="vw-tools-panel"]')
    for sel in ('[data-g="mpart"]', '[data-g="mrange"]', '[data-g="mode"]', '[data-g="ya"]', '[data-g="step"]', '[data-a="back"]',
                '[data-a="fwd"]', '[data-a="full"]', '[data-a="evp"]', '[data-a="evn"]', '[data-a="cur"]', '[data-a="hcur"]',
                '[data-a="list"]', '[data-a="tab"]', '[data-a="csv_view"]', '[data-a="csv_cur"]', '[data-a="png"]', ".pidv-help"):
        assert panel.locator(sel).count() == 1, sel
    assert _bar_h(chart, M) > h0
    if SHOT:
        chart.locator(M).screenshot(path=os.path.join(SHOT, "charttools-model-expanded.png"))
    chart.locator(f'{M} [data-testid="vw-tools"]').click()
    chart.wait_for_selector(f'{M} [data-testid="vw-tools-panel"]', state="detached")
    _collapsed_checks(chart, M)


def test_model_keyboard_toggle(chart, server):
    """Tlačítko je button dosažitelný klávesou Tab (za polem Rezidua), Enter ho přepíná a fokus zůstane na něm."""
    chart.locator(f'{M} [data-testid="mw-resid"]').focus()
    chart.keyboard.press("Tab")
    assert chart.evaluate("() => document.activeElement?.dataset.testid") == "vw-tools"
    assert chart.evaluate("() => document.activeElement.tagName") == "BUTTON"
    chart.keyboard.press("Enter")
    chart.wait_for_selector(f'{M} [data-testid="vw-tools-panel"]')
    assert chart.evaluate("() => document.activeElement?.dataset.testid") == "vw-tools"
    chart.keyboard.press("Enter")
    chart.wait_for_selector(f'{M} [data-testid="vw-tools-panel"]', state="detached")
    assert chart.evaluate("() => document.activeElement?.dataset.testid") == "vw-tools"


def test_model_wheel_and_cursors_when_collapsed(chart, server):
    """Kolečko přibližuje a Shift+klik nastaví kurzor B i bez panelu; zapnutý kurzor je ve sbalené liště vidět a jde vypnout."""
    _tools(chart, M, False)
    v0 = chart.evaluate("() => window.__pidView.model_view.state().view")
    chart.evaluate("s => document.querySelector(s)?.scrollIntoView({block: 'center'})", f"{M} .pidv-panel canvas")
    chart.wait_for_timeout(200)
    cv = chart.locator(f"{M} .pidv-panel").first.locator("canvas").nth(1).bounding_box()
    chart.mouse.move(cv["x"] + cv["width"] / 2, cv["y"] + cv["height"] / 2)
    chart.mouse.wheel(0, -300)
    chart.wait_for_function("v0 => { const v = window.__pidView.model_view.state().view; return v[1] - v[0] < v0[1] - v0[0]; }", arg=v0)
    _tools(chart, M)                                                                # zapnout kurzory v panelu a sbalit
    chart.locator(f'{M} [data-a="cur"]').click()
    chart.locator(f'{M} [data-a="hcur"]').click()
    _tools(chart, M, False)
    act = chart.locator(f'{M} .pidv-bar [data-testid="vw-active"]')
    assert act.locator('[data-a="cur"].on').count() == 1 and act.locator('[data-a="hcur"].on').count() == 1
    assert _bar_h(chart, M) <= ONE_ROW
    cv = chart.locator(f"{M} .pidv-panel").first.locator("canvas").nth(1).bounding_box()
    chart.mouse.click(cv["x"] + cv["width"] * 0.35, cv["y"] + cv["height"] / 2)
    chart.keyboard.down("Shift")
    chart.mouse.click(cv["x"] + cv["width"] * 0.6, cv["y"] + cv["height"] / 2)
    chart.keyboard.up("Shift")
    st = chart.evaluate("() => window.__pidView.model_view.state().cur")
    assert st["on"] and st["a"] is not None and st["b"] is not None
    act.locator('[data-a="cur"]').click()
    act.locator('[data-a="hcur"]').click()
    st = chart.evaluate("() => window.__pidView.model_view.state()")
    assert not st["cur"]["on"] and not st["hc"]["on"]
    assert chart.locator(f'{M} .pidv-bar [data-testid="vw-active"]').count() == 0


def test_model_toggle_contrast(chart, server):
    """Tlačítko Nástroje grafu: kontrast textu ≥ 4,5 : 1 ve sbaleném i rozbaleném stavu."""
    btn = f'{M} [data-testid="vw-tools"]'
    for open_ in (False, True):
        _tools(chart, M, open_)
        c, bg = chart.evaluate("""s => { const e = document.querySelector(s), st = getComputedStyle(e); return [st.color, st.backgroundColor]; }""", btn)
        assert _contrast(_rgb(c), _rgb(bg)) >= 4.5, (open_, c, bg)
    _tools(chart, M, False)


def test_model_state_survives_reload(chart, server):
    _tools(chart, M)
    _saved(server, chart, "mview", True)
    _reload_to(chart, _open_model)
    assert _expanded(chart, M) and chart.locator(f'{M} [data-testid="vw-tools-panel"]').count() == 1
    _tools(chart, M, False)
    _saved(server, chart, "mview", False)
    _reload_to(chart, _open_model)
    _collapsed_checks(chart, M)


def test_model_list_default_and_old_layouts(chart, server):
    """Seznam signálů tlačítkem Signály; starý uložený rozložení se seznamem (bez „tools“) se bere jako výchozí = skrytý,
    rozložení uložené po zavedení panelu s volbou seznamu volbu zachová."""
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
    _call(server, chart, "PATCH", B + "/settings", {"mview": None})
    _reload_to(chart, _open_model)
    _collapsed_checks(chart, M)


def test_diag_collapsed_toggle_and_reload(chart, server):
    _reload_to(chart, _open_diag)
    _collapsed_checks(chart, D)
    bar = chart.locator(f"{D} .pidv-bar")
    assert bar.locator('[data-testid="ab-zoom-win"]').is_visible()
    assert chart.locator(f'{D} [data-testid="mw-mode-grp"]').count() == 0
    if SHOT:
        chart.locator(D).screenshot(path=os.path.join(SHOT, "charttools-diag-collapsed.png"))
    chart.locator(f'{D} [data-testid="ab-zoom-win"]').focus()
    chart.keyboard.press("Tab")
    assert chart.evaluate("() => document.activeElement?.dataset.testid") == "vw-tools"
    chart.keyboard.press("Enter")
    chart.wait_for_selector(f'{D} [data-testid="vw-tools-panel"]')
    panel = chart.locator(f'{D} [data-testid="vw-tools-panel"]')
    for sel in ('[data-g="mode"]', '[data-a="back"]', '[data-a="cur"]', '[data-a="hcur"]', '[data-a="list"]', '[data-a="png"]'):
        assert panel.locator(sel).count() == 1, sel
    _saved(server, chart, "diagview", True)
    _reload_to(chart, _open_diag)
    assert _expanded(chart, D)
    _list(chart, D)
    assert chart.locator(f"{D} .pidv-list .pidv-sig").count() >= 2
    _tools(chart, D, False)
    _saved(server, chart, "diagview", False)
    _reload_to(chart, _open_diag)
    assert not _expanded(chart, D) and chart.locator(f"{D} .pidv-list").count() == 1                 # volba seznamu zůstává
    _call(server, chart, "PATCH", B + "/settings", {"diagview": None})
    _reload_to(chart, _open_diag)
    _collapsed_checks(chart, D)


def test_trends_toolbar_unchanged(chart, server):
    """Data › Trendy (samostatný nástroj) nejsou kompaktní: všechny nástroje i seznam signálů jsou vidět hned."""
    chart.locator('[data-tab="data"]').click()
    chart.locator('[data-sub="trends"]').click()
    V = '[data-testid="trd-viewer"]'
    chart.wait_for_selector(f"{V} .pidv-panel canvas", timeout=30000)
    assert chart.locator(f'{V} [data-testid="vw-tools"]').count() == 0
    assert chart.locator(f'{V} .pidv-bar [data-a="back"]').count() == 1 and chart.locator(f'{V} .pidv-bar [data-a="cur"]').count() == 1
    assert chart.locator(f'{V} .pidv-bar [data-g="mode"]').count() == 1
