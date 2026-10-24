"""
API – techniky APC (M11b): kaskáda, gain scheduling (PV a ER), rozvazbení a override shodné s voláním app vrstvy
(jako desktop). Dvousmyčkové techniky běží na projektu se dvěma provázanými smyčkami (syntetická data).
"""
import io
import os
import sys
import time

import numpy as np
import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from pidtools import core  # noqa: E402
from pidtools.api import create_app  # noqa: E402
from pidtools.app import guides, signalpack  # noqa: E402
from pidtools.app.apc import cascade as acas  # noqa: E402
from pidtools.app.apc import decouple as adec  # noqa: E402
from pidtools.app.apc import gainsched as ags  # noqa: E402
from pidtools.app.apc import override as aov  # noqa: E402
from pidtools.app.apc.common import clean, tchar  # noqa: E402
from pidtools.core.apc import rga_advice  # noqa: E402
from pidtools.i18n import T  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))


def _wait(client, job, t=600):
    t0 = time.time()
    while time.time() - t0 < t:
        st = client.get(f"/jobs/{job['id']}").json()
        if st["state"] not in ("queued", "running"):
            return st
        time.sleep(0.2)
    raise AssertionError("job timeout")


def _done(client, job):
    st = _wait(client, job)
    assert st["state"] == "done", st
    return st


def _sig(c, url, body=None):
    return signalpack.unframe(c.post(url, json=body or {}).content)[1]


def _pid(d):
    return {k: d[k] for k in ("Kc", "Ti", "Td")}


@pytest.fixture(scope="module")
def ws():
    """Demo s modely P1D a I1D (jedna smyčka)."""
    with TestClient(create_app()) as c:
        wid = c.post("/workspaces").json()["id"]
        c.post(f"/workspaces/{wid}/data/demo")
        c.patch(f"/workspaces/{wid}/settings", json={"chosen": ["P1D", "I1D"]})
        _done(c, c.post(f"/workspaces/{wid}/identify").json())
        c.patch(f"/workspaces/{wid}/settings", json={"mcode": "P1D"})
        yield c, wid, c.app.state.workspace(wid)


def _two_frame():
    """Dvě provázané smyčky: MV každé působí i na PV té druhé (jako tests/test_desktop.py)."""
    import pandas as pd
    t = np.arange(0, 3000.0)
    rng = np.random.default_rng(1)
    mv1 = 50 + 8.0 * ((t >= 200) & (t < 800)) - 6.0 * ((t >= 1600) & (t < 2200))
    mv2 = 50 + 7.0 * ((t >= 500) & (t < 1100)) - 5.0 * ((t >= 1900) & (t < 2500))
    pv1 = 50 + core.simulate("P1D", [1.0, 30.0, 3.0], t, mv1 - 50, 1.0) + \
        core.simulate("P1D", [0.5, 40.0, 4.0], t, mv2 - 50, 1.0) + rng.normal(0, 0.05, t.size)
    pv2 = 50 + core.simulate("P1D", [0.8, 25.0, 2.0], t, mv2 - 50, 1.0) + \
        core.simulate("P1D", [0.4, 35.0, 3.0], t, mv1 - 50, 1.0) + rng.normal(0, 0.05, t.size)
    return pd.DataFrame({"Time": t, "FIC1.PV": pv1, "FIC1.MV": mv1, "FIC2.PV": pv2, "FIC2.MV": mv2})


@pytest.fixture(scope="module")
def two():
    """Projekt se dvěma smyčkami s modely; aktivní je smyčka 0 (FIC1), druhá (index 1) je FIC2."""
    with TestClient(create_app()) as c:
        wid = c.post("/workspaces").json()["id"]
        u = f"/workspaces/{wid}"
        buf = io.StringIO()
        _two_frame().to_csv(buf, index=False)
        assert c.post(f"{u}/data/file", params={"name": "two.csv"}, content=buf.getvalue().encode(),
                      headers={"content-type": "application/octet-stream"}).status_code == 200
        c.put(f"{u}/columns", json={"pv": "FIC1.PV", "mv": "FIC1.MV", "dists": ["FIC2.MV"]})
        c.patch(f"{u}/settings", json={"chosen": ["P1D"]})
        _done(c, c.post(f"{u}/identify").json())
        c.post(f"{u}/loops", json={"name": "FIC2", "pv": "FIC2.PV", "mv": "FIC2.MV"})
        c.put(f"{u}/columns", json={"pv": "FIC2.PV", "mv": "FIC2.MV", "dists": ["FIC1.MV"]})
        c.patch(f"{u}/settings", json={"chosen": ["P1D"]})
        _done(c, c.post(f"{u}/identify").json())
        c.put(f"{u}/loops/active", json={"index": 0})
        yield c, wid, c.app.state.store.get(wid)


def test_requires_model():
    with TestClient(create_app()) as c:
        wid = c.post("/workspaces").json()["id"]
        for k in ("cascade", "gainsched", "gainsched_er", "decouple", "override"):
            assert c.get(f"/workspaces/{wid}/apc/{k}").status_code == 409


def test_two_loop_techniques_need_second_loop(ws):
    c, wid, _ = ws
    for k in ("decouple", "override"):
        assert c.get(f"/workspaces/{wid}/apc/{k}").status_code == 409
        assert c.post(f"/workspaces/{wid}/apc/{k}/simulate", json={}).status_code == 409
        assert c.post(f"/workspaces/{wid}/apc/{k}/simulate/curves", json={}).status_code == 409
    info = c.get(f"/workspaces/{wid}/apc/cascade").json()
    assert info["inputs"]["source"] == "manual" and info["inputs"]["loops"] == []


# ---- kaskáda
def test_cascade_manual_like_desktop(ws):
    c, wid, s = ws
    url = f"/workspaces/{wid}/apc/cascade"
    samp, dg = float(s.get("samp")), float(s.get("diffgain"))
    info = c.get(url).json()
    inner = acas.manual_inner(1.0, 5.0, 0.0, 1.0)
    ci, pi = inner
    si = acas.tune_loop(ci, pi, "SIMC", "PI", samp, dg, core.default_tc(ci, pi, samp))
    ictrl = acas.inner_ctrl(si, dg, samp)
    t63, tc_eff = acas.inner_response(ci, pi, ictrl, samp)
    co, po = acas.outer_model(s.model, tc_eff, pi[-1])
    so = acas.tune_loop(co, po, "SIMC", "PI", samp, dg, core.default_tc(co, po, samp, "SIMC", "PI", dg))
    assert _pid(info["inner"]) == pytest.approx(_pid({"Kc": si["Kc"], "Ti": si["Ti"], "Td": si["Td"]}))
    assert _pid(info["outer"]) == pytest.approx({"Kc": so["Kc"], "Ti": so["Ti"], "Td": so["Td"]})
    assert info["t63"] == pytest.approx(t63) and info["tc_eff"] == pytest.approx(tc_eff)
    assert info["outer_model"]["code"] == co and [x["value"] for x in info["outer_model"]["params"]] == \
        pytest.approx(po)
    sep = acas.separation(core.default_tc(co, po, samp, "SIMC", "PI", dg), so, t63)
    assert info["separation"] == pytest.approx(sep) and info["sep_warn"] == (sep < 4)
    inp = info["inputs"]
    assert inp["tci"] is None and inp["tci_default"] == pytest.approx(core.default_tc(ci, pi, samp))
    assert not inp["tci_edited"] and not inp["tco_edited"] and info["impl_text"]
    assert {r["param"] for r in info["rows"]} >= {"inner.Gain", "outer.TI"}
    a = dict(s.report_record(), name=s.get("loop_tag") or str(s.c_pv))
    assert [x["text"] for x in info["checks"]] == [x[1] for x in guides.apc_cascade(a, [])]
    # simulace
    sim = c.post(f"{url}/simulate").json()
    ts, oc, ok = acas.simulate(inner, ictrl, (s.model[0], s.model[1]), dict(s.base_ctrl(), Gain=so["Kc"], TI=so["Ti"],
                               TD=so["Td"], MV_Lo=0.0, MV_Hi=100.0), samp, samp, po, co,
                               core.default_tc(co, po, samp, "SIMC", "PI", dg))
    assert sim["ok"] == ok and sim["T_end"] == pytest.approx(float(ts[-1]))
    assert sim["iae_outer"] == pytest.approx(float(core.iae(ts, oc[:, 0], oc[:, 1]) * s.PR / 100))
    sig = _sig(c, f"{url}/simulate/curves")
    assert {"sp_o", "pv_o", "sp_i", "pv_i", "valve"} <= set(sig)
    assert np.allclose(sig["pv_o"][1], s.EP(oc[:, 1]), rtol=1e-4, atol=1e-3)


def test_cascade_settings_roundtrip_and_reset(ws):
    c, wid, s = ws
    url = f"/workspaces/{wid}/apc/cascade"
    base = c.get(url).json()
    c.patch(f"/workspaces/{wid}/settings", json={"cas_k": 2.0, "cas_t1": 8.0, "cas_t2": 3.0, "cas_th": 0.5,
                                                 "cas_tci": 4.0, "cas_tco": 50.0, "cas_oct": "PID", "cas_samp": 0.5})
    info = c.get(url).json()
    inp = info["inputs"]
    assert inp["manual"] == [2.0, 8.0, 3.0, 0.5] and inp["tci"] == 4.0 and inp["tci_edited"] and inp["tco_edited"]
    assert inp["outer_ctype"] == "PID" and inp["samp_i"] == 0.5
    assert info["inner_model"]["code"] == "P2D"                      # T2 > 0
    ci, pi = acas.manual_inner(2.0, 8.0, 3.0, 0.5)
    si = acas.tune_loop(ci, pi, "SIMC", "PI", 0.5, float(s.get("diffgain")), 4.0)
    assert info["inner"]["Kc"] == pytest.approx(si["Kc"]) and info["outer"]["Td"] >= 0
    for part in ("manual", "inner", "outer"):
        info = c.post(f"{url}/reset", json={"part": part}).json()
    assert info["inputs"]["manual"] == [1.0, 5.0, 0.0, 1.0] and not info["inputs"]["tci_edited"]
    assert info["inputs"]["samp_i"] == pytest.approx(float(s.get("samp")))
    c.patch(f"/workspaces/{wid}/settings", json={"cas_oct": "PI"})
    assert c.get(url).json()["outer"] == base["outer"]
    assert c.post(f"{url}/reset", json={"part": "x"}).status_code == 422
    # OPT: MIGO jako v desktopu
    c.patch(f"/workspaces/{wid}/settings", json={"cas_om": "OPT"})
    opt = c.get(url).json()
    assert opt["inputs"]["outer_method"] == "OPT"
    co, po = base["outer_model"]["code"], [x["value"] for x in base["outer_model"]["params"]]
    ref = acas.tune_loop(co, po, "OPT", "PI", float(s.get("samp")), float(s.get("diffgain")), None)
    assert _pid(opt["outer"]) == pytest.approx({"Kc": ref["Kc"], "Ti": ref["Ti"], "Td": ref["Td"]}, rel=1e-3)
    c.patch(f"/workspaces/{wid}/settings", json={"cas_om": "SIMC"})


def test_cascade_inner_from_loop_and_data(two):
    c, wid, proj = two
    url = f"/workspaces/{wid}/apc/cascade"
    ws0, ws1 = proj.loops
    info = c.get(url).json()
    assert info["inputs"]["source"] == "loop" and info["inputs"]["loop"] == 1
    assert [x["index"] for x in info["inputs"]["loops"]] == [1]
    m = ws1.model
    assert info["inner_model"]["code"] == m[0]
    assert [x["value"] for x in info["inner_model"]["params"]] == pytest.approx(list(m[1]))
    samp, dg = float(ws0.get("samp")), float(ws0.get("diffgain"))
    si = acas.tune_loop(m[0], list(m[1]), "SIMC", "PI", samp, dg, core.default_tc(m[0], list(m[1]), samp))
    assert info["inner"]["Kc"] == pytest.approx(si["Kc"])
    assert c.get(url, params={"loop": 7}).status_code == 404
    assert c.post(f"{url}/simulate", params={"loop": 1}).json()["ok"]
    # model vnitřní smyčky z dat (úloha)
    c.patch(f"/workspaces/{wid}/settings", json={"cas_src": "data"})
    assert c.get(url).json()["inner_model"] is None and c.post(f"{url}/simulate").status_code == 409
    job = c.post(f"{url}/fit", json={"ipv": "FIC2.PV", "imv": "FIC2.MV"}).json()
    _done(c, job)
    fit = c.get(f"/jobs/{job['id']}/result").json()
    after = c.get(url).json()
    assert after["inner_fit"]["model"]["code"] == fit["code"] and after["inner_model"]["code"] == fit["code"]
    assert after["inner_fit"]["fit"] == pytest.approx(fit["fit"]) and fit["fit"] > 50
    assert c.post(f"{url}/simulate").status_code == 200
    assert c.post(f"{url}/fit", json={"ipv": "NOPE", "imv": "FIC2.MV"}).status_code == 422
    c.patch(f"/workspaces/{wid}/settings", json={"cas_src": "loop"})


# ---- gain scheduling podle PV
def test_gainsched_fit_job_and_values(ws):
    c, wid, s = ws
    url = f"/workspaces/{wid}/apc/gainsched"
    pre = c.get(url).json()
    assert not pre["integ"] and not pre["fitted"] and pre["points"] == [] and pre["inputs"]["ranges_auto"]
    g = s.grid
    rg = ags.auto_ranges(g.t, s.pv, s.mv, s.sp, g.Ts, g.has_sp, 4 * tchar(s.model), 3)
    assert pre["inputs"]["ranges"] == [list(r) for r in rg] and pre["inputs"]["n"] == 3
    assert c.post(f"{url}/simulate").status_code == 409                       # body ještě nejsou
    job = c.post(f"{url}/fit").json()
    _done(c, job)
    assert [s.get(f"gs_r{i}") for i in (1, 2, 3)] == [list(r) for r in rg]    # úseky uložené jako v desktopu
    pts_ref, err = ags.fit_points(s.model[0], rg, g.t, s.pv, s.mv, g.Ts)
    assert err is None
    assert np.allclose(s.get("gs_pts"), pts_ref) and s.get("gs_key") == ags.key(s.model[0], rg, s.norm)
    info = c.get(url).json()
    assert info["fitted"] and not info["stale"] and not info["inputs"]["ranges_auto"]
    pts = ags.points(pts_ref)
    for q in pts:
        r = ags.tune_point(s.model[0], q["p"], "SIMC", "PI", float(s.get("samp")), float(s.get("diffgain")), 1.0, 1.6)
        q.update(gain=float(r["Kc"]), ti=float(r["Ti"]) if r["Ti"] > 0 else np.inf, td=float(r["Td"]))
    assert [p["gain"] for p in info["points"]] == pytest.approx([q["gain"] for q in pts])
    assert [p["x"] for p in info["points"]] == pytest.approx([float(s.EP(q["x"])) for q in pts])
    assert [p["fit"] for p in info["points"]] == pytest.approx([q["fit"] for q in pts])
    tab, filled = ags.table(pts, s.EP, s.get("u_pv") or "PV")
    assert info["filled"] == filled
    assert [(r["input"], r["unit"]) for r in info["table"]] == [(n, u) for n, _, u in tab]
    assert np.allclose([r["values"] for r in info["table"]], [v for _, v, _ in tab])
    assert info["issues"] == core.gs_issues(pts) and info["impl_text"]
    assert [x["text"] for x in info["checks"]] == [x[1] for x in guides.apc_gainsched(
        dict(s.report_record(), name=s.c_pv), False, info["spread"], pts, False, info["issues"])]
    # simulace
    sim = c.post(f"{url}/simulate").json()
    ref = ags.simulate_pv(s.model[0], pts, s.base_ctrl(), s.set_ctrl(2), float(s.get("samp")))
    f = s.PR / 100
    assert sim["T_end"] == pytest.approx(float(ref["t"][-1]))
    assert [k["iae_sched"] for k in sim["kpis"]] == pytest.approx([x[3] * f for x in ref["iae"]])
    assert [k["iae_fixed"] for k in sim["kpis"]] == pytest.approx([x[2] * f for x in ref["iae"]])
    assert [k["from_x"] for k in sim["kpis"]] == pytest.approx([float(s.EP(x[0])) for x in ref["iae"]])
    sig = _sig(c, f"{url}/simulate/curves")
    assert {"sp", "pv_fixed", "pv_sched", "mv_fixed", "mv_sched", "gain_fixed", "gain_sched"} <= set(sig)
    assert np.allclose(sig["pv_sched"][1], s.EP(ref["sched"][1]["PV"]), rtol=1e-4, atol=1e-3)
    assert np.allclose(sig["gain_sched"][1], ref["sched"][1]["Gain"], rtol=1e-4, atol=1e-3)


def test_gainsched_settings_stale_auto_reset(ws):
    c, wid, s = ws
    url = f"/workspaces/{wid}/apc/gainsched"
    patch = f"/workspaces/{wid}/settings"
    c.patch(patch, json={"gs_m": "AMIGO", "gs_ct": "PID", "gs_tcf": 2.0, "gs_ms": 1.8})
    info = c.get(url).json()
    assert info["inputs"]["method"] == "AMIGO" and info["inputs"]["ctype"] == "PID" and info["inputs"]["tcf"] == 2.0
    pts = ags.points(s.get("gs_pts"))
    r = ags.tune_point(s.model[0], pts[0]["p"], "AMIGO", "PID", float(s.get("samp")), float(s.get("diffgain")), 2.0, 1.8)
    assert info["points"][0]["gain"] == pytest.approx(r["Kc"]) and info["points"][0]["td"] == pytest.approx(r["Td"])
    c.patch(patch, json={"gs_m": "OPT", "gs_ct": "PI"})
    opt = c.get(url).json()
    r = ags.tune_point(s.model[0], pts[0]["p"], "OPT", "PI", float(s.get("samp")), float(s.get("diffgain")), 2.0, 1.8)
    assert opt["points"][0]["gain"] == pytest.approx(r["Kc"], rel=1e-3)
    res = c.post(f"{url}/reset").json()
    assert (res["inputs"]["tcf"], res["inputs"]["ms"]) == (1.0, 1.6)
    c.patch(patch, json={"gs_m": "SIMC"})
    # jiné úseky → body zastaralé; auto je vrátí na návrh
    rg = c.get(url).json()["inputs"]["ranges"]
    c.patch(patch, json={"gs_r1": [rg[0][0], rg[0][1] - 100.0]})
    assert c.get(url).json()["stale"]
    back = c.post(f"{url}/auto").json()
    assert back["inputs"]["ranges"] == rg and not back["stale"]
    # dva body: třetí se doplní
    c.patch(patch, json={"gs_n": 2})
    two_pts = c.get(url).json()
    assert two_pts["inputs"]["n"] == 2 and len(two_pts["inputs"]["ranges"]) == 2 and two_pts["stale"]
    c.patch(patch, json={"gs_n": 3})
    # chybný úsek se fitovat nedá: úloha skončí chybou a body zůstanou
    c.patch(patch, json={"gs_r1": [0.0, 5.0]})
    job = c.post(f"{url}/fit").json()
    assert _wait(c, job)["state"] == "error"
    assert s.get("gs_pts") is not None
    c.post(f"{url}/auto")


def test_gainsched_integrating_process(ws):
    c, wid, _ = ws
    c.patch(f"/workspaces/{wid}/settings", json={"mcode": "I1D"})
    try:
        for k in ("gainsched", "gainsched_er"):
            info = c.get(f"/workspaces/{wid}/apc/{k}").json()
            assert info["integ"] and info["checks"]
            assert c.post(f"/workspaces/{wid}/apc/{k}/simulate").status_code == 409
        assert c.post(f"/workspaces/{wid}/apc/gainsched/fit").status_code == 409
    finally:
        c.patch(f"/workspaces/{wid}/settings", json={"mcode": "P1D"})


# ---- gain scheduling podle ER
def test_gainsched_er_like_desktop(ws):
    c, wid, s = ws
    url = f"/workspaces/{wid}/apc/gainsched_er"
    code, p, _ = s.model
    PR = s.PR
    info = c.get(url).json()
    inp = info["inputs"]
    assert (inp["E"], inp["k"], inp["spstep"], inp["d"]) == pytest.approx((round(0.05 * PR, 6), 2.0,
                                                                          round(0.2 * PR, 6), 10.0))
    assert not inp["edited"]
    set2 = clean(s.set_ctrl(2))
    assert info["k_max"] == pytest.approx(ags.k_max(code, p, s.set_ctrl(2)))
    rb = core.robustness(code, list(p), dict(set2, Gain=2.0 * set2["Gain"]))
    ms_k = rb["Ms"] if rb["stable"] and np.isfinite(rb["Ms"]) else np.inf
    assert (info["ms_k"] if info["ms_k"] is not None else np.inf) == pytest.approx(ms_k)
    tab = ags.er_table(inp["E"], 2.0, set2, s.get("u_pv") or "PV")
    assert np.allclose([r["values"] for r in info["table"]], [v for _, v, _ in tab])
    assert [x["text"] for x in info["checks"]] == [x[1] for x in guides.apc_gs_er(dict(s.report_record(),
                                                                                       name=s.c_pv), ms_k)]
    # změna přes PATCH /settings, reset
    c.patch(f"/workspaces/{wid}/settings", json={"gs_er_E": 3.0, "gs_er_k": 1.5, "gs_er_spstep": 8.0, "gs_er_d": 5.0})
    ed = c.get(url).json()
    assert ed["inputs"]["edited"] and ed["inputs"]["E"] == 3.0 and ed["table"][0]["values"][0] == pytest.approx(-3.0)
    sim = c.post(f"{url}/simulate").json()
    r = ags.simulate_er(code, p, set2, 3.0 / PR * 100, 1.5, float(max(-45, min(45, 8.0 / PR * 100))), 5.0,
                        float(s.get("samp")))
    assert sim["T_end"] == pytest.approx(float(r["t"][-1]))
    assert [k["name"] for k in sim["kpis"]] == ["fixed", "sched"] + (["zone"] if r["zone"] is not None else [])
    for k, (_, o) in zip(sim["kpis"], (r["fixed"], r["sched"])):
        ref = ags.er_kpis(r["t"], r["sp"], r["tp"], o, set2, PR)
        assert {x: k[x] for x in ref} == pytest.approx(ref)
    assert (sim["zone"] is None) == (r["cz"] is None)
    if r["cz"]:
        assert sim["zone"] == pytest.approx(r["cz"] * PR / 100) and len(sim["scan"]) == len(r["scan"])
    t0 = time.time()
    sig = _sig(c, f"{url}/simulate/curves")                           # bez nového výpočtu (stejné vstupy)
    assert time.time() - t0 < 1.0
    assert {"sp", "pv_fixed", "pv_sched", "mv_sched", "gain_sched"} <= set(sig)
    assert np.allclose(sig["pv_sched"][1], s.EP(r["sched"][1]["PV"]), rtol=1e-4, atol=1e-3)
    rs = c.post(f"{url}/reset").json()["inputs"]
    assert not rs["edited"] and rs["k"] == 2.0 and rs["E"] == pytest.approx(round(0.05 * PR, 6))
    assert not any(k.startswith("gs_er_") for k in s.settings)


# ---- rozvazbení
def test_decouple_like_desktop(two):
    c, wid, proj = two
    url = f"/workspaces/{wid}/apc/decouple"
    (bi, b), = proj.others()
    a = dict(proj.state.report_record(), name=proj.names()[proj.active])
    assert bi == 1
    dz = adec.design(a, b)
    info = c.get(url).json()
    assert info["ok"] and info["loop"] == 1 and info["a"] == a["name"] and info["b"] == b["name"]
    assert info["lam"] == pytest.approx(dz["lam"]) and info["advice_key"] == rga_advice(dz["lam"])
    assert info["advice"] == T(rga_advice(dz["lam"]), a=a["name"], b=b["name"], mva=a["c_mv"], mvb=b["c_mv"])
    assert info["impl_text"]
    ref = adec.params(dz, a, b)
    assert [p["target"] for p in info["params"]] == [x[1] for x in ref]
    assert np.allclose([(p["gain"], p["gain_eng"], p["lead"], p["lag"], p["delay"]) for p in info["params"]],
                       [x[2:] for x in ref])
    assert dz["dab"]["gain"] == pytest.approx(-0.5, abs=0.05)
    assert [x["text"] for x in info["checks"]] == [x[1] for x in guides.apc_decouple(a, b, 0, 1, dz["xab"], dz["xba"])]
    # simulace
    body = {"dtype": "static", "amp_a": 4.0, "amp_b": -3.0}
    sim = c.post(f"{url}/simulate", json=body).json()
    runs = adec.simulate(dz, clean(a["ctrl"]), clean(b["ctrl"]), 4.0, -3.0)
    tab = adec.iae_table(runs, a, b)
    assert [(k["variant"], k["iae_a"], k["iae_b"]) for k in sim["kpis"]] == \
        [(v, pytest.approx(x), pytest.approx(y)) for v, x, y in tab]
    assert sim["dtype"] == "static" and sim["T_end"] == pytest.approx(float(runs["none"][0][-1]))
    sig = _sig(c, f"{url}/simulate/curves", body)
    assert {"sp_a", "pv_a_none", "pv_a", "sp_b", "pv_b_none", "pv_b", "mv_a", "mv_b"} <= set(sig)
    ea = a["pv_rng"][0] + runs["static"][1]["PV_A"] * (a["pv_rng"][1] - a["pv_rng"][0]) / 100
    assert np.allclose(sig["pv_a"][1], ea, rtol=1e-4, atol=1e-3)
    dyn = c.post(f"{url}/simulate", json={}).json()
    assert dyn["dtype"] == "dyn" and dyn["kpis"][2]["iae_a"] != sim["kpis"][2]["iae_a"]
    assert c.post(f"{url}/simulate", json={"amp_a": 500}).status_code == 422
    assert c.post(f"{url}/simulate", json={"dtype": "x"}).status_code == 422
    assert c.get(url, params={"loop": 0}).status_code == 404                    # druhá smyčka nesmí být aktivní
    assert c.get(url, params={"loop": 5}).status_code == 404


def test_decouple_without_cross_coupling_and_missing_model():
    """Demo + druhá smyčka na stejném ventilu: bez modelu 409, pak bez vazby (decoupler nejde), override ano."""
    with TestClient(create_app()) as c:
        wid = c.post("/workspaces").json()["id"]
        u = f"/workspaces/{wid}"
        c.post(f"{u}/data/demo")
        c.patch(f"{u}/settings", json={"chosen": ["P1D"]})
        _done(c, c.post(f"{u}/identify").json())
        c.post(f"{u}/loops", json={"name": "FIC", "pv": "FI100.Pritok", "mv": "LIC101.MV"})
        c.put(f"{u}/loops/active", json={"index": 0})
        for k in ("decouple", "override"):
            assert c.get(f"{u}/apc/{k}").status_code == 409                 # druhá smyčka nemá model
        c.put(f"{u}/loops/active", json={"index": 1})
        c.patch(f"{u}/settings", json={"chosen": ["P1D"]})
        _done(c, c.post(f"{u}/identify").json())
        c.put(f"{u}/loops/active", json={"index": 0})
        info = c.get(f"{u}/apc/decouple").json()
        assert not info["ok"] and info["lam"] is None and info["params"] == [] and info["checks"]
        assert info["advice"] and info["b"] in info["advice"] and info["advice_key"] is None   # vysvětlení chybějící vazby
        assert c.post(f"{u}/apc/decouple/simulate", json={}).status_code == 409
        assert c.post(f"{u}/apc/decouple/simulate/curves", json={}).status_code == 409
        ov = c.get(f"{u}/apc/override").json()
        assert not ov["mv_differs"] and ov["mv_a"] == ov["mv_b"] == "LIC101.MV"
        assert c.post(f"{u}/apc/override/simulate", json={}).status_code == 200


# ---- override
def test_override_like_desktop(two):
    c, wid, proj = two
    url = f"/workspaces/{wid}/apc/override"
    (bi, b), = proj.others()
    a = dict(proj.state.report_record(), name=proj.names()[proj.active])
    for sel in ("min", "max"):
        info = c.get(url, params={"sel": sel}).json()
        step, lim = aov.defaults(a, b, sel)
        assert info["defaults"] == pytest.approx({"step": step, "lim": lim}) and info["sel"] == sel
        assert info["mv_differs"] == (b["c_mv"] != a["c_mv"]) and info["impl_text"]
        assert [x["text"] for x in info["checks"]] == [x[1] for x in guides.apc_override(a, b, bi)]
    assert info["mv_differs"]                                                # smyčky mají různé ventily
    # výchozí scénář a vlastní vstupy
    for sel, body in (("min", {}), ("max", {"sel": "max", "step": 3.0, "lim": 52.0})):
        step, lim = aov.defaults(a, b, sel)
        step, lim = (body.get("step", step), body.get("lim", lim))
        tt, o, o0 = aov.simulate(a, b, step, lim, sel)
        k = aov.kpis(a, b, o, o0, sel)
        sim = c.post(f"{url}/simulate", json=body).json()
        assert sim["sel"] == sel and sim["step"] == pytest.approx(step) and sim["lim"] == pytest.approx(lim)
        assert sim["kpis"] == pytest.approx(k) and sim["T_end"] == pytest.approx(float(tt[-1]))
        sig = _sig(c, f"{url}/simulate/curves", body)
        assert {"sp_a", "pv_a_without", "pv_a", "lim_b", "pv_b", "u_a", "u_b", "mv"} <= set(sig)
        eb = b["pv_rng"][0] + o["PV_B"] * (b["pv_rng"][1] - b["pv_rng"][0]) / 100
        assert np.allclose(sig["pv_b"][1], eb, rtol=1e-4, atol=1e-3)
    assert c.post(f"{url}/simulate", json={"sel": "mid"}).status_code == 422
    assert c.post(f"{url}/simulate", json={}, params={"loop": 3}).status_code == 404
