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


def _api_post(server, path, body, page):
    import json
    wid = page.evaluate("sessionStorage.getItem('pid.wid')")
    req = urllib.request.Request(server + path.format(wid=wid), data=json.dumps(body).encode(), method="POST",
                                 headers={"X-PID-Token": TOKEN, "Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=60).read())


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


def test_model_tab_identify(page, server):
    """Model: graf s úseky (sdílený trend.js), identifikace jako úloha, tabulka modelů, výběr, průběh modelu."""
    page.locator('[data-tab="data"]').click()
    page.locator('[data-testid="load-demo"]').click()
    page.wait_for_function("() => (document.querySelector('[data-testid=\"data-info\"]')||{}).innerText?.includes('demo')")
    page.locator('[data-tab="model"]').click()
    page.wait_for_selector('[data-testid="model-trend"] .pidw', timeout=20000)
    assert page.locator('[data-testid="no-model"]').count() == 1
    for c in ("P0D", "P2D", "I0D"):                         # rychlejší: jen P1D a I1D
        box = page.locator(f'[data-testid="chk-{c}"]')
        if box.is_checked():
            box.click()                                       # řízený prvek: stav se promítne po překreslení
            page.wait_for_function(f"() => !document.querySelector('[data-testid=\"chk-{c}\"]').checked")
    page.locator('[data-testid="identify"]').click()
    page.wait_for_selector('[data-testid="models"] tbody tr', timeout=120000)
    rows = page.locator('[data-testid="models"] tbody tr')
    assert rows.count() == 2
    m = _api(server, "/workspaces/{wid}/model", page)
    assert m["selected"] == "I1D" and abs(m["current"]["p"][0] - (-0.00394)) < 2e-4      # = zlatý případ demo
    page.locator('[data-testid="models"] input[aria-label="P1D"]').click()
    page.wait_for_function("() => document.querySelector('[data-testid=\"models\"] input[aria-label=\"P1D\"]').checked")
    page.wait_for_timeout(800)
    assert _api(server, "/workspaces/{wid}/model", page)["selected"] == "P1D"
    page.wait_for_timeout(1000)
    assert page.locator('[data-testid="model-trend"] svg').count() >= 2              # karty grafu (SVG)
    paths = page.evaluate("() => document.querySelectorAll('[data-testid=\"model-trend\"] svg path').length")
    assert paths >= 4                                                                 # PV, model, MV, porucha
    # úseky podle vstupů: přepínač v grafu → nastavení win_mode
    page.locator('[data-testid="model-trend"] .pidw-seg[data-g="mode"] button[data-v="inputs"]').click()
    page.wait_for_timeout(800)
    assert _api(server, "/workspaces/{wid}/settings", page)["win_mode"] == "inputs"
    page.locator('[data-testid="model-trend"] .pidw-seg[data-g="mode"] button[data-v="common"]').click()
    page.wait_for_timeout(500)


def test_model_edit_refit_validation_uncertainty(page, server):
    """Model 2: zafixovaný θ a dofitování, návrat k nafitovaným hodnotám, ověření modelu, nejistota (P1D z dema)."""
    def wait_jobs():
        page.wait_for_timeout(500)
        page.wait_for_function("() => !document.querySelector('.jobs .job')", timeout=120000)
        page.wait_for_timeout(800)
    page.wait_for_selector('[data-testid="params"]')
    assert "FIT" in page.locator('[data-testid="validation"]').inner_text()
    th = page.locator('[data-testid="ed-ed|P1D|2"]')
    th.fill("30")
    th.press("Enter")
    page.locator('[data-testid="fx-fx|P1D|2"]').click()
    page.wait_for_timeout(600)
    page.locator('[data-testid="refit"]').click()
    wait_jobs()
    p = _api(server, "/workspaces/{wid}/model", page)["current"]["p"]
    assert abs(p[2] - 30.0) < 1e-6
    page.locator('[data-testid="fx-fx|P1D|2"]').click()
    page.locator('[data-testid="reset"]').click()
    page.wait_for_timeout(800)
    st = _api(server, "/workspaces/{wid}/settings", page)
    assert abs(st["ed|P1D|2"] - 30.0) < 1e-6                 # návrat = hodnoty posledního (dofitovaného) výsledku
    page.locator('[data-testid="uncertainty"] input.num').fill("3")
    page.locator('[data-testid="unc-run"]').click()
    wait_jobs()
    page.wait_for_selector('[data-testid="unc-table"] tbody tr')
    assert page.locator('[data-testid="unc-table"] tbody tr').count() == 3


def test_tuning_tab(page, server):
    """Ladění: sady s robustností, návrh SIMC, zápis do Set 2, odezva scénáře a ukazatele, nastavení bloku."""
    page.locator('[data-tab="tuning"]').click()
    page.wait_for_selector('[data-testid="sets"] tbody tr')
    assert page.locator('[data-testid="sets"] tbody tr').count() == 2
    page.select_option('[data-testid="method"]', "SIMC")
    page.locator('[data-testid="calc"]').click()
    page.wait_for_selector('[data-testid="sug-values"]')
    sug = _api_post(server, "/workspaces/{wid}/tuning/suggest", {"method": "SIMC"}, page)
    assert f"{sug['Kc']:.4g}".rstrip("0").rstrip(".") in page.locator('[data-testid="sug-values"]').inner_text()
    page.locator('[data-testid="to-set2"]').click()
    page.wait_for_timeout(800)
    s2 = next(s for s in _api(server, "/workspaces/{wid}/tuning", page)["sets"] if s["n"] == 2)
    assert abs(s2["gain"] - sug["Kc"]) < 1e-9 and abs(s2["ti"] - sug["Ti"]) < 1e-9
    page.wait_for_selector('[data-testid="kpis"] tbody tr')
    assert page.locator('[data-testid="kpis"] tbody tr').count() == 3          # Set 1, Set 2, návrh
    page.wait_for_selector('[data-testid="resp-pv"] path', timeout=20000)
    assert page.locator('[data-testid="resp-pv"] path').count() >= 4
    page.locator('[data-testid="set-samp"]').fill("2")
    page.locator('[data-testid="set-samp"]').press("Enter")
    page.wait_for_timeout(600)
    assert _api(server, "/workspaces/{wid}/settings", page)["samp"] == 2.0
    page.locator('[data-testid="set-samp"]').fill("1")
    page.locator('[data-testid="set-samp"]').press("Enter")
