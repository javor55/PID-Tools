"""Zdroje a mapování v projektu (app.workspace.sources): starý projekt a jednosoubor se chovají jako dřív, více zdrojů
se složí na společnou mřížku, mapování smyček, uložení a načtení nového formátu, podklady pro Trendy."""
import json
import os
import sys

import numpy as np
import pandas as pd
import pytest

from pidtools.app import project as prj
from pidtools.app.dataio import read_table
from pidtools.app.domain import trend
from pidtools.app.domain.model import LoopSpec, Roles, SourceRef, TimeGrid
from pidtools.app.workspace import Workspace
from pidtools.app.workspace.loops import Project
from pidtools.core import demo_data

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
import golden  # noqa: E402


def _load(path):
    with open(os.path.join(HERE, path), encoding="utf-8") as f:
        return prj.load_project(f.read())


# ---- zlaté případy přes novou cestu (migrace → zdroj → Workspace): výsledky se nesmí změnit
class ViaProject(Workspace):
    """Pracovní prostor, jehož `apply_project` / `load_demo` jde přes `loops.Project` (migrace a zdroje)."""

    def apply_project(self, proj):
        p = Project()
        p.apply_project(proj)
        self.__dict__.update(p.state.__dict__)

    def load_demo(self):
        p = Project()
        p.load_demo()
        self.__dict__.update(p.state.__dict__)


@pytest.mark.parametrize("name", list(golden.CASES))
def test_golden_through_project_path(name, monkeypatch):
    monkeypatch.setattr(golden, "_state", ViaProject)
    diffs = golden.compare(golden.load(name), golden.run_case(name))
    assert not diffs, "\n".join(f"{p}: uloženo {a!r}, nyní {b!r}" for p, a, b in diffs[:40])


@pytest.mark.parametrize("src", ["golden/tic001.json", "data/project_v1.json"])
def test_old_project_same_data_as_workspace(src):
    """Starý projekt (v1 i v2) otevřený projektem dá tytéž signály, mřížku, sloupce a nastavení jako Workspace."""
    proj = _load(src)
    w = Workspace()
    w.apply_project(proj)
    p = Project()
    p.apply_project(proj)
    s = p.state
    assert len(p.sources) == 1 and p.sources[0].src.id == "s1"
    assert (s.c_pv, s.c_mv, s.c_sp, s.c_d, s.c_pos) == (w.c_pv, w.c_mv, w.c_sp, w.c_d, w.c_pos)
    assert s.fname == w.fname and s.rng == w.rng and s.settings == w.settings
    for a, b in ((s.grid.t, w.grid.t), (s.grid.pv_e, w.grid.pv_e), (s.grid.mv_e, w.grid.mv_e)):
        np.testing.assert_array_equal(a, b)


def test_save_writes_versioned_format_and_roundtrips():
    p = Project()
    p.apply_project(_load("golden/tic001.json"))
    d1 = json.loads(prj.serialize_project(p.to_project(include_data=True)))
    assert d1["format"] == "pidtools.project" and d1["version"] == 3 and "data" not in d1
    assert d1["sources"][0]["data_ref"]["embedded"] and len(d1["sources"][0]["data_ref"]["sha256"]) == 64
    assert d1["spec"]["roles"]["pv"] == dict(source="s1", column="TIC001_PV")
    p2 = Project()
    p2.apply_project(prj.load_project(json.dumps(d1)))
    d2 = json.loads(prj.serialize_project(p2.to_project(include_data=True)))
    for d in (d1, d2):
        d.pop("created", None)
    assert golden.compare(d1, d2, rtol=1e-9, atol=1e-12) == []
    np.testing.assert_allclose(p2.state.grid.pv_e, p.state.grid.pv_e, rtol=1e-5)


def test_save_without_data_and_reload_keeps_loaded_data():
    p = Project()
    p.apply_project(_load("golden/tic001.json"))
    d = json.loads(prj.serialize_project(p.to_project(include_data=False)))
    assert not d["sources"][0]["data_ref"]["embedded"] and "data" not in d["sources"][0]
    p.apply_project(prj.load_project(json.dumps(d)))                        # data zůstanou ta načtená
    assert p.state.has_data and p.state.c_pv == "TIC001_PV"
    q = Project()
    q.apply_project(prj.load_project(json.dumps(d)))                        # bez dat: smyčka s nastavením, bez dat
    assert not q.state.has_data and q.state.get("loop_tag") == "TIC001"


def test_multi_loop_project_roundtrip():
    t = np.arange(0, 2000.0)
    r = np.random.default_rng(0)
    df = pd.DataFrame({"Time": t, "A.PV": np.cumsum(r.normal(size=len(t))), "A.OUT": np.round(r.normal(size=len(t))),
                       "B.PV": np.cumsum(r.normal(size=len(t))), "B.OUT": np.round(r.normal(size=len(t)))})
    p = Project()
    p.load_frame(df, "two.csv")
    p.add_loop_with("B", "B.PV", "B.OUT")
    assert [lp.tag for lp in map(p.loop_spec, range(2))] == ["", "B"]
    d = json.loads(prj.serialize_project(p.to_project(True)))
    assert len(d["loops"]) == 2 and d["active"] == 2 and d["loops"][1]["spec"]["roles"]["pv"]["column"] == "B.PV"
    q = Project()
    q.apply_project(prj.load_project(json.dumps(d)))
    assert q.active == 1 and [ls.c_pv for ls in q.loops] == [ls.c_pv for ls in p.loops]
    assert len(q.sources) == 1 and q.loops[0].src_ids == ["s1"]


# ---- jeden soubor jako dnes
def test_single_file_through_source_equals_workspace():
    t, sp, pv, mv, q = demo_data()
    csv = pd.DataFrame({"Time": t, "LIC.SP": sp, "LIC.PV": pv, "LIC.MV": mv}).to_csv(index=False).encode()
    w = Workspace()
    w.load_frame(read_table("a.csv", csv), "a.csv")
    p = Project()
    rt = p.add_source("a.csv", csv)
    assert rt.src.kind == "csv" and p.state.fname == "a.csv"
    for a, b in ((p.state.grid.t, w.grid.t), (p.state.grid.pv_e, w.grid.pv_e), (p.state.grid.mv_e, w.grid.mv_e),
                 (p.state.grid.sp_e, w.grid.sp_e)):
        np.testing.assert_array_equal(a, b)
    assert (p.state.c_pv, p.state.c_mv, p.state.c_sp) == (w.c_pv, w.c_mv, w.c_sp)


def test_table_loaded_into_workspace_is_registered_as_source():
    p = Project()
    t = np.arange(100.0)
    p.state.load_frame(pd.DataFrame({"Time": t, "X.PV": t, "X.OUT": t % 7}), "x.xlsx")
    p.sync()
    assert [r.src.name for r in p.sources] == ["x.xlsx"] and p.sources[0].src.kind == "xlsx"
    assert p.loop_spec(0).roles.pv == SourceRef("s1", "X.PV")
    p.state.load_frame(pd.DataFrame({"Time": t, "Y.PV": t, "Y.OUT": t % 7}), "y.csv")      # tabulka nahrazena
    p.sync()
    assert [r.src.name for r in p.sources] == ["y.csv"]


# ---- více zdrojů: posun, časové pásmo, vlastní vzorkování, mapování
def _two_sources():
    t, sp, pv, mv, q = demo_data()
    t0 = pd.Timestamp("2026-03-01 08:00:00")
    a = pd.DataFrame({"Time": t0 + pd.to_timedelta(t, unit="s"), "LIC101.SP": sp, "LIC101.PV": pv, "LIC101.MV": mv})
    idx = np.arange(0, len(t), 10)
    b = pd.DataFrame({"Time": t0 + pd.to_timedelta(t[idx], unit="s") + pd.Timedelta(hours=1), "FI100.Pritok": q[idx]})
    p = Project()
    p.add_source("a.csv", a.to_csv(index=False).encode(), timezone="UTC")
    p.add_source("b.csv", b.to_csv(index=False).encode(), timezone="Europe/Prague")      # hodiny v CET = o hodinu víc
    return p, t, q, idx


def test_two_sources_timezone_alignment_and_mapping():
    p, t, q, idx = _two_sources()
    assert [r.id for r in p.sources] == ["s1", "s2"] and p.state.src_ids == ["s1"]
    spec = p.loop_spec(0)
    spec.roles.dv = [SourceRef("s2", "FI100.Pritok")]
    p.set_loop_spec(0, spec)
    ws = p.state
    assert ws.src_ids == ["s1", "s2"] and ws.c_d == ["FI100.Pritok"] and ws.grid.Ts == 1.0
    np.testing.assert_allclose(ws.grid.dists[0], np.interp(ws.t + ws.grid.T0, t[idx], q[idx]), atol=1e-9)
    assert ws.sig.origin == pd.Timestamp("2026-03-01 08:00:00")             # hodiny zdroje bez pásma
    assert p.loop_spec(0).roles.dv == [SourceRef("s2", "FI100.Pritok")]


def test_offset_manual_period_and_rollback():
    p, t, q, idx = _two_sources()
    spec = p.loop_spec(0)
    spec.roles.dv = [SourceRef("s2", "FI100.Pritok")]
    p.set_loop_spec(0, spec)
    p.update_source("s2", offset_s=60.0)                                    # pomalejší zdroj o minutu později
    ws = p.state
    assert ws.grid.T0 == 60.0 and len(ws.t) == 3591 - 60 - 1 + 1 - 0 or len(ws.t) > 3000
    before = (len(ws.t), p.rt("s2").src.offset_s, ws.c_d)
    with pytest.raises(ValueError):
        p.update_source("s2", offset_s=1e7)                                 # žádný překryv → nic se nezmění
    assert (len(p.state.t), p.rt("s2").src.offset_s, p.state.c_d) == before
    p.set_time_grid(TimeGrid(period=5.0))
    assert p.state.grid.Ts == 5.0 and p.state.ts_user == 5.0
    with pytest.raises(ValueError):
        p.update_source("s2", timezone="Mars/Olympus")
    assert p.rt("s2").src.timezone == "Europe/Prague"


def test_source_with_own_sampling_without_time_column():
    t = np.arange(0, 200.0)
    a = pd.DataFrame({"Time": t, "X.PV": np.sin(t / 20), "X.OUT": (t // 20) % 2 * 10.0})
    b = pd.DataFrame({"FI": np.arange(40.0), "FJ": np.ones(40)})                                # bez času, vzorek každých 5 s
    p = Project()
    p.add_source("a.csv", a.to_csv(index=False).encode())
    p.add_source("b.csv", b.to_csv(index=False).encode(), sampling_s=5.0, options={"c_time": "#row"})
    spec = p.loop_spec(0)
    spec.roles.dv = [SourceRef("s2", "FI")]
    p.set_loop_spec(0, spec)
    np.testing.assert_allclose(p.state.grid.dists[0], np.interp(p.state.t, np.arange(40.0) * 5.0, np.arange(40.0)))


def test_mapping_validation_and_column_in_more_loops():
    p, *_ = _two_sources()
    spec = p.loop_spec(0)
    with pytest.raises(ValueError):
        p.set_loop_spec(0, LoopSpec(roles=Roles(pv=spec.roles.pv)))            # chybí MV
    with pytest.raises(ValueError):
        p.set_loop_spec(0, LoopSpec(roles=Roles(pv=SourceRef("s1", "nope"), mv=spec.roles.mv)))
    with pytest.raises(ValueError):
        p.set_loop_spec(0, LoopSpec(roles=Roles(pv=SourceRef("sX", "a"), mv=spec.roles.mv)))
    new = LoopSpec(tag="L2", description="druhá", roles=Roles(pv=spec.roles.pv, mv=spec.roles.mv,   # stejné sloupce
                   dv=[SourceRef("s2", "FI100.Pritok")]), norm_pv=(0.0, 50.0), norm_mv=(0.0, 100.0))
    p.add_loop_from_spec(new)
    assert len(p.loops) == 2 and p.active == 1 and p.state.src_ids == ["s1", "s2"]
    got = p.loop_spec(1)
    assert got.tag == "L2" and got.description == "druhá" and got.norm_pv == (0.0, 50.0)
    assert p.loop_spec(0).roles.pv == got.roles.pv
    got.cascade_to = 0
    p.set_loop_spec(1, got)
    assert p.loop_spec(1).cascade_to == 0
    got.cascade_to = 1
    with pytest.raises(ValueError):
        p.set_loop_spec(1, got)


def test_remove_source_only_when_unused():
    p, *_ = _two_sources()
    spec = p.loop_spec(0)
    spec.roles.dv = [SourceRef("s2", "FI100.Pritok")]
    p.set_loop_spec(0, spec)
    with pytest.raises(ValueError):
        p.remove_source("s2")
    spec.roles.dv = []
    p.set_loop_spec(0, spec)
    p.remove_source("s2")
    assert [r.id for r in p.sources] == ["s1"] and p.state.src_ids == ["s1"]


def test_multi_source_project_roundtrip():
    p, *_ = _two_sources()
    spec = p.loop_spec(0)
    spec.roles.dv = [SourceRef("s2", "FI100.Pritok")]
    p.set_loop_spec(0, spec)
    p.set_time_grid(TimeGrid(period=2.0, mode="overlap", max_gap=30.0))
    p.update_source("s2", offset_s=15.0)
    d = json.loads(prj.serialize_project(p.to_project(True)))
    assert [s["id"] for s in d["sources"]] == ["s1", "s2"] and d["sources"][1]["timezone"] == "Europe/Prague"
    assert d["sources"][1]["offset_s"] == 15.0 and d["time_grid"]["period"] == 2.0
    q = Project()
    q.apply_project(prj.load_project(json.dumps(d)))
    assert q.state.src_ids == ["s1", "s2"] and q.state.c_d == ["FI100.Pritok"] and q.time_grid.max_gap == 30.0
    assert q.state.grid.Ts == 2.0 and len(q.state.t) == len(p.state.t)
    np.testing.assert_allclose(q.state.grid.dists[0], p.state.grid.dists[0], rtol=1e-5, atol=1e-6)
    assert q.rt("s2").src.offset_s == 15.0


def test_clashing_column_names_get_source_suffix():
    t = np.arange(300.0)
    mk = lambda c: pd.DataFrame({"Time": t, c: np.sin(t / 30), "OUT": t % 11}).to_csv(index=False).encode()   # noqa: E731
    p = Project()
    p.add_source("one.csv", mk("PV"))
    p.add_source("two.csv", mk("PV"))
    spec = p.loop_spec(0)
    spec.roles.dv = [SourceRef("s2", "PV")]
    p.set_loop_spec(0, spec)
    assert set(p.state.c_d) == {"PV (two.csv)"} and p.state.c_pv == "PV (one.csv)"


def test_suggest_and_import_through_project():
    t = np.arange(400.0)
    df = pd.DataFrame({"Time": t, "TIC1.PV": t % 9, "TIC1.OUT": t % 5, "TIC1.SP": 3.0 + 0 * t, "FIC2.PV": t % 4,
                       "FIC2.OUT": t % 6})
    p = Project()
    p.add_source("x.csv", df.to_csv(index=False).encode())
    from pidtools.app.domain import suggest as sg
    out, unused = sg.suggest(p.column_refs())
    assert [s.tag for s in out] == ["TIC1", "FIC2"] and not unused
    p.add_loop_from_spec(out[1].to_spec())
    assert p.state.get("loop_tag") == "FIC2" and p.state.c_pv == "FIC2.PV"
    loops, warns = sg.parse_mapping_csv("loop,role,column\nTIC1,PV,TIC1.PV\nTIC1,MV,TIC1.OUT\n", p.source_tuples())
    assert loops[0].complete and not warns


# ---- podklady pro Trendy
def test_trend_decimation_keeps_extremes():
    t = np.arange(100000.0)
    v = np.sin(t / 500)
    v[54321] = 9.0
    v[77777] = -9.0
    tt, vv = trend.decimate(t, v, n=500)
    assert len(tt) <= 1000 + 2 and vv.max() == 9.0 and vv.min() == -9.0 and np.all(np.diff(tt) > 0)
    ta, va = trend.decimate(t, v, 1000, 2000, n=500)
    assert ta[0] >= 1000 and ta[-1] <= 2000
    ts, vs = trend.decimate(t[:100], v[:100], n=500)
    assert len(ts) == 100                                                    # krátká řada beze změny


def test_trend_stats_and_value_at():
    t = np.arange(10.0)
    v = np.array([1, 2, np.nan, 4, 5, 6, 7, 8, 9, 10.0])
    s = trend.stats(t, v, 0, 9)
    assert s["count"] == 9 and s["missing"] == 1 and s["min"] == 1 and s["max"] == 10 and s["mean"] == pytest.approx(5.777, abs=1e-3)
    assert trend.stats(t, v, 100, 200)["count"] == 0
    assert trend.value_at(t, v, 4.5) == pytest.approx(5.5) and trend.value_at(t, v, -1) is None
    assert trend.value_at(t, v, 5.0) == 6.0 and trend.value_at(t, v, 100) is None
    g = np.r_[np.arange(5.0), np.arange(50.0, 55.0)]
    assert trend.value_at(g, g, 20.0) is None                                # uvnitř mezery
    assert trend.value_at(g, g, 20.0, max_gap=100.0) == pytest.approx(20.0)
