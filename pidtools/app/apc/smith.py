"""APC – Smithův prediktor: výchozí τc a hodnoty pro bloky šablony SmithPredictorControl."""
import numpy as np

from ...core import tune
from ...core.apc import no_delay, smith_apl


def tc0(p, samp):
    """Výchozí τc = θ: rychlost jako SIMC, ale bez penalizace za zpoždění."""
    lags = float(sum(p[1:-1]))
    return float(max(p[-1], 2 * samp, 0.05 * lags))


def operating_point(pv_id, mv_id):
    """Pracovní bod [%] = začátek úseku identifikace (ustálený stav před prvním skokem)."""
    n0 = max(3, len(pv_id) // 20)
    return float(np.nanmedian(pv_id[:n0])), float(np.nanmedian(mv_id[:n0]))


def values(code, p, sc, pv_op, mv_op, ctype, tc, samp, u_pv="PV", u_mv="MV"):
    """
    Hodnoty pro šablonu: (výsledek smith_apl, regulátor pro model bez zpoždění, řádky [(blok, vstup, hodnota, jedn.)]).
    sc: převody jednotek (Scaling); pv_op, mv_op: pracovní bod v %.
    """
    v = smith_apl(p, sc.PR, sc.MR, float(sc.EP(pv_op)), float(sc.EM(mv_op)))
    r = tune(code, no_delay(p), "SIMC", tc or tc0(p, samp), ctype, samp)
    rows = [("SmithModelTimLag (Lag)", "LagTime", v["lag"], "s"),
            ("SmithModelGain (Mul04)", "In2", v["k"], f"{u_pv}/{u_mv}"),
            ("PV0 (Add04)", "In2", v["pv0"], u_pv),
            ("SmithModelDeadti (DeadTime)", "DeadTime", v["theta"], "s"),
            ("PIDConL", "Gain", r["Kc"], "–"),
            ("PIDConL", "TI", r["Ti"], "s")]
    if ctype == "PID":
        rows.append(("PIDConL", "TD", r["Td"], "s"))
    return v, r, rows
