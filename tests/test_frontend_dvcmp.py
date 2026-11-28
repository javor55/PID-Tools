"""
Model › Identifikace: tabulka struktur přenosu poruchy má stejné sloupce jako tabulka modelů MV a strukturu volí
přepínač v řádku (beta 5). Potřebuje sestavené UI (cd frontend && npm run build).
"""
import json
import time
import urllib.request

import pytest

pytest.importorskip("playwright.sync_api")
import test_frontend as _tf  # noqa: E402

TOKEN = _tf.TOKEN
server, page = _tf.server, _tf.page                      # fixtury serveru a prohlížeče
B = "/api/v1/workspaces/{wid}"


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


def test_dv_table_like_mv_table(page, server):
    page.locator('[data-tab="data"]').click()
    page.locator('[data-sub="sources"]').click()
    page.locator('[data-testid="src-demo"]').click()
    page.wait_for_function("() => (document.querySelector('[data-testid=\"data-info\"]')||{}).innerText?.includes('demo')")
    _call(server, page, "PATCH", B + "/settings", {"chosen": ["I1D"]})
    j = _call(server, page, "POST", B + "/identify", {})
    _until(lambda: _call(server, page, "GET", f"/api/v1/jobs/{j['id']}")["state"] not in ("queued", "running"), 180)
    page.reload(wait_until="networkidle")
    page.wait_for_selector('[data-testid="api-ok"]', timeout=20000)
    page.locator('[data-tab="model"]').click()
    page.locator('[data-testid="model-subtabs"] [data-sub="ident"]').click()
    page.wait_for_selector('[data-testid="dist-cmp-0"] tr[data-struct]', timeout=60000)
    mv = page.locator('[data-testid="models"] thead th').all_inner_texts()
    dv = page.locator('[data-testid="dist-cmp-0"] thead th').all_inner_texts()
    # DV: typ místo modelu; bez případného sloupce uzavřené smyčky
    assert mv[:1] + mv[2:5] == dv[:1] + dv[2:5] and mv[2:4] == ["FIT [%]", "NRMSE [%]"] and dv[0] == "" and dv[1]
    assert mv[-1] == dv[-1]                                         # poslední sloupec: parametry modelu
    assert page.locator('[data-testid="dist-cmp-0"] tr[data-current="1"]').get_attribute("class") == "sel"
    m = _call(server, page, "GET", B + "/model")
    d = next(r for r in m["results"] if r["code"] == m["selected"])["dists"][0]
    cur = page.locator('[data-testid="dist-cmp-0"] tr[data-current="1"]').get_attribute("data-struct")
    assert cur == d["struct"]
    other = next(c["struct"] for c in d["cmp"] if c["fit"] is not None and c["struct"] != cur)
    row = page.locator(f'[data-testid="dist-cmp-0"] tr[data-struct="{other}"]')
    assert len(row.locator("td").all_inner_texts()) == len(dv)
    page.locator(f'[data-testid="dist-use-0-{other}"]').click()
    page.wait_for_selector(f'[data-testid="dist-cmp-0"] tr[data-struct="{other}"][data-current="1"]')
    assert page.locator(f'[data-testid="dist-use-0-{other}"]').is_checked()
    _until(lambda: _call(server, page, "GET", B + "/settings").get(f"dsel|{m['selected']}|0") == other)
    page.screenshot(path="/tmp/claude-0/-home-user-PID-Tools/9e878b15-9708-5d7c-a096-74b94a632b83/scratchpad/dvcmp.png")
    page.locator('[data-testid="reset"]').click()
    page.wait_for_selector(f'[data-testid="dist-cmp-0"] tr[data-struct="{d["ident"]}"][data-current="1"]')
