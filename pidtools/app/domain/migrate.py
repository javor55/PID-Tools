"""
Migrace souboru projektu (`.pidproj`) po verzích: v1 → v2 → v3. Každý krok je čistá funkce `dict → dict`
(vstup se nemění) a má test na vzorovém souboru staré verze (tests/data/project_v1.json, tests/golden/tic001.json,
tests/test_domain_project.py). Další verze formátu = jeden krok navíc v `STEPS`.

  v1 → v2  nastavení smyčky (`state`): P ve zpětné vazbě ano/ne → PropFacSP (app.project.migrate_state)
  v2 → v3  jeden soubor s daty = jeden zdroj `s1` (data v projektu jako `sources[0].data`), mapování sloupců
           `map` smyček → `spec.roles`, rozsahy NormPV / NormMV ze `state`; formát nese `format` a `version`
"""
from ...i18n import T
from .. import project as prj
from .model import FORMAT, VERSION, DataRef, LoopSpec, Roles, Source, SourceRef, TimeGrid
from .registry import kind_for

DASH = "—"


def _v1_to_v2(proj):
    out = dict(proj)
    out["state"] = prj.migrate_state(proj.get("state", {}))
    if proj.get("loops"):
        out["loops"] = [{**r, "state": prj.migrate_state(r["state"])} if "state" in r else r for r in proj["loops"]]
    out["version"] = 2
    return out


def _ref(sid, col):
    return None if col in (None, "", DASH) else SourceRef(sid, str(col))


def _spec(rec, sid):
    mp, st = rec.get("map") or {}, rec.get("state") or {}

    def rng(lo, hi):
        a, b = st.get(lo), st.get(hi)
        return (float(a), float(b)) if isinstance(a, (int, float)) and isinstance(b, (int, float)) else None
    roles = Roles(pv=_ref(sid, mp.get("c_pv")), sp=_ref(sid, mp.get("c_sp")), mv=_ref(sid, mp.get("c_mv")),
                  pos=_ref(sid, mp.get("c_pos")), dv=[r for r in (_ref(sid, c) for c in mp.get("c_d") or []) if r])
    return LoopSpec(tag=str(rec.get("tag") or st.get("loop_tag") or ""), roles=roles,
                    norm_pv=rng("pv_lo", "pv_hi"), norm_mv=rng("mv_lo", "mv_hi")).to_dict()


def _v2_to_v3(proj):
    out = dict(proj)
    fname = str(proj.get("fname") or "")
    name = fname.split("|")[0] or "data"
    data = out.pop("data", None)
    src = Source(id="s1", name=name, kind=kind_for(name), options=dict(layout="wide") if data else {},
                 data=DataRef(kind="embedded" if data else "file", name=name,
                              rows=len(next(iter(data["cols"].values()))) if data and data.get("cols") else 0))
    sd = src.to_dict()
    if data:
        sd["data"] = data
    out["sources"] = [sd]
    out["time_grid"] = TimeGrid().to_dict()
    if proj.get("loops"):
        out["loops"] = [{**r, "spec": _spec({**proj, **r}, "s1")} for r in proj["loops"]]
    out["spec"] = _spec(proj, "s1")
    out["format"], out["version"] = FORMAT, 3
    return out


STEPS = {1: _v1_to_v2, 2: _v2_to_v3}


def version_of(proj):
    return int(proj.get("version") or 1)


def migrate_project(proj):
    """Projekt libovolné známé verze → aktuální verze (slovník); novější verze než aplikace → ValueError."""
    if not isinstance(proj, dict):
        raise ValueError(T("err_project_format", what="project"))
    v = version_of(proj)
    if v > VERSION:
        raise ValueError(T("err_project_newer", v=v))
    while v < VERSION:
        proj = STEPS[v](proj)
        v = version_of(proj)
    return proj
