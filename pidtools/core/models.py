"""
Struktury modelů procesu, simulace jejich odezvy a predikce PV z naměřených dat.

Všechny procesní veličiny PV, SP, MV jsou v % normovacího rozsahu (NormPV, NormMV),
takže zesílení procesu i Gain regulátoru jsou bezrozměrné (%/%).
Měřené poruchy zůstávají v inženýrských jednotkách.

Modely MV -> PV (všechny s dopravním zpožděním θ):
  P0D : K · e^(-θs)
  P1D : K · e^(-θs) / (T1 s + 1)
  P2D : K · e^(-θs) / ((T1 s + 1)(T2 s + 1))
  I0D : Ki · e^(-θs) / s
  I1D : Ki · e^(-θs) / (s (T1 s + 1))
Model poruchy -> PV: Kd · e^(-θd s) / (Tp s + 1), u integračních procesů navíc · 1/s.
"""
import numpy as np

from .util import lag as _lag

MODELS = {
    "P0D": dict(name="0. řád (zesílení + zpoždění)", params=["K", "θ"], integ=False),
    "P1D": dict(name="1. řád + zpoždění (FOPDT)", params=["K", "T1", "θ"], integ=False),
    "P2D": dict(name="2. řád + zpoždění (SOPDT)", params=["K", "T1", "T2", "θ"], integ=False),
    "I0D": dict(name="Integrační + zpoždění", params=["Ki", "θ"], integ=True),
    "I1D": dict(name="Integrační + 1. řád + zpoždění", params=["Ki", "T1", "θ"], integ=True),
}
DIST_PARAMS = ["Kd", "Tp", "θd"]


def n_free(code: str) -> int:
    return len(MODELS[code]["params"]) - 1

# ================================================================ simulace modelu
def simulate(code: str, p: list[float], t: np.ndarray, du: np.ndarray, h: float) -> np.ndarray:
    """Odezva MV -> PV (odchylka) na odchylku MV `du`, rovnoměrná mřížka s krokem h."""
    ud = np.interp(t - p[-1], t, du, left=0.0)
    if code == "P0D":
        return p[0] * ud
    if code == "P1D":
        return p[0] * _lag(ud, p[1], h)
    if code == "P2D":
        return p[0] * _lag(_lag(ud, p[1], h), p[2], h)
    if code == "I0D":
        return p[0] * np.cumsum(ud) * h
    if code == "I1D":
        return p[0] * np.cumsum(_lag(ud, p[1], h)) * h
    raise ValueError(code)


def simulate_dist(integ, pd, t, dd, h):
    K, T, th = pd
    y = K * _lag(np.interp(t - th, t, dd, left=0.0), T, h)
    return np.cumsum(y) * h if integ else y


def model_dev(code, p, pdl, t, du, dD, h):
    y = simulate(code, p, t, du, h)
    integ = MODELS[code]["integ"]
    for pd, dd in zip(pdl, dD):
        y = y + simulate_dist(integ, pd, t, dd, h)
    return y


def fit_percent(y, yhat):
    den = np.linalg.norm(y - y.mean())
    return float("nan") if den == 0 else 100.0 * (1 - np.linalg.norm(y - yhat) / den)


def stiction_valve(u: np.ndarray, S: float, J: float = None) -> np.ndarray:
    """
    Jednoduchý model stikce ventilu (stick-slip): ventil stojí, dokud se výstup regulátoru nevzdálí
    od jeho polohy o víc než S; pak skočí na u − sign·(S − J). J = S (výchozí) = čistá stikce, J = 0 = vůle.
    """
    u = np.asarray(u, float)
    if S is None or S <= 0:
        return u.copy()
    J = S if J is None else min(max(J, 0.0), S)
    v = np.empty_like(u)
    x = u[0]
    for k, uk in enumerate(u):
        d = uk - x
        if abs(d) > S:
            x = uk - np.sign(d) * (S - J)
        v[k] = x
    return v


def high_pass(x, Th, h):
    """Horní propust 1. řádu (odstraní pomalé změny delší než ~Th)."""
    x = np.asarray(x, float) - x[0]
    return x - _lag(x, Th, h)


def spline_projector(t, Th, lam=1.0):
    """Matice pro odhad pomalé neměřené poruchy lomenou čarou s uzly po Th (s vyhlazením)."""
    k = max(3, int(np.ceil((t[-1] - t[0]) / Th)) + 1)
    knots = np.linspace(t[0], t[-1], k)
    dk = knots[1] - knots[0]
    B = np.maximum(0.0, 1.0 - np.abs(t[:, None] - knots[None, :]) / dk)
    D = np.diff(np.eye(k), 2, axis=0)
    BtB = B.T @ B
    lam_ = lam * np.trace(BtB) / k
    S = np.linalg.solve(BtB + lam_ * D.T @ D + 1e-9 * np.eye(k), B.T)
    return B, S


def dyn_scale(code, p):
    """Charakteristická doba dynamiky modelu: θ + ΣT."""
    return p[-1] + (p[1] if code in ("P1D", "P2D", "I1D") else 0.0) + (p[2] if code == "P2D" else 0.0)


def predict(code, p, pdl, t, pv, mv, dists, h, stic=0.0, level="none", Th=None):
    """
    Predikce PV z naměřené MV (a poruch). Vrací (predikce, shoda %) na „efektivních“ datech:
    none = surová data; medium = data po horní propusti; high = data s odečtenou odhadnutou neměřenou poruchou.
    """
    r = predict_full(code, p, pdl, t, pv, mv, dists, h, stic, level, Th)
    return r["yhat"], r["fit"]


def predict_full(code, p, pdl, t, pv, mv, dists, h, stic=0.0, level="none", Th=None):
    mv_v = stiction_valve(mv, stic) if stic else mv
    du = mv_v - mv_v[0]
    dD = [d - d[0] for d in dists]
    if level == "medium" and Th:
        pv_e = high_pass(pv, Th, h)
        dev = model_dev(code, p, pdl, t, high_pass(du, Th, h), [high_pass(d, Th, h) for d in dD], h)
        yhat = dev + _offset(code, t, pv_e - dev)
        return dict(yhat=yhat, pv=pv_e, fit=fit_percent(pv_e, yhat), dist=None, raw=None)
    dev = model_dev(code, p, pdl, t, du, dD, h)
    if level == "high" and Th:
        B, S = spline_projector(t, Th)
        d_est = B @ (S @ (pv - dev))
        yhat = dev + d_est
        raw = dev + _offset(code, t, pv - dev)
        return dict(yhat=yhat, pv=pv, fit=fit_percent(pv, yhat), dist=d_est, raw=raw)
    yhat = dev + _offset(code, t, pv - dev)
    return dict(yhat=yhat, pv=pv, fit=fit_percent(pv, yhat), dist=None, raw=None)


def _offset(code, t, r):
    """Optimální posun (u integračních i počáteční drift – proces nemusel začínat v rovnováze)."""
    if MODELS[code]["integ"]:
        A = np.column_stack([np.ones_like(t), t - t[0]])
        return A @ np.linalg.lstsq(A, r, rcond=None)[0]
    return np.full_like(r, np.mean(r))


def step_response(code, p, pdl=None, dmv=10.0, horizon=None, n=600):
    """Odezva modelu na skok MV o dmv [%] v čase 0."""
    T = p[-1] + sum(p[1:-1]) if len(p) > 2 else p[-1]
    horizon = horizon or max(6 * T, 10 * p[-1], 1.0)
    h = horizon / n
    t = np.arange(n + 1) * h
    return t, simulate(code, p, t, np.full_like(t, dmv), h)
