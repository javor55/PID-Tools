"""Triáž smyček (app.triage): registr pravidel, prahy, verdikty na syntetických smyčkách."""
import numpy as np

from pidtools.app import audit, triage


class Sig:
    def __init__(self, t, cols):
        self.t_all, self.cols, self.sigs = t, cols, list(cols)

    def get(self, c):
        return self.cols[c]


def sim(kind="good", n=6000, h=1.0, seed=1):
    """PI regulace procesu 1. řádu se zpožděním; kind: good | stic | osc | man."""
    rng = np.random.default_rng(seed)
    t = np.arange(n) * h
    sp = np.full(n, 50.0)
    dist = np.zeros(n)
    for k in range(1, n):
        dist[k] = rng.normal(0, 0.3)
    pv = np.full(n, 50.0)
    mv = np.full(n, 50.0)
    valve = np.full(n, 50.0)
    x, integ, stuck, dl = 50.0, 0.0, 50.0, 5
    for k in range(1, n):
        e = sp[k - 1] - pv[k - 1]
        if kind == "man":
            u = 50.0
        else:
            integ += e * h / (10.0 if kind == "stic" else 40.0)
            u = 50 + 1.5 * (e + integ)
        mv[k] = float(np.clip(u, 0, 100))
        if kind == "stic" and abs(mv[k] - stuck) > 4:
            stuck = mv[k]
        valve[k] = stuck if kind == "stic" else mv[k]
        x += h / (8.0 if kind == "stic" else 40.0) * (-(x - 50.0) + (valve[max(k - dl, 0)] - 50.0) + dist[k])
        pv[k] = x + rng.normal(0, 0.05) + (6 * np.sin(2 * np.pi * k * h / 300.0) if kind == "osc" else 0.0)
    if kind == "stic":                  # klasická stikce: MV trojúhelník, PV téměř obdélník
        ph = 2 * np.pi * t / 200.0
        mv = 50 + 10 * (2 / np.pi) * np.arcsin(np.sin(ph))
        pv = 50 + 3 * np.tanh(4 * np.sin(ph - np.pi / 2)) + rng.normal(0, 0.05, n)
    return t, sp, pv, mv


def make(kinds):
    t = sim()[0]
    cols, defs = {}, []
    for n, (name, kind) in enumerate(kinds):
        _, sp, pv, mv = sim(kind, seed=n + 1)
        cols.update({f"{name}.PV": pv, f"{name}.MV": mv, f"{name}.SP": sp})
        defs.append(audit.LoopDef(name=name, pv=f"{name}.PV", mv=f"{name}.MV", sp=f"{name}.SP"))
    return Sig(t, cols), defs


def run(kinds, links=None, thr=None):
    sig, defs = make(kinds)
    ms = [triage.loop_metrics(sig, d) for d in defs]
    return ms, triage.verdicts(ms, links, thr)


def base_metrics(**kw):
    m = dict(name="x", ok=True, auto_pct=90, harris=0.9, theta=5, osc=False, period=None, stic=None, stic_ratio=None,
             hyst_pct=None, nonlin=None, frozen_pct=0, nan_pct=0, std_e_pct=1)
    m.update(kw)
    return m


def test_registry_complete():
    from pidtools.i18n import T
    ids = [r.id for r in triage.RULES]
    assert ids == ["low_auto", "foreign", "cascade", "valve", "nonlinear", "tune", "ok"]
    for r in triage.RULES:
        assert T(r.label) != r.label
        for t in r.thresholds.values():
            assert t.lo <= t.default <= t.hi and T(t.label) != t.label
    assert set(triage.default_thresholds()) == set(ids)


def test_thresholds_merge_clamps_and_ignores_junk():
    thr = triage.merge_thresholds({"valve": {"hyst_pct": 1e9, "zzz": 1}, "nope": {}, "tune": {"harris_min": "x"}})
    assert thr["valve"]["hyst_pct"] == triage.BY_ID["valve"].thresholds["hyst_pct"].hi
    assert thr["tune"]["harris_min"] == 0.5 and "zzz" not in thr["valve"]


def test_good_loop_ok_with_evidence():
    ms, (v, _) = run([("A", "good")])
    assert ms[0]["ok"] and ms[0]["auto_pct"] > 50
    assert v[0]["verdict"] == "ok" and v[0]["evidence"]


def test_stiction_loop():
    ms, (v, _) = run([("S", "stic")])
    assert ms[0]["osc"]
    assert v[0]["verdict"] == "valve" and v[0]["evidence"][0]["metric"] == "stic_ratio"


def test_oscillating_loop_needs_tuning():
    ms, (v, _) = run([("O", "osc")])
    assert ms[0]["osc"] and v[0]["verdict"] == "tune"


def test_mostly_manual_low_auto():
    ms, (v, _) = run([("M", "man")])
    assert ms[0]["auto_pct"] < 30
    assert v[0]["verdict"] == "low_auto" and v[0]["evidence"][0]["metric"] == "auto_pct"


def test_rules_are_pure_on_metrics():
    thr = triage.merge_thresholds(None)
    assert triage.evaluate(base_metrics(), thr)[0] == "ok"
    assert triage.evaluate(base_metrics(nonlin=5.0), thr)[0] == "nonlinear"
    assert triage.evaluate(base_metrics(hyst_pct=5.0), thr)[0] == "valve"
    assert triage.evaluate(base_metrics(harris=0.2), thr)[0] == "tune"
    assert triage.evaluate(base_metrics(auto_pct=5), thr)[0] == "low_auto"
    thr2 = triage.merge_thresholds({"nonlinear": {"nonlin_ratio": 10}})
    assert triage.evaluate(base_metrics(nonlin=5.0), thr2)[0] == "ok"


def test_cascade_and_foreign():
    m = base_metrics(harris=0.2, osc=True, period=300.0)
    slave = {**m, "name": "s", "stic": "likely", "stic_ratio": 0.1}
    thr = triage.merge_thresholds(None)
    assert triage.evaluate(m, thr, {"slave": slave})[0] == "cascade"
    assert triage.evaluate(m, thr, {"foreign": dict(source="s", period=300.0)})[0] == "foreign"
    v, com = triage.verdicts([{**m, "name": "m"}, {**slave, "period": 310.0}], {0: 1})
    assert len(com) == 1 and com[0]["source"] == 1          # zdroj = stikce
    assert v[0]["verdict"] == "foreign" and v[1]["verdict"] == "valve"


def test_common_periods_tolerance():
    mk = lambda p: dict(ok=True, osc=True, period=p, stic=None, std_e_pct=1.0)       # noqa: E731
    assert len(triage.common_periods([mk(100), mk(109), mk(300)])) == 1
    assert triage.common_periods([mk(100), mk(125)]) == []
