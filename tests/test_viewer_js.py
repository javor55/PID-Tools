"""Výpočty prohlížeče záznamu v prohlížeči (pidtools/ui/static/viewer_an.js) – přes Node.js."""
import json
import os
import shutil
import subprocess

import pytest

AN = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "pidtools", "ui", "static", "viewer_an.js"))
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="Node.js není k dispozici")


def _run(body):
    script = f"const A = require({json.dumps(AN)});\n" + """
const sig = (name, f, n, role, dt) => { dt = dt || 1; const t = new Float64Array(n), v = new Float64Array(n);
  for (let i = 0; i < n; i++) { t[i] = i * dt; v[i] = f(i); } return { name, role, t, v, n, ti: 0 }; };
let seed = 7; const rnd = () => { seed = (seed * 16807) % 2147483647; return seed / 2147483647 - 0.5; };
""" + body
    r = subprocess.run([NODE, "-e", script], capture_output=True, text=True, timeout=60, check=True)
    return json.loads(r.stdout)


def test_expressions():
    """Vzorce: priorita operátorů, funkce, signály jménem i v závorkách, filtry v čase; chyby s pozicí."""
    out = _run("""
const n = 100, a = sig("A.PV", (i) => i, n), b = sig("B 1", (i) => 2, n);
const ev = (src) => Array.from(A.evaluate(A.parse(src, ["A.PV", "B 1"]).ast, { t: a.t, n, sig: (q) => (q === "A.PV" ? a.v : b.v) }));
const err = (src) => { try { A.parse(src, ["A.PV", "B 1"]); return null; } catch (e) { return [e.msg, e.pos, e.arg === undefined ? null : e.arg]; } };
console.log(JSON.stringify({
  prec: ev("2 + 3 * 4 ^ 2 / 8 - -1")[0], pow: ev("2^3^2")[0], cmp: ev("A.PV > 50 and not (A.PV > 90)").slice(49, 52),
  sig: ev("[B 1] * A.PV")[10], fn: ev("clip(A.PV, 10, 20)").slice(5, 7).concat(ev("if(A.PV < 3, -1, max(A.PV, 50, 7))").slice(2, 4)),
  der: ev("der(A.PV * 2)")[50], diff: ev("diff(A.PV)")[50], integ: ev("integ([B 1])")[99], delay: ev("delay(A.PV, 5)")[20],
  avg: ev("avg(A.PV, 4)")[20], lag: ev("lag([B 1], 10)")[50], t: ev("t")[7],
  errors: [err("A.PV +"), err("foo(1)"), err("X + 1"), err("max(1)"), err("A.PV $ 2"), err("[B 1"), err("lag(A.PV, A.PV)") ,
           err("constructor"), err("__proto__(1)"), err("")],
  refs: A.parse("A.PV + [B 1] + A.PV", ["A.PV", "B 1"]).refs,
}));""")
    assert out["prec"] == 2 + 3 * 16 / 8 + 1 and out["pow"] == 512
    assert out["cmp"] == [0, 0, 1]
    assert out["sig"] == 20 and out["fn"] == [10, 10, -1, 50]
    assert out["der"] == pytest.approx(2) and out["diff"] == 1 and out["integ"] == pytest.approx(198)
    assert out["delay"] == 15 and out["avg"] == pytest.approx(18) and out["lag"] == pytest.approx(2) and out["t"] == 7
    e = out["errors"]
    assert e[0][0] == "unexpected_end" and e[1][:1] == ["unknown_fn"] and e[2] == ["unknown_sig", 0, "X"]
    assert e[3][0] == "bad_args" and e[4][0] == "bad_char" and e[5][0] == "unclosed"
    assert e[7][0] == "unknown_sig" and e[8][0] == "unknown_fn" and e[9][0] == "empty"
    assert out["refs"] == ["A.PV", "B 1"]


def test_need_number():
    """Časová konstanta filtru musí být číslo, ne průběh signálu."""
    out = _run("""
const a = sig("A", (i) => i, 10);
try { A.evaluate(A.parse("lag(A, A)", ["A"]).ast, { t: a.t, n: 10, sig: () => a.v }); console.log(JSON.stringify(null)); }
catch (e) { console.log(JSON.stringify(e.msg)); }""")
    assert out == "need_number"


def test_step_response_fopdt_and_integrating():
    """Odezva na skok: model 1. řádu se zpožděním (K, T, θ) a integrační proces (Ki)."""
    out = _run("""
const n = 3000, ts = 1000;
const u = sig("MV", (i) => (i >= ts ? 55 : 50), n, "MV");
const y = sig("PV", (i) => (i < ts + 20 ? 30 : 30 - 1.5 * 5 * (1 - Math.exp(-(i - ts - 20) / 120))) + 0.02 * rnd(), n, "PV");
const yi = sig("L", (i) => (i < ts + 10 ? 40 : 40 + 0.004 * 5 * (i - ts - 10)) + 0.01 * rnd(), n, "PV");
console.log(JSON.stringify({ a: A.step(u, y, 600, 2200), b: A.step(u, yi, 600, 2000), c: A.step(u, y, 1100, 2200) }));""")
    a = out["a"]
    assert a["ok"] and not a["integ"]
    assert a["K"] == pytest.approx(-1.5, rel=0.02) and a["T"] == pytest.approx(120, rel=0.05)
    assert a["theta"] == pytest.approx(20, abs=4) and a["ovs"] < 0.02
    b = out["b"]
    assert b["ok"] and b["integ"] and b["Ki"] == pytest.approx(0.004, rel=0.05)
    assert out["c"]["ok"] is False


def test_events():
    """Události: skoky MV a SP, změny stavového signálu, MV na limitu, signál beze změny, výpadek dat."""
    out = _run("""
const n = 4000;
const mv = sig("MV", (i) => (i < 1000 ? 40 : i < 2000 ? 47 : i < 3000 ? 100 : 60) + 0.05 * rnd(), n, "MV");
for (let i = 2000; i < 3000; i++) mv.v[i] = 100;
const sp = sig("SP", (i) => (i < 1500 ? 50 : 52), n, "SP");
const md = sig("MODE", (i) => (i < 2500 ? 1 : 0), n, "");
const pv = sig("PV", (i) => 50 + Math.sin(i / 50) + 0.1 * rnd(), n, "PV");
for (let i = 3200; i < 3400; i++) pv.v[i] = pv.v[3199];
const tt = new Float64Array(n); for (let i = 0; i < n; i++) tt[i] = i < 1200 ? i : i + 500;
const fl = { name: "FL", role: "", t: tt, v: Float64Array.from(pv.v), n, ti: 9 };
console.log(JSON.stringify(A.events([mv, sp, md, pv, fl], {}).map((e) => [e.kind, e.sig, Math.round(e.t)])));""")
    kinds = {(k, s_) for k, s_, _ in out}
    assert ("mv", "MV") in kinds and ("sp", "SP") in kinds and ("state", "MODE") in kinds
    assert ("sat", "MV") in kinds and ("flat", "PV") in kinds and ("gap", "FL") in kinds
    assert [t for k, s_, t in out if k == "mv"] == [1000, 2000, 3000]
    assert [t for k, s_, t in out if k == "sp"] == [1500]
    assert not any(k == "flat" and s_ == "MV" for k, s_, _ in out)      # MV na limitu není „beze změny“


def test_xcorr_finds_lag():
    """Vzájemná korelace najde zpoždění vazby (samoregulační i integrační proces)."""
    out = _run("""
const n = 4000;
const u = sig("U", (i) => (Math.floor(i / 137) % 3) * 2 + 0.3 * rnd(), n);
const w = sig("W", () => rnd(), n);
let x = 0; const y = sig("Y", (i) => { x += 0.1 * ((i >= 25 ? u.v[i - 25] : 0) - x); return x + 0.05 * rnd(); }, n);
let z = 0; const yi = sig("I", (i) => { z += 0.01 * (i >= 40 ? u.v[i - 40] - 2 : 0); return z; }, n);
const a = A.xcorr(y, [w, u], 0, n - 1, { mode: "incr", maxLag: 200 });
const b = A.xcorr(yi, [u, w], 0, n - 1, { mode: "int", maxLag: 200 });
console.log(JSON.stringify([a.list.map((q) => [q.name, q.r, q.lag]), b.list.map((q) => [q.name, q.r, q.lag])]));""")
    a, b = out
    assert a[0][0] == "U" and a[0][1] > 0.3 and 25 <= a[0][2] <= 40
    assert b[0][0] == "U" and b[0][1] > 0.3 and 35 <= b[0][2] <= 50
