"""
E9-A v prohlížeči: štítky doporučení (doporučeno / nevhodné / není potřeba) = API, rozsah vnitřní PV z dat v kartě
kaskády, úseky gain schedulingu a Ms bodů, volba jednosměrného rozvazbení, popis metody („?“). Potřebuje sestavené UI.
"""
import pytest

pytest.importorskip("playwright.sync_api")
import test_frontend as _tf  # noqa: E402
import test_frontend_help as _h  # noqa: E402

server, page, prepared = _h.server, _tf.page, _h.prepared


def _tech(page, tech):
    page.locator('[data-tab="apc"]').click()
    page.locator(f'[data-testid="apc-tech-{tech}"]').click()


def test_reco_status_pills_and_method_help(prepared, server):
    page = prepared
    page.locator('[data-tab="apc"]').click()
    page.wait_for_selector('[data-testid="apc-reco"] li', timeout=30000)
    reco = _tf._api(server, "/workspaces/{wid}/apc/recommend", page)
    assert {r["status"] for r in reco} - {"rec"}, "demo should yield at least one unsuitable / not needed label"
    for st, cls in (("rec", "ok"), ("unsuitable", "bad"), ("skip", "info")):
        want = sum(1 for r in reco if r["status"] == st)
        assert page.locator(f'[data-testid="apc-reco"] li[data-status="{st}"] .apc-tag.{cls}').count() == want
    assert page.locator('[data-testid="apc-intro"] .qm').count() == 1


def test_cascade_inner_range_from_data(prepared, server):
    page = prepared
    _tech(page, "cascade")
    page.select_option('[data-testid="set-cas_src"]', "data")
    page.wait_for_selector('[data-testid="cas-ilo"]', timeout=30000)
    sig = page.locator('[data-testid="cas-ipv"]').input_value()
    rng = _tf._api(server, f"/workspaces/{{wid}}/apc/cascade/irange?ipv={sig}", page)
    page.wait_for_function("([lo, hi]) => parseFloat(document.querySelector('[data-testid=\"cas-ilo\"]').value) === lo"
                           " && parseFloat(document.querySelector('[data-testid=\"cas-ihi\"]').value) === hi",
                           arg=[rng["lo"], rng["hi"]], timeout=30000)


def test_gainsched_segments_and_ms(prepared, server):
    page = prepared
    _tech(page, "gainsched")
    page.wait_for_selector('[data-testid="gs-segments"]', timeout=30000)
    gs = _tf._api(server, "/workspaces/{wid}/apc/gainsched", page)
    page.wait_for_function("() => document.querySelectorAll('[data-testid=\"gs-seg-pv\"] rect').length > 0", timeout=30000)
    assert page.locator('[data-testid="gs-seg-pv"] g[data-testid*="-band-"]').count() == len(gs["inputs"]["ranges"])
    page.locator('[data-testid="gs-fit"]').click()
    page.wait_for_selector('[data-testid="gs-ms-sched-0"]', timeout=120000)


def test_decouple_way_select(prepared, server):
    page = prepared
    _tech(page, "decouple")
    page.wait_for_selector('[data-testid="dec-way"]', timeout=30000)
    assert page.locator('[data-testid="dec-way"] option').count() == 3
