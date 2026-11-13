"""Speciální funkce regulátoru (R3): gap, nelineární zesílení, anti-windup, rychlostní algoritmus, dynamické meze a výstupní
stupně (split range, 3-step, PWM). Chování + shoda Python × JS (< 1e-9)."""
import copy
import json
import os
import shutil
import subprocess

import numpy as np
import pytest

from pidtools.controllers import load_preset
from pidtools.controllers.parts import PARTS
from pidtools.core.controller import REGISTRIES, Controller, Profile, nonlinear_parts

ENGINE = os.path.join(os.path.dirname(__file__), "..", "pidtools", "ui", "static", "ctrl_engine.js")
NODE = shutil.which("node")
BASE = dict(Gain=0.9, TI=30.0, TD=3.0, DiffGain=5.0, SampleTime=1.0, MV_Lo=0.0, MV_Hi=100.0)


def _profile(structure=None, add=(), error=None):
    p = copy.deepcopy(load_preset("pcs7_pidconl"))
    p["structure"].update(structure or {})
    if error:
        p["structure"]["error"] = dict(p["structure"]["error"], **error)
    p["params"] = p["params"] + list(add)
    return p


def _out(**kw):
    return dict(limits=True, rate_limit=True, control_zone=True, **kw)


GAP_DB = {"deadband": {"modes": {"gap": "gap"}, "other": "gap"}}
GAP_ADD = [{"key": "GapGain", "role": "gap_gain", "default": 0.3}]
STAGE_ADD = [{"key": k, "role": r, "default": d} for k, r, d in (
    ("SplitPoint", "split_point", 40.0), ("SplitGap", "split_gap", 6.0), ("KHeat", "k_heat", 1.2), ("KCool", "k_cool", 0.8),
    ("MotorTime", "motor_time", 20.0), ("TriThr", "tri_threshold", 0.8), ("MinPulse", "min_pulse", 1.5),
    ("MinPause", "min_pause", 2.0), ("PwmPeriod", "pwm_period", 10.0))]
TT = [{"key": "Tt", "role": "Tt", "default": 8.0}]

VARIANTS = {
    "gap": (_profile(error=GAP_DB, add=GAP_ADD), dict(BASE, DeadBand=1.5, DbMode="gap")),
    "squared": (_profile(error=dict(nonlinear={"kind": "squared"}), add=[{"key": "E0", "role": "nl_e0", "default": 4.0}]), BASE),
    "table_pv": (_profile(error=dict(nonlinear={"kind": "table", "input": "pv", "x": [30, 50, 70], "y": [2.0, 1.0, 0.4]})), BASE),
    "table_sp": (_profile(error=dict(nonlinear={"kind": "table", "input": "sp", "x": [40, 60], "y": [1.5, 0.5]})), BASE),
    "table_mv": (_profile(error=dict(nonlinear={"kind": "table", "input": "mv", "x": [0, 50, 100], "y": [1.0, 1.0, 0.3]})), BASE),
    "table_err": (_profile(error=dict(nonlinear={"kind": "table", "input": "error", "x": [-5, 0, 5], "y": [0.5, 1.0, 2.0]})), BASE),
    "velocity": (_profile(structure={"algorithm": "velocity"}), dict(BASE, MV_Lo=35.0, MV_Hi=65.0)),
    "ext_reset": (_profile(structure={"antiwindup": "external_reset"}), dict(BASE, MV_Lo=35.0, MV_Hi=65.0)),
    "ext_reset_tt": (_profile(structure={"antiwindup": "external_reset"}, add=TT), dict(BASE, MV_Lo=35.0, MV_Hi=65.0)),
    "split": (_profile(structure={"output": _out(stage="split_range")}, add=STAGE_ADD), BASE),
    "three_step": (_profile(structure={"output": _out(stage="three_step")}, add=STAGE_ADD), BASE),
    "pwm": (_profile(structure={"output": _out(stage="pwm")}, add=STAGE_ADD), BASE),
}


def _signals(seed, n=400):
    rng = np.random.default_rng(seed)
    k = np.arange(n)
    sp = 50 + 9 * np.sign(np.sin(k / 55.0)) + rng.normal(0, 0.05, n)
    y = 50 + 7 * np.sin(k / 19.0) + np.cumsum(rng.normal(0, 0.15, n))
    ext = 50 + 12 * np.sin(k / 41.0)
    man = (k >= 150) & (k < 190)
    out = []
    for i in range(n):
        lim = (30.0, 70.0) if 250 <= i < 300 else None                     # dynamické meze
        out.append([float(sp[i]), float(y[i]), float(2 * np.sin(i / 30.0)), bool(man[i]), float(55 + 0.05 * (i - 150)),
                    float(ext[i]) if i % 7 else None, lim])
    return out


def _py(profile, ctrl, steps, h=0.5):
    c = Controller(profile, ctrl, h)
    c.init(steps[0][0], steps[0][1], 50.0, steps[0][2])
    rows = []
    for sp, y, ff, man, um, ext, lim in steps:
        c.ext_reset = ext
        if lim:
            c.set_limits(*lim)
        elif c.hi == 70.0 and c.lo == 30.0:
            c.set_limits(ctrl["MV_Lo"], ctrl["MV_Hi"])
        u = c.track(sp, y, um, ff) if man else c.step(sp, y, ff)
        rows.append([u, c.I, c.D, c.u, *c.outputs.values()])
    return np.array(rows)


def _js(profile, ctrl, steps, h=0.5):
    script = f"""
const E = require({json.dumps(os.path.abspath(ENGINE))});
const cfg = {json.dumps(dict(profile=profile, ctrl=ctrl, h=h, steps=steps))};
const c = new E.Controller(E.profile(cfg.profile), cfg.ctrl, cfg.h);
const s0 = cfg.steps[0];
c.init(s0[0], s0[1], 50.0, s0[2]);
const out = [];
for (const [sp, y, ff, man, um, ext, lim] of cfg.steps) {{
  c.extReset = ext;
  if (lim) c.setLimits(lim[0], lim[1]);
  else if (c.hi === 70.0 && c.lo === 30.0) c.setLimits(cfg.ctrl.MV_Lo, cfg.ctrl.MV_Hi);
  const u = man ? c.track(sp, y, um, ff) : c.step(sp, y, ff);
  out.push([u, c.I, c.D, c.u].concat(Object.values(c.outputs)));
}}
console.log(JSON.stringify(out));
"""
    r = subprocess.run([NODE, "-e", script], capture_output=True, text=True, timeout=120, check=True)
    return np.array(json.loads(r.stdout))


@pytest.mark.skipif(NODE is None, reason="Node.js není k dispozici")
@pytest.mark.parametrize("name", list(VARIANTS))
def test_python_js_match(name):
    prof, ctrl = VARIANTS[name]
    steps = _signals(7 + len(name))
    py, js = _py(prof, ctrl, steps), _js(prof, ctrl, steps)
    assert py.shape == js.shape and np.all(np.isfinite(py))
    assert np.max(np.abs(py - js)) < 1e-9


# ---- gap a nelineární zesílení
def _run(prof, ctrl, ys, sp=50.0, y0=50.0, u0=50.0, h=1.0):
    c = Controller(prof, ctrl, h)
    c.init(sp, y0, u0)
    return c, np.array([c.step(sp, y) for y in ys])


def test_gap_reduces_gain_inside_band_and_is_continuous():
    prof, ctrl = _profile(error=GAP_DB, add=GAP_ADD), dict(BASE, TD=0.0, TI=None, DeadBand=2.0, DbMode="gap", Gain=1.0)
    _, u_in = _run(prof, ctrl, [51.0])                       # e = -1 uvnitř pásma: P = k·e = -0.3
    assert u_in[0] == pytest.approx(50.0 - 0.3)
    _, u_edge = _run(prof, ctrl, [48.0 + 1e-9])              # těsně pod hranicí: |e| ≈ 2 → -k·2 = -0.6
    _, u_out = _run(prof, ctrl, [48.0 - 1e-9])
    assert u_edge[0] == pytest.approx(u_out[0], abs=1e-6)    # spojité na hranici
    _, u_far = _run(prof, ctrl, [42.0])                      # e = +8 → 8 − 2·(1 − 0.3) = 6.6 (znaménko dle směru)
    assert abs(u_far[0] - 50.0) == pytest.approx(6.6)


def test_squared_error_gain_proportional_to_error():
    prof, ctrl = _profile(error=dict(nonlinear={"kind": "squared"}), add=[{"key": "E0", "role": "nl_e0", "default": 4.0}]), \
        dict(BASE, TD=0.0, TI=None, Gain=1.0, DeadBand=0.0)
    for e in (1.0, 2.0, 3.0, 8.0):
        _, u = _run(prof, ctrl, [50.0 - e])
        assert u[0] - 50.0 == pytest.approx(e * e / 4.0 if e < 4.0 else e)


def test_table_gain_scheduling_by_pv():
    nl = {"kind": "table", "input": "pv", "x": [40, 60], "y": [2.0, 1.0]}
    prof, ctrl = _profile(error=dict(nonlinear=nl)), dict(BASE, TD=0.0, TI=None, Gain=1.0, MV_Lo=-1e9, MV_Hi=1e9)
    _, u1 = _run(prof, ctrl, [39.0], sp=40.0, y0=40.0, u0=0.0)       # PV < 40 → násobek 2
    _, u2 = _run(prof, ctrl, [50.0], sp=51.0, y0=51.0, u0=0.0)       # PV = 50 → 1.5
    assert u1[0] == pytest.approx(2.0 * 1.0) and u2[0] == pytest.approx(1.5 * 1.0)
    with pytest.raises(ValueError, match="increasing"):
        Controller(_profile(error=dict(nonlinear=dict(nl, x=[60, 40]))), ctrl, 1.0)


# ---- rychlostní algoritmus
def test_velocity_matches_incremental_reference():
    prof = _profile(structure={"algorithm": "velocity"})
    ctrl = dict(BASE, MV_Lo=40.0, MV_Hi=60.0, PropFacSP=0.7, SPRate=0.0, PVFilt=0.0)
    rng = np.random.default_rng(3)
    ys = 50 + 5 * np.sin(np.arange(300) / 15.0) + rng.normal(0, 0.2, 300)
    sps = np.where(np.arange(300) < 150, 52.0, 47.0)
    c = Controller(prof, ctrl, 1.0)
    c.init(sps[0], ys[0], 50.0)
    got = [c.step(float(s), float(y)) for s, y in zip(sps, ys)]
    # nezávislá přírůstková implementace: Δu = ΔP + ΔI + ΔD, u = clamp(u_prev + Δu)
    Kc, Ti, Td, N, b = 0.9, 30.0, 3.0, 5.0, 0.7
    Tf = Td / N
    ad, kd, ki = Tf / (Tf + 1.0), Kc * Td / (Tf + 1.0), Kc / Ti
    p_prev = Kc * (b * (sps[0] - ys[0]) - (1 - b) * ys[0])
    xd_prev, D_prev, u_prev, ref = sps[0] - ys[0], 0.0, 50.0, []
    for s, y in zip(sps, ys):
        e = s - y
        P = Kc * (b * e - (1 - b) * y)
        D = ad * D_prev + kd * (e - xd_prev)
        u_prev = min(max(u_prev + (P - p_prev) + ki * e + (D - D_prev), 40.0), 60.0)
        p_prev, D_prev, xd_prev = P, D, e
        ref.append(u_prev)
    assert np.max(np.abs(np.array(got) - np.array(ref))) < 1e-9


def test_velocity_has_no_windup_and_meets_limits():
    prof, ctrl = _profile(structure={"algorithm": "velocity"}), dict(BASE, MV_Lo=40.0, MV_Hi=60.0, TD=0.0)
    c, u = _run(prof, ctrl, np.full(500, 50.0), sp=80.0)              # trvalá odchylka 30 % → výstup na mezi
    assert u[-1] == 60.0
    u2 = [c.step(30.0, 50.0) for _ in range(5)]                       # změna znaménka → výstup okamžitě opouští mez
    assert u2[0] < 60.0


# ---- anti-windup: externí reset
def test_external_reset_follows_downstream_position():
    prof = _profile(structure={"antiwindup": "external_reset"})
    ctrl = dict(BASE, TD=0.0, MV_Lo=0.0, MV_Hi=100.0)
    c = Controller(prof, ctrl, 1.0)
    c.init(50.0, 50.0, 50.0)
    for _ in range(300):                                              # pohon za regulátorem stojí na 55 %, SP je mimo
        c.ext_reset = 55.0
        c.step(60.0, 50.0)
    assert abs(c.I - 55.0) < 0.5                       # integrál se srovnal s vnější polohou
    c.ext_reset = None                                                # bez signálu = zpětný výpočet z vlastního výstupu
    c.step(60.0, 50.0)
    assert np.isfinite(c.I)


# ---- dynamické meze
def test_dynamic_limits():
    c = Controller(_profile(), dict(BASE, TD=0.0), 1.0)
    c.init(50.0, 50.0, 50.0)
    assert c.step(70.0, 50.0) < 100.0
    c.set_limits(45.0, 55.0)
    assert [c.step(70.0, 50.0) for _ in range(3)] == [55.0] * 3
    c.set_limits(0.0, 100.0)
    assert c.step(70.0, 50.0) > 55.0


# ---- výstupní stupně
def test_split_range_identity_and_gap():
    P = dict(split_point=50.0, split_gap=0.0, k_heat=1.0, k_cool=1.0)
    prof, ctrl = _profile(structure={"output": _out(stage="split_range")},
                          add=[{"key": k, "role": k, "default": v} for k, v in P.items()]), dict(BASE, TD=0.0)
    c = Controller(prof, ctrl, 1.0)
    st = c.stage
    for u in (0, 10, 40, 50, 60, 90, 100):
        assert st(float(u)) == pytest.approx(u)
    assert st(75.0) == pytest.approx(75.0) and c.outputs["MV"] == pytest.approx(50.0) and c.outputs["MV2"] == 0.0
    assert st(25.0) == pytest.approx(25.0) and c.outputs["MV2"] == pytest.approx(50.0) and c.outputs["MV"] == 0.0
    # mezera 10 % kolem 50: uvnitř ani ohřev, ani chlazení
    prof2 = _profile(structure={"output": _out(stage="split_range")},
                     add=[{"key": k, "role": k, "default": v} for k, v in dict(P, split_gap=10.0).items()])
    st2 = Controller(prof2, ctrl, 1.0).stage
    assert st2(52.0) == pytest.approx(50.0) and st2(48.0) == pytest.approx(50.0)
    assert st2(100.0) == pytest.approx(100.0) and st2(0.0) == pytest.approx(0.0)


def _stage(stage, h=1.0, **roles):
    prof = _profile(structure={"output": _out(stage=stage)}, add=[{"key": k, "role": k, "default": v} for k, v in roles.items()])
    return Controller(prof, dict(BASE, TD=0.0), h).stage


def test_three_step_motor_moves_with_min_pulse_and_pause():
    st = _stage("three_step", motor_time=20.0, tri_threshold=1.0, min_pulse=2.0, min_pause=1.0)
    assert st(50.0) == 50.0                                           # první volání nastaví polohu
    assert st(50.5) == 50.0                                           # pod prahem 1 % se nehýbe
    assert st(51.0) == 50.0 and st.outputs["PULSE_UP"] == 0.0         # puls by trval 0.2 s < min. puls 2 s
    pos = [st(70.0) for _ in range(12)]                               # 19 % při 20 s / 100 % = 3.8 s pulzu
    assert pos[0] == pytest.approx(55.0)
    assert max(pos) <= 70.0 + 1e-9 and pos[-1] == pytest.approx(70.0, abs=0.1)
    down = [st(10.0) for _ in range(30)]
    assert down[-1] == pytest.approx(10.0, abs=0.1) and min(down) >= 10.0 - 1e-9
    assert [st(0.0) for _ in range(40)][-1] == 0.0 and st(0.0) == 0.0  # koncová poloha
    # průměrný ekvivalent následuje požadavek: pohon dojede do cíle
    st = _stage("three_step", motor_time=60.0, tri_threshold=0.5, min_pulse=0.0, min_pause=0.0)
    st(20.0)
    assert [st(80.0) for _ in range(80)][-1] == pytest.approx(80.0, abs=0.5)


def test_pwm_average_equals_duty_and_min_pulse():
    st = _stage("pwm", h=0.5, pwm_period=10.0, min_pulse=0.0)
    flags = []
    for _ in range(200):
        st(30.0)
        flags.append(st.outputs["PWM"])
    assert np.mean(flags) == pytest.approx(0.3, abs=1e-9) and st(30.0) == pytest.approx(30.0)
    st = _stage("pwm", h=0.5, pwm_period=10.0, min_pulse=2.0)         # 10 % = 1 s < min. puls 2 s → pod polovinou 0
    assert st(8.0) == 0.0                                             # 0.8 s < 1 s
    st = _stage("pwm", h=0.5, pwm_period=10.0, min_pulse=2.0)
    assert st(15.0) == pytest.approx(20.0)                            # 1.5 s → zaokrouhleno na 2 s
    st = _stage("pwm", h=0.5, pwm_period=10.0, min_pulse=2.0)
    assert st(95.0) == pytest.approx(100.0) and _stage("pwm", pwm_period=10.0, min_pulse=2.0)(87.0) == pytest.approx(80.0)


def test_staged_loop_runs_with_simulation_interface():
    from pidtools.core.simulation import pidconl_sim_full
    prof = _profile(structure={"output": _out(stage="pwm")}, add=[{"key": "PwmPeriod", "role": "pwm_period", "default": 10.0}])
    sp = np.full(600, 50.0)
    sp[20:] = 58.0
    r = pidconl_sim_full("P1D", [1.0, 30.0, 2.0], [], 1.0, sp, 50.0, 50.0, dict(BASE, Gain=1.0, TI=25.0, TD=0.0), profile=prof)
    assert abs(r["PV"][-1] - 58.0) < 1.0


# ---- registry a katalog částí
def test_catalog_covers_registries_and_nonlinear_parts():
    for kind, reg in REGISTRIES.items():
        for key, (_obj, planned) in reg.items.items():
            if not planned:
                assert key in PARTS[kind], f"{kind}.{key} chybí v katalogu částí"
    assert nonlinear_parts(_profile()) == []
    assert nonlinear_parts(_profile(error=GAP_DB, add=GAP_ADD)) == ["gap"]
    assert nonlinear_parts(_profile(structure={"output": _out(stage="pwm")}, error=dict(nonlinear={"kind": "squared"}))) \
        == ["nonlinear_gain", "pwm"]
    with pytest.raises(ValueError, match="unknown item"):
        Profile(_profile(structure={"output": _out(stage="nesmysl")}))


@pytest.mark.skipif(NODE is None, reason="Node.js není k dispozici")
def test_js_registries_match_python():
    script = f"""const E = require({json.dumps(os.path.abspath(ENGINE))});
const r = E.registries, out = {{}};
for (const k of Object.keys(r)) out[k] = Object.keys(r[k].items).filter(i => !r[k].items[i].planned).sort();
console.log(JSON.stringify(out));"""
    js = json.loads(subprocess.run([NODE, "-e", script], capture_output=True, text=True, check=True).stdout)
    camel = dict(d_sources="dSources", d_filters="dFilters", nl_gains="nlGains", output_stages="outputStages",
                 pv_filters="pvFilters")
    for kind, reg in REGISTRIES.items():
        py = sorted(k for k, (_, planned) in reg.items.items() if not planned)
        assert js[camel.get(kind, kind)] == py, kind


# ---- R5 (test použitelnosti) a robustnost u nelineárních profilů
def _checked(prof):
    from pidtools.app.controller_check import run_check
    return run_check(prof, only=["translation", "determinism", "rest", "direction", "switching", "linearity", "numerics"])


@pytest.mark.parametrize("name", ["gap", "squared", "table_pv", "pwm", "three_step", "split"])
def test_nonlinear_profile_is_optimisation_only(name):
    res = _checked(VARIANTS[name][0])
    lin = next(c for c in res["checks"] if c["id"] == "linearity")
    assert lin["status"] == "fail" and lin["severity"] == "mapping" and lin["msg"][0] == "ctl_m_lin_parts"
    assert res["verdict"] == "optimisation_only", [(c["id"], c["status"]) for c in res["checks"]]


def test_linear_velocity_profile_stays_suitable():
    res = _checked(VARIANTS["velocity"][0])
    assert res["verdict"] == "suitable"


def test_robustness_of_nonlinear_profile_is_flagged_approximate():
    from pidtools.core import robustness_for
    ctrl = dict(BASE, DeadBand=1.0, DbMode="gap")
    lin = robustness_for(_profile())("P1D", [1.0, 20.0, 2.0], BASE)
    nl = robustness_for(VARIANTS["gap"][0])("P1D", [1.0, 20.0, 2.0], ctrl)
    assert "approximate" not in lin
    assert nl["approximate"] is True and nl["nonlinear"] == ["gap"]
    assert nl["Ms"] == pytest.approx(lin["Ms"])                         # linearizovaná část = ideální PID


def test_catalog_parts_have_i18n_descriptions():
    from pidtools import i18n
    from pidtools.controllers.parts import describe
    for part in describe():
        for lang in ("cs", "en"):
            assert part["desc_key"] in i18n.TEXTS[lang], (lang, part["desc_key"])
