"""
Deník ladění (E10) v prohlížeči: Projekt › Deník ladění – uložení verze, seznam a detail, změna stavu, poznámka, příloha,
porovnání dvou verzí, „Otevřít tento stav“ a report z verze; sekce a jazyk reportu. Potřebuje sestavené UI.
"""
import json
import os
import urllib.request

import pytest

pw = pytest.importorskip("playwright.sync_api")
import test_frontend as _tf  # noqa: E402

TOKEN = _tf.TOKEN
server, page = _tf.server, _tf.page                      # fixtury serveru a prohlížeče
HERE = os.path.dirname(os.path.abspath(__file__))


def _call(server, page, method, path, body=None):
    wid = page.evaluate("sessionStorage.getItem('pid.wid')")
    req = urllib.request.Request(server + path.format(wid=wid), method=method,
                                 data=None if body is None else json.dumps(body).encode(),
                                 headers={"X-PID-Token": TOKEN, "Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=120).read() or b"null")


@pytest.fixture(scope="module")
def prepared(page, server):
    """Prostor s projektem tic001 (model, sady) a otevřeným Deníkem ladění."""
    wid = page.evaluate("sessionStorage.getItem('pid.wid')")
    text = open(os.path.join(HERE, "golden", "tic001.json"), "rb").read()
    req = urllib.request.Request(server + f"/workspaces/{wid}/project", method="PUT", data=text,
                                 headers={"X-PID-Token": TOKEN, "Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=60).read()
    page.reload(wait_until="networkidle")
    page.wait_for_selector('[data-testid="api-ok"]', timeout=20000)
    page.locator('[data-tab="project"]').click()
    page.locator('[data-testid="proj-sub"] [data-value="journal"]').click()
    return page


def test_empty_journal_and_save_versions(prepared, server):
    pg = prepared
    pg.wait_for_selector('[data-testid="jr-empty"]', timeout=10000)
    pg.locator('[data-testid="jr-label"]').fill("První návrh")
    pg.locator('[data-testid="jr-save"]').click()
    pg.wait_for_selector('[data-testid="jr-row"]', timeout=10000)
    assert "v1" in pg.locator('[data-testid="jr-row"]').first.inner_text()
    assert pg.locator('[data-testid="jr-detail"] [data-testid="jr-pill"]').first.get_attribute("data-status") == "draft"
    assert pg.locator('[data-testid="jr-verified"]').get_attribute("data-ok") == "true"
    # změna nastavení smyčky a druhá verze
    g = _call(server, pg, "GET", "/workspaces/{wid}/settings")["set2_gain"]
    _call(server, pg, "PATCH", "/workspaces/{wid}/settings", {"set2_gain": g * 2})
    pg.locator('[data-testid="jr-save"]').click()
    pg.wait_for_function("() => document.querySelectorAll('[data-testid=\"jr-row\"]').length === 2", timeout=10000)
    assert pg.locator('[data-testid="jr-count"]').inner_text().startswith("2")


def test_status_note_attachment(prepared, tmp_path):
    pg = prepared
    pg.locator('[data-testid="jr-status"] [data-value="deployed"]').click()
    pg.wait_for_function("() => document.querySelector('[data-testid=\"jr-detail\"] [data-testid=\"jr-pill\"]').dataset.status === 'deployed'", timeout=10000)
    assert pg.locator('[data-testid="jr-hist"] div').count() == 2
    pg.locator('[data-testid="jr-note-in"]').fill("Po výpadku čerpadla")
    pg.locator('[data-testid="jr-note-add"]').click()
    pg.wait_for_selector('[data-testid="jr-note"]', timeout=10000)
    f = tmp_path / "zmena.txt"
    f.write_text("protokol o změně")
    pg.locator('[data-testid="jr-att-in"]').set_input_files(str(f))
    pg.wait_for_selector('[data-testid="jr-att"]', timeout=10000)
    assert "zmena.txt" in pg.locator('[data-testid="jr-att"]').inner_text()
    pill = pg.locator('[data-testid="jr-row"][data-sid="j2"] [data-testid="jr-pill"]')
    assert pill.get_attribute("data-status") == "deployed"


def test_compare_restore_and_report(prepared, server):
    pg = prepared
    pg.locator('[data-testid="jr-cmp-sel"]').select_option(index=1)
    pg.wait_for_selector('[data-testid="jr-compare"]', timeout=10000)
    diffs = pg.locator('[data-testid="jr-diff"]').all_inner_texts()
    assert any("set2_gain" in t for t in diffs)
    pg.locator('[data-testid="jr-cmp-close"]').click()
    # obnova první verze: nastavení se vrátí, předchozí stav je uložen jako nová verze
    g1 = _call(server, pg, "GET", "/workspaces/{wid}/journal/j1")["content"]["sets"]["set2_gain"]
    pg.locator('[data-testid="jr-row"][data-sid="j1"]').click()
    pg.locator('[data-testid="jr-restore"]').click()
    pg.wait_for_selector('[data-testid="jr-msg"]', timeout=20000)
    assert _call(server, pg, "GET", "/workspaces/{wid}/settings")["set2_gain"] == pytest.approx(g1)
    assert pg.locator('[data-testid="jr-row"]').count() == 3
    # report z verze se zobrazí v náhledu
    pg.locator('[data-testid="jr-report"]').click()
    pg.wait_for_selector('[data-testid="report-frame"]', timeout=60000)
    body = pg.frame_locator('[data-testid="report-frame"]').locator("body")     # protokol do rámce přichází zprávou
    pw.expect(body).to_contain_text("v1", timeout=60000)
    assert body.locator("h2").count() >= 1


def test_report_sections_and_language(prepared):
    pg = prepared
    pg.locator('[data-testid="proj-sub"] [data-value="report"]').click()
    for s in ("data", "controller", "scenario", "field", "history"):
        pg.wait_for_selector(f'[data-testid="rep-sec-{s}"]', timeout=10000)
    assert pg.locator('[data-testid="rep-sec-model"]').is_checked() and not pg.locator('[data-testid="rep-sec-data"]').is_checked()
    pg.locator('[data-testid="rep-sec-history"]').check()
    pg.locator('[data-testid="rep-lang"] [data-value="cs"]').click()
    pg.locator('[data-testid="report-build"]').click()
    pg.wait_for_selector('[data-testid="report-frame"]', timeout=60000)
    pw.expect(pg.frame_locator('[data-testid="report-frame"]').locator("body")).to_contain_text("Historie změn", timeout=60000)
    pg.locator('[data-testid="rep-lang"] [data-value="en"]').click()
    pg.locator('[data-testid="report-build"]').click()
    pw.expect(pg.frame_locator('[data-testid="report-frame"]').locator("body")).to_contain_text("Change history", timeout=60000)
    pg.locator('[data-testid="report-summary"]').click()
    pw.expect(pg.frame_locator('[data-testid="report-frame"]').locator("body")).to_contain_text("Loop summary report", timeout=60000)


def test_journal_controls_have_help(prepared):
    pg = prepared
    pg.locator('[data-testid="proj-sub"] [data-value="journal"]').click()
    bad = pg.evaluate("""() => [...document.querySelectorAll('[data-testid="journal"] button, [data-testid="journal"] select, [data-testid="journal"] input, [data-testid="jr-new"] input, [data-testid="jr-new"] textarea')]
        .filter((e) => !(e.title || e.getAttribute('aria-label') || e.closest('[title]') || e.closest('label')?.title)).map((e) => e.outerHTML.slice(0, 80))""")
    assert bad == []
