"""
Zlaté případy (docs/cs/milniky.md, M1): výsledky aplikace na pevné sadě dat se nesmí změnit bez záměru.
Po vědomé změně výpočtů: python tools/golden.py --update (a změnu výsledků popsat v PR).
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import golden  # noqa: E402


@pytest.mark.parametrize("name", list(golden.CASES))
def test_golden(name):
    assert os.path.exists(golden.path_of(name)), f"chybí {name}.out.json – python tools/golden.py --update {name}"
    diffs = golden.compare(golden.load(name), golden.run_case(name))
    assert not diffs, "\n".join(f"{p}: uloženo {a!r}, nyní {b!r}" for p, a, b in diffs[:40])


def test_golden_cases_complete():
    """Každý uložený výsledek patří k případu (po přejmenování nezůstávají staré soubory)."""
    saved = {f[:-len(".out.json")] for f in os.listdir(golden.GOLDEN) if f.endswith(".out.json")}
    assert saved == set(golden.CASES)


def test_anonymised_project():
    """Reálný projekt v sadě je anonymizovaný (jen TIC001 / TIC002, bez názvu souboru a data pořízení)."""
    txt = open(os.path.join(golden.GOLDEN, "tic001.json"), encoding="utf-8").read()
    assert "TIC001" in txt and "TIC002" in txt
    for bad in ("TT363", "TICA89", "destil"):
        assert bad.lower() not in txt.lower()


@pytest.mark.parametrize("src", ["golden/tic001.json", "data/project_v1.json"])
def test_project_roundtrip(src):
    """Projekt (i starý formát v1) → pracovní stav → projekt → pracovní stav → projekt: obsah se nezmění."""
    import json

    from pidtools.app import project as prj
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), src), encoding="utf-8") as f:
        proj = prj.load_project(f.read())
    s1 = golden._state()
    s1.apply_project(proj)
    p1 = json.loads(prj.serialize_project(s1.to_project(include_data=True)))
    s2 = golden._state()
    s2.apply_project(p1)
    p2 = json.loads(prj.serialize_project(s2.to_project(include_data=True)))
    for p in (p1, p2):
        p.pop("created", None)
    assert golden.compare(p1, p2, rtol=1e-9, atol=1e-12) == []
