"""
Model › Identifikace: graf je prohlížeč záznamu (viewer.js) s vrstvou úseků identifikace (viewer_spans.js) a přepínači
průběhu modelu (viewer_model.js) – ne dřívější samostatný graf úseků. Výchozí panely (PV + SP + model | MV | každá porucha), přepínač
úseků společný / podle vstupů (PATCH win_mode), tažení táhel (PUT /range, PUT /windows), časové kurzory A / B, přidání
dalšího signálu ze záznamu, rozložení uložené po smyčce (nastavení mview) nezávisle na Trendech (dview), průběh modelu a
rezidua, kontrast štítků úseků. Potřebuje sestavené UI (cd frontend && npm run build).
"""
import io
import json
import os
import re
import time
import urllib.request

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("playwright.sync_api")
import test_frontend as _tf  # noqa: E402

TOKEN = _tf.TOKEN
server, page = _tf.server, _tf.page                      # fixtury serveru a prohlížeče
B = "/api/v1/workspaces/{wid}"
M = '[data-testid="model-trend"]'
SHOT = os.environ.get("MODELCHART_SHOT")                 # složka pro snímky obrazovky (jen ruční kontrola)


def _call(server, page, method, path, body=None, raw=None):
    wid = page.evaluate("sessionStorage.getItem('pid.wid')")
    data = raw if raw is not None else (None if body is None else json.dumps(body).encode())
    req = urllib.request.Request(server + path.format(wid=wid), method=method, data=data, headers={
        "X-PID-Token": TOKEN, "Content-Type": "application/octet-stream" if raw is not None else "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=120).read() or b"null")


def _until(fn, timeout=30.0):
    end = time.time() + timeout
    while time.time() < end:
        v = fn()
        if v:
            return v
        time.sleep(0.2)
    raise AssertionError("timeout")


def _state(pg):
    return pg.evaluate("() => window.__pidView.model_view.state()")


def _open_model(pg):
    pg.locator('[data-tab="model"]').click()
    pg.locator('[data-testid="model-subtabs"] [data-sub="ident"]').click()
    pg.wait_for_selector(f"{M} .pidv-panel canvas", timeout=30000)
    pg.wait_for_selector(f'{M} [data-testid="mw-track"]', timeout=30000)
    pg.wait_for_timeout(400)


def _reload(pg):
    pg.reload(wait_until="networkidle")
    pg.wait_for_selector('[data-testid="api-ok"]', timeout=20000)
    _open_model(pg)


@pytest.fixture(scope="module")
def chart(page, server):
    """Demo a identifikovaný model (P1D, I1D); otevřený Model › Identifikace."""
    page.locator('[data-tab="data"]').click()
    page.locator('[data-sub="sources"]').click()
    page.locator('[data-testid="src-demo"]').click()
    page.wait_for_function("() => (document.querySelector('[data-testid=\"data-info\"]')||{}).innerText?.includes('demo')")
    _call(server, page, "PATCH", B + "/settings", {"chosen": ["P1D", "I1D"], "win_mode": "common"})
    j = _call(server, page, "POST", B + "/identify", {})
    _until(lambda: _call(server, page, "GET", f"/api/v1/jobs/{j['id']}")["state"] not in ("queued", "running"), 120)
    page.reload(wait_until="networkidle")
    page.wait_for_selector('[data-testid="api-ok"]', timeout=20000)
    _open_model(page)
    return page


def _box(pg, sel, tries=20):
    """
    Poloha prvku po posunu na střed okna (mimo přilepený přehled záznamu dole). Vrstva úseků lištu po změně dat ze
    serveru sestaví znovu, takže prvek může mezi čekáním a čtením polohy zmizet – pak se zkusí znovu.
    """
    for _ in range(tries):
        pg.locator(sel).first.wait_for(timeout=10000)
        pg.evaluate("s => document.querySelector(s)?.scrollIntoView({block: 'center'})", sel)
        pg.wait_for_timeout(200)
        bb = pg.evaluate("""s => { const e = document.querySelector(s); if (!e) return null;
          const r = e.getBoundingClientRect(); return {x: r.x, y: r.y, width: r.width, height: r.height}; }""", sel)
        if bb and bb["width"] > 0:
            return bb
    raise AssertionError(f"element not stable: {sel}")


def _drag(pg, sel, dx):
    """Táhne prvek o dx pixelů (táhlo úseku); posluchače tažení jsou na okně."""
    bb = _box(pg, sel)
    x, y = bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] / 2
    pg.mouse.move(x, y)
    pg.mouse.down()
    for i in range(1, 9):
        pg.mouse.move(x + dx * i / 8, y)
    pg.mouse.up()


def test_default_panels(chart, server):
    ws = _call(server, chart, "GET", B)
    st = _state(chart)
    panels = [p["sigs"] for p in st["panels"]]
    assert len(panels) == 2 + len(ws["dists"]), panels                       # PV+SP+model | MV | každá porucha zvlášť
    assert panels[0][:2] == [ws["pv"], ws["sp"]] and len(panels[0]) == 3     # třetí = celý model
    assert panels[1] == [ws["mv"]]
    assert [p for p in panels[2:]] == [[d] for d in ws["dists"]]
    assert chart.locator(f"{M} .pidv-panel").count() == len(panels)
    # model je vykreslen čárkovaně a jeho štítek je v hlavičce panelu 1
    assert chart.locator(f"{M} .pidv-panel").first.locator(".pidv-chip").count() == 3
    # přepínače modelu: celý / MV / poruchy, v úsecích / celý záznam, rezidua
    grp = chart.locator(f'{M} [data-testid="mw-model"]')
    assert grp.locator('[data-g="mpart"] button').count() == 3
    assert grp.locator('[data-g="mrange"] button.on').get_attribute("data-v") == "full"
    assert grp.locator('[data-testid="mw-resid"]').is_checked() is False
    assert SHOT is None or chart.locator(M).screenshot(path=os.path.join(SHOT, "modelchart-common.png")) is not None


def test_model_parts_and_residuals(chart, server):
    ws = _call(server, chart, "GET", B)
    grp = chart.locator(f'{M} [data-testid="mw-model"]')
    grp.locator('[data-g="mpart"] button[data-v="mv"]').click()
    chart.wait_for_function("() => window.__pidView.model_view.state().panels[0].sigs.some(n => /MV part|část od MV/.test(n))")
    assert len(_state(chart)["panels"][0]["sigs"]) == 3                       # model v panelu jen jeden: část od MV
    grp.locator('[data-g="mpart"] button[data-v="dv"]').click()
    chart.wait_for_function("() => window.__pidView.model_view.state().panels[0].sigs.some(n => /disturbance part|část od poruch/.test(n))")
    grp.locator('[data-g="mrange"] button[data-v="win"]').click()
    grp.locator('[data-g="mpart"] button[data-v="all"]').click()
    chart.wait_for_function("() => window.__pidView.model_view.state().panels[0].sigs.some(n => /segments only|jen úseky/.test(n))")
    grp.locator('[data-g="mrange"] button[data-v="full"]').click()
    chart.wait_for_function("() => window.__pidView.model_view.state().panels[0].sigs.some(n => /^Model$/.test(n))")
    n0 = chart.locator(f"{M} .pidv-panel").count()
    grp.locator('[data-testid="mw-resid"]').check()
    chart.wait_for_function("n => document.querySelectorAll('%s .pidv-panel').length === n + 1" % M, arg=n0)
    grp.locator('[data-testid="mw-resid"]').uncheck()
    chart.wait_for_function("n => document.querySelectorAll('%s .pidv-panel').length === n" % M, arg=n0)
    assert _state(chart)["panels"][0]["sigs"][:2] == [ws["pv"], ws["sp"]]


def test_mode_switch_patches_win_mode(chart, server):
    seg = f'{M} .pidv-seg[data-g="wmode"]'
    n_in = 1 + len(_call(server, chart, "GET", B)["dists"])
    assert chart.locator(f'{M} [data-testid="mw-track"]').count() == 1       # společný úsek: jedna lišta
    chart.locator(f'{seg} button[data-v="inputs"]').click()
    _until(lambda: _call(server, chart, "GET", B + "/settings")["win_mode"] == "inputs")
    chart.wait_for_function("n => document.querySelectorAll('%s [data-testid=\"mw-track\"]').length === n" % M, arg=n_in)
    assert chart.locator(f'{M} [data-testid="mw-badge"]').count() == n_in    # štítek s počtem úseků v panelu vstupu
    assert chart.locator(f'{seg} button.on').get_attribute("data-v") == "inputs"
    chart.wait_for_selector(f'{M} [data-testid="mw-wlab"]', timeout=10000)                  # štítek úseku na liště
    assert SHOT is None or chart.locator(M).screenshot(path=os.path.join(SHOT, "modelchart-inputs.png")) is not None
    chart.locator(f'{seg} button[data-v="common"]').click()
    _until(lambda: _call(server, chart, "GET", B + "/settings")["win_mode"] == "common")
    chart.wait_for_function("() => document.querySelectorAll('%s [data-testid=\"mw-track\"]').length === 1" % M)


def test_drag_handle_common_puts_range(chart, server):
    before = _call(server, chart, "GET", B)["rng"]
    puts = []
    chart.on("request", lambda r: puts.append((r.method, r.url)) if r.method == "PUT" else None)
    _drag(chart, f'{M} [data-testid="mw-track"][data-owner="common"] [data-testid="mw-handle"][data-k="1"]', -150)
    after = _until(lambda: (lambda r: r if r != before else None)(_call(server, chart, "GET", B)["rng"]))
    assert after[1] < before[1] and abs(after[0] - before[0]) < 1e-6
    assert any(u.endswith("/range") for _, u in puts), puts
    # čip úseku ukazuje nová čísla a políčko jde psát (Enter) → znovu PUT /range
    chip = chart.locator(f'{M} [data-testid="mw-chips"][data-owner="common"] input').nth(1)
    chip.fill("30")
    chip.press("Enter")
    unit = chart.evaluate("/\\bmin\\b/.test(document.querySelector('%s [data-testid=\"mw-chip\"]').innerText) ? 60 : 1" % M)
    _until(lambda: abs(_call(server, chart, "GET", B)["rng"][1] - 30 * unit) < 1.5)
    _call(server, chart, "PUT", B + "/range", {"a": before[0], "b": before[1]})
    _reload(chart)


def test_drag_handle_inputs_puts_windows(chart, server):
    chart.locator(f'{M} .pidv-seg[data-g="wmode"] button[data-v="inputs"]').click()
    _until(lambda: _call(server, chart, "GET", B + "/settings")["win_mode"] == "inputs")
    chart.wait_for_selector(f'{M} [data-testid="mw-track"][data-owner="MV"]')
    before = _call(server, chart, "GET", B + "/windows")["wins"]
    puts = []
    chart.on("request", lambda r: puts.append((r.method, r.url)) if r.method == "PUT" else None)
    _drag(chart, f'{M} [data-testid="mw-track"][data-owner="MV"] [data-testid="mw-handle"][data-k="1"]', -120)
    after = _until(lambda: (lambda w: w if w != before else None)(_call(server, chart, "GET", B + "/windows")["wins"]))
    assert after["MV"][0][1] < before["MV"][0][1]
    assert any(u.endswith("/windows") for _, u in puts), puts
    # přidání a odebrání úseku vstupu
    n0 = len(after["MV"])
    chart.locator(f'{M} [data-testid="mw-add"]').first.click()
    _until(lambda: len(_call(server, chart, "GET", B + "/windows")["wins"]["MV"]) == n0 + 1)
    chart.locator(f'{M} [data-testid="mw-chips"][data-owner="MV"] [data-a="del"]').last.click()
    _until(lambda: len(_call(server, chart, "GET", B + "/windows")["wins"]["MV"]) == n0)
    # rozhraní se srovná se serverem (opožděné načtení po přidání může úsek na chvíli vrátit) – teprve pak dvojklik
    _until(lambda: chart.locator(f'{M} [data-testid="mw-chips"][data-owner="MV"] [data-testid="mw-chip"]').count() == n0)
    chart.wait_for_timeout(500)
    # dvojklik na liště přitáhne nejbližší mez na místo kliknutí
    trk = _box(chart, f'{M} [data-testid="mw-track"][data-owner="MV"]')
    w0 = _call(server, chart, "GET", B + "/windows")["wins"]["MV"][0]
    chart.mouse.dblclick(trk["x"] + trk["width"] * 0.9, trk["y"] + 30)
    _until(lambda: _call(server, chart, "GET", B + "/windows")["wins"]["MV"][0] != w0)
    # návrat do výchozího stavu
    _call(server, chart, "PUT", B + "/windows", {"wins": before})
    _call(server, chart, "PATCH", B + "/settings", {"win_mode": "common"})
    _reload(chart)


def test_time_cursors_ab(chart):
    bar = chart.locator(f"{M} .pidv-bar")
    bar.locator("[data-a=cur]").click()
    assert _state(chart)["cur"]["on"]
    chart.evaluate("s => document.querySelector(s)?.scrollIntoView({block: 'center'})", f"{M} .pidv-panel canvas")
    chart.wait_for_timeout(200)
    cv = chart.locator(f"{M} .pidv-panel").first.locator("canvas").nth(1).bounding_box()
    chart.mouse.click(cv["x"] + cv["width"] * 0.35, cv["y"] + cv["height"] / 2)
    chart.keyboard.down("Shift")
    chart.mouse.click(cv["x"] + cv["width"] * 0.6, cv["y"] + cv["height"] / 2)
    chart.keyboard.up("Shift")
    st = _state(chart)["cur"]
    assert st["a"] is not None and st["b"] is not None and st["a"] < st["b"]
    txt = chart.locator(f"{M} .pidv-read").first.inner_text()
    assert "Δt" in txt and "A" in txt and "B" in txt
    assert re.search(r"Model", txt)                                         # odečet zahrnuje i průběh modelu
    # hodnotové kurzory, osa Y: zoom kolečkem nad osou mění rozsah
    bar.locator("[data-a=hcur]").click()
    assert _state(chart)["hc"]["on"] and chart.locator(f"{M} [data-testid=hc-sig]").count() == 1
    bar.locator("[data-a=hcur]").click()
    chart.evaluate("s => document.querySelector(s)?.scrollIntoView({block: 'center'})", f"{M} .pidv-panel canvas")
    chart.wait_for_timeout(200)
    cv = chart.locator(f"{M} .pidv-panel").first.locator("canvas").nth(1).bounding_box()
    ax = {"x": cv["x"] + 40, "y": cv["y"] + cv["height"] / 2}
    chart.mouse.move(ax["x"], ax["y"])
    chart.mouse.wheel(0, -200)
    chart.wait_for_function("() => Object.values(window.__pidView.model_view.state().sig).some(c => c.lo !== undefined)")   # osa Y přiblížena
    bar.locator("[data-a=cur]").click()
    assert not _state(chart)["cur"]["on"]


def test_exports_png_csv(chart):
    with chart.expect_download() as d:
        chart.locator(f'{M} .pidv-bar [data-a="png"]').click()
    assert d.value.suggested_filename.endswith(".png")
    with chart.expect_download() as d:
        chart.locator(f'{M} .pidv-bar [data-a="csv_view"]').click()
    path = d.value.path()
    head = open(path, encoding="utf-8-sig").readline()
    assert "Model" in head


def _csv_extra():
    t = np.arange(0, 1800.0)
    sp = 50 + 5 * np.sign(np.sin(t / 300))
    pv = sp + np.sin(t / 40)
    mv = 40 + 8 * np.sin(t / 200)
    t0 = pd.Timestamp("2026-10-08 09:00:00")
    df = pd.DataFrame({"Time": t0 + pd.to_timedelta(t, unit="s"), "TIC102.PV": pv, "TIC102.SP": sp,
                       "TIC102.MV": mv, "XTRA.TEMP [degC]": 20 + 0.01 * t})
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode()


def test_add_signal_and_layout_per_loop(chart, server):
    """Další signál ze záznamu v seznamu signálů; rozložení se ukládá do mview (po smyčce), dview (Trendy) se nemění."""
    wid0 = chart.evaluate("sessionStorage.getItem('pid.wid')")
    dview0 = _call(server, chart, "GET", B + "/settings").get("dview")
    new = json.loads(urllib.request.urlopen(urllib.request.Request(
        server + "/api/v1/workspaces", method="POST", data=b"", headers={"X-PID-Token": TOKEN}), timeout=60).read())
    chart.evaluate("w => sessionStorage.setItem('pid.wid', w)", new["id"])
    _call(server, chart, "POST", f"/api/v1/workspaces/{new['id']}/sources?name=x.csv&timezone=UTC", raw=_csv_extra())
    _call(server, chart, "POST", f"/api/v1/workspaces/{new['id']}/loops/suggest", {"apply": True})
    _reload(chart)
    names = chart.locator(f"{M} .pidv-list .pidv-sig .nm").all_inner_texts()
    assert any("XTRA.TEMP" in n for n in names), names                          # ostatní signály záznamu jsou v seznamu
    before = [p["sigs"] for p in _state(chart)["panels"]]
    assert not any("XTRA.TEMP" in n for p in before for n in p)                 # výchozí rozložení je beze změny
    row = chart.locator(f"{M} .pidv-list .pidv-sig", has_text="XTRA.TEMP").first
    row.locator("input[type=checkbox]").check()
    chart.wait_for_function("() => window.__pidView.model_view.state().panels.some(p => p.sigs.some(n => n.includes('XTRA.TEMP')))")
    # uloženo po smyčce: nastavení mview (po 1,5 s klidu), ne dview
    saved = _until(lambda: _call(server, chart, "GET", B + "/settings").get("mview"), 15)
    assert "XTRA.TEMP" in saved
    assert _call(server, chart, "GET", B + "/settings").get("dview") == dview0
    _reload(chart)                                                              # po znovunačtení je signál v grafu
    assert any("XTRA.TEMP" in n for p in _state(chart)["panels"] for n in p["sigs"])
    # Trendy mají vlastní rozložení: změna dview model nezmění
    _call(server, chart, "PATCH", B + "/settings", {"dview": json.dumps({"v": 1, "panels": []})})
    _reload(chart)
    assert any("XTRA.TEMP" in n for p in _state(chart)["panels"] for n in p["sigs"])
    # jiná smyčka (původní prostor) má vlastní, nedotčené rozložení
    chart.evaluate("w => sessionStorage.setItem('pid.wid', w)", wid0)
    _reload(chart)
    assert not any("XTRA.TEMP" in n for p in _state(chart)["panels"] for n in p["sigs"])
    assert _call(server, chart, "GET", B + "/settings").get("mview") in (None, "") or \
        "XTRA.TEMP" not in _call(server, chart, "GET", B + "/settings")["mview"]


def _lum(rgb):
    c = [x / 255 for x in rgb]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def _contrast(a, b):
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _rgb(s):
    return tuple(int(x) for x in re.findall(r"\d+", s)[:3])


def _label_contrasts(pg):
    rows = pg.evaluate("""(sel) => [...document.querySelectorAll(sel + ' [data-testid="mw-wlab"], ' + sel + ' [data-testid="mw-badge"], ' + sel + ' [data-testid="mw-chip"]')]
        .map(e => { const s = getComputedStyle(e); return [e.dataset.testid, s.color, s.backgroundColor, e.innerText.slice(0, 20)]; })""", M)
    return [(k, _contrast(_rgb(c), _rgb(b)), t) for k, c, b, t in rows]


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("mode", ["common", "inputs"])
def test_segment_label_contrast(chart, server, theme, mode):
    """Štítky úseků, štítky počtu a čipy mají kontrast textu ≥ 4,5 : 1 (změřeno z vypočtených barev) ve světlém i tmavém vzhledu."""
    ws = _call(server, chart, "GET", B)
    wins0 = _call(server, chart, "GET", B + "/windows")["wins"]
    if mode == "inputs":                                                        # úsek má i porucha: změří se štítky všech vstupů
        _call(server, chart, "PUT", B + "/windows", {"wins": {**wins0, ws["dists"][0]: [[600.0, 1500.0]]}})
    _call(server, chart, "PATCH", B + "/settings", {"win_mode": mode})
    _reload(chart)
    _tf._settings(chart)
    chart.select_option('select[aria-label="theme"]', theme)
    chart.locator('[data-testid="settings"] summary').click()                   # zavřít panel Nastavení
    chart.wait_for_function("t => document.querySelector('%s .pidv').classList.contains('dark') === (t === 'dark')" % M, arg=theme, timeout=20000)
    chart.wait_for_selector(f'{M} [data-testid="mw-wlab"]', timeout=20000)
    chart.wait_for_timeout(400)
    rows = _label_contrasts(chart)
    assert rows
    if mode == "inputs":
        assert len({r[2][:3] for r in rows if r[0] == "mw-wlab"}) >= 2 and len([r for r in rows if r[0] == "mw-wlab"]) >= 2
    bad = [r for r in rows if r[1] < 4.5]
    assert not bad, bad
    if SHOT:
        chart.locator(M).screenshot(path=os.path.join(SHOT, f"modelchart-{mode}-{theme}.png"))
    if theme == "dark":
        _tf._settings(chart)
        chart.select_option('select[aria-label="theme"]', "light")
        chart.locator('[data-testid="settings"] summary').click()
    _call(server, chart, "PUT", B + "/windows", {"wins": wins0})
    _call(server, chart, "PATCH", B + "/settings", {"win_mode": "common"})
