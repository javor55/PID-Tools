"""
Kontrola textů v prohlížeči (TICKET-016): v žádné záložce, podzáložce, sekci nastavení ani kartě průvodce není vidět
surový klíč překladu, tj. text odpovídající `^[a-z][a-z0-9]*(_[a-z0-9]+)+$` jako celý obsah textového uzlu
(ani jako `title` / `aria-label` / `placeholder`). Prochází se Data (Zdroje, Trendy, Kvalita, Diagnostika obě),
Model (3 podzáložky), Ladění (3 pohledy), APC (všechny techniky), Živá simulace, Projekt, Nastavení (všechny
sekce) a průvodce (F1, všechny karty). Ukázková data a identifikace přes API.
Potřebuje sestavené UI (cd frontend && npm run build).
"""
import json
import re
import time
import urllib.request

import pytest

pytest.importorskip("playwright.sync_api")
import test_frontend as _tf  # noqa: E402

TOKEN = _tf.TOKEN
server, page = _tf.server, _tf.page                      # fixtury serveru a prohlížeče
B = "/api/v1/workspaces/{wid}"
RAW = re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+)+$")

# Prochází celý dokument včetně skrytých částí (zavřené karty, dialog průvodce); vrací [[kde, text], …]
_SCAN = """() => {
  const out = [];
  const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let n = w.nextNode(); n; n = w.nextNode()) {
    const p = n.parentElement;
    if (!p || /^(SCRIPT|STYLE|NOSCRIPT|TEMPLATE)$/.test(p.tagName)) continue;
    const t = n.nodeValue.trim();
    if (t) out.push(["text", t]);
  }
  for (const e of document.querySelectorAll("[title],[aria-label],[placeholder]"))
    for (const a of ["title", "aria-label", "placeholder"]) {
      const v = (e.getAttribute(a) || "").trim();
      if (v) out.push([a, v]);
    }
  return out;
}"""


def _call(server, page, method, path, body=None):
    wid = page.evaluate("sessionStorage.getItem('pid.wid')")
    req = urllib.request.Request(server + path.format(wid=wid), method=method,
                                 data=None if body is None else json.dumps(body).encode(),
                                 headers={"X-PID-Token": TOKEN, "Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=120).read() or b"null")


def _until(fn, timeout=30.0):
    end = time.time() + timeout
    while time.time() < end:
        v = fn()
        if v:
            return v
        time.sleep(0.2)
    raise AssertionError("timeout")


def _settle(pg):
    """Počká na dokončení načítání (žádný prvek s aria-busy) a na ustálení překreslení."""
    pg.wait_for_load_state("networkidle")
    try:
        pg.wait_for_function("() => !document.querySelector('[aria-busy=\"true\"]')", timeout=15000)
    except Exception:
        pass                                                 # dlouhý výpočet: kontrola se provede i tak
    pg.wait_for_timeout(500)


def _scan(pg, where, found, seen):
    seen.append(where)
    for kind, text in pg.evaluate(_SCAN):
        if RAW.match(text):
            found.append(f"{where} [{kind}]: {text}")


@pytest.fixture(scope="module")
def ready(page, server):
    page.locator('[data-tab="data"]').click()
    page.locator('[data-sub="sources"]').click()
    page.locator('[data-testid="src-demo"]').click()
    page.wait_for_function("() => (document.querySelector('[data-testid=\"data-info\"]')||{}).innerText?.includes('demo')")
    _call(server, page, "PATCH", B + "/settings", {"chosen": ["P1D", "I1D"]})
    j = _call(server, page, "POST", B + "/identify", {})
    _until(lambda: _call(server, page, "GET", f"/api/v1/jobs/{j['id']}")["state"] not in ("queued", "running"), 120)
    page.reload(wait_until="networkidle")
    page.wait_for_selector('[data-testid="api-ok"]', timeout=20000)
    return page


def test_no_raw_keys_in_any_view(ready):
    pg = ready
    found, seen = [], []

    def tab(name):
        pg.locator(f'[data-tab="{name}"]').click()
        _settle(pg)

    # Data: podzáložky a obě Diagnostiky
    tab("data")
    for sub in ("sources", "trends", "quality", "diag"):
        pg.locator(f'[data-testid="data-subtabs"] [data-sub="{sub}"]').click()
        _settle(pg)
        _scan(pg, f"data/{sub}", found, seen)
    for v in ("diag-all", "diag-detail"):
        pg.locator(f'[data-testid="diag-sub"] [data-value="{v}"]').click()
        _settle(pg)
        _scan(pg, f"data/{v}", found, seen)

    # Model: Identifikace, Validace, Rezidua a nejistota
    tab("model")
    for sub in ("ident", "validate", "residuals"):
        pg.locator(f'[data-testid="model-subtabs"] [data-sub="{sub}"]').click()
        _settle(pg)
        _scan(pg, f"model/{sub}", found, seen)

    # Ladění: čas / frekvence / vše
    tab("tuning")
    pg.wait_for_selector('[data-testid="tun-view"]', timeout=30000)
    for v in ("time", "freq", "all"):
        pg.locator(f'[data-testid="tun-view"] [data-value="{v}"]').click()
        _settle(pg)
        _scan(pg, f"tuning/{v}", found, seen)

    # APC: všechny techniky
    tab("apc")
    pg.wait_for_selector('[data-testid="apc-techs"]', timeout=30000)
    techs = [b.get_attribute("data-testid") for b in pg.locator('[data-testid="apc-techs"] [role="tab"]').all()]
    assert len(techs) >= 11
    for tid in techs:
        pg.locator(f'[data-testid="{tid}"]').click()
        _settle(pg)
        _scan(pg, f"apc/{tid}", found, seen)

    # Živá simulace, Projekt a report
    tab("live")
    _scan(pg, "live", found, seen)
    tab("project")
    _scan(pg, "project", found, seen)

    # Nastavení: všechny sekce
    pg.locator('[data-testid="settings"] summary').click()
    pg.locator('[data-testid="open-settings"]').click()
    pg.wait_for_selector('[data-testid="settings-page"]', timeout=20000)
    for nav in pg.locator('[data-testid^="settings-nav-"]').all():
        tid = nav.get_attribute("data-testid")
        nav.click()
        _settle(pg)
        _scan(pg, f"settings/{tid}", found, seen)
    pg.locator('[data-testid="settings-back"]').click()
    _settle(pg)

    # Průvodce (F1) na několika záložkách, všechny karty
    for name in ("data", "model", "tuning", "apc"):
        tab(name)
        pg.keyboard.press("F1")
        pg.wait_for_selector('[data-testid="help-dialog"][open]', timeout=10000)
        for card in ("steps", "checklist", "tables", "glossary", "keys"):
            pg.locator(f'[data-testid="guide-tab-{card}"]').click()
            _settle(pg)
            _scan(pg, f"guide/{name}/{card}", found, seen)
        pg.keyboard.press("Escape")

    assert len(seen) >= 35, seen
    assert not found, "Surové klíče v rozhraní:\n" + "\n".join(sorted(set(found)))
