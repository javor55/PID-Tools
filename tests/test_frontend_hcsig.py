"""
Data › Trendy: hodnotové kurzory Y₁ / Y₂ měří jeden signál – výběr signálu v panelu nástrojů (select data-testid=hc-sig),
jméno signálu v odečtu a kontrast textu štítků kurzorů (barvy z CSS proměnných prohlížeče záznamu) ve světlém i tmavém vzhledu.
Potřebuje sestavené UI (cd frontend && npm run build).
"""
import os
import re

import pytest

pytest.importorskip("playwright.sync_api")
import test_frontend as _tf  # noqa: E402
import test_frontend_trends as _tt  # noqa: E402

server, page = _tf.server, _tf.page
trends = _tt.trends                                      # fixtura: dva zdroje, otevřené Trendy
V = '[data-testid="trd-viewer"]'
SHOT = os.environ.get("HCSIG_SHOT")


def _state(p):
    return p.evaluate("() => window.__pidView.trends_view.state()")


def _lum(rgb):
    c = [x / 255 for x in rgb]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def _contrast(a, b):
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _rgb(s):
    s = s.strip()
    if s.startswith("#"):
        s = s[1:]
        s = "".join(ch * 2 for ch in s) if len(s) == 3 else s
        return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))
    return tuple(int(x) for x in re.findall(r"\d+", s)[:3])


def _label_contrast(p):
    """Kontrast barvy textu štítku (--pv-text) k podkladu štítku (--pv-card) – tak je štítek kreslen."""
    t, c = p.evaluate("""() => { const s = getComputedStyle(document.querySelector('%s .pidv'));
        return [s.getPropertyValue('--pv-text'), s.getPropertyValue('--pv-card')]; }""" % V)
    return _contrast(_rgb(t), _rgb(c))


def test_hc_signal_selector(trends):
    bar = trends.locator(f"{V} .pidv-bar")
    assert trends.locator(f"{V} [data-testid=hc-sig]").count() == 0          # kurzory vypnuté → bez výběru
    # panel s více signály: jeden panel pro všechno
    trends.locator('[data-testid="trd-layout"] button').nth(0).click()
    trends.wait_for_function("() => window.__pidView.trends_view.state().panels.length === 1")
    bar.locator("[data-a=hcur]").click()
    sel = trends.locator(f"{V} [data-testid=hc-sig]")
    assert sel.count() == 1
    assert sel.get_attribute("aria-label")
    opts = sel.locator("option").all_inner_texts()
    shown = trends.evaluate("() => window.__pidView.trends_view.state().panels.flatMap(p => p.sigs)")
    assert len(opts) >= 2 and opts == shown
    first = _state(trends)["hc"]["sig"]
    assert sel.input_value() == first
    other = next(o for o in opts if o != first)
    sel.select_option(other)
    assert _state(trends)["hc"]["sig"] == other
    trends.wait_for_function(
        "n => document.querySelector('%s .pidv-read .pidv-rhead span').innerText.trim() === n" % V, arg=other)
    assert trends.locator(f"{V} [data-testid=hc-sig]").input_value() == other
    # změna aktivního signálu jinak (štítek v panelu) se promítne do výběru
    chip = trends.locator(f"{V} .pidv-chip[data-n='{first}']")
    chip.click()
    trends.wait_for_function("n => document.querySelector('%s [data-testid=hc-sig]').value === n" % V, arg=first)
    assert _state(trends)["hc"]["sig"] == first
    # signál zmizel z grafu → výběr se přepne na zobrazený signál
    trends.locator(f"{V} .pidv-chip[data-n='{other}']").click()
    trends.locator('[data-testid="trd-tree"] .pidv-sig', has_text=other).first.locator("input[type=checkbox]").uncheck()
    trends.wait_for_function(
        "n => !window.__pidView.trends_view.state().panels.flatMap(p => p.sigs).includes(n)", arg=other)
    trends.wait_for_function("() => document.querySelector('%s [data-testid=hc-sig]') !== null" % V)
    now = _state(trends)["hc"]["sig"]
    assert now != other and trends.locator(f"{V} [data-testid=hc-sig]").input_value() == now
    # kurzory vypnuté → výběr zmizí
    bar.locator("[data-a=hcur]").click()
    assert trends.locator(f"{V} [data-testid=hc-sig]").count() == 0


def test_hc_label_contrast_and_screenshot(trends):
    bar = trends.locator(f"{V} .pidv-bar")
    if not _state(trends)["hc"]["on"]:
        bar.locator("[data-a=hcur]").click()
    trends.wait_for_selector(f"{V} [data-testid=hc-sig]")
    trends.wait_for_timeout(300)
    assert _label_contrast(trends) >= 4.5
    if SHOT:
        trends.locator(V).screenshot(path=SHOT)
    _tf._settings(trends)
    trends.select_option('select[aria-label="theme"]', "dark")
    trends.wait_for_function("() => document.querySelector('%s .pidv').classList.contains('dark')" % V, timeout=20000)
    assert _label_contrast(trends) >= 4.5
    trends.select_option('select[aria-label="theme"]', "light")
