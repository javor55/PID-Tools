"""
Data › Zdroje a smyčky (E4-B) v prohlížeči: soubory s časovou osou, posun času, společná mřížka, návrh smyček podle názvů
tagů, úprava rolí výběrem i přetažením sloupce, odebrání zdroje / smyčky a pokrytí nápovědy. Potřebuje sestavené UI;
bez podzáložky „Zdroje a smyčky“ (navigace E4-A) se testy přeskočí.
"""
import io

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("playwright.sync_api")
import test_frontend as _tf  # noqa: E402
import test_frontend_help as _help  # noqa: E402

server, page = _tf.server, _tf.page                      # fixtury serveru a prohlížeče

SUBTAB = "Zdroje a smyčky"


def _csv(df):
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode()


def _files():
    rng = np.random.default_rng(3)
    t0 = pd.Timestamp("2026-10-08 06:00:00")
    n = 720
    ta = t0 + pd.to_timedelta(np.arange(n) * 10.0, unit="s")                    # 2 h po 10 s
    sp = 50 + 5 * (np.arange(n) // 120 % 2)
    pv = sp + np.cumsum(rng.normal(0, .1, n))
    a = pd.DataFrame({"Time": ta, "TIC101.PV": pv, "TIC101.SP": sp, "TIC101.OUT": 40 + rng.normal(0, 1, n)})
    m = 120
    tb = t0 + pd.Timedelta(minutes=30) + pd.to_timedelta(np.arange(m) * 30.0, unit="s")     # od 6:30, po 30 s
    b = pd.DataFrame({"Time": tb, "FIC205.PV": 20 + rng.normal(0, .2, m), "FIC205.SP": 20.0, "FIC205.OUT": 55 + rng.normal(0, .5, m)})
    return {"historian.csv": _csv(a), "pcs7.csv": _csv(b)}


def _open(pg):
    """Otevře Data › Zdroje a smyčky; bez podzáložky v navigaci (a bez vložené obrazovky) vrátí False."""
    pg.evaluate("() => { localStorage.setItem('pid.tab', JSON.stringify('data')); localStorage.setItem('pid.lang', JSON.stringify('cs')); }")
    pg.reload(wait_until="networkidle")
    pg.wait_for_selector('[data-testid="api-ok"]', timeout=20000)
    tab = pg.get_by_text(SUBTAB, exact=True)
    if tab.count():
        tab.first.click()
    elif pg.locator('[data-testid="sources-main"]').count() == 0:
        return False
    pg.wait_for_selector('[data-testid="sources-main"]')
    return True


@pytest.fixture(scope="module")
def sources_page(page):
    if not _open(page):
        pytest.skip("podzáložka „Zdroje a smyčky“ ještě není v navigaci (E4-A)")
    return page


def test_empty_state_and_upload(sources_page):
    pg = sources_page
    assert pg.locator('[data-testid="src-empty"]').count() == 1
    files = _files()
    pg.set_input_files('[data-testid="src-add-file"]', [{"name": n, "mimeType": "text/csv", "buffer": b} for n, b in files.items()])
    pg.wait_for_selector('[data-testid="src-row-s2"]')
    assert pg.locator('[data-testid="src-table"] tbody tr').count() == 2
    assert pg.locator('[data-testid="src-bar-s1"]').count() == 1 and pg.locator('[data-testid="src-bar-s2"]').count() == 1
    assert "6:00" in pg.locator('[data-testid="src-range-s1"]').inner_text()
    assert "6:30" in pg.locator('[data-testid="src-range-s2"]').inner_text()
    assert "6:30" in pg.locator('[data-testid="src-span-note"]').inner_text()          # společný úsek začíná druhým souborem
    assert pg.locator('[data-testid="src-tl-common"]').count() == 1


def test_offset_moves_span_and_grid_mode(sources_page):
    pg = sources_page
    pg.fill('[data-testid="src-off-s2"]', "1")
    pg.keyboard.press("Enter")
    pg.wait_for_function("() => document.querySelector('[data-testid=\"src-range-s2\"]').innerText.includes('7:30')")
    pg.locator('[data-testid="src-grid-mode"] [data-value="union"]').click()
    pg.wait_for_function("() => document.querySelector('[data-testid=\"src-span-note\"]').innerText.includes('Sjednocení')")
    pg.locator('[data-testid="src-grid-mode"] [data-value="overlap"]').click()
    pg.wait_for_function("() => !document.querySelector('[data-testid=\"src-span-note\"]').innerText.includes('Sjednocení')")
    pg.fill('[data-testid="src-off-s2"]', "0")
    pg.keyboard.press("Enter")
    pg.wait_for_function("() => document.querySelector('[data-testid=\"src-range-s2\"]').innerText.includes('6:30')")


def test_bad_timezone_shows_error(sources_page):
    pg = sources_page
    pg.fill('[data-testid="src-tz-s1"]', "Mars/Olympus")
    pg.keyboard.press("Enter")
    pg.wait_for_selector('[data-testid="src-err"]')
    pg.fill('[data-testid="src-tz-s1"]', "")
    assert _open(pg)                                                            # po obnovení stránky zůstane vše uložené
    pg.wait_for_selector('[data-testid="src-row-s1"]')


def test_suggest_review_apply(sources_page):
    pg = sources_page
    pg.locator('[data-testid="src-suggest"]').click()
    pg.wait_for_selector('[data-testid="src-proposal"]')
    assert pg.locator('[data-testid="src-prop-table"] tbody tr').count() == 2
    n_before = pg.locator('[data-testid="src-loops-table"] tbody tr').count()
    pg.locator('[data-testid="src-prop-apply"]').click()
    pg.wait_for_selector('[data-testid="src-proposal"]', state="detached")
    rows = pg.locator('[data-testid="src-loops-table"] tbody tr')
    assert rows.count() >= n_before
    tags = pg.eval_on_selector_all('[data-testid^="src-tag-"]', "els => els.map(e => e.value)")
    assert "TIC101" in tags and "FIC205" in tags
    assert pg.locator('[data-testid="src-status-0"]').inner_text() != ""


def test_edit_role_select_and_drag(sources_page):
    pg = sources_page
    tags = pg.eval_on_selector_all('[data-testid^="src-tag-"]', "els => els.map(e => e.value)")
    i = tags.index("FIC205")
    sp = f'[data-testid="src-sp-{i}"]'
    key = pg.eval_on_selector(sp, "e => [...e.options].map(o => o.value).find(v => v.endsWith('FIC205.PV'))")
    key_sp = pg.eval_on_selector(sp, "e => [...e.options].map(o => o.value).find(v => v.endsWith('FIC205.SP'))")
    pg.select_option(sp, key)                                                   # SP smyčky = její PV (jen zkouška)
    pg.wait_for_function("(s) => document.querySelector(s).value.endsWith('FIC205.PV')", arg=sp)
    pg.select_option(sp, key_sp)
    pg.wait_for_function("(s) => document.querySelector(s).value.endsWith('FIC205.SP')", arg=sp)
    # přetažení sloupce z panelu do buňky DV smyčky
    pg.drag_and_drop('[data-testid="src-col-s1-TIC101.OUT"]', f'[data-testid="src-dv-{i}"]')
    pg.wait_for_selector(f'[data-testid="src-loop-{i}"] .src-chip')
    # klávesnicová alternativa: „Použít jako…“ aktivní smyčce
    pg.locator('[data-testid="src-col-s1-TIC101.PV"] select').select_option("sp")
    pg.wait_for_function("() => document.querySelectorAll('[data-testid=\"src-col-s1-TIC101.PV\"] .src-use').length >= 2")


def test_cascade_and_active(sources_page):
    pg = sources_page
    tags = pg.eval_on_selector_all('[data-testid^="src-tag-"]', "els => els.map(e => e.value)")
    a, b = tags.index("TIC101"), tags.index("FIC205")
    pg.select_option(f'[data-testid="src-casc-{a}"]', str(b))
    pg.wait_for_function("(i) => document.querySelector(`[data-testid=\"src-casc-${i}\"]`).value !== ''", arg=a)
    assert "SP ←" in pg.locator(f'[data-testid="src-loop-{b}"]').inner_text()
    pg.locator(f'[data-testid="src-activate-{b}"]').click()
    pg.wait_for_function("(i) => document.querySelector(`[data-testid=\"src-activate-${i}\"]`).getAttribute('aria-pressed') === 'true'", arg=b)


def test_remove_used_source_refused_then_loop_and_source_removed(sources_page):
    pg = sources_page
    pg.locator('[data-testid="src-del-s2"]').click()
    pg.wait_for_selector('[data-testid="src-err"]')                              # zdroj používá smyčka (409)
    n = pg.locator('[data-testid="src-loops-table"] tbody tr').count()
    tags = pg.eval_on_selector_all('[data-testid^="src-tag-"]', "els => els.map(e => e.value)")
    pg.locator(f'[data-testid="src-rm-{tags.index("FIC205")}"]').click()
    pg.wait_for_function("(n) => document.querySelectorAll('[data-testid=\"src-loops-table\"] tbody tr').length < n", arg=n)
    pg.locator('[data-testid="src-del-s2"]').click()
    pg.wait_for_selector('[data-testid="src-row-s2"]', state="detached")


def test_import_csv(sources_page):
    pg = sources_page
    csv = "loop,role,source,column\nX1,PV,historian.csv,TIC101.PV\nX1,MV,historian.csv,TIC101.OUT\n"
    pg.set_input_files('[data-testid="src-import-file"]', {"name": "map.csv", "mimeType": "text/csv", "buffer": csv.encode()})
    pg.wait_for_selector('[data-testid="src-proposal"]')
    assert "X1" in pg.locator('[data-testid="src-prop-table"]').inner_text()
    pg.locator('[data-testid="src-prop-close"]').click()
    pg.wait_for_selector('[data-testid="src-proposal"]', state="detached")


def test_help_coverage_sources(sources_page):
    pg = sources_page
    pg.locator('[data-testid="src-edit-s1"]').click()                           # i panel čtení
    _help._open_all_cards(pg)
    gaps = _help._gaps(pg, "sources")
    assert not gaps, gaps
    assert _help.COUNTS["sources"] >= 10, _help.COUNTS
