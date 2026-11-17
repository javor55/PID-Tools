"""
API – zpět / znovu pro změny nastavení smyčky (FEATURE-006): zásobník kroků v `Project.history` (app.undo).
Pokrývá PATCH /settings, PUT /tuning/sets/{n}, PUT /range a PUT /scenario; načtení dat a identifikace ho vyprázdní.
Čas pro slučování změn téhož klíče se podvrhuje (`history.clock`).
"""
import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from pidtools.api import create_app  # noqa: E402
from pidtools.app import undo as ud  # noqa: E402

API = "/api/v1/workspaces"


class Clock:
    """Řízený čas: `tick` posune hodiny (výchozí posun mezi dvěma změnami je větší než okno slučování)."""
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def tick(self, dt=10.0):
        self.t += dt


def _wait(c, job, t=300):
    import time
    t0 = time.time()
    while time.time() - t0 < t:
        st = c.get(f"/api/v1/jobs/{job['id']}").json()
        if st["state"] not in ("queued", "running"):
            assert st["state"] == "done", st
            return st
        time.sleep(0.2)
    raise AssertionError("job timeout")


@pytest.fixture(scope="module")
def ws():
    with TestClient(create_app()) as c:
        wid = c.post("/api/v1/workspaces").json()["id"]
        c.post(f"{API}/{wid}/data/demo")
        c.patch(f"{API}/{wid}/settings", json={"chosen": ["P1D"]})
        _wait(c, c.post(f"{API}/{wid}/identify").json())
        proj = c.app.state.store.get(wid)
        base = {k: proj.state.settings.get(k) for k in ("opt_ms", "pvfilt", "set1_gain", "set1_ti", "set1_td")}
        yield c, wid, proj, base


@pytest.fixture
def env(ws):
    """Čistý zásobník a řízené hodiny pro každý test."""
    c, wid, proj, base = ws
    c.patch(f"{API}/{wid}/settings", json={k: v for k, v in base.items() if v is not None})   # stejný výchozí stav testů
    c.put(f"{API}/{wid}/range", json={"a": 0, "b": float(proj.state.t[-1])})
    proj.history.clear()
    clk = Clock()
    proj.history.clock = clk
    yield c, f"{API}/{wid}", proj, clk
    proj.history.clock = ud.time.monotonic


def _undo(c, u):
    return c.get(f"{u}/undo").json()


def test_three_changes_undo_and_redo(env):
    c, u, proj, clk = env
    s0, r0 = c.get(f"{u}/settings").json(), c.get(u).json()["rng"]
    assert _undo(c, u) == {"undo": None, "redo": None}
    assert c.patch(f"{u}/settings", json={"opt_ms": 1.8}).status_code == 200
    clk.tick()
    assert c.patch(f"{u}/settings", json={"pvfilt": 2.5}).status_code == 200
    clk.tick()
    assert c.put(f"{u}/range", json={"a": 0, "b": r0[1] / 2}).status_code == 200
    s3, rng3 = c.get(f"{u}/settings").json(), c.get(u).json()["rng"]
    assert s3 != s0 and rng3 != r0
    for _ in range(3):
        assert c.post(f"{u}/undo").status_code == 200
    assert c.get(f"{u}/settings").json() == s0
    assert c.get(u).json()["rng"] == r0
    assert _undo(c, u)["undo"] is None and _undo(c, u)["redo"] is not None
    for _ in range(3):
        assert c.post(f"{u}/redo").status_code == 200
    assert c.get(f"{u}/settings").json() == s3
    assert c.get(u).json()["rng"] == rng3
    assert _undo(c, u)["redo"] is None


def test_new_change_after_undo_clears_redo(env):
    c, u, proj, clk = env
    c.patch(f"{u}/settings", json={"opt_ms": 1.4})
    clk.tick()
    c.patch(f"{u}/settings", json={"opt_ms": 2.0})
    assert c.post(f"{u}/undo").status_code == 200
    assert _undo(c, u)["redo"] is not None
    clk.tick()
    c.patch(f"{u}/settings", json={"pvfilt": 3.0})
    assert _undo(c, u)["redo"] is None
    assert c.post(f"{u}/redo").status_code == 409


def test_empty_stack_is_409(env):
    c, u, *_ = env
    for what in ("undo", "redo"):
        r = c.post(f"{u}/{what}")
        assert r.status_code == 409 and r.json()["detail"]


def test_same_key_within_two_seconds_is_one_step(env):
    c, u, proj, clk = env
    s0 = c.get(f"{u}/settings").json()
    c.patch(f"{u}/settings", json={"opt_ms": 1.4})
    clk.tick(1.5)
    c.patch(f"{u}/settings", json={"opt_ms": 1.8})                  # do 2 s od předchozí změny: sloučí se
    assert len(proj.history.undo) == 1
    assert _undo(c, u)["undo"] == "Robustness Ms 1.6 → 1.8"     # before z prvního, after z posledního
    clk.tick(1.9)
    c.patch(f"{u}/settings", json={"opt_ms": 2.0})                  # okno se počítá od poslední změny
    assert len(proj.history.undo) == 1
    clk.tick(2.5)
    c.patch(f"{u}/settings", json={"opt_ms": 1.4})                  # po 2 s nový krok
    assert len(proj.history.undo) == 2
    c.post(f"{u}/undo")
    assert c.get(f"{u}/settings").json()["opt_ms"] == 2.0
    c.post(f"{u}/undo")
    assert c.get(f"{u}/settings").json() == s0


def test_merge_back_to_original_drops_step(env):
    c, u, proj, clk = env
    c.patch(f"{u}/settings", json={"opt_ms": 1.8})
    clk.tick(0.5)
    c.patch(f"{u}/settings", json={"opt_ms": 1.6})
    assert proj.history.undo == []


def test_different_keys_and_noop_do_not_merge(env):
    c, u, proj, clk = env
    c.patch(f"{u}/settings", json={"opt_ms": 1.8})
    clk.tick(0.5)
    c.patch(f"{u}/settings", json={"pvfilt": 1.0})
    assert len(proj.history.undo) == 2
    c.patch(f"{u}/settings", json={"pvfilt": 1.0})                  # beze změny hodnoty krok nevznikne
    assert len(proj.history.undo) == 2


def test_ui_only_keys_make_no_step(env):
    c, u, proj, clk = env
    assert c.patch(f"{u}/settings", json={"dview": "{}", "plot_h": 300}).status_code == 200
    assert proj.history.undo == []


def test_limit_of_50_steps(env):
    c, u, proj, clk = env
    for i in range(55):
        clk.tick()
        c.patch(f"{u}/settings", json={"pvfilt": float(i + 1)})
    assert len(proj.history.undo) == ud.LIMIT


def test_set2_and_set2_defined_return_together(env):
    c, u, proj, clk = env
    c.patch(f"{u}/settings", json={"set2_defined": False, "set2_gain": 1.0, "set2_ti": 100.0, "set2_td": 0.0})
    proj.history.clear()
    s0 = c.get(f"{u}/settings").json()
    assert s0["set2_defined"] is False
    r = c.put(f"{u}/tuning/sets/2", json={"Kc": 2.5, "Ti": 40.0, "Td": 0.0, "log": {"method": "test"}})
    assert r.status_code == 200
    s1 = c.get(f"{u}/settings").json()
    assert s1["set2_defined"] is True and s1["set2_gain"] == 2.5
    lab = _undo(c, u)["undo"]
    assert lab.startswith("Set 2 Gain 1 → 2.5") and "TI" in lab
    assert c.post(f"{u}/undo").status_code == 200
    assert c.get(f"{u}/settings").json() == s0                      # i set2_defined a historie ladění
    assert c.post(f"{u}/redo").status_code == 200
    assert c.get(f"{u}/settings").json() == s1


def test_set1_label_uses_minus_sign(env):
    c, u, proj, clk = env
    c.patch(f"{u}/settings", json={"set1_gain": -2.0, "set1_ti": 50.0, "set1_td": 0.0})
    proj.history.clear()
    clk.tick()
    c.patch(f"{u}/settings", json={"set1_gain": -1.5})
    assert _undo(c, u)["undo"] == "Set 1 Gain −2 → −1.5"


def test_range_label_and_undo(env):
    c, u, proj, clk = env
    a0, b0 = c.get(u).json()["rng"]
    c.put(f"{u}/range", json={"a": 0, "b": 900})
    assert _undo(c, u)["undo"] == f"Segment {a0:g}–{b0:g} s → 0–900 s"
    c.post(f"{u}/undo")
    assert c.get(u).json()["rng"] == [a0, b0]


def test_scenario_undo(env):
    c, u, proj, clk = env
    k0 = c.get(f"{u}/scenario").json()
    other = next(k for k in k0["kinds"] if k != k0["kind"])
    assert c.put(f"{u}/scenario", json={"kind": other}).status_code == 200
    assert c.get(f"{u}/scenario").json()["kind"] == other
    assert _undo(c, u)["undo"].startswith("Scenario")
    c.post(f"{u}/undo")
    assert c.get(f"{u}/scenario").json()["kind"] == k0["kind"]
    clk.tick()
    sp0 = k0["sp_from_to"]
    c.put(f"{u}/scenario", json={"sp_from_to": [sp0[0] + 1, sp0[1] + 2]})
    c.post(f"{u}/undo")
    assert c.get(f"{u}/scenario").json()["sp_from_to"] == sp0


def test_invalid_value_from_history_is_checked(env):
    c, u, proj, clk = env
    proj.history.undo.append(ud.Step(proj.active, {"samp": -5.0}, {"samp": 1.0}))     # hodnota, která by neprošla
    r = c.post(f"{u}/undo")
    assert r.status_code == 409 and "samp" in r.json()["detail"]
    assert proj.history.undo == []                                                    # krok se přeskočil


def test_step_of_removed_loop_is_skipped(env):
    c, u, proj, clk = env
    proj.history.undo.append(ud.Step(7, {"pvfilt": 1.0}, {"pvfilt": 2.0}))
    r = c.post(f"{u}/undo")
    assert r.status_code == 409 and "loop" in r.json()["detail"]
    assert proj.history.undo == []


def test_missing_key_is_removed_on_undo(env):
    c, u, proj, clk = env
    assert "ed|X" not in proj.state.settings
    c.patch(f"{u}/settings", json={"ed|X": 1.5})
    assert proj.state.settings["ed|X"] == 1.5
    c.post(f"{u}/undo")
    assert "ed|X" not in proj.state.settings
    c.post(f"{u}/redo")
    assert proj.state.settings["ed|X"] == 1.5


def test_step_belongs_to_its_loop_and_survives_loop_switch(env):
    c, u, proj, clk = env
    assert c.post(f"{u}/loops", json={"name": "L2", "pv": proj.state.c_pv, "mv": proj.state.c_mv}).status_code == 200
    try:
        c.put(f"{u}/loops/active", json={"index": 0})
        c.patch(f"{u}/settings", json={"pvfilt": 7.0})
        c.put(f"{u}/loops/active", json={"index": 1})                 # přepnutí smyčky zásobník nemaže
        lab = _undo(c, u)["undo"]
        assert lab is not None and "·" in lab                    # popisek nese název smyčky kroku
        c.post(f"{u}/undo")
        assert proj.loops[0].settings["pvfilt"] != 7.0 and proj.active == 1
    finally:
        c.delete(f"{u}/loops/1")
        c.put(f"{u}/loops/active", json={"index": 0})


def test_history_is_not_saved_into_project(env):
    c, u, proj, clk = env
    c.patch(f"{u}/settings", json={"opt_ms": 1.8})
    assert "undo" not in str(proj.to_project(False).keys()) and "history" not in proj.to_project(False)


def test_load_data_and_identify_clear_stack(ws):
    c, wid, proj, _ = ws
    u = f"{API}/{wid}"
    proj.history.clear()
    c.patch(f"{u}/settings", json={"pvfilt": 11.0})
    assert _undo(c, u)["undo"] is not None
    _wait(c, c.post(f"{u}/identify").json())                          # výsledek identifikace zásobník vyprázdní
    assert _undo(c, u) == {"undo": None, "redo": None}
    c.patch(f"{u}/settings", json={"pvfilt": 12.0})
    assert _undo(c, u)["undo"] is not None
    c.put(f"{u}/columns", json={"pv": proj.state.c_pv, "mv": proj.state.c_mv})   # změna sloupců
    assert _undo(c, u)["undo"] is None
    c.patch(f"{u}/settings", json={"pvfilt": 11.0})
    assert c.post(f"{u}/data/demo").status_code == 200                # načtení dat
    assert _undo(c, u) == {"undo": None, "redo": None}
    assert c.post(f"{u}/undo").status_code == 409
