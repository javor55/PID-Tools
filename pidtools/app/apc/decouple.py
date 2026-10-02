"""APC – rozvazbení 2×2: vazby mezi smyčkami, RGA, decouplery, simulace a parametry pro PCS 7."""
import numpy as np

from ...core import iae
from ...core.apc import ff_design, mimo2_sim, rga2
from .common import cross_model, grid, tchar


def gain_eng(d, src, dst):
    """Zesílení decoupleru v inženýrských jednotkách: ΔMV_dst [j.] / ΔMV_src [j.]."""
    return d["gain"] * (dst["mv_rng"][1] - dst["mv_rng"][0]) / (src["mv_rng"][1] - src["mv_rng"][0])


def design(a, b):
    """Rozvazbení dvou smyček: vzájemné vazby z modelů měřených poruch, decouplery (ff_design) a RGA λ₁₁."""
    xab, xba = cross_model(a, b), cross_model(b, a)
    ga, gb = (a["model"][0], list(a["model"][1])), (b["model"][0], list(b["model"][1]))
    return dict(ga=ga, gb=gb, xab=xab, xba=xba,
                dab=ff_design(*ga, xab) if xab else None, dba=ff_design(*gb, xba) if xba else None,
                lam=rga2(ga[1][0], xab[0] if xab else 0.0, xba[0] if xba else 0.0, gb[1][0]))


def simulate(dz, ctrl_a, ctrl_b, amp_a, amp_b, sim=None):
    """
    Simulace změn SP obou smyček (A v 5 %, B v 50 % délky; amplitudy v %) bez rozvazbení, se statickými a
    s dynamickými decouplery. Vrací {"none" | "static" | "dyn": (čas, průběhy)}.
    """
    sim = sim or mimo2_sim
    t_end = 14 * max(tchar(dz["ga"]), tchar(dz["gb"])) + 200 * max(ctrl_a["SampleTime"], ctrl_b["SampleTime"])
    h, n, t = grid(t_end, min(ctrl_a["SampleTime"], ctrl_b["SampleTime"]))
    sp_a = np.where(t >= 0.05 * t_end, 50.0 + amp_a, 50.0)
    sp_b = np.where(t >= 0.5 * t_end, 50.0 + amp_b, 50.0)
    runs = {}
    for v in ("none", "static", "dyn"):
        on = v != "none"
        runs[v] = sim(dz["ga"], dz["gb"], dz["xab"], dz["xba"], ctrl_a, ctrl_b, h, sp_a, sp_b,
                      dz["dab"] if on else None, dz["dba"] if on else None, v == "dyn")
    return runs


def iae_table(runs, a, b):
    """IAE obou smyček v jednotkách PV pro každou variantu: [(varianta, IAE A, IAE B)]."""
    out = []
    for v in ("none", "static", "dyn"):
        t, o = runs[v]
        out.append((v, iae(t, o["SP_A"], o["PV_A"]) * (a["pv_rng"][1] - a["pv_rng"][0]) / 100,
                    iae(t, o["SP_B"], o["PV_B"]) * (b["pv_rng"][1] - b["pv_rng"][0]) / 100))
    return out


def params(dz, a, b):
    """Parametry decouplerů pro PCS 7: [(zdroj MV, cílová smyčka, zesílení %, zesílení v jedn., lead, lag, zpoždění)]."""
    out = []
    for d, src, dst in ((dz["dab"], b, a), (dz["dba"], a, b)):
        if d is not None:
            out.append((src["c_mv"], dst["name"], d["gain"], gain_eng(d, src, dst), d["lead"], d["lag"], d["delay"]))
    return out
