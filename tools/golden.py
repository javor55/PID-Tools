"""
Zlaté případy: výsledky dnešní aplikace na pevné sadě dat, se kterými se porovnává každá další verze
(i nové API a nové rozhraní – docs/cs/milniky.md, M1).

Každý případ načte data do pracovního prostoru bez UI (pidtools.app.workspace), spustí
identifikaci, návrh ladění, scénář, robustnost, frekvenční charakteristiky, diagnostiku a doporučení APC
a uloží čísla do tests/golden/<případ>.out.json. tests/test_golden.py je přepočítá a porovná s tolerancí.

    python tools/golden.py               # přepočítat a porovnat (jako test), vypsat rozdíly
    python tools/golden.py --update      # záměrně přegenerovat uložené výsledky (po vědomé změně výpočtů)
    python tools/golden.py --update demo_common tic001_open    # jen vybrané případy
"""
import json
import math
import os
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
GOLDEN = os.path.join(ROOT, "tests", "golden")
DATA = os.path.join(ROOT, "tests", "data")

RTOL = 0.02          # relativní tolerance porovnání (2 %)
ATOL = 1e-6          # absolutní tolerance u hodnot blízko nuly
SIG = 6              # platné číslice uložených výsledků


# ---- data případů
def _state():
    from pidtools.app.workspace import Workspace
    return Workspace()


def _project(name):
    with open(os.path.join(GOLDEN, name), encoding="utf-8") as f:
        return json.load(f)


def _from_cols(cols, mp, state=None, rng=None, tag="case"):
    proj = dict(version=2, tag=tag, fname=f"{tag}.csv", state=state or {}, map=mp,
                ranges={"id": list(rng) if rng else None, "val": None}, ff=[],
                data={"cols": {k: [float(x) for x in v] for k, v in cols.items()}})
    s = _state()
    s.apply_project(proj)
    return s


def _mixed_cols():
    """P1D (K 1,2; T 300 s; θ 60 s): 3 h ručně se skokem MV, pak 3 h v AUTO (Gain 1, TI 300) se změnami SP."""
    sys.path.insert(0, os.path.join(ROOT, "tests"))
    from test_mixed import mixed_record
    t, sp, pv, mv = mixed_record()
    return dict(t_s=t, PV=pv, MV=mv, SP=sp)


MAP1 = {"c_pv": "PV", "c_mv": "MV", "c_sp": "SP", "c_d": [], "c_pos": "—"}
SET_CL = dict(set1_gain=1.0, set1_ti=300.0, set1_td=0.0, pv_lo=0.0, pv_hi=100.0, mv_lo=0.0, mv_hi=100.0, samp=1.0)


def case_demo_common():
    """Ukázková hladina (integrační proces, odtokový ventil) s měřeným přítokem – společný úsek."""
    s = _state()
    s.load_demo()
    s.set(chosen=["P1D", "I1D"])
    return s, dict(methods="all", apc=True, diag=True)


def case_demo_inputs():
    """Ukázka – úseky podle vstupů (MV a porucha zvlášť)."""
    s = _state()
    s.load_demo()
    s.set(chosen=["I1D"], win_mode="inputs", **{"dkind|FI100.Pritok": "auto"})
    s.set_wins("MV", [[250, 1300], [2500, 3300]])
    s.set_wins("FI100.Pritok", [[850, 1750]])
    return s, dict(methods=("SIMC", "OPT"))


def case_ff_example():
    """
    Uživatelská data s měřenou poruchou (CV / MV / SP / DV, MV 125–135 %). Smyčka je celou dobu v AUTO, ale Set 1
    má výchozí zástupné hodnoty – režim „automaticky“ proto zůstane u otevřené smyčky.
    """
    import pandas as pd
    df = pd.read_csv(os.path.join(DATA, "ff_example.csv"))
    cols = {"t_s": (df["Sample#"] - 1).to_numpy(), "CV": df.CV.to_numpy(), "MV": df.MV.to_numpy(),
            "SP": df.SP.to_numpy(), "DV": df.DV.to_numpy()}
    s = _from_cols(cols, {"c_pv": "CV", "c_mv": "MV", "c_sp": "SP", "c_d": ["DV"], "c_pos": "—"}, tag="ff")
    s.set(chosen=["P1D", "P2D"])
    return s, dict(methods=("SIMC", "Lambda", "OPT"), diag=True, apc=True)


def case_tic001_saved():
    """Reálná teplotní smyčka (anonymizovaná) – úsek uložený v projektu obsahuje i data v AUTO (θ ≈ 0, varování)."""
    s = _state()
    s.apply_project(_project("tic001.json"))
    s.set(chosen=["P1D"], id_mode="open")
    return s, dict(methods=("SIMC", "Lambda", "OPT"), checks=True, diag=True)


def case_tic001_open():
    """Reálná teplotní smyčka – jen ruční úsek 5,0–8,6 h (otevřená smyčka)."""
    s = _state()
    s.apply_project(_project("tic001.json"))
    s.set(chosen=["P1D", "P2D"], id_mode="open")
    s.rng = (5.0 * 3600, 8.6 * 3600)
    return s, dict(methods=("SIMC", "Lambda", "OPT"), checks=True, apc=True)


def case_tic001_mixed():
    """
    Reálná teplotní smyčka – kombinovaná identifikace: ruční úsek MV + úsek v AUTO (Set 1 z projektu). Rozsah PV
    v projektu (0–100) data nepokrývá (98–101 °C), vyřazení dat podle mezí PV je proto vypnuté.
    """
    s = _state()
    s.apply_project(_project("tic001.json"))
    s.set(chosen=["P1D"], id_mode="auto", win_mode="inputs")
    s.excl["PV"] = [False, 0.0, 100.0]
    s.set_wins("MV", [[5.0 * 3600, 8.6 * 3600], [8.65 * 3600, 11.1 * 3600]])
    return s, dict(methods=("SIMC",), checks=True)


def case_synth_mixed():
    """Syntetická smyčka: ruční úsek + úsek v AUTO, kombinovaná identifikace (známý proces K 1,2, T 300, θ 60)."""
    s = _from_cols(_mixed_cols(), MAP1, dict(SET_CL), tag="mix")
    s.set(chosen=["P1D"], thmax=1000.0, id_mode="auto", win_mode="inputs")
    s.set_wins("MV", [[3000, 10700], [11000, 21500]])
    return s, dict(methods=("SIMC", "OPT"))


def case_synth_closed():
    """
    Syntetická smyčka jen v AUTO – identifikace v uzavřené smyčce (nepřímá metoda se Set 1). Úsek začíná v ustáleném
    stavu: se začátkem uprostřed přechodu metoda uvízne v lokálním minimu θ (známé omezení, docs/cs/milniky.md).
    """
    s = _from_cols(_mixed_cols(), MAP1, dict(SET_CL), rng=(10800.0, 21600.0), tag="cl")
    s.set(chosen=["P1D"], thmax=1000.0, id_mode="cl")
    return s, dict(methods=("SIMC",), diag=True)


CASES = {n[5:]: f for n, f in sorted(globals().items()) if n.startswith("case_")}


# ---- výpočet
def _r(x):
    """Zaokrouhlení na SIG platných číslic; numpy → Python; nekonečna / NaN jako text."""
    if isinstance(x, dict):
        return {str(k): _r(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_r(v) for v in x]
    if isinstance(x, np.ndarray):
        return _r(x.tolist())
    if isinstance(x, (bool, np.bool_)):
        return bool(x)
    if isinstance(x, (int, np.integer)):
        return int(x)
    if isinstance(x, (float, np.floating)):
        x = float(x)
        if not math.isfinite(x):
            return str(x)
        return float(f"{x:.{SIG}g}")
    return x


def _model_rec(r):
    out = dict(p=r["p"], fit=r.get("fit"))
    for k in ("pdl", "stic", "fit_cl_pv", "fit_cl_mv", "p_open", "method", "mixed"):
        if r.get(k) is not None:
            out[k] = r[k]
    if out.get("pdl"):
        out["pdl"] = [list(q[:3]) + list(q[4:5]) for q in out["pdl"]]      # bez kódu struktury (index 3)
    return out


def _kpis(k):
    if not k:
        return None
    out = {n: k[n] for n in ("iae", "maxdev", "mv_travel", "reversals") if n in k}
    st = k.get("step") or {}
    out.update({f"step_{n}": st.get(n) for n in ("t90", "over", "settle")})
    return out


def run_case(name):
    """Výsledky případu jako slovník (zaokrouhlený, JSON)."""
    from pidtools.app import frequency as fq
    from pidtools.app import loopmode as lm
    s, opt = CASES[name]()
    g = s.grid
    out = {"data": dict(n=len(s.t), Ts=g.Ts, has_sp=g.has_sp, rng=list(s.rng))}
    q = s.quality()
    if q:
        out["quality"] = dict(level=q["level"], checks=[c[0] for c in q["checks"]], snr=q.get("snr"),
                              n_steps=q.get("n_steps"))
    det = s.loop_det()
    out["loopmode"] = dict(frac=det["frac"], runs=[(a, b, k) for a, b, k in det["runs"]], auto_frac=s.auto_frac(),
                           eff=s.id_mode_eff, mv_modes=s.mv_modes())
    errs = s.identify()
    res = s.fit["res"] if s.fit else {}
    out["model"] = dict(errors=[list(e) for e in errs], best=s.get("mcode"),
                        res={c: _model_rec(r) for c, r in sorted(res.items())})
    if not res:
        return _r(out)
    code, p, pdl = s.model
    Ts = float(g.Ts)
    out["model"]["checks"] = [k for k, _ in lm.model_checks(code, p, Ts)]
    # ladění: návrhy metod, robustnost návrhů a sady 1
    meths = s.methods() if opt.get("methods") == "all" else [m for m in opt.get("methods", ()) if m in s.methods()]
    tun_out, sug = {}, None
    for m in meths:
        r = s.suggest(m)
        rec = dict(Kc=r["Kc"], Ti=r["Ti"], Td=r["Td"], notes=[n for n, _ in r.get("notes", [])])
        if opt.get("checks"):
            rec["checks"] = [k for k, _ in lm.tuning_checks(code, p, r["Kc"], Ts, float(s.get("set1_gain")))]
        tun_out[m] = rec
        sug = sug or dict(Kc=r["Kc"], Ti=r["Ti"], Td=r["Td"])
    out["tuning"] = tun_out
    out["set1_metrics"] = {k: v for k, v in s.set_metrics(1).items() if k != "Ms_worst"}
    # scénář: sada 1 a první návrh
    sim = s.simulate(preview=sug)
    out["scenario"] = dict(T_end=sim["T_end"], set1=_kpis(sim["kpis"].get(1)), sug=_kpis(sim["kpis"].get("sug")))
    # frekvenční charakteristiky: šířka pásma a Ms pro sadu 1 a návrh
    sets = {"set1": s.set_ctrl(1)}
    if sug:
        sets["sug"] = s.ctrl_of(sug)
    fr = fq.compare(code, p, sets)
    out["frequency"] = {n: dict(bw=fq.bandwidth(r), Ms=float(np.max(np.abs(r["S"])))) for n, r in fr.items()}
    if opt.get("diag"):
        out["diag"] = _diag(s)
    if opt.get("apc"):
        out["apc"] = _apc(s)
    return _r(out)


def _diag(s):
    code = s.model[0]
    out = dict(kpis=_plain(s.diag_kpis(*s.rng)), valve=_plain(s.valve(*s.rng, code.startswith("I"))))
    nl = s.nonlinearity()
    if nl is not None:
        out["nonlinearity"] = dict(n=len(nl[0]), spread=nl[1])
    return out


def _plain(d):
    """Jen čísla, texty a jejich seznamy (bez polí s průběhy) – pro uložení."""
    if isinstance(d, dict):
        out = {}
        for k, v in d.items():
            if isinstance(v, np.ndarray) and v.size > 10:
                continue
            if isinstance(v, (list, tuple)) and len(v) > 10:
                continue
            pv = _plain(v)
            if pv is not None:
                out[str(k)] = pv
        return out
    if isinstance(d, (list, tuple)):
        return [_plain(v) for v in d]
    if isinstance(d, (str, bool, int, float, np.number, np.bool_)) or d is None:
        return d
    if isinstance(d, np.ndarray):
        return d.tolist()
    return None


def _apc(s):
    from pidtools.app.apc import recommend as rc
    from pidtools.app.apc import smith as sm
    code, p, pdl = s.model
    ts, pv, mv, d = s.segment()
    out = dict(delay_ratio=rc.delay_ratio(code, p), smith_tc=sm.tc_default(p, float(s.get("samp")), "SIMC"))
    if pdl:
        out["nl_spread"] = rc.nl_spread(code, p, pdl, ts, pv, mv, d, s.grid.Ts)
    return _plain(out)


# ---- porovnání
def compare(ref, new, path="", rtol=RTOL, atol=ATOL):
    """Rozdíly [(cesta, uložené, nové)] – čísla s tolerancí, ostatní přesně."""
    diffs = []
    if isinstance(ref, dict) and isinstance(new, dict):
        for k in sorted(set(ref) | set(new)):
            if k not in ref or k not in new:
                diffs.append((f"{path}/{k}", ref.get(k, "—chybí—"), new.get(k, "—chybí—")))
            else:
                diffs += compare(ref[k], new[k], f"{path}/{k}", rtol, atol)
    elif isinstance(ref, list) and isinstance(new, list):
        if len(ref) != len(new):
            diffs.append((path + "#len", len(ref), len(new)))
        elif _is_params(path, ref):
            # parametry přenosu [K, časy…]: časy s tolerancí z největší časové konstanty – malé, špatně určitelné
            # členy (např. T2 ≪ T1 pod periodou dat) se mezi platformami liší víc než o 2 % své hodnoty
            at = max(atol, rtol * max(abs(x) for x in ref[1:]))
            for i, (a, b) in enumerate(zip(ref, new)):
                diffs += compare(a, b, f"{path}[{i}]", rtol, atol if i == 0 else at)
        else:
            for i, (a, b) in enumerate(zip(ref, new)):
                diffs += compare(a, b, f"{path}[{i}]", rtol, atol)
    elif isinstance(ref, int) and isinstance(new, int):          # počty (vzorky, kroky, obraty) přesně
        if ref != new:
            diffs.append((path, ref, new))
    elif isinstance(ref, (int, float)) and isinstance(new, (int, float)):
        if not math.isclose(ref, new, rel_tol=rtol, abs_tol=atol):
            diffs.append((path, ref, new))
    elif ref != new:
        diffs.append((path, ref, new))
    return diffs


def _is_params(path, ref):
    """Parametry přenosu procesu / poruchy ve výsledku modelu (…/p, …/p_open, …/pdl[j])."""
    tail = path.rsplit("/", 1)[-1]
    return (len(ref) > 1 and all(isinstance(x, (int, float)) for x in ref)
            and (tail in ("p", "p_open") or tail.startswith("pdl[")))


def path_of(name):
    return os.path.join(GOLDEN, f"{name}.out.json")


def load(name):
    with open(path_of(name), encoding="utf-8") as f:
        return json.load(f)


def save(name, res):
    with open(path_of(name), "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write("\n")


def main(argv):
    update = "--update" in argv
    names = [a for a in argv if not a.startswith("--")] or list(CASES)
    bad = 0
    for n in names:
        t0 = time.time()
        res = run_case(n)
        dt = time.time() - t0
        if update:
            save(n, res)
            print(f"{n}: uloženo ({dt:.1f} s)")
            continue
        d = compare(load(n), res)
        print(f"{n}: {'OK' if not d else f'{len(d)} rozdílů'} ({dt:.1f} s)")
        for x in d[:30]:
            print("   ", *x)
        bad += bool(d)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
