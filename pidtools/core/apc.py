"""
Pokročilé regulační struktury (APC) nad stejným simulačním jádrem jako ostatní simulace.

  – rozvazbení 2×2: RGA (relativní zesílení) a dopředné decouplery MV_B → MV_A (statické / lead-lag + zpoždění)
  – override: dva regulátory na jednom ventilu, výběr MIN/MAX, neaktivní regulátor s external reset feedback
  – Smithův prediktor: PI(D) na modelu bez dopravního zpoždění, citlivost na chybu modelu

Vše v % normovacích rozsahů. Model smyčky = (kód, parametry), křížový model = [K, T, θ] (stejný tvar jako model
měřené poruchy; u integrační smyčky je i křížová vazba integrační).
"""
import numpy as np

from .models import MODELS, dist_integ
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
    ideálně −K/Kp · (Tp·s + 1)/(T·s + 1) · e^−(θ − θp)·s → zesílení −K/Kp, lead = časové konstanty procesu,
    zpoždění = θ vazby − θ procesu. Působí-li vstup rychleji než MV (θ < θp), ideální člen by musel předbíhat
    o Δ = θp − θ; to nejde, a tak se o Δ zkrátí lag (e^Δs/(T·s + 1) ≈ 1/((T − Δ)·s + 1)) – při Δ ≥ T zbude statická FF.
    """
    lead = (p[1] if code in ("P1D", "P2D", "I1D") else 0.0) + (p[2] if code == "P2D" else 0.0)
    ahead = max(0.0, p[-1] - pd[2])
    if dist_integ(MODELS[code]["integ"], pd) != MODELS[code]["integ"]:
        # jiný typ přenosu poruchy než MV (např. samoregulační porucha u integračního procesu): ideální člen by
        # derivoval / integroval – statická dopředná vazba nemá smysl (mismatch = True, zesílení 0)
        return dict(gain=0.0, lead=0.0, lag=0.0, delay=0.0, mismatch=True)
    return dict(gain=-pd[0] / p[0], lead=lead, lag=max(0.0, pd[1] - ahead), delay=max(0.0, pd[2] - p[-1]))


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
    return ProcStep("I1D" if dist_integ(integ, pd) else "P1D", [pd[0], max(pd[1], 1e-6), pd[2]], h)


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
    c.u_prev = u_sel   # rychlost MV se počítá od skutečně použité hodnoty; vlastní návrh výstupu (c.u) zůstává


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


def smith_apl(p, pv_span, mv_span, pv_op, mv_op):
    """
    Hodnoty pro šablonu SmithPredictorControl (PCS 7 APL; Siemens, entry 37361207). Bloky modelu v CFC pracují
    ve fyzikálních jednotkách: Lag (LagTime) → Mul04 (zesílení) → Add04 PV0 → DeadTime.
    p: model aplikace v % rozsahu (K v %/%); pv_span, mv_span: rozsahy PV a MV; pv_op, mv_op: pracovní bod
    ve fyzikálních jednotkách. Model vyššího řádu se nahradí součtovou časovou konstantou (doporučení Siemens).
    PV0 = PV v ustáleném stavu při MV = 0 – extrapolace lineárního modelu z pracovního bodu.
    """
    k = float(p[0]) * pv_span / mv_span
    lag = float(sum(p[1:-1]))
    th = float(p[-1])
    return dict(k=k, lag=lag, theta=th, pv0=float(pv_op - k * mv_op), th_lag=th / lag if lag > 0 else np.inf)


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


# ================================================================ split range
def split_map(u, b, mode="opposite", gap=0.0):
    """
    Výstup regulátoru u [%] → (ventil A, ventil B) [%] s bodem rozdělení b [%] a mezerou (+) / překryvem (−) gap.
    mode "opposite": A se zavírá od 0 do b (např. chlazení), B se otevírá od b do 100 (ohřev);
    mode "sequence": nejdřív A (0 … b), pak B (b … 100), oba otevírají (malý a velký ventil).
    """
    lo, hi = b - gap / 2, b + gap / 2
    a = (lo - u) / max(lo, 1e-9) * 100 if mode == "opposite" else u / max(lo, 1e-9) * 100
    bb = (u - hi) / max(100 - hi, 1e-9) * 100
    return float(np.clip(a, 0, 100)), float(np.clip(bb, 0, 100))


def split_range_sim(ga, gb, ctrl, h, sp, b, mode="opposite", gap=0.0, pv0=50.0, u0=None, d=None):
    """
    Jeden regulátor, dva akční členy přes rozdělení rozsahu. ga, gb = (kód, p) modely ventil A / B [% ventilu]
    → PV [%]. d = porucha na výstupu (PV) [%]. Vrací t a dict polí SP, PV, U, VA, VB.
    """
    n = len(sp)
    pa, pb = ProcStep(*ga, h), ProcStep(*gb, h)
    c = PIDConL(ctrl, h)
    u0 = b + (100 - b) / 2 if u0 is None else u0
    a0, b0 = split_map(u0, b, mode, gap)
    c.init(sp[0], pv0, u0)
    d = np.zeros(n) if d is None else d
    out = {k: np.zeros(n) for k in ("SP", "PV", "U", "VA", "VB")}
    for k in range(n):
        y = pv0 + pa.output() + pb.output() + d[k]
        u = c.step(sp[k], y)
        va, vb = split_map(u, b, mode, gap)
        pa.step(va - a0)
        pb.step(vb - b0)
        for key, v in (("SP", sp[k]), ("PV", y), ("U", u), ("VA", va), ("VB", vb)):
            out[key][k] = v
    return np.arange(n) * h, out


# ================================================================ regulace polohy ventilu (mid-range, VPC)
def vpc_sim(g1, g2, ctrl1, ctrl_vpc, h, sp, sp_vpc=50.0, d=None, pv0=50.0, mv10=50.0, mv20=50.0, enabled=True):
    """
    Regulace polohy ventilu: hlavní regulátor řídí PV rychlým (malým) akčním členem MV1, regulátor VPC pomalu
    přestavuje velký akční člen MV2 tak, aby MV1 zůstal kolem sp_vpc (rezerva na obě strany).
    g1, g2 = (kód, p) modely MV1 → PV a MV2 → PV [%]. d = porucha na vstupu procesu 1 [% MV1].
    enabled=False → MV2 stojí (srovnání). Vrací t a dict polí SP, PV, MV1, MV2.
    """
    n = len(sp)
    p1, p2 = ProcStep(*g1, h), ProcStep(*g2, h)
    c1, cv = PIDConL(ctrl1, h), PIDConL(ctrl_vpc, h)
    c1.init(sp[0], pv0, mv10)
    cv.init(sp_vpc, mv10, mv20)
    d = np.zeros(n) if d is None else d
    out = {k: np.zeros(n) for k in ("SP", "PV", "MV1", "MV2")}
    for k in range(n):
        y = pv0 + p1.output() + p2.output()
        u1 = c1.step(sp[k], y)
        u2 = cv.step(sp_vpc, u1) if enabled else mv20
        p1.step(u1 - mv10 + d[k])
        p2.step(u2 - mv20)
        for key, v in (("SP", sp[k]), ("PV", y), ("MV1", u1), ("MV2", u2)):
            out[key][k] = v
    return np.arange(n) * h, out


# ================================================================ poměrová regulace s křížovým omezením
def ratio_sim(gf, ga, ctrl_f, ctrl_a, h, demand, R, cross=True, pv0=(50.0, 50.0), mv0=(50.0, 50.0)):
    """
    Poměrová regulace palivo–vzduch: požadavek výkonu (demand, % rozsahu paliva) → SP paliva a SP vzduchu = R × SP
    paliva (R v %vzduchu / %paliva). S křížovým omezením: vzduch = max(požadavek, skutečné palivo) × R, palivo =
    min(požadavek, skutečný vzduch / R) – při růstu výkonu vede vzduch, při poklesu palivo (nikdy přebytek paliva).
    gf, ga = (kód, p) modely MV → průtok paliva / vzduchu [%]. Vrací t a dict polí D, SPF, PVF, SPA, PVA, LAM
    (LAM = vzduch / (R × palivo), < 1 = nedostatek vzduchu).
    """
    n = len(demand)
    pf, pa = ProcStep(*gf, h), ProcStep(*ga, h)
    cf, ca = PIDConL(ctrl_f, h), PIDConL(ctrl_a, h)
    cf.init(demand[0], pv0[0], mv0[0])
    ca.init(demand[0] * R, pv0[1], mv0[1])
    out = {k: np.zeros(n) for k in ("D", "SPF", "PVF", "SPA", "PVA", "LAM")}
    for k in range(n):
        yf, ya = pv0[0] + pf.output(), pv0[1] + pa.output()
        if cross:
            spf, spa = min(demand[k], ya / R), max(demand[k], yf) * R
        else:
            spf, spa = demand[k], demand[k] * R
        uf, ua = cf.step(spf, yf), ca.step(spa, ya)
        pf.step(uf - mv0[0])
        pa.step(ua - mv0[1])
        lam = ya / (R * yf) if yf > 1e-6 else np.nan
        for key, v in (("D", demand[k]), ("SPF", spf), ("PVF", yf), ("SPA", spa), ("PVA", ya), ("LAM", lam)):
            out[key][k] = v
    return np.arange(n) * h, out


# ================================================================ interakce N×N
def rga(K):
    """Relativní zisková matice Λ = K ∘ (K⁻¹)ᵀ (NaN, je-li K singulární)."""
    K = np.asarray(K, float)
    try:
        return K * np.linalg.inv(K).T
    except np.linalg.LinAlgError:
        return np.full_like(K, np.nan)


def niederlinski(K):
    """Niederlinskiho index NI = det K / Π K_ii (záporný → párování po diagonále je nestabilní s integrací)."""
    K = np.asarray(K, float)
    dg = np.prod(np.diag(K))
    return float(np.linalg.det(K) / dg) if abs(dg) > 1e-12 else float("nan")


def best_pairing(K):
    """Párování MV → PV s RGA prvky nejblíž 1 (bez záporných); malé N – všechny permutace. Vrací (perm, skóre)."""
    from itertools import permutations
    L = rga(K)
    n = len(L)
    best, best_s = None, np.inf
    for perm in permutations(range(n)):
        lam = [L[i, perm[i]] for i in range(n)]
        if any(not np.isfinite(v) or v <= 0 for v in lam):
            continue
        s = sum(abs(np.log(v)) for v in lam)
        if s < best_s:
            best, best_s = list(perm), s
    return best, best_s
