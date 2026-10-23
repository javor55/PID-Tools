"""
Nové rozhraní (frontend/, React + TS) v prohlížeči nad API (M12): záložky, jazyk, vzhled, spojení s výpočty
a pracovní prostor, žádný požadavek mimo vlastní server, fonty IBM Plex. Potřebuje sestavené UI
(cd frontend && npm ci && npm run build → pidtools/api/ui); bez něj nebo bez Playwrightu se přeskočí.
"""
import os
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
TOKEN = "e2e-token"


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def server():
    if not os.path.exists(UI):
        pytest.skip("rozhraní není sestavené (cd frontend && npm run build)")
    port = _free_port()
    p = subprocess.Popen([sys.executable, "-m", "pidtools.api", "--port", str(port), "--token", TOKEN], cwd=ROOT,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    for _ in range(100):
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
        ctx = b.new_context(viewport={"width": 1440, "height": 900}, locale="en-US")
        pg = ctx.new_page()
        pg.requested = []
        pg.on("request", lambda r: pg.requested.append((r.method, r.url)))
        pg.goto(f"{server}/#token={TOKEN}", wait_until="networkidle")
        pg.wait_for_selector('[data-testid="api-ok"]', timeout=20000)
        yield pg
        b.close()


def test_shell_tabs_and_connection(page):
    tabs = page.locator('[role="tab"]')
    assert tabs.count() == 8
    assert tabs.first.inner_text() == "1 · Data"
    assert "version" in page.locator('[data-testid="api-ok"]').inner_text()
    assert any(m == "POST" and u.endswith("/workspaces") for m, u in page.requested)     # pracovní prostor
    assert "#token" not in page.url                                                       # token z adresy pryč
    page.locator('[data-tab="model"]').click()
    assert page.locator('[data-testid="tab-model"]').count() == 1


def test_language_and_theme(page):
    page.select_option('select[aria-label="Language"]', "cs")
    page.wait_for_function("() => document.querySelector('[data-tab=\"tuning\"]').innerText.includes('Ladění')")
    assert page.evaluate("document.documentElement.lang") == "cs"
    page.select_option('select[aria-label="theme"]', "dark")
    assert page.evaluate("document.documentElement.dataset.theme") == "dark"
    bg = page.evaluate("getComputedStyle(document.body).backgroundColor")
    assert bg == "rgb(11, 18, 32)"
    page.select_option('select[aria-label="theme"]', "light")
    page.select_option('select[aria-label="Jazyk"]', "en")


def test_offline_and_fonts(page, server):
    page.evaluate("document.fonts.ready")
    ext = [u for _, u in page.requested if not u.startswith((server, "data:", "blob:"))]
    assert not ext, ext[:10]
    assert page.evaluate("""() => [...document.fonts].some(f => f.family.replace(/"/g, '') === 'IBM Plex Sans'
                                   && f.status === 'loaded')""")


def test_api_still_needs_token(server):
    with pytest.raises(urllib.error.HTTPError):
        urllib.request.urlopen(server + "/i18n/en", timeout=5)
    assert urllib.request.urlopen(server + "/", timeout=5).status == 200      # rozhraní samo je veřejné
