"""
Nápověda a průvodce v novém rozhraní (E2) v prohlížeči: dialog Průvodce (F1, karty, akce kontrolního seznamu, hledání)
a test pokrytí nápovědy – každý viditelný ovládací prvek s popiskem má „?“ (LabelHelp) nebo neprázdný `title`;
prochází všechny záložky a všechny struktury APC. Potřebuje sestavené UI (cd frontend && npm run build).
"""
import json
import time
import urllib.request

import pytest

pytest.importorskip("playwright.sync_api")
import test_frontend as _tf  # noqa: E402

TOKEN = _tf.TOKEN
import test_frontend_controllers as _tfc  # noqa: E402
server, page = _tfc.server, _tf.page                     # server s dočasnou složkou vlastních regulátorů a fixtura prohlížeče

APC_TECHS = ["cascade", "ff", "decouple", "override", "smith", "gainsched", "gs_er", "split", "vpc", "ratio", "rga"]
TABS = ["data", "model", "tuning", "apc", "live", "project"]
SUBS = ["sources", "trends", "quality", "diag-all", "diag-detail"]       # podzáložky Data


def _call(server, page, method, path, body=None):
    wid = page.evaluate("sessionStorage.getItem('pid.wid')")
    req = urllib.request.Request(server + path.format(wid=wid), method=method,
                                 data=None if body is None else json.dumps(body).encode(),
                                 headers={"X-PID-Token": TOKEN, "Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=120).read() or b"null")


def _job(server, page, path):
    j = _call(server, page, "POST", path, {})
    for _ in range(600):
        st = _call(server, page, "GET", f"/jobs/{j['id']}")
        if st["state"] not in ("queued", "running"):
            assert st["state"] == "done", st
            return
        time.sleep(0.2)
    raise AssertionError("job timeout")


@pytest.fixture(scope="module")
def prepared(page, server):
    """Demo, model aktivní smyčky a druhá smyčka s modelem (aby šly zobrazit i struktury se dvěma smyčkami)."""
    page.locator('[data-tab="data"]').click()
    page.locator('[data-sub="quality"]').click()
    page.locator('[data-testid="src-seg"] [data-value="demo"]').click()
    page.wait_for_function("() => (document.querySelector('[data-testid=\"data-info\"]')||{}).innerText?.includes('demo')")
    _call(server, page, "PATCH", "/workspaces/{wid}/settings", {"chosen": ["P1D", "I1D"]})
    _job(server, page, "/workspaces/{wid}/identify")
    _call(server, page, "PUT", "/workspaces/{wid}/model/select", {"code": "P1D"})        # samoregulační: Smith, gain scheduling
    _call(server, page, "POST", "/workspaces/{wid}/loops", {})
    _call(server, page, "PUT", "/workspaces/{wid}/loops/active", {"index": 1})
    _job(server, page, "/workspaces/{wid}/identify")
    _call(server, page, "PUT", "/workspaces/{wid}/model/select", {"code": "P1D"})
    _call(server, page, "PUT", "/workspaces/{wid}/loops/active", {"index": 0})
    page.reload(wait_until="networkidle")
    page.wait_for_selector('[data-testid="api-ok"]', timeout=20000)
    return page


# ---- dialog Průvodce
def test_guide_dialog_tabs_checklist_and_action(prepared):
    pg = prepared
    pg.locator('[data-tab="tuning"]').click()
    pg.locator('[data-testid="help-btn"]').click()
    dlg = pg.locator('[data-testid="help-dialog"]')
    assert dlg.evaluate("e => e.open")
    assert "Guide" in dlg.locator("h2").inner_text()
    assert dlg.locator(".g-tabs button").count() == 4
    pg.wait_for_selector(".g-steps li")
    assert pg.locator(".g-steps li").count() >= 5
    # kontrolní seznam: stavy a tlačítka akcí
    pg.locator('[data-testid="guide-tab-checklist"]').click()
    pg.wait_for_selector('[data-testid="guide-checklist"] li')
    oks = {li.get_attribute("data-ok") for li in pg.locator('[data-testid="guide-checklist"] li').all()}
    assert oks <= {"ok", "warn", "todo"} and "ok" in oks
    assert pg.locator('[data-testid="guide-action"]').count() >= 1
    # tabulka „Která metoda kdy“ se vykreslí jako HTML tabulka
    pg.locator('[data-testid="guide-tab-tables"]').click()
    pg.wait_for_selector('[data-testid="guide-tables"] table')
    assert pg.locator('[data-testid="guide-tables"] thead th').first.inner_text() == "Method"
    assert pg.locator('[data-testid="guide-tables"] tbody tr').count() >= 5
    pg.locator('[data-testid="guide-tab-glossary"]').click()
    assert pg.locator('[data-testid="guide-glossary"] dt').count() >= 10
    # akce: Sada 1 → záložka Ladění, zaostřený vstup sady 1 (stav z API: demo má sady vyplněné, proto zkusíme první akci)
    pg.locator('[data-testid="guide-tab-checklist"]').click()
    act = pg.locator('[data-testid="guide-action"]').first
    act.click()
    assert not dlg.evaluate("e => e.open")


def test_guide_f1_escape_search_and_switch_tab_action(prepared):
    pg = prepared
    pg.locator('[data-tab="data"]').click()
    pg.locator('[data-sub="quality"]').click()
    dlg = pg.locator('[data-testid="help-dialog"]')
    pg.keyboard.press("F1")
    assert dlg.evaluate("e => e.open")
    pg.wait_for_selector(".g-steps li")
    pg.fill('[data-testid="guide-search"]', "stiction")
    pg.wait_for_selector('[data-testid="guide-results"]')
    assert "tiction" in pg.locator('[data-testid="guide-results"]').inner_text()
    pg.fill('[data-testid="guide-search"]', "qqqqzzzz")
    pg.wait_for_selector('[data-testid="guide-none"]')
    pg.fill('[data-testid="guide-search"]', "")
    pg.keyboard.press("Escape")
    assert not dlg.evaluate("e => e.open")
    # akce kontrolního seznamu Data › rozsahy → záložka Ladění, rozbalená karta Blok PIDConL a zaostřený NormPV
    pg.keyboard.press("F1")
    pg.locator('[data-testid="guide-tab-checklist"]').click()
    pg.wait_for_selector('[data-testid="guide-checklist"] li')
    btn = pg.locator('[data-testid="guide-checklist"] li:has-text("NormPV") [data-testid="guide-action"]')
    assert btn.count() == 1
    btn.click()
    assert not dlg.evaluate("e => e.open")
    pg.wait_for_selector('[data-tab="tuning"][aria-selected="true"]')
    pg.wait_for_function("() => document.activeElement && document.activeElement.dataset.testid === 'set-pv_hi'", timeout=10000)
    assert pg.locator('[data-testid="card-block"]').evaluate("e => e.open")


def test_guide_translates_with_language(prepared):
    pg = prepared
    pg.evaluate("() => localStorage.setItem('pid.lang', JSON.stringify('cs'))")
    pg.reload(wait_until="networkidle")
    pg.wait_for_selector('[data-testid="api-ok"]', timeout=20000)
    pg.locator('[data-tab="model"]').click()
    pg.locator('[data-testid="help-btn"]').click()
    pg.wait_for_selector(".g-steps li")
    assert "Průvodce" in pg.locator('[data-testid="help-dialog"] h2').inner_text()
    pg.locator('[data-testid="guide-tab-tables"]').click()
    pg.wait_for_selector('[data-testid="guide-tables"] table')
    assert "Model" in pg.locator('[data-testid="guide-tables"] thead th').first.inner_text()
    pg.keyboard.press("Escape")
    pg.evaluate("() => localStorage.setItem('pid.lang', JSON.stringify('en'))")
    pg.reload(wait_until="networkidle")
    pg.wait_for_selector('[data-testid="api-ok"]', timeout=20000)


def test_label_help_bubble_opens_and_closes(prepared):
    pg = prepared
    pg.locator('[data-tab="tuning"]').click()
    btn = pg.locator("aside.side button.qm").first
    btn.scroll_into_view_if_needed()
    btn.click()
    assert pg.locator('[role="tooltip"]').count() == 1
    assert pg.locator('[role="tooltip"]').inner_text().strip() == btn.get_attribute("aria-label").strip()
    pg.keyboard.press("Escape")
    assert pg.locator('[role="tooltip"]').count() == 0


# ---- pokrytí nápovědy
FIND_GAPS = """() => {
  const vis = (e) => !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length);
  const filled = (e) => !!e && (e.getAttribute('title') || '').trim() !== '';
  const name = (c) => {
    const lab = c.closest('label');
    const txt = (lab ? lab.innerText : '') || c.getAttribute('aria-label') || c.getAttribute('placeholder') || '';
    return (c.tagName.toLowerCase() + '[' + (c.type || '') + '] ' + (c.dataset.testid || '') + ' "' + txt.trim().slice(0, 50) + '"');
  };
  const qm = (e) => !!e && !!e.querySelector('.qm');
  const gaps = [];
  let n = 0;
  for (const c of document.querySelectorAll('main input, main select, main textarea, aside input, aside select, aside textarea, .settings-page input, .settings-page select, .settings-page textarea')) {
    if (!vis(c) || c.type === 'hidden' || c.type === 'file' || c.closest('.pidv, .pidw, .pidv-root')) continue;
    n++;
    const labs = [...(c.labels || [])];
    const lab = c.closest('label');
    const row = c.closest('.trow, .field, .apc-check, .chk-help, .mrow');
    const th = c.closest('td, th') && c.closest('table') ? c.closest('table').querySelector('th[title], th .qm') : null;
    const ok = filled(c) || filled(lab) || qm(lab) || labs.some((l) => filled(l) || qm(l)) || qm(row) || !!th || filled(row)
      || filled(c.closest('.chk-help'));
    if (!ok) gaps.push(name(c));
  }
  for (const g of document.querySelectorAll('main div.seg, aside div.seg, main .segs, aside .segs, .settings-page div.seg')) {
    if (!vis(g) || g.closest('.pidv, .pidw, .pidv-root')) continue;
    n++;
    const bts = [...g.querySelectorAll('button')];
    const ok = filled(g) || bts.length > 0 && bts.every(filled) || qm(g.parentElement) || g.parentElement.classList.contains('seg-help')
      || qm(g.closest('.trow, .field, .mrow')) || filled(g.closest('.trow, .field, .mrow'));
    if (!ok) gaps.push('seg ' + (g.dataset.testid || '') + ' "' + (g.getAttribute('aria-label') || '') + '"');
  }
  return { gaps, n };
}"""


COUNTS = {}


def _gaps(pg, name):
    """Mezery v pokrytí nápovědy na aktuální obrazovce; počet zkontrolovaných prvků se hlídá (test nesmí projít naprázdno)."""
    pg.wait_for_timeout(700)
    r = pg.evaluate(FIND_GAPS)
    COUNTS[name] = r["n"]
    return r["gaps"]


def _open_all_cards(pg):
    """Rozbalí sbalené karty pravého panelu, aby se zkontrolovaly i jejich prvky."""
    pg.evaluate("() => document.querySelectorAll('details.scard:not([open]), main details:not([open])').forEach((d) => { d.open = true; })")
    pg.wait_for_timeout(300)


def test_help_coverage_all_tabs(prepared):
    pg = prepared
    report = {}
    for tab in TABS:
        pg.locator(f'[data-tab="{tab}"]').click()
        if tab == "data":
            pg.locator('[data-sub="quality"]').click()
        pg.wait_for_timeout(800)
        if tab == "apc":
            continue
        _open_all_cards(pg)
        report[tab] = _gaps(pg, tab)
    pg.locator('[data-tab="data"]').click()
    for sub in SUBS:                                                    # podzáložky Data (Zdroje, Trendy, Kvalita, Diagnostika)
        if sub.startswith("diag"):
            pg.locator('[data-sub="diag"]').click()
            pg.locator(f'[data-testid="diag-sub"] [data-value="{sub}"]').click()
        else:
            pg.locator(f'[data-sub="{sub}"]').click()
        pg.wait_for_timeout(800)
        _open_all_cards(pg)
        report[sub] = _gaps(pg, sub)
    pg.locator('[data-sub="quality"]').click()
    bad = {k: v for k, v in report.items() if v}
    assert not bad, json.dumps(bad, indent=1, ensure_ascii=False)
    assert all(COUNTS[t] >= 3 for t in ("data", "model", "tuning", "live", "diag-detail", "diag-all", "project")), COUNTS
    assert COUNTS["tuning"] >= 20, COUNTS


@pytest.mark.parametrize("tech", APC_TECHS)
def test_help_coverage_apc_structures(prepared, tech):
    pg = prepared
    pg.locator('[data-tab="apc"]').click()
    pg.locator(f'[data-testid="apc-tech-{tech}"]').click()
    pg.wait_for_selector(f'[data-testid="apc-{tech}"]')
    pg.wait_for_timeout(1500)
    _open_all_cards(pg)
    gaps = _gaps(pg, tech)
    assert COUNTS[tech] >= (0 if tech == "rga" else 1), tech            # RGA nemá vstupy
    assert not gaps, json.dumps({tech: gaps}, indent=1, ensure_ascii=False)


def _sweep_select(pg, sel, label):
    """Projde všechny hodnoty výběru (jiné metody / režimy ukazují jiná pole) a vrátí mezery; nakonec vrátí první hodnotu."""
    gaps = {}
    vals = pg.eval_on_selector_all(f"{sel} option", "els => els.map(e => e.value)")
    orig = pg.eval_on_selector(sel, "e => e.value")
    for v in vals:
        pg.select_option(sel, v)
        pg.wait_for_timeout(500)
        _open_all_cards(pg)
        g = _gaps(pg, f"{label}={v}")
        if g:
            gaps[f"{label}={v}"] = g
    pg.select_option(sel, orig)
    pg.wait_for_timeout(300)
    return gaps


def _sweep_seg(pg, seg, label):
    gaps = {}
    vals = pg.eval_on_selector_all(f'[data-testid="{seg}"] button', "els => els.map(e => e.dataset.value)")
    cur = pg.eval_on_selector(f'[data-testid="{seg}"]', "e => e.querySelector('[aria-pressed=true]').dataset.value")
    for v in vals:
        pg.locator(f'[data-testid="{seg}"] [data-value="{v}"]').click()
        pg.wait_for_timeout(500)
        _open_all_cards(pg)
        g = _gaps(pg, f"{label}={v}")
        if g:
            gaps[f"{label}={v}"] = g
    pg.locator(f'[data-testid="{seg}"] [data-value="{cur}"]').click()
    pg.wait_for_timeout(300)
    return gaps


def test_help_coverage_variants(prepared):
    """Pole, která se objeví až při jiné metodě / režimu (průměrování, optimalizace, PID, kaskáda z dat, Smith …)."""
    pg = prepared
    bad = {}
    pg.locator('[data-tab="tuning"]').click()
    pg.wait_for_selector('[data-testid="method"]')
    bad |= _sweep_select(pg, '[data-testid="method"]', "method")
    pg.select_option('[data-testid="method"]', "OPT")
    pg.wait_for_timeout(500)
    bad |= _sweep_select(pg, '[data-testid="set-opt_crit"]', "opt_crit")
    bad |= _sweep_seg(pg, "set-ctype", "ctype")
    pg.select_option('[data-testid="method"]', "SIMC")
    bad |= _sweep_seg(pg, "tun-view", "view")
    pg.locator('[data-testid="tun-view"] [data-value="time"]').click()
    for tech, sel in (("cascade", "set-cas_src"), ("smith", "set-apc_sm_method"), ("gainsched", "set-gs_m"),
                      ("split", "split-mode"), ("ratio", "ratio-src"), ("decouple", "dec-dtype"), ("override", "ov-sel")):
        pg.locator('[data-tab="apc"]').click()
        pg.locator(f'[data-testid="apc-tech-{tech}"]').click()
        pg.wait_for_selector(f'[data-testid="apc-{tech}"]')
        pg.wait_for_timeout(1200)
        bad |= _sweep_select(pg, f'[data-testid="{sel}"]', f"{tech}:{sel}")
    pg.locator('[data-testid="apc-tech-ff"]').click()
    pg.wait_for_selector('[data-testid="apc-ff"]')
    pg.wait_for_timeout(800)
    bad |= _sweep_seg(pg, "ff-dyn-0", "ff-dyn")
    assert not bad, json.dumps(bad, indent=1, ensure_ascii=False)


def test_help_coverage_settings_controllers(prepared):
    """Nastavení › Obecné a Regulátory: knihovna (všechny záložky detailu), editor (skládání i text) a test použitelnosti."""
    pg = prepared
    pg.locator('[data-testid="settings"] summary').click()
    pg.locator('[data-testid="open-settings"]').click()
    report = {}
    pg.locator('[data-testid="settings-nav-general"]').click()
    report["general"] = _gaps(pg, "set-general")
    pg.locator('[data-testid="settings-nav-controllers"]').click()
    pg.wait_for_selector('[data-testid="rg-item-isa_ideal"]')
    pg.locator('[data-testid="rg-item-isa_ideal"]').click()
    for t in ("eq", "par", "fn", "io", "test"):
        pg.locator(f'[data-testid="rg-tab-{t}"]').click()
        report[f"lib-{t}"] = _gaps(pg, f"set-lib-{t}")
    pg.locator('[data-testid="rg-make-custom"]').click()
    pg.wait_for_selector('[data-testid="reg-editor"]')
    report["editor-compose"] = _gaps(pg, "set-ed-compose")
    pg.locator('[data-testid="rg-mode"] [data-value="text"]').click()
    pg.wait_for_selector('[data-testid="rg-source"]')
    report["editor-text"] = _gaps(pg, "set-ed-text")
    pg.locator('[data-testid="rg-save"]').click()
    pg.wait_for_selector('[data-testid="rg-msg"].ok')
    pg.locator('[data-testid="rg-full-test"]').click()
    pg.wait_for_selector('[data-testid="rg-checks"] li', timeout=60000)
    report["test"] = _gaps(pg, "set-test")
    bad = {k: v for k, v in report.items() if v}
    assert not bad, json.dumps(bad, indent=1, ensure_ascii=False)
    assert COUNTS["set-general"] >= 2 and COUNTS["set-ed-compose"] >= 5 and COUNTS["set-ed-text"] >= 1, COUNTS
    pg.locator('[data-testid="settings-back"]').click()
