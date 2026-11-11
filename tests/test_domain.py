"""Doménový model (app.domain): serializace, registr zdrojů, společná časová mřížka, návrh smyček, migrace."""
import json
import os

import numpy as np
import pytest

from pidtools.app import domain
from pidtools.app.domain import registry as sreg
from pidtools.app.domain import suggest as sg
from pidtools.app.domain import timegrid as tgm
from pidtools.app.domain.model import LoopSpec, Roles, Source, SourceRef, TimeGrid

HERE = os.path.dirname(os.path.abspath(__file__))


# ---- model
def test_project_dict_roundtrip():
    p = domain.Project(
        sources=[Source("s1", "a.csv", "csv", {"layout": "wide", "unit": "s"}, "Europe/Prague", 3600.0, 2.0),
                 Source("s2", "b.xlsx", "xlsx")],
        loops=[LoopSpec("TIC101", "Reactor", Roles(pv=SourceRef("s1", "PV"), mv=SourceRef("s2", "a:b"),
                                                  dv=[SourceRef("s2", "FI")]), (0.0, 150.0), (0.0, 100.0), 1),
               LoopSpec("TIC102")],
        active=1, time_grid=TimeGrid("union", 5.0, 60.0))
    d = json.loads(json.dumps(p.to_dict()))
    assert d["format"] == "pidtools.project" and d["version"] == domain.VERSION
    assert d["active"] == 2                                      # v souboru od 1
    back = domain.Project.from_dict(d)
    assert back == p
    assert json.dumps(back.to_dict(), sort_keys=True) == json.dumps(d, sort_keys=True)


def test_project_rejects_bad_input():
    good = domain.Project(sources=[Source("s1", "a")], loops=[LoopSpec()]).to_dict()
    for bad in (dict(good, format="other"), dict(good, version=99), dict(good, time_grid={"mode": "x"}),
                dict(good, sources=[{"id": "s1"}, {"id": "s1"}]), dict(good, time_grid={"period": -1})):
        with pytest.raises(ValueError):
            domain.Project.from_dict(bad)


def test_source_ref_parse():
    r = SourceRef.parse("s2:PV:raw")
    assert (r.source_id, r.column) == ("s2", "PV:raw") and str(r) == "s2:PV:raw"
    with pytest.raises(ValueError):
        SourceRef.parse("nocolon")


def test_column_in_more_loops():
    r = SourceRef("s1", "PV")
    p = domain.Project(sources=[Source("s1", "a")], loops=[LoopSpec(roles=Roles(pv=r)), LoopSpec(roles=Roles(dv=[r]))])
    assert domain.Project.from_dict(p.to_dict()).loops[1].roles.dv == [r]


# ---- registr zdrojů
@pytest.mark.parametrize("kind", sreg.SOURCES.ids())
def test_every_source_has_description_params_and_sample(kind):
    from pidtools import i18n
    e = sreg.SOURCES.get(kind)
    for lang in i18n.LANGS:
        assert e.desc in i18n.TEXTS[lang]
        assert all(v["desc"] in i18n.TEXTS[lang] for v in e.params.values())
    df = sreg.load(kind, **e.meta["sample"]())
    assert len(df) >= 5 and df.shape[1] >= 2


def test_source_kind_and_errors():
    assert [sreg.kind_for(n) for n in ("a.CSV", "b.xlsx", "c.xls", "d.txt", "e.unknown")] == \
        ["csv", "xlsx", "xlsx", "txt", "csv"]
    with pytest.raises(ValueError):
        sreg.load("nope", "x")
    with pytest.raises(ValueError):
        sreg.load("csv", "x.csv")
    assert [d["id"] for d in sreg.SOURCES.describe()] == ["csv", "txt", "xlsx", "opc"]


# ---- společná časová mřížka
def _series(t0, t1, dt, f):
    t = np.arange(t0, t1 + 1e-9, dt)
    return t, f(t)


def test_grid_overlap_different_rates_and_offsets():
    a = _series(0, 100, 1.0, lambda t: t)                  # 1 s
    b = _series(20, 140, 10.0, lambda t: 2 * t)            # 10 s, začíná později
    g = tgm.common_grid([a, b])
    assert g.Ts == 1.0                                     # nejjemnější perioda
    assert g.t[0] == 20 and g.t[-1] == 100                 # společný úsek
    np.testing.assert_allclose(g.values[0], g.t)
    np.testing.assert_allclose(g.values[1], 2 * g.t)       # lineární interpolace pomalejšího zdroje
    assert not any(np.isnan(v).any() for v in g.values)


def test_grid_union_marks_outside_as_nan():
    a = _series(0, 50, 1.0, lambda t: t)
    b = _series(30, 90, 1.0, lambda t: t)
    g = tgm.common_grid([a, b], TimeGrid(mode="union"))
    assert g.t[0] == 0 and g.t[-1] == 90
    assert np.isnan(g.values[1][g.t < 30]).all() and np.isnan(g.values[0][g.t > 50]).all()
    assert np.isfinite(g.values[0][g.t <= 50]).all()


def test_grid_manual_period():
    a = _series(0, 100, 1.0, lambda t: t)
    g = tgm.common_grid([a], TimeGrid(period=5.0))
    assert g.Ts == 5.0 and len(g.t) == 21
    assert tgm.choose_period([a], TimeGrid()) == 1.0
    assert tgm.choose_period([a], TimeGrid(), own=[2.0]) == 2.0           # vlastní vzorkování zdroje


def test_grid_gap_is_not_interpolated():
    t = np.r_[np.arange(0, 20.0), np.arange(60, 100.0)]    # mezera 19 → 60
    g = tgm.common_grid([(t, t * 1.0)])
    gap = (g.t > 19) & (g.t < 60)
    assert np.isnan(g.values[0][gap]).all() and np.isfinite(g.values[0][~gap]).all()
    assert g.gaps[0] == [(19.0, 60.0)]
    tol = tgm.common_grid([(t, t * 1.0)], TimeGrid(max_gap=100.0))        # práh vyšší než mezera → interpoluje se
    assert np.isfinite(tol.values[0]).all()
    short = tgm.common_grid([(t, t * 1.0)], TimeGrid(gap_factor=50.0))
    assert np.isfinite(short.values[0]).all()


def test_grid_zoh_holds_step():
    mv = (np.arange(0, 100.0, 10.0), np.r_[np.zeros(5), np.ones(5)] * 50.0)
    pv = _series(0, 90, 1.0, lambda t: t)
    g = tgm.common_grid([pv, mv], zoh={1})
    assert g.values[1][g.t == 39][0] == 0.0 and g.values[1][g.t == 50][0] == 50.0     # schod, ne rampa


def test_grid_errors_and_overlap():
    a, b = _series(0, 10, 1.0, lambda t: t), _series(50, 60, 1.0, lambda t: t)
    with pytest.raises(ValueError):
        tgm.common_grid([a, b])                            # nepřekrývají se
    assert tgm.overlap([a, b]) is None
    assert tgm.overlap([a, _series(5, 30, 1.0, lambda t: t)]) == (5.0, 10.0)
    with pytest.raises(ValueError):
        tgm.common_grid([(np.array([1.0]), np.array([1.0]))])


def test_grid_large_record_is_coarsened():
    t = np.arange(0, 100000.0)
    g = tgm.common_grid([(t, t)])
    assert len(g.t) <= tgm.MAX_POINTS + 1 and g.Ts > 1.0


# ---- návrh smyček
def _cols(*names, sid="s1"):
    return [SourceRef(sid, n) for n in names]


def _roles(sg_):
    return {k: getattr(sg_.roles, k).column if getattr(sg_.roles, k) else None for k in ("pv", "sp", "mv", "pos", "mode")}


def test_suggest_dot_suffix():
    out, unused = sg.suggest(_cols("TIC101.PV", "TIC101.SP", "TIC101.OUT", "FIC200.PV", "FIC200.MV", "FIC200.SP",
                                   "Ambient"))
    assert [s.tag for s in out] == ["TIC101", "FIC200"]
    assert _roles(out[0]) == dict(pv="TIC101.PV", sp="TIC101.SP", mv="TIC101.OUT", pos=None, mode=None)
    assert _roles(out[1])["mv"] == "FIC200.MV" and all(s.complete for s in out)
    assert [r.column for r in unused] == ["Ambient"]


def test_suggest_pcs7_style():
    out, _ = sg.suggest(_cols("TIC101/PV_Out", "TIC101/SP_Out", "TIC101/MV", "LIC5/PV_Out", "LIC5/LMN", "LIC5/Mode"))
    assert [s.tag for s in out] == ["TIC101", "LIC5"] and {s.via for s in out} == {"pcs7"}
    assert _roles(out[0]) == dict(pv="TIC101/PV_Out", sp="TIC101/SP_Out", mv="TIC101/MV", pos=None, mode=None)
    assert _roles(out[1])["mv"] == "LIC5/LMN" and _roles(out[1])["mode"] == "LIC5/Mode"


def test_suggest_deltav_style():
    out, _ = sg.suggest(_cols("TIC101/PID1/PV.CV", "TIC101/PID1/SP.CV", "TIC101/PID1/OUT.CV", "TIC101/PID1/BKCAL_IN.CV"))
    assert len(out) == 1 and out[0].tag == "TIC101" and out[0].via == "deltav"
    assert _roles(out[0]) == dict(pv="TIC101/PID1/PV.CV", sp="TIC101/PID1/SP.CV", mv="TIC101/PID1/OUT.CV",
                                  pos="TIC101/PID1/BKCAL_IN.CV", mode=None)


def test_suggest_keeps_sources_and_falls_back_to_guess():
    refs = _cols("A.PV", sid="s1") + _cols("A.SP", "A.OUT", sid="s2")
    out, _ = sg.suggest(refs)
    assert [r.source_id for r in out[0].roles.refs()] == ["s1", "s2", "s2"]
    out, unused = sg.suggest(_cols("Teplota_mereni", "Ventil_vystup", "Zadana_hodnota", "Cas_x"))
    assert len(out) == 1 and out[0].via == "guess" and out[0].roles.pv and out[0].roles.mv
    assert sg.suggest([]) == ([], [])


def test_parse_name_cases():
    assert sg.parse_name("TIC101.PV") == ("TIC101", "pv", "dot")
    assert sg.parse_name("Plant/Area/TIC101/SP_Out") == ("TIC101", "sp", "pcs7")
    assert sg.parse_name("Temperature") is None


SOURCES = [("s1", "plant.csv", ["TIC101.PV", "TIC101.OUT", "FI.DV", "TIC101.SP"]), ("s2", "b.xlsx", ["X"])]


def test_mapping_csv_import():
    text = ("loop;role;source;column;description\n"
            "TIC101;PV;s1;TIC101.PV;Reactor temperature\nTIC101;MV;plant.csv;TIC101.OUT;\nTIC101;SP;s1;TIC101.SP;\n"
            "TIC101;DV;s1;FI.DV;\nTIC101;dv;s2;X;\nTIC102;PV;s1;MISSING;\nTIC102;XX;s1;TIC101.PV;\nTIC101;PV;s1;FI.DV;\n"
            "TIC103;PV;nosrc;TIC101.PV;\n")
    loops, warns = sg.parse_mapping_csv(text.encode("utf-8"), SOURCES)
    assert [lp.tag for lp in loops] == ["TIC101"]
    lp = loops[0]
    assert lp.description == "Reactor temperature" and str(lp.roles.mv) == "s1:TIC101.OUT"
    assert [str(r) for r in lp.roles.dv] == ["s1:FI.DV", "s2:X"] and lp.complete
    assert len(warns) == 4                                                  # sloupec, role, duplicitní PV, zdroj


def test_mapping_csv_single_source_and_comma_header_aliases():
    text = "Smyčka,Role,Sloupec\nA,PV,TIC101.PV\nA,MV,TIC101.OUT\n"
    loops, warns = sg.parse_mapping_csv(text, [("s1", "x", ["TIC101.PV", "TIC101.OUT"])])
    assert not warns and loops[0].complete
    with pytest.raises(ValueError):
        sg.parse_mapping_csv("a,b\n1,2\n", SOURCES)


# ---- migrace
def _load(path):
    with open(os.path.join(HERE, path), encoding="utf-8") as f:
        return json.load(f)


def test_migrate_golden_project_v2():
    p = domain.migrate_project(_load("golden/tic001.json"))
    assert p["format"] == "pidtools.project" and p["version"] == 3
    assert len(p["sources"]) == 1 and p["sources"][0]["id"] == "s1" and p["sources"][0]["data"]["cols"]
    assert p["sources"][0]["kind"] == "csv" and p["sources"][0]["data_ref"]["kind"] == "embedded"
    assert "data" not in p
    spec = LoopSpec.from_dict(p["spec"])
    assert str(spec.roles.pv) == "s1:TIC001_PV" and spec.tag == "TIC001"
    pj = domain.Project.from_dict(p)
    assert pj.sources[0].name == "TIC001.csv" and len(pj.loops) == 1


def test_migrate_v1_applies_state_migration():
    raw = _load("data/project_v1.json")
    assert raw["version"] == 1
    p = domain.migrate_project(raw)
    assert p["version"] == 3 and raw["version"] == 1                      # vstup se nemění
    assert p["sources"][0]["data_ref"]["kind"] in ("file", "embedded") and p["sources"][0]["name"] == "example4.xlsx"
    assert p["sources"][0]["kind"] == "xlsx"
    if "pfb" in raw["state"]:
        assert "propfac" in p["state"]


def test_migrate_multi_loop_and_idempotent_and_newer():
    rec = lambda tag, pv: dict(tag=tag, state={}, map=dict(c_pv=pv, c_mv="MV", c_sp="—", c_d=["D"], c_pos="—"))
    proj = dict(version=2, fname="x.csv", **rec("A", "PV1"), loops=[rec("A", "PV1"), rec("B", "PV2")], active=2,
                data={"cols": {"t_s": [0, 1, 2], "PV1": [1, 2, 3], "PV2": [1, 2, 3], "MV": [1, 1, 1], "D": [0, 0, 0]}})
    p = domain.migrate_project(proj)
    pj = domain.Project.from_dict(p)
    assert [lp.tag for lp in pj.loops] == ["A", "B"] and pj.active == 1
    assert str(pj.loops[1].roles.pv) == "s1:PV2" and [str(r) for r in pj.loops[1].roles.dv] == ["s1:D"]
    assert domain.migrate_project(p) is p                                  # už aktuální
    with pytest.raises(ValueError):
        domain.migrate_project(dict(version=99))
