"""
Živá simulace pro frontend, který ji počítá sám (desktop): jedna nebo dvě smyčky (sada 1 a 2) nad core.LiveLoop,
ruční / automatický režim, SP, poruchy na vstupu i výstupu procesu, změna procesu, šum PV a ukazatele od poslední
události. Vše uvnitř v % rozsahů regulátoru; vstupy a výstupy pro uživatele v inženýrských jednotkách přes Scaling.
(Webová aplikace počítá živou simulaci v prohlížeči – ui/static/live_engine.js.)
"""
import numpy as np

from ..core import LiveLoop
from .apc.common import tchar


def step_h(code, p, samp):
    """Krok simulace: nejvýš SampleTime, jemnější u rychlých procesů."""
    return float(min(samp, max(tchar((code, p)) / 400, samp / 10)))


class LiveSession:
    """
    Živá simulace sad regulátoru na stejném procesu. sets: {název: ctrl}; plant: dict(Noise, Stic, …) v %.
    Proces lze změnit (K a θ jako násobek modelu) – smyčky se pak spustí znovu z pracovního bodu.
    """

    def __init__(self, sc, model, sets, pv0, mv0, plant=None, window=None):
        self.sc, self.model, self.sets = sc, model, dict(sets)
        self.pv0, self.mv0 = float(pv0), float(mv0)
        self.plant = dict(plant or {})
        code, p, _ = model
        self.h = step_h(code, p, min(c["SampleTime"] for c in self.sets.values()))
        self.window = window or max(60 * tchar((code, p)), 600 * self.h)
        self.k_fac, self.th_fac = 1.0, 1.0
        self.sp, self.auto, self.u_man = self.pv0, True, self.mv0
        self.d_in, self.d_out = 0.0, 0.0
        self.shape = dict(kind="step", period=60.0, t0=0.0)    # tvar poruch: step, ramp, sine, random, pulse
        self._rnd, self._rnd_val, self._rnd_k = np.random.default_rng(1), 0.0, -1
        self.events = []
        self.reset()

    # ---- stav
    def reset(self):
        code, p, _ = self.model
        q = list(p)
        q[0] *= self.k_fac
        q[-1] *= self.th_fac
        n_hist = int(self.window / self.h) + 2
        self.loops = {n: LiveLoop(code, q, c, self.h, self.pv0, self.mv0, self.plant, history=n_hist)
                      for n, c in self.sets.items()}
        self.t = 0.0
        self.mark = 0.0
        self.events = []

    def set_process(self, k_fac=1.0, th_fac=1.0):
        self.k_fac, self.th_fac = float(k_fac), float(th_fac)
        self.reset()

    def set_tuning(self, sets):
        """Nové parametry sad za běhu (bez rázu výstupu)."""
        for n, c in sets.items():
            self.sets[n] = c
            if n in self.loops:
                self.loops[n].set_tuning(c)

    def event(self, label):
        """Událost (změna SP, poruchy, režimu) – od ní se počítají ukazatele."""
        self.events.append((self.t, label))
        self.mark = self.t

    # ---- vstupy v inženýrských jednotkách
    def set_sp(self, sp_e):
        self.sp = float(self.sc.P(sp_e))
        self.event("SP")

    def set_mode(self, auto, u_man_e=None):
        self.auto = bool(auto)
        if u_man_e is not None:
            self.u_man = float(self.sc.M(u_man_e))
        self.event("A" if auto else "M")

    def set_dist(self, d_in_e=None, d_out_e=None, kind=None, period=None):
        """
        Porucha na vstupu procesu [jednotky MV] a na výstupu [jednotky PV] (amplitudy) a její tvar: step (skok),
        ramp (náběh za periodu), sine (sinus s periodou), random (náhodná změna každou periodu), pulse (pulz délky
        poloviny periody, opakovaně).
        """
        if d_in_e is not None:
            self.d_in = float(d_in_e) / self.sc.MR * 100
        if d_out_e is not None:
            self.d_out = float(d_out_e) / self.sc.PR * 100
        if kind is not None:
            self.shape["kind"] = kind
        if period is not None:
            self.shape["period"] = max(float(period), 1e-3)
        self.shape["t0"] = self.t
        self._rnd = np.random.default_rng(int(self.t * 1000) % 2 ** 31)
        self._rnd_val, self._rnd_k = 0.0, -1
        self.event("D")

    def _shape(self, t):
        """Násobek amplitudy poruchy v čase t (0 … 1, u sinu −1 … 1)."""
        k, per, t0 = self.shape["kind"], self.shape["period"], self.shape["t0"]
        x = t - t0
        if k == "ramp":
            return min(max(x / per, 0.0), 1.0)
        if k == "sine":
            return float(np.sin(2 * np.pi * x / per))
        if k == "pulse":
            return 1.0 if (x % per) < per / 2 else 0.0
        if k == "random":
            n = int(x // per)
            if n != self._rnd_k:
                self._rnd_k, self._rnd_val = n, float(self._rnd.uniform(-1, 1))
            return self._rnd_val
        return 1.0

    # ---- běh
    def advance(self, seconds):
        """Posun o seconds; u proměnných poruch po krocích (≤ 1/40 periody), aby tvar zůstal zachovaný."""
        k = self.shape["kind"]
        chunk = seconds if k == "step" else max(self.h, min(seconds, self.shape["period"] / 40))
        done = 0.0
        while done < seconds - 1e-9:
            dt = min(chunk, seconds - done)
            f = self._shape(self.t + dt / 2) if k != "step" else 1.0
            for lp in self.loops.values():
                lp.advance(dt, self.sp, self.auto, self.u_man, self.d_in * f, self.d_out * f)
            self.t = next(iter(self.loops.values())).t
            done += dt

    def to_frame(self):
        """Průběhy všech sad v jednotkách (export CSV)."""
        import pandas as pd
        cols = {}
        for n in self.loops:
            d = self.series(n)
            cols.setdefault("t [s]", d["t"])
            cols.setdefault("SP", d["SP"])
            cols[f"PV {n}"], cols[f"MV {n}"] = d["PV"], d["MV"]
        m = min(len(v) for v in cols.values())
        return pd.DataFrame({k: v[-m:] for k, v in cols.items()})

    def series(self, n):
        """Průběhy sady n v inženýrských jednotkách: dict(t, SP, PV, MV)."""
        hi = self.loops[n].hist
        return dict(t=np.asarray(hi["t"]), SP=self.sc.EP(np.asarray(hi["SP"])), PV=self.sc.EP(np.asarray(hi["PV"])),
                    MV=self.sc.EM(np.asarray(hi["MV"])))

    def kpis(self, n):
        """Ukazatele sady n od poslední události: IAE [PV·s], max. odchylka [PV], dráha MV [MV]."""
        hi = self.loops[n].hist
        t = np.asarray(hi["t"])
        m = t >= self.mark
        if m.sum() < 2:
            return None
        e = (np.asarray(hi["SP"])[m] - np.asarray(hi["PV"])[m]) * self.sc.PR / 100
        mv = np.asarray(hi["MV"])[m] * self.sc.MR / 100
        return dict(iae=float(np.sum(np.abs(e)) * self.h), maxdev=float(np.max(np.abs(e))),
                    travel=float(np.abs(np.diff(mv)).sum()))
