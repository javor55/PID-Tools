"""
Líné načítání záložek (TICKET-019): těžké záložky jsou samostatné chunky, které se stáhnou až při prvním zobrazení;
přepnutí na ně nevyvolá chybu v konzoli a největší soubor sestavení je menší než 450 kB.
Potřebuje sestavené UI (cd frontend && npm run build).
"""
import re
from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api")
import test_frontend as _tf  # noqa: E402

TOKEN = _tf.TOKEN
server, page = _tf.server, _tf.page                      # fixtury serveru a prohlížeče
ASSETS = Path(_tf.UI).parent / "assets"
LAZY = ["ApcTab", "LiveTab", "SettingsPage", "TrendsView", "ProjectTab"]


def _chunk_of(url: str) -> str | None:
    m = re.search(r"/assets/([A-Za-z0-9_]+?)-[A-Za-z0-9_-]{6,}\.js$", url)
    return m.group(1) if m else None


def _watch(pg):
    got = []
    pg.on("request", lambda r: got.append(_chunk_of(r.url)) if "/assets/" in r.url else None)
    return got


def _wait_ok(pg):
    pg.wait_for_selector('[data-testid="api-ok"]', timeout=20000)


def test_lazy_chunks_exist():
    names = {_chunk_of("/assets/" + f.name) for f in ASSETS.glob("*.js")}
    for n in LAZY:
        assert n in names, f"chunk {n} chybí v sestavení"


def test_lazy_not_loaded_at_start(page, server):
    got = _watch(page)
    page.goto(f"{server}/#token={TOKEN}", wait_until="networkidle")
    page.reload(wait_until="networkidle")
    _wait_ok(page)
    assert any(g and g.startswith("index") for g in got)          # hlavní balík se načetl
    page.locator('[data-tab="data"]').click()
    page.locator('[data-sub="sources"]').click()
    page.wait_for_load_state("networkidle")
    for n in ("ApcTab", "LiveTab", "SettingsPage", "TrendsView", "ProjectTab"):
        assert n not in got, f"chunk {n} se načetl už při startu"


def test_lazy_tabs_render_without_console_errors(page, server):
    page.locator('[data-tab="data"]').click()
    page.locator('[data-sub="sources"]').click()
    page.locator('[data-testid="src-demo"]').click()
    page.wait_for_function("() => (document.querySelector('[data-testid=\"data-info\"]')||{}).innerText?.includes('demo')")
    got = _watch(page)
    page.errors.clear()
    console = []
    page.on("console", lambda m: console.append(m.text) if m.type == "error" else None)
    page.locator('[data-tab="data"]').click()
    page.locator('[data-sub="trends"]').click()
    page.wait_for_selector('[data-testid="tab-data"][data-dsub="trends"]', timeout=20000)
    page.locator('[data-tab="apc"]').click()
    page.wait_for_selector('[data-testid="tab-apc"]', timeout=20000)
    page.locator('[data-tab="live"]').click()
    page.wait_for_selector('[data-testid="tab-live"]', timeout=20000)
    page.locator('[data-tab="project"]').click()
    page.wait_for_selector('[data-testid="tab-project"]', timeout=20000)
    page.locator('[data-testid="settings"] summary').click()
    page.locator('[data-testid="open-settings"]').click()
    page.wait_for_function("() => !document.querySelector('[data-testid=\"qs-skeleton\"]')", timeout=20000)
    page.wait_for_load_state("networkidle")
    for n in ("ApcTab", "LiveTab", "SettingsPage", "TrendsView", "ProjectTab"):
        assert n in got, f"chunk {n} se po přepnutí nenačetl"
    assert page.locator('[data-testid="err-boundary"]').count() == 0
    assert page.errors == []
    assert console == []


def test_largest_bundle_under_450kb():
    sizes = {f.name: f.stat().st_size for f in ASSETS.glob("*.js")}
    name, size = max(sizes.items(), key=lambda kv: kv[1])
    assert size < 450_000, f"{name} má {size} B"
