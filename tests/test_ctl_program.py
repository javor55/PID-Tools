"""Vlastní rovnice regulátoru (R4): překladač a chybové hlášky, sémantika jazyka, mapování, shoda Python × JS, výkon."""
import json
import math
import os
import shutil
import subprocess
import time

import numpy as np
import pytest

from pidtools.controllers import Library, parse_profile, validate_profile
from pidtools.controllers.program import LIMITS, ProgramErrors, compile_program, eval_tree
from pidtools.core.controller import Controller, make_profile
from pidtools.core.program import ProgramController, ProgramProfile

ENGINE = os.path.join(os.path.dirname(__file__), "..", "pidtools", "ui", "static", "ctrl_engine.js")
NODE = shutil.which("node")

PID_GAP = '''
# PID s gap pásmem a back-calculation anti-windupem
param Ts   = 1    "Perioda"          [s]
param Kp   = 1.0  "Zesílení"         [-]
param Ti   = 60   "Integrační čas"   [s]   min 0.1
param Td   = 2    "Derivační čas"    [s]
param N    = 10   "Filtr D"          [-]
param Gap  = 0.5  "Šířka gap pásma"  [%]
param Kgap = 0.3  "Zesílení v pásmu" [-]
state I    = 0    [%] init MV0 - Kp * (SP - PV) - FF

e   = gap(SP - PV, Gap, Kgap)
d   = lag(Td * ddt(-PV), Td / N)
v   = Kp * e + I + Kp * d + FF
MV  = clamp(v, MV_LO, MV_HI)
I   = I + Kp / Ti * e * dt + (MV - v) * dt / Ti      # back-calculation

map Kp = Kc
map Ti = Ti
map Td = Td
map N = N
'''

FEATURES = '''
param Ts = 1 [s]
param Kp = 1.2 "Zesílení" [-]
param T1 = 5 [s]
state I = 0 init MV0 - Kp * (SP - PV)
state n = 0
e = deadband(SP - PV, 0.3)
ff = lead_lag(FF, 4, T1)
sched = table(PV, [0, 40, 60, 100], [1.5, 1.0, 0.7, 0.5])
hot = (PV > 55 and SP > 50) ? 1 : 0
v = sched * Kp * e + I + rate(ff, 1.5, 2.5) + prev(e) * 0.1 + sign(e) * min(abs(e), 2) - max(-e, 0) * 0.2
MV = clamp(v, MV_LO, MV_HI)
MV2 = 100 - MV + sqrt(abs(e)) + exp(-abs(e)) + log(1 + abs(e)) + e ^ 2 / (1 + hot) + (not hot) * 3 + (e != 0 or hot == 1) * 2
I = I + Kp * e * dt / 30
n = n + 1
map Kp = Kc
unmap Kc = Kp
'''

PI_CLAMP = '''
param Ts = 1 [s]
param Gain = 0.9 [-]
param TI = 30 [s]
state I = 0 init MV0 - Gain * (SP - PV) - FF
e = SP - PV
inc = Gain * dt / TI * e
u = Gain * e + I + inc + FF
MV = clamp(u, MV_LO, MV_HI)
I = (MV == u or (u > MV and inc < 0) or (u < MV and inc > 0)) ? I + inc : I
map Gain = Kc
map TI = Ti
'''

PROGRAMS = {"pid_gap": PID_GAP, "features": FEATURES, "pi_clamp": PI_CLAMP}


def _data(src, name="prog"):
    return parse_profile({"format": "pidctrl", "version": 1, "id": name, "name": name, "kind": "program", "source": src})


def _steps(seed, n=300):
    rng = np.random.default_rng(seed)
    k = np.arange(n)
    sp = 50 + 8 * np.sign(np.sin(k / 45.0)) + rng.normal(0, 0.05, n)
    y = 50 + 6 * np.sin(k / 17.0) + np.cumsum(rng.normal(0, 0.12, n))
    out = []
    for i in range(n):
        out.append([float(sp[i]), float(y[i]), float(1.5 * np.sin(i / 23.0)), bool(120 <= i < 150), float(55 + 0.05 * (i - 120)),
                    (1.4, 40.0, 3.0) if i == 200 else None, (40.0, 60.0) if 230 <= i < 260 else None])
    return out


def _py(data, ctrl, steps, h=0.5):
    c = Controller(data, ctrl, h)
    assert isinstance(c, ProgramController)
    c.init(steps[0][0], steps[0][1], 50.0, steps[0][2])
    rows = []
    for sp, y, ff, man, um, tune, lim in steps:
        if tune:
            c.set_tuning(*tune)
        if lim:
            c.set_limits(*lim)
        elif c.lo == 40.0 and c.hi == 60.0:
            c.set_limits(ctrl["MV_Lo"], ctrl["MV_Hi"])
        u = c.track(sp, y, um, ff) if man else c.step(sp, y, ff)
        rows.append([u, c.outputs.get("MV2", 0.0), c.S[0] if c.S else 0.0])
    return np.array(rows)


def _js(data, ctrl, steps, h=0.5):
    script = f"""
const E = require({json.dumps(os.path.abspath(ENGINE))});
const cfg = {json.dumps(dict(profile=data, ctrl=ctrl, h=h, steps=steps))};
const c = new E.Controller(E.profile(cfg.profile), cfg.ctrl, cfg.h);
const s0 = cfg.steps[0];
c.init(s0[0], s0[1], 50.0, s0[2]);
const st = cfg.profile.program.states, out = [];
for (const [sp, y, ff, man, um, tune, lim] of cfg.steps) {{
  if (tune) c.setTuning(...tune);
  if (lim) c.setLimits(lim[0], lim[1]);
  else if (c.lo === 40.0 && c.hi === 60.0) c.setLimits(cfg.ctrl.MV_Lo, cfg.ctrl.MV_Hi);
  const u = man ? c.track(sp, y, um, ff) : c.step(sp, y, ff);
  out.push([u, c.outputs.MV2 === undefined ? 0 : c.outputs.MV2, st.length ? c.V[st[0].name] : 0]);
}}
console.log(JSON.stringify(out));
"""
    r = subprocess.run([NODE, "-e", script], capture_output=True, text=True, timeout=120, check=True)
    return np.array(json.loads(r.stdout))


CTRLS = {"pid_gap": dict(Kp=1.1, Ti=40.0, Td=3.0, MV_Lo=0.0, MV_Hi=100.0), "features": dict(MV_Lo=0.0, MV_Hi=100.0),
         "pi_clamp": dict(MV_Lo=35.0, MV_Hi=65.0)}


@pytest.mark.skipif(NODE is None, reason="Node.js není k dispozici")
@pytest.mark.parametrize("name", list(PROGRAMS))
@pytest.mark.parametrize("h", [0.5, 1.0])
def test_python_js_match(name, h):
    data, steps = _data(PROGRAMS[name], name), _steps(len(name))
    py, js = _py(data, CTRLS[name], steps, h), _js(data, CTRLS[name], steps, h)
    assert py.shape == js.shape and np.all(np.isfinite(py))
    assert np.max(np.abs(py - js)) < 1e-9
    assert np.ptp(py[:, 0]) > 1.0                                    # signál není degenerovaný


# ---- překladač: chybové hlášky s řádkem a sloupcem
@pytest.mark.parametrize("src,code,line,col", [
    ("MV = foo + 1", "unknown_name", 1, 6),
    ("x = 1 +\nMV = x", "expected", 1, 8),
    ("param a = 1\nMV = a(", "expected", 2, 8),
    ("param a = 1\nMV = a $ 2", "bad_char", 2, 8),
    ("MV = lag(SP)", "arity", 1, 6),
    ("c = SP > 1\nMV = c ? lag(PV, 1) : 0", "stateful_in_branch", 2, 10),
    ("MV = (SP > 1 and lag(PV, 1) > 0) ? 1 : 0", "stateful_in_branch", 1, 18),
    ("param Kp = 1\nKp = 3\nMV = Kp", "assign_param", 2, 1),
    ("SP = 3\nMV = 1", "assign_input", 1, 1),
    ("x = 2\n", "missing_mv", 1, 1),
    ("MV = y\ny = 1", "use_before_assign", 1, 6),
    ("MV = nonsense(1)", "unknown_function", 1, 6),
    ("param a = 1\nparam a = 2\nMV = a", "duplicate", 2, 7),
    ("param a = 5 min 6\nMV = a", "default_out_of_range", 1, 1),
    ("MV = table(SP, [3, 1], [1, 2])", "table_order", 1, 16),
    ("MV = table(SP, 1, 2)", "table_lists", 1, 6),
    ("map Kx = Kc\nMV = 1", "map_target", 1, 5),
    ("param a = 1 \"neukončený\nMV = a", "unterminated_string", 1, 13),
    ("MV = 1e999", "bad_number", 1, 6),
    ("param MV = 1\nMV = 2", "reserved", 1, 7),
    ("state s = 0 init lag(PV, 1)\nMV = s", "stateful_not_allowed", 1, 18),
])
def test_error_messages(src, code, line, col):
    with pytest.raises(ProgramErrors) as ex:
        compile_program(src)
    err = ex.value.errors[0]
    assert (err.code, err.line, err.col) == (code, line, col), [str(e) for e in ex.value.errors]


def test_all_errors_reported_not_only_first():
    with pytest.raises(ProgramErrors) as ex:
        compile_program("a = 1 +\nMV = zzz\nb = $\n")
    assert [e.line for e in ex.value.errors] == [1, 2, 3]


def test_size_limits_and_hostile_input():
    for bad in ["MV = " + "(" * 5000 + "1" + ")" * 5000, "MV = " + " + ".join(["SP"] * 500),
                "x = 1\n" * (LIMITS["statements"] + 1) + "MV = 1", "# " + "x" * LIMITS["source"] + "\nMV = 1"]:
        with pytest.raises(ProgramErrors) as ex:
            compile_program(bad)
        assert ex.value.errors[0].code in ("too_deep", "too_big")
    # názvy z Pythonu nic nespouštějí: jen identifikátory s předponou
    src = "param __class__ = 2\nparam __import__ = 3\nMV = __class__ * __import__ + __builtins__"
    with pytest.raises(ProgramErrors):
        compile_program(src)
    ok = "param __class__ = 2\nparam __import__ = 3\nMV = __class__ * __import__"
    c = Controller(_data(ok), {}, 1.0)
    c.init(0, 0, 0)
    assert c.step(0, 0) == 6.0
    for kw in ("import os", "MV = open(1)", "MV = SP.real", "MV = [1][0]", "MV = SP; os.x"):
        with pytest.raises(ProgramErrors):
            compile_program(kw)


def test_warnings_for_unit_mismatch():
    r = compile_program('param a = 1 [s]\nparam b = 2 [%]\nMV = a + b')
    assert [w.code for w in r["warnings"]] == ["unit_mismatch"] and r["warnings"][0].line == 3
    assert compile_program('param a = 1 [s]\nparam b = 2 [-]\nMV = a * 2 + b')["warnings"] == []


# ---- sémantika
def _val(expr, **inputs):
    c = Controller(_data(f"MV = {expr}"), {}, 1.0)
    c.init(0, 0, 0)
    return c.step(inputs.get("sp", 0.0), inputs.get("pv", 0.0), inputs.get("ff", 0.0))


@pytest.mark.parametrize("expr,expected", [
    ("1 + 2 * 3", 7.0), ("(1 + 2) * 3", 9.0), ("-2 ^ 2", -4.0), ("2 ^ 3 ^ 2", 512.0), ("2 ^ -1", 0.5), ("10 - 4 - 3", 3.0),
    ("8 / 2 / 2", 2.0), ("1 / 0", 0.0), ("0 ^ -1", 0.0), ("(-8) ^ 0.5", 0.0), ("sqrt(-4)", 0.0), ("sqrt(9)", 3.0),
    ("log(0)", math.log(1e-300)), ("exp(1000)", math.exp(700)), ("1 < 2", 1.0), ("2 <= 1", 0.0), ("1 == 1 and 2 != 2", 0.0),
    ("not 0", 1.0), ("not 5", 0.0), ("0 or 3", 1.0), ("1 ? 2 : 3", 2.0), ("0 ? 2 : 3", 3.0), ("1 ? 0 ? 5 : 6 : 7", 6.0),
    ("clamp(5, 0, 3)", 3.0), ("clamp(-5, 0, 3)", 0.0), ("min(3, 1, 2)", 1.0), ("max(3, 1, 2)", 3.0), ("abs(-2.5)", 2.5),
    ("sign(-3) + sign(0) + sign(7)", 0.0), ("deadband(5, 2)", 3.0), ("deadband(-5, 2)", -3.0), ("deadband(1, 2)", 0.0),
    ("gap(1, 2, 0.5)", 0.5), ("gap(5, 2, 0.5)", 4.0), ("table(5, [0, 10], [0, 100])", 50.0), ("table(-1, [0, 10], [3, 100])", 3.0),
    ("table(99, [0, 10], [3, 100])", 100.0), ("1e3 + .5", 1000.5),
])
def test_expression_semantics(expr, expected):
    assert _val(expr) == pytest.approx(expected, rel=1e-12, abs=1e-12)


def test_eval_tree_matches_generated_code():
    for expr in ("SP * 2 - PV ^ 2 / (1 + abs(FF))", "SP > PV ? gap(SP - PV, 1, 0.2) : deadband(PV - SP, 0.5)"):
        c = Controller(_data(f"MV = {expr}"), {}, 1.0)
        tree = compile_program(f"MV = {expr}")["program"]["body"][0][2]
        for sp, pv, ff in ((3.0, 1.0, 0.5), (1.0, 4.0, -2.0), (0.0, 0.0, 0.0)):
            c.init(0, 0, 0)
            assert c.step(sp, pv, ff) == pytest.approx(eval_tree(tree, dict(SP=sp, PV=pv, FF=ff)), abs=1e-12)


def test_stateful_functions_against_references():
    src = "param Ts = 1 [s]\nMV = lag(SP, 5)\nMV2 = ddt(SP)\nx = rate(SP, 2, 1)\ny = lead_lag(SP, 10, 5)\nz = prev(SP)\n" \
          "MV = MV + 0 * (x + y + z)"
    # každá funkce zvlášť proti referenci
    sig = [0.0, 10.0, 10.0, -5.0, 3.0, 3.0, 8.0]
    for fn, ref in (
        ("lag(SP, 5)", lambda xs: _lag_ref(xs, 5.0)),
        ("ddt(SP)", lambda xs: [0.0] + [b - a for a, b in zip(xs, xs[1:])]),
        ("rate(SP, 2, 1)", lambda xs: _rate_ref(xs, 2.0, 1.0)),
        ("lead_lag(SP, 10, 5)", lambda xs: _ll_ref(xs, 10.0, 5.0)),
        ("prev(SP)", lambda xs: [xs[0]] + xs[:-1]),
        ("lag(SP, 0)", lambda xs: xs),
    ):
        c = Controller(_data(f"param Ts = 1 [s]\nMV = {fn}"), {}, 1.0)
        c.init(sig[0], 0, 0)
        got = [c.step(s, 0.0) for s in sig]
        assert got == pytest.approx(ref(sig), abs=1e-12), fn
    assert src                                                      # zdroj se přeloží i s několika stavovými funkcemi najednou
    compile_program(src)


def _lag_ref(xs, T):
    a, s, out = math.exp(-1.0 / T), xs[0], []
    for x in xs:
        s = a * s + (1 - a) * x
        out.append(s)
    return out


def _rate_ref(xs, up, dn):
    s, out = xs[0], []
    for i, x in enumerate(xs):
        s = x if i == 0 else s + min(max(x - s, -dn), up)
        out.append(s)
    return out


def _ll_ref(xs, tld, tlg):
    L, out = xs[0], []
    for x in xs:
        L = math.exp(-1.0 / tlg) * L + (1 - math.exp(-1.0 / tlg)) * x
        out.append(L + tld / tlg * (x - L))
    return out


def test_sample_time_and_hold():
    c = Controller(_data("param Ts = 3 [s]\nstate n = 0\nn = n + 1\nMV = n"), {}, 1.0)
    c.init(0, 0, 0)
    assert [c.step(0, 0) for _ in range(7)] == [1.0, 1.0, 1.0, 2.0, 2.0, 2.0, 3.0] and c.Tc == 3.0


def test_param_clamp_defaults_and_set_tuning():
    c = Controller(_data(PI_CLAMP), dict(Gain=5.0, TI=0.0, MV_Lo=0, MV_Hi=100), 1.0)       # TI bez min. → 0 nezmění
    assert c._vals[2] == 0.0
    d = _data('param a = 2 min 1 max 3 \nparam b = 1\nMV = a * b\nmap b = Kc\n')
    c = Controller(d, dict(a=10.0), 1.0)
    assert c._vals[0] == 3.0
    c.init(0, 0, 0)
    c.set_tuning(4.0)
    assert c.step(0, 0) == 12.0 and d["params"][0]["range"] == [1.0, 3.0]


# ---- bezrázové převzetí a rovnost s PIDConL
def test_bumpless_track_and_init():
    c = Controller(_data(PID_GAP), dict(Kp=1.5, Ti=30.0, Td=0.0, MV_Lo=0.0, MV_Hi=100.0), 1.0)
    c.init(50.0, 50.0, 42.0)
    assert c.step(50.0, 50.0) == pytest.approx(42.0)
    for k in range(20):
        c.track(50.0 + 0.1 * k, 50.0 + 0.1 * k, 70.0)
    assert abs(c.step(51.9, 51.9) - 70.0) < 1e-9


def test_program_equals_pidconl_preset():
    from pidtools.core.simulation import PIDConL
    ctrl = dict(Gain=0.9, TI=30.0, TD=0.0, DiffGain=5.0, SampleTime=1.0, MV_Lo=35.0, MV_Hi=65.0)
    ref, prog = PIDConL(ctrl, 1.0), Controller(_data(PI_CLAMP), dict(Gain=0.9, TI=30.0, MV_Lo=35.0, MV_Hi=65.0), 1.0)
    steps = _steps(3, 400)
    ref.init(50, 50, 50)
    prog.init(50, 50, 50)
    for sp, y, ff, *_ in steps:
        assert prog.step(sp, y, ff) == pytest.approx(ref.step(sp, y, ff), abs=1e-9)


# ---- mapování (pravidla ladění)
def test_mapping_roundtrip_and_rules():
    from pidtools.controllers import canonical_to_profile, profile_to_canonical
    d = _data(PID_GAP)
    m = canonical_to_profile(d, dict(Kc=2.0, Ti=25.0, Td=4.0, b=1.0, c=1.0, N=8.0))
    assert m["values"] == dict(Kp=2.0, Ti=25.0, Td=4.0, N=8.0) and m["warnings"] == []
    back = profile_to_canonical(d, m["values"])
    assert (back["Kc"], back["Ti"], back["Td"], back["N"]) == (2.0, 25.0, 4.0, 8.0)
    # výraz v mapování a explicitní opačný směr: Ti v minutách, zesílení jako pásmo proporcionality
    src = 'param PB = 50 [%]\nparam Timin = 1 [min]\nMV = 100 / PB * (SP - PV)\nmap PB = 100 / Kc\nmap Timin = Ti / 60\n' \
          'unmap Kc = 100 / PB\nunmap Ti = Timin * 60\n'
    d2 = _data(src)
    m2 = canonical_to_profile(d2, dict(Kc=4.0, Ti=90.0))
    assert m2["values"] == dict(PB=25.0, Timin=1.5)
    c2 = profile_to_canonical(d2, m2["values"])
    assert c2["Kc"] == pytest.approx(4.0) and c2["Ti"] == pytest.approx(90.0)
    with pytest.raises(ValueError, match="mapování"):
        canonical_to_profile(_data("param a = 1\nMV = a"), dict(Kc=1.0))


def test_program_profile_in_library(tmp_path):
    lib = Library(str(tmp_path))
    data = {"format": "pidctrl", "version": 1, "id": "prog_a", "name": "Program A", "kind": "program", "source": PID_GAP}
    assert validate_profile(data) == []
    out = lib.import_profile(data)
    assert out["kind"] == "program" and [p["key"] for p in out["params"]][:3] == ["Ts", "Kp", "Ti"] and out["structure"] == {}
    back = lib.get(out["id"])
    assert back["program"]["format"] == "pidprog" and back["source"] == PID_GAP
    bad = dict(data, source="MV = nope")
    problems = validate_profile(bad)
    assert problems and problems[0]["path"] == "source:1:6"
    assert validate_profile(dict(data, source="")) != []


def test_make_profile_and_simulation_interface():
    from pidtools.core.simulation import pidconl_sim_full
    prof = make_profile(_data(PID_GAP))
    assert isinstance(prof, ProgramProfile) and prof.tuning_roles == ["Kp", "Ti", "Td", "N"]
    sp = np.full(500, 50.0)
    sp[20:] = 58.0
    r = pidconl_sim_full("P1D", [1.0, 30.0, 2.0], [], 1.0, sp, 50.0, 50.0, dict(Kp=1.0, Ti=25.0, Td=0.0, MV_Lo=0.0, MV_Hi=100.0),
                         profile=prof)
    assert abs(r["PV"][-1] - 58.0) < 0.5 and r["SPr"][-1] == 58.0


def test_suitability_check_of_program():
    from pidtools.app.controller_check import run_check
    res = run_check(_data(PID_GAP), only=["translation", "determinism", "rest", "direction", "switching", "numerics", "performance",
                                          "steady", "processes", "antiwindup"])
    bad = [(c["id"], c["status"], c["msg"]) for c in res["checks"] if c["status"] == "fail"]
    assert not bad, bad
    nomap = run_check(_data("param Kp = 1 [-]\nMV = Kp * (SP - PV)"), only=["translation", "equivalent"])
    assert nomap["verdict"] == "optimisation_only"
    assert next(c for c in nomap["checks"] if c["id"] == "equivalent")["msg"][0] == "ctl_m_prog_nomap"


def test_robustness_of_program_is_approximate():
    from pidtools.core import robustness_for
    r = robustness_for(_data(PID_GAP))("P1D", [1.0, 20.0, 2.0], dict(Kp=1.0, Ti=30.0, Td=0.0, N=10.0, Ts=1.0))
    assert r["approximate"] is True and np.isfinite(r["Ms"])


# ---- výkon (jen se vypíše; pojistka proti omylu)
@pytest.mark.parametrize("name", ["pid_gap", "features"])
def test_program_step_benchmark(name, capsys, record_property):
    c = Controller(_data(PROGRAMS[name], name), CTRLS[name], 1.0)
    c.init(50.0, 50.0, 50.0)
    n = 100000
    ys = (50 + np.sin(np.arange(n) / 50.0)).tolist()
    best = 1e9
    for _ in range(3):
        t0 = time.perf_counter()
        for y in ys:
            c.step(52.0, y, 0.0)
        best = min(best, (time.perf_counter() - t0) / n * 1e6)
    record_property("step_us", round(best, 3))
    with capsys.disabled():
        print(f"\n[benchmark] program '{name}': {best:.2f} µs/krok")
    assert best < 50
