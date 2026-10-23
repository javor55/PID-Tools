"""
Test webové aplikace ve skutečném prohlížeči (Playwright + Chromium): vzhled stojí na CSS napojeném na vnitřní
strukturu Streamlitu – po změně verze Streamlitu se může rozbít bez chyby v Pythonu. Test spustí aplikaci
s ukázkovými daty a ověří rám (nezávislé rolování plochy a panelu), pole (bílá s rámečkem), zarovnání popisků,
prohlížeč záznamu (Data: panely, zoom, kurzory, tabulka), společný graf průběhů (Model) a tažení táhla úseku.

Bez Playwrightu nebo prohlížeče se test přeskočí (CI je instaluje, viz .github/workflows/tests.yml).
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

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def server():
    port = _free_port()
    proc = subprocess.Popen([sys.executable, "-m", "streamlit", "run", "app.py", "--server.headless", "true",
                             "--server.port", str(port), "--browser.gatherUsageStats", "false"],
                            cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    for _ in range(120):
        try:
            urllib.request.urlopen(url + "/_stcore/health", timeout=1)
            break
        except Exception:
            time.sleep(0.5)
    else:
        proc.kill()
        pytest.skip("Streamlit se nespustil")
    yield url
    proc.terminate()
    proc.wait(10)


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
        pg = b.new_page(viewport={"width": 1440, "height": 900})
        pg.requested = []                                  # všechny požadavky stránky (kontrola offline provozu)
        pg.on("request", lambda r: pg.requested.append(r.url))
        pg.goto(server, wait_until="networkidle")
        pg.wait_for_selector('[data-testid="stTab"]', timeout=60000)
        # zdroj dat: ukázka (přepínač Zdroj dat v panelu záložky Data)
        pg.locator('[class*="st-key-pidside_"] [data-testid="stButtonGroup"] button', has_text="Demo").first.click()
        pg.wait_for_selector(".pidv-panel canvas", timeout=60000)
        _idle(pg)
        yield pg
        b.close()


def _idle(pg, extra=500):
    """Počkat, než Streamlit doběhne (stavový widget zmizí)."""
    pg.wait_for_timeout(300)
    for _ in range(600):
        if not pg.locator('[data-testid="stStatusWidget"]').count():
            break
        pg.wait_for_timeout(100)
    pg.wait_for_timeout(extra)


def _tab(pg, i):
    pg.locator('[data-testid="stTab"]').nth(i).click()
    _idle(pg, 1500)


def test_offline_no_external_requests(page, server):
    """Žádný požadavek mimo vlastní server (fonty přibalené ve static/fonts, žádné CDN) a fonty IBM Plex načtené."""
    page.evaluate("document.fonts.ready")
    ext = [u for u in page.requested if not u.startswith((server, "data:", "blob:"))]
    assert not ext, ext[:10]
    assert any("/app/static/fonts/ibm-plex-sans-" in u for u in page.requested)
    assert page.evaluate("""() => [...document.fonts].some(f => f.family.replace(/"/g, '') === 'IBM Plex Sans'
                                   && f.status === 'loaded')""")
    assert page.evaluate("document.fonts.check(\"12px 'IBM Plex Mono'\")")


def test_frame_scrolls_independently(page):
    """Plocha a panel mají výšku okna pod hlavičkou a rolují každý zvlášť (stránka sama nerojuje)."""
    _tab(page, 0)
    r = page.evaluate("""() => {
        const side = [...document.querySelectorAll('[class*="st-key-pidside_"]')].find(e => e.offsetParent);
        const b = side.getBoundingClientRect();
        return {bottom: b.bottom, h: innerHeight, over: getComputedStyle(side).overflowY};
    }""")
    assert abs(r["bottom"] - r["h"]) <= 2 and r["over"] == "auto"
    m = page.evaluate("""() => {
        const col = [...document.querySelectorAll('[data-testid=stColumn]')]
            .find(c => c.offsetParent && c.querySelector('[class*="st-key-pidmain_"]'));
        const c = getComputedStyle(col);
        return {over: c.overflowY, scrollable: col.scrollHeight > col.clientHeight + 10,
                h: col.getBoundingClientRect().bottom, page: document.querySelector('[data-testid=stMain]').scrollHeight};
    }""")
    assert m["over"] == "auto" and m["scrollable"], m          # hlavní plocha roluje sama
    assert m["page"] <= page.viewport_size["height"] + 2, m    # stránka jako celek nepřetéká


def test_fields_are_white_with_border(page):
    """Pole mají bílé pozadí a rámeček (CSS na vnitřní označení prvků Streamlitu)."""
    for sel in ('[data-testid="stSelectbox"] > div:not([data-testid])', '[data-testid="stTextInputRootElement"]'):
        st_ = page.evaluate(f"""() => {{ const e = [...document.querySelectorAll('{sel}')].find(x => x.offsetParent);
            if (!e) return null; const c = getComputedStyle(e);
            return [c.backgroundColor, c.borderTopWidth]; }}""")
        assert st_ is not None, sel
        assert st_[0] == "rgb(255, 255, 255)" and st_[1] == "1px", (sel, st_)


def test_labels_aligned_with_fields(page):
    """Řádek „popisek | pole“: střed popisku a pole ve stejné výšce (±2 px)."""
    rows = page.evaluate("""() => [...document.querySelectorAll('.pid-plab')].filter(e => e.offsetParent).slice(0, 4)
        .map(l => { const row = l.closest('[data-testid=stHorizontalBlock]'); if (!row || row.children.length < 2) return null;
                    const f = row.children[1].getBoundingClientRect(), b = l.getBoundingClientRect();
                    return (b.top + b.bottom) / 2 - (f.top + f.bottom) / 2; }).filter(x => x !== null)""")
    assert rows and all(abs(d) <= 2 for d in rows), rows


def test_data_viewer(page):
    """
    Data: prohlížeč záznamu – panel pro PV + SP, MV a poruchu, seznam všech signálů; kurzory s odečtem hodnot
    každého zobrazeného signálu; tabulka hodnot výřezu – zoom kolečkem výřez (počet řádků) zmenší.
    """
    _tab(page, 0)
    assert page.locator(".pidv-panel").count() >= 3
    assert page.locator(".pidv-sig").count() >= 4
    page.locator(".pidv-bar [data-a=cur]").click()
    page.wait_for_timeout(300)
    assert page.locator(".pidv-read tbody tr").count() >= 4          # PV, SP, MV, porucha
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
    page.locator(".pidv-bar [data-a=full]").click()
    page.wait_for_timeout(300)
    assert rows() == n0
    page.locator(".pidv-bar [data-a=tab]").click()
    page.locator(".pidv-bar [data-a=cur]").click()
    # měřítko Y signálu: pevné min / max z okénka u signálu, zpět na auto
    yb = page.locator(".pidv-sig", has_text="LIC101.MV").locator(".pidv-yb")
    yb.click()
    page.locator(".pidv-pop input[value=fix]").check()
    page.locator(".pidv-pop [data-k=lo]").fill("0")
    page.locator(".pidv-pop [data-k=hi]").fill("100")
    page.locator(".pidv-pop [data-k=ok]").click()
    assert yb.inner_text().replace(" ", "") == "0–100"
    yb.click()
    page.locator(".pidv-pop input[value=view]").check()
    page.locator(".pidv-pop [data-k=x]").click()
    assert yb.inner_text() == "auto"


def test_data_viewer_analysis(page):
    """
    Data › Analýza: události (skoky MV ukázky), odezva na skok mezi kurzory (najít skok → zesílení), korelace
    a vypočtený signál ze vzorce (nový panel; chybný vzorec hlásí chybu).
    """
    _tab(page, 0)
    page.locator(".pidv-tabb[data-an=ev]").click()
    page.wait_for_timeout(500)
    assert page.locator(".pidv-an tbody tr").count() >= 6                 # ukázka: 6 skoků MV, skoky přítoku
    page.locator(".pidv-tabb[data-an=step]").click()
    page.locator(".pidv-an [data-k=find]").click()
    page.wait_for_timeout(500)
    assert page.locator(".pidv-an .pidv-kv tr").count() >= 4
    page.locator(".pidv-tabb[data-an=corr]").click()
    page.locator(".pidv-an [data-k=run]").click()
    page.wait_for_timeout(500)
    assert page.locator(".pidv-an tbody tr").count() >= 2
    n0 = page.locator(".pidv-panel").count()
    page.locator(".pidv-add").click()
    form = page.locator(".pidv-calc").first
    form.locator("[data-k=name]").fill("odchylka")
    form.locator("[data-k=expr]").fill("LIC101.SP - LIC101.PV")
    form.locator("[data-k=ok]").click()
    page.wait_for_timeout(500)
    assert page.locator(".pidv-panel").count() == n0 + 1
    page.locator(".pidv-add").click()
    form = page.locator(".pidv-calc").first
    form.locator("[data-k=name]").fill("x")
    form.locator("[data-k=expr]").fill("nic + 1")
    form.locator("[data-k=ok]").click()
    assert "nic" in form.locator(".pidv-cerr").inner_text()
    form.locator("[data-k=cancel]").click()
    page.locator(".pidv-tabb.on").click()                                # analýzu zavřít
    page.locator(".pidv-bar [data-a=cur]").click()                       # kurzory zapnula odezva na skok


def test_model_handle_drag(page):
    """Model: tažení táhla konce úseku doleva zkrátí úsek (hodnota v políčku pod grafem se změní)."""
    _tab(page, 1)
    page.wait_for_selector(".pidw-handle", timeout=30000)
    end0 = page.locator(".pidw-chip input").nth(1).input_value()
    h = page.locator(".pidw-handle").nth(1).bounding_box()
    page.mouse.move(h["x"] + 10, h["y"] + 10)
    page.mouse.down()
    for k in range(12):
        page.mouse.move(h["x"] + 10 - 12 * k, h["y"] + 10)
        page.wait_for_timeout(20)
    page.mouse.up()
    _idle(page, 1500)
    assert page.locator(".pidw-chip input").nth(1).input_value() != end0
