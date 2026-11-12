# ruff: noqa: F811
"""E9-A (APC parity): rozsah vnitřní PV z dat, štítky doporučení (nevhodné / není potřeba), jednosměrné rozvazbení,
Ms bodů gain schedulingu, úseky GS a pásma override."""
import numpy as np
import pytest

pytest.importorskip("fastapi")
from pidtools.api.apc_loops import CascadeFitReq, _cas_fit_args  # noqa: E402
from pidtools.app import signalpack  # noqa: E402
from pidtools.app.apc import cascade as acas  # noqa: E402
from pidtools.app.apc import decouple as adec  # noqa: E402
from pidtools.app.apc import recommend as reco  # noqa: E402
from pidtools.app.apc.common import clean  # noqa: E402
from test_api_apc_loops import _done, two, ws  # noqa: E402,F401  (fixtury)


def _rec(model, c_d=(), name="A", mv="MV1", sp=None):
    return dict(name=name, model=model, c_mv=mv, c_sp=sp, c_d=list(c_d), pv_rng=(0, 100), mv_rng=(0, 100))


# ---- rozsah vnitřní PV z dat (oprava chyby: pole Od / Do ukazovala 0 a 100, identifikace brala data)
def test_inner_range_from_data():
    x = np.array([np.nan, 12.3, 48.9, 77.2])
    assert acas.inner_range(x) == (12.0, 78.0)
    assert acas.inner_range(x, lo=0.0) == (0.0, 78.0) and acas.inner_range(x, hi=90) == (12.0, 90.0)
    with pytest.raises(ValueError):
        acas.inner_range(np.full(3, np.nan))


def test_cascade_irange_endpoint_matches_fit(ws):
    c, wid, s = ws
    u = f"/workspaces/{wid}"
    sig = next(str(x) for x in s.sig.sigs if str(x) != str(s.c_pv))
    r = c.get(f"{u}/apc/cascade/irange", params={"ipv": sig})
    assert r.status_code == 200
    from pidtools.app.dataset import on_grid
    lo, hi = acas.inner_range(on_grid(s.sig, s.grid, sig))
    assert (r.json()["lo"], r.json()["hi"]) == (lo, hi) and (lo, hi) != (0.0, 100.0)
    assert c.get(f"{u}/apc/cascade/irange", params={"ipv": "nope"}).status_code == 422
    ts, ipv, _, _ = _cas_fit_args(s, CascadeFitReq(ipv=sig, imv=sig))
    ref = (on_grid(s.sig, s.grid, sig)[s.sel_mask] - lo) / max(hi - lo, 1e-9) * 100
    assert np.allclose(ipv, ref)


# ---- štítky doporučení
def test_assess_unsuitable_and_skip():
    smith_small = _rec(("P1D", [1.0, 50.0, 2.0], []))                    # θ/(θ+T) = 0,04
    items = reco.assess(smith_small, [], 1.2, True)
    got = {(k, st) for k, st, _, _ in items}
    assert ("smith", "skip") in got and ("gainsched", "skip") in got and ("ff", "unsuitable") in got
    integ = reco.assess(_rec(("I1D", [0.05, 10.0, 1.0], [])), [], None, True)
    got = {(k, st) for k, st, _, _ in integ}
    assert ("smith", "unsuitable") in got and ("gainsched", "unsuitable") in got
    dead = reco.assess(_rec(("P1D", [1.0, 5.0, 20.0], [[0.5, 5.0, 2.0]]), c_d=["X"]), [], 2.0, False)
    assert [(k, st) for k, st, _, _ in dead][:2] == [("smith", "rec"), ("gainsched", "rec")]       # doporučené první
    assert not any(st != "rec" and k in ("smith", "gainsched", "ff") for k, st, _, _ in dead)
    assert all(isinstance(t, str) and t for _, _, t, _ in items)


def test_assess_keeps_recommend_and_decouple_weak():
    a = _rec(("P1D", [1.0, 30.0, 3.0], [[0.01, 30.0, 3.0]]), c_d=["MV2"], name="A", mv="MV1")
    b = _rec(("P1D", [0.8, 25.0, 2.0], [[0.01, 30.0, 3.0]]), c_d=["MV1"], name="B", mv="MV2")
    items = reco.assess(a, [(1, b)], 1.1, True)
    assert [x for x in items if x[1] == "rec"] == [(k, "rec", t, o) for k, t, o in reco.recommend(a, [(1, b)], 1.1, True)]
    assert ("decouple", "skip", 1) in [(k, st, o) for k, st, _, o in items]


def test_recommend_endpoint_status(ws):
    c, wid, _ = ws
    items = c.get(f"/workspaces/{wid}/apc/recommend").json()
    assert items and {x["status"] for x in items} <= {"rec", "unsuitable", "skip"}
    order = [x["status"] for x in items]
    assert order == sorted(order, key=["rec", "unsuitable", "skip"].index)
    assert ("ff", "rec") in [(x["kind"], x["status"]) for x in items]


# ---- jednosměrné rozvazbení
def test_one_way_decoupling(two):
    c, wid, proj = two
    (bi, b), = proj.others()
    a = dict(proj.state.report_record(), name=proj.names()[proj.active])
    dz = adec.design(a, b)
    url = f"/workspaces/{wid}/apc/decouple"
    assert [p["way"] for p in c.get(url).json()["params"]] == ["ab", "ba"]
    assert [p[1] for p in adec.params(dz, a, b, "ab")] == [a["name"]] and [p[1] for p in adec.params(dz, a, b, "ba")] == [b["name"]]
    k = {}
    for way in ("both", "ab", "ba"):
        sim = c.post(f"{url}/simulate", json={"way": way, "dtype": "static"}).json()
        assert sim["way"] == way
        runs = adec.simulate(dz, clean(a["ctrl"]), clean(b["ctrl"]), 5.0, 5.0, way=way)
        ref = adec.iae_table(runs, a, b)
        assert [x["iae_a"] for x in sim["kpis"]] == pytest.approx([x[1] for x in ref])
        k[way] = sim["kpis"][1]
    assert k["ab"]["iae_a"] == pytest.approx(k["both"]["iae_a"], rel=0.3) or k["ab"] != k["ba"]
    assert k["ab"] != k["both"] and k["ba"] != k["both"]
    assert c.post(f"{url}/simulate", json={"way": "x"}).status_code == 422


# ---- GS: Ms bodů a úseky; override: pásma
def test_gainsched_ms_and_segments(ws):
    c, wid, _ = ws
    u = f"/workspaces/{wid}/apc/gainsched"
    _done(c, c.post(f"{u}/fit").json())
    info = c.get(u).json()
    assert info["fitted"]
    for p in info["points"]:
        assert p["ms_sched"] is None or 1.0 <= p["ms_sched"] < 4
        assert p["ms_fixed"] is None or p["ms_fixed"] >= 1.0
    assert any(p["ms_sched"] is not None for p in info["points"])
    sig = signalpack.unframe(c.get(f"{u}/segments/curves").content)[1]
    assert {"pv", "mv"} <= set(sig) and len(sig["pv"][0]) == len(sig["mv"][0]) > 10


def test_override_band_signal(two):
    c, wid, _ = two
    sig = signalpack.unframe(c.post(f"/workspaces/{wid}/apc/override/simulate/curves", json={}).content)[1]
    act = sig["act"][1]
    assert set(np.unique(act)) <= {0.0, 1.0} and len(act) == len(sig["pv_b"][1])
