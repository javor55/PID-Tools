"""
APC – Smithův prediktor: regulátor pro model bez zpoždění (metoda, τc), obecné hodnoty prediktoru, z čeho výpočet
vychází, a hodnoty pro bloky šablony SmithPredictorControl.
"""
import numpy as np

from ...core import tune
from ...core.apc import no_delay, smith_apl

# metody návrhu regulátoru pro model bez zpoždění
METHODS = ("SIMC", "Lambda", "OPT", "manual")
DEFAULT_METHOD = "SIMC"
# chyby modelu [%] (zesílení, časové konstanty, zpoždění), na kterých robustní optimalizace hodnotí regulátor:
# nominální model, delší a kratší zpoždění (podhodnocené θ je pro prediktor nebezpečné) a jiné zesílení
OPT_ERRORS = ((0, 0, 0), (0, 0, 20), (30, 0, 20), (-30, 0, -20))
OPT_STEPS = 1000


def tc0(p, samp):
    """
    Výchozí τc = θ/2: s prediktorem regulátor zpoždění „nevidí“, takže může být rychlejší než běžné PID (u PID
    je SIMC τc = θ). Kratší τc už prediktor dělá citlivým na chybu zpoždění a zesílení.
    """
    lags = float(sum(p[1:-1]))
    return float(max(0.5 * p[-1], 2 * samp, 0.05 * lags))


def tc_default(p, samp, method):
    """Výchozí τc podle metody: SIMC θ/2 (tc0), Lambda λ = součet časových konstant (uzavřená smyčka zhruba
    stejně rychlá jako otevřená – obvyklá průmyslová volba)."""
    if method == "Lambda":
        return float(max(sum(p[1:-1]), 2 * samp))
    return tc0(p, samp)


def operating_point(pv_id, mv_id):
    """Pracovní bod [%] = začátek úseku identifikace (ustálený stav před prvním skokem)."""
    n0 = max(3, len(pv_id) // 20)
    return float(np.nanmedian(pv_id[:n0])), float(np.nanmedian(mv_id[:n0]))


def plant_error(p, ek=0.0, et=0.0, eth=0.0):
    """Proces s chybou modelu: zesílení, časové konstanty a zpoždění změněné o ek, et, eth [%]."""
    q = list(p)
    q[0] *= 1 + ek / 100
    for i in range(1, len(q) - 1):
        q[i] *= 1 + et / 100
    q[-1] *= 1 + eth / 100
    return q


def _scenario(p, samp, n_max=None):
    """Mřížka a průběhy srovnání: skok SP o 5 % v 5 % délky, porucha 5 % na vstupu procesu v polovině."""
    from .common import grid
    lags = float(sum(p[1:-1]))
    t_end = 30 * (p[-1] + lags) + 200 * samp
    if n_max:
        h = max(t_end / n_max, min(samp, t_end / n_max))
        n = int(t_end / h) + 1
        t = np.arange(n) * h
    else:
        h, n, t = grid(t_end, samp)
    sp = np.where(t >= 0.05 * t_end, 55.0, 50.0)
    d = np.where(t >= 0.5 * t_end, 5.0, 0.0)
    return h, t, sp, d, t_end


def _ctrl(base_ctrl, r):
    from .common import clean
    return dict(clean(base_ctrl), Gain=r["Kc"], TI=r["Ti"] if r["Ti"] > 0 else np.inf, TD=r["Td"])


def optimize(code, p, ctype, samp, base_ctrl, start, smith_fn=None, errors=OPT_ERRORS):
    """
    Robustní optimalizace regulátoru Smithova prediktoru: minimum průměrné IAE (skok SP + porucha na vstupu) přes
    nominální proces a procesy s chybou modelu (OPT_ERRORS); start = návrh SIMC. Simulace na hrubší mřížce.
    """
    from scipy.optimize import minimize

    from ...core import iae
    from ...core.apc import smith_sim
    smith_fn = smith_fn or smith_sim
    h, t, sp, d, t_end = _scenario(p, samp, OPT_STEPS)
    plants = [plant_error(p, *e) for e in errors]
    pid = ctype == "PID" and start["Td"] > 0
    x0 = np.log([max(abs(start["Kc"]), 1e-9), max(start["Ti"], 1e-6)] + ([start["Td"]] if pid else []))
    sgn = 1.0 if start["Kc"] >= 0 else -1.0

    def rr(x):
        return dict(Kc=sgn * float(np.exp(x[0])), Ti=float(np.exp(x[1])), Td=float(np.exp(x[2])) if pid else 0.0)

    def cost(x):
        c = _ctrl(base_ctrl, rr(x))
        J = 0.0
        for q in plants:
            _, o = smith_fn(code, q, list(p), c, h, sp, d)
            pv = o["PV"]
            if not np.all(np.isfinite(pv)) or np.max(np.abs(pv[-len(pv) // 10:] - 55.0)) > 2.0:
                return 1e12                      # nestabilní nebo trvale kmitá
            J += iae(t, sp, pv)
        return J / len(plants)

    res = minimize(cost, x0, method="Nelder-Mead", options=dict(maxiter=60 * len(x0), xatol=0.02, fatol=1e-3))
    best = res.x if res.fun < cost(x0) else x0
    r = rr(best)
    return dict(r, notes=[("sm_opt_note", {})])


def controller(code, p, method, ctype, tc, samp, base_ctrl=None, manual=None, smith_fn=None):
    """
    Regulátor pro Smithův prediktor (navržený na model bez zpoždění): SIMC (τc), Lambda (λ = τc, TI = T),
    OPT = robustní optimalizace na smyčce s prediktorem (start SIMC), manual = (Gain, TI, TD) zadané uživatelem.
    """
    tc = tc or tc_default(p, samp, method)
    if method == "manual" and manual:
        g, ti, td = (float(x) for x in manual)
        return dict(Kc=g, Ti=ti, Td=td if ctype == "PID" else 0.0, notes=[])
    p0 = no_delay(p)
    if method == "Lambda":
        return tune(code, p0, "Lambda", tc, ctype, samp)
    r = tune(code, p0, "SIMC", tc, ctype, samp)
    if method == "OPT" and base_ctrl is not None:
        return optimize(code, p, ctype, samp, base_ctrl, r, smith_fn)
    return r


def values(code, p, sc, pv_op, mv_op, ctype, tc, samp, u_pv="PV", u_mv="MV", r=None):
    """
    Hodnoty pro šablonu: (výsledek smith_apl, regulátor, řádky [(blok, vstup, hodnota, jedn.)]).
    sc: převody jednotek (Scaling); pv_op, mv_op: pracovní bod v %; r = regulátor (None = SIMC s τc).
    """
    v = smith_apl(p, sc.PR, sc.MR, float(sc.EP(pv_op)), float(sc.EM(mv_op)))
    r = r or tune(code, no_delay(p), "SIMC", tc or tc0(p, samp), ctype, samp)
    rows = [("SmithModelTimLag (Lag)", "LagTime", v["lag"], "s"),
            ("SmithModelGain (Mul04)", "In2", v["k"], f"{u_pv}/{u_mv}"),
            ("PV0 (Add04)", "In2", v["pv0"], u_pv),
            ("SmithModelDeadti (DeadTime)", "DeadTime", v["theta"], "s"),
            ("PIDConL", "Gain", r["Kc"], "–"),
            ("PIDConL", "TI", r["Ti"], "s")]
    if ctype == "PID":
        rows.append(("PIDConL", "TD", r["Td"], "s"))
    return v, r, rows


def basis_text(code, p, sc, pv_op, mv_op, samp, u_pv="PV", u_mv="MV"):
    """Z čeho výpočet vychází (text sm_basis): model a jeho parametry, rozsahy bloku, pracovní bod, SampleTime."""
    from ...i18n import T

    def f(x):
        return f"{x:.4g}"
    lags = float(sum(p[1:-1]))
    return T("sm_basis", m=T("model_" + code), k=f(p[0]), kk=f(p[0] * sc.PR / sc.MR), u=f"{u_pv}/{u_mv}",
             t1=f(p[1]), t2=f", T2 = {f(p[2])} s" if code == "P2D" else "", th=f(p[-1]),
             r=f"{p[-1] / max(p[-1] + lags, 1e-9):.2f}", pv=f"{sc.pv_lo:g}–{sc.pv_hi:g} {u_pv}",
             mv=f"{sc.mv_lo:g}–{sc.mv_hi:g} {u_mv}", pvop=f"{f(sc.EP(pv_op))} {u_pv}", mvop=f"{f(sc.EM(mv_op))} {u_mv}",
             samp=f"{samp:g}")


def general_rows(code, p, sc, pv_op, mv_op, r, tc, method, ctype, u_pv="PV", u_mv="MV"):
    """
    Obecné hodnoty Smithova prediktoru (nezávislé na šabloně): [(klíč textu, hodnota, jednotka)].
    Model bez zpoždění G0 = K/(T1·s + 1)(T2·s + 1), zpoždění θ, pracovní bod a regulátor.
    """
    v = smith_apl(p, sc.PR, sc.MR, float(sc.EP(pv_op)), float(sc.EM(mv_op)))
    rows = [("smg_k", v["k"], f"{u_pv}/{u_mv}"), ("smg_k_pct", float(p[0]), "%/%"), ("smg_t1", float(p[1]), "s")]
    if code == "P2D":
        rows.append(("smg_t2", float(p[2]), "s"))
    rows += [("smg_theta", v["theta"], "s"), ("smg_pv_op", float(sc.EP(pv_op)), u_pv),
             ("smg_mv_op", float(sc.EM(mv_op)), u_mv), ("smg_pv0", v["pv0"], u_pv),
             ("smg_gain", r["Kc"], "–"), ("smg_ti", r["Ti"], "s")]
    if ctype == "PID":
        rows.append(("smg_td", r["Td"], "s"))
    if method in ("SIMC", "Lambda"):
        rows.append(("smg_tc", float(tc), "s"))
    return rows


def simulate(code, p, plant, base_ctrl, pid_ctrl, ctype, tc, samp, smith_fn=None, pid_fn=None, r=None):
    """
    Skok SP (5 %) a porucha na vstupu (50 % délky): Smithův prediktor s regulátorem r (None = SIMC pro model bez
    zpoždění) vs. PID (pid_ctrl) na procesu plant. Vrací dict(t, sp, smith = (čas, výsledek), pid = (čas, PV, MV),
    r = regulátor, iae = {"smith" | "pid": (IAE SP, IAE porucha)} v %·s).
    """
    from ...core import iae, pidconl_sim
    from ...core.apc import smith_sim
    from .common import clean
    smith_fn, pid_fn = smith_fn or smith_sim, pid_fn or pidconl_sim
    r = r or tune(code, no_delay(p), "SIMC", tc or tc0(p, samp), ctype, samp)
    h, t, sp, d, t_end = _scenario(p, samp)
    tt, o = smith_fn(code, plant, list(p), _ctrl(base_ctrl, r), h, sp, d)
    tb, _, PVb, MVb = pid_fn(code, plant, [], h, sp, 50.0, 50.0, clean(pid_ctrl), [], d)
    half = t < 0.5 * t_end

    def ia(tx, pv):
        return iae(tx[half], sp[half], pv[half]), iae(tx[~half], sp[~half], pv[~half])
    return dict(t=t, sp=sp, smith=(tt, o), pid=(tb, PVb, MVb), r=r, iae=dict(smith=ia(tt, o["PV"]), pid=ia(tb, PVb)))
