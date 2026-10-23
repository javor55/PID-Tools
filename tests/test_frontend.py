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


def _api(server, path, page):
    """GET na API s tokenem a ID prostoru stránky."""
    import json
    wid = page.evaluate("sessionStorage.getItem('pid.wid')")
    req = urllib.request.Request(server + path.format(wid=wid), headers={"X-PID-Token": TOKEN})
    return json.loads(urllib.request.urlopen(req, timeout=10).read())


def test_data_tab_viewer_columns_layout(page, server):
    """Data: ukázka → prohlížeč záznamu (sdílený viewer.js), kurzory a zoom, kvalita, sloupce, uložené rozložení."""
    import re
    page.locator('[data-tab="data"]').click()
    page.locator('[data-testid="load-demo"]').click()
    page.wait_for_selector(".pidv-panel canvas", timeout=30000)
    page.wait_for_timeout(500)
    assert page.locator(".pidv-panel").count() >= 3 and page.locator(".pidv-sig").count() >= 4
    assert "demo" in page.locator('[data-testid="data-info"]').inner_text()
    page.wait_for_selector('[data-testid="quality"] li')
    assert page.locator('[data-testid="quality"] li').count() == 2
    assert "AUTO" in page.locator('[data-testid="loopmode"]').inner_text()
    page.locator(".pidv-bar [data-a=cur]").click()
    page.wait_for_timeout(300)
    assert page.locator(".pidv-read tbody tr").count() >= 4
    page.locator(".pidv-bar [data-a=tab]").click()
    page.wait_for_timeout(300)

    def rows():
        txt = page.locator(".pidv-read .pidv-rhead").last.inner_text()
        return int("".join(ch for ch in re.match(r"[\d\s,.]+", txt).group(0) if ch.isdigit()))
    n0 = rows()
    box = page.locator(".pidv-panel canvas").nth(1).bounding_box()
    page.mouse.move(box["x"] + box["width"] * 0.6, box["y"] + box["height"] / 2)
    for _ in range(4):
        page.mouse.wheel(0, -120)
        page.wait_for_timeout(80)
    page.wait_for_timeout(300)
    assert rows() < n0
    page.wait_for_timeout(2500)                                   # viewer.js ukládá rozložení po 1,5 s klidu
    lay = _api(server, "/workspaces/{wid}/settings", page).get("dview")
    assert isinstance(lay, str) and "panels" in lay
    # sloupce: SP pryč a zpět
    page.select_option('[data-testid="col-sp"]', "—")
    page.wait_for_function("() => document.querySelector('[data-testid=\"col-sp\"]').value === '—'")
    page.wait_for_timeout(500)
    assert _api(server, "/workspaces/{wid}", page)["sp"] is None
    page.select_option('[data-testid="col-sp"]', "LIC101.SP")
    page.wait_for_timeout(500)
    assert _api(server, "/workspaces/{wid}", page)["sp"] == "LIC101.SP"


def test_data_file_upload(page, server):
    page.set_input_files('[data-testid="load-file"]', os.path.join(ROOT, "tests", "data", "ff_example.csv"))
    page.wait_for_function("() => (document.querySelector('[data-testid=\"data-info\"]')||{}).innerText?.includes('ff_example')")
    w = _api(server, "/workspaces/{wid}", page)
    assert w["fname"] == "ff_example.csv" and {"CV", "MV", "SP", "DV"} <= set(w["columns"])
    page.wait_for_selector(".pidv-panel canvas")
