"""
Zlaté případy regulátoru (E1): dnešní výstupy PIDConL, pidconl_sim_full, kaskády, LiveLoop, návrhu ladění,
robustnosti a živého enginu v JS se nesmí změnit (tolerance 1e-9). Přegenerování po vědomé změně:
python tools/golden_controller.py --update
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import golden_controller as gc  # noqa: E402

_cache = {}


def _ref():
    if "ref" not in _cache:
        assert os.path.exists(gc.GOLDEN), "chybí tests/golden/controller_golden.npz – python tools/golden_controller.py --update"
        _cache["ref"] = gc.load()
    return _cache["ref"]


def _check(prefix, new):
    ref = {k: v for k, v in _ref().items() if k.startswith(prefix)}
    assert ref, f"v uložených výsledcích nic nezačíná {prefix}"
    diffs, worst = gc.compare(ref, new)
    assert not diffs, "\n".join(diffs[:30])
    return worst


@pytest.mark.parametrize("cfg", list(gc.CONFIGS))
def test_golden_steps(cfg):
    """PIDConL krok po kroku (track, set_tuning, FF, všechny volby) na třech procesech."""
    new = {}
    for pn in gc.PROCS:
        for k, v in gc._run_steps(gc.CONFIGS[cfg], pn).items():
            new[f"steps/{cfg}/{pn}/{k}"] = v
    _check(f"steps/{cfg}/", new)


def test_golden_sims():
    """pidconl_sim_full (ukázková data, 3 syntetické smyčky s DV a FF) a kaskáda."""
    _check("sim/", gc._sims())


def test_golden_live_python():
    _check("live_py/", gc._live_py())


@pytest.mark.skipif(gc.NODE is None, reason="Node.js není k dispozici")
def test_golden_live_js():
    """Živý engine v prohlížeči (live_engine.js přes Node) – záznam kroků."""
    _check("live_js/", gc._live_js())


def test_golden_tuning_and_robustness():
    """Návrh ladění (SIMC, Lambda, AMIGO), robustnost sad, scénář a frekvenční charakteristika (app/workspace)."""
    _check("tuning/", gc._tuning())


def test_golden_complete():
    """Uložené klíče odpovídají případům (žádné staré ani chybějící)."""
    keys = set(_ref())
    for cfg in gc.CONFIGS:
        for pn in gc.PROCS:
            assert f"steps/{cfg}/{pn}/u" in keys
