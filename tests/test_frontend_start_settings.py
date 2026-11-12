"""
Start, globální Nastavení aplikace, automatické ukládání a „Nový“ projekt v prohlížeči (E10-B). Potřebuje sestavené UI
(cd frontend && npm run build); nastavení a uživatelská data jdou do dočasných složek.
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

import pytest

pytest.importorskip("playwright.sync_api")
import test_frontend as _tf  # noqa: E402
import test_frontend_controllers as _tfc  # noqa: E402

page = _tf.page
ROOT, TOKEN = _tf.ROOT, _tf.TOKEN


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    if not os.path.exists(_tf.UI):
        pytest.skip("rozhraní není sestavené (cd frontend && npm run build)")
    port = _tfc._free_port()
    t = tmp_path_factory
    env = dict(os.environ, PIDTOOLS_CONTROLLERS_DIR=str(t.mktemp("controllers")), PIDTOOLS_CONFIG_DIR=str(t.mktemp("config")),
               PIDTOOLS_DATA_DIR=str(t.mktemp("data")))
    p = subprocess.Popen([sys.executable, "-m", "pidtools.api", "--port", str(port), "--token", TOKEN], cwd=ROOT, env=env,
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


def _api(server, method, path, page=None, body=None, raw=None):
    wid = page.evaluate("sessionStorage.getItem('pid.wid')") if page else None
    req = urllib.request.Request(server + "/api/v1" + path.format(wid=wid), method=method, headers={"X-PID-Token": TOKEN},
                                 data=raw if raw is not None else None if body is None else json.dumps(body).encode())
    if body is not None:
        req.add_header("Content-Type", "application/json")
    return json.loads(urllib.request.urlopen(req, timeout=60).read() or b"null")


def _reload(pg):
    pg.reload(wait_until="networkidle")
    pg.wait_for_selector('[data-testid="api-ok"]', timeout=20000)


def _open_settings(pg, section):
    if pg.locator('[data-testid="settings-page"]').count() == 0:
        pg.locator('[data-testid="settings"] summary').click()
        pg.locator('[data-testid="open-settings"]').click()
    pg.locator(f'[data-testid="settings-nav-{section}"]').click()
    pg.wait_for_selector(f'[data-testid="settings-{section}"], [data-testid="reg-library"]')


def test_start_screen_demo_and_unsaved_header(page, server):
    page.wait_for_selector('[data-testid="start-screen"]', timeout=15000)
    assert page.locator('[data-testid="start-steps"] li').count() == 5
    assert page.locator('[data-testid="start-recent-item"]').count() == 0
    assert page.locator('[data-testid="data-sum"]').count() == 0
    page.locator('[data-testid="start-demo"]').click()
    page.wait_for_selector('[data-testid="start-screen"]', state="detached")
    page.wait_for_function("() => (document.querySelector('[data-testid=\"data-sum\"]')||{}).innerText?.includes('not saved')")
    assert page.locator('[data-testid="data-sum"]').get_attribute("data-dirty") == "1"


def test_new_project_confirms_when_unsaved_and_returns_to_start(page, server):
    msgs = []
    page.once("dialog", lambda d: (msgs.append(d.message), d.dismiss()))
    page.locator('[data-testid="new-project"]').click()
    page.wait_for_timeout(300)
    assert msgs and "unsaved" in msgs[0] and page.locator('[data-testid="start-screen"]').count() == 0     # „Zrušit“ nic nezmění
    page.once("dialog", lambda d: d.accept())
    page.locator('[data-testid="new-project"]').click()
    page.wait_for_selector('[data-testid="start-screen"]', timeout=15000)
    assert not _api(server, "GET", "/workspaces/{wid}", page)["has_data"]


def test_autosave_then_recovery_banner_after_lost_workspace(page, server):
    page.locator('[data-testid="start-demo"]').click()
    page.wait_for_selector('[data-testid="start-screen"]', state="detached")
    for _ in range(60):                                  # v klidu ~8 s a kontrola po 2 s
        if _api(server, "GET", "/autosave/latest")["available"]:
            break
        time.sleep(1)
    rec = _api(server, "GET", "/autosave/latest")
    assert rec["available"] and rec["loops"] == 1
    page.wait_for_function("() => /saved \\d/.test((document.querySelector('[data-testid=\"data-sum\"]')||{}).innerText||'')", timeout=15000)
    # „pád“: prostor zmizí (restart serveru), po obnově stránky nabídne Start záchrannou kopii
    page.evaluate("sessionStorage.setItem('pid.wid', 'gone')")
    _reload(page)
    page.wait_for_selector('[data-testid="start-recovery"]', timeout=15000)
    page.locator('[data-testid="start-restore"]').click()
    page.wait_for_selector('[data-testid="start-screen"]', state="detached", timeout=15000)
    assert _api(server, "GET", "/workspaces/{wid}", page)["has_data"]
    assert _api(server, "GET", "/workspaces/{wid}/save-state", page)["dirty"]          # obnovený projekt je neuložený
    # nový projekt záchrannou kopii smaže (úmyslné zahození)
    page.once("dialog", lambda d: d.accept())
    page.locator('[data-testid="new-project"]').click()
    page.wait_for_selector('[data-testid="start-screen"]')
    assert not _api(server, "GET", "/autosave/latest")["available"]
    assert page.locator('[data-testid="start-recovery"]').count() == 0


def test_recent_projects_after_manual_save(page, server):
    page.locator('[data-testid="start-demo"]').click()
    page.wait_for_selector('[data-testid="start-screen"]', state="detached")
    wid = page.evaluate("sessionStorage.getItem('pid.wid')")
    urllib.request.urlopen(urllib.request.Request(server + f"/api/v1/workspaces/{wid}/project",
                                                  headers={"X-PID-Token": TOKEN})).read()          # ruční uložení projektu
    page.wait_for_function("() => !(document.querySelector('[data-testid=\"data-sum\"]')||{}).innerText?.includes('not saved')", timeout=15000)
    page.locator('[data-testid="new-project"]').click()                 # po uložení se Nový neptá
    page.wait_for_selector('[data-testid="start-recent-item"]', timeout=15000)
    page.locator('[data-testid="start-recent-item"] .st-recent-open').first.click()
    page.wait_for_selector('[data-testid="start-screen"]', state="detached", timeout=15000)
    assert not _api(server, "GET", "/workspaces/{wid}/save-state", page)["dirty"]               # otevřený projekt je „uložený“
    page.locator('[data-testid="new-project"]').click()                 # otevřený projekt je uložený, bez dialogu
    page.wait_for_selector('[data-testid="start-screen"]')


def test_start_example_ff_loads_apc_data(page, server):
    page.locator('[data-testid="start-example-ff"]').click()
    page.wait_for_selector('[data-testid="start-screen"]', state="detached", timeout=15000)
    w = _api(server, "GET", "/workspaces/{wid}", page)
    assert w["fname"] == "apc_ff_example.csv" and w["has_data"]
    page.once("dialog", lambda d: d.accept())
    page.locator('[data-testid="new-project"]').click()
    page.wait_for_selector('[data-testid="start-screen"]')


SECTIONS = ["general", "appearance", "charts", "diagnostics", "defaults", "journal", "report", "connections", "io", "controllers"]


def test_settings_sections_and_server_persistence(page, server):
    _open_settings(page, "general")
    for s in SECTIONS:
        assert page.locator(f'[data-testid="settings-nav-{s}"]').count() == 1
    assert page.locator('[data-testid="set-version"]').inner_text() != "…"
    page.locator('[data-testid="set-autosave"]').select_option("5")
    _open_settings(page, "appearance")
    page.locator('[data-testid="set-font"]').select_option("l")
    page.locator('[data-testid="set-lang"]').select_option("cs")
    page.wait_for_function("() => document.documentElement.lang === 'cs'")
    _open_settings(page, "charts")
    page.locator('[data-testid="set-chart-h"]').fill("350")
    page.locator('[data-testid="set-chart-h"]').press("Enter")
    for _ in range(30):
        s = _api(server, "GET", "/app-settings")
        if s["charts"]["height"] == 350 and s["general"]["autosave_min"] == 5:
            break
        time.sleep(0.2)
    assert s["charts"]["height"] == 350 and s["general"]["autosave_min"] == 5
    assert s["appearance"]["font_size"] == "l" and s["appearance"]["language"] == "cs"
    assert page.evaluate("document.documentElement.dataset.font") == "l"
    _reload(page)                                                   # nastavení přežije obnovení stránky (server)
    assert page.evaluate("document.documentElement.lang") == "cs"
    _open_settings(page, "charts")
    assert page.locator('[data-testid="set-chart-h"]').input_value() == "350"
    page.locator('[data-testid="set-chart-h"]').fill("220")
    page.locator('[data-testid="set-chart-h"]').press("Enter")


def test_settings_diagnostics_defaults_apply_to_new_project(page, server):
    _open_settings(page, "diagnostics")
    inputs = page.locator('[data-testid^="set-thr-"]:not([data-testid="set-thr-reset"])')
    page.wait_for_selector('[data-testid^="set-thr-"]:not([data-testid="set-thr-reset"])')
    assert inputs.count() >= 4
    first = inputs.first
    tid = first.get_attribute("data-testid")
    first.fill("33")
    first.press("Enter")
    _open_settings(page, "defaults")
    page.wait_for_selector('[data-testid="set-def-ctl"] option[value="isa_ideal"]', state="attached")
    page.locator('[data-testid="set-def-ctl"]').select_option("isa_ideal")
    page.locator('[data-testid="set-def-ctype"]').select_option("PID")
    for _ in range(30):
        s = _api(server, "GET", "/app-settings")
        if s["defaults"]["controller"] == "isa_ideal" and s["defaults"]["sim"]["ctype"] == "PID":
            break
        time.sleep(0.2)
    assert s["defaults"]["controller"] == "isa_ideal" and s["diagnostics"]["thresholds"]
    # nový projekt (a nový prostor) dostane výchozí regulátor i práh
    page.locator('[data-testid="settings-back"]').click()
    old = page.evaluate("sessionStorage.getItem('pid.wid')")
    page.locator('[data-testid="new-project"]').click()
    page.wait_for_function("(o) => sessionStorage.getItem('pid.wid') !== o", arg=old)
    page.wait_for_selector('[data-testid="start-screen"]')
    assert _api(server, "GET", "/workspaces/{wid}/controller", page)["profile"]["id"] == "isa_ideal"
    thr = _api(server, "GET", "/workspaces/{wid}/triage/thresholds", page)["values"]
    rule, name = tid[len("set-thr-"):].split("-", 1)
    assert thr[rule][name] == 33
    # reset prahů v nastavení
    _open_settings(page, "diagnostics")
    page.locator('[data-testid="set-thr-reset"]').click()
    page.wait_for_function("(t) => document.querySelector(`[data-testid=\"${t}\"]`).value !== '33'", arg=tid)


def test_settings_report_logo_connections_export_import(page, server, tmp_path):
    _open_settings(page, "report")
    page.locator('[data-testid="set-company"]').fill("ACME Chemie")
    page.locator('[data-testid="set-company"]').press("Enter")
    logo = tmp_path / "firma.svg"
    logo.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="40" height="20"><rect width="40" height="20" fill="#1f5fa8"/></svg>')
    page.set_input_files('[data-testid="set-logo-file"]', str(logo))
    page.wait_for_selector('[data-testid="set-logo-img"]', timeout=10000)
    assert _api(server, "GET", "/app-settings")["report"]["logo"] == "logo.svg"
    _open_settings(page, "connections")
    assert page.locator('[data-testid="set-opc-add"]').is_disabled()
    page.fill('[data-testid="set-opc-name"]', "Reaktor K2")
    page.fill('[data-testid="set-opc-url"]', "opc.tcp://plc01:4840")
    page.locator('[data-testid="set-opc-add"]').click()
    page.wait_for_selector('[data-testid="set-opc-0"]')
    page.locator('[data-testid="set-hist-pi"]').fill("https://pi.firma.cz/piwebapi")
    page.locator('[data-testid="set-hist-pi"]').press("Enter")
    for _ in range(30):
        s = _api(server, "GET", "/app-settings")
        if s["connections"]["historians"]["pi"] and s["connections"]["opc"]:
            break
        time.sleep(0.2)
    assert s["connections"]["opc"] == [{"name": "Reaktor K2", "url": "opc.tcp://plc01:4840"}] and s["report"]["company"] == "ACME Chemie"
    # export → reset → import vrátí hodnoty
    _open_settings(page, "io")
    with page.expect_download() as dl:
        page.locator('[data-testid="set-export"]').click()
    exp = tmp_path / "exp.json"
    dl.value.save_as(str(exp))
    assert json.loads(exp.read_text())["format"] == "pidtools.settings"
    page.once("dialog", lambda d: d.accept())
    page.locator('[data-testid="set-reset"]').click()
    page.wait_for_function("() => /restored|obnoveno/i.test(document.querySelector('[data-testid=\"set-io-msg\"]')?.innerText || '')")
    assert _api(server, "GET", "/app-settings")["report"]["company"] == ""
    page.set_input_files('[data-testid="set-import-file"]', str(exp))
    page.wait_for_function("() => /imported|načteno/i.test(document.querySelector('[data-testid=\"set-io-msg\"]')?.innerText || '')")
    assert _api(server, "GET", "/app-settings")["report"]["company"] == "ACME Chemie"
    bad = tmp_path / "bad.json"
    bad.write_text("{}")
    page.set_input_files('[data-testid="set-import-file"]', str(bad))
    page.wait_for_selector('[data-testid="set-io-msg"][role="alert"]')


def test_controller_default_and_test_memo_are_server_side(page, server):
    _open_settings(page, "controllers")
    page.locator('[data-testid="rg-item-pcs7_pidconl"]').click()
    page.locator('[data-testid="rg-default"]').click()
    for _ in range(30):
        if _api(server, "GET", "/app-settings")["defaults"]["controller"] == "pcs7_pidconl":
            break
        time.sleep(0.2)
    assert _api(server, "GET", "/app-settings")["defaults"]["controller"] == "pcs7_pidconl"
    assert page.evaluate("localStorage.getItem('pid.defctl')") is None
