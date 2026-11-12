"""
Simulace regulační smyčky se strukturou PIDConL (SIMATIC PCS 7 APL).

Jediná implementace regulátoru (`PIDConL`), ventilu (`Valve`) a procesu (`ProcStep`) krok po kroku,
kterou používají dávková simulace (`pidconl_sim_full`), kaskáda (`cascade_sim`) i živá simulace (`LiveLoop`).
Všechny veličiny PV, SP, MV jsou v % normovacích rozsahů.
"""
import numpy as np

from .controller import Controller, preset_profile
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


class PIDConL(Controller):
    """
    Regulátor PIDConL krok po kroku: ideální tvar, D s filtrem TD/DiffGain, P a D volitelně jen z PV,
    deadband, limity a rychlost MV s anti-windupem, rampa SP, filtr PV, dopředná vazba a bezrázové přepínání.
    Tenký obal obecného regulátoru (`core.controller`) s dodaným profilem `pcs7_pidconl`
    (`pidtools/controllers/presets/pcs7_pidconl.json`); výsledky jsou stejné jako u dřívější samostatné třídy.
    `step` se volá v každém kroku simulace h; regulátor počítá každých round(SampleTime/h) kroků.
    ctrl: Gain, TI, TD, DiffGain, SampleTime, PropFacSP (0–1), DiffFbk, DeadBand [%], DbMode, MV_Lo, MV_Hi [%],
          PVFilt [s], MVRate [%/s], SPRate [%/s], ConZone [%] (řídicí pásmo: |ER| > ConZone → MV na limit,
          po návratu do pásma regulátor pokračuje bezrázově z limitu; 0 = vypnuto)
    Metody: init(sp, y_meas, u0, ff), step(sp, y_meas, ff), track(sp, y_meas, u_man, ff), set_tuning(Gain, TI, TD).
    """

    def __init__(self, ctrl, h):
        super().__init__(preset_profile("pcs7_pidconl"), ctrl, h)


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
def pidconl_sim_full(code, p, pdl, h, sp, pv0, mv0, ctrl, dmeas=(), dist_mv=None, dist_pv=None, profile=None):
    """
    Uzavřená smyčka: model procesu + PIDConL + prvky smyčky a ventilu.
    h ....... krok simulace [s]; sp ... pole SP [%] (cíl); pv0, mv0 počáteční PV a MV [%] (ustálený stav)
    ctrl .... parametry PIDConL (viz PIDConL) + FF, FF_LL (dopředná vazba), Stic, SticJ [% MV] (stikce),
              ValveChar (10 zesílení), Noise [% PV] (šum měření), Seed
    dmeas ... měřené poruchy (odchylky, j.) – působí přes modely poruch pdl a na FF
    profile . profil regulátoru (dict / Profile); bez něj PIDConL
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
    pid = PIDConL(ctrl, h) if profile is None else Controller(profile, ctrl, h)
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

    def advance(self, seconds, sp, auto=True, u_man=None, d_in=0.0, d_out=0.0):
        """Posune simulaci o `seconds` sekund (sp, u_man, d_in na vstupu procesu, d_out na PV – vše v % rozsahů)."""
        for _ in range(max(1, int(round(seconds / self.h)))):
            y = self.pv0 + self.proc.output() + d_out
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
