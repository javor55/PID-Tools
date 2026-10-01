"""
Pokročilé regulační struktury (APC) nad stejným simulačním jádrem jako ostatní simulace.

  – rozvazbení 2×2: RGA (relativní zesílení) a dopředné decouplery MV_B → MV_A (statické / lead-lag + zpoždění)
  – override: dva regulátory na jednom ventilu, výběr MIN/MAX, neaktivní regulátor s external reset feedback
  – Smithův prediktor: PI(D) na modelu bez dopravního zpoždění, citlivost na chybu modelu

Vše v % normovacích rozsahů. Model smyčky = (kód, parametry), křížový model = [K, T, θ] (stejný tvar jako model
měřené poruchy; u integrační smyčky je i křížová vazba integrační).
"""
import numpy as np

from .models import MODELS
from .simulation import PIDConL, ProcStep

__all__ = ["rga2", "rga_advice", "ff_design", "LeadLag", "mimo2_sim", "override_sim", "smith_sim", "no_delay"]


# ================================================================ rozvazbení
def rga2(k11, k12, k21, k22):
    """
    Relativní zesílení λ11 pro 2×2 (λ22 = λ11, λ12 = λ21 = 1 − λ11).
    Zesílení integračních smyček jsou rychlosti (Ki); RGA na násobení řádku nezávisí, takže je to v pořádku,
    pokud jsou integrační obě vazby téže PV (jak je tomu u modelů poruch).
    """
    den = k11 * k22 - k12 * k21
    if den == 0:
        return np.inf
    return k11 * k22 / den


def rga_advice(lam):
    """Klíč textu doporučení podle λ11."""
    if not np.isfinite(lam):
        return "rga_singular"
    if lam < 0:
        return "rga_swap"
    if lam < 0.5:
        return "rga_swap_weak"
    if 0.8 <= lam <= 1.25:
        return "rga_weak"
    if lam <= 2.0:
        return "rga_moderate"
    return "rga_strong"


def ff_design(code, p, pd):
    """
    Dopředný člen ze vstupu x na MV smyčky (code, p), kde x působí na PV modelem pd = [K, T, θ]:
    zesílení −K/Kp, lead = časové konstanty procesu, lag = T vazby, zpoždění = θ vazby − θ procesu (≥ 0).
    """
    lead = (p[1] if code in ("P1D", "P2D", "I1D") else 0.0) + (p[2] if code == "P2D" else 0.0)
    return dict(gain=-pd[0] / p[0], lead=lead, lag=pd[1], delay=max(0.0, pd[2] - p[-1]))


class LeadLag:
    """Zesílení · (lead·s + 1)/(lag·s + 1) · zpoždění, krok po kroku (dynamic=False → jen zesílení)."""

    def __init__(self, gain, lead=0.0, lag=0.0, delay=0.0, h=1.0, dynamic=True):
        self.g = gain
        self.dyn = dynamic and lag > 0
        self.q = [0.0] * (max(0, int(round(delay / h))) if dynamic else 0)
        self.a = np.exp(-h / lag) if self.dyn else 0.0
        self.r = lead / lag if self.dyn else 1.0
        self.z = 0.0

    def step(self, x):
        if self.q:
            self.q.append(x)
            x = self.q.pop(0)
        if not self.dyn:
            return self.g * x
        self.z = self.a * self.z + (1 - self.a) * x
        return self.g * (self.r * x + (1 - self.r) * self.z)


def _cross(integ, pd, h):
    """Křížová vazba jako proces krok po kroku."""
    return ProcStep("I1D" if integ else "P1D", [pd[0], max(pd[1], 1e-6), pd[2]], h)


def mimo2_sim(ga, gb, xab, xba, ctrl_a, ctrl_b, h, sp_a, sp_b, dec_ab=None, dec_ba=None, dyn=True,
              d_a=None, d_b=None, pv0=(50.0, 50.0), mv0=(50.0, 50.0)):
    """
    Dvě interagující smyčky A, B:  PV_A = G_A·MV_A + X_AB·MV_B,  PV_B = G_B·MV_B + X_BA·MV_A.
    ga, gb = (kód, p); xab, xba = [K, T, θ] nebo None (bez vazby); dec_ab/dec_ba = ff_design(...) nebo None
    (decoupler přičítá k MV_A člen z MV_B, resp. naopak); dyn = lead-lag a zpoždění decoupleru.
    d_a, d_b = poruchy na vstupu procesů [% MV]. Vrací t a dict polí SP_A, PV_A, MV_A, SP_B, PV_B, MV_B.
    """
    n = len(sp_a)
    pa, pb = ProcStep(*ga, h), ProcStep(*gb, h)
    ia, ib = MODELS[ga[0]]["integ"], MODELS[gb[0]]["integ"]
    cab = _cross(ia, xab, h) if xab is not None else None
    cba = _cross(ib, xba, h) if xba is not None else None
    dab = LeadLag(dec_ab["gain"], dec_ab["lead"], dec_ab["lag"], dec_ab["delay"], h, dyn) if dec_ab else None
    dba = LeadLag(dec_ba["gain"], dec_ba["lead"], dec_ba["lag"], dec_ba["delay"], h, dyn) if dec_ba else None
    d_a = np.zeros(n) if d_a is None else d_a
    d_b = np.zeros(n) if d_b is None else d_b
    ca, cb = PIDConL(ctrl_a, h), PIDConL(ctrl_b, h)
    ca.init(sp_a[0], pv0[0], mv0[0])
    cb.init(sp_b[0], pv0[1], mv0[1])
    ua, ub = mv0
    out = {k: np.zeros(n) for k in ("SP_A", "PV_A", "MV_A", "SP_B", "PV_B", "MV_B")}
    for k in range(n):
        ya = pv0[0] + pa.output() + (cab.output() if cab else 0.0)
        yb = pv0[1] + pb.output() + (cba.output() if cba else 0.0)
        ff_a = dab.step(ub - mv0[1]) if dab else 0.0     # MV druhé smyčky z minulého kroku
        ff_b = dba.step(ua - mv0[0]) if dba else 0.0
        ua, ub = ca.step(sp_a[k], ya, ff_a), cb.step(sp_b[k], yb, ff_b)
        pa.step(ua - mv0[0] + d_a[k])
        pb.step(ub - mv0[1] + d_b[k])
        if cab:
            cab.step(ub - mv0[1])
        if cba:
            cba.step(ua - mv0[0])
        for key, v in (("SP_A", sp_a[k]), ("PV_A", ya), ("MV_A", ua), ("SP_B", sp_b[k]), ("PV_B", yb), ("MV_B", ub)):
            out[key][k] = v
    return np.arange(n) * h, out


# ================================================================ override
def _ext_reset(c, u_sel, ff=0.0):
    """
    External reset feedback neaktivního regulátoru: I složka sleduje (s časovou konstantou TI) skutečně
    použitý výstup, P složka zůstává aktivní → regulátor převezme řízení, až jeho regulační odchylka
    požaduje „přísnější“ výstup než aktivní regulátor; přechod je bez rázu a bez windupu.
    """
    if (c.k - 1) % c.m:
        return
    a = c.Tc / (c.Ti + c.Tc) if c.use_i else 1.0
    c.I += a * (u_sel - ff - c.I)
    c.u = c.u_prev = u_sel


def override_sim(ga, gb, ctrl_a, ctrl_b, h, sp_a, sp_b, select="min", enabled=True, d=None,
                 pv0=(50.0, 50.0), mv0=50.0):
    """
    Override: hlavní regulátor A a omezující regulátor B řídí tentýž ventil, použije se MIN (nebo MAX) z jejich
    výstupů. ga, gb = (kód, p) modely MV → PV_A a MV → PV_B; sp_b = mez omezované veličiny.
    enabled=False → jen regulátor A (pro srovnání, jak by mez byla překročena). d = porucha na vstupu [% MV].
    Vrací t a dict polí SP_A, PV_A, SP_B, PV_B, U_A, U_B, MV, ACT (0 = A, 1 = B).
    """
    n = len(sp_a)
    pa, pb = ProcStep(*ga, h), ProcStep(*gb, h)
    ca, cb = PIDConL(ctrl_a, h), PIDConL(ctrl_b, h)
    ca.init(sp_a[0], pv0[0], mv0)
    cb.init(sp_b[0], pv0[1], mv0)
    d = np.zeros(n) if d is None else d
    pick = min if select == "min" else max
    out = {k: np.zeros(n) for k in ("SP_A", "PV_A", "SP_B", "PV_B", "U_A", "U_B", "MV", "ACT")}
    act = 0
    for k in range(n):
        ya, yb = pv0[0] + pa.output(), pv0[1] + pb.output()
        ua, ub = ca.step(sp_a[k], ya), cb.step(sp_b[k], yb)
        if enabled:
            u = pick(ua, ub)
            if ua != ub:  # při shodě (mezi cykly regulátorů) zůstává aktivní dosavadní regulátor
                act = 0 if u == ua else 1
            _ext_reset(cb if act == 0 else ca, u)
        else:
            u, act = ua, 0
            _ext_reset(cb, u)
        pa.step(u - mv0 + d[k])
        pb.step(u - mv0 + d[k])
        for key, v in (("SP_A", sp_a[k]), ("PV_A", ya), ("SP_B", sp_b[k]), ("PV_B", yb), ("U_A", ua), ("U_B", ub),
                       ("MV", u), ("ACT", act)):
            out[key][k] = v
    return np.arange(n) * h, out


# ================================================================ Smithův prediktor
def no_delay(p):
    """Parametry modelu bez dopravního zpoždění."""
    return list(p[:-1]) + [0.0]


def smith_sim(code, p_plant, p_model, ctrl, h, sp, d=None, pv0=50.0, mv0=50.0):
    """
    Smithův prediktor: regulátor vidí PV + (model bez zpoždění − model se zpožděním)·MV, tj. predikci PV
    bez dopravního zpoždění. p_plant = skutečný proces, p_model = model v prediktoru (pro test chyby modelu).
    Vrací t a dict polí SP, PV, MV, PRED (signál, který vidí regulátor).
    """
    n = len(sp)
    plant, md, m0 = ProcStep(code, p_plant, h), ProcStep(code, p_model, h), ProcStep(code, no_delay(p_model), h)
    c = PIDConL(ctrl, h)
    c.init(sp[0], pv0, mv0)
    d = np.zeros(n) if d is None else d
    out = {k: np.zeros(n) for k in ("SP", "PV", "MV", "PRED")}
    for k in range(n):
        y = pv0 + plant.output()
        ym = y + m0.output() - md.output()
        u = c.step(sp[k], ym)
        plant.step(u - mv0 + d[k])
        md.step(u - mv0)
        m0.step(u - mv0)
        out["SP"][k], out["PV"][k], out["MV"][k], out["PRED"][k] = sp[k], y, u, ym
    return np.arange(n) * h, out
