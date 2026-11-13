"""
Veřejný režim v prohlížeči (PIDTOOLS_AUTH=public): relace v cookie, Start s upozorněním na soukromí, ukázka a identifikace,
OPC UA a logo skryté, bez porušení CSP a bez zápisu na disk. Potřebuje sestavené UI a Playwright (jinak se přeskočí).
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


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    if not os.path.exists(UI):
        pytest.skip("rozhraní není sestavené (cd frontend && npm run build)")
    tmp = tmp_path_factory.mktemp("pub")
    port = _free_port()
    env = dict(os.environ, PIDTOOLS_AUTH="public", PIDTOOLS_COOKIE_SECURE="0", PORT=str(port), HOST="127.0.0.1",
               PIDTOOLS_CONFIG_DIR=str(tmp / "cfg"), PIDTOOLS_DATA_DIR=str(tmp / "data"),
               PIDTOOLS_CONTROLLERS_DIR=str(tmp / "ctl"), PIDTOOLS_RATE_LIMIT="6000")
    p = subprocess.Popen([sys.executable, "-m", "pidtools.api.serve"], cwd=ROOT, env=env,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    for _ in range(150):
        try:
            urllib.request.urlopen(url + "/health", timeout=1)
            break
        except Exception:
            time.sleep(0.1)
    yield url, tmp
    p.terminate()
    p.wait(10)


@pytest.fixture(scope="module")
def page(server):
    url, _ = server
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
        pg.console_msgs = []
        pg.on("console", lambda m: pg.console_msgs.append(m.text))
        pg.errors = []
        pg.on("pageerror", lambda e: pg.errors.append(str(e)))
        pg.ctx = ctx
        pg.goto(url, wait_until="networkidle")
        pg.wait_for_selector('[data-testid="start-screen"]', timeout=20000)
        yield pg
        b.close()


def test_session_cookie_and_privacy_notice(page):
    cookies = {c["name"]: c for c in page.ctx.cookies()}
    c = cookies["pidtools_sid"]
    assert c["httpOnly"] and c["sameSite"] == "Strict" and len(c["value"]) >= 43
    assert "pidtools_sid" not in page.evaluate("() => document.cookie")             # cookie není čitelná skriptem
    note = page.locator('[data-testid="public-notice"]')
    assert note.count() == 1 and "discarded" in note.inner_text()
    assert page.locator('[data-testid="opc-open"]').count() == 0                      # OPC UA skryté


def test_demo_identify_and_help_notice(page):
    page.locator('[data-testid="start-demo"]').click()
    page.wait_for_selector('[data-testid="start-screen"]', state="detached")
    page.locator('[data-tab="model"]').click()
    page.wait_for_selector('[data-testid="model-trend"] .pidw', timeout=20000)
    for c in ("P0D", "P2D", "I0D"):
        box = page.locator(f'[data-testid="chk-{c}"]')
        if box.is_checked():
            box.click()
            page.wait_for_function(f"() => !document.querySelector('[data-testid=\"chk-{c}\"]').checked")
    page.locator('[data-testid="identify"]').click()
    page.wait_for_selector('[data-testid="models"] tbody tr', timeout=120000)
    page.locator('[data-testid="help-btn"]').click()
    page.wait_for_selector('[data-testid="public-notice-help"]', timeout=10000)
    assert "Nothing is stored permanently" in page.locator('[data-testid="public-notice-help"]').inner_text()
    page.keyboard.press("Escape")


def test_data_tab_without_opc_and_no_csp_violations(page, server):
    page.locator('[data-tab="data"]').click()
    page.locator('[data-sub="sources"]').click()
    page.wait_for_selector('[data-testid="src-demo"]', timeout=10000)
    assert page.locator('[data-testid="src-add-file"]').count() == 1
    assert page.locator('[data-testid="opc-open"]').count() == 0                     # OPC UA ve veřejném režimu není
    assert not [m for m in page.console_msgs if "Content Security Policy" in m or "Refused to" in m], page.console_msgs
    assert not page.errors
    _, tmp = server
    assert not (tmp / "cfg").exists() and not (tmp / "data").exists() and not (tmp / "ctl").exists()   # nic na disk
