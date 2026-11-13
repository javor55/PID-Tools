"""
Ladění s profilem regulátoru smyčky (E8-B) v prohlížeči: karta Regulátor smyčky (změna profilu → názvy parametrů),
varování mapování, τc, Proces a ventil, tabulka robustnosti, export pro řídicí systém (stažení) a CSV srovnání.
Potřebuje sestavené UI (cd frontend && npm run build).
"""
import json
import time
import urllib.request

import pytest

pytest.importorskip("playwright.sync_api")
import test_frontend as _tf  # noqa: E402

TOKEN = _tf.TOKEN
server, page = _tf.server, _tf.page                      # fixtury serveru a prohlížeče


def _call(server, page, method, path, body=None):
    wid = page.evaluate("sessionStorage.getItem('pid.wid')")
    req = urllib.request.Request(server + path.format(wid=wid), method=method,
                                 data=None if body is None else json.dumps(body).encode(),
                                 headers={"X-PID-Token": TOKEN, "Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=120).read() or b"null")


@pytest.fixture(scope="module")
def prepared(page, server):
    page.locator('[data-tab="data"]').click()
    page.locator('[data-sub="quality"]').click()
    page.locator('[data-sub="sources"]').click()
    page.locator('[data-testid="src-demo"]').click()
    page.wait_for_function("() => (document.querySelector('[data-testid=\"data-info\"]')||{}).innerText?.includes('demo')")
    _call(server, page, "PATCH", "/workspaces/{wid}/settings", {"chosen": ["P1D", "I1D"]})
    j = _call(server, page, "POST", "/workspaces/{wid}/identify", {})
    for _ in range(600):
        if _call(server, page, "GET", f"/jobs/{j['id']}")["state"] not in ("queued", "running"):
            break
        time.sleep(0.2)
    page.reload(wait_until="networkidle")
    page.wait_for_selector('[data-testid="api-ok"]', timeout=20000)
    page.locator('[data-tab="tuning"]').click()
    page.wait_for_selector('[data-testid="sets"] tbody tr', timeout=30000)
    page.locator('[data-testid="card-block"] > summary').click()
    return page


def _names(pg):
    return [t.strip() for t in pg.locator('[data-testid="sets"] tbody th').all_inner_texts()]


def test_default_profile_card(prepared):
    pg = prepared
    assert "PIDConL" in pg.locator('[data-testid="ctrl-name"]').inner_text()
    assert [n.split(" ")[0] for n in _names(pg)] == ["Gain", "TI", "TD"]
    assert pg.locator('[data-testid="blk-params"] [data-testid="set-samp"]').count() == 1       # blok podle profilu
    pg.wait_for_function("() => document.querySelectorAll('[data-testid=\"rob-table\"] tbody tr').length >= 2",
                         timeout=30000)                                 # tabulka robustnosti se dopočítá asynchronně                        # tabulka robustnosti
    assert "Mt" in pg.locator('[data-testid="rob-table"] thead').inner_text()
    assert pg.locator('[data-testid="set-tc"]').count() == 0 or pg.locator('[data-testid="method"]').input_value() != "SIMC"


def test_tc_and_plant(prepared, server):
    pg = prepared
    pg.select_option('[data-testid="method"]', "SIMC")
    pg.wait_for_selector('[data-testid="set-tc"]')
    base = _call(server, pg, "POST", "/workspaces/{wid}/tuning/suggest", {"method": "SIMC"})
    pg.locator('[data-testid="set-tc"]').fill(str(round(base["tc"] * 3, 3)))
    pg.locator('[data-testid="set-tc"]').press("Enter")
    pg.wait_for_selector('[data-testid="sug-robust"]')
    st = _call(server, pg, "GET", "/workspaces/{wid}/settings")
    key = next(k for k in st if k.startswith("tc|") and k.endswith("|SIMC|PI"))
    assert abs(st[key] - base["tc"] * 3) < 1e-2
    slow = _call(server, pg, "POST", "/workspaces/{wid}/tuning/suggest", {"method": "SIMC", "tc": st[key]})
    assert abs(slow["Ti"]) > 0 and slow["tc"] == pytest.approx(st[key])
    # proces a ventil v simulaci
    pg.locator('[data-testid="card-plant"] > summary').click()
    pg.locator('[data-testid="plant-noise"]').fill("0.2")
    pg.locator('[data-testid="plant-noise"]').press("Enter")
    deadline = time.time() + 10
    while time.time() < deadline and _call(server, pg, "GET", "/workspaces/{wid}/tuning/plant")["noise"] != 0.2:
        time.sleep(0.2)
    assert _call(server, pg, "GET", "/workspaces/{wid}/tuning/plant")["noise"] == 0.2
    pg.locator('[data-testid="plant-noise"]').fill("0")
    pg.locator('[data-testid="plant-noise"]').press("Enter")
    _call(server, pg, "PATCH", "/workspaces/{wid}/settings", {f"tc|{st['mcode']}|SIMC|PI": 0})


def test_change_profile_renames_parameters(prepared, server):
    pg = prepared
    pg.select_option('[data-testid="ctrl-select"]', "isa_parallel")
    pg.wait_for_function("() => [...document.querySelectorAll('[data-testid=\"sets\"] tbody th')].some(e => e.innerText.startsWith('Kp'))")
    assert [n.split(" ")[0] for n in _names(pg)] == ["Kp", "Ki", "Kd"]
    assert "isa_parallel" in json.dumps(_call(server, pg, "GET", "/workspaces/{wid}/controller")["profile"]["id"])
    pg.select_option('[data-testid="ctrl-select"]', "isa_series")
    pg.wait_for_function("() => [...document.querySelectorAll('[data-testid=\"sets\"] tbody th')].some(e => e.innerText.startsWith('Kc'))")
    # sada s Ti < 4·Td nemá sériový ekvivalent: varování mapování
    _call(server, pg, "PUT", "/workspaces/{wid}/tuning/sets/2", {"Kc": -2.0, "Ti": 20.0, "Td": 10.0})
    pg.reload(wait_until="networkidle")
    pg.locator('[data-tab="tuning"]').click()
    pg.wait_for_selector('[data-testid="set2-map-warn"]', timeout=30000)
    # odkaz do knihovny (událost pro Nastavení › Regulátory)
    pg.evaluate("window.__open = null; window.addEventListener('pid:open-settings', (e) => { window.__open = e.detail; })")
    pg.locator('[data-testid="card-block"] > summary').click()
    pg.locator('[data-testid="ctrl-open-lib"]').click()
    assert pg.evaluate("window.__open") == {"section": "controllers", "id": "isa_series"}
    pg.wait_for_selector('[data-testid="settings-page"]', timeout=10000)                   # Nastavení › Regulátory
    pg.locator('[data-testid="settings-back"]').click()
    pg.wait_for_selector('[data-testid="card-block"]', timeout=10000)
    if not pg.locator('[data-testid="loop-ctrl"]').is_visible():                          # karta se po návratu vykreslí znovu
        pg.locator('[data-testid="card-block"] > summary').click()
    pg.wait_for_selector('[data-testid="loop-ctrl"]', state="visible", timeout=10000)


def test_export_download_and_csv(prepared, server):
    pg = prepared
    pg.locator('[data-testid="export-open"]').click()
    pg.select_option('[data-testid="export-fmt"]', "pcs7")
    with pg.expect_download() as d:
        pg.locator('[data-testid="export-go"]').click()
    path = d.value.path()
    txt = open(path, encoding="utf-8-sig").read()
    assert d.value.suggested_filename == "tuning_set2_pcs7.txt"
    assert "Kc :=" in txt and "Ti :=" in txt and "Td :=" in txt                         # názvy parametrů profilu
    pg.select_option('[data-testid="export-fmt"]', "csv")
    with pg.expect_download() as d:
        pg.locator('[data-testid="export-go"]').click()
    assert open(d.value.path(), encoding="utf-8-sig").read().splitlines()[0] == "parameter;unit;set_1;set_2"
    # zpět na výchozí PIDConL (sdílený stav testů)
    pg.select_option('[data-testid="ctrl-select"]', "pcs7_pidconl")
    pg.wait_for_function("() => [...document.querySelectorAll('[data-testid=\"sets\"] tbody th')].some(e => e.innerText.startsWith('Gain'))")
    assert _call(server, pg, "GET", "/workspaces/{wid}/controller")["is_default"] is True

