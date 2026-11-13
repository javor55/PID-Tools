"""
Rozhraní je ve výchozím stavu celé anglicky – i v prohlížeči s českým locale a s čistým nastavením aplikace. Projde
záložky, podzáložky a stránku nastavení s ukázkovými daty a hledá české znaky v textech, nápovědách (title),
popiscích (aria-label) a zástupných textech. Výjimkou jsou jen vlastní názvy jazyků ve výběru jazyka („Čeština“).
Po přepnutí na češtinu se texty změní. Potřebuje sestavené UI a Playwright, jinak se přeskočí.
"""
import os
import re
import socket
import subprocess
import sys
import time
import urllib.request

import pytest

pw = pytest.importorskip("playwright.sync_api")
pytest.importorskip("fastapi")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(ROOT, "pidtools", "api", "ui", "index.html")
TOKEN = "e2e-i18n"
CZ = re.compile(r"[áčďéěíňóřšťúůýžÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ]")

# texty + atributy, které vidí uživatel (bez výběru jazyka, kde jsou vlastní názvy jazyků)
SCAN = """() => {
  const out = [], skip = (e) => e.closest('select[data-lang-select], [data-testid="set-lang"], [data-testid="set-rep-lang"], [data-testid="rep-lang"]');
  const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let n;
  while ((n = w.nextNode())) {
    const t = n.textContent.trim(), p = n.parentElement;
    if (t && p && !skip(p) && !p.closest('script, style')) out.push(t);
  }
  document.querySelectorAll('[title], [aria-label], [placeholder]').forEach((e) => {
    if (skip(e)) return;
    for (const a of ['title', 'aria-label', 'placeholder']) { const v = e.getAttribute(a); if (v) out.push('@' + a + ': ' + v); }
  });
  return out;
}"""


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    if not os.path.exists(UI):
        pytest.skip("rozhraní není sestavené (cd frontend && npm run build)")
    port = _free_port()
    env = dict(os.environ, PIDTOOLS_CONFIG_DIR=str(tmp_path_factory.mktemp("cfg")))    # čisté nastavení aplikace
    p = subprocess.Popen([sys.executable, "-m", "pidtools.api", "--port", str(port), "--token", TOKEN], cwd=ROOT,
                         env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    for _ in range(150):
        try:
            urllib.request.urlopen(url + "/health", timeout=1)
            break
        except Exception:
            time.sleep(0.1)
    yield url
    p.terminate()
    p.wait(10)


@pytest.fixture(scope="module")
def page(server):
    with pw.sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception:
            exe = "/opt/pw-browsers/chromium"
            if not os.path.exists(exe):
                pytest.skip("Chromium pro Playwright není nainstalovaný")
            b = p.chromium.launch(executable_path=exe)
        ctx = b.new_context(viewport={"width": 1440, "height": 1000}, locale="cs-CZ")   # český prohlížeč
        pg = ctx.new_page()
        pg.goto(f"{server}/#token={TOKEN}", wait_until="networkidle")
        pg.wait_for_selector('[data-testid="api-ok"]', timeout=20000)
        yield pg
        b.close()


def _czech(page, where, found):
    for t in page.evaluate(SCAN):
        if CZ.search(t):
            found.setdefault(t, where)


def _click_all(page, sel, where, found):
    for i in range(page.locator(sel).count()):
        it = page.locator(sel).nth(i)
        try:
            if not it.is_visible():
                continue
            it.click(timeout=2000)
            page.wait_for_timeout(500)
            _czech(page, f"{where}/{(it.inner_text() or '')[:24]}", found)
        except Exception:                              # prvek zmizel po předchozím kliknutí
            pass


def test_english_by_default_everywhere(page):
    assert page.evaluate("document.documentElement.lang") == "en"
    page.locator('[data-tab="data"]').click()
    page.locator('[data-sub="quality"]').click()
    page.locator('[data-testid="src-seg"] [data-value="demo"]').click()
    page.wait_for_function("() => (document.querySelector('[data-testid=\"data-info\"]')||{}).innerText?.includes('demo')")
    found = {}
    _czech(page, "start", found)
    for tab in [t.get_attribute("data-tab") for t in page.locator("nav.tabs [data-tab], header [data-tab]").all()]:
        page.locator(f'[data-tab="{tab}"]').first.click()
        page.wait_for_timeout(1200)
        _czech(page, tab, found)
        _click_all(page, 'nav.subtabs [role="tab"], main [role="tab"]', tab, found)
        page.keyboard.press("Escape")
    page.locator('[data-testid="settings"] summary').click()
    page.locator('[data-testid="open-settings"]').click()
    page.wait_for_selector('[data-testid="settings-page"]')
    _click_all(page, '[data-testid^="settings-nav-"]', "settings", found)
    page.locator('[data-testid="settings-back"]').click()
    assert not found, "\n".join(f"[{w}] {t[:140]}" for t, w in found.items())


def test_switch_to_czech_and_back(page):
    page.locator('[data-tab="tuning"]').click()
    if not page.locator('[data-testid="settings"]').evaluate("e => e.open"):
        page.locator('[data-testid="settings"] summary').click()
    sel = page.locator('[data-testid="settings"] select[data-lang-select]')
    assert [o.get_attribute("value") for o in sel.locator("option").all()][:2] == ["en", "cs"]   # z /i18n, angličtina první
    sel.select_option("cs")
    page.wait_for_function("() => document.querySelector('[data-tab=\"tuning\"]').innerText.includes('Ladění')")
    assert page.evaluate("document.documentElement.lang") == "cs"
    sel.select_option("en")
    page.wait_for_function("() => document.querySelector('[data-tab=\"tuning\"]').innerText.includes('Tuning')")
    page.locator('[data-testid="settings"] summary').click()
