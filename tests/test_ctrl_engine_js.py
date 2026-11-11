"""Shoda obecného regulátoru: Python (core.controller) × JS (ui/static/ctrl_engine.js), stejný profil, ~50 signálů."""
import copy
import json
import os
import shutil
import subprocess
import sys

import numpy as np
import pytest

from pidtools.controllers import load_preset
from pidtools.core.controller import Controller

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import golden_controller as gc  # noqa: E402

ENGINE = os.path.join(os.path.dirname(__file__), "..", "pidtools", "ui", "static", "ctrl_engine.js")
NODE = shutil.which("node")
TOL = 1e-9
BASE = dict(Gain=0.9, TI=30.0, TD=4.0, DiffGain=5.0, SampleTime=1.0, MV_Lo=0.0, MV_Hi=100.0)


def _profile(**over):
    """Varianta dodaného profilu: změny `structure` (dict) a přidané / nahrazené parametry."""
    p = copy.deepcopy(load_preset("pcs7_pidconl"))
    p["structure"].update(over.get("structure", {}))
    keep = [x for x in p["params"] if x["key"] not in over.get("drop", ())]
    p["params"] = keep + over.get("add", [])
    return p


VARIANTS = {
    "pcs7": (_profile(), BASE),
    "series": (_profile(structure={"form": "series"}), BASE),
    "parallel": (_profile(structure={"form": "parallel"}, drop=("Gain", "TI", "TD"),
                          add=[{"key": "Kp", "role": "Kp", "required": True},
                               {"key": "Ki", "role": "Ki", "required": True, "nullable": True},
                               {"key": "Kd", "role": "Kd", "required": True}]),
                 dict(BASE, Kp=0.9, Ki=0.03, Kd=3.6)),
    "backcalc": (_profile(structure={"antiwindup": "back_calculation"}, add=[{"key": "Tt", "role": "Tt", "default": 10.0}]),
                 dict(BASE, MV_Lo=40.0, MV_Hi=60.0)),
    "aw_none": (_profile(structure={"antiwindup": "none"}), dict(BASE, MV_Lo=40.0, MV_Hi=60.0)),
    "d_fixed": (_profile(structure={"d": {"source": "error", "filter": "fixed"}},
                         add=[{"key": "Tf", "role": "Tf", "default": 2.5}]), BASE),
    "d_nofilter": (_profile(structure={"d": {"source": "pv", "filter": "none"}}), dict(BASE, PropFacSP=0.5)),
    "no_pvfilter": (_profile(structure={"pv": {"filter": "none"}}), dict(BASE, PVFilt=3.0)),
}


def _signals(seed, n=500):
    """Vstupní signály: SP s kroky, PV šum + trend + skoky, FF, ruční úseky a změny ladění."""
    rng = np.random.default_rng(seed)
    k = np.arange(n)
    sp = 50 + 8 * np.sign(np.sin(k / (40 + 10 * (seed % 5)))) + rng.normal(0, 0.05, n)
    y = 50 + 6 * np.sin(k / (15 + seed % 7)) + np.cumsum(rng.normal(0, 0.1, n)) + 10 * (k > 300) * (seed % 2)
    ff = 2 * np.sin(k / 33.0) * (seed % 3 == 0)
    man = (k >= 200) & (k < 240 + 3 * seed)
    um = 55 + 0.03 * (k - 200)
    tune = {150: (0.6, 50.0, 1.0), 250: (1.4, None, 3.0), 330: (0.8, 20.0, 0.0)}
    return [[float(sp[i]), float(y[i]), float(ff[i]), bool(man[i]), float(um[i]), tune.get(i)] for i in range(n)]


def _ctrl_for(seed):
    """Náhodná konfigurace bloku (všechny volby PCS 7 podle semínka)."""
    r = np.random.default_rng(1000 + seed)
    c = dict(Gain=float(r.choice([-1.0, 1.0]) * r.uniform(0.3, 2.0)), TI=float(r.uniform(10, 80)),
             TD=float(r.choice([0.0, r.uniform(1, 8)])), DiffGain=float(r.uniform(2, 10)),
             SampleTime=float(r.choice([0.5, 1.0, 2.0])), MV_Lo=float(r.uniform(0, 40)), MV_Hi=float(r.uniform(60, 100)))
    for key, val in (("PropFacSP", r.uniform(0, 1)), ("DiffFbk", bool(r.integers(2))), ("DeadBand", r.uniform(0.1, 2)),
                     ("DbMode", str(r.choice(["spojité", "skokové"]))), ("PVFilt", r.uniform(0.5, 5)),
                     ("MVRate", r.uniform(0.2, 2)), ("SPRate", r.uniform(0.1, 1)), ("ConZone", r.uniform(3, 9))):
        if r.random() < 0.5:
            c[key] = float(val) if not isinstance(val, (bool, str)) else val
    return c


def _python(profile, ctrl, h, steps):
    c = Controller(profile, ctrl, h)
    c.init(steps[0][0], steps[0][1], 50.0, steps[0][2])
    out = []
    for sp, y, ff, man, um, tune in steps:
        if tune:
            c.set_tuning(*tune)
        u = c.track(sp, y, um, ff) if man else c.step(sp, y, ff)
        out.append([u, c.spr, c.yf, c.I, c.D])
    return np.array(out)


def _js(profile, ctrl, h, steps):
    ctrl = {k: (None if isinstance(v, float) and not np.isfinite(v) else v) for k, v in ctrl.items()}
    script = f"""
const E = require({json.dumps(os.path.abspath(ENGINE))});
const cfg = {json.dumps(dict(profile=profile, ctrl=ctrl, h=h, steps=steps))};
const c = new E.Controller(E.profile(cfg.profile), cfg.ctrl, cfg.h);
const s0 = cfg.steps[0];
c.init(s0[0], s0[1], 50.0, s0[2]);
const out = [];
for (const [sp, y, ff, man, um, tune] of cfg.steps) {{
  if (tune) c.setTuning(tune[0], tune[1], tune[2]);
  const u = man ? c.track(sp, y, um, ff) : c.step(sp, y, ff);
  out.push([u, c.spr, c.yf, c.I, c.D]);
}}
console.log(JSON.stringify(out));
"""
    r = subprocess.run([NODE, "-e", script], capture_output=True, text=True, timeout=120, check=True)
    return np.array(json.loads(r.stdout))


def _cases():
    prof = load_preset("pcs7_pidconl")
    cases = []
    for i, (name, cfg) in enumerate(gc.CONFIGS.items()):             # 24 konfigurací z zlatých případů
        c = dict(BASE, **{k: v for k, v in cfg.items() if not k.startswith("_")})
        cases.append((f"cfg_{name}", prof, c, 0.5, _signals(i)))
    for s in range(16):                                              # 16 náhodných konfigurací a signálů
        cases.append((f"rand_{s}", prof, _ctrl_for(s), 0.5, _signals(100 + s)))
    for j, (name, (p, c)) in enumerate(VARIANTS.items()):            # 8 variant profilu (formy, AW, filtry)
        cases.append((f"var_{name}", p, c, 0.5, _signals(200 + j)))
    return cases


CASES = _cases()


def test_signal_count():
    assert len(CASES) >= 40


@pytest.mark.skipif(NODE is None, reason="Node.js není k dispozici")
@pytest.mark.parametrize("name,profile,ctrl,h,steps", CASES, ids=[c[0] for c in CASES])
def test_python_js_match(name, profile, ctrl, h, steps):
    py, js = _python(profile, ctrl, h, steps), _js(profile, ctrl, h, steps)
    assert py.shape == js.shape
    assert np.all(np.isfinite(py))
    assert np.max(np.abs(py - js)) < TOL


@pytest.mark.skipif(NODE is None, reason="Node.js není k dispozici")
def test_js_rejects_planned_and_bad_profile():
    prof = _profile(structure={"antiwindup": "external_reset"})
    script = f"""
const E = require({json.dumps(os.path.abspath(ENGINE))});
let msg = "";
try {{ E.profile({json.dumps(prof)}); }} catch (e) {{ msg = e.message; }}
let bad = "";
try {{ E.profile({{format: "x", version: 1}}); }} catch (e) {{ bad = e.message; }}
console.log(JSON.stringify([msg, bad]));
"""
    msg, bad = json.loads(subprocess.run([NODE, "-e", script], capture_output=True, text=True, check=True).stdout)
    assert "external_reset" in msg and "profil" in bad
