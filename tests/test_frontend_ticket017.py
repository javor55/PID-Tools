"""
TICKET-017: barvy rolí a řad prohlížeče záznamu se čtou z proměnných CSS (tokens.css) a mění se s vzhledem.
Měří se v prohlížeči: barvy, kterými viewer.js skutečně kreslí čáry (zachycení strokeStyle plátna), a pozadí grafu
(--pv-card); kontrast každé řady proti pozadí musí být ≥ 3 : 1 ve světlém i tmavém vzhledu.
Potřebuje sestavené UI (cd frontend && npm run build).
"""
import re

import pytest

pytest.importorskip("playwright.sync_api")
import test_frontend as _tf  # noqa: E402

server, page = _tf.server, _tf.page                      # fixtury serveru a prohlížeče

_HEX = re.compile(r"^#[0-9a-f]{6}$")

# zachytí hodnoty strokeStyle nastavené na 2D plátnech (jednou za stránku)
_HOOK = """() => {
  if (window.__strokeHook) return;
  window.__strokeHook = true; window.__stroke = new Set();
  const d = Object.getOwnPropertyDescriptor(CanvasRenderingContext2D.prototype, 'strokeStyle');
  Object.defineProperty(CanvasRenderingContext2D.prototype, 'strokeStyle', {
    get() { return d.get.call(this); },
    set(v) { d.set.call(this, v); if (typeof v === 'string') window.__stroke.add(String(d.get.call(this)).toLowerCase()); } });
}"""
# paleta z proměnných CSS a pozadí grafu aktuálního vzhledu
_PAL = """() => {
  const cs = getComputedStyle(document.documentElement), v = n => norm(cs.getPropertyValue(n));
  const box = document.querySelector('.pidv');
  const norm = c => { const g = document.createElement('canvas').getContext('2d'); g.fillStyle = c.trim(); return g.fillStyle; };
  return { theme: document.documentElement.dataset.theme, dark: !!box && box.classList.contains('dark'),
    bg: box ? norm(getComputedStyle(box).getPropertyValue('--pv-card')) : '',
    roles: { pv: v('--pid-pv'), sp: v('--pid-sp'), mv: v('--pid-mv'), pos: v('--pid-pos') },
    series: Array.from({length: 14}, (_, i) => v('--pid-series-' + (i + 1))),
    dist: Array.from({length: 4}, (_, i) => v('--pid-dist-' + (i + 1))) };
}"""


def _lum(h):
    c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def contrast(a, b):
    hi, lo = sorted((_lum(a), _lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _demo(page):
    page.locator('[data-tab="data"]').click()
    page.locator('[data-sub="sources"]').click()
    page.locator('[data-testid="src-demo"]').click()
    page.wait_for_function("() => (document.querySelector('[data-testid=\"data-info\"]')||{}).innerText?.includes('demo')")


def _theme(page, theme):
    _tf._settings(page)
    page.select_option('select[aria-label="theme"]', theme)
    page.locator('[data-testid="settings"] summary').click()
    page.wait_for_function(f"() => document.documentElement.dataset.theme === '{theme}'")


def _measure(page, sub, host, theme):
    """Otevře podzáložku s prohlížečem ve vzhledu `theme`; vrátí paletu a barvy, kterými se kreslilo."""
    _theme(page, theme)
    page.locator('[data-tab="data"]').click()
    page.locator('[data-sub="sources"]').click()           # vynucené nové připojení prohlížeče
    page.evaluate(_HOOK)
    page.evaluate("() => window.__stroke.clear()")
    page.locator(f'[data-sub="{sub}"]').click()
    page.wait_for_selector(f'{host} .pidv-panel canvas', timeout=30000)
    page.wait_for_function(f"() => document.querySelector('{host} .pidv').classList.contains('dark') === {str(theme == 'dark').lower()}")
    page.wait_for_function("() => window.__stroke.size > 3", timeout=10000)
    pal = page.evaluate(_PAL)
    used = sorted(c for c in page.evaluate("() => [...window.__stroke]") if _HEX.match(c))
    return pal, used


def test_quality_view_colors_follow_theme(page, server):
    """Data › Kvalita dat (RecordViewer; Data › Trendy má barvy ze serveru, viz zpráva k úkolu): čáry PV / SP / MV mají barvy z proměnných vzhledu a kontrast ≥ 3 : 1 proti pozadí grafu."""
    _demo(page)
    res = {}
    for theme in ("light", "dark"):
        pal, used = _measure(page, "quality", '[data-testid="record-viewer"]', theme)
        assert _HEX.match(pal["bg"]), pal
        # každá z těchto proměnných musí být v daném vzhledu kontrastní vůči pozadí grafu
        for name, col in [*pal["roles"].items(), *[(f"series-{i + 1}", c) for i, c in enumerate(pal["series"])],
                          *[(f"dist-{i + 1}", c) for i, c in enumerate(pal["dist"])]]:
            assert _HEX.match(col), (theme, name, col)
            assert contrast(col, pal["bg"]) >= 3, (theme, name, col, pal["bg"], round(contrast(col, pal["bg"]), 2))
        # skutečně použité barvy: PV a MV (rolí smyčky) kreslí viewer právě těmito barvami
        assert pal["roles"]["pv"] in used and pal["roles"]["mv"] in used, (theme, pal["roles"], used)
        res[theme] = (pal, used)
    light, dark = res["light"][0], res["dark"][0]
    assert light["dark"] is False and dark["dark"] is True
    assert dark["roles"]["pv"] != light["roles"]["pv"]       # PV se čte z proměnné, ne z literálu
    assert dark["roles"]["pv"] not in res["light"][1]        # a ve světlém vzhledu se tmavá barva nekreslí
    assert light["roles"]["pv"] not in res["dark"][1]
    _theme(page, "light")
