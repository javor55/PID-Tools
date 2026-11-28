"""
Lišta prohlížeče záznamu (viewer.js) s rozbalovacími nabídkami – jedna a táž ve všech třech grafech (Data › Trendy,
Model › Identifikace, Data › Diagnostika): jeden řádek (výška ≤ 48 px při šířce 1440 px), nabídky Tažení myší / Zobrazení /
Kurzory / Export otevřené a zavřené klikem, Enter, Esc a klikem mimo, přepínače a zaškrtávátka nabídku nechávají otevřenou
a použijí se, nabídka je celá v okně a nad plátnem, ukazatel kurzorů v tlačítku, nabídka ⋯ v hlavičce panelu (přesun, odebrání,
společná osa Y), šipky na klávesnici, kontrast ve světlém i tmavém vzhledu. Potřebuje sestavené UI (cd frontend && npm run build).
"""
import os

import pytest

pytest.importorskip("playwright.sync_api")
import test_frontend as _tf  # noqa: E402
from chartmenu import menu  # noqa: E402
from test_frontend_diagchart import D, _open_diag  # noqa: E402
from test_frontend_modelchart import B, M, _call, _contrast, _open_model, _rgb, _until  # noqa: E402

server, page = _tf.server, _tf.page                      # fixtury serveru a prohlížeče
TV = '[data-testid="trd-viewer"]'
ONE_ROW = 48                                             # nejvýše tolik px: jeden řádek lišty (8 + řádek + 8)
SHOT = os.environ.get("CHARTMENUS_SHOT")                 # složka pro snímky obrazovky (jen ruční kontrola)
VIEW = {"trends": "trends_view", "model": "model_view", "diag": "diag_view"}


def _open_trends(pg):
    pg.locator('[data-tab="data"]').click()
    pg.locator('[data-sub="trends"]').click()
    pg.wait_for_selector(f"{TV} .pidv-panel canvas", timeout=30000)
    pg.wait_for_timeout(400)


CH = {"trends": (TV, _open_trends), "model": (M, _open_model), "diag": (D, _open_diag)}
ALL = list(CH)


@pytest.fixture(scope="module")
def chart(page, server):
    """Demo a identifikovaný model (Model i Diagnostika mají data)."""
    page.locator('[data-tab="data"]').click()
    page.locator('[data-sub="sources"]').click()
    page.locator('[data-testid="src-demo"]').click()
    page.wait_for_function("() => (document.querySelector('[data-testid=\"data-info\"]')||{}).innerText?.includes('demo')")
    _call(server, page, "PATCH", B + "/settings", {"chosen": ["P1D", "I1D"], "win_mode": "common"})
    j = _call(server, page, "POST", B + "/identify", {})
    _until(lambda: _call(server, page, "GET", f"/api/v1/jobs/{j['id']}")["state"] not in ("queued", "running"), 120)
    page.reload(wait_until="networkidle")
    page.wait_for_selector('[data-testid="api-ok"]', timeout=20000)
    return page


def _go(pg, name):
    """Otevře graf (stránku) a vrátí selektor jeho kořene; nabídky zavře, ať test začíná z čistého stavu."""
    root, opener = CH[name]
    opener(pg)
    for b in pg.locator(f'{root} [data-m][aria-expanded="true"]').all():
        b.click()
    pg.wait_for_selector(f'{root} [data-testid="vw-menu"]', state="detached")
    return root


def _state(pg, name):
    return pg.evaluate("n => window.__pidView[n].state()", VIEW[name])


def _active(pg):
    return pg.evaluate("() => ({tid: document.activeElement?.dataset.testid, mk: document.activeElement?.dataset.mk, tag: document.activeElement?.tagName})")


def _canvas_click(pg, root, fx=0.5, fy=0.5):
    """Klik do plátna prvního panelu (mimo nabídku); v režimu posunu bez kurzorů nic nemění."""
    pg.evaluate("s => document.querySelector(s)?.scrollIntoView({block: 'center'})", f"{root} .pidv-panel canvas")
    pg.wait_for_timeout(200)
    cv = pg.locator(f"{root} .pidv-panel").first.locator("canvas").nth(1).bounding_box()
    pg.mouse.click(cv["x"] + cv["width"] * fx, cv["y"] + cv["height"] * fy)


@pytest.mark.parametrize("name", ALL)
def test_one_row(chart, name):
    root = _go(chart, name)
    assert chart.viewport_size["width"] == 1440
    h = chart.evaluate("s => document.querySelector(s + ' .pidv-bar').getBoundingClientRect().height", root)
    assert h <= ONE_ROW, h
    bar = chart.locator(f"{root} .pidv-bar")
    for n in ("mode", "view", "cur", "exp"):
        b = bar.locator(f'[data-testid="vw-m-{n}"]')
        assert b.is_visible() and b.get_attribute("aria-haspopup") == "menu" and b.get_attribute("aria-expanded") == "false"
    for a in ("back", "fwd", "full"):                                              # ikony s popiskem i názvem pro čtečky
        b = bar.locator(f'[data-a="{a}"]')
        assert b.get_attribute("title") and b.get_attribute("aria-label") and b.is_visible()
    assert bar.locator('[data-testid="vw-help"]').is_visible()
    assert chart.locator(f'{root} [data-testid="vw-tools"]').count() == 0 and chart.locator(f'{root} [data-testid="vw-menu"]').count() == 0
    assert bar.locator('[data-testid="vw-m-mode"]').inner_text().replace("▾", "").strip() == "Pan"
    assert chart.locator(f'{root} [data-testid="vw-m-panel"]').count() == chart.locator(f"{root} .pidv-panel").count()
    if SHOT:
        chart.locator(root).screenshot(path=os.path.join(SHOT, f"chartmenus-{name}-row.png"))


@pytest.mark.parametrize("name", ALL)
def test_menus_open_close(chart, name):
    root = _go(chart, name)
    for n in ("mode", "view", "cur", "exp"):
        btn = chart.locator(f'{root} [data-testid="vw-m-{n}"]')
        btn.click()                                                                # klik otevře a fokus jde na první položku
        assert btn.get_attribute("aria-expanded") == "true"
        m = chart.locator(f'{root} [data-testid="vw-menu"]')
        assert m.count() == 1 and m.get_attribute("role") == "menu"
        first = m.locator(".pidv-mi:not([disabled])").first
        assert chart.evaluate("() => document.activeElement.classList.contains('pidv-mi')") and first.get_attribute("data-mk") == _active(chart)["mk"]
        assert m.locator("button").count() == m.locator("button[role^=menuitem]").count()          # každé tlačítko nabídky má roli položky
        chart.keyboard.press("Escape")                                             # Esc zavře a vrátí fokus na tlačítko
        chart.wait_for_selector(f'{root} [data-testid="vw-menu"]', state="detached")
        assert btn.get_attribute("aria-expanded") == "false" and _active(chart)["tid"] == f"vw-m-{n}"
        chart.keyboard.press("Enter")                                              # Enter na tlačítku otevře
        chart.wait_for_selector(f'{root} [data-testid="vw-menu"]')
        assert btn.get_attribute("aria-expanded") == "true"
        assert chart.evaluate("() => document.activeElement.classList.contains('pidv-mi')")
        _canvas_click(chart, root)                                                 # klik mimo zavře
        chart.wait_for_selector(f'{root} [data-testid="vw-menu"]', state="detached")
        assert btn.get_attribute("aria-expanded") == "false"
        btn.click()                                                                # druhý klik na tlačítko zavře
        btn.click()
        chart.wait_for_selector(f'{root} [data-testid="vw-menu"]', state="detached")
    # jen jedna nabídka naráz
    chart.locator(f'{root} [data-testid="vw-m-view"]').click()
    chart.locator(f'{root} [data-testid="vw-m-cur"]').click()
    assert chart.locator(f'{root} [data-testid="vw-menu"]').count() == 1
    assert chart.locator(f'{root} [data-testid="vw-m-view"]').get_attribute("aria-expanded") == "false"
    assert chart.locator(f'{root} [data-testid="vw-m-cur"]').get_attribute("aria-expanded") == "true"
    chart.keyboard.press("Escape")


@pytest.mark.parametrize("name", ALL)
def test_radio_and_checkbox_keep_menu_open(chart, name):
    root = _go(chart, name)
    mn = lambda k: chart.locator(f'{root} [data-testid="vw-menu"] [data-mk="{k}"]')       # noqa: E731
    menu(chart, root, "mode")
    mn("mode:box").click()
    assert chart.locator(f'{root} [data-testid="vw-menu"]').count() == 1                    # nabídka zůstala otevřená
    assert mn("mode:box").get_attribute("aria-checked") == "true" and mn("mode:pan").get_attribute("aria-checked") == "false"
    assert _state(chart, name)["mode"] == "box" and _active(chart)["mk"] == "mode:box"       # fokus zůstal na položce
    assert chart.locator(f'{root} [data-testid="vw-m-mode"]').inner_text().replace("▾", "").strip() == "Zoom ⬚"
    chart.keyboard.press("ArrowDown")
    assert _active(chart)["mk"] == "mode:x"
    chart.keyboard.press("Enter")                                                          # Enter na položce = stejné jako klik
    assert _state(chart, name)["mode"] == "x" and _active(chart)["mk"] == "mode:x"
    mn("mode:pan").click()
    assert _state(chart, name)["mode"] == "pan"
    menu(chart, root, "view")
    mn("ya:all").click()
    assert _state(chart, name)["ya"] == "all" and mn("ya:all").get_attribute("aria-checked") == "true"
    mn("ya:view").click()
    mn("step:1").click()
    assert _state(chart, name)["step"] is True and mn("step:1").get_attribute("aria-checked") == "true"
    mn("step:0").click()
    assert _state(chart, name)["step"] is False
    mn("tab").click()                                                                       # tabulka: zaškrtávátko
    assert _state(chart, name)["tab"] is True and mn("tab").get_attribute("role") == "menuitemcheckbox"
    assert mn("tab").get_attribute("aria-checked") == "true" and chart.locator(f'{root} [data-testid="vw-menu"]').count() == 1
    chart.wait_for_selector(f"{root} .pidv-dtab", timeout=10000)
    mn("tab").click()
    assert _state(chart, name)["tab"] is False
    menu(chart, root, "view", False)


@pytest.mark.parametrize("name", ALL)
def test_menu_inside_viewport_and_on_top(chart, name):
    root = _go(chart, name)
    for width in (1440, 700):
        chart.set_viewport_size({"width": width, "height": 900})
        chart.wait_for_timeout(300)
        for n in ("mode", "view", "cur", "exp"):
            menu(chart, root, n)
            r = chart.evaluate("""s => { const m = document.querySelector(s + ' [data-testid="vw-menu"]'); const b = m.getBoundingClientRect();
                const pts = [[0.5, 0.5], [0.05, 0.1], [0.95, 0.1], [0.05, 0.9], [0.95, 0.9]];
                const top = pts.map(([fx, fy]) => { const e = document.elementFromPoint(b.left + b.width * fx, b.top + b.height * fy);
                  return !!e && !!e.closest('.pidv-menu'); });
                return { l: b.left, r: b.right, t: b.top, b: b.bottom, vw: document.documentElement.clientWidth, vh: window.innerHeight, top }; }""", root)
            assert r["l"] >= 0 and r["r"] <= r["vw"] and r["t"] >= 0 and r["b"] <= r["vh"], (n, width, r)
            assert all(r["top"]), (n, width, r)                                         # menu je nad plátny, ne pod nimi
            menu(chart, root, n, False)
    chart.set_viewport_size({"width": 1440, "height": 900})
    chart.wait_for_timeout(300)


@pytest.mark.parametrize("name", ALL)
def test_menu_follows_button_on_scroll(chart, name):
    """Nabídka je position: fixed – po posunu stránky se znovu umístí těsně pod (nebo nad) tlačítko."""
    root = _go(chart, name)
    menu(chart, root, "view")
    chart.mouse.move(5, 5)
    chart.mouse.wheel(0, 150)
    chart.wait_for_timeout(300)
    r = chart.evaluate("""s => { const m = document.querySelector(s + ' [data-testid="vw-menu"]'), b = document.querySelector(s + ' [data-testid="vw-m-view"]');
        const a = m.getBoundingClientRect(), c = b.getBoundingClientRect(); return { below: a.top - c.bottom, above: c.top - a.bottom, mr: a.right, br: c.right }; }""", root)
    assert abs(r["below"] - 4) < 3 or abs(r["above"] - 4) < 3, r
    chart.keyboard.press("Escape")
    chart.mouse.wheel(0, -300)


def test_cursor_indicator(chart):
    root = _go(chart, "trends")
    btn = chart.locator(f'{root} [data-testid="vw-m-cur"]')
    label = lambda: btn.inner_text().replace("▾", "").strip()      # noqa: E731
    on = lambda: "on" in (btn.get_attribute("class") or "").split()  # noqa: E731
    assert label() == "Cursors" and not on()
    menu(chart, root, "cur")
    chart.locator(f'{root} [data-a="cur"]').click()
    assert label() == "Cursors · A/B" and on()
    assert chart.locator(f'{root} [data-testid="vw-menu"]').count() == 1                    # nabídka zůstala otevřená
    assert chart.locator(f'{root} [data-a="cur"]').get_attribute("aria-checked") == "true"
    chart.locator(f'{root} [data-a="hcur"]').click()
    assert label() == "Cursors · A/B · Y₁/Y₂" and on()
    chart.locator(f'{root} [data-a="cur"]').click()
    assert label() == "Cursors · Y₁/Y₂" and on()
    assert chart.locator(f'{root} [data-testid="vw-menu"] [data-testid="hc-sig"]').count() == 1      # výběr signálu je v nabídce
    chart.locator(f'{root} [data-a="hcur"]').click()
    assert label() == "Cursors" and not on()
    assert chart.locator(f'{root} [data-testid="hc-sig"]').count() == 0
    chart.keyboard.press("Escape")
    menu(chart, root, "cur")
    chart.locator(f'{root} [data-a="cur"]').click()
    menu(chart, root, "cur", False)
    assert on()
    if SHOT:
        chart.locator(root).screenshot(path=os.path.join(SHOT, "chartmenus-trends-cursors.png"))
    menu(chart, root, "cur")
    chart.locator(f'{root} [data-a="cur"]').click()
    menu(chart, root, "cur", False)
    assert not on()


@pytest.mark.parametrize("name", ALL)
def test_export_menu(chart, name):
    root = _go(chart, name)
    menu(chart, root, "exp")
    assert chart.locator(f'{root} [data-a="csv_cur"]').is_disabled()                       # bez kurzorů A / B nejde
    items = chart.locator(f'{root} [data-testid="vw-menu"] [role="menuitem"]')
    assert items.count() == 3
    chart.keyboard.press("ArrowUp")                                                         # od začátku zpět: poslední (PNG)
    assert _active(chart)["mk"] == "png"
    chart.keyboard.press("ArrowUp")
    assert _active(chart)["mk"] == "csv_view"                                               # zakázaná položka se přeskočí
    with chart.expect_download() as d:
        chart.keyboard.press("Enter")
    assert d.value.suggested_filename.endswith(".csv")
    assert chart.locator(f'{root} [data-testid="vw-menu"]').count() == 0                    # akce nabídku zavřela
    assert _active(chart)["tid"] == "vw-m-exp"
    menu(chart, root, "cur")
    chart.locator(f'{root} [data-a="cur"]').click()
    menu(chart, root, "exp")
    assert chart.locator(f'{root} [data-a="csv_cur"]').is_enabled()
    menu(chart, root, "cur")                                                                # přepnutí na jinou nabídku zavře Export
    assert chart.locator(f'{root} [data-testid="vw-m-exp"]').get_attribute("aria-expanded") == "false"
    chart.locator(f'{root} [data-a="cur"]').click()
    menu(chart, root, "cur", False)


@pytest.mark.parametrize("name", ALL)
def test_mode_menu_events_and_keys(chart, name):
    root = _go(chart, name)
    menu(chart, root, "mode")
    m = chart.locator(f'{root} [data-testid="vw-menu"]')
    assert m.locator('[data-g="mode"] [role="menuitemradio"]').count() == 4
    assert m.locator('[data-a="evp"]').count() == (1 if name == "trends" else 0)               # události jen v Trendech
    assert m.locator('[data-a="evn"]').count() == (1 if name == "trends" else 0)
    assert _active(chart)["mk"] == "mode:pan"
    for k in ("mode:box", "mode:x", "mode:y"):
        chart.keyboard.press("ArrowDown")
        assert _active(chart)["mk"] == k
    chart.keyboard.press("ArrowDown")
    assert _active(chart)["mk"] == ("evp" if name == "trends" else "mode:pan")                  # pokračuje / zalamuje
    chart.keyboard.press("End")
    assert _active(chart)["mk"] == ("evn" if name == "trends" else "mode:y")
    chart.keyboard.press("Home")
    assert _active(chart)["mk"] == "mode:pan"
    chart.keyboard.press("ArrowUp")
    assert _active(chart)["mk"] == ("evn" if name == "trends" else "mode:y")
    if name == "trends":
        chart.keyboard.press("Enter")                                                          # předchozí / další událost zavře nabídku
        chart.wait_for_selector(f'{root} [data-testid="vw-menu"]', state="detached")
    else:
        chart.keyboard.press("Escape")


def test_view_menu_contents(chart):
    root = _go(chart, "model")
    menu(chart, root, "view")
    m = chart.locator(f'{root} [data-testid="vw-menu"]')
    for sel in ('[data-g="mpart"]', '[data-g="mrange"]', '[data-testid="mw-resid"]', '[data-g="ya"]', '[data-g="step"]', '[data-a="list"]', '[data-a="tab"]'):
        assert m.locator(sel).count() == 1, sel
    assert m.locator('[data-g="mpart"] [role="menuitemradio"]').count() == 3
    assert m.locator('[data-testid="mw-resid"]').get_attribute("role") == "menuitemcheckbox"
    # parametr nabídky: radio části modelu mění panel a nabídka zůstane
    m.locator('[data-g="mpart"] [data-v="mv"]').click()
    chart.wait_for_function("() => window.__pidView.model_view.state().panels[0].sigs.some(n => /MV part|část od MV/.test(n))")
    assert chart.locator(f'{root} [data-testid="vw-menu"]').count() == 1
    assert _active(chart)["mk"] == "mpart:mv"
    m.locator('[data-g="mpart"] [data-v="all"]').click()
    if SHOT:
        chart.locator(root).screenshot(path=os.path.join(SHOT, "chartmenus-model-view.png"))
    chart.keyboard.press("Escape")
    # Trendy a Diagnostika nemají modelové přepínače
    for n in ("trends", "diag"):
        r = _go(chart, n)
        menu(chart, r, "view")
        assert chart.locator(f'{r} [data-testid="vw-menu"] [data-g="mpart"]').count() == 0
        assert chart.locator(f'{r} [data-testid="vw-menu"] [data-a="list"]').count() == (0 if n == "trends" else 1)    # Trendy: seznam v pravém panelu
        chart.keyboard.press("Escape")


@pytest.mark.parametrize("name", ["trends", "model"])
def test_panel_menu(chart, name):
    root = _go(chart, name)
    if name == "trends" and chart.locator(f"{root} .pidv-panel").count() < 2:
        chart.locator('[data-testid="trd-layout"] button').nth(2).click()                    # panel na veličinu: víc panelů
        chart.wait_for_function("() => window.__pidView.trends_view.state().panels.length >= 2")
        chart.wait_for_timeout(300)
    n0 = chart.locator(f"{root} .pidv-panel").count()
    assert n0 >= 2
    first = chart.locator(f'{root} [data-testid="vw-m-panel"][data-pi="0"]')
    last = chart.locator(f'{root} [data-testid="vw-m-panel"][data-pi="{n0 - 1}"]')
    assert first.get_attribute("aria-haspopup") == "menu" and first.get_attribute("aria-label")
    assert chart.locator(f'{root} .pidv-ph [data-a="pup"]').count() == 0 and chart.locator(f"{root} .pidv-ph .pidv-x").count() == 0   # ↑ ↓ × zanikly
    first.click()
    m = chart.locator(f'{root} [data-testid="vw-menu"]')
    assert m.count() == 1 and m.get_attribute("role") == "menu"
    assert m.locator('[data-a="pup"]').is_disabled() and m.locator('[data-a="pdown"]').is_enabled()
    sigs0 = _state(chart, name)["panels"]
    if len(sigs0[0]["sigs"]) > 1:                                                          # společná osa jen u panelu s více signály
        sh = m.locator('[data-a="pshared"]')
        assert sh.get_attribute("role") == "menuitemcheckbox" and sh.get_attribute("aria-checked") == "false"
        sh.click()
        assert _state(chart, name)["panels"][0]["shared"] is True
        assert chart.locator(f'{root} [data-testid="vw-menu"]').count() == 1               # nabídka zůstala otevřená
        assert chart.locator(f'{root} [data-a="pshared"]').get_attribute("aria-checked") == "true"
        assert _active(chart)["mk"] == "pshared"
        chart.locator(f'{root} [data-a="pshared"]').click()
        assert _state(chart, name)["panels"][0]["shared"] is False
    # panel s jediným signálem nemá položku společné osy
    last.click()
    chart.wait_for_selector(f'{root} [data-testid="vw-menu"] [data-a="pup"]')
    assert chart.locator(f'{root} [data-testid="vw-menu"] [data-a="pdown"]').is_disabled()
    assert chart.locator(f'{root} [data-testid="vw-menu"] [data-a="pup"]').is_enabled()
    assert chart.locator(f'{root} [data-testid="vw-menu"]').count() == 1
    chart.keyboard.press("Escape")
    # přesun dolů: pořadí se prohodí, nabídka se zavře
    first.click()
    chart.locator(f'{root} [data-testid="vw-menu"] [data-a="pdown"]').click()
    chart.wait_for_selector(f'{root} [data-testid="vw-menu"]', state="detached")
    after = _state(chart, name)["panels"]
    assert after[1]["sigs"] == sigs0[0]["sigs"] and after[0]["sigs"] == sigs0[1]["sigs"]
    assert _active(chart)["tid"] == "vw-m-panel"
    # a zpět nahoru
    chart.locator(f'{root} [data-testid="vw-m-panel"][data-pi="1"]').click()
    chart.locator(f'{root} [data-testid="vw-menu"] [data-a="pup"]').click()
    assert [p["sigs"] for p in _state(chart, name)["panels"]][:2] == [sigs0[0]["sigs"], sigs0[1]["sigs"]]
    # odebrání panelu (signály zůstanou v seznamu)
    chart.locator(f'{root} [data-testid="vw-m-panel"][data-pi="1"]').click()
    chart.locator(f'{root} [data-testid="vw-menu"] [data-a="prem"]').click()
    chart.wait_for_function("([s, n]) => document.querySelectorAll(s + ' .pidv-panel').length === n - 1", arg=[root, n0])
    assert chart.locator(f'{root} [data-testid="vw-menu"]').count() == 0
    _reset_layout(chart, name)                                                              # výchozí rozložení pro další testy


def _reset_layout(pg, name):
    """Vrátí výchozí rozložení grafu (nastavení dview / mview / diagview), aby další testy viděly všechny panely."""
    key = {"trends": "dview", "model": "mview", "diag": "diagview"}[name]
    pg.wait_for_timeout(2000)                                                               # rozložení se ukládá s odstupem 1,5 s
    _call(pg.server, pg, "PATCH", B + "/settings", {key: None})
    pg.reload(wait_until="networkidle")
    pg.wait_for_selector('[data-testid="api-ok"]', timeout=20000)
    CH[name][1](pg)


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_contrast_menus(chart, theme):
    """Kontrast textu tlačítek lišty a položek nabídek ≥ 4,5 : 1 (světlý i tmavý vzhled; zvýrazněné tlačítko i nabídka)."""
    _tf._settings(chart)
    chart.select_option('select[aria-label="theme"]', theme)
    root = _go(chart, "model")
    chart.wait_for_function("([s, t]) => document.querySelector(s + ' .pidv').classList.contains('dark') === (t === 'dark')", arg=[root, theme], timeout=20000)
    menu(chart, root, "cur")
    chart.locator(f'{root} [data-a="cur"]').click()
    chart.locator(f'{root} [data-a="hcur"]').click()
    rows = []
    for n in ("cur", "view", "mode", "exp"):
        menu(chart, root, n)
        rows += chart.evaluate("""s => { const bg = (e) => { while (e) { const c = getComputedStyle(e).backgroundColor; if (!/rgba\\(.*, 0\\)$|transparent/.test(c)) return c; e = e.parentElement; } return 'rgb(255,255,255)'; };
          const m = document.querySelector(s + ' [data-testid="vw-menu"]'); const els = [...m.querySelectorAll('.pidv-mi:not(:disabled), .pidv-mt, .pidv-mh, .pidv-mk, select')];
          return els.map((e) => [e.className || e.tagName, getComputedStyle(e).color, bg(e), (e.innerText || '').slice(0, 24)]); }""", root)
        menu(chart, root, n, False)
    rows += chart.evaluate("""s => [...document.querySelectorAll(s + ' .pidv-bar button, ' + s + ' .pidv-bar .pidv-help, ' + s + ' .pidv-bar .pidv-lab')].map((e) => {
        let b = e, bg = getComputedStyle(b).backgroundColor;
        while (/rgba\\(.*, 0\\)$|transparent/.test(bg) && b.parentElement) { b = b.parentElement; bg = getComputedStyle(b).backgroundColor; }
        return [e.className || e.tagName, getComputedStyle(e).color, bg, (e.innerText || e.title || '').slice(0, 24)]; })""", root)
    assert len(rows) > 20
    bad = [r for r in rows if _contrast(_rgb(r[1]), _rgb(r[2])) < 4.5]
    assert not bad, bad
    if SHOT and theme == "dark":
        menu(chart, root, "view")
        chart.locator(root).screenshot(path=os.path.join(SHOT, "chartmenus-model-dark-view.png"))
        menu(chart, root, "view", False)
    menu(chart, root, "cur")
    chart.locator(f'{root} [data-a="cur"]').click()
    chart.locator(f'{root} [data-a="hcur"]').click()
    menu(chart, root, "cur", False)
    _tf._settings(chart)
    chart.select_option('select[aria-label="theme"]', "light")
