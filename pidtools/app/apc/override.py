"""APC – override: hlavní a omezující regulátor na jednom ventilu, výběr MIN/MAX s externím resetem."""
import numpy as np

from ...core import MODELS
from ...core.apc import override_sim
from .common import clean, eng, grid, tchar


def defaults(a, b, sel):
    """
    Výchozí scénář: změna SP hlavní smyčky A žene MV směrem, který omezení hlídá; mez smyčky B v půlce očekávané
    změny PV_B. Vrací (skok SP A [jednotky PV_A], mez B [jednotky PV_B]).
    """
    ka, kb = a["model"][1][0], b["model"][1][0]
    dir_mv = 1.0 if sel == "min" else -1.0
    PRa = a["pv_rng"][1] - a["pv_rng"][0]
    PRb = b["pv_rng"][1] - b["pv_rng"][0]
    step = round(dir_mv * np.sign(ka) * 0.2 * PRa, 4)
    dmv = 20.0 if MODELS[a["model"][0]]["integ"] else min(abs(0.2 * 100 / ka), 40.0)
    dpvb = 10.0 * np.sign(kb) * dir_mv if MODELS[b["model"][0]]["integ"] else kb * dir_mv * dmv
    lim = round(b["pv_rng"][0] + PRb / 2 + 0.5 * np.clip(dpvb, -45, 45) * PRb / 100, 4)
    return step, lim


def simulate(a, b, step_a, lim, sel, sim=override_sim):
    """Simulace s výběrem (o) a bez něj (o0, jen hlavní regulátor). Vrací (čas, o, o0)."""
    ga, gb = (a["model"][0], list(a["model"][1])), (b["model"][0], list(b["model"][1]))
    ctrl_a, ctrl_b = clean(a["ctrl"]), clean(b["ctrl"])
    PRa = a["pv_rng"][1] - a["pv_rng"][0]
    PRb = b["pv_rng"][1] - b["pv_rng"][0]
    t_end = 14 * max(tchar(ga), tchar(gb)) + 200 * max(ctrl_a["SampleTime"], ctrl_b["SampleTime"])
    h, n, t = grid(t_end, min(ctrl_a["SampleTime"], ctrl_b["SampleTime"]))
    sp_a = np.where(t >= 0.05 * t_end, 50.0 + step_a / PRa * 100, 50.0)
    sp_a[t >= 0.6 * t_end] = 50.0
    sp_b = np.full(n, (lim - b["pv_rng"][0]) / PRb * 100)
    tt, o = sim(ga, gb, ctrl_a, ctrl_b, h, sp_a, sp_b, sel, True)
    _, o0 = sim(ga, gb, ctrl_a, ctrl_b, h, sp_a, sp_b, sel, False)
    return tt, o, o0


def kpis(a, b, o, o0, sel):
    """Nejhorší PV_B s výběrem a bez něj [jednotky PV_B], podíl času řízení omezujícím regulátorem, počet přepnutí."""
    kb = b["model"][1][0]
    dir_mv = 1.0 if sel == "min" else -1.0
    worst = np.max if np.sign(kb) * dir_mv > 0 else np.min
    EB = eng(b["pv_rng"])
    return dict(peak=float(EB(worst(o["PV_B"]))), peak_without=float(EB(worst(o0["PV_B"]))),
                share=float(np.mean(o["ACT"])), switches=int(np.abs(np.diff(o["ACT"])).sum()))


def active_spans(act, limit=50):
    """Úseky (od, do) indexů, kdy řídí omezující regulátor."""
    a = np.r_[0, act, 0]
    starts, ends = np.where(np.diff(a) == 1)[0], np.where(np.diff(a) == -1)[0]
    return list(zip(starts, ends))[:limit]
