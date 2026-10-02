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


def plant_error(p, ek=0.0, et=0.0, eth=0.0):
    """Proces s chybou modelu: zesílení, časové konstanty a zpoždění změněné o ek, et, eth [%]."""
    q = list(p)
    q[0] *= 1 + ek / 100
    for i in range(1, len(q) - 1):
        q[i] *= 1 + et / 100
    q[-1] *= 1 + eth / 100
    return q


def simulate(code, p, plant, base_ctrl, pid_ctrl, ctype, tc, samp, smith_fn=None, pid_fn=None):
    """
    Skok SP (5 %) a porucha na vstupu (50 % délky): Smithův prediktor s regulátorem pro model bez zpoždění vs. PID
    (pid_ctrl) na procesu plant. Vrací dict(t, sp, smith = (čas, výsledek), pid = (čas, PV, MV), r = regulátor,
    iae = {"smith" | "pid": (IAE SP, IAE porucha)} v %·s).
    """
    from ...core import iae, pidconl_sim
    from ...core.apc import smith_sim
    from .common import clean, grid, tchar
    smith_fn, pid_fn = smith_fn or smith_sim, pid_fn or pidconl_sim
    lags = tchar((code, p)) - p[-1]
    r = tune(code, no_delay(p), "SIMC", tc or tc0(p, samp), ctype, samp)
    ctrl_s = dict(clean(base_ctrl), Gain=r["Kc"], TI=r["Ti"] if r["Ti"] > 0 else np.inf, TD=r["Td"])
    t_end = 30 * (p[-1] + lags) + 200 * samp
    h, n, t = grid(t_end, samp)
    sp = np.where(t >= 0.05 * t_end, 55.0, 50.0)
    d = np.where(t >= 0.5 * t_end, 5.0, 0.0)
    tt, o = smith_fn(code, plant, list(p), ctrl_s, h, sp, d)
    tb, _, PVb, MVb = pid_fn(code, plant, [], h, sp, 50.0, 50.0, clean(pid_ctrl), [], d)
    half = t < 0.5 * t_end

    def ia(tx, pv):
        return iae(tx[half], sp[half], pv[half]), iae(tx[~half], sp[~half], pv[~half])
    return dict(t=t, sp=sp, smith=(tt, o), pid=(tb, PVb, MVb), r=r, iae=dict(smith=ia(tt, o["PV"]), pid=ia(tb, PVb)))
