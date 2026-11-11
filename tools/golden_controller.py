"""
Zlaté případy regulátoru (E1, docs/cs/plan-v2.md): plné výstupy dnešního PIDConL a navazujících simulací
v plné přesnosti (npz), se kterými se porovnává obecný regulátor (core.controller).

Pokrytí: PropFacSP < 1 (i starý klíč PropFbk), DiffGain, DeadBand + DbMode, limity MV (windup), MVRate, SPRate,
PVFilt, ConZone, FF, track (MAN → AUTO), set_tuning za běhu, SampleTime > h; procesy FOPDT (P1D, záporné zesílení),
integrační (I1D); pidconl_sim_full pro ukázková data a 3 syntetické smyčky (s měřenou poruchou), kaskáda, LiveLoop,
návrh ladění + robustnost přes pracovní prostor (app/workspace) a živý engine v JS (live_engine.js přes Node).

    python tools/golden_controller.py            # porovnat s uloženým
    python tools/golden_controller.py --update   # záměrně přegenerovat (jen po vědomé změně výpočtů)
"""
import json
import os
import shutil
import subprocess
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
GOLDEN = os.path.join(ROOT, "tests", "golden", "controller_golden.npz")
ENGINE = os.path.join(ROOT, "pidtools", "ui", "static", "live_engine.js")
NODE = shutil.which("node")

PROCS = {                          # kód, parametry, Gain, TI, TD, nový krok h
    "fopdt": ("P1D", [1.2, 40.0, 6.0], 0.8, 40.0, 5.0, 0.5),
    "fopdt_neg": ("P1D", [-0.8, 30.0, 4.0], -0.9, 35.0, 3.0, 0.5),
    "integ": ("I1D", [0.02, 20.0, 3.0], 4.0, 200.0, 8.0, 0.5),
}

CONFIGS = {
    "pi": dict(TD=0.0),
    "pid_n5": dict(),
    "pid_n2": dict(DiffGain=2.0),
    "pid_dfb": dict(DiffFbk=True),
    "propfac04": dict(PropFacSP=0.4),
    "propfac0": dict(PropFacSP=0.0, DiffFbk=True),
    "propfbk_legacy": dict(PropFbk=True),
    "db_cont": dict(DeadBand=1.5, DbMode="spojité"),
    "db_step": dict(DeadBand=1.5, DbMode="skokové"),
    "db_step_dfb": dict(DeadBand=1.0, DbMode="skokové", DiffFbk=True, PropFacSP=0.7),
    "limits_windup": dict(MV_Lo=40.0, MV_Hi=60.0),
    "mvrate": dict(MVRate=0.5),
    "mvrate_limits": dict(MVRate=0.4, MV_Lo=35.0, MV_Hi=70.0),
    "sprate": dict(SPRate=0.2),
    "pvfilt": dict(PVFilt=4.0),
    "conzone": dict(ConZone=3.0, MV_Lo=10.0, MV_Hi=90.0),
    "conzone_rate": dict(ConZone=2.0, MV_Lo=10.0, MV_Hi=90.0, MVRate=1.0),
    "ff": dict(_ff=1.0),
    "ff_limits": dict(_ff=1.5, MV_Lo=30.0, MV_Hi=75.0),
    "sample4": dict(SampleTime=2.0),
    "sample4_all": dict(SampleTime=2.0, SPRate=0.1, MVRate=0.3, PVFilt=3.0),
    "p_only": dict(TI=np.inf),
    "all_in_one": dict(DiffGain=4.0, PropFacSP=0.5, DiffFbk=True, DeadBand=0.8, DbMode="spojité", MV_Lo=20.0,
                       MV_Hi=85.0, PVFilt=2.0, MVRate=0.8, SPRate=0.3, ConZone=6.0, _ff=0.7),
}

N_STEPS = 1500


def _scenario(n, h):
    """Signály scénáře: SP, porucha na vstupu procesu, FF, ruční MV, režim a změny ladění."""
    k = np.arange(n)
    sp = np.where(k < 100, 50.0, np.where(k < 600, 58.0, 45.0))
    d = np.where((k >= 400) & (k < 900), 4.0, 0.0)
    ff = 2.0 * np.sin(k / 50.0) + np.where(k >= 300, 1.5, 0.0)
    man = (k >= 700) & (k < 800)
    uman = 55.0 + 0.02 * (k - 700)
    return sp, d, ff, man, uman


def _run_steps(cfg, proc):
    """Jeden běh smyčky krok po kroku (PIDConL + ProcStep) – vrací pole u, spr, yf a dem."""
    from pidtools.core.simulation import PIDConL, ProcStep
    code, p, gain, ti, td, h = PROCS[proc]
    cfg = dict(cfg)
    ffg = cfg.pop("_ff", 0.0)
    ctrl = dict(Gain=gain, TI=ti, TD=td, DiffGain=5.0, SampleTime=1.0, MV_Lo=0.0, MV_Hi=100.0)
    ctrl.update(cfg)
    n = N_STEPS
    sp, d, ff, man, uman = _scenario(n, h)
    ff = ff * ffg
    pid, pr = PIDConL(ctrl, h), ProcStep(code, p, h)
    pv0 = u0 = 50.0
    pid.init(sp[0], pv0, u0, ff[0])
    u_, spr_, yf_ = np.zeros(n), np.zeros(n), np.zeros(n)
    for k in range(n):
        if k == 1000:
            pid.set_tuning(ctrl["Gain"] * 0.6, ctrl["TI"] * 1.5 if np.isfinite(ctrl["TI"]) else ctrl["TI"],
                           ctrl["TD"] * 0.5)
        elif k == 1200:
            pid.set_tuning(ctrl["Gain"] * 0.8, np.inf, ctrl["TD"])
        elif k == 1350:
            pid.set_tuning(ctrl["Gain"], 60.0, ctrl["TD"])
        y = pv0 + pr.output()
        u = pid.track(sp[k], y, uman[k], ff[k]) if man[k] else pid.step(sp[k], y, ff[k])
        pr.step(u - u0 + d[k])
        u_[k], spr_[k], yf_[k] = u, pid.spr, pid.yf
    return dict(u=u_, spr=spr_, yf=yf_, dem=np.array(pid.dem))


def _steps():
    out = {}
    for cn, cfg in CONFIGS.items():
        for pn in PROCS:
            for k, v in _run_steps(cfg, pn).items():
                out[f"steps/{cn}/{pn}/{k}"] = v
    return out


def _put(out, prefix, d):
    for k, v in d.items():
        if isinstance(v, dict):
            _put(out, f"{prefix}/{k}", v)
        elif isinstance(v, (list, tuple)) and v and isinstance(v[0], (dict, list, tuple)):
            for i, x in enumerate(v):
                _put(out, f"{prefix}/{k}/{i}", x if isinstance(x, dict) else {"v": x})
        elif v is None or isinstance(v, str):
            continue
        else:
            out[f"{prefix}/{k}"] = np.asarray(v, float)


def _sims():
    from pidtools.core import demo_data
    from pidtools.core.simulation import cascade_sim, pidconl_sim_full
    out = {}
    # ---- ukázková data (hladina, integrační proces s měřeným přítokem)
    t, _sp, _pv, _mv, q = demo_data()
    h = 1.0
    sp = np.where(t < 600, 50.0, 55.0)
    pdl = [[0.01, 5.0, 3.0, 2.0, 0.0]]
    base = dict(Gain=-5.0, TI=200.0, TD=0.0, SampleTime=1.0, DiffGain=5.0, MV_Lo=0.0, MV_Hi=100.0)
    out_demo = {
        "demo_plain": base,
        "demo_ff_noise": dict(base, TD=10.0, FF=[-0.5], FF_LL=[(5.0, 10.0, 2.0)], Noise=0.1, Seed=3, PVFilt=2.0,
                              PropFacSP=0.6),
    }
    for nm, c in out_demo.items():
        _put(out, f"sim/{nm}", pidconl_sim_full("I1D", [-0.004, 15.0, 8.0], pdl, h, sp, 50.0, 50.0, c,
                                                dmeas=[q - 20.0]))
    # ---- syntetické smyčky: FOPDT (stikce, charakteristika ventilu), integrační s DV a FF, FOPDT s poruchami
    n = 2400
    t = np.arange(n) * 0.5
    sp = np.where(t < 100, 50.0, np.where(t < 700, 58.0, 47.0))
    dv = np.where(t > 300, 3.0, 0.0) + np.where(t > 900, -5.0, 0.0)
    dmv = np.where((t > 400) & (t < 600), 2.0, 0.0)
    dpv = 0.5 * np.sin(t / 80.0)
    valve = dict(Stic=1.0, SticJ=0.6, ValveChar=[0.6, 0.8, 1.0, 1.1, 1.2, 1.2, 1.1, 1.0, 0.9, 0.8])
    cases = {
        "synth_fopdt": ("P1D", [1.2, 40.0, 6.0], [], [], None, None, dict(
            Gain=0.8, TI=40.0, TD=5.0, DiffGain=3.0, SampleTime=1.0, PropFacSP=0.5, DiffFbk=True, DeadBand=0.2,
            DbMode="spojité", MV_Lo=10.0, MV_Hi=90.0, PVFilt=2.0, MVRate=1.5, SPRate=0.4, Noise=0.05, Seed=7,
            **valve)),
        "synth_integ_dv": ("I1D", [0.02, 20.0, 3.0], [[0.015, 10.0, 4.0, 2.0, 0.0]], [dv], None, dmv, dict(
            Gain=4.0, TI=200.0, TD=0.0, SampleTime=1.0, MV_Lo=0.0, MV_Hi=100.0, FF=[-0.6],
            FF_LL=[(8.0, 15.0, 3.0)], ConZone=8.0)),
        "synth_fopdt_dv_ff": ("P1D", [0.9, 60.0, 10.0], [[0.5, 30.0, 5.0, 2.0, 0.0]], [dv], dpv, dmv, dict(
            Gain=1.1, TI=60.0, TD=8.0, DiffGain=5.0, SampleTime=2.0, DeadBand=0.5, DbMode="skokové", MV_Lo=0.0,
            MV_Hi=100.0, FF=[-0.55], FF_LL=[(0.0, 0.0, 6.0)], PropFacSP=0.8)),
    }
    for nm, (code, p, pdl, dm, dpv_, dmv_, c) in cases.items():
        _put(out, f"sim/{nm}", pidconl_sim_full(code, p, pdl, 0.5, sp, 50.0, 50.0, c, dmeas=dm, dist_mv=dmv_,
                                                dist_pv=dpv_))
    # ---- kaskáda
    sp_o = np.where(np.arange(1500) < 100, 50.0, 56.0)
    ictrl = dict(Gain=2.0, TI=15.0, TD=0.0, SampleTime=1.0, MV_Lo=0.0, MV_Hi=100.0)
    octrl = dict(Gain=0.9, TI=80.0, TD=4.0, DiffGain=5.0, SampleTime=1.0, MV_Lo=20.0, MV_Hi=80.0, PropFacSP=0.7)
    tt, arr = cascade_sim(("P1D", [1.0, 5.0, 1.0]), ictrl, ("P1D", [1.0, 60.0, 8.0]), octrl, 1.0, sp_o,
                          d_inner=np.where(np.arange(1500) > 700, 2.0, 0.0))
    out["sim/cascade/t"], out["sim/cascade/y"] = tt, arr
    return out


def _live_scenario(n):
    steps = []
    for k in range(n):
        steps.append((50.0 if k < 50 else 58.0, not (300 <= k < 400), 62.0, 4.0 if k >= 600 else 0.0,
                      dict(Gain=0.7, TI=60.0, TD=0.0) if k == 800 else None))
    return steps


LIVE = {
    "P1D": ("P1D", [1.2, 40.0, 6.0]),
    "P2D": ("P2D", [-0.8, 30.0, 10.0, 4.0]),
    "I1D": ("I1D", [0.015, 20.0, 3.0]),
}
LIVE_CTRL = dict(Gain=1.1, TI=35.0, TD=4.0, DiffGain=5.0, SampleTime=1.0, PropFacSP=0.6, DiffFbk=True, DeadBand=0.3,
                 DbMode="spojité", MV_Lo=5.0, MV_Hi=95.0, PVFilt=2.0, MVRate=2.0, SPRate=0.5)
LIVE_PLANT = dict(Stic=1.5, SticJ=1.0, ValveChar=[0.6, 0.8, 1.0, 1.1, 1.2, 1.2, 1.1, 1.0, 0.9, 0.8], Noise=0.05, Seed=5)


def _live_ctrl(code):
    c = dict(LIVE_CTRL)
    if code == "I1D":
        c.update(Gain=4.0, TI=200.0)
    return c


def _live_py():
    from pidtools.core import LiveLoop
    out = {}
    h = 0.25
    steps = _live_scenario(1200)
    for nm, (code, p) in LIVE.items():
        loop = LiveLoop(code, p, _live_ctrl(code), h, 50.0, 50.0, LIVE_PLANT)
        rows = []
        for sp, auto, um, d, tune in steps:
            if tune:
                loop.set_tuning(tune)
            loop.advance(h, sp, auto, um, d)
            rows.append([loop.hist[k][-1] for k in ("t", "SP", "PV", "MV", "V")])
        out[f"live_py/{nm}"] = np.array(rows)
    return out


def _live_js(engine=ENGINE, plant=None):
    """Živý engine v prohlížeči (Node). Šum JS má vlastní generátor, proto jeho záznam bez šumu a s Math-RNG zvlášť."""
    out = {}
    h = 0.25
    steps = _live_scenario(1200)
    plant = dict(LIVE_PLANT if plant is None else plant)
    for nm, (code, p) in LIVE.items():
        cfg = dict(code=code, p=p, ctrl=_live_ctrl(code), plant=plant, h=h, steps=steps)
        script = f"""
const E = require({json.dumps(os.path.abspath(engine))});
const cfg = {json.dumps(cfg)};
const L = new E.LiveLoop(cfg.code, cfg.p, cfg.ctrl, cfg.h, 50.0, 50.0, cfg.plant);
const out = [];
for (const [sp, auto, um, d, tune] of cfg.steps) {{
  if (tune) L.setTuning(tune);
  out.push(L.tick(sp, auto, um, d));
}}
console.log(JSON.stringify(out));
"""
        r = subprocess.run([NODE, "-e", script], capture_output=True, text=True, timeout=120, check=True)
        out[f"live_js/{nm}"] = np.array(json.loads(r.stdout))
    return out


def _tuning():
    """Návrh ladění a robustnost přes pracovní prostor (ukázková data; model zafixován ručními hodnotami)."""
    from pidtools.app.workspace import Workspace
    s = Workspace()
    s.load_demo()
    s.set(chosen=["I1D"])
    s.identify()
    kw = {f"ed|I1D|{i}": v for i, v in enumerate([-0.004, 13.0, 11.5])}
    kw.update({f"ed|I1D|d0|{i}": v for i, v in enumerate([0.01, 8.0, 2.0, 0.0])})
    s.set(**kw, set2_gain=-3.0, set2_ti=150.0, set2_td=10.0, ctype="PID", propfac=0.7, dfb=True, db=0.2,
          pvfilt=2.0, mvrate=0.5, sprate=0.3)
    out = {}
    sug = None
    for m in ("SIMC", "Lambda", "AMIGO"):
        if m not in s.methods():
            continue
        r = s.suggest(m)
        sug = sug or r
        _put(out, f"tuning/{m}", {k: r[k] for k in ("Kc", "Ti", "Td")})
    for n in (1, 2):
        _put(out, f"tuning/metrics{n}", {k: v for k, v in s.set_metrics(n).items() if isinstance(v, (int, float))})
    sim = s.simulate(preview=sug, robust=True)
    for n, r in sim["runs"].items():
        _put(out, f"tuning/run{n}", {k: r[k] for k in ("t", "SPr", "PV", "PVm", "MV", "V", "dem")})
    for n, k in sim["kpis"].items():
        if k:
            _put(out, f"tuning/kpi{n}", {a: b for a, b in k.items() if not isinstance(b, dict)})
    for i, (_nm, r) in enumerate(sim["extra"]):
        _put(out, f"tuning/extra{i}", {k: r[k] for k in ("PV", "MV")})
    # robustnost a frekvenční charakteristika návrhu
    from pidtools.app import frequency as fq
    code, p, _pdl = s.model
    fr = fq.compare(code, p, {"set1": s.set_ctrl(1), "sug": s.ctrl_of(sug)})
    for n, r in fr.items():
        out[f"tuning/freq_{n}_S"] = np.abs(np.asarray(r["S"]))
        out[f"tuning/freq_{n}_bw"] = np.asarray(float(fq.bandwidth(r)))
    return out


def compute(with_js=True):
    out = {}
    out.update(_steps())
    out.update(_sims())
    out.update(_live_py())
    out.update(_tuning())
    if with_js and NODE:
        out.update(_live_js())
    return out


def compare(ref, new, rtol=1e-9, atol=1e-9):
    """Vrací (seznam rozdílů, největší absolutní odchylka)."""
    diffs, worst = [], 0.0
    for k in sorted(set(ref) | set(new)):
        if k not in ref or k not in new:
            diffs.append(f"{k}: chybí v {'uloženém' if k not in ref else 'novém'}")
            continue
        a, b = np.asarray(ref[k], float), np.asarray(new[k], float)
        if a.shape != b.shape:
            diffs.append(f"{k}: tvar {a.shape} × {b.shape}")
            continue
        if not np.allclose(a, b, rtol=rtol, atol=atol, equal_nan=True):
            diffs.append(f"{k}: max |Δ| = {np.nanmax(np.abs(a - b)):.3e}")
        if a.size:
            worst = max(worst, float(np.nanmax(np.abs(a - b))))
    return diffs, worst


def load():
    with np.load(GOLDEN) as z:
        return {k.replace("__", "/"): z[k] for k in z.files}


def save(res):
    np.savez_compressed(GOLDEN, **{k.replace("/", "__"): v for k, v in res.items()})


def main(argv):
    if "--update" in argv:
        save(compute())
        print("uloženo", GOLDEN)
        return 0
    diffs, worst = compare(load(), compute())
    print("\n".join(diffs) or "shoda", f"(max |Δ| = {worst:.3e})")
    return 1 if diffs else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
