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
        pg.errors = []                                      # výjimky JS na stránce (kontroluje poslední test)
        pg.on("pageerror", lambda e: pg.errors.append(str(e)))
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


def _api_raw(server, path, page):
    """GET na API s tokenem – surová data (binární balík signálů)."""
    wid = page.evaluate("sessionStorage.getItem('pid.wid')")
    req = urllib.request.Request(server + path.format(wid=wid), headers={"X-PID-Token": TOKEN})
    return urllib.request.urlopen(req, timeout=30).read()


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


def test_model_residuals_and_dist_structs(page, server):
    """Model 2: rezidua (průběh, ACF, CCF) = API, porovnání struktur poruchy = API, výběr jiné struktury."""
    _track(page)
    page.locator('[data-tab="model"]').click()
    page.wait_for_selector('[data-testid="residuals"] [data-testid="acf-chart"]', timeout=30000)
    v = _api(server, "/workspaces/{wid}/model/validation", page)["metrics"]
    for key in ("acf", "ccf"):
        page.wait_for_function(f"() => document.querySelectorAll('[data-testid=\"{key}-chart\"] rect').length === {len(v[key])}")
        assert page.locator(f'[data-testid="{key}-chart"] line.bound').count() == 2
        assert abs(float(page.locator(f'[data-testid="{key}-chart"]').get_attribute("data-bound")) - v["bound"]) < 1e-9
        bad = sum(abs(x) > v["bound"] for x in v[key])
        assert page.locator(f'[data-testid="{key}-chart"] rect[data-bad="1"]').count() == bad
    import numpy as np
    from pidtools.app import signalpack
    meta, sig = signalpack.unframe(_api_raw(server, "/workspaces/{wid}/model/curves", page))
    n_res = int(np.isfinite(sig["residual"][1]).sum())
    page.wait_for_selector('[data-testid="resid-chart"] path')
    assert int(page.locator('[data-testid="resid-chart"]').get_attribute("data-n")) == n_res > 0
    assert page.locator('[data-testid="resid-verdict"]').inner_text().strip()
    # porovnání struktur poruchy
    m = _api(server, "/workspaces/{wid}/model", page)
    code = m["selected"]
    d = next(r for r in m["results"] if r["code"] == code)["dists"][0]
    assert len(d["cmp"]) == 5
    page.wait_for_selector('[data-testid="dist-cmp-0"]')
    for c in d["cmp"]:
        if c["fit"] is not None:
            _wait_cell(page, f'[data-testid="dist-fit-0-{c["struct"]}"]', c["fit"], rel=1e-3)
    assert page.locator('[data-testid="dist-cmp-0"] tr[data-current="1"]').get_attribute("data-struct") == d["struct"]
    other = next(c["struct"] for c in d["cmp"] if c["fit"] is not None and c["struct"] != d["struct"])
    page.locator(f'[data-testid="dist-use-0-{other}"]').click()
    _until(lambda: next(r for r in _api(server, "/workspaces/{wid}/model", page)["results"]
                        if r["code"] == code)["dists"][0]["struct"] == other)
    page.wait_for_selector(f'[data-testid="dist-cmp-0"] tr[data-struct="{other}"][data-current="1"]')
    assert _api(server, "/workspaces/{wid}/settings", page)[f"dsel|{code}|0"] == other
    # zpět na identifikovanou strukturu (sdílený stav testů: demo + identifikovaný model)
    page.locator('[data-testid="reset"]').click()
    _until(lambda: next(r for r in _api(server, "/workspaces/{wid}/model", page)["results"]
                        if r["code"] == code)["dists"][0]["struct"] == d["ident"])
    page.wait_for_selector(f'[data-testid="dist-cmp-0"] tr[data-struct="{d["ident"]}"][data-current="1"]')
    _quiet(page)


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
    page.wait_for_function("() => document.querySelectorAll('[data-testid=\"kpis\"] tbody tr').length === 3",
                           timeout=20000)                                       # Set 1, Set 2, návrh
    page.wait_for_selector('[data-testid="resp-pv"] path', timeout=20000)
    assert page.locator('[data-testid="resp-pv"] path').count() >= 4
    page.locator('[data-testid="set-samp"]').fill("2")
    page.locator('[data-testid="set-samp"]').press("Enter")
    page.wait_for_timeout(600)
    assert _api(server, "/workspaces/{wid}/settings", page)["samp"] == 2.0
    page.locator('[data-testid="set-samp"]').fill("1")
    page.locator('[data-testid="set-samp"]').press("Enter")


def test_tuning_scenario_compare_frequency(page, server):
    """Ladění 2: předvolba scénáře a vlastní událost, porovnání metod (úloha) s převzetím řádku, frekvenční analýza."""
    page.locator('[data-tab="tuning"]').click()
    page.wait_for_selector('[data-testid="scen-kind"]')
    page.select_option('[data-testid="scen-kind"]', "in")
    page.wait_for_function("() => document.querySelector('[data-testid=\"scen-kind\"]').value === 'in'")
    assert _api(server, "/workspaces/{wid}/scenario", page)["kind"] == "in"
    n = page.locator('[data-testid="scen-row"]').count()
    page.locator('[data-testid="scen-add"]').click()
    page.wait_for_function(f"() => document.querySelectorAll('[data-testid=\"scen-row\"]').length === {n + 1}")
    sc = _api(server, "/workspaces/{wid}/scenario", page)
    assert sc["kind"] == "custom" and len(sc["rows"]) == n + 1 and sc["rows"][-1][1] == "IN"
    page.locator(f'[data-testid="scen-{n}-3"]').fill("2.5")
    page.locator(f'[data-testid="scen-{n}-3"]').press("Enter")
    page.wait_for_timeout(600)
    assert _api(server, "/workspaces/{wid}/scenario", page)["rows"][-1][3] == 2.5
    page.select_option('[data-testid="scen-kind"]', "sp")                     # zpět na výchozí

    page.wait_for_selector('[data-testid="freq-table"] tbody tr', timeout=20000)
    assert page.locator('[data-testid="freq-table"] tbody tr').count() >= 2
    assert page.locator('[data-testid="freq-mag"] path').count() >= 2
    assert page.locator('[data-testid="freq-nyq"] path').count() >= 2     # sady + kružnice Ms + kříž −1

    page.locator('[data-testid="cmp-run"]').click()
    page.wait_for_selector('[data-testid="cmp-row"]', timeout=120000)
    assert page.locator('[data-testid="cmp-row"]').count() >= 3
    page.locator('[data-testid="cmp-row"]').first.click()
    page.wait_for_selector('[data-testid="sug-values"]')
    page.wait_for_function("() => document.querySelectorAll('[data-testid=\"freq-table\"] tbody tr').length === 3",
                           timeout=20000)                                       # Set 1, Set 2, návrh


def test_tuning_spread(page, server):
    """Simulace na variantách z nejistoty modelu (nejistota spočtená v testu záložky Model): šedé průběhy v grafu PV."""
    page.locator('[data-tab="tuning"]').click()
    page.wait_for_selector('[data-testid="resp-pv"] path', timeout=20000)
    n0 = page.locator('[data-testid="resp-pv"] path').count()
    box = page.locator('[data-testid="sim-spread"]')
    assert box.is_enabled()
    box.click()
    page.wait_for_function(f"() => document.querySelectorAll('[data-testid=\"resp-pv\"] path').length > {n0}",
                           timeout=30000)
    box.click()
def test_live_tab(page, server):
    """Živá simulace (M18): sdílené live_ui.js, běh a čas simulace, zápis laděného zesílení do sady 2."""
    page.locator('[data-tab="live"]').click()
    page.wait_for_selector('[data-testid="live-sim"] canvas#cv', timeout=20000)
    assert page.locator('[data-testid="live-sim"] .pidlive').count() == 1
    assert page.locator("aside.side").count() == 0                                 # panel si kreslí komponenta
    page.locator("#run").click()
    page.wait_for_function("() => /Pause|Pozastavit/.test(document.querySelector('#run').textContent)")
    page.wait_for_function("() => /t = [1-9]/.test(document.querySelector('#tnow').textContent)", timeout=20000)
    t1 = page.locator("#tnow").inner_text()
    page.wait_for_timeout(1200)
    assert page.locator("#tnow").inner_text() != t1                                  # čas simulace běží
    assert page.locator("#read").inner_text().strip()
    page.locator("#run").click()                                                    # pauza
    page.locator("details:has(#tune) > summary").click()
    g0 = next(s for s in _api(server, "/workspaces/{wid}/tuning", page)["sets"] if s["n"] == 2)["gain"]
    gain = page.locator("#tune input.num").first
    gain.fill(f"{g0 * 1.5:.6g}")
    gain.dispatch_event("change")
    page.locator("#apply").click()
    page.wait_for_function(
        "async ([a]) => { const r = await fetch('/workspaces/' + sessionStorage.getItem('pid.wid') + '/tuning', "
        "{headers: {'X-PID-Token': '" + TOKEN + "'}}); const s = (await r.json()).sets.find((x) => x.n === 2); "
        "return Math.abs(s.gain - a) < 1e-9 * Math.max(1, Math.abs(a)); }", arg=[float(f"{g0 * 1.5:.6g}")])
    s2 = next(s for s in _api(server, "/workspaces/{wid}/tuning", page)["sets"] if s["n"] == 2)
    assert s2["gain"] == pytest.approx(float(f"{g0 * 1.5:.6g}"))
    page.locator('[data-tab="data"]').click()                                       # odpojení komponenty bez chyby
    page.wait_for_selector('[data-testid="tab-data"]')


def _rel(a, b, tol=2e-3):
    return abs(a - b) <= tol * max(1.0, abs(b))


def _wait_num(page, testid, want, rel=2e-3, timeout=20000):
    """Počká, až číslo v prvku odpovídá očekávané hodnotě (dotazy drží do přepočtu předchozí výsledek)."""
    page.wait_for_function(
        "([id, w, r]) => { const e = document.querySelector(`[data-testid=\"${id}\"]`);"
        " if (!e) return false; const v = parseFloat(e.innerText.replace(',', '.'));"
        " return Math.abs(v - w) <= r * Math.max(1, Math.abs(w)); }", arg=[testid, want, rel], timeout=timeout)


def test_apc_tab_recommendations_ff_smith(page, server):
    """APC (M19, 1. část): doporučení, dopředná vazba (zapnutí, úprava, reset, simulace), Smith = API, optimalizace."""
    page.locator('[data-tab="apc"]').click()
    page.wait_for_selector('[data-testid="apc-reco"]', timeout=20000)
    reco = _api(server, "/workspaces/{wid}/apc/recommend", page)
    page.wait_for_function("() => document.querySelector('[data-testid=\"apc-reco\"] li, [data-testid=\"apc-reco-none\"]')")
    assert page.locator('[data-testid="apc-reco"] li').count() == len(reco)
    for r in reco:
        assert r["text"] in page.locator(f'[data-testid="apc-reco-{r["kind"]}"]').first.inner_text()
    assert page.locator('[data-testid="apc-techs"] [role="tab"]').count() == 11
    # dopředná vazba
    page.locator('[data-testid="apc-tech-ff"]').click()
    ff = _api(server, "/workspaces/{wid}/apc/ff", page)
    if not ff["dists"]:
        page.wait_for_selector('[data-testid="ff-none"]')
    else:
        d0 = ff["dists"][0]
        page.wait_for_selector('[data-testid="ff-dist-0"]')
        assert not d0["design"]["use"] and page.locator('[data-testid="ff-edited-0"]').count() == 0
        page.locator('[data-testid="ff-use-0"]').click()
        page.locator('[data-testid="ff-dyn-0"]').click()
        page.wait_for_function("() => document.querySelectorAll('[data-testid=\"ff-kpis\"] tbody tr').length === 3",
                               timeout=20000)
        page.wait_for_selector('[data-testid="ff-values-0"] tbody tr', timeout=20000)    # hodnoty pro PIDConL
        cur = _api(server, "/workspaces/{wid}/apc/ff", page)["dists"][0]
        assert cur["design"]["use"] and cur["design"]["dyn"]
        page.locator('[data-testid="ff-gain-0"]').fill("2.5")
        page.locator('[data-testid="ff-gain-0"]').press("Enter")
        page.wait_for_selector('[data-testid="ff-edited-0"]')
        cur = _api(server, "/workspaces/{wid}/apc/ff", page)["dists"][0]
        assert cur["design"]["gain"] == 2.5 and cur["edited"]
        sim = _api_post(server, "/workspaces/{wid}/apc/ff/simulate", {"dist": 0}, page)
        want = sim["kpis"]["dynamic"]["iae"]
        page.wait_for_function(
            "(w) => { const t = document.querySelector('[data-testid=\"ff-kpi-dynamic\"] td:nth-child(2)');"
            " return t && Math.abs(parseFloat(t.innerText) - w) <= 2e-3 * Math.max(1, Math.abs(w)); }", arg=want,
            timeout=20000)
        assert page.locator('[data-testid="ff-pv"] path').count() == 3
        page.locator('[data-testid="ff-reset-all"]').click()
        page.wait_for_function("() => !document.querySelector('[data-testid=\"ff-edited-0\"]')")
        cur = _api(server, "/workspaces/{wid}/apc/ff", page)["dists"][0]
        assert cur["design"]["gain"] == pytest.approx(cur["defaults"]["gain"]) and not cur["edited"]
        page.locator('[data-testid="ff-use-0"]').click()
        page.locator('[data-testid="ff-dyn-0"]').click()
        page.wait_for_selector('[data-testid="ff-all-off"]')
        assert not _api(server, "/workspaces/{wid}/apc/ff", page)["dists"][0]["design"]["use"]
    # Smithův prediktor: hodnoty = API
    page.locator('[data-testid="apc-tech-smith"]').click()
    page.wait_for_selector('[data-testid="sm-kc"]', timeout=20000)
    sm = _api(server, "/workspaces/{wid}/apc/smith", page)
    assert sm["inputs"]["method"] == "SIMC" and sm["opt_ready"]
    assert _rel(float(page.locator('[data-testid="sm-kc"]').inner_text()), sm["controller"]["Kc"])
    assert _rel(float(page.locator('[data-testid="sm-ti"]').inner_text()), sm["controller"]["Ti"])
    assert f"{sm['ratio']:.2f}" in page.locator('[data-testid="sm-ratio"]').inner_text().replace(",", ".")
    if sm["integ"]:
        assert page.locator('[data-testid="sm-template"]').count() == 0
    else:
        page.wait_for_selector('[data-testid="sm-template"] tbody tr')
        assert page.locator('[data-testid="sm-template"] tbody tr').count() == len(sm["rows"])
        assert page.locator('[data-testid="sm-general"] tbody tr').count() == len(sm["general_rows"])
        assert page.locator('[data-testid="sm-op"]').count() == 1
    page.wait_for_function("() => document.querySelectorAll('[data-testid=\"sm-kpis\"] tbody tr').length === 2",
                           timeout=30000)
    sim = _api_post(server, "/workspaces/{wid}/apc/smith/simulate", {}, page)
    for k in ("pid", "smith"):
        got = page.locator(f'[data-testid="sm-kpi-{k}"] td:nth-child(2)').inner_text()
        assert _rel(float(got), sim["kpis"][k]["iae_sp"], 5e-3)
    assert page.locator('[data-testid="sm-pv"] path').count() == 3
    # změna typu regulátoru přes nastavení → regulátor z API
    page.select_option('[data-testid="set-apc_sm_ct"]', "PID")
    page.wait_for_timeout(1200)
    assert _api(server, "/workspaces/{wid}/settings", page)["apc_sm_ct"] == "PID"
    sm = _api(server, "/workspaces/{wid}/apc/smith", page)
    _wait_num(page, "sm-kc", sm["controller"]["Kc"])            # do načtení zůstává vidět předchozí hodnota
    page.select_option('[data-testid="set-apc_sm_ct"]', "PI")
    # robustní optimalizace jako úloha
    page.select_option('[data-testid="set-apc_sm_method"]', "OPT")
    page.wait_for_selector('[data-testid="sm-opt"]')
    page.wait_for_timeout(800)
    if not _api(server, "/workspaces/{wid}/apc/smith", page)["opt_ready"]:
        page.wait_for_selector('[data-testid="sm-need-opt"]')
        page.locator('[data-testid="sm-opt"]').click()
    page.wait_for_function("() => document.querySelector('[data-testid=\"sm-opt\"]') && "
                           "!document.querySelector('[data-testid=\"sm-opt\"]').disabled", timeout=180000)
    sm = _api(server, "/workspaces/{wid}/apc/smith", page)
    assert sm["opt_ready"] and sm["inputs"]["method"] == "OPT"
    _wait_num(page, "sm-kc", sm["controller"]["Kc"])
    page.select_option('[data-testid="set-apc_sm_method"]', "SIMC")
    page.wait_for_timeout(800)


def _wait_sel(page, sel, want, rel=5e-3, timeout=30000):
    """Jako _wait_num, ale pro libovolný CSS selektor (buňka tabulky)."""
    page.wait_for_function(
        "([s, w, r]) => { const e = document.querySelector(s); if (!e) return false;"
        " const v = parseFloat(e.innerText.replace(',', '.')); return Math.abs(v - w) <= r * Math.max(1, Math.abs(w)); }",
        arg=[sel, want, rel], timeout=timeout)


def _set_num(page, testid, value):
    page.locator(f'[data-testid="{testid}"]').fill(str(value))
    page.locator(f'[data-testid="{testid}"]').press("Enter")


def _api_send(server, method, path, body, page):
    """PATCH / PUT / POST s tělem JSON (odpověď JSON)."""
    import json
    wid = page.evaluate("sessionStorage.getItem('pid.wid')")
    req = urllib.request.Request(server + path.format(wid=wid), data=json.dumps(body).encode(), method=method,
                                 headers={"X-PID-Token": TOKEN, "Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=60).read() or b"null")


def _until(fn, timeout=30.0):
    """Počká, až podmínka platí (stav na serveru po změně z rozhraní); vrátí její hodnotu."""
    t0 = time.time()
    while True:
        v = fn()
        if v:
            return v
        assert time.time() - t0 < timeout, "podmínka nenastala"
        time.sleep(0.1)


def _job_done(server, page, job, timeout=240):
    st = _until(lambda: (lambda s: s if s["state"] not in ("queued", "running") else None)(
        _api(server, f"/jobs/{job['id']}", page)), timeout)
    assert st["state"] == "done", st


def _wnum(page, testid, want, rel=2e-3, timeout=90000):
    _wait_num(page, testid, want, rel, timeout)


def _wait_cell(page, selector, want, rel=2e-3, timeout=60000):
    """Počká, až číslo v buňce odpovídá API (dotazy drží do přepočtu předchozí výsledek)."""
    page.wait_for_function(
        "([s, w, r]) => { const e = document.querySelector(s); if (!e) return false;"
        " const v = parseFloat(e.innerText.replace(',', '.')); return Math.abs(v - w) <= r * Math.max(1, Math.abs(w)); }",
        arg=[selector, want, rel], timeout=timeout)


def _track(page):
    """Počítá rozpracované požadavky stránky (pro `_quiet`); stačí zavolat jednou."""
    if not hasattr(page, "inflight"):
        page.inflight = 0

        def add(d):
            page.inflight += d
        page.on("request", lambda r: add(1))
        page.on("requestfinished", lambda r: add(-1))
        page.on("requestfailed", lambda r: add(-1))


def _quiet(page, timeout=60.0):
    """Počká, až rozhraní nemá rozpracované požadavky (výpočty serveru nepřetékají do dalšího testu a do ukončení)."""
    t0, calm = time.time(), 0
    while calm < 3:
        page.wait_for_timeout(200)                       # zpracování událostí stránky; o správnosti nerozhoduje
        calm = calm + 1 if page.inflight <= 0 else 0
        assert time.time() - t0 < timeout, "rozhraní stále čeká na server"


def _setting(server, page, key):
    """Hodnota klíče nastavení (levný dotaz: nezatěžuje výpočty techniky, které si žádá rozhraní)."""
    return _api(server, "/workspaces/{wid}/settings", page).get(key)


def _apc_tech(page, tech):
    page.locator('[data-tab="apc"]').click()
    page.locator(f'[data-testid="apc-tech-{tech}"]').click()


def _fill_enter(page, testid, value):
    page.locator(f'[data-testid="{testid}"]').fill(str(value))
    page.locator(f'[data-testid="{testid}"]').press("Enter")


def test_apc_split_vpc_ratio_rga(page, server):
    """APC (M19, další techniky): split range, VPC, poměr a RGA = API; úprava modelu druhého členu; RGA s jednou smyčkou."""
    page.locator('[data-tab="apc"]').click()
    # split range
    page.locator('[data-testid="apc-tech-split"]').click()
    page.wait_for_selector('[data-testid="split-val-b"]', timeout=20000)
    info = _api(server, "/workspaces/{wid}/apc/split", page)
    d = info["design"]
    _wait_num(page, "split-val-b", d["bstar"])
    _wait_num(page, "split-val-corr", d["corr"])
    assert page.locator('[data-testid="split-checks"] li').count() == len(d["checks"])
    assert f"{d['bstar']:.1f}".replace(".", ",") in page.locator('[data-testid="split-result"]').inner_text().replace(".", ",")
    sim = _api_post(server, "/workspaces/{wid}/apc/split/simulate", info["defaults"], page)
    page.wait_for_selector('[data-testid="split-kpi-new"]', timeout=30000)
    _wait_sel(page, '[data-testid="split-kpi-new"] td:nth-child(2)', sim["kpis"]["new"]["iae"])
    _wait_sel(page, '[data-testid="split-kpi-now"] td:nth-child(3)', sim["kpis"]["now"]["maxdev"])
    assert page.locator('[data-testid="split-pv"] path').count() == 3
    assert page.locator('[data-testid="split-valves"] path').count() == 2
    # úprava zesílení ventilu A → návrh podle API
    va = d["valve_a"]["values"]
    assert page.locator('[data-testid="split-va-reset"]').is_disabled()
    _set_num(page, "split-va-0", va[0] * 2)
    body = dict(info["defaults"], valve_a=[va[0] * 2, *va[1:]])
    d2 = _api_post(server, "/workspaces/{wid}/apc/split/design", body, page)
    assert d2["bstar"] != pytest.approx(d["bstar"])
    _wait_num(page, "split-val-b", d2["bstar"])
    sim2 = _api_post(server, "/workspaces/{wid}/apc/split/simulate", body, page)
    _wait_sel(page, '[data-testid="split-kpi-new"] td:nth-child(2)', sim2["kpis"]["new"]["iae"])
    page.locator('[data-testid="split-va-reset"]').click()
    _wait_num(page, "split-val-b", d["bstar"])
    # VPC
    page.locator('[data-testid="apc-tech-vpc"]').click()
    page.wait_for_selector('[data-testid="vpc-val-kc"]', timeout=20000)
    info = _api(server, "/workspaces/{wid}/apc/vpc", page)
    _wait_num(page, "vpc-val-kc", info["design"]["controller"]["Kc"])
    _wait_num(page, "vpc-val-ti", info["design"]["controller"]["Ti"])
    _wait_num(page, "vpc-val-tc", info["design"]["tc"])
    assert page.locator('[data-testid="vpc-checks"] li').count() == len(info["design"]["checks"])
    sim = _api_post(server, "/workspaces/{wid}/apc/vpc/simulate", info["defaults"], page)
    page.wait_for_selector('[data-testid="vpc-kpi-on"]', timeout=30000)
    _wait_sel(page, '[data-testid="vpc-kpi-on"] td:nth-child(2)', sim["kpis"]["on"]["iae"])
    _wait_sel(page, '[data-testid="vpc-kpi-on"] td:nth-child(4)', sim["kpis"]["on"]["reserve"])
    assert page.locator('[data-testid="vpc-mv1"] path').count() == 3
    g2 = info["defaults"]["mv2"]
    _set_num(page, "vpc-mv2-0", g2[0] * 1.5)
    body = dict(info["defaults"], mv2=[g2[0] * 1.5, *g2[1:]])
    d2 = _api_post(server, "/workspaces/{wid}/apc/vpc/design", body, page)
    _wait_num(page, "vpc-val-kc", d2["controller"]["Kc"])
    _set_num(page, "vpc-sp", 60)
    _wait_num(page, "vpc-val-sp", 60)
    sim2 = _api_post(server, "/workspaces/{wid}/apc/vpc/simulate", dict(body, sp=60), page)
    _wait_sel(page, '[data-testid="vpc-kpi-on"] td:nth-child(3)', sim2["kpis"]["on"]["at_lim"])
    page.locator('[data-testid="vpc-reset"]').click()
    page.locator('[data-testid="vpc-mv2-reset"]').click()
    _wait_num(page, "vpc-val-sp", 50)
    _wait_num(page, "vpc-val-kc", info["design"]["controller"]["Kc"])
    # poměrová regulace (jedna smyčka → jen ruční model vzduchu)
    page.locator('[data-testid="apc-tech-ratio"]').click()
    page.wait_for_selector('[data-testid="ratio-kpi-cross"]', timeout=30000)
    info = _api(server, "/workspaces/{wid}/apc/ratio", page)
    assert info["design"]["sources"] == [] and page.locator('[data-testid="ratio-src"] option').count() == 1
    sim = _api_post(server, "/workspaces/{wid}/apc/ratio/simulate", info["defaults"], page)
    _wait_sel(page, '[data-testid="ratio-kpi-cross"] td:nth-child(2)', sim["kpis"]["cross"]["lam_min"])
    _wait_sel(page, '[data-testid="ratio-kpi-plain"] td:nth-child(3)', sim["kpis"]["plain"]["t_rich"])
    assert page.locator('[data-testid="ratio-checks"] li').count() == len(info["design"]["checks"])
    assert page.locator('[data-testid="ratio-flows"] path').count() == 4
    _set_num(page, "ratio-R", 2)
    _wait_num(page, "ratio-val-R", 2)
    sim2 = _api_post(server, "/workspaces/{wid}/apc/ratio/simulate", dict(info["defaults"], R=2.0), page)
    _wait_sel(page, '[data-testid="ratio-kpi-plain"] td:nth-child(2)', sim2["kpis"]["plain"]["lam_min"])
    air = info["defaults"]["air"]
    _set_num(page, "ratio-air-1", air[1] * 3)
    sim3 = _api_post(server, "/workspaces/{wid}/apc/ratio/simulate", dict(info["defaults"], R=2.0, air=[air[0], air[1] * 3, *air[2:]]), page)
    assert sim3["kpis"]["cross"] != sim2["kpis"]["cross"]
    _wait_sel(page, '[data-testid="ratio-kpi-cross"] td:nth-child(4)', sim3["kpis"]["cross"]["iae"])
    page.locator('[data-testid="ratio-reset"]').click()
    page.locator('[data-testid="ratio-air-reset"]').click()
    _wait_num(page, "ratio-val-R", 1.2)
    _wait_sel(page, '[data-testid="ratio-kpi-cross"] td:nth-child(2)', sim["kpis"]["cross"]["lam_min"])
    # RGA s jednou smyčkou: kontrolní seznam, co chybí
    page.locator('[data-testid="apc-tech-rga"]').click()
    page.wait_for_selector('[data-testid="rga-notready"]', timeout=20000)
    rga = _api(server, "/workspaces/{wid}/apc/rga", page)
    assert rga["ready"] is False
    assert page.locator('[data-testid="rga-checks"] li').count() == len(rga["checks"])
    assert page.locator('[data-testid="rga-k"]').count() == 0
    for c in rga["checks"]:
        assert c["text"] in page.locator('[data-testid="rga-checks"]').inner_text()
    page.locator('[data-testid="apc-tech-ff"]').click()


def test_apc_cascade(page, server):
    """APC: kaskáda – hodnoty = API, ruční model a reset, model vnitřní smyčky z dat (úloha), jediná smyčka v projektu."""
    _track(page)
    url = "/workspaces/{wid}/apc/cascade"
    _apc_tech(page, "cascade")
    page.wait_for_selector('[data-testid="cas-inner-kc"]', timeout=60000)
    cas = _api(server, url, page)
    assert cas["inputs"]["source"] == "manual" and cas["inputs"]["loops"] == []
    assert page.locator('[data-testid="apc-loop-cascade"]').count() == 0
    _wnum(page, "cas-inner-kc", cas["inner"]["Kc"])
    _wnum(page, "cas-outer-kc", cas["outer"]["Kc"])
    _wnum(page, "cas-t63", cas["t63"])
    _wnum(page, "cas-sep", cas["separation"])
    assert page.locator('[data-testid="cas-values"] tbody tr').count() == len(cas["rows"])
    assert page.locator('[data-testid="apc-checks"] li').count() == len(cas["checks"])
    assert page.locator('[data-testid="cas-impl"]').count() == 1 and (page.locator('[data-testid="cas-sep-warn"]').count() == 1) == \
        cas["sep_warn"]
    sim = _api_post(server, url + "/simulate", {}, page)
    if sim["ok"]:
        _wnum(page, "cas-sim-iae", sim["iae_outer"])
        page.wait_for_function("() => document.querySelectorAll('[data-testid=\"cas-pv\"] path').length === 2", timeout=60000)
    else:
        page.wait_for_selector('[data-testid="cas-unstable"]', timeout=60000)
    # ruční model vnitřní smyčky: změna K přes nastavení → ladění z API; reset vrátí původní hodnoty
    _fill_enter(page, "set-cas_k", 2)
    _until(lambda: _setting(server, page, "cas_k") == 2)
    new = _api(server, url, page)
    assert new["inner"]["Kc"] != pytest.approx(cas["inner"]["Kc"])
    _wnum(page, "cas-inner-kc", new["inner"]["Kc"])
    page.locator('[data-testid="cas-reset-manual"]').click()
    _until(lambda: _setting(server, page, "cas_k") == 1.0)
    _wnum(page, "cas-inner-kc", cas["inner"]["Kc"])
    # model vnitřní smyčky z dat (úloha): do spuštění identifikace chybí model
    page.select_option('[data-testid="set-cas_src"]', "data")
    page.wait_for_selector('[data-testid="cas-need-inner"]', timeout=60000)
    ws = _api(server, "/workspaces/{wid}", page)
    page.select_option('[data-testid="cas-ipv"]', ws["pv"])
    page.select_option('[data-testid="cas-imv"]', ws["mv"])
    page.locator('[data-testid="cas-fit"]').click()
    page.wait_for_selector('[data-testid="cas-fit-info"]', timeout=180000)
    cas = _api(server, url, page)
    assert cas["inner_fit"] and cas["inputs"]["source"] == "data"
    assert f"{cas['inner_fit']['fit']:.1f}" in page.locator('[data-testid="cas-fit-info"]').inner_text().replace(",", ".")
    _wnum(page, "cas-inner-kc", cas["inner"]["Kc"])
    page.select_option('[data-testid="set-cas_src"]', "manual")
    page.wait_for_selector('[data-testid="set-cas_k"]')
    _quiet(page)


def test_apc_two_loop_techniques_single_loop(page, server):
    """APC: rozvazbení a override v projektu s jedinou smyčkou ukážou vysvětlující text (API odpoví 409)."""
    _track(page)
    for tech, kind in (("decouple", "decouple"), ("override", "override")):
        with pytest.raises(urllib.error.HTTPError) as e:
            _api(server, f"/workspaces/{{wid}}/apc/{kind}", page)
        assert e.value.code == 409
        _apc_tech(page, tech)
        page.wait_for_selector('[data-testid="apc-need-loop"]', timeout=60000)
        page.wait_for_selector(f'[data-testid="apc-nootherloop-{kind}"]')
        assert page.locator(f'[data-testid="apc-loop-{kind}"]').count() == 0
        assert page.locator('[data-testid="apc-need-loop"]').inner_text().strip()
    _quiet(page)


def test_apc_gainsched_integrating_then_fit(page, server):
    """APC: gain scheduling (PV a ER) – integrační model vrací API s integ=true; po přechodu na P1D identifikace bodů
    (úloha), ladění v bodech, tabulka pro GainSched, simulace a zastaralé úseky."""
    _track(page)
    gs_url, er_url = "/workspaces/{wid}/apc/gainsched", "/workspaces/{wid}/apc/gainsched_er"
    if _api(server, gs_url, page)["integ"]:
        _apc_tech(page, "gainsched")
        page.wait_for_selector('[data-testid="gs-integ"]', timeout=60000)
        assert page.locator('[data-testid="apc-checks"] li').count() == len(_api(server, gs_url, page)["checks"])
        _apc_tech(page, "gs_er")
        page.wait_for_selector('[data-testid="er-integ"]', timeout=60000)
        assert page.locator('[data-testid="er-sim"]').count() == 0
        # samoregulační model P1D (identifikace jako úloha, pak vybraný model)
        sets = "/workspaces/{wid}/settings"
        _api_send(server, "PATCH", sets, {"chosen": ["P1D"]}, page)
        _job_done(server, page, _api_post(server, "/workspaces/{wid}/identify", {}, page))
        _api_send(server, "PATCH", sets, {"mcode": "P1D"}, page)
        page.locator('[data-tab="data"]').click()                                   # návrat načte dotazy znovu
    _apc_tech(page, "gainsched")
    page.wait_for_selector('[data-testid="gs-need-fit"]', timeout=60000)
    gs = _api(server, gs_url, page)
    assert not gs["integ"] and not gs["fitted"] and gs["inputs"]["ranges_auto"]
    for i, r in enumerate(gs["inputs"]["ranges"]):
        assert _rel(float(page.locator(f'[data-testid="gs-r{i + 1}-from"]').input_value()), r[0], 1e-5)
        assert _rel(float(page.locator(f'[data-testid="gs-r{i + 1}-to"]').input_value()), r[1], 1e-5)
    page.locator('[data-testid="gs-fit"]').click()
    page.wait_for_selector('[data-testid="gs-table"]', timeout=180000)
    gs = _api(server, gs_url, page)
    assert gs["fitted"] and not gs["stale"] and not gs["inputs"]["ranges_auto"]
    pts = gs["points"]
    assert page.locator('[data-testid="gs-points"] tbody tr').count() == len(pts)
    for i, p in enumerate(pts):
        _wnum(page, f"gs-gain-{i}", p["gain"])
    assert page.locator('[data-testid="gs-table"] tbody tr').count() == len(gs["table"])
    assert page.locator('[data-testid="gs-issue"]').count() == len(gs["issues"])
    assert page.locator('[data-testid="apc-checks"] li').count() == len(gs["checks"])
    sim = _api_post(server, gs_url + "/simulate", {}, page)
    page.wait_for_function(f"() => document.querySelectorAll('[data-testid=\"gs-kpis\"] tbody tr').length === {len(sim['kpis'])}",
                           timeout=60000)
    for i, k in enumerate(sim["kpis"]):
        _wait_cell(page, f'[data-testid="gs-kpi-{i}"] td:nth-child(2)', k["iae_fixed"])
        _wait_cell(page, f'[data-testid="gs-kpi-{i}"] td:nth-child(3)', k["iae_sched"])
    page.wait_for_function("() => document.querySelectorAll('[data-testid=\"gs-pv\"] path').length === 3", timeout=60000)
    # metoda a násobek τc → ladění v bodech z API; reset
    page.select_option('[data-testid="set-gs_m"]', "AMIGO")
    _until(lambda: _setting(server, page, "gs_m") == "AMIGO")
    _wnum(page, "gs-gain-0", _api(server, gs_url, page)["points"][0]["gain"])
    page.select_option('[data-testid="set-gs_m"]', "SIMC")
    _until(lambda: _setting(server, page, "gs_m") == "SIMC")
    _wnum(page, "gs-gain-0", pts[0]["gain"])
    _fill_enter(page, "set-gs_tcf", 2)
    _until(lambda: _setting(server, page, "gs_tcf") == 2.0)
    _wnum(page, "gs-gain-0", _api(server, gs_url, page)["points"][0]["gain"])
    page.locator('[data-testid="gs-reset"]').click()
    _until(lambda: _setting(server, page, "gs_tcf") == 1.0)
    _wnum(page, "gs-gain-0", pts[0]["gain"])
    # změněný úsek → body zastaralé; návrh úseků je vrátí
    rg = gs["inputs"]["ranges"]
    _fill_enter(page, "gs-r1-to", rg[0][1] - 100)
    page.wait_for_selector('[data-testid="gs-stale"]', timeout=60000)
    assert _api(server, gs_url, page)["stale"]
    page.locator('[data-testid="gs-auto"]').click()
    page.wait_for_selector('[data-testid="gs-stale"]', state="detached", timeout=60000)
    assert not _api(server, gs_url, page)["stale"]
    # podle ER: hodnoty = API, vstupy z nastavení, simulace, reset
    _apc_tech(page, "gs_er")
    page.wait_for_selector('[data-testid="er-table"]', timeout=60000)
    er = _api(server, er_url, page)
    assert not er["integ"] and page.locator('[data-testid="er-table"] tbody tr').count() == len(er["table"])
    assert (page.locator('[data-testid="er-base-bad"]').count() == 1) == (not er["k_max"])
    assert page.locator('[data-testid="apc-checks"] li').count() == len(er["checks"])
    _fill_enter(page, "set-gs_er_E", 3)
    _until(lambda: _setting(server, page, "gs_er_E") == 3.0)
    _wait_cell(page, '[data-testid="er-table"] tbody tr:first-child td:nth-child(2)', -3.0)
    er = _api(server, er_url, page)
    assert er["inputs"]["edited"] and er["table"][0]["values"][0] == pytest.approx(-3.0)
    sim = _api_post(server, er_url + "/simulate", {}, page)
    page.wait_for_function(f"() => document.querySelectorAll('[data-testid=\"er-kpis\"] tbody tr').length === {len(sim['kpis'])}",
                           timeout=90000)
    for k in sim["kpis"]:
        _wait_cell(page, f'[data-testid="er-kpi-{k["name"]}"] td:nth-child(2)', k["iae_sp"], timeout=90000)
    assert page.locator('[data-testid="er-zone"]').inner_text().strip()
    page.wait_for_function(f"() => document.querySelectorAll('[data-testid=\"er-pv\"] path').length === {1 + len(sim['kpis'])}",
                           timeout=60000)
    page.locator('[data-testid="er-reset"]').click()
    _until(lambda: _setting(server, page, "gs_er_E") is None)
    _wait_cell(page, '[data-testid="er-table"] tbody tr:first-child td:nth-child(2)', _api(server, er_url, page)["table"][0]["values"][0])
    assert page.locator('[data-testid="er-reset"]').is_disabled()
    _quiet(page)


def test_apc_override_decouple_second_loop(page, server):
    """APC: s druhou smyčkou na stejném ventilu – override (hodnoty = API, MIN / MAX, vlastní mez), rozvazbení bez
    modelu vazby ukáže vysvětlení, výběr druhé smyčky."""
    _track(page)
    base, sets = "/workspaces/{wid}", "/workspaces/{wid}/settings"
    _api_send(server, "POST", base + "/loops", {"name": "FIC", "pv": "FI100.Pritok", "mv": "LIC101.MV"}, page)
    _api_send(server, "PUT", base + "/loops/active", {"index": 1}, page)
    _api_send(server, "PATCH", sets, {"chosen": ["P1D"]}, page)
    _job_done(server, page, _api_post(server, base + "/identify", {}, page))
    _api_send(server, "PUT", base + "/loops/active", {"index": 0}, page)
    page.locator('[data-tab="data"]').click()
    ov_url = base + "/apc/override"
    _apc_tech(page, "override")
    page.wait_for_selector('[data-testid="ov-peak"]', timeout=60000)
    page.wait_for_selector('[data-testid="apc-loop-override"]')
    ov = _api(server, ov_url, page)
    assert ov["loop"] == 1 and page.locator('[data-testid="apc-loop-override"] option').count() == len(ov["loops"])
    assert page.locator('[data-testid="ov-mv-differs"]').count() == (1 if ov["mv_differs"] else 0)
    assert page.locator('[data-testid="apc-checks"] li').count() == len(ov["checks"])
    assert _rel(float(page.locator('[data-testid="ov-step"]').input_value()), ov["defaults"]["step"], 1e-5)
    sim = _api_post(server, ov_url + "/simulate", {}, page)
    _wnum(page, "ov-peak", sim["kpis"]["peak"])
    _wnum(page, "ov-peak-without", sim["kpis"]["peak_without"])
    assert int(page.locator('[data-testid="ov-switches"]').inner_text()) == sim["kpis"]["switches"]
    page.wait_for_function("() => document.querySelectorAll('[data-testid=\"ov-pv-b\"] path').length === 3", timeout=60000)
    # MAX a vlastní mez → výsledek simulace z API se stejným tělem
    page.select_option('[data-testid="ov-sel"]', "max")
    mx = _api(server, ov_url + "?sel=max", page)
    page.wait_for_function("(v) => Math.abs(parseFloat(document.querySelector('[data-testid=\"ov-lim\"]').value) - v) <="
                           " 1e-5 * Math.max(1, Math.abs(v))", arg=mx["defaults"]["lim"], timeout=60000)
    lim = round(mx["defaults"]["lim"] + 1.0, 3)
    _fill_enter(page, "ov-lim", lim)
    sim = _api_post(server, ov_url + "/simulate", {"sel": "max", "lim": lim}, page)
    assert sim["lim"] == pytest.approx(lim)
    _wnum(page, "ov-peak", sim["kpis"]["peak"])
    page.locator('[data-testid="ov-reset"]').click()
    sim = _api_post(server, ov_url + "/simulate", {"sel": "max"}, page)
    _wnum(page, "ov-peak", sim["kpis"]["peak"])
    # rozvazbení: smyčky na společném ventilu nemají model vazby
    _apc_tech(page, "decouple")
    page.wait_for_selector('[data-testid="dec-rga"]', timeout=60000)
    dec = _api(server, base + "/apc/decouple", page)
    assert dec["ok"] == (page.locator('[data-testid="dec-lam"]').count() == 1)
    if not dec["ok"]:
        assert page.locator('[data-testid="dec-need-cross"]').count() == 1 and page.locator('[data-testid="dec-sim"]').count() == 0
    assert page.locator('[data-testid="apc-checks"] li').count() == len(dec["checks"])
    # kaskáda s vnitřní smyčkou z jiné smyčky projektu
    _apc_tech(page, "cascade")
    page.select_option('[data-testid="set-cas_src"]', "loop")
    page.wait_for_selector('[data-testid="apc-loop-cascade"]', timeout=60000)
    cas = _api(server, base + "/apc/cascade", page)
    assert cas["inputs"]["source"] == "loop" and cas["inputs"]["loop"] == 1
    _wnum(page, "cas-inner-kc", cas["inner"]["Kc"])
    page.select_option('[data-testid="set-cas_src"]', "manual")
    _quiet(page)


def test_no_page_errors(page):
    """Během všech předchozích scénářů nevznikla na stránce žádná výjimka JS."""
    assert page.errors == []
