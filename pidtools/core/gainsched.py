"""
Gain scheduling (plánování parametrů) podle bloku GainSched z PCS 7 APL (šablona GainScheduling; Siemens, entry 38755162).

Blok drží až tři sady parametrů PID pro pracovní body X1 < X2 < X3 měřené veličiny X (typicky PV), mezi body je
lineárně interpoluje a mimo ně drží krajní hodnoty. Pro ověření přínosu se nelineární proces skládá z lineárních
modelů identifikovaných v jednotlivých bodech (vše v % normovacích rozsahů):
  - statická charakteristika: lokální zesílení se interpoluje podle MV a integruje (Hammersteinův model),
  - dynamika (časové konstanty, dopravní zpoždění) se interpoluje podle aktuální PV.
"""
import numpy as np

from .simulation import PIDConL

__all__ = ["gs_table", "gs_interp", "gs_issues", "SchedPlant", "gs_sim"]

_LAGS = {"P0D": 0, "P1D": 1, "P2D": 2}


def gs_interp(x, X, vals):
    """Parametr v bodě x jako v bloku GainSched: lineárně mezi body, mimo krajní body konstantně."""
    return float(np.interp(x, X, vals))


def gs_table(points):
    """
    Tabulka pro blok GainSched ze 2–3 bodů [{x, gain, ti, td}, …] (x v %): seřazená podle x, vždy tři řádky.
    Při dvou bodech se prostřední doplní interpolací (blok má tři vstupy). Vrací (řádky, doplněno).
    """
    pts = sorted(points, key=lambda q: q["x"])
    if len(pts) == 2:
        a, b = pts
        mid = {k: (a[k] + b[k]) / 2 for k in ("x", "gain", "ti", "td")}
        return [a, mid, b], True
    return pts[:3], False


def gs_issues(points):
    """Problémy rozvrhu: [klíč, …] – znaménko zesílení, splývající body, nemonotónní charakteristika."""
    out = []
    ks = [q["p"][0] for q in points]
    if len({np.sign(k) for k in ks}) > 1:
        out.append("sign")
    xs = sorted(q["x"] for q in points)
    if any(b - a < 2.0 for a, b in zip(xs, xs[1:])):
        out.append("close")
    by_u = sorted(points, key=lambda q: q["u"])
    dx = np.diff([q["x"] for q in by_u])
    if len(dx) and "sign" not in out and np.any(np.sign(dx) * np.sign(ks[0]) < 0):
        out.append("order")
    return out


class SchedPlant:
    """
    Nelineární proces krok po kroku z modelů v pracovních bodech (pro P0D/P1D/P2D).
    points: [{x, u, p}, …] – x, u = PV a MV v bodě [%], p = parametry modelu (K, T1[, T2], θ) daného kódu.
    """

    def __init__(self, code, points, h, n_hist):
        self.code, self.h, self.nl = code, h, _LAGS[code]
        by_u = sorted(points, key=lambda q: q["u"])
        U = np.array([q["u"] for q in by_u])
        K = np.array([q["p"][0] for q in by_u])
        self.grid = np.arange(min(-50.0, U.min() - 50), max(150.0, U.max() + 50), 0.05)
        Kg = np.interp(self.grid, U, K)
        F = np.r_[0.0, np.cumsum((Kg[1:] + Kg[:-1]) / 2 * np.diff(self.grid))]
        self.F = F + np.mean([q["x"] - np.interp(q["u"], self.grid, F) for q in by_u])  # PV v ustáleném stavu
        by_x = sorted(points, key=lambda q: q["x"])
        self.X = np.array([q["x"] for q in by_x])
        self.Tl = [np.array([q["p"][1 + j] for q in by_x]) for j in range(self.nl)]
        self.TH = np.array([q["p"][-1] for q in by_x])
        self.w = np.zeros(n_hist)
        self.k = 0

    def steady(self, y):
        """MV v ustáleném stavu pro PV = y (inverze statické charakteristiky)."""
        F = self.F
        return float(np.interp(y, F, self.grid) if F[-1] >= F[0] else np.interp(y, F[::-1], self.grid[::-1]))

    def init(self, u0):
        w0 = float(np.interp(u0, self.grid, self.F))
        self.w0 = w0
        self.w[:] = w0
        self.x = [w0] * self.nl
        self.y = w0
        self.k = 0

    def step(self, u):
        """Jeden krok se vstupem u [%] (absolutní hodnota MV), vrací PV [%]."""
        y = self.y
        self.w[self.k] = np.interp(u, self.grid, self.F)
        nd = int(round(np.interp(y, self.X, self.TH) / self.h))
        v = self.w[self.k - nd] if self.k >= nd else self.w0
        for j in range(self.nl):
            a = np.exp(-self.h / max(np.interp(y, self.X, self.Tl[j]), 1e-9))
            self.x[j] = a * self.x[j] + (1 - a) * v
            v = self.x[j]
        self.y = v
        self.k += 1
        return self.y


def gs_sim(code, points, ctrl, sched, h, sp, d=None):
    """
    Uzavřená smyčka PIDConL na nelineárním procesu. sched = None (pevné parametry ctrl) nebo
    {X, gain, ti, td} – parametry se v každém kroku interpolují podle PV jako v bloku GainSched (bezrázově).
    sp a d (porucha na vstupu procesu) v %. Vrací t a dict polí SP, PV, MV, Gain, TI.
    """
    n = len(sp)
    d = np.zeros(n) if d is None else np.asarray(d, float)
    plant = SchedPlant(code, points, h, n)
    u0 = plant.steady(sp[0])
    plant.init(u0)
    c = PIDConL(ctrl, h)
    y = plant.y
    c.init(sp[0], y, u0)
    X = sched["X"] if sched else None
    out = {k: np.zeros(n) for k in ("SP", "PV", "MV", "Gain", "TI")}
    for k in range(n):
        if sched:
            c.set_tuning(gs_interp(y, X, sched["gain"]), gs_interp(y, X, sched["ti"]), gs_interp(y, X, sched["td"]))
        u = c.step(sp[k], y)
        out["SP"][k], out["PV"][k], out["MV"][k], out["Gain"][k], out["TI"][k] = sp[k], y, u, c.Kc, c.Ti
        y = plant.step(u + d[k])
    return np.arange(n) * h, out
