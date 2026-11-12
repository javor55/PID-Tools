"""
Nastavení › Regulátory v prohlížeči (E8-A): knihovna, vytvoření vlastního z předvolby, editor v textovém režimu
s chybou překladu a opravou, uložení, test použitelnosti s verdiktem a 12 kontrolami. Potřebuje sestavené UI
(cd frontend && npm run build); vlastní regulátory se ukládají do dočasné složky (PIDTOOLS_CONTROLLERS_DIR).
"""
import os
import socket
import subprocess
import sys
import time
import urllib.request

import pytest

pytest.importorskip("playwright.sync_api")
import test_frontend as _tf  # noqa: E402

page = _tf.page                                          # fixtura prohlížeče (používá fixturu serveru níže)
ROOT, TOKEN = _tf.ROOT, _tf.TOKEN


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    if not os.path.exists(_tf.UI):
        pytest.skip("rozhraní není sestavené (cd frontend && npm run build)")
    port = _free_port()
    env = dict(os.environ, PIDTOOLS_CONTROLLERS_DIR=str(tmp_path_factory.mktemp("controllers")))
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


def _open_library(pg):
    if pg.locator('[data-testid="settings-page"]').count() == 0:
        pg.locator('[data-testid="settings"] summary').click()
        pg.locator('[data-testid="open-settings"]').click()
    pg.locator('[data-testid="settings-nav-controllers"]').click()
    pg.wait_for_selector('[data-testid="reg-library"] [data-testid^="rg-item-"]')


def test_library_lists_presets_in_groups(page):
    _open_library(page)
    assert page.locator('[data-testid="rg-group-siemens"]').count() == 1
    assert page.locator('[data-testid="rg-group-other"]').count() == 1
    assert page.locator('[data-testid="rg-group-mine"]').count() == 0                      # zatím žádné vlastní
    page.locator('[data-testid="rg-item-pcs7_pidconl"]').click()
    assert "PIDConL" in page.locator('[data-testid="rg-name"]').inner_text()
    assert page.locator('[data-testid="rg-chain"] .rg-block').count() >= 5
    page.locator('[data-testid="rg-tab-par"]').click()
    assert page.locator('[data-testid="rg-pane-par"] tbody tr').count() > 5
    page.locator('[data-testid="rg-search"]').fill("compact")                                # hledání
    assert page.locator('[data-testid^="rg-item-"]').count() == 1
    page.locator('[data-testid="rg-search"]').fill("")


def test_create_custom_edit_text_with_error_fix_save_and_test(page):
    _open_library(page)
    page.locator('[data-testid="rg-item-isa_ideal"]').click()
    page.locator('[data-testid="rg-make-custom"]').click()
    page.wait_for_selector('[data-testid="reg-editor"]')
    # skládání: změna části doplní její parametry
    page.locator('[data-testid="rg-seg-deadbands"] [data-value="gap"]').click()
    assert page.locator('[data-testid="rg-sec-params"] input[type="number"]').count() >= 3
    page.locator('[data-testid="rg-name-input"]').fill("Kotelna K2 – PID_K2")
    # text: vznikne vlastní program, překlad proběhne sám
    page.locator('[data-testid="rg-mode"] [data-value="text"]').click()
    page.wait_for_function("() => document.querySelector('[data-testid=\"rg-compile-status\"]')?.className.includes('ok')")
    src = page.locator('[data-testid="rg-source"]')
    good = src.input_value()
    assert "MV  = clamp(" in good
    src.fill(good.replace("MV  = clamp(", "MV  = clmp(", 1))                                # chyba: neznámá funkce
    page.wait_for_selector('[data-testid="rg-code"] .rg-ln.error')
    assert page.locator('[data-testid="rg-issues"] li').count() >= 1
    assert page.locator('[data-testid="rg-issues"] code').first.inner_text().count(":") == 1   # řádek:sloupec
    page.locator('[data-testid="rg-save"]').click()                                        # uložení neplatného zdroje selže
    page.wait_for_selector('[data-testid="rg-msg"].bad')
    src.fill(good)                                                                          # oprava
    page.wait_for_selector('[data-testid="rg-code"] .rg-ln.error', state="detached")
    page.wait_for_function("() => document.querySelector('[data-testid=\"rg-compile-status\"]')?.className.includes('ok')")
    assert page.locator('[data-testid="rg-quick"] li').count() >= 5                         # rychlé kontroly
    page.locator('[data-testid="rg-save"]').click()
    page.wait_for_selector('[data-testid="rg-msg"].ok')
    # přepočet návrhu přes /map uloženého programu
    page.wait_for_selector('[data-testid="rg-recalc"] tbody tr')
    # knihovna: vlastní regulátor ve skupině Moje regulátory
    page.locator('[data-testid="rg-back"]').click()
    page.wait_for_selector('[data-testid="rg-group-mine"] [data-testid^="rg-item-"]')
    page.locator('[data-testid="rg-group-mine"] [data-testid^="rg-item-"]').first.click()
    assert "K2" in page.locator('[data-testid="rg-name"]').inner_text()
    page.locator('[data-testid="rg-run-test"]').click()
    page.wait_for_selector('[data-testid="rg-verdict"]', timeout=60000)
    assert page.locator('[data-testid="rg-verdict"]').get_attribute("data-verdict") in ("suitable", "optimisation_only", "unsuitable")
    assert page.locator('[data-testid="rg-checks"] li').count() == 12
    page.locator('[data-testid="rg-back"]').click()
    page.wait_for_selector('[data-testid="rg-memo"]')                                      # výsledek testu v detailu


def test_back_to_project_and_no_js_errors(page):
    page.locator('[data-testid="settings-back"]').click()
    assert page.locator('[data-testid="settings-page"]').count() == 0
    assert page.locator('nav.tabs [role="tab"]').count() == 5
    assert not page.errors
