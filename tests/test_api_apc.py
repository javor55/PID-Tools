"""
API – techniky APC (M11b): dopředná vazba a Smithův prediktor shodné s voláním app vrstvy (jako desktop) na demu.
"""
import os
import sys
import time

import numpy as np
import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from pidtools.api import create_app  # noqa: E402
from pidtools.app import feedforward as ffm  # noqa: E402
from pidtools.app import signalpack  # noqa: E402
from pidtools.app.apc import feedforward as aff  # noqa: E402
from pidtools.app.apc import smith as asm  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
import golden  # noqa: E402

REF = golden.load("demo_common")


def _wait(client, job, t=600):
    t0 = time.time()
    while time.time() - t0 < t:
        st = client.get(f"/jobs/{job['id']}").json()
        if st["state"] not in ("queued", "running"):
            assert st["state"] == "done", st
            return st
        time.sleep(0.2)
    raise AssertionError("job timeout")


@pytest.fixture(scope="module")
def ws():
    with TestClient(create_app()) as c:
        wid = c.post("/workspaces").json()["id"]
        c.post(f"/workspaces/{wid}/data/demo")
        c.patch(f"/workspaces/{wid}/settings", json={"chosen": ["P1D", "I1D"]})
        _wait(c, c.post(f"/workspaces/{wid}/identify").json())
        yield c, wid, c.app.state.workspace(wid)


def test_requires_model():
    with TestClient(create_app()) as c:
        wid = c.post("/workspaces").json()["id"]
        assert c.get(f"/workspaces/{wid}/apc/ff").status_code == 409
        assert c.get(f"/workspaces/{wid}/apc/smith").status_code == 409


def test_ff_default_roundtrip_reset(ws):
    c, wid, s = ws
    code, p, pdl = s.model
    url = f"/workspaces/{wid}/apc/ff"
    info = c.get(url).json()
    ref = ffm.design(code, p, pdl, None)
    assert info["model"] == code and len(info["dists"]) == len(pdl) == 1
    d = info["dists"][0]
    assert d["name"] == s.c_d[0] and d["design"] == ref[0] and not d["edited"] and d["values"] == []
    assert d["defaults"] == pytest.approx({k: ref[0][k] for k in ("gain", "lead", "lag", "delay")})
    assert d["eng_gain"] == pytest.approx(ffm.eng_gain(ref[0]["gain"], s.MR))
    # částečná změna → stav jako u desktopu (ffm.state)
    new = c.put(url, json=[{"use": True, "dyn": True, "gain": 1.5, "lag": 4.0}]).json()["dists"][0]
    assert new["design"] == dict(ref[0], use=True, dyn=True, gain=1.5, lag=4.0) and new["edited"]
    assert s.ff_state == ffm.state([new["design"]])
    assert new["eng_gain"] == pytest.approx(1.5 * s.MR / 100)
    assert any(r["param"] == "PIDConL.FFwdHiLim" for r in new["values"])
    assert c.get(url).json()["dists"][0]["design"] == new["design"]
    assert c.put(url, json=[None]).json()["dists"][0]["design"] == new["design"]
    assert c.put(url, json=[{}, {}]).status_code == 422
    assert c.put(url, json=[{"lag": -1}]).status_code == 422
    # reset: hodnoty z modelu, zapnutí a dynamika zůstanou
    rs = c.post(f"{url}/reset", json={"index": 0}).json()["dists"][0]
    assert rs["design"] == dict(ref[0], use=True, dyn=True) and not rs["edited"]
    assert c.post(f"{url}/reset", json={"index": 5}).status_code == 404
    c.put(url, json=[{"gain": 9.0}])
    assert c.post(f"{url}/reset").json()["dists"][0]["design"]["gain"] == pytest.approx(ref[0]["gain"])
    c.put(url, json=[{"use": False, "dyn": False}])


def test_ff_simulation_like_desktop(ws):
    c, wid, s = ws
    url = f"/workspaces/{wid}/apc/ff"
    c.put(url, json=[{"use": True, "dyn": True}])
    step = c.get(url).json()["dists"][0]["step"]
    code, p, pdl = s.model
    t, outs = aff.simulate(code, p, pdl, s.set_ctrl(2), ffm.design(code, p, pdl, s.ff_state), 0, step,
                           float(s.get("samp")))
    ref = aff.sim_kpis(t, outs, s.PR)
    sim = c.post(f"{url}/simulate", json={"dist": 0}).json()
    assert sim["step"] == step and sim["T_end"] == pytest.approx(float(t[-1]))
    for k in ("none", "static", "dynamic"):
        assert sim["kpis"][k] == pytest.approx(ref[k])
    assert sim["kpis"]["dynamic"]["iae"] != sim["kpis"]["none"]["iae"]
    meta, sig = signalpack.unframe(c.post(f"{url}/simulate/curves", json={"dist": 0}).content)
    assert {"pv_none", "mv_none", "pv_static", "pv_dynamic", "mv_dynamic"} <= set(sig)
    tt, pv = sig["pv_dynamic"]
    assert np.allclose(pv, s.EP(outs["dynamic"]["PV"]), rtol=1e-4, atol=1e-3)
    assert c.post(f"{url}/simulate", json={"dist": 3}).status_code == 404
    c.put(url, json=[{"use": False, "dyn": False}])


def test_ff_changes_tuning_simulation(ws):
    c, wid, s = ws
    ff = f"/workspaces/{wid}/apc/ff"
    sim_url = f"/workspaces/{wid}/simulate"
    c.put(f"/workspaces/{wid}/scenario", json={"kind": "meas"})         # skok měřené poruchy
    c.put(ff, json=[{"use": False}])
    off = c.post(sim_url, json={}).json()["kpis"]["2"]
    code, p, pdl = s.model
    assert s.set_ctrl(2)["FF"] == [0.0]
    c.put(ff, json=[{"use": True, "dyn": False}])
    ctrl = s.set_ctrl(2)
    des = ffm.design(code, p, pdl, s.ff_state)
    assert (ctrl["FF"], ctrl["FF_LL"]) == ffm.to_ctrl(des)
    on = c.post(sim_url, json={"ff_cmp": True}).json()["kpis"]["2"]
    assert on != off
    c.put(ff, json=[{"use": False}])
    assert c.post(sim_url, json={}).json()["kpis"]["2"] == off
    c.put(f"/workspaces/{wid}/scenario", json={"kind": "sp"})


def test_smith_like_direct_calls(ws):
    c, wid, s = ws
    code, p, _ = s.model
    samp = float(s.get("samp"))
    url = f"/workspaces/{wid}/apc/smith"
    info = c.get(url).json()
    inp = info["inputs"]
    assert inp["method"] == "SIMC" and inp["ctype"] == "PI" and info["opt_ready"]
    assert inp["tc"] == pytest.approx(inp["tc_default"])
    assert inp["tc"] == pytest.approx(REF["apc"]["smith_tc"], rel=1e-3)     # zlatý případ (zaokrouhlený, platforma)
    assert inp["tc_key"] == f"apc_sm_tc|{code}|{p[-1]:.4g}"
    r = asm.controller(code, p, "SIMC", "PI", inp["tc"], samp, s.base_ctrl(), None)
    assert {k: info["controller"][k] for k in ("Kc", "Ti", "Td")} == pytest.approx({k: r[k] for k in ("Kc", "Ti", "Td")})
    assert info["integ"]                                        # demo = I1D → bez hodnot šablony
    assert info["rows"] is None and info["basis_text"] is None
    # zpoždění a poměr
    from pidtools.app.apc.common import tchar
    assert info["ratio"] == pytest.approx(p[-1] / tchar((code, p)))
    # simulace PID vs Smith s chybou procesu
    body = {"ek": 10, "et": -5, "eth": 20}
    sim = c.post(f"{url}/simulate", json=body).json()
    ref = asm.simulate(code, p, asm.plant_error(p, 10, -5, 20), s.base_ctrl(), s.set_ctrl(2), "PI", inp["tc"], samp,
                       r=r)
    f = s.PR / 100
    for k in ("pid", "smith"):
        assert sim["kpis"][k]["iae_sp"] == pytest.approx(ref["iae"][k][0] * f)
        assert sim["kpis"][k]["iae_load"] == pytest.approx(ref["iae"][k][1] * f)
    meta, sig = signalpack.unframe(c.post(f"{url}/simulate/curves", json=body).content)
    assert {"sp", "pv_pid", "mv_pid", "pv_smith", "mv_smith"} <= set(sig)
    assert np.allclose(sig["pv_smith"][1], s.EP(ref["smith"][1]["PV"]), rtol=1e-4, atol=1e-3)
    assert c.post(f"{url}/simulate", json={"ek": 500}).status_code == 422


def test_smith_settings_and_values():
    """Model bez integrace: hodnoty šablony, ruční metoda a klíče nastavení jako desktop."""
    with TestClient(create_app()) as c:
        wid = c.post("/workspaces").json()["id"]
        c.post(f"/workspaces/{wid}/data/demo")
        c.patch(f"/workspaces/{wid}/settings", json={"chosen": ["P1D"]})
        _wait(c, c.post(f"/workspaces/{wid}/identify").json())
        s = c.app.state.workspace(wid)
        c.patch(f"/workspaces/{wid}/settings", json={"mcode": "P1D"})
        code, p, _ = s.model
        assert code == "P1D"
        url = f"/workspaces/{wid}/apc/smith"
        samp = float(s.get("samp"))
        pv_id, mv_id = s.segment()[1:3]
        pv_op, mv_op = asm.operating_point(pv_id, mv_id)
        u_pv, u_mv = s.get("u_pv") or "PV", s.get("u_mv") or "MV"
        info = c.get(url).json()
        assert not info["integ"] and info["rows"] and info["general_rows"] and info["basis_text"]
        r = asm.controller(code, p, "SIMC", "PI", info["inputs"]["tc"], samp, s.base_ctrl(), None)
        v, _, rows = asm.values(code, p, s, pv_op, mv_op, "PI", info["inputs"]["tc"], samp, u_pv, u_mv, r=r)
        assert [x["value"] for x in info["rows"]] == pytest.approx([x[2] for x in rows])
        assert info["values"]["k"] == pytest.approx(v["k"])
        assert info["basis_text"] == asm.basis_text(code, p, s, pv_op, mv_op, samp, u_pv, u_mv)
        assert info["pv_op"] == pytest.approx(float(s.EP(pv_op)))
        gen = asm.general_rows(code, p, s, pv_op, mv_op, r, info["inputs"]["tc"], "SIMC", "PI", u_pv, u_mv)
        assert [g["key"] for g in info["general_rows"]] == [g[0] for g in gen]
        # změna přes PATCH /settings: ruční metoda a PID
        c.patch(url.replace("/apc/smith", "/settings"),
                json={"apc_sm_method": "manual", "apc_sm_ct": "PID", "apc_sm_man": [2.0, 30.0, 4.0]})
        m = c.get(url).json()
        assert m["inputs"]["method"] == "manual" and m["inputs"]["manual"] == [2.0, 30.0, 4.0]
        assert (m["controller"]["Kc"], m["controller"]["Ti"], m["controller"]["Td"]) == (2.0, 30.0, 4.0)
        assert [x["input"] for x in m["rows"]][-1] == "TD"


def test_smith_optimize_job(ws):
    c, wid, s = ws
    code, p, _ = s.model
    samp = float(s.get("samp"))
    url = f"/workspaces/{wid}/apc/smith"
    c.patch(f"/workspaces/{wid}/settings", json={"apc_sm_method": "OPT", "apc_sm_ct": "PI"})
    pre = c.get(url).json()
    assert not pre["opt_ready"] and pre["controller"] is None
    assert c.post(f"{url}/simulate", json={}).status_code == 409
    job = c.post(f"{url}/optimize").json()
    _wait(c, job)
    res = c.get(f"/jobs/{job['id']}/result").json()
    ref = asm.controller(code, p, "OPT", "PI", None, samp, s.base_ctrl())
    assert {k: res[k] for k in ("Kc", "Ti", "Td")} == pytest.approx({k: ref[k] for k in ("Kc", "Ti", "Td")})
    post = c.get(url).json()
    assert post["opt_ready"] and post["controller"]["Kc"] == pytest.approx(ref["Kc"])
    assert post["controller"]["notes"][0]["key"] == "sm_opt_note"
    assert c.post(f"{url}/simulate", json={}).status_code == 200
    c.patch(f"/workspaces/{wid}/settings", json={"apc_sm_method": "SIMC"})
