"""
API – techniky APC (M11b), další struktury: split range, VPC, poměrová regulace a RGA shodné s voláním app vrstvy
(jako desktop) na demu.
"""
import time

import numpy as np
import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from pidtools.api import create_app  # noqa: E402
from pidtools.app import guides, signalpack  # noqa: E402
from pidtools.app.apc import ratio as aratio  # noqa: E402
from pidtools.app.apc import rgan  # noqa: E402
from pidtools.app.apc import splitrange as asr  # noqa: E402
from pidtools.app.apc import vpc as avpc  # noqa: E402


def _wait(client, job, t=600):
    t0 = time.time()
    while time.time() - t0 < t:
        st = client.get(f"/jobs/{job['id']}").json()
        if st["state"] not in ("queued", "running"):
            assert st["state"] == "done", st
            return st
        time.sleep(0.2)
    raise AssertionError("job timeout")


def _identify(c, wid):
    c.patch(f"/workspaces/{wid}/settings", json={"chosen": ["P1D", "I1D"]})
    _wait(c, c.post(f"/workspaces/{wid}/identify").json())


@pytest.fixture(scope="module")
def ws():
    with TestClient(create_app()) as c:
        wid = c.post("/workspaces").json()["id"]
        c.post(f"/workspaces/{wid}/data/demo")
        _identify(c, wid)
        yield c, wid, c.app.state.workspace(wid), c.app.state.store.get(wid)


def test_requires_model():
    with TestClient(create_app()) as c:
        wid = c.post("/workspaces").json()["id"]
        for u in ("split", "vpc", "ratio", "rga"):
            assert c.get(f"/workspaces/{wid}/apc/{u}").status_code == 409
        c.post(f"/workspaces/{wid}/data/demo")
        assert c.get(f"/workspaces/{wid}/apc/split").status_code == 409
        assert c.post(f"/workspaces/{wid}/apc/vpc/simulate", json={}).status_code == 409


# ---- split range
@pytest.mark.parametrize("mode", ["opposite", "sequence"])
def test_split_matches_app(ws, mode):
    c, wid, s, _ = ws
    url = f"/workspaces/{wid}/apc/split"
    info = c.get(url, params={"mode": mode, "b0": 40, "gap": 2}).json()
    gb = asr.valve_b(s.model, 40.0)
    ga = asr.default_a(gb, mode)
    assert info["model"] == s.model[0]
    assert info["defaults"] == dict(mode=mode, b0=40.0, gap=2.0, valve_a=pytest.approx(ga[1]))
    d = info["design"]
    bstar = asr.balanced(ga[1][0], gb[1][0])
    assert d["bstar"] == pytest.approx(bstar) and d["valve_b"]["values"] == pytest.approx(gb[1])
    assert len(d["valve_a"]["params"]) == len(ga[1])
    ctrl = s.set_ctrl(2)
    for key, b in (("now", 40.0), ("new", bstar)):
        h = asr.halves(ga, gb, ctrl, b, mode)
        for half, ref in zip(("lower", "upper"), h):
            assert d[key][half]["k"] == pytest.approx(ref[0])
            assert d[key][half]["ms"] == pytest.approx(ref[1]) and d[key][half]["stable"] == ref[2]
    up1 = asr.eff_gains(ga[1][0], gb[1][0], bstar, mode)[1]
    assert d["corr"] == pytest.approx(s.model[1][0] / up1)
    assert "{" not in d["impl_text"] and d["checks"] and d["checks"][0]["state"] is True
    # POST /design se stejným tělem dává totéž (vstup z GET)
    assert c.post(f"{url}/design", json=info["defaults"]).json() == d


def test_split_simulate_and_curves(ws):
    c, wid, s, _ = ws
    url = f"/workspaces/{wid}/apc/split"
    body = {"mode": "opposite", "b0": 45, "gap": 1.5, "valve_a": None}
    gb = asr.valve_b(s.model, 45.0)
    ga = asr.default_a(gb, "opposite")
    bstar = asr.balanced(ga[1][0], gb[1][0])
    runs, amp = asr.simulate(ga, gb, s.set_ctrl(2), 45.0, bstar, "opposite", 1.5, float(s.get("samp")))
    sim = c.post(f"{url}/simulate", json=body).json()
    assert sim["amp"] == pytest.approx(amp) and sim["bstar"] == pytest.approx(bstar)
    assert sim["T_end"] == pytest.approx(runs["new"][0][-1])
    for k in ("now", "new"):
        assert sim["kpis"][k] == pytest.approx(asr.kpis(runs[k], s.PR))
    raw = c.post(f"{url}/simulate/curves", json=body)
    assert raw.status_code == 200
    names, t, vals = _unpack(raw.content)
    assert names == ["sp", "pv_now", "pv_new", "u_now", "u_new", "va", "vb"]
    assert t[-1] == pytest.approx(runs["new"][0][-1])
    assert vals["pv_new"] == pytest.approx(s.EP(np.asarray(runs["new"][1]["PV"])), abs=1e-3)
    assert vals["va"] == pytest.approx(np.asarray(runs["new"][1]["VA"]), abs=1e-3)


def _unpack(raw):
    """(názvy, čas, {název: hodnoty}) z app.signalpack.frame."""
    _, sig = signalpack.unframe(raw)
    names = list(sig)
    return names, sig[names[0]][0], {k: v[1] for k, v in sig.items()}


def test_split_custom_valve_and_errors(ws):
    c, wid, s, _ = ws
    url = f"/workspaces/{wid}/apc/split"
    p = list(asr.default_a(asr.valve_b(s.model, 50.0), "opposite")[1])
    p[0] *= 2
    d = c.post(f"{url}/design", json={"valve_a": p}).json()
    assert d["valve_a"]["values"] == pytest.approx(p)
    assert d["bstar"] == pytest.approx(asr.balanced(p[0], asr.valve_b(s.model, 50.0)[1][0]))
    neg = c.post(f"{url}/design", json={"valve_a": [p[0], -1.0, -2.0]}).json()      # p[1:] ≥ 0 jako v desktopu
    assert all(v >= 0 for v in neg["valve_a"]["values"][1:])
    assert c.post(f"{url}/design", json={"valve_a": [1.0]}).status_code == 422
    assert c.post(f"{url}/design", json={"b0": 100}).status_code == 422
    assert c.post(f"{url}/simulate", json={"mode": "x"}).status_code == 422
    assert c.get(url, params={"b0": 0}).status_code == 422
    assert c.get("/workspaces/nope/apc/split").status_code == 404


# ---- VPC
def test_vpc_matches_app(ws):
    c, wid, s, _ = ws
    url = f"/workspaces/{wid}/apc/vpc"
    info = c.get(url).json()
    g1 = (s.model[0], list(s.model[1]))
    g2 = avpc.default_mv2(g1)
    assert info["defaults"] == dict(mv2=pytest.approx(g2[1]), sp=50.0, factor=5.0, d=35.0)
    cv, p, tc = avpc.tune_vpc(g1, g2, s.set_ctrl(2), s.base_ctrl(), 5.0)
    d = info["design"]
    assert d["controller"] == pytest.approx(dict(Kc=cv["Gain"], Ti=cv["TI"], Td=cv["TD"]))
    assert d["surrogate"]["values"] == pytest.approx(p) and d["tc"] == pytest.approx(tc)
    assert d["loop_time"] == pytest.approx(avpc.loop_time(g1, s.set_ctrl(2)))
    assert d["mv2"]["code"] == s.model[0] and "{" not in d["impl_text"]
    body = {"mv2": [g2[1][0] * 1.5, *g2[1][1:]], "sp": 60, "factor": 8, "d": -20}
    g2b = (g1[0], body["mv2"])
    cv, p, tc = avpc.tune_vpc(g1, g2b, s.set_ctrl(2), s.base_ctrl(), 8.0)
    d2 = c.post(f"{url}/design", json=body).json()
    assert d2["controller"]["Kc"] == pytest.approx(cv["Gain"]) and d2["tc"] == pytest.approx(tc)
    assert d2["controller"]["Kc"] != pytest.approx(d["controller"]["Kc"])


def test_vpc_simulate_and_curves(ws):
    c, wid, s, _ = ws
    url = f"/workspaces/{wid}/apc/vpc"
    body = {"sp": 55, "factor": 6, "d": 25}
    g1 = (s.model[0], list(s.model[1]))
    g2 = avpc.default_mv2(g1)
    cv, _, _ = avpc.tune_vpc(g1, g2, s.set_ctrl(2), s.base_ctrl(), 6.0)
    runs = avpc.simulate(g1, g2, s.set_ctrl(2), cv, 25.0, 55.0, float(s.get("samp")))
    sim = c.post(f"{url}/simulate", json=body).json()
    assert sim["T_end"] == pytest.approx(runs["on"][0][-1])
    assert sim["controller"]["Kc"] == pytest.approx(cv["Gain"])
    for k in ("off", "on"):
        assert sim["kpis"][k] == pytest.approx(avpc.kpis(runs[k], s.PR))
    names, t, vals = _unpack(c.post(f"{url}/simulate/curves", json=body).content)
    assert names == ["sp", "pv_off", "pv_on", "mv1_off", "mv1_on", "mv2_on"]
    assert vals["mv2_on"] == pytest.approx(np.asarray(runs["on"][1]["MV2"]), abs=1e-3)
    assert vals["pv_on"] == pytest.approx(s.EP(np.asarray(runs["on"][1]["PV"])), abs=1e-3)
    assert c.post(f"{url}/simulate", json={"sp": 99}).status_code == 422
    assert c.post(f"{url}/simulate", json={"factor": 0.5}).status_code == 422
    assert c.post(f"{url}/design", json={"mv2": [1, 2]}).status_code == 422


# ---- poměr
def test_ratio_manual_matches_app(ws):
    c, wid, s, _ = ws
    url = f"/workspaces/{wid}/apc/ratio"
    info = c.get(url).json()
    gf = (s.model[0], list(s.model[1]))
    ga = aratio.default_air(gf)
    assert info["defaults"] == dict(air_loop=None, air=pytest.approx(ga[1]), R=1.2, step=15.0)
    assert info["design"]["air"]["values"] == pytest.approx(ga[1]) and info["design"]["sources"] == []
    assert "{" not in info["design"]["impl_text"]
    assert [x["state"] for x in info["design"]["checks"]] == [x[0] for x in guides.apc_ratio(
        dict(name=s.c_pv, model=s.model, c_mv=s.c_mv), 0)]
    body = {"R": 2.0, "step": -10.0}
    runs = aratio.simulate(gf, ga, s.set_ctrl(2), s.set_ctrl(2), 2.0, -10.0, float(s.get("samp")))
    sim = c.post(f"{url}/simulate", json=body).json()
    assert sim["T_end"] == pytest.approx(runs["cross"][0][-1])
    for k in ("plain", "cross"):
        ref = aratio.kpis(runs[k], s.PR)
        assert sim["kpis"][k] == pytest.approx(ref) and sim["lam_min"][k] == pytest.approx(ref["lam_min"])
    names, t, vals = _unpack(c.post(f"{url}/simulate/curves", json=body).content)
    assert names == ["demand", "fuel", "air_r", "air_r_plain", "lam", "lam_plain"]
    assert vals["lam"] == pytest.approx(np.asarray(runs["cross"][1]["LAM"]), abs=1e-3)
    assert vals["air_r"] == pytest.approx(np.asarray(runs["cross"][1]["PVA"]) / 2.0, abs=1e-3)
    custom = c.post(f"{url}/design", json={"air": [gf[1][0], *[v * 3 for v in gf[1][1:]]]}).json()
    assert custom["air"]["values"][1] == pytest.approx(gf[1][1] * 3)


def test_ratio_errors(ws):
    c, wid, s, _ = ws
    url = f"/workspaces/{wid}/apc/ratio"
    assert c.post(f"{url}/simulate", json={"R": 0}).status_code == 422
    assert c.post(f"{url}/simulate", json={"air": [1.0]}).status_code == 422
    assert c.post(f"{url}/simulate", json={"air_loop": 7}).status_code == 404
    assert c.post(f"{url}/simulate", json={"air_loop": 0}).status_code == 404       # aktivní smyčka není zdroj
    assert c.post(f"{url}/simulate", json={"air_loop": 1, "air": list(s.model[1])}).status_code == 422


# ---- víc smyček: poměr se zdrojem vzduchu, RGA
@pytest.fixture(scope="module")
def two():
    with TestClient(create_app()) as c:
        wid = c.post("/workspaces").json()["id"]
        c.post(f"/workspaces/{wid}/data/demo")
        _identify(c, wid)
        proj = c.app.state.store.get(wid)
        one = c.get(f"/workspaces/{wid}/apc/rga").json()
        c.post(f"/workspaces/{wid}/loops", json={"name": "L2"})
        proj.active = 1
        _identify(c, wid)
        proj.active = 0
        yield c, wid, proj, one


def test_rga_single_loop(two):
    _, _, _, one = two
    assert one["ready"] is False and one["names"] == [] and one["pairing"] is None
    assert [x["state"] for x in one["checks"]][1:] == [False, False]


def test_rga_matches_app(two):
    c, wid, proj, _ = two
    info = c.get(f"/workspaces/{wid}/apc/rga").json()
    recs = [dict(proj.state.report_record(), name=proj.names()[0])] + [rec for _, rec in proj.others()]
    assert len(recs) == 2
    ref = rgan.analyse(recs)
    assert info["ready"] and info["names"] == ref["names"] and info["mvs"] == ref["mvs"]
    assert np.array(info["K"]) == pytest.approx(ref["K"]) and np.array(info["known"]).tolist() == ref["known"].tolist()
    assert np.array(info["L"], float) == pytest.approx(ref["L"], nan_ok=True)
    assert info["pairing"] == (None if ref["pairing"] is None else list(ref["pairing"]))
    assert [a["key"] for a in info["advice"]] == ref["advice"]
    n_cross = int(ref["known"].sum() - 2)
    assert [(x["state"], x["text"]) for x in info["checks"]] == [(a, b) for a, b, _ in guides.apc_rga(
        dict(name=proj.names()[0], model=proj.state.model, c_mv=proj.state.c_mv), 2, n_cross)]


def test_ratio_air_from_loop(two):
    c, wid, proj, _ = two
    url = f"/workspaces/{wid}/apc/ratio"
    s, other = proj.loops[0], proj.loops[1]
    info = c.get(url, params={"air_loop": 1}).json()
    assert info["design"]["sources"] == [{"index": 1, "name": "L2"}]
    assert info["design"]["air"]["values"] == pytest.approx(other.model[1])
    assert info["defaults"]["air"] is None and info["defaults"]["air_loop"] == 1
    gf = (s.model[0], list(s.model[1]))
    runs = aratio.simulate(gf, (other.model[0], list(other.model[1])), s.set_ctrl(2), other.set_ctrl(2), 1.2, 15.0,
                           float(s.get("samp")))
    sim = c.post(f"{url}/simulate", json={"air_loop": 1}).json()
    for k in ("plain", "cross"):
        assert sim["kpis"][k] == pytest.approx(aratio.kpis(runs[k], s.PR))
    assert c.post(f"{url}/simulate", json={"air_loop": 1, "air": list(other.model[1])}).status_code == 422
    assert c.post(f"{url}/simulate", json={"air_loop": 5}).status_code == 404
