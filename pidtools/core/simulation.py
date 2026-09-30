"""
Simulace regulační smyčky se strukturou PIDConL (SIMATIC PCS 7 APL).

Jediná implementace regulátoru (`PIDConL`), ventilu (`Valve`) a procesu (`ProcStep`) krok po kroku,
kterou používají dávková simulace (`pidconl_sim_full`), kaskáda (`cascade_sim`) i živá simulace (`LiveLoop`).
Všechny veličiny PV, SP, MV jsou v % normovacích rozsahů.
"""
import numpy as np

from .models import MODELS, simulate_dist
from .util import lag as _lag

__all__ = ["ProcStep", "PIDConL", "Valve", "valve_char_fn", "pidconl_sim_full", "pidconl_sim", "cascade_sim",
           "LiveLoop", "iae"]


# ================================================================ stavební bloky
class ProcStep:
    """Proces krok po kroku (přesná diskretizace členů 1. řádu, dopravní zpoždění jako fronta vzorků)."""

    def __init__(self, code, p, h):
        self.code, self.p, self.h = code, list(p), h
        self.q = [0.0] * max(1, int(round(p[-1] / h)))
        self.a1 = np.exp(-h / p[1]) if code in ("P1D", "P2D", "I1D") else 0.0
        self.a2 = np.exp(-h / p[2]) if code == "P2D" else 0.0
        self.x1 = self.x2 = self.z = 0.0

    def output(self):
        """Odchylka PV od pracovního bodu [%]."""
        c = self.code
        if c == "P0D":
            return self.p[0] * self.q[0]
        if c == "P1D":
            return self.p[0] * self.x1
        if c == "P2D":
            return self.p[0] * self.x2
        return self.z

    def step(self, u):
        """Jeden krok s odchylkou vstupu u [%]."""
        self.q.append(u)
        ud = self.q.pop(0)
        c = self.code
        if c in ("P1D", "P2D", "I1D"):
            x1n = self.a1 * self.x1 + (1 - self.a1) * ud
            if c == "P2D":
                self.x2 = self.a2 * self.x2 + (1 - self.a2) * self.x1
            self.x1 = x1n
        if c == "I0D":
            self.z += self.p[0] * ud * self.h
        elif c == "I1D":
            self.z += self.p[0] * self.x1 * self.h


def _deadband(e, db, mode):
    if db <= 0 or abs(e) >= db:
        return e - np.sign(e) * db if (db > 0 and mode == "spojité") else e
    return 0.0


class PIDConL:
    """
    Regulátor PIDConL krok po kroku: ideální tvar, D s filtrem TD/DiffGain, P a D volitelně jen z PV,
    deadband, limity a rychlost MV s anti-windupem, rampa SP, filtr PV, dopředná vazba a bezrázové přepínání.
    `step` se volá v každém kroku simulace h; regulátor počítá každých round(SampleTime/h) kroků.
    ctrl: Gain, TI, TD, DiffGain, SampleTime, PropFbk, DiffFbk, DeadBand [%], DbMode, MV_Lo, MV_Hi [%],
          PVFilt [s], MVRate [%/s], SPRate [%/s]
    """

    def __init__(self, ctrl, h):
        self.h = h
        self.m = max(1, int(round(ctrl["SampleTime"] / h)))
        self.Tc = self.m * h
        self.lo, self.hi = ctrl.get("MV_Lo", -np.inf), ctrl.get("MV_Hi", np.inf)
        self.db, self.dbm = ctrl.get("DeadBand", 0.0), ctrl.get("DbMode", "spojité")
        self.pfb, self.dfb = ctrl.get("PropFbk", False), ctrl.get("DiffFbk", False)
        self.Tpv = ctrl.get("PVFilt", 0.0) or 0.0
        self.apv = np.exp(-h / self.Tpv) if self.Tpv > 0 else 0.0
        self.rate = ctrl.get("MVRate", 0.0) or 0.0
        self.sprate = ctrl.get("SPRate", 0.0) or 0.0
        self.N = max(ctrl.get("DiffGain", 5.0), 1e-6)
        self._set_gains(ctrl["Gain"], ctrl["TI"], ctrl["TD"])
        self.k = 0
        self.dem = 0.0

    def _set_gains(self, Kc, Ti, Td):
        self.Kc, self.Ti, self.Td = Kc, Ti, Td
        self.use_i = Ti is not None and np.isfinite(Ti) and Ti > 0
        self.Tf = Td / self.N if Td > 0 else 0.0

    def _p_term(self, e):
        return self.Kc * (-self.yf) if self.pfb else self.Kc * e

    def init(self, sp, y_meas, u0, ff=0.0):
        """Bezrázový start: I složka se nastaví tak, aby výstup byl u0."""
        self.yf = y_meas
        self.spr = sp
        e = _deadband(self.spr - self.yf, self.db, self.dbm)
        self.I = u0 - self._p_term(e) - ff
        self.D = 0.0
        self.xd_prev = -self.yf if self.dfb else self.spr - self.yf
        self.u = self.u_prev = u0

    def set_tuning(self, Gain, TI, TD):
        """Změna parametrů za běhu bez rázu výstupu (přepočet I složky)."""
        e = _deadband(self.spr - self.yf, self.db, self.dbm)
        P_old = self._p_term(e)
        self._set_gains(Gain, TI, TD)
        self.I += P_old - self._p_term(e)

    def track(self, sp, y_meas, u_man, ff=0.0):
        """Ruční režim: výstup = u_man, regulátor sleduje (bezrázový přechod do automatu)."""
        self.yf = self.apv * self.yf + (1 - self.apv) * y_meas if self.Tpv > 0 else y_meas
        self.spr = sp
        e = _deadband(self.spr - self.yf, self.db, self.dbm)
        self.xd_prev = -self.yf if self.dfb else self.spr - self.yf
        self.D = 0.0
        self.I = u_man - self._p_term(e) - ff
        self.u = self.u_prev = u_man
        self.k += 1
        return u_man

    def step(self, sp, y_meas, ff=0.0):
        self.yf = self.apv * self.yf + (1 - self.apv) * y_meas if self.Tpv > 0 else y_meas
        if self.k % self.m == 0:
            Tc = self.Tc
            if self.sprate > 0:
                self.spr = self.spr + float(np.clip(sp - self.spr, -self.sprate * Tc, self.sprate * Tc))
            else:
                self.spr = sp
            e = _deadband(self.spr - self.yf, self.db, self.dbm)
            P = self._p_term(e)
            xd = -self.yf if self.dfb else self.spr - self.yf
            if self.Td > 0:
                self.D = self.Tf / (self.Tf + Tc) * self.D + self.Kc * self.Td / (self.Tf + Tc) * (xd - self.xd_prev)
            self.xd_prev = xd
            inc = self.Kc * Tc / self.Ti * e if self.use_i else 0.0
            u_un = P + self.I + inc + self.D + ff
            self.dem = max(self.dem, abs(u_un - self.u_prev))
            u = min(max(u_un, self.lo), self.hi)
            if self.rate > 0:
                u = float(np.clip(u, self.u_prev - self.rate * Tc, self.u_prev + self.rate * Tc))
            # anti-windup: při omezení (limit nebo rychlost) integruj jen směrem, který omezení uvolňuje
            if u == u_un or (u_un > u and inc < 0) or (u_un < u and inc > 0):
                self.I += inc
            self.u = self.u_prev = u
        self.k += 1
        return self.u


def valve_char_fn(gains):
    """Charakteristika ventilu: zesílení pro pásma 0–10, 10–20, … 90–100 % → funkce poloha → „efektivní“ MV [%]."""
    if not gains:
        return None
    g = np.asarray(list(gains) + [1.0] * (10 - len(gains)), float)[:10]
    if np.allclose(g, 1.0):
        return None
    cum = np.r_[0.0, np.cumsum(g * 10.0)]

    def f(x):
        x = min(max(x, 0.0), 100.0)
        i = min(int(x // 10), 9)
        return cum[i] + g[i] * (x - 10 * i)
    return f


class Valve:
    """Ventil: stikce (pásmo S, skok J; J = S čistá stikce, J = 0 vůle) a charakteristika. Vrací odchylku vstupu procesu."""

    def __init__(self, S=0.0, J=None, gains=None, v0=50.0):
        self.S = S or 0.0
        self.J = self.S if J is None else min(max(J, 0.0), self.S)
        self.fch = valve_char_fn(gains)
        self.v = v0
        self.f0 = self.fch(v0) if self.fch else v0

    def step(self, u):
        if self.S > 0:
            dv = u - self.v
            if abs(dv) > self.S:
                self.v = u - np.sign(dv) * (self.S - self.J)
        else:
            self.v = u
        return (self.fch(self.v) - self.f0) if self.fch else (self.v - self.f0)


# ================================================================ dávková simulace
def pidconl_sim_full(code, p, pdl, h, sp, pv0, mv0, ctrl, dmeas=(), dist_mv=None, dist_pv=None):
    """
    Uzavřená smyčka: model procesu + PIDConL + prvky smyčky a ventilu.
    h ....... krok simulace [s]; sp ... pole SP [%] (cíl); pv0, mv0 počáteční PV a MV [%] (ustálený stav)
    ctrl .... parametry PIDConL (viz PIDConL) + FF, FF_LL (dopředná vazba), Stic, SticJ [% MV] (stikce),
              ValveChar (10 zesílení), Noise [% PV] (šum měření), Seed
    dmeas ... měřené poruchy (odchylky, j.) – působí přes modely poruch pdl a na FF
    dist_mv . neměřená porucha na vstupu procesu [% MV]; dist_pv . porucha přičtená k PV [% PV]
    Vrací dict: t, SP (cíl), SPr (po rampě), PV (skutečná), PVm (měřená po filtru), MV, V (poloha ventilu),
    dem (max. požadovaná rychlost MV [%/s]).
    """
    n = len(sp)
    t = np.arange(n) * h
    integ = MODELS[code]["integ"]
    dmeas = [np.asarray(d, float) for d in dmeas]
    ydist = np.zeros(n)
    for pd, dd in zip(pdl, dmeas):
        ydist += simulate_dist(integ, pd, t, dd, h)
    if dist_pv is not None:
        ydist = ydist + np.asarray(dist_pv, float)
    dist_mv = np.zeros(n) if dist_mv is None else np.asarray(dist_mv, float)
    sig = ctrl.get("Noise", 0.0) or 0.0
    noise = np.random.default_rng(int(ctrl.get("Seed", 1))).normal(0, sig, n) if sig > 0 else np.zeros(n)

    # dopředná vazba: zesílení · lead-lag (Tlead s + 1)/(Tlag s + 1) · zpoždění
    ffg = list(ctrl.get("FF", [])) + [0.0] * len(dmeas)
    ffll = list(ctrl.get("FF_LL", [])) + [(0.0, 0.0, 0.0)] * len(dmeas)
    ff_sig = np.zeros(n)
    for g, d, (tld, tlg, tdl) in zip(ffg, dmeas, ffll):
        if g == 0:
            continue
        x = np.interp(t - tdl, t, d, left=0.0) if tdl > 0 else d
        if tlg > 0:
            x = tld / tlg * x + (1 - tld / tlg) * _lag(x, tlg, h)
        ff_sig += g * x

    proc = ProcStep(code, p, h)
    pid = PIDConL(ctrl, h)
    valve = Valve(ctrl.get("Stic", 0.0), ctrl.get("SticJ"), ctrl.get("ValveChar"), mv0)
    pid.init(sp[0], pv0 + ydist[0] + noise[0], mv0, ff_sig[0])

    out = {k_: np.zeros(n) for k_ in ("SP", "SPr", "PV", "PVm", "MV", "V")}
    for k in range(n):
        y = pv0 + proc.output() + ydist[k]
        u = pid.step(sp[k], y + noise[k], ff_sig[k])
        uin = valve.step(u)
        proc.step(uin + dist_mv[k])
        out["SP"][k], out["SPr"][k], out["PV"][k], out["PVm"][k], out["MV"][k], out["V"][k] = \
            sp[k], pid.spr, y, pid.yf, u, valve.v
    out["t"] = t
    out["dem"] = pid.dem / pid.Tc
    return out


def pidconl_sim(code, p, pdl, h, sp, pv0, mv0, ctrl, dmeas=(), dist_mv=None, dist_pv=None):
    """Zkrácené rozhraní: vrací t, SP (efektivní, po rampě), PV (skutečná), MV."""
    r = pidconl_sim_full(code, p, pdl, h, sp, pv0, mv0, ctrl, dmeas, dist_mv, dist_pv)
    return r["t"], r["SPr"], r["PV"], r["MV"]


def iae(t, sp, pv):
    trap = getattr(np, "trapezoid", None) or np.trapz
    return float(trap(np.abs(sp - pv), t))


# ================================================================ kaskáda
def cascade_sim(inner, ictrl, outer, octrl, h, sp_o, d_inner=None, d_outer=None, pv0_o=50.0, x0_i=50.0, mv0_i=50.0):
    """
    Kaskáda: vnější regulátor → SP vnitřní smyčky; vnitřní regulátor → ventil.
    inner/outer = (code, p). Vnější proces má jako vstup PV vnitřní smyčky (odchylka, %).
    d_inner: porucha na vstupu vnitřního procesu [% MV], d_outer: porucha na vstupu vnějšího procesu [%].
    Vrací t a pole (n × 5): SP vnější, PV vnější, SP vnitřní, PV vnitřní, ventil.
    """
    n = len(sp_o)
    pi_, po_ = ProcStep(*inner, h), ProcStep(*outer, h)
    ci, co = PIDConL(ictrl, h), PIDConL(octrl, h)
    d_inner = np.zeros(n) if d_inner is None else d_inner
    d_outer = np.zeros(n) if d_outer is None else d_outer
    co.init(sp_o[0], pv0_o, x0_i)
    ci.init(x0_i, x0_i, mv0_i)
    out = np.zeros((n, 5))
    for k in range(n):
        yi = x0_i + pi_.output()
        yo = pv0_o + po_.output()
        spi = co.step(sp_o[k], yo)
        u = ci.step(spi, yi)
        pi_.step(u - mv0_i + d_inner[k])
        po_.step(yi - x0_i + d_outer[k])
        out[k] = (sp_o[k], yo, spi, yi, u)
    return np.arange(n) * h, out


# ================================================================ živá simulace
class LiveLoop:
    """
    Smyčka pro živou simulaci: stav se drží mezi voláními `advance`, parametry i režim jdou měnit za běhu.
    Vše v % normovacích rozsahů; pv0/mv0 jsou pracovní bod (ustálený stav na začátku).
    """

    def __init__(self, code, p, ctrl, h, pv0, mv0, plant=None, history=3000):
        plant = plant or {}
        self.h = h
        self.pv0, self.mv0 = pv0, mv0
        self.proc = ProcStep(code, p, h)
        self.pid = PIDConL(ctrl, h)
        self.valve = Valve(plant.get("Stic", 0.0), plant.get("SticJ"), plant.get("ValveChar"), mv0)
        self.sigma = plant.get("Noise", 0.0) or 0.0
        self.rng = np.random.default_rng(int(plant.get("Seed", 1)))
        self.pid.init(pv0, pv0, mv0)
        self.t = 0.0
        self.history = history
        self.hist = {k: [] for k in ("t", "SP", "PV", "MV", "V", "D")}

    def set_tuning(self, ctrl):
        self.pid.set_tuning(ctrl["Gain"], ctrl["TI"], ctrl["TD"])

    def advance(self, seconds, sp, auto=True, u_man=None, d_in=0.0):
        """Posune simulaci o `seconds` sekund (sp, u_man, d_in v % rozsahů)."""
        for _ in range(max(1, int(round(seconds / self.h)))):
            y = self.pv0 + self.proc.output()
            ym = y + (self.rng.normal(0, self.sigma) if self.sigma > 0 else 0.0)
            if auto:
                u = self.pid.step(sp, ym)
            else:
                u = self.pid.track(sp, ym, self.mv0 if u_man is None else u_man)
            uin = self.valve.step(u)
            self.proc.step(uin + d_in)
            self.t += self.h
            for k_, v_ in (("t", self.t), ("SP", self.pid.spr if auto else sp), ("PV", y), ("MV", u),
                           ("V", self.valve.v), ("D", d_in)):
                self.hist[k_].append(v_)
        if len(self.hist["t"]) > self.history:
            for k_ in self.hist:
                self.hist[k_] = self.hist[k_][-self.history:]
        return self.hist
