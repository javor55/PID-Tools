"""
Data › Diagnostika: graf záznamu je prohlížeč záznamu (viewer.js) s vrstvou úseků v režimu „ab“ (viewer_spans.js) – ne
dřívější samostatný graf úseků. Výchozí panely (PV + SP | MV), tažení táhel úseku A (ukazatele z API pro nový úsek), přidání
a odebrání úseku B, rozložení uložené po smyčce (nastavení diagview) nezávisle na Trendech (dview) a na Modelu (mview),
kurzory A / B, hodnotové kurzory, export, kontrast štítků A / B, stav načítání. Potřebuje sestavené UI (cd frontend && npm run build).
"""
import json
import os
import re
import urllib.request

import pytest

pytest.importorskip("playwright.sync_api")
import test_frontend as _tf  # noqa: E402
from test_frontend_modelchart import _contrast, _call, _csv_extra, _drag, _rgb, _until  # noqa: E402

TOKEN = _tf.TOKEN
server, page = _tf.server, _tf.page                      # fixtury serveru a prohlížeče
B = "/api/v1/workspaces/{wid}"
D = '[data-testid="diag-trend"]'
SHOT = os.environ.get("DIAGCHART_SHOT")                  # složka pro snímky obrazovky (jen ruční kontrola)


def _state(pg):
    return pg.evaluate("() => window.__pidView.diag_view.state()")


def _open_diag(pg):
    pg.locator('[data-tab="data"]').click()
    pg.locator('[data-sub="diag"]').click()
    pg.locator('[data-testid="diag-sub"] [data-value="diag-detail"]').click()
    pg.wait_for_selector(f"{D} .pidv-panel canvas", timeout=60000)
    pg.wait_for_selector(f'{D} [data-testid="mw-track"]', timeout=30000)
    pg.wait_for_timeout(400)


def _reload(pg):
    pg.reload(wait_until="networkidle")
    pg.wait_for_selector('[data-testid="api-ok"]', timeout=20000)
    _open_diag(pg)


def _seg_inputs(pg):
    """Číselná pole úseků v pravém panelu (A od, A do, B od, B do) – hodnota v jednotce osy."""
    return pg.locator('[data-testid="diag-side-seg"] input[type="number"]')


@pytest.fixture(scope="module")
def chart(page, server):
    """Demo; otevřená Data › Diagnostika › Detail smyčky."""
    page.locator('[data-tab="data"]').click()
    page.locator('[data-sub="sources"]').click()
    page.locator('[data-testid="src-demo"]').click()
    page.wait_for_function("() => (document.querySelector('[data-testid=\"data-info\"]')||{}).innerText?.includes('demo')")
    _open_diag(page)
    return page


def test_default_panels(chart, server):
    ws = _call(server, chart, "GET", B)
    panels = [p["sigs"] for p in _state(chart)["panels"]]
    assert panels == [[ws["pv"], ws["sp"]], [ws["mv"]]], panels                # jako dřívější graf: PV + SP | MV
    assert chart.locator(f"{D} .pidv-panel").count() == 2
    assert chart.locator(f'{D} [aria-busy="true"]').count() == 0
    # úsek A přes celý záznam, B není; jedna lišta pod prvním panelem a štítek „Segment A“
    assert chart.locator(f'{D} [data-testid="mw-track"]').count() == 1
    assert chart.locator(f'{D} [data-testid="mw-wlab"]').all_inner_texts() == [chart.evaluate("() => document.querySelector('.diag-seg span').innerText")]
    assert chart.locator(f'{D} [data-testid="mw-handle"]').count() == 2
    assert chart.locator(f'{D} [data-testid="mw-mode-grp"]').count() == 0      # bez přepínače režimu úseků (to je jen Model)
    assert chart.locator(f'{D} [data-testid="ab-zoom-win"]').count() == 1
    # ostatní signály záznamu (poruchy) jsou v seznamu, ale ne ve výchozích panelech
    names = chart.locator(f"{D} .pidv-list .pidv-sig .nm").all_inner_texts()
    assert all(any(d in n for n in names) for d in ws["dists"]), names
    assert SHOT is None or chart.locator(D).screenshot(path=os.path.join(SHOT, "diagchart-a.png")) is not None


def test_drag_handle_a_changes_segment(chart, server):
    """Tažení konce úseku A: pole v pravém panelu i ukazatele (KPI) odpovídají API pro nový úsek."""
    T = _call(server, chart, "GET", B)["duration"]
    unit = chart.evaluate("/\\bmin\\b/.test(document.querySelector('%s [data-testid=\"mw-chip\"]').innerText) ? 60 : 1" % D)
    before = float(_seg_inputs(chart).nth(1).input_value())
    assert abs(before * unit - T) < unit
    _drag(chart, f'{D} [data-testid="mw-track"] [data-testid="mw-handle"][data-k="1"]', -200)
    chart.wait_for_function("(b) => parseFloat(document.querySelectorAll('[data-testid=\"diag-side-seg\"] input[type=number]')[1].value) < b",
                            arg=before, timeout=20000)
    end = float(_seg_inputs(chart).nth(1).input_value()) * unit
    d = _call(server, chart, "GET", B + f"/diagnostics?a=0&b={end}")
    _tf._wait_sel(chart, '[data-testid="diag-kpi-std-a"]', d["kpis"]["std_e"], 1e-2, 60000)
    # čip úseku ukazuje totéž číslo a políčko jde psát (Enter) → pole v panelu následuje
    chip = chart.locator(f'{D} [data-testid="mw-chip"] input').nth(1)
    assert abs(float(chip.input_value()) * unit - end) < 1.5 * unit
    chip.fill(str(round(T / unit, 4)))
    chip.press("Enter")
    chart.wait_for_function("(b) => parseFloat(document.querySelectorAll('[data-testid=\"diag-side-seg\"] input[type=number]')[1].value) > b",
                            arg=end / unit, timeout=20000)
    # dvojklik na liště přitáhne nejbližší mez na místo kliknutí
    chart.evaluate("s => document.querySelector(s).scrollIntoView({block: 'center'})", f'{D} [data-testid="mw-track"]')
    chart.wait_for_timeout(200)
    trk = chart.locator(f'{D} [data-testid="mw-track"]').first.bounding_box()
    e0 = float(_seg_inputs(chart).nth(1).input_value())
    chart.mouse.dblclick(trk["x"] + trk["width"] * 0.7, trk["y"] + 30)
    chart.wait_for_function("(b) => parseFloat(document.querySelectorAll('[data-testid=\"diag-side-seg\"] input[type=number]')[1].value) < b",
                            arg=e0, timeout=20000)
    # a pole v pravém panelu přesune úsek v grafu (stav je jeden)
    inp = _seg_inputs(chart).nth(0)
    inp.fill("5")
    inp.press("Enter")
    chart.wait_for_function("() => Math.abs(parseFloat(document.querySelector('%s [data-testid=\"mw-chip\"] input').value) - 5) < 0.01" % D, timeout=20000)
    inp.fill("0")
    inp.press("Enter")


def test_add_and_remove_segment_b(chart, server):
    assert chart.locator(f'{D} [data-testid="mw-chip"]').count() == 1
    chart.locator('[data-testid="diag-cmp"]').check()
    chart.wait_for_function("() => document.querySelectorAll('%s [data-testid=\"mw-chip\"]').length === 2" % D, timeout=20000)
    assert chart.locator(f'{D} [data-testid="mw-handle"]').count() == 4
    labs = chart.locator(f'{D} [data-testid="mw-wlab"]').all_inner_texts()
    assert len(labs) == 2 and labs[0] != labs[1]
    assert chart.locator(f'{D} [data-testid="mw-track"]').count() == 1
    assert SHOT is None or chart.locator(D).screenshot(path=os.path.join(SHOT, "diagchart-ab.png")) is not None
    # tažení začátku B mění diagnostiku B (API pro nový úsek)
    T = _call(server, chart, "GET", B)["duration"]
    unit = chart.evaluate("/\\bmin\\b/.test(document.querySelector('%s [data-testid=\"mw-chip\"]').innerText) ? 60 : 1" % D)
    b0 = float(_seg_inputs(chart).nth(2).input_value())
    _drag(chart, f'{D} [data-testid="mw-track"] [data-testid="mw-handle"][data-i="1"][data-k="0"]', 120)
    chart.wait_for_function("(b) => parseFloat(document.querySelectorAll('[data-testid=\"diag-side-seg\"] input[type=number]')[2].value) > b",
                            arg=b0, timeout=20000)
    b1 = float(_seg_inputs(chart).nth(2).input_value()) * unit
    db = _call(server, chart, "GET", B + f"/diagnostics?a={b1}&b={T}")
    _tf._wait_sel(chart, '[data-testid="diag-kpi-std-b"]', db["kpis"]["std_e"], 1e-2, 60000)
    # odebrání B (políčko Porovnat) – i z grafu; úsek A zůstane
    chart.locator('[data-testid="diag-cmp"]').uncheck()
    chart.wait_for_function("() => document.querySelectorAll('%s [data-testid=\"mw-chip\"]').length === 1" % D, timeout=20000)
    assert chart.locator(f'{D} [data-testid="mw-handle"]').count() == 2
    assert chart.locator('[data-testid="diag-kpi-std-b"]').count() == 0


def test_layout_saved_per_loop(chart, server):
    """Přidání signálu do grafu → nastavení diagview (po smyčce); dview a mview se nemění; po znovunačtení platí."""
    ws = _call(server, chart, "GET", B)
    s0 = _call(server, chart, "GET", B + "/settings")
    assert s0.get("diagview") in (None, "")
    dv = ws["dists"][0]
    row = chart.locator(f"{D} .pidv-list .pidv-sig", has_text=dv).first
    row.locator("input[type=checkbox]").check()
    chart.wait_for_function("d => window.__pidView.diag_view.state().panels.some(p => p.sigs.some(n => n.includes(d)))", arg=dv)
    saved = _until(lambda: _call(server, chart, "GET", B + "/settings").get("diagview"), 15)
    assert dv in saved
    s1 = _call(server, chart, "GET", B + "/settings")
    assert s1.get("dview") == s0.get("dview") and s1.get("mview") == s0.get("mview")
    _reload(chart)
    assert any(dv in n for p in _state(chart)["panels"] for n in p["sigs"])
    # Trendy a Model mají vlastní rozložení: změna dview diagnostiku nezmění
    _call(server, chart, "PATCH", B + "/settings", {"dview": json.dumps({"v": 1, "panels": []})})
    _reload(chart)
    assert any(dv in n for p in _state(chart)["panels"] for n in p["sigs"])
    # jiná smyčka (nový prostor) má vlastní výchozí rozložení
    wid0 = chart.evaluate("sessionStorage.getItem('pid.wid')")
    new = json.loads(urllib.request.urlopen(urllib.request.Request(
        server + "/api/v1/workspaces", method="POST", data=b"", headers={"X-PID-Token": TOKEN}), timeout=60).read())
    chart.evaluate("w => sessionStorage.setItem('pid.wid', w)", new["id"])
    _call(server, chart, "POST", f"/api/v1/workspaces/{new['id']}/sources?name=x.csv&timezone=UTC", raw=_csv_extra())
    _call(server, chart, "POST", f"/api/v1/workspaces/{new['id']}/loops/suggest", {"apply": True})
    _reload(chart)
    assert not any("XTRA" in n for p in _state(chart)["panels"] for n in p["sigs"])
    assert len(_state(chart)["panels"]) == 2
    assert _call(server, chart, "GET", B + "/settings").get("diagview") in (None, "")
    chart.evaluate("w => sessionStorage.setItem('pid.wid', w)", wid0)
    _reload(chart)
    assert any(dv in n for p in _state(chart)["panels"] for n in p["sigs"])
    _call(server, chart, "PATCH", B + "/settings", {"dview": s0.get("dview"), "diagview": None})
    _reload(chart)
    assert len(_state(chart)["panels"]) == 2


def test_cursors_and_export(chart, server):
    ws_pv = _call(server, chart, "GET", B)["pv"]
    bar = chart.locator(f"{D} .pidv-bar")
    bar.locator("[data-a=cur]").click()
    assert _state(chart)["cur"]["on"]
    chart.evaluate("s => document.querySelector(s).scrollIntoView({block: 'center'})", f"{D} .pidv-panel canvas")
    chart.wait_for_timeout(200)
    cv = chart.locator(f"{D} .pidv-panel").first.locator("canvas").nth(1).bounding_box()
    chart.mouse.click(cv["x"] + cv["width"] * 0.35, cv["y"] + cv["height"] / 2)
    chart.keyboard.down("Shift")
    chart.mouse.click(cv["x"] + cv["width"] * 0.6, cv["y"] + cv["height"] / 2)
    chart.keyboard.up("Shift")
    st = _state(chart)["cur"]
    assert st["a"] is not None and st["b"] is not None and st["a"] < st["b"]
    assert "Δt" in chart.locator(f"{D} .pidv-read").first.inner_text()
    bar.locator("[data-a=cur]").click()
    bar.locator("[data-a=hcur]").click()                                       # hodnotové kurzory Y₁ / Y₂
    assert _state(chart)["hc"]["on"] and chart.locator(f"{D} [data-testid=hc-sig]").count() == 1
    bar.locator("[data-a=hcur]").click()
    # přiblížení na úseky a zpět
    bar.locator('[data-testid="ab-zoom-win"]').click()
    with chart.expect_download() as d:
        bar.locator('[data-a="png"]').click()
    assert d.value.suggested_filename.endswith(".png")
    with chart.expect_download() as d:
        bar.locator('[data-a="csv_view"]').click()
    assert ws_pv in open(d.value.path(), encoding="utf-8-sig").readline()


def _label_contrasts(pg):
    rows = pg.evaluate("""(sel) => [...document.querySelectorAll(sel + ' [data-testid="mw-wlab"], ' + sel + ' [data-testid="mw-chip"], ' + sel + ' [data-testid="mw-chip"] button, ' + sel + ' [data-testid="mw-chip"] input')]
        .map(e => { const s = getComputedStyle(e); let b = e, bg = s.backgroundColor;     // průhledné pozadí = barva nejbližšího předka
          while (/rgba\\(.*, 0\\)$/.test(bg) && b.parentElement) { b = b.parentElement; bg = getComputedStyle(b).backgroundColor; }
          return [e.dataset.testid || e.tagName.toLowerCase(), s.color, bg, (e.innerText || e.value).slice(0, 20)]; })""", D)
    return [(k, _contrast(_rgb(c), _rgb(b)), t) for k, c, b, t in rows]


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_ab_label_contrast(chart, server, theme):
    """Štítky a čipy úseků A / B mají kontrast textu ≥ 4,5 : 1 (z vypočtených barev) ve světlém i tmavém vzhledu."""
    chart.locator('[data-testid="diag-cmp"]').check()
    chart.wait_for_function("() => document.querySelectorAll('%s [data-testid=\"mw-chip\"]').length === 2" % D, timeout=20000)
    _tf._settings(chart)
    chart.select_option('select[aria-label="theme"]', theme)
    chart.locator('[data-testid="settings"] summary').click()
    chart.wait_for_function("t => document.querySelector('%s .pidv').classList.contains('dark') === (t === 'dark')" % D, arg=theme, timeout=20000)
    chart.wait_for_timeout(400)
    rows = _label_contrasts(chart)
    assert len([r for r in rows if r[0] == "mw-wlab"]) == 2 and len([r for r in rows if r[0] == "mw-chip"]) == 2
    assert len([r for r in rows if r[0] in ("button", "input")]) == 6                    # zoom + dvě políčka u obou úseků
    bad = [r for r in rows if r[1] < 4.5]
    assert not bad, bad
    if SHOT:
        print(theme, [(k, round(c, 2), t) for k, c, t in rows])
        chart.locator(D).screenshot(path=os.path.join(SHOT, f"diagchart-ab-{theme}.png"))
    if theme == "dark":
        _tf._settings(chart)
        chart.select_option('select[aria-label="theme"]', "light")
        chart.locator('[data-testid="settings"] summary').click()
    chart.locator('[data-testid="diag-cmp"]').uncheck()


def test_viewer_destroyed_on_leave(chart):
    """Po odchodu z Diagnostiky nezůstává v dokumentu ani v registru žádný prohlížeč."""
    chart.locator('[data-sub="sources"]').click()
    chart.wait_for_selector('[data-testid="src-demo"]', timeout=10000)
    assert chart.evaluate("() => ({pidv: document.querySelectorAll('.pidv').length, reg: Object.keys(window.__pidView || {}).length})") \
        == {"pidv": 0, "reg": 0}
    _open_diag(chart)
    assert re.search(r"PV", chart.locator(f"{D} .pidv-panel").first.inner_text())


def test_loading_and_error_states(chart):
    """Mřížka se načítá: kostra s popisem (ne „…“); chyba načtení: hlášení s tlačítkem Zkusit znovu; pak graf."""
    state = {"mode": "slow"}

    def handle(route):
        if "source=grid" not in route.request.url:
            return route.continue_()
        if state["mode"] == "slow":
            chart.wait_for_timeout(1500)
            return route.continue_()
        if state["mode"] == "fail":
            return route.fulfill(status=500, content_type="application/json", body='{"detail": "boom"}')
        return route.continue_()

    def to_diag():
        chart.reload(wait_until="domcontentloaded")
        chart.wait_for_selector('[data-testid="api-ok"]', timeout=20000)
        chart.locator('[data-tab="data"]').click()
        chart.locator('[data-sub="diag"]').click()
        chart.locator('[data-testid="diag-sub"] [data-value="diag-detail"]').click()

    chart.route("**/api/v1/workspaces/*/signals*", handle)
    try:
        to_diag()
        chart.wait_for_selector('[data-testid="diag-rec"] [data-testid="qs-skeleton"]', timeout=20000)
        assert chart.locator('[data-testid="diag-rec"] .card.muted').count() == 0           # ne dřívější karta s jediným znakem „…“
        chart.wait_for_selector(f"{D} .pidv-panel canvas", timeout=30000)
        state["mode"] = "fail"
        to_diag()
        chart.wait_for_selector('[data-testid="diag-rec"] [data-testid="qs-retry"]', timeout=60000)
        state["mode"] = "ok"
        chart.locator('[data-testid="diag-rec"] [data-testid="qs-retry"]').click()
        chart.wait_for_selector(f"{D} .pidv-panel canvas", timeout=30000)
    finally:
        chart.unroute("**/api/v1/workspaces/*/signals*", handle)
    _reload(chart)
