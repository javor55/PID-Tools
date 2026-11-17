"""
FEATURE-007: přehled smyček v záložce Projekt s hromadnými akcemi. Projekt se třemi smyčkami (FIC1, FIC2 a FIC3 bez
buzení MV): výběr smyček, identifikace s průběhem ve stavovém řádku a souhrnem, ladění jen jako návrh, převzetí
návrhů do Setu 2, hromadný export a zrušení úlohy. Potřebuje sestavené UI (cd frontend && npm run build).
"""
import io
import json
import os
import sys
import urllib.request

import pytest

pytest.importorskip("playwright.sync_api")
import test_frontend as _tf  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_api_batch import _frame  # noqa: E402

TOKEN = _tf.TOKEN
server, page = _tf.server, _tf.page                      # fixtury serveru a prohlížeče
NAMES = ("FIC1", "FIC2", "FIC3")


def _call(page, method, path, body=None, raw=None, ctype="application/json"):
    wid = page.evaluate("sessionStorage.getItem('pid.wid')")
    data = raw if raw is not None else (None if body is None else json.dumps(body).encode())
    req = urllib.request.Request(page.server + path.format(wid=wid), method=method, data=data,
                                 headers={"X-PID-Token": TOKEN, "Content-Type": ctype})
    return json.loads(urllib.request.urlopen(req, timeout=120).read() or b"null")


def _rows(page):
    return {r["index"]: r for r in _call(page, "GET", "/api/v1/workspaces/{wid}/loops/overview")["loops"]}


def _counts(page, action):
    """Počty ze souhrnu poslední úlohy `action` (čeká, až se souhrn této úlohy objeví)."""
    page.wait_for_function("(a) => (document.querySelector('[data-testid=\"proj-batch-summary\"]')?.innerText || '').includes(a)",
                           arg=action, timeout=120000)
    el = page.locator('[data-testid="batch-counts"]')
    return {k: int(el.get_attribute(f"data-{k}")) for k in ("ok", "skipped", "error")}


@pytest.fixture(scope="module")
def three(page, server):
    """Tři smyčky nad jedním souborem (modely P1D a P2D, ať identifikace chvíli trvá), záložka Projekt › Smyčky."""
    buf = io.StringIO()
    _frame().to_csv(buf, index=False)
    _call(page, "POST", "/api/v1/workspaces/{wid}/data/file?name=three.csv", raw=buf.getvalue().encode(), ctype="application/octet-stream")
    _call(page, "PUT", "/api/v1/workspaces/{wid}/columns", {"pv": "FIC1.PV", "mv": "FIC1.MV"})
    _call(page, "PATCH", "/api/v1/workspaces/{wid}/settings", {"loop_tag": "FIC1", "chosen": ["P1D", "P2D"]})
    for nm in NAMES[1:]:
        _call(page, "POST", "/api/v1/workspaces/{wid}/loops", {"name": nm, "pv": f"{nm}.PV", "mv": f"{nm}.MV"})
        _call(page, "PATCH", "/api/v1/workspaces/{wid}/settings", {"chosen": ["P1D", "P2D"]})
    _call(page, "PUT", "/api/v1/workspaces/{wid}/loops/active", {"index": 0})
    page.reload(wait_until="networkidle")
    page.wait_for_selector('[data-testid="api-ok"]', timeout=20000)
    page.locator('[data-tab="project"]').click()
    page.locator('[data-testid="proj-sub"] [data-value="loops"]').click()
    page.wait_for_selector('[data-testid="proj-loops-table"]', timeout=30000)
    return True


def test_card_lists_loops_and_disables_actions(page, three):
    assert page.locator('[data-testid="proj-loops"]').count() == 1
    for i, nm in enumerate(NAMES):
        row = page.locator(f'[data-testid="proj-loop-{i}"]')
        assert row.count() == 1 and nm in row.inner_text()
        assert row.get_attribute("data-stage") == "data"
    assert page.locator('[data-testid="proj-loop-0"]').get_attribute("data-active") == "true"
    for b in ("identify", "tune", "accept", "export"):                  # nic není vybráno
        assert page.locator(f'[data-testid="batch-{b}"]').is_disabled()


def test_keyboard_row_selection(page, three):
    row = page.locator('[data-testid="proj-loop-1"]')
    row.focus()
    page.keyboard.press("Space")
    assert page.locator('[data-testid="batch-pick-1"]').is_checked()
    assert page.locator('[data-testid="batch-identify"]').is_enabled()
    page.keyboard.press("Enter")
    assert not page.locator('[data-testid="batch-pick-1"]').is_checked()
    assert page.locator('[data-testid="batch-identify"]').is_disabled()


def test_identify_all_progress_and_summary(page, three):
    page.locator('[data-testid="batch-pick-all"]').check()
    assert page.locator('[data-testid="batch-selected"]').inner_text().strip() == "3 selected"
    page.locator('[data-testid="batch-identify"]').click()
    # průběh ve stavovém řádku: „k / 3 · název smyčky“ a tlačítko zrušení
    page.wait_for_function(r"() => /\d \/ 3 · FIC\d/.test(document.querySelector('.status .jobs')?.innerText || '')", timeout=60000,
                           polling=50)
    assert page.locator(".status .job progress").count() == 1 and page.locator(".status .job button").count() == 1
    assert _counts(page, "Identification of loops") == {"ok": 2, "skipped": 1, "error": 0}
    assert "No significant MV or SP step" in page.locator('[data-testid="batch-reason-2"]').inner_text()
    assert page.locator('[data-testid="proj-batch-summary"]').get_attribute("aria-busy") is None
    page.wait_for_function("() => document.querySelector('[data-testid=\"proj-loop-0\"]')?.dataset.stage === 'model'", timeout=30000)
    stages = [page.locator(f'[data-testid="proj-loop-{i}"]').get_attribute("data-stage") for i in range(3)]
    assert stages == ["model", "model", "data"]
    assert "%" in page.locator('[data-testid="proj-loop-model-0"]').inner_text()            # model a jeho FIT [%]
    # filtr „jen problémy“: přeskočená smyčka zůstane
    page.locator('[data-testid="batch-only-problems"]').check()
    assert page.locator('[data-testid="proj-loop-2"]').count() == 1
    page.locator('[data-testid="batch-only-problems"]').uncheck()
    assert page.locator('[data-testid="proj-loop-1"]').count() == 1


def test_tune_stores_proposal_and_keeps_set2(page, three):
    before = {i: (r["set2"], r["set2_defined"]) for i, r in _rows(page).items()}
    page.locator('[data-testid="batch-tune"]').click()
    page.wait_for_selector('[data-testid="batch-tune-dialog"]', state="visible")
    page.select_option('[data-testid="batch-method"]', "SIMC")
    page.locator('[data-testid="batch-tune-run"]').click()
    c = _counts(page, "Tuning of loops")
    assert c == {"ok": 2, "skipped": 1, "error": 0}
    assert "identify it first" in page.locator('[data-testid="batch-reason-2"]').inner_text()
    page.wait_for_function("() => document.querySelector('[data-testid=\"proj-loop-0\"]')?.dataset.stage === 'proposal'", timeout=30000)
    rows = _rows(page)
    assert {i: (r["set2"], r["set2_defined"]) for i, r in rows.items()} == before          # Set 2 beze změny
    assert [rows[i]["stage"] for i in range(3)] == ["proposal", "proposal", "data"]
    assert page.locator('[data-testid="proj-loop-change-0"]').inner_text().strip() == "—"


def _proposal(page, i):
    _call(page, "PUT", "/api/v1/workspaces/{wid}/loops/active", {"index": i})
    st = _call(page, "GET", "/api/v1/workspaces/{wid}/settings")
    return next(v for k, v in st.items() if k.startswith("batch_sug|"))


def test_accept_writes_set2(page, three):
    sug = {i: _proposal(page, i) for i in (0, 1)}
    _call(page, "PUT", "/api/v1/workspaces/{wid}/loops/active", {"index": 0})
    page.locator('[data-testid="batch-accept"]').click()
    assert _counts(page, "Accepting proposals") == {"ok": 2, "skipped": 1, "error": 0}
    page.wait_for_function("() => document.querySelector('[data-testid=\"proj-loop-1\"]')?.dataset.stage === 'set2'", timeout=30000)
    rows = _rows(page)
    for i in (0, 1):
        assert rows[i]["set2_defined"] and rows[i]["stage"] == "set2"
        assert [rows[i]["set2"][k] for k in ("gain", "ti", "td")] == pytest.approx(sug[i][:3])
    assert not rows[2]["set2_defined"]
    assert page.locator('[data-testid="proj-loop-2"]').get_attribute("data-stage") == "data"
    assert page.locator('[data-testid="proj-loop-change-1"]').inner_text().strip() != "—" \
        or not rows[1]["set1_defined"]                     # změna Gain jen při skutečném Setu 1


@pytest.mark.parametrize("fmt", ["csv", "pcs7"])
def test_export_selected_loops(page, three, fmt):
    page.locator('[data-testid="batch-export"]').click()
    page.wait_for_selector('[data-testid="batch-export-dialog"]', state="visible")
    assert "FIC3" in page.locator('[data-testid="batch-export-note"]').inner_text()       # bez modelu se nevyexportuje
    page.select_option('[data-testid="batch-export-fmt"]', fmt)
    page.select_option('[data-testid="batch-export-set"]', "2")
    with page.expect_download() as dl:
        page.locator('[data-testid="batch-export-go"]').click()
    path = dl.value.path()
    assert dl.value.suggested_filename.startswith(f"tuning_set2_{fmt}_loops.")
    text = open(path, encoding="utf-8-sig").read()
    assert "FIC3" not in text
    if fmt == "csv":
        lines = text.splitlines()
        assert lines[0].startswith("loop;parameter")
        assert {x.split(";")[0] for x in lines[1:]} == {"FIC1", "FIC2"}
    else:
        assert text.count("// ===== loop ") == 2 and "// ===== loop FIC1 =====" in text and "// ===== loop FIC2 =====" in text
    page.wait_for_selector('[data-testid="batch-export-dialog"]', state="hidden")


def test_click_name_activates_loop(page, three):
    page.locator('[data-testid="proj-loop-name-1"]').click()
    page.wait_for_function("() => document.querySelector('[data-testid=\"proj-loop-1\"]')?.dataset.active === 'true'", timeout=20000)
    assert _call(page, "GET", "/api/v1/workspaces/{wid}/loops")["active"] == 1
    assert page.locator('[data-testid="batch-pick-1"]').is_checked()                   # klik na název výběr nemění


def test_cancel_keeps_finished_loops(page, three):
    # všechny smyčky znovu: po první hotové smyčce úlohu zrušit
    page.locator('[data-testid="batch-pick-all"]').check()
    page.locator('[data-testid="batch-identify"]').click()
    page.wait_for_function(r"() => /1 \/ 3 · FIC1/.test(document.querySelector('.status .jobs')?.innerText || '')", timeout=60000, polling=50)
    page.wait_for_function(r"() => /2 \/ 3 · FIC2/.test(document.querySelector('.status .jobs')?.innerText || '')", timeout=120000, polling=20)
    page.locator(".status .job button").click()
    page.wait_for_selector('[data-testid="batch-cancelled"]', timeout=30000)
    assert page.locator(".status .job").count() == 0
    c = _counts(page, "Identification of loops")
    assert c["ok"] >= 1 and c["ok"] + c["skipped"] + c["error"] < 3          # nedokončené smyčky se do souhrnu nedostaly
    assert _rows(page)[0]["stage"] in ("model", "set2")                     # hotová smyčka zůstala identifikovaná
