"""Živá simulace v prohlížeči (pidtools/ui/static/live_engine.js) se musí chovat stejně jako Python LiveLoop."""
import json
import os
import shutil
import subprocess

import numpy as np
import pytest

from pidtools.core import LiveLoop

ENGINE = os.path.join(os.path.dirname(__file__), "..", "pidtools", "ui", "static", "live_engine.js")
NODE = shutil.which("node")

CASES = {
    "P0D": ("P0D", [1.5, 8.0]),
    "P1D": ("P1D", [1.2, 40.0, 6.0]),
    "P2D": ("P2D", [-0.8, 30.0, 10.0, 4.0]),
    "I0D": ("I0D", [0.02, 5.0]),
    "I1D": ("I1D", [0.015, 20.0, 3.0]),
}
CTRL = dict(Gain=1.1, TI=35.0, TD=4.0, DiffGain=5.0, SampleTime=1.0, PropFacSP=0.6, DiffFbk=True,
            DeadBand=0.3, DbMode="spojité", MV_Lo=5.0, MV_Hi=95.0, PVFilt=2.0, MVRate=2.0, SPRate=0.5)
PLANT = dict(Stic=1.5, SticJ=1.0, ValveChar=[0.6, 0.8, 1.0, 1.1, 1.2, 1.2, 1.1, 1.0, 0.9, 0.8])


def _scenario(n):
    """Kroky: (sp, auto, u_man, d, nové ladění nebo None)."""
    steps = []
    for k in range(n):
        sp = 50.0 if k < 50 else 58.0
        auto = not (300 <= k < 400)               # úsek v ručním režimu (bezrázový návrat)
        d = 4.0 if k >= 600 else 0.0
        tune = dict(Gain=0.7, TI=60.0, TD=0.0) if k == 800 else None
        steps.append((sp, auto, 62.0, d, tune))
    return steps


def _python(code, p, ctrl, plant, h, steps):
    loop = LiveLoop(code, p, ctrl, h, 50.0, 50.0, plant)
    out = []
    for sp, auto, um, d, tune in steps:
        if tune:
            loop.set_tuning(tune)
        loop.advance(h, sp, auto, um, d)
        out.append([loop.hist[k][-1] for k in ("t", "SP", "PV", "MV", "V")])
    return np.array(out)


def _js(code, p, ctrl, plant, h, steps):
    script = f"""
const E = require({json.dumps(os.path.abspath(ENGINE))});
const cfg = {json.dumps(dict(code=code, p=p, ctrl=ctrl, plant=plant, h=h, steps=steps))};
const L = new E.LiveLoop(cfg.code, cfg.p, cfg.ctrl, cfg.h, 50.0, 50.0, cfg.plant);
const out = [];
for (const [sp, auto, um, d, tune] of cfg.steps) {{
  if (tune) L.setTuning(tune);
  out.push(L.tick(sp, auto, um, d));
}}
console.log(JSON.stringify(out));
"""
    r = subprocess.run([NODE, "-e", script], capture_output=True, text=True, timeout=60, check=True)
    return np.array(json.loads(r.stdout))


@pytest.mark.skipif(NODE is None, reason="Node.js není k dispozici")
@pytest.mark.parametrize("case", list(CASES))
@pytest.mark.parametrize("variant", ["plain", "full"])
def test_js_engine_matches_python(case, variant):
    code, p = CASES[case]
    ctrl = dict(CTRL) if variant == "full" else dict(Gain=1.0, TI=30.0, TD=0.0, SampleTime=1.0, MV_Lo=0.0,
                                                      MV_Hi=100.0)
    if code in ("I0D", "I1D"):
        ctrl.update(Gain=4.0, TI=200.0)
    plant = PLANT if variant == "full" else {}
    h = 0.25
    steps = _scenario(1200)
    py, js = _python(code, p, ctrl, plant, h, steps), _js(code, p, ctrl, plant, h, steps)
    assert py.shape == js.shape
    assert np.max(np.abs(py - js)) < 1e-6


@pytest.mark.skipif(NODE is None, reason="Node.js není k dispozici")
@pytest.mark.parametrize("case", list(CASES))
def test_js_plant_change_is_bumpless(case):
    """Změna procesu za běhu (násobky zesílení, konstant, zpoždění) nesmí skokově pohnout PV.
    Výjimkou je P0D (čisté zesílení bez setrvačnosti) – tam se změna zesílení projeví hned, jak to fyzikálně odpovídá."""
    code, p = CASES[case]
    ctrl = dict(Gain=0.5 if code[0] == "P" else 3.0, TI=60.0, TD=0.0, SampleTime=1.0, MV_Lo=0.0, MV_Hi=100.0)
    script = f"""
const E = require({json.dumps(os.path.abspath(ENGINE))});
const p = {json.dumps(p)}, code = {json.dumps(code)};
const L = new E.LiveLoop(code, p, {json.dumps(ctrl)}, 0.25, 50, 50, {{}});
for (let k = 0; k < 800; k++) L.tick(k < 20 ? 50 : 56, true, 50, 0);
const before = L.tick(56, true, 50, 0)[2];
const q = p.slice(); q[0] *= 1.4; if (q.length > 2) q[1] *= 1.6; q[q.length - 1] *= 1.5;
L.setPlant(q);
const after = L.tick(56, true, 50, 0)[2];
const out = L.tick(56, true, 50, 0, 3.0)[2];       // porucha +3 % přímo na PV
console.log(JSON.stringify([before, after, out]));
"""
    before, after, out = json.loads(subprocess.run([NODE, "-e", script], capture_output=True, text=True, timeout=60,
                                                   check=True).stdout)
    if code == "P0D":
        assert after - 50 == pytest.approx((before - 50) * 1.4, rel=0.05)
    else:
        assert abs(after - before) < 0.3
    assert out - after == pytest.approx(3.0, abs=0.3)
