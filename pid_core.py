"""
Výpočetní jádro: identifikace procesních modelů (MV + měřené poruchy -> PV),
návrh ladění a simulace regulátoru ve struktuře PIDConL (SIMATIC PCS 7 APL).

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
from scipy.optimize import least_squares
from scipy.signal import lfilter

MODELS = {
    "P0D": dict(name="0. řád (zesílení + zpoždění)", params=["K", "θ"], integ=False),
    "P1D": dict(name="1. řád + zpoždění (FOPDT)", params=["K", "T1", "θ"], integ=False),
    "P2D": dict(name="2. řád + zpoždění (SOPDT)", params=["K", "T1", "T2", "θ"], integ=False),
    "I0D": dict(name="Integrační + zpoždění", params=["Ki", "θ"], integ=True),
    "I1D": dict(name="Integrační + 1. řád + zpoždění", params=["Ki", "T1", "θ"], integ=True),
}
DIST_PARAMS = ["Kd", "Tp", "θd"]


def n_free(code):
    return len(MODELS[code]["params"]) - 1


# ================================================================ simulace modelu
def _lag(x, T, h):
    a = np.exp(-h / max(T, 1e-9))
    return lfilter([1 - a], [1, -a], x)


def simulate(code, p, t, du, h):
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


def stiction_valve(u, S, J=None):
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


def _hp(x, Th, h):
    """Horní propust 1. řádu (odstraní pomalé změny delší než ~Th)."""
    x = np.asarray(x, float) - x[0]
    return x - _lag(x, Th, h)


def _spline_projector(t, Th, lam=1.0):
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
        pv_e = _hp(pv, Th, h)
        dev = model_dev(code, p, pdl, t, _hp(du, Th, h), [_hp(d, Th, h) for d in dD], h)
        yhat = dev + _offset(code, t, pv_e - dev)
        return dict(yhat=yhat, pv=pv_e, fit=fit_percent(pv_e, yhat), dist=None, raw=None)
    dev = model_dev(code, p, pdl, t, du, dD, h)
    if level == "high" and Th:
        B, S = _spline_projector(t, Th)
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


# ================================================================ identifikace
def fit_model(code, t, pv, mv, h, dists=(), theta_max=None, n_grid=20, fixed=None, level="none", Th=None,
              strength=4.0, stic=0.0, sign=0):
    """
    Nafituje model MV → PV (+ modely měřených poruch).
    fixed ..... zafixované parametry: {"p0": K, "p1": T1, …, "pθ" = poslední index procesu, "d{j}_{i}": parametry poruch}
    level ..... neměřené poruchy: "none", "medium" (horní propust dat), "high" (současný odhad pomalé poruchy)
    Th ........ časové měřítko neměřených poruch [s]; None = automaticky z dynamiky (dynamika × 12/strength)
    stic ...... známá stikce ventilu [% MV] – MV se před fitem převede na polohu ventilu
    sign ...... znaménko zesílení procesu: 0 = automaticky, +1 / −1 = vynucené (jako „Positive/Negative gain“)
    Postup: mřížka přes θ (je-li volné) + least squares ostatních volných parametrů, pak společné doladění.
    """
    fixed = dict(fixed or {})
    dists = [np.asarray(d, float) for d in dists]
    mv_v = stiction_valve(mv, stic) if stic else np.asarray(mv, float)
    du = mv_v - mv_v[0]
    dD = [d - d[0] for d in dists]
    nd = len(dD)
    if np.allclose(du, 0):
        raise ValueError("err_mv_const")
    span = t[-1] - t[0]
    theta_max = max(theta_max if theta_max else 0.4 * span, h)
    tmin, Tmax = 0.2 * h, 20 * span
    integ = MODELS[code]["integ"]
    nf = n_free(code)

    # časové měřítko neměřených poruch
    if level in ("medium", "high") and not Th:
        Th = auto_th(t, mv, h, strength)
    y = np.asarray(pv, float)
    proj = None
    if level == "medium":
        y, du, dD = _hp(y, Th, h), _hp(du, Th, h), [_hp(d, Th, h) for d in dD]
    elif level == "high":
        proj = _spline_projector(t, Th)

    # počáteční zesílení lineární regresí (u „high“ na datech bez pomalé složky)
    target = np.gradient(y, h) if integ else y - y[0]
    A = np.column_stack([du] + dD)
    if proj is not None:
        B_, S_ = proj
        target = target - B_ @ (S_ @ target)
        A = A - B_ @ (S_ @ A)
    coef = np.linalg.lstsq(A, target, rcond=None)[0]
    g0, kd0 = coef[0], coef[1:]
    if sign and np.sign(g0) != sign:
        g0 = -g0 if g0 != 0 else sign * 1e-3
    if abs(g0) < 1e-12:
        g0 = 1e-3 * (sign or 1)
    T0 = span / 10
    nb = 0 if level == "high" else (2 if integ else 1)
    tr_ = t - t[0]

    # plný vektor parametrů: [procesní bez θ (nf)] + [θ] + [posun (nb)] + [poruchy 3·nd]
    names = [f"p{i}" for i in range(nf)] + [f"p{nf}"] + [f"b{i}" for i in range(nb)] + \
            [f"d{j}_{i}" for j in range(nd) for i in range(3)]
    th_idx = nf
    lb = [0.0 if sign > 0 else -np.inf] + [tmin] * (nf - 1) + [0.0] + [-np.inf] * nb
    ub = [0.0 if sign < 0 else np.inf] + [Tmax] * (nf - 1) + [theta_max] + [np.inf] * nb
    th_d0 = min(h, theta_max / 2)
    for _ in range(nd):
        lb += [-np.inf, tmin, 0.0]
        ub += [np.inf, Tmax, theta_max]
    lb, ub = np.array(lb, float), np.array(ub, float)
    starts_proc = {1: [[g0]], 2: [[g0, T0], [g0, T0 / 5]], 3: [[g0, T0, T0 / 3], [g0, T0 / 3, T0 / 10]]}[nf]
    dist0 = []
    for k in kd0:
        dist0 += [k, T0 / 3, th_d0]
    base0 = [y[0], 0.0][:nb]

    fixed_mask = np.array([n in fixed for n in names])
    zfix = np.array([float(fixed.get(n, 0.0)) for n in names])
    free_nt = np.where(~fixed_mask & (np.arange(len(names)) != th_idx))[0]
    th_free = not fixed_mask[th_idx]

    def resid(z):
        p = [float(v) for v in z[:nf + 1]]
        pdl = [[float(v) for v in z[nf + 1 + nb + 3 * j: nf + 4 + nb + 3 * j]] for j in range(nd)]
        r = y - model_dev(code, p, pdl, t, du, dD, h)
        if nb:
            r = r - z[nf + 1] - (z[nf + 2] * tr_ if nb == 2 else 0.0)
        if proj is not None:
            B, S = proj
            r = r - B @ (S @ r)
        return r

    def make_z(x, theta):
        z = zfix.copy()
        z[free_nt] = x
        if th_free:
            z[th_idx] = theta
        return z

    best = None
    thetas = np.linspace(0, theta_max, n_grid) if th_free else [zfix[th_idx]]
    for theta in thetas:
        for sp_ in starts_proc:
            z0 = np.r_[sp_, 0.0, base0, dist0]
            z0 = np.where(fixed_mask, zfix, z0)
            x0 = np.clip(z0[free_nt], lb[free_nt], ub[free_nt])
            if len(x0) == 0:
                cost = 0.5 * np.sum(resid(make_z(x0, theta)) ** 2)
                if best is None or cost < best[0]:
                    best = (cost, x0, theta)
                continue
            try:
                r = least_squares(lambda x: resid(make_z(x, theta)), x0, bounds=(lb[free_nt], ub[free_nt]),
                                  max_nfev=150)
            except Exception:
                continue
            if best is None or r.cost < best[0]:
                best = (r.cost, r.x, theta)
    if best is None:
        raise ValueError("err_fit_failed")

    xb, thb = best[1], best[2]
    if th_free and len(xb):
        lb2, ub2 = np.r_[lb[free_nt], 0.0], np.r_[ub[free_nt], theta_max]
        w0 = np.clip(np.r_[xb, thb], lb2, ub2)
        try:
            r = least_squares(lambda w: resid(make_z(w[:-1], w[-1])), w0, bounds=(lb2, ub2), max_nfev=400)
            if r.cost <= best[0]:
                xb, thb = r.x[:-1], r.x[-1]
        except Exception:
            pass
    z = make_z(xb, thb)
    p = [float(v) for v in z[:nf + 1]]
    pdl = [[float(v) for v in z[nf + 1 + nb + 3 * j: nf + 4 + nb + 3 * j]] for j in range(nd)]
    if code == "P2D" and p[2] > p[1] and "p1" not in fixed and "p2" not in fixed:
        p[1], p[2] = p[2], p[1]
    res_ = resid(z)
    fit = 100.0 * (1 - np.linalg.norm(res_) / max(np.linalg.norm(y - y.mean()), 1e-12))
    return dict(code=code, p=p, pdl=pdl, fit=float(fit), level=level, Th=float(Th) if Th else None,
                stic=float(stic or 0.0), fixed=sorted(fixed))


def auto_th(t, mv, h, strength=4.0):
    """Automatické časové měřítko neměřených poruch z typického odstupu změn MV (× 4/síla potlačení)."""
    d = np.abs(np.diff(np.asarray(mv, float)))
    thr = max(0.25 * d.max(), 1e-9) if len(d) else 1e-9
    idx = np.where(d > thr)[0]
    span = t[-1] - t[0]
    spacing = float(np.median(np.diff(t[idx]))) if len(idx) > 2 else span / 4
    return float(max(spacing * 4.0 / max(strength, 0.5), 10 * h, span / 60))


def fit_with_stiction(code, t, pv, mv, h, dists=(), theta_max=None, fixed=None, level="none", Th=None,
                      strength=4.0, s_max=None, n_s=13, sign=0, k=1):
    """
    Současná identifikace stikce ventilu a modelu: mřížka přes S (stikci), pro každé S fit modelu.
    Data se předávají v plném rozlišení (stikce se počítá na plných datech), fit běží na každém k-tém vzorku.
    """
    mv = np.asarray(mv, float)
    s_max = s_max or min(max(3.0, 0.3 * float(np.ptp(mv))), 15.0)
    ds = [np.asarray(d, float)[::k] for d in dists]

    def fit_S(S, ng):
        v = stiction_valve(mv, S)
        r = fit_model(code, t[::k], pv[::k], v[::k], h * k, ds, theta_max, ng, fixed, level, Th, strength, sign=sign)
        r["stic"] = float(S)
        return r

    best = None
    step = s_max / (n_s - 1)
    for S in np.linspace(0.0, s_max, n_s):
        try:
            r = fit_S(S, 10)
        except Exception:
            continue
        if best is None or r["fit"] > best["fit"] + 0.05:
            best = r
    if best is None:
        raise ValueError("err_fit_failed")
    for dS in (-step / 2, step / 2, -step / 4, step / 4):
        S = best["stic"] + dS
        if S <= 0:
            continue
        try:
            r = fit_S(S, 10)
            if r["fit"] > best["fit"]:
                best = r
        except Exception:
            pass
    return fit_S(best["stic"], 20)


# ================================================================ hodnocení modelu
def model_metrics(y, yhat, u, h, dyn=None):
    """
    Ukazatele kvality modelu: FIT [%], NRMSE [%], IAE (průměrná abs. chyba), R²,
    test reziduí – autokorelace (bílost) a vzájemná korelace s ΔMV (nevysvětlený vliv vstupu),
    slovní hodnocení 0 (výborný) … 4 (špatný).
    """
    y, yhat, u = np.asarray(y, float), np.asarray(yhat, float), np.asarray(u, float)
    e = y - yhat
    den = np.linalg.norm(y - y.mean())
    FIT = 100 * (1 - np.linalg.norm(e) / den) if den > 0 else float("nan")
    rng_ = np.ptp(y)
    NRMSE = 100 * np.sqrt(np.mean(e ** 2)) / rng_ if rng_ > 0 else float("nan")
    IAE = float(np.mean(np.abs(e)))
    R2 = 1 - np.var(e) / np.var(y) if np.var(y) > 0 else float("nan")
    k = max(1, int(round((dyn / 10) / h))) if dyn else 1
    ed, ud = e[::k], u[::k]
    ed = ed - ed.mean()
    dud = np.diff(ud)
    n = len(ed)
    L = int(max(5, min(20, n // 6)))
    bound = 2.58 / np.sqrt(max(n, 1))
    acf = _acf(ed)[1:L + 1] if n > L + 1 and np.std(ed) > 0 else np.zeros(L)
    ccf = np.zeros(L + 1)
    if len(dud) > L + 1 and np.std(dud) > 0 and np.std(ed) > 0:
        ee = ed[1:]
        dd = dud - dud.mean()
        m = len(dd)
        for lag in range(L + 1):
            ccf[lag] = np.sum(ee[lag:m] * dd[:m - lag]) / (m * np.std(ee) * np.std(dd))
    fa = float(np.mean(np.abs(acf) > bound)) if len(acf) else 0.0
    fc = float(np.mean(np.abs(ccf) > bound)) if len(ccf) else 0.0
    st = 0 if FIT >= 90 else 1 if FIT >= 80 else 2 if FIT >= 70 else 3 if FIT >= 50 else 4
    if fc > 0.2:
        st = min(4, st + 1)
    return dict(FIT=float(FIT), NRMSE=float(NRMSE), IAE=IAE, R2=float(R2), acf=acf, ccf=ccf, bound=float(bound),
                frac_acf=fa, frac_ccf=fc, status=int(st), lag_step=k * h)


# ================================================================ ladění
def _series_to_ideal(Kc, Ti, Td):
    if Td <= 0:
        return Kc, Ti, 0.0
    f = 1 + Td / Ti
    return Kc * f, Ti * f, Td / f


def integ_gain(code, p):
    """Rychlost náběhu PV na jednotku MV (u samoregulačních aproximace K/T1)."""
    if MODELS[code]["integ"]:
        return p[0]
    if code in ("P1D", "P2D"):
        return p[0] / p[1]
    return None


def default_tc(code, p, Ts_ctrl=0.0, method="SIMC"):
    theta = p[-1] + Ts_ctrl / 2
    T = p[1] if code in ("P1D", "P2D", "I1D") else 0.0
    if method == "Lambda":  # běžná průmyslová volba λ ≈ 3θ (klidná, robustní smyčka)
        return float(max(3 * theta, 0.05 * T, Ts_ctrl, 1e-3))
    return float(max(theta, 0.02 * T, Ts_ctrl, 1e-3))  # SIMC: τc = θ („těsná“ regulace)


def _amigo(code, p, ctype):
    """AMIGO (Åström & Hägglund 2004) – robustní ladění s cílem Ms ≈ 1,4. p už obsahuje θ + Ts/2."""
    th = max(p[-1], 1e-6)
    notes = [("note_amigo", {})]
    if MODELS[code]["integ"]:
        Kv = p[0]
        L = th + (p[1] if code == "I1D" else 0.0)  # zpoždění 1. řádu přičteno k θ
        if ctype == "PID":
            Kc, Ti, Td = 0.45 / (Kv * L), 8 * L, 0.5 * L
        else:
            Kc, Ti, Td = 0.35 / (Kv * L), 13.4 * L, 0.0
        notes.append(("note_amigo_b0", {}))
        return dict(Kc=Kc, Ti=Ti, Td=Td, notes=notes)
    K = p[0]
    if code == "P0D":
        T, L = 0.0, th
    elif code == "P1D":
        T, L = p[1], th
    else:
        T, L = p[1] + p[2] / 2, th + p[2] / 2
    tau = L / (L + T)
    if ctype == "PID" and T > 0:
        Kc = (0.2 + 0.45 * T / L) / K
        Ti = L * (0.4 * L + 0.8 * T) / (L + 0.1 * T)
        Td = 0.5 * L * T / (0.3 * L + T)
    else:
        if ctype == "PID":
            notes.append(("note_nod", {}))
        Kc = 0.15 / K + (0.35 - L * T / (L + T) ** 2) * T / (K * L)
        Ti = 0.35 * L + 13 * L * T ** 2 / (T ** 2 + 12 * L * T + 7 * L ** 2)
        Td = 0.0
    notes.append(("note_amigo_b0" if tau <= 0.5 else "note_amigo_b1", dict(tau=tau)))
    return dict(Kc=Kc, Ti=Ti, Td=Td, notes=notes)


def tune(code, p, method="SIMC", tc=None, ctype="PI", Ts_ctrl=0.0, avg=None):
    """
    Návrh PI/PID v ideálním tvaru (Gain, TI, TD) – shodném s PIDConL.
    Dopravní zpoždění se zvětšuje o Ts_ctrl/2 (vliv vzorkování regulátoru).
    method: "SIMC", "Lambda", "AVG" (průměrovací) (avg = (dPV_max %, dMV_max %)).
    """
    p = list(p)
    p[-1] = p[-1] + Ts_ctrl / 2
    theta = p[-1]
    tc = tc if (tc and tc > 0) else max(theta, 1e-3)
    notes = []  # seznam (klíč textu, argumenty) – texty jsou v i18n.py

    if method == "AVG":
        kp = integ_gain(code, p)
        if kp is None:
            raise ValueError("err_avg_integ")
        dpv, dmv = avg
        Kc = abs(dmv) / abs(dpv) * np.sign(kp)
        Ti = 4.0 / (abs(kp) * abs(Kc))
        tc_eq = 1.0 / (abs(kp) * abs(Kc)) - theta
        notes.append(("note_avg", dict(tc=tc_eq)))
        if tc_eq < theta:
            notes.append(("note_avg_aggr", {}))
        if not MODELS[code]["integ"]:
            notes.append(("note_avg_selfreg", {}))
        return dict(Kc=Kc, Ti=Ti, Td=0.0, notes=notes)

    if method == "AMIGO":
        return _amigo(code, p, ctype)
    if method == "iSIMC" and code not in ("P1D", "P2D"):
        method = "SIMC"  # zlepšené pravidlo se týká jen samoregulačních procesů

    if method == "iSIMC" and code in ("P1D", "P2D"):
        K, T1 = p[0], p[1]
        th = theta
        if code == "P2D":
            if ctype == "PID":
                Kc_s, Ti_s = T1 / (K * (tc + theta)), min(T1, 4 * (tc + theta))
                Kc, Ti, Td = _series_to_ideal(Kc_s, Ti_s, p[2])
                return dict(Kc=Kc, Ti=Ti, Td=Td, notes=[("note_isimc_p2d", {}),
                                                        ("note_series", dict(kc=Kc_s, ti=Ti_s, td=p[2]))])
            T1, th = T1 + p[2] / 2, theta + p[2] / 2
            notes.append(("note_half", {}))
        if ctype == "PID" and code == "P1D":
            Kc_s, Ti_s, Td_s = T1 / (K * (tc + th)), min(T1, 4 * (tc + th)), th / 3
            Kc, Ti, Td = _series_to_ideal(Kc_s, Ti_s, Td_s)
            notes.append(("note_series", dict(kc=Kc_s, ti=Ti_s, td=Td_s)))
            return dict(Kc=Kc, Ti=Ti, Td=Td, notes=notes)
        Kc = (T1 + th / 3) / (K * (tc + th))
        Ti = min(T1 + th / 3, 4 * (tc + th))
        notes.append(("note_isimc", {}))
        return dict(Kc=Kc, Ti=Ti, Td=0.0, notes=notes)

    if code == "P0D":
        K = p[0]
        Ki = 1.0 / (K * (tc + theta))
        Kc = 0.25 / K
        return dict(Kc=Kc, Ti=Kc / Ki, Td=0.0, notes=[("note_p0d", {})])

    if code == "P1D":
        K, T1 = p[0], p[1]
        Kc = T1 / (K * (tc + theta))
        Ti = min(T1, 4 * (tc + theta)) if method == "SIMC" else T1
        if ctype == "PID":
            notes.append(("note_nod", {}))
        return dict(Kc=Kc, Ti=Ti, Td=0.0, notes=notes)

    if code == "P2D":
        K, T1, T2 = p[0], p[1], p[2]
        if ctype == "PI":
            T1e, th_e = T1 + T2 / 2, theta + T2 / 2
            Kc = T1e / (K * (tc + th_e))
            Ti = min(T1e, 4 * (tc + th_e)) if method == "SIMC" else T1e
            return dict(Kc=Kc, Ti=Ti, Td=0.0, notes=[("note_half", {})])
        Kc_s = T1 / (K * (tc + theta))
        Ti_s = min(T1, 4 * (tc + theta)) if method == "SIMC" else T1
        Kc, Ti, Td = _series_to_ideal(Kc_s, Ti_s, T2)
        return dict(Kc=Kc, Ti=Ti, Td=Td, notes=[("note_series", dict(kc=Kc_s, ti=Ti_s, td=T2))])

    if code in ("I0D", "I1D"):
        kp = p[0]
        T1 = p[1] if code == "I1D" else 0.0
        use_d = code == "I1D" and ctype == "PID"
        th = theta if use_d or code == "I0D" else theta + T1
        if method == "SIMC":
            Kc_s, Ti_s = 1.0 / (kp * (tc + th)), 4 * (tc + th)
        else:
            Kc_s, Ti_s = (2 * tc + th) / (kp * (tc + th) ** 2), 2 * tc + th
        if code == "I0D" and ctype == "PID":
            notes.append(("note_nod", {}))
        if use_d:
            Kc, Ti, Td = _series_to_ideal(Kc_s, Ti_s, T1)
            notes.append(("note_series", dict(kc=Kc_s, ti=Ti_s, td=T1)))
        else:
            Kc, Ti, Td = Kc_s, Ti_s, 0.0
            if code == "I1D":
                notes.append(("note_lag_to_delay", {}))
        return dict(Kc=Kc, Ti=Ti, Td=Td, notes=notes)
    raise ValueError(code)


def ff_gain(code, p, pd):
    """Statická dopředná vazba: ΔMV[%] = FF · Δporucha[j.]."""
    return -pd[0] / p[0]


def step_response(code, p, pdl=None, dmv=10.0, horizon=None, n=600):
    """Odezva modelu na skok MV o dmv [%] v čase 0."""
    T = p[-1] + sum(p[1:-1]) if len(p) > 2 else p[-1]
    horizon = horizon or max(6 * T, 10 * p[-1], 1.0)
    h = horizon / n
    t = np.arange(n + 1) * h
    return t, simulate(code, p, t, np.full_like(t, dmv), h)


# ================================================================ PIDConL
def _deadband(e, db, mode):
    if db <= 0 or abs(e) >= db:
        return e - np.sign(e) * db if (db > 0 and mode == "spojité") else e
    return 0.0


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


def pidconl_sim_full(code, p, pdl, h, sp, pv0, mv0, ctrl, dmeas=(), dist_mv=None, dist_pv=None):
    """
    Uzavřená smyčka: model procesu + regulátor ve struktuře PIDConL + prvky smyčky.
    h ....... krok simulace [s]; regulátor běží každých round(SampleTime/h) kroků
    sp ...... pole SP [%] (cíl); pv0, mv0 počáteční PV a MV [%] (ustálený stav)
    ctrl .... Gain, TI, TD, DiffGain, SampleTime, PropFbk, DiffFbk, DeadBand [%], DbMode, MV_Lo, MV_Hi [%],
              FF, FF_LL (dopředná vazba), PVFilt [s] (filtr PV), MVRate [%/s] (limit rychlosti MV),
              SPRate [%/s] (rampa SP), Stic, SticJ [% MV] (stikce ventilu), ValveChar (10 zesílení),
              Noise [% PV] (šum měření), Seed
    dmeas ... měřené poruchy (odchylky, j.) – působí přes modely poruch pdl a na FF
    dist_mv . neměřená porucha na vstupu procesu [% MV]; dist_pv . porucha přičtená k PV [% PV]
    Vrací dict: t, SP (cíl), SPr (po rampě), PV (skutečná), PVm (měřená po filtru), MV (výstup regulátoru),
    V (poloha ventilu), dem (max. požadovaná změna MV za krok regulátoru).
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
    ffg = list(ctrl.get("FF", [])) + [0.0] * len(dmeas)

    dd_ = max(1, int(round(p[-1] / h)))
    a1 = np.exp(-h / p[1]) if code in ("P1D", "P2D", "I1D") else 0.0
    a2 = np.exp(-h / p[2]) if code == "P2D" else 0.0
    m = max(1, int(round(ctrl["SampleTime"] / h)))
    Tc = m * h
    Kc, Ti, Td = ctrl["Gain"], ctrl["TI"], ctrl["TD"]
    use_i = Ti is not None and np.isfinite(Ti) and Ti > 0
    Tf = Td / max(ctrl.get("DiffGain", 5.0), 1e-6) if Td > 0 else 0.0
    lo, hi = ctrl.get("MV_Lo", -np.inf), ctrl.get("MV_Hi", np.inf)
    db, dbm = ctrl.get("DeadBand", 0.0), ctrl.get("DbMode", "spojité")
    pfb, dfb = ctrl.get("PropFbk", False), ctrl.get("DiffFbk", False)
    Tpv = ctrl.get("PVFilt", 0.0) or 0.0
    apv = np.exp(-h / Tpv) if Tpv > 0 else 0.0
    rate = ctrl.get("MVRate", 0.0) or 0.0
    sprate = ctrl.get("SPRate", 0.0) or 0.0
    S, J = ctrl.get("Stic", 0.0) or 0.0, ctrl.get("SticJ", None)
    J = S if J is None else min(max(J, 0.0), S)
    fch = valve_char_fn(ctrl.get("ValveChar"))
    sig = ctrl.get("Noise", 0.0) or 0.0
    noise = np.random.default_rng(int(ctrl.get("Seed", 1))).normal(0, sig, n) if sig > 0 else np.zeros(n)

    # dopředná vazba: zesílení · lead-lag (Tlead s + 1)/(Tlag s + 1) · zpoždění
    ffll = list(ctrl.get("FF_LL", [])) + [(0.0, 0.0, 0.0)] * len(dmeas)
    ff_sig = np.zeros(n)
    for g, d, (tld, tlg, tdl) in zip(ffg, dmeas, ffll):
        if g == 0:
            continue
        x = np.interp(t - tdl, t, d, left=0.0) if tdl > 0 else d
        if tlg > 0:
            x = tld / tlg * x + (1 - tld / tlg) * _lag(x, tlg, h)
        ff_sig += g * x

    buf = np.zeros(n + dd_ + 1)
    x1 = x2 = z = 0.0
    out = {k_: np.zeros(n) for k_ in ("SP", "SPr", "PV", "PVm", "MV", "V")}
    f0 = fch(mv0) if fch else mv0

    # bezrázový start: I složka nastavena tak, aby u = mv0
    y = pv0 + ydist[0]
    ym = y + noise[0]
    yf = ym
    spr = sp[0]
    e = _deadband(spr - yf, db, dbm)
    P = Kc * (-yf) if pfb else Kc * e
    I = mv0 - P - ff_sig[0]
    D = 0.0
    xd_prev = -yf if dfb else spr - yf
    u = u_prev = mv0
    v = mv0
    dem = 0.0

    for k in range(n):
        if code == "P0D":
            yd = p[0] * buf[k]
        elif code == "P1D":
            yd = p[0] * x1
        elif code == "P2D":
            yd = p[0] * x2
        else:
            yd = z
        y = pv0 + yd + ydist[k]
        ym = y + noise[k]
        yf = apv * yf + (1 - apv) * ym if Tpv > 0 else ym

        if k % m == 0:
            if sprate > 0:
                spr = spr + float(np.clip(sp[k] - spr, -sprate * Tc, sprate * Tc))
            else:
                spr = sp[k]
            e = _deadband(spr - yf, db, dbm)
            P = Kc * (-yf) if pfb else Kc * e
            xd = -yf if dfb else spr - yf
            if Td > 0:
                D = Tf / (Tf + Tc) * D + Kc * Td / (Tf + Tc) * (xd - xd_prev)
            xd_prev = xd
            inc = Kc * Tc / Ti * e if use_i else 0.0
            u_un = P + I + inc + D + ff_sig[k]
            dem = max(dem, abs(u_un - u_prev))
            u = min(max(u_un, lo), hi)
            if rate > 0:
                u = float(np.clip(u, u_prev - rate * Tc, u_prev + rate * Tc))
            # anti-windup: při omezení (limit nebo rychlost) integruj jen směrem, který omezení uvolňuje
            if u == u_un or (u_un > u and inc < 0) or (u_un < u and inc > 0):
                I += inc
            u_prev = u

        # ventil: stikce a charakteristika
        if S > 0:
            dv = u - v
            if abs(dv) > S:
                v = u - np.sign(dv) * (S - J)
        else:
            v = u
        uin = (fch(v) - f0) if fch else (v - mv0)
        buf[k + dd_] = uin + dist_mv[k]
        ud = buf[k]
        if code in ("P1D", "P2D", "I1D"):
            x1n = a1 * x1 + (1 - a1) * ud
            if code == "P2D":
                x2 = a2 * x2 + (1 - a2) * x1
            x1 = x1n
        if code == "I0D":
            z += p[0] * ud * h
        elif code == "I1D":
            z += p[0] * x1 * h
        out["SP"][k], out["SPr"][k], out["PV"][k], out["PVm"][k], out["MV"][k], out["V"][k] = sp[k], spr, y, yf, u, v
    out["t"] = t
    out["dem"] = dem / Tc
    return out


def pidconl_sim(code, p, pdl, h, sp, pv0, mv0, ctrl, dmeas=(), dist_mv=None, dist_pv=None):
    """Zkrácené rozhraní: vrací t, SP (efektivní, po rampě), PV (skutečná), MV."""
    r = pidconl_sim_full(code, p, pdl, h, sp, pv0, mv0, ctrl, dmeas, dist_mv, dist_pv)
    return r["t"], r["SPr"], r["PV"], r["MV"]


def iae(t, sp, pv):
    trap = getattr(np, "trapezoid", None) or np.trapz
    return float(trap(np.abs(sp - pv), t))


# ================================================================ robustnost
def loop_tf(code, p, ctrl, w):
    s = 1j * w
    if code == "P0D":
        G = p[0] * np.ones_like(s)
    elif code == "P1D":
        G = p[0] / (p[1] * s + 1)
    elif code == "P2D":
        G = p[0] / ((p[1] * s + 1) * (p[2] * s + 1))
    elif code == "I0D":
        G = p[0] / s
    else:
        G = p[0] / (s * (p[1] * s + 1))
    G = G * np.exp(-s * (p[-1] + ctrl["SampleTime"] / 2))
    if ctrl.get("PVFilt", 0) and ctrl["PVFilt"] > 0:
        G = G / (ctrl["PVFilt"] * s + 1)
    Kc, Ti, Td = ctrl["Gain"], ctrl["TI"], ctrl["TD"]
    C = np.ones_like(s)
    if Ti and np.isfinite(Ti) and Ti > 0:
        C = C + 1 / (Ti * s)
    if Td > 0:
        C = C + Td * s / (1 + Td * s / max(ctrl.get("DiffGain", 5.0), 1e-6))
    return Kc * C * G


def _n_integrators(code, ctrl):
    Ti = ctrl.get("TI")
    return (1 if MODELS[code]["integ"] else 0) + (1 if Ti and np.isfinite(Ti) and Ti > 0 else 0)


def _freq_grid(code, p, ctrl, n=4000):
    Tchar = p[-1] + (p[1] if code in ("P1D", "P2D", "I1D") else 0) + ctrl["SampleTime"] + 1e-6
    w_hi = np.pi / max(ctrl["SampleTime"], 1e-6)
    return np.logspace(np.log10(1e-5 / Tchar), np.log10(w_hi), n)


def is_stable(code, p, ctrl, w=None, L=None):
    """
    Nyquistovo kritérium pro otevřenou smyčku bez nestabilních pólů (integrátory v počátku jsou povoleny):
    stabilní ⇔ změna úhlu (1 + L(jω)) pro ω: 0+ → ∞ je n·π/2 (n = počet integrátorů) a |L| na konci < 1.
    """
    if L is None:
        w = _freq_grid(code, p, ctrl) if w is None else w
        L = loop_tf(code, p, ctrl, w)
    if not np.all(np.isfinite(L)) or np.abs(L[-1]) >= 1:
        return False
    d = np.unwrap(np.angle(1 + L))
    return bool(abs((d[-1] - d[0]) - _n_integrators(code, ctrl) * np.pi / 2) < np.pi / 2)


def robustness(code, p, ctrl):
    """Ms (max. citlivost), Mt, amplitudová bezpečnost GM, fázová bezpečnost PM [°], stabilita."""
    w = _freq_grid(code, p, ctrl)
    L = loop_tf(code, p, ctrl, w)
    mag, ph = np.abs(L), np.unwrap(np.angle(L))
    if ph[0] > 0.5 * np.pi:
        ph -= 2 * np.pi
    Ms = float(np.max(np.abs(1 / (1 + L))))
    Mt = float(np.max(np.abs(L / (1 + L))))
    PM = GM = float("nan")
    i = np.where((mag[:-1] >= 1) & (mag[1:] < 1))[0]
    if len(i):
        i = i[-1]
        f = (mag[i] - 1) / (mag[i] - mag[i + 1])
        PM = float(np.degrees(np.pi + ph[i] + f * (ph[i + 1] - ph[i])))
    j = np.where((ph[:-1] > -np.pi) & (ph[1:] <= -np.pi))[0]
    if len(j):
        j = j[0]
        f = (ph[j] + np.pi) / (ph[j] - ph[j + 1])
        GM = float(1 / (mag[j] + f * (mag[j + 1] - mag[j])))
    return dict(Ms=Ms, Mt=Mt, GM=GM, PM=PM, stable=is_stable(code, p, ctrl, L=L))


def hf_gain(Kc, Td, N, Ts):
    """Vysokofrekvenční zesílení diskrétního PID (P + D s filtrem TD/N, vzorkování Ts)."""
    return abs(Kc) * (1 + (Td / (Td / max(N, 1e-6) + Ts) if Td > 0 else 0.0))


def mv_noise(ctrl, sigma_pv):
    """Přibližná směrodatná odchylka šumu MV [%] z bílého šumu PV [%]."""
    return hf_gain(ctrl["Gain"], ctrl.get("TD", 0.0), ctrl.get("DiffGain", 5.0), ctrl.get("SampleTime", 1.0)) * sigma_pv


# ================================================================ doporučení D a optimalizace
def d_advice(code, p):
    """Doporučení D složky podle poměru dopravního zpoždění a časových konstant."""
    th = p[-1]
    if code == "P0D":
        return dict(key="d_p0d", tau=1.0, rec="PI")
    if code == "I0D":
        return dict(key="d_i0d", tau=None, rec="PI")
    if code == "I1D":
        return dict(key="d_i1d_yes" if p[1] > th else "d_i1d_no", tau=None, rec="PID" if p[1] > th else "PI",
                    ratio=p[1] / max(th, 1e-9))
    if code == "P2D" and p[2] > th:
        tau = (th + p[2] / 2) / (th + p[1] + p[2])
        return dict(key="d_p2d_yes", tau=tau, rec="PID", ratio=p[2] / max(th, 1e-9))
    T = p[1] + (p[2] / 2 if code == "P2D" else 0)
    L = th + (p[2] / 2 if code == "P2D" else 0)
    tau = L / (L + T)
    if tau < 0.1:
        return dict(key="d_lag", tau=tau, rec="PI")
    if tau < 0.6:
        return dict(key="d_balanced", tau=tau, rec="PID")
    return dict(key="d_delay", tau=tau, rec="PI")


def optimize_migo(code, p, ctype, Ts_ctrl, diffgain=5.0, Ms_max=1.6, hf_max=None, starts=(), extra_ps=(), pvf=0.0):
    """
    MIGO (Åström–Hägglund): maximalizace integračního zesílení Ki = Gain/TI – tedy minimalizace
    integrované chyby při poruše na vstupu – za podmínky Ms ≤ Ms_max, Mt ≤ Ms_max, stability a u PID TD ≤ TI/4.
    Pro PID volitelně omezení vysokofrekvenčního zesílení (šum do MV): hf_gain ≤ hf_max.
    extra_ps: další varianty modelu (nejistota) – podmínky Ms/Mt a stabilita musí platit pro všechny.
    """
    from scipy.optimize import minimize
    sgn = 1.0 if p[0] >= 0 else -1.0
    base = dict(DiffGain=diffgain, SampleTime=Ts_ctrl, PVFilt=pvf)
    w = _freq_grid(code, p, dict(base, TI=1.0), n=1500)
    pid = ctype == "PID"

    def unpack(x):
        Kc = sgn * np.exp(x[0])
        Ti = np.exp(x[1])
        Td = np.exp(x[2]) if pid else 0.0
        return Kc, Ti, Td

    def cost(x):
        Kc, Ti, Td = unpack(x)
        ctrl = dict(base, Gain=Kc, TI=Ti, TD=Td)
        Ms = Mt = 0.0
        for pp in [p] + list(extra_ps):
            L = loop_tf(code, pp, ctrl, w)
            if not is_stable(code, pp, ctrl, L=L):
                return 1e6
            Ms = max(Ms, np.max(np.abs(1 / (1 + L))))
            Mt = max(Mt, np.max(np.abs(L / (1 + L))))
        pen = 200 * max(0.0, Ms / Ms_max - 1) ** 2 + 200 * max(0.0, Mt / Ms_max - 1) ** 2
        if pid:  # realizovatelné, „rozumné“ PID: TD ≤ TI/4 (reálné nuly regulátoru)
            pen += 200 * max(0.0, 4 * Td / Ti - 1) ** 2
        if pid and hf_max:
            pen += 200 * max(0.0, hf_gain(Kc, Td, diffgain, Ts_ctrl) / hf_max - 1) ** 2
        return -np.log(abs(Kc) / Ti) + pen

    best = None
    for Kc0, Ti0, Td0 in starts:
        if not (np.isfinite(Kc0) and np.isfinite(Ti0) and Kc0 != 0 and Ti0 > 0):
            continue
        for scale in (1.0, 0.5):
            x0 = [np.log(abs(Kc0) * scale), np.log(Ti0)] + ([np.log(max(Td0, 0.05 * Ti0))] if pid else [])
            if cost(x0) >= 1e6:
                continue
            r = minimize(cost, x0, method="Nelder-Mead",
                         options=dict(maxiter=1500, xatol=1e-4, fatol=1e-6))
            if best is None or r.fun < best.fun:
                best = r
    if best is None or best.fun >= 1e6:
        raise ValueError("err_opt_failed")
    Kc, Ti, Td = unpack(best.x)
    notes = [("note_opt", dict(ms=Ms_max))] + ([("note_opt_robust", dict(n=len(extra_ps)))] if extra_ps else [])
    return dict(Kc=float(Kc), Ti=float(Ti), Td=float(Td), notes=notes)


# ================================================================ optimalizace podle časových kritérií (IAE, ISE, ITAE, překmit)
def _padd(a, b):
    n = max(len(a), len(b))
    return np.pad(np.asarray(a, float), (0, n - len(a))) + np.pad(np.asarray(b, float), (0, n - len(b)))


def _proc_poly(code, p, h):
    """Diskrétní model procesu B(z⁻¹)/A(z⁻¹) – stejná diskretizace jako pidconl_sim (krok h)."""
    d = max(1, int(round(p[-1] / h)))
    zd = np.zeros(d + 1)
    zd[d] = 1.0
    if code == "P0D":
        return p[0] * zd, np.array([1.0])
    if code == "P1D":
        a = np.exp(-h / p[1])
        return np.convolve(zd, [0.0, p[0] * (1 - a)]), np.array([1.0, -a])
    if code == "P2D":
        a1, a2 = np.exp(-h / p[1]), np.exp(-h / p[2])
        return p[0] * np.convolve(zd, np.convolve([0.0, 1 - a1], [0.0, 1 - a2])), np.convolve([1.0, -a1], [1.0, -a2])
    if code == "I0D":
        return np.convolve(zd, [0.0, p[0] * h]), np.array([1.0, -1.0])
    a1 = np.exp(-h / p[1])
    return p[0] * h * np.convolve(zd, [0.0, 1 - a1]), np.convolve([1.0, -a1], [1.0, -1.0])


def _ctrl_poly(ctrl, h):
    """PIDConL (ideální tvar, D s filtrem, P/D ve zpětné vazbě) jako polynomy: u = Nr/Dc·r − Ny/Dc·y."""
    Kc, Ti, Td = ctrl["Gain"], ctrl["TI"], ctrl["TD"]
    N = ctrl.get("DiffGain", 5.0)
    Tf = Td / N if Td > 0 else 0.0
    cf = Tf / (Tf + h) if Td > 0 else 0.0
    Ki = Kc * h / Ti if (Ti and np.isfinite(Ti) and Ti > 0) else 0.0
    Kd = Kc * Td / (Tf + h) if Td > 0 else 0.0
    beta = 0.0 if ctrl.get("PropFbk") else 1.0
    gam = 0.0 if ctrl.get("DiffFbk") else 1.0
    d1 = np.convolve([1.0, -1.0], [1.0, -cf])
    d2 = np.convolve([1.0, -1.0], [1.0, -1.0])
    oc = np.array([1.0, -cf])
    Ny = _padd(_padd(Kc * d1, Ki * oc), Kd * d2)
    Nr = _padd(_padd(Kc * beta * d1, Ki * oc), Kd * gam * d2)
    return Nr, Ny, d1


def _loop_polys(code, p, ctrl, h):
    B, A = _proc_poly(code, p, h)
    Nr, Ny, Dc = _ctrl_poly(ctrl, h)
    Tpv = ctrl.get("PVFilt", 0.0) or 0.0
    if Tpv > 0:  # filtr PV: yf = (1−a)/(1 − a z⁻¹) · y
        a_ = np.exp(-h / Tpv)
        Bf, Af = np.array([1 - a_]), np.array([1.0, -a_])
    else:
        Bf, Af = np.array([1.0]), np.array([1.0])
    den = _padd(np.convolve(np.convolve(A, Dc), Af), np.convolve(np.convolve(B, Ny), Bf))
    return B, A, Nr, Ny, Dc, Bf, Af, den


def closed_loop_steps(code, p, ctrl, h, n, with_u=False):
    """Lineární odezvy uzavřené smyčky na jednotkový skok SP a poruchy na vstupu procesu (rychle, přes lfilter)."""
    B, A, Nr, Ny, Dc, Bf, Af, den = _loop_polys(code, p, ctrl, h)
    one = np.ones(n)
    y_sp = lfilter(np.convolve(np.convolve(B, Nr), Af), den, one)
    y_d = lfilter(np.convolve(np.convolve(B, Dc), Af), den, one)
    if not with_u:
        return 1.0 - y_sp, -y_d  # regulační odchylky
    u_sp = lfilter(np.convolve(np.convolve(A, Nr), Af), den, one)
    u_d = lfilter(-np.convolve(np.convolve(B, Ny), Bf), den, one)
    return 1.0 - y_sp, -y_d, u_sp, u_d


def _crit(e, h, crit, ovs_lim):
    t = np.arange(len(e)) * h
    if crit == "ISE":
        return float(np.sum(e ** 2) * h)
    if crit == "ITAE":
        return float(np.sum(t * np.abs(e)) * h)
    J = float(np.sum(np.abs(e)) * h)
    if crit == "OVS":
        k = int(np.argmax(np.abs(e)))
        pk = e[k]
        opp = float(np.max(-np.sign(pk) * e[k:])) if pk != 0 else 0.0
        ratio = max(opp, 0.0) / max(abs(pk), 1e-12)
        J *= 1.0 + 200.0 * max(0.0, ratio - ovs_lim) + 2000.0 * max(0.0, ratio - ovs_lim) ** 2
    return J


def overshoot_ratio(e):
    k = int(np.argmax(np.abs(e)))
    pk = e[k]
    return float(max(np.max(-np.sign(pk) * e[k:]), 0.0) / max(abs(pk), 1e-12)) if pk != 0 else 0.0


def optimize_time(code, p, ctype, Ts_ctrl, diffgain=5.0, crit="IAE", target="both", Ms_max=1.6, hf_max=None,
                  starts=(), extra_ps=(), ovs_lim=0.02, pfb=False, dfb=True, pvf=0.0, rate=0.0, sp_amp=1.0, d_amp=1.0):
    """
    Optimalizace parametrů podle časového kritéria odezvy (IAE, ISE, ITAE nebo IAE s limitem překmitu „OVS“)
    na skok SP, skok poruchy na vstupu procesu nebo obojí. Vždy s podmínkou robustnosti Ms (a Mt) ≤ Ms_max,
    stability, u PID TD ≤ TI/4 a volitelně limitu šumu MV. Odezvy se počítají na diskrétním modelu s regulátorem
    PIDConL (SampleTime, DiffGain, P/D ve zpětné vazbě); limity MV a deadband se ověřují až v simulaci.
    """
    from scipy.optimize import minimize
    sgn = 1.0 if p[0] >= 0 else -1.0
    pid = ctype == "PID"
    th = p[-1]
    Tsum = (p[1] if code in ("P1D", "P2D", "I1D") else 0.0) + (p[2] if code == "P2D" else 0.0)
    Ti_s = max([s[1] for s in starts if np.isfinite(s[1])] + [1.0])
    Th = max(40 * (th + Tsum + Ts_ctrl), 8 * Ti_s, 200 * Ts_ctrl)
    h = max(Ts_ctrl, Th / 8000)
    n = int(Th / h) + 1
    base = dict(DiffGain=diffgain, SampleTime=Ts_ctrl, PropFbk=pfb, DiffFbk=dfb, PVFilt=pvf)
    w = _freq_grid(code, p, dict(base, TI=1.0), n=1200)
    rate_state = {"du": 0.0}

    def unpack(x):
        return sgn * np.exp(x[0]), np.exp(x[1]), (np.exp(x[2]) if pid else 0.0)

    def responses(Kc, Ti, Td):
        if rate > 0:
            e_sp, e_d, u_sp, u_d = closed_loop_steps(code, p, dict(base, Gain=Kc, TI=Ti, TD=Td), h, n, True)
            rate_state["du"] = max(np.max(np.abs(np.diff(np.r_[0.0, u_sp]))) * abs(sp_amp) if target != "dist" else 0,
                                   np.max(np.abs(np.diff(np.r_[0.0, u_d]))) * abs(d_amp) if target != "sp" else 0) / h
        else:
            e_sp, e_d = closed_loop_steps(code, p, dict(base, Gain=Kc, TI=Ti, TD=Td), h, n)
        if not (np.all(np.isfinite(e_sp)) and np.all(np.isfinite(e_d))):
            return None
        tail = slice(int(0.9 * n), n)
        if np.max(np.abs(e_sp[tail])) > 0.05 or np.max(np.abs(e_d[tail])) > 0.05 * max(np.max(np.abs(e_d)), 1e-9):
            return None  # neustálí se (nestabilní nebo extrémně pomalé)
        return e_sp, e_d

    def raw_J(Kc, Ti, Td):
        r = responses(Kc, Ti, Td)
        if r is None:
            return None
        e_sp, e_d = r
        return _crit(e_sp, h, crit, ovs_lim), _crit(e_d, h, crit, ovs_lim)

    # normalizace podle výchozího bodu (aby SP a porucha vážily v „obojím“ stejně)
    J0 = None
    for s in starts:
        if s[0] != 0 and np.isfinite(s[0]) and s[1] > 0:
            J0 = raw_J(*s)
            if J0 is not None:
                break
    if J0 is None:
        raise ValueError("err_opt_failed")
    J0 = (max(J0[0], 1e-12), max(J0[1], 1e-12))

    def cost(x):
        Kc, Ti, Td = unpack(x)
        ctrl = dict(base, Gain=Kc, TI=Ti, TD=Td)
        Ms = Mt = 0.0
        for pp in [p] + list(extra_ps):
            L = loop_tf(code, pp, ctrl, w)
            if not is_stable(code, pp, ctrl, L=L):
                return 1e6
            Ms = max(Ms, np.max(np.abs(1 / (1 + L))))
            Mt = max(Mt, np.max(np.abs(L / (1 + L))))
        pen = 200 * max(0.0, Ms / Ms_max - 1) ** 2 + 200 * max(0.0, Mt / Ms_max - 1) ** 2
        if pid:
            pen += 200 * max(0.0, 4 * Td / Ti - 1) ** 2
            if hf_max:
                pen += 200 * max(0.0, hf_gain(Kc, Td, diffgain, Ts_ctrl) / hf_max - 1) ** 2
        J = raw_J(Kc, Ti, Td)
        if J is None:
            return 1e6
        if rate > 0:
            pen += 200 * max(0.0, rate_state["du"] / rate - 1) ** 2
        Js, Jd = J[0] / J0[0], J[1] / J0[1]
        val = Js if target == "sp" else Jd if target == "dist" else 0.5 * (Js + Jd)
        return np.log(max(val, 1e-12)) + pen

    best = None
    for Kc0, Ti0, Td0 in starts:
        if not (np.isfinite(Kc0) and np.isfinite(Ti0) and Kc0 != 0 and Ti0 > 0):
            continue
        x0 = [np.log(abs(Kc0)), np.log(Ti0)] + ([np.log(max(Td0, 0.05 * Ti0))] if pid else [])
        if cost(x0) >= 1e6:
            x0[0] -= np.log(2)
            if cost(x0) >= 1e6:
                continue
        r = minimize(cost, x0, method="Nelder-Mead", options=dict(maxiter=600, xatol=1e-3, fatol=1e-4))
        if best is None or r.fun < best.fun:
            best = r
    if best is None or best.fun >= 1e6:
        raise ValueError("err_opt_failed")
    Kc, Ti, Td = unpack(best.x)
    notes = [("note_topt", dict(ms=Ms_max))] + ([("note_opt_robust", dict(n=len(extra_ps)))] if extra_ps else [])
    if crit == "OVS":
        e_sp, e_d = closed_loop_steps(code, p, dict(base, Gain=Kc, TI=Ti, TD=Td), h, n)
        ratio = overshoot_ratio(e_sp if target != "dist" else e_d)
        if ratio > ovs_lim + 0.005:
            notes.append(("note_ovs_fail", dict(r=100 * ratio, lim=100 * ovs_lim)))
    return dict(Kc=float(Kc), Ti=float(Ti), Td=float(Td), notes=notes)


def optimize_scenario(code, p, pdl, ctype, ctrl_base, crit, h, sp, pv0, mv0, dmeas=(), dist_mv=None, dist_pv=None,
                      Ms_max=1.6, hf_max=None, starts=(), extra_ps=(), ovs_lim=0.02):
    """
    Optimalizace na celém scénáři simulace (skoky/rampy/sinus/pulzy SP a poruch) včetně nelineárních prvků
    smyčky (limity a rychlost MV, deadband, rampa SP, filtr PV, stikce, charakteristika ventilu).
    Kritérium se počítá z odchylky SP − PV; podmínky Ms (lineární model), TD ≤ TI/4, šum MV a limit rychlosti MV.
    """
    from scipy.optimize import minimize
    sgn = 1.0 if p[0] >= 0 else -1.0
    pid = ctype == "PID"
    base = {k: v for k, v in ctrl_base.items() if k not in ("Gain", "TI", "TD")}
    base["Noise"] = 0.0
    rate = base.get("MVRate", 0.0) or 0.0
    w = _freq_grid(code, p, dict(base, TI=1.0), n=1000)

    def unpack(x):
        return sgn * np.exp(x[0]), np.exp(x[1]), (np.exp(x[2]) if pid else 0.0)

    def J_of(Kc, Ti, Td):
        r = pidconl_sim_full(code, p, pdl, h, sp, pv0, mv0, dict(base, Gain=Kc, TI=Ti, TD=Td), dmeas, dist_mv, dist_pv)
        e = r["SPr"] - r["PV"]
        if not np.all(np.isfinite(e)) or np.abs(e).max() > 1e4:
            return None, None
        return _crit(e, h, crit, ovs_lim), r["dem"]

    J0 = None
    for s in starts:
        if s[0] != 0 and np.isfinite(s[0]) and s[1] > 0:
            J0 = J_of(*s)[0]
            if J0:
                break
    if not J0:
        raise ValueError("err_opt_failed")

    def cost(x):
        Kc, Ti, Td = unpack(x)
        ctrl = dict(base, Gain=Kc, TI=Ti, TD=Td)
        Ms = Mt = 0.0
        for pp in [p] + list(extra_ps):
            L = loop_tf(code, pp, ctrl, w)
            if not is_stable(code, pp, ctrl, L=L):
                return 1e6
            Ms = max(Ms, np.max(np.abs(1 / (1 + L))))
            Mt = max(Mt, np.max(np.abs(L / (1 + L))))
        pen = 200 * max(0.0, Ms / Ms_max - 1) ** 2 + 200 * max(0.0, Mt / Ms_max - 1) ** 2
        if pid:
            pen += 200 * max(0.0, 4 * Td / Ti - 1) ** 2
            if hf_max:
                pen += 200 * max(0.0, hf_gain(Kc, Td, base.get("DiffGain", 5.0), base["SampleTime"]) / hf_max - 1) ** 2
        J, dem = J_of(Kc, Ti, Td)
        if J is None:
            return 1e6
        if rate > 0:
            pen += 200 * max(0.0, dem / rate - 1) ** 2
        return np.log(max(J / J0, 1e-12)) + pen

    best = None
    for Kc0, Ti0, Td0 in starts:
        if not (np.isfinite(Kc0) and np.isfinite(Ti0) and Kc0 != 0 and Ti0 > 0):
            continue
        x0 = [np.log(abs(Kc0)), np.log(Ti0)] + ([np.log(max(Td0, 0.05 * Ti0))] if pid else [])
        if cost(x0) >= 1e6:
            continue
        r = minimize(cost, x0, method="Nelder-Mead", options=dict(maxiter=250, xatol=2e-3, fatol=1e-3))
        if best is None or r.fun < best.fun:
            best = r
    if best is None or best.fun >= 1e6:
        raise ValueError("err_opt_failed")
    Kc, Ti, Td = unpack(best.x)
    return dict(Kc=float(Kc), Ti=float(Ti), Td=float(Td), notes=[("note_scen", dict(ms=Ms_max))])


# ================================================================ krokový simulátor (kaskáda)
class ProcStep:
    """Proces krok po kroku (stejná diskretizace jako pidconl_sim)."""

    def __init__(self, code, p, h):
        self.code, self.p, self.h = code, list(p), h
        self.q = [0.0] * max(1, int(round(p[-1] / h)))
        self.a1 = np.exp(-h / p[1]) if code in ("P1D", "P2D", "I1D") else 0.0
        self.a2 = np.exp(-h / p[2]) if code == "P2D" else 0.0
        self.x1 = self.x2 = self.z = 0.0

    def output(self):
        c = self.code
        if c == "P0D":
            return self.p[0] * self.q[0]
        if c == "P1D":
            return self.p[0] * self.x1
        if c == "P2D":
            return self.p[0] * self.x2
        return self.z

    def step(self, u):
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


class PIDStep:
    """PIDConL krok po kroku (ideální tvar, D s filtrem, anti-windup, P/D ve zpětné vazbě)."""

    def __init__(self, ctrl, h):
        self.c = ctrl
        self.m = max(1, int(round(ctrl["SampleTime"] / h)))
        self.Tc = self.m * h
        self.Kc, self.Ti, self.Td = ctrl["Gain"], ctrl["TI"], ctrl["TD"]
        self.use_i = self.Ti is not None and np.isfinite(self.Ti) and self.Ti > 0
        self.Tf = self.Td / max(ctrl.get("DiffGain", 5.0), 1e-6) if self.Td > 0 else 0.0
        self.lo, self.hi = ctrl.get("MV_Lo", -np.inf), ctrl.get("MV_Hi", np.inf)
        self.pfb, self.dfb = ctrl.get("PropFbk", False), ctrl.get("DiffFbk", False)
        self.k = 0

    def init(self, sp, y, u0):
        P = self.Kc * (-y) if self.pfb else self.Kc * (sp - y)
        self.I, self.D, self.u = u0 - P, 0.0, u0
        self.xd_prev = -y if self.dfb else sp - y

    def update(self, sp, y):
        if self.k % self.m == 0:
            e = sp - y
            P = self.Kc * (-y) if self.pfb else self.Kc * e
            xd = -y if self.dfb else sp - y
            if self.Td > 0:
                self.D = self.Tf / (self.Tf + self.Tc) * self.D + self.Kc * self.Td / (self.Tf + self.Tc) * (xd - self.xd_prev)
            self.xd_prev = xd
            inc = self.Kc * self.Tc / self.Ti * e if self.use_i else 0.0
            u_un = P + self.I + inc + self.D
            self.u = min(max(u_un, self.lo), self.hi)
            if self.u == u_un or (u_un > self.hi and inc < 0) or (u_un < self.lo and inc > 0):
                self.I += inc
        self.k += 1
        return self.u


def cascade_sim(inner, ictrl, outer, octrl, h, sp_o, d_inner=None, d_outer=None, pv0_o=50.0, x0_i=50.0, mv0_i=50.0):
    """
    Kaskáda: vnější regulátor → SP vnitřní smyčky; vnitřní regulátor → ventil.
    inner/outer = (code, p). Vnější proces má jako vstup PV vnitřní smyčky (odchylka, %).
    d_inner: porucha na vstupu vnitřního procesu [% MV], d_outer: porucha na vstupu vnějšího procesu [%].
    """
    n = len(sp_o)
    pi_, po_ = ProcStep(*inner, h), ProcStep(*outer, h)
    ci, co = PIDStep(ictrl, h), PIDStep(octrl, h)
    d_inner = np.zeros(n) if d_inner is None else d_inner
    d_outer = np.zeros(n) if d_outer is None else d_outer
    co.init(sp_o[0], pv0_o, x0_i)
    ci.init(x0_i, x0_i, mv0_i)
    out = np.zeros((n, 5))
    for k in range(n):
        yi = x0_i + pi_.output()
        yo = pv0_o + po_.output()
        spi = co.update(sp_o[k], yo)
        u = ci.update(spi, yi)
        pi_.step(u - mv0_i + d_inner[k])
        po_.step(yi - x0_i + d_outer[k])
        out[k] = (sp_o[k], yo, spi, yi, u)
    return np.arange(n) * h, out


# ================================================================ diagnostika
def _acf(x):
    x = np.asarray(x, float) - np.mean(x)
    n = len(x)
    f = np.fft.rfft(x, 2 * n)
    a = np.fft.irfft(f * np.conj(f))[:n]
    return a / a[0] if a[0] > 0 else a


def oscillation(x, h):
    """
    Detekce oscilací přes autokorelaci (Thornhill): perioda a pravidelnost r.
    r > 1 ⇒ pravidelná oscilace. Vrací dict(osc, period, r, amp).
    """
    x = np.asarray(x, float)
    if len(x) < 50 or np.std(x) == 0:
        return dict(osc=False, period=np.nan, r=0.0, amp=0.0)
    tt = np.arange(len(x))
    x = x - np.polyval(np.polyfit(tt, x, 1), tt)
    a = _acf(x)[: len(x) // 2]
    zc = np.where(np.sign(a[:-1]) != np.sign(a[1:]))[0]
    amp = float((np.percentile(x, 95) - np.percentile(x, 5)) / 2)
    if len(zc) < 5:
        return dict(osc=False, period=np.nan, r=0.0, amp=amp)
    zc = zc[:12]
    per = 2 * np.diff(zc) * h
    Tp = float(np.mean(per))
    r = float(Tp / (3 * np.std(per))) if np.std(per) > 0 else 10.0
    # první maximum ACF po první nule musí být výrazné
    peak = float(np.max(a[zc[1]:zc[2] + 1]))  # první kladné maximum ACF (jedna perioda)
    return dict(osc=bool(r > 1 and peak > 0.2), period=Tp, r=r, amp=amp)


def stiction_ccf(mv, pv, h, integ, period=None):
    """
    Horchův test: korelace MV a PV (u integračních procesů MV a dPV/dt).
    Lichá korelace (ρ(0) ≈ 0) ukazuje na stikci ventilu, sudá (maximum u nuly) spíš na ladění / vnější poruchu.
    Vrací poměr |ρ(0)| / max|ρ| a průběh korelace.
    """
    x = np.asarray(mv, float)
    y = np.gradient(np.asarray(pv, float), h) if integ else np.asarray(pv, float)
    x, y = x - x.mean(), y - y.mean()
    n = len(x)
    L = int(min(n // 3, (period / h if period and np.isfinite(period) else n // 6)))
    L = max(L, 5)
    lags = np.arange(-L, L + 1)
    den = np.std(x) * np.std(y) * n
    if den == 0:
        return dict(ratio=np.nan, lags=lags * h, ccf=np.zeros_like(lags, float))
    nf = 1 << int(np.ceil(np.log2(2 * n)))
    full = np.fft.irfft(np.conj(np.fft.rfft(x, nf)) * np.fft.rfft(y, nf), nf)  # full[k] = Σ x[i]·y[i+k]
    ccf = np.r_[full[nf - L:], full[:L + 1]] / den
    ratio = float(abs(ccf[L]) / max(np.max(np.abs(ccf)), 1e-12))
    return dict(ratio=ratio, lags=lags * h, ccf=ccf)


def valve_hysteresis(mv, pos, nbins=20):
    """Odhad hystereze/vůle ventilu z MV a měřené polohy: rozdíl MV při otevírání a zavírání pro stejnou polohu."""
    mv, pos = np.asarray(mv, float), np.asarray(pos, float)
    d = np.sign(np.diff(mv))
    d = np.r_[d[0] if len(d) else 0, d]
    # směr pohybu držíme i během konstantní MV
    for i in range(1, len(d)):
        if d[i] == 0:
            d[i] = d[i - 1]
    edges = np.linspace(np.percentile(pos, 2), np.percentile(pos, 98), nbins + 1)
    diffs = []
    for a, b in zip(edges[:-1], edges[1:]):
        m = (pos >= a) & (pos < b)
        up, dn = mv[m & (d > 0)], mv[m & (d < 0)]
        if len(up) > 3 and len(dn) > 3:
            diffs.append(np.median(up) - np.median(dn))
    return float(np.median(diffs)) if diffs else float("nan")


def harris_index(e, d, p_ar=20):
    """
    Harrisův index (minimum variance, FCOR): η = σ²_MV / σ²_e ∈ (0, 1].
    d = dopravní zpoždění ve vzorcích (≥ 1). Blízko 1 = regulace na hranici možností, malé = prostor ke zlepšení.
    """
    e = np.asarray(e, float) - np.mean(e)
    n = len(e)
    p_ar = int(min(p_ar, n // 10))
    if n < 100 or p_ar < 2 or np.var(e) == 0:
        return float("nan")
    X = np.column_stack([e[p_ar - i - 1:n - i - 1] for i in range(p_ar)])
    yv = e[p_ar:]
    a = np.linalg.lstsq(X, yv, rcond=None)[0]
    s2 = np.var(yv - X @ a)
    d = max(1, int(d))
    psi = np.zeros(d)
    psi[0] = 1.0
    for i in range(1, d):
        psi[i] = sum(a[j] * psi[i - j - 1] for j in range(min(p_ar, i)))
    return float(min(1.0, s2 * np.sum(psi ** 2) / np.var(e)))


def loop_kpis(t, sp, pv, mv, h, mv_lo, mv_hi, theta, has_sp=True):
    """Ukazatele výkonu smyčky z provozních dat (veličiny v %)."""
    e = (sp - pv) if has_sp else (pv - np.mean(pv))
    hours = max((t[-1] - t[0]) / 3600, 1e-9)
    dmv = np.diff(mv)
    thr = max(1e-6, 0.05 * np.std(dmv)) if len(dmv) else 1e-6
    s = np.sign(dmv[np.abs(dmv) > thr])
    rev = int(np.sum(s[1:] != s[:-1])) if len(s) > 1 else 0
    osc = oscillation(e, h)
    return dict(std_e=float(np.std(e)), iae_h=float(np.sum(np.abs(e)) * h / hours),
                travel_h=float(np.sum(np.abs(dmv)) / hours), rev_h=float(rev / hours),
                at_lim=float(np.mean((mv <= mv_lo + 1e-6) | (mv >= mv_hi - 1e-6)) * 100),
                harris=harris_index(e, theta / h + 1), osc=osc)


# ================================================================ kvalita dat a hledání úseků
def _robust_sigma(x):
    d = np.diff(np.asarray(x, float))
    d = d[np.isfinite(d)]
    if len(d) < 5:
        return 0.0
    return float(1.4826 * np.median(np.abs(d - np.median(d))) / np.sqrt(2))


def detect_steps(x, h, thr=None):
    """Skokové změny signálu (MV/SP v %). Vrací seznam dict(i, size)."""
    x = np.asarray(x, float)
    n = len(x)
    if n < 5 or not np.all(np.isfinite(x)):
        x = np.nan_to_num(x, nan=np.nanmedian(x) if np.any(np.isfinite(x)) else 0.0)
    d = np.diff(x)
    noise = 1.4826 * np.median(np.abs(d - np.median(d))) if len(d) else 0.0
    thr = thr if thr else max(0.5, 8 * noise)
    idx = np.where(np.abs(d) > thr)[0]
    # souvislé změny (rampy po několik vzorků) sloučit do jedné události
    ev = []
    for i in idx:
        if ev and i - ev[-1][1] <= 2:
            ev[-1][1] = i
        else:
            ev.append([i, i])
    out = []
    for a, b in ev:
        before = x[max(0, a - 2):a + 1].mean()
        after = x[b + 1:min(n, b + 4)].mean() if b + 1 < n else x[-1]
        if abs(after - before) > thr:
            out.append(dict(i=int(a + 1), size=float(after - before)))
    return out


def data_quality(t, pv, mv, sp, h, has_sp, mv_lo, mv_hi, rep_frac=None, model=None):
    """
    Hodnocení vhodnosti úseku pro identifikaci. Úrovně: 0 = vhodná, 1 = s výhradou, 2 = nevhodná.
    Vrací dict(level, checks=[(klíč textu, úroveň, argumenty)], snr, sigma, n_steps).
    """
    checks = []
    st_mv = detect_steps(mv, h)
    sp_moves = has_sp and np.nanmax(sp) - np.nanmin(sp) > 1e-6
    st_sp = detect_steps(sp, h) if sp_moves else []
    n_eff = len(st_mv) + len(st_sp)
    sizes = [s["size"] for s in st_mv + st_sp]
    if n_eff >= 2:
        checks.append(("q_steps_ok", 0, dict(n=n_eff)))
    elif n_eff == 1:
        checks.append(("q_steps_one", 1, {}))
    else:
        checks.append(("q_steps_none", 2, {}))
    if n_eff >= 2 and (all(s > 0 for s in sizes) or all(s < 0 for s in sizes)):
        checks.append(("q_one_dir", 1, {}))
    sigma = _robust_sigma(pv)
    k = max(3, len(pv) // 200)
    pv_s = np.convolve(pv, np.ones(k) / k, mode="valid") if len(pv) > k else np.asarray(pv)
    signal = float(np.percentile(pv_s, 98) - np.percentile(pv_s, 2))
    snr = signal / sigma if sigma > 0 else np.inf
    if snr >= 10:
        checks.append(("q_snr_ok", 0, dict(s=snr)))
    elif snr >= 4:
        checks.append(("q_snr_low", 1, dict(s=snr)))
    else:
        checks.append(("q_snr_bad", 2, dict(s=snr)))
    at_lim = float(np.mean((mv <= mv_lo + 1e-6) | (mv >= mv_hi - 1e-6)) * 100)
    if at_lim >= 20:
        checks.append(("q_lim_bad", 2, dict(p=at_lim)))
    elif at_lim >= 5:
        checks.append(("q_lim_warn", 1, dict(p=at_lim)))
    if rep_frac is not None and rep_frac > 0.5:
        checks.append(("q_compressed", 1, dict(p=rep_frac * 100)))
    if sp_moves and not st_sp:
        checks.append(("q_sp_ramp", 1, {}))
    if model is not None:
        code, p = model
        th = p[-1]
        Tsum = (p[1] if code in ("P1D", "P2D", "I1D") else 0.0) + (p[2] if code == "P2D" else 0.0)
        if h > max(th / 2, (th + Tsum) / 10, 1e-9):
            checks.append(("q_sampling", 1, dict(h=h)))
        ti = sorted(t[s["i"]] for s in st_mv + st_sp)
        if len(ti) >= 2 and not MODELS[code]["integ"]:
            gap = float(np.min(np.diff(ti)))
            if gap < th + 3 * Tsum:
                checks.append(("q_fast_steps", 1, dict(g=gap, s=th + 3 * Tsum)))
        if len(ti) >= 1 and (t[-1] - ti[-1]) < th + 2 * Tsum:
            checks.append(("q_short_tail", 1, dict(s=th + 2 * Tsum)))
    level = max(c_[1] for c_ in checks) if checks else 2
    return dict(level=level, checks=checks, snr=float(snr), sigma=sigma, n_steps=n_eff)


def find_segments(t, mv, sp, h, has_sp, max_gap=None, settle=None):
    """
    Automatické nalezení úseků vhodných pro identifikaci: shluky skoků MV (ruční režim) nebo SP (automat).
    max_gap: skoky dál od sebe tvoří samostatné úseky. settle: doba ustálení procesu (θ + 4T), je-li známa.
    """
    ev = [(t[s["i"]], "mv", s["size"]) for s in detect_steps(mv, h)]
    if has_sp and np.nanmax(sp) - np.nanmin(sp) > 1e-6:
        ev += [(t[s["i"]], "sp", s["size"]) for s in detect_steps(sp, h)]
    if not ev:
        return []
    ev.sort()
    times = np.array([e[0] for e in ev])
    if max_gap is None:
        gaps = np.diff(times)
        base = np.median(gaps) if len(gaps) else (t[-1] - t[0]) / 4
        max_gap = max(3 * base, 3 * (settle or 0), 60 * h)
    groups, cur = [], [ev[0]]
    for e in ev[1:]:
        if e[0] - cur[-1][0] > max_gap:
            groups.append(cur)
            cur = [e]
        else:
            cur.append(e)
    groups.append(cur)
    out = []
    for gi, g in enumerate(groups):
        first, last = g[0][0], g[-1][0]
        prev_end = groups[gi - 1][-1][0] if gi > 0 else t[0]
        next_start = groups[gi + 1][0][0] if gi + 1 < len(groups) else t[-1]
        tail = max(settle or 0, min(max_gap, 0.6 * (next_start - last)) if gi + 1 < len(groups) else max_gap)
        start = max(t[0], first - min(0.3 * max_gap, 0.5 * (first - prev_end)) if gi > 0 else first - min(0.3 * max_gap, first - t[0]))
        end = min(t[-1], last + min(tail, next_start - last - h) if gi + 1 < len(groups) else last + tail)
        out.append(dict(start=float(start), end=float(end), n_mv=sum(1 for e in g if e[1] == "mv"),
                        n_sp=sum(1 for e in g if e[1] == "sp"), up=sum(1 for e in g if e[2] > 0),
                        down=sum(1 for e in g if e[2] < 0)))
    return out


# ================================================================ nelinearita
def local_gains(code, p, pdl, t, pv, mv, dists, h, thr=None):
    """
    Lokální zesílení pro každý skok MV: odchylka dat od globálního modelu se v okně po skoku
    vysvětlí změnou zesílení (odezva na daný skok · f + posun). Vrací seznam dict.
    """
    yhat, _ = predict(code, p, pdl, t, pv, mv, dists, h)
    dm = np.diff(mv)
    if thr is None:
        thr = max(0.25 * np.max(np.abs(dm)), 1e-6) if len(dm) else 1e-6
    idx = np.where(np.abs(dm) > thr)[0] + 1
    # sloučit rychle po sobě jdoucí změny (rampy)
    merged = []
    for i in idx:
        if merged and i - merged[-1] < max(3, int(0.05 * p[-1] / h) + 2):
            continue
        merged.append(i)
    out = []
    min_len = int((p[-1] + (p[1] if code in ("P1D", "P2D", "I1D") else 0)) / h) + 10
    for k, i0 in enumerate(merged):
        i1 = merged[k + 1] if k + 1 < len(merged) else len(t)
        if i1 - i0 < min_len:
            continue
        step = np.zeros(len(t))
        dstep = mv[i0] - mv[i0 - 1]
        step[i0:] = dstep
        s = simulate(code, p, t, step, h)[i0:i1]
        r = (pv - yhat)[i0:i1]
        cols = [s, np.ones_like(s)]  # drift už je v globálním modelu (u integračních by byl kolineární s rampou)
        f = np.linalg.lstsq(np.column_stack(cols), r, rcond=None)[0][0]
        out.append(dict(t=float(t[i0]), mv_from=float(mv[i0 - 1]), mv_to=float(mv[i0]), dmv=float(dstep),
                        gain=float(p[0] * (1 + f)), ratio=float(1 + f)))
    return out


# ================================================================ nejistota modelu
def bootstrap_models(code, t, pv, mv, h, dists, theta_max, base, n=15, seed=0, progress=None):
    """Bootstrap reziduí po blocích: n refitů modelu → rozptyl parametrů."""
    rng = np.random.default_rng(seed)
    yhat, _ = predict(code, base["p"], base["pdl"], t, pv, mv, dists, h)
    r = pv - yhat
    N = len(r)
    B = max(10, N // 15)
    res = []
    for i in range(n):
        starts = rng.integers(0, max(1, N - B), size=N // B + 1)
        rb = np.concatenate([r[s:s + B] for s in starts])[:N]
        try:
            f = fit_model(code, t, yhat + rb, mv, h, dists, theta_max=theta_max, n_grid=10)
            res.append(f)
        except Exception:
            pass
        if progress:
            progress((i + 1) / n)
    return res


# ================================================================ plán skokového testu
def step_plan(code, p, sigma, dpv_max, mv_room=(-np.inf, np.inf), snr=10.0):
    """
    Návrh skokového testu v ručním režimu (vše v %).
    Samoregulační: dublet +Δ / 0 / −Δ / 0, každý krok drží do ustálení (θ + 4ΣT).
    Integrační: pulzy +Δ/−Δ (hladina se vrací), délka pulzu z dynamiky, Δ z povolené odchylky.
    Vrací dict s časem, průběhem MV (odchylka), predikcí PV a parametry.
    """
    th = p[-1]
    Tsum = (p[1] if code in ("P1D", "P2D", "I1D") else 0.0) + (p[2] if code == "P2D" else 0.0)
    integ = MODELS[code]["integ"]
    room = min(abs(mv_room[0]), abs(mv_room[1]))
    if not integ:
        hold = th + 4 * Tsum + max(th, 1.0)
        dmv_max = dpv_max / abs(p[0])
        dmv_min = snr * sigma / abs(p[0])
        dmv = float(min(dmv_max, room, max(dmv_min, 0.5 * dmv_max)))
        seq = [(hold, dmv), (hold, 0.0), (hold, -dmv), (hold, 0.0)]
        dpv = abs(p[0]) * dmv
    else:
        hold = 2 * (th + 3 * Tsum) + 5 * max(th, 1.0)
        dmv_max = dpv_max / (abs(p[0]) * hold)
        dmv = float(min(dmv_max, room))
        seq = [(hold, dmv), (hold, -dmv), (hold / 2, 0.0), (hold, -dmv), (hold, dmv), (hold / 2, 0.0)]
        dpv = abs(p[0]) * dmv * hold
    total = sum(s[0] for s in seq)
    hs = max(total / 3000, 0.05)
    t = np.arange(0, total + hs, hs)
    u = np.zeros_like(t)
    t0 = 0.0
    for dur, val in seq:
        u[(t >= t0) & (t < t0 + dur)] = val
        t0 += dur
    y = simulate(code, p, t, u, hs)
    snr_ach = dpv / sigma if sigma > 0 else np.inf
    return dict(t=t, u=u, y=y, dmv=dmv, hold=hold, total=total, dpv=float(np.max(np.abs(y))), snr=float(snr_ach),
                feasible=bool(snr_ach >= 3), integ=integ)


# ================================================================ kaskáda – efektivní vnější model
def outer_with_inner(code, p, tc_i, th_i):
    """
    Vnější model včetně dynamiky uzavřené vnitřní smyčky ≈ e^(-θi s)/(τci s + 1):
    přidá zpoždění θi a setrvačnost τci (menší z konstant převedena pravidlem polovin na zpoždění).
    Vrací (code, p) rozšířeného modelu.
    """
    th = p[-1] + th_i
    if code == "P0D":
        return "P1D", [p[0], tc_i, th]
    if code == "P1D":
        T1, T2 = max(p[1], tc_i), min(p[1], tc_i)
        return "P2D", [p[0], T1, T2, th]
    if code == "P2D":
        Ts_ = sorted([p[1], p[2], tc_i], reverse=True)
        return "P2D", [p[0], Ts_[0], Ts_[1] + Ts_[2] / 2, th + Ts_[2] / 2]
    if code == "I0D":
        return "I1D", [p[0], tc_i, th]
    T1, T2 = max(p[1], tc_i), min(p[1], tc_i)
    return "I1D", [p[0], T1, th + T2]


# ================================================================ demo data
def demo_data(seed=1):
    """
    Nádrž: hladina = integrační proces s malým zpožděním, MV = odtokový ventil (záporné zesílení),
    měřený přítok jako porucha. Záznam: 1 h ručního režimu se skoky MV.
    Ki = -0.004 %/(%·s), T1 = 15 s, θ = 8 s; přítok: Kd = 0.01 %/(m3/h·s).
    """
    rng = np.random.default_rng(seed)
    h = 1.0
    t = np.arange(0, 3600, h)
    mv = np.full_like(t, 50.0)
    for t0, v in [(300, 55), (600, 50), (1200, 45), (1500, 50), (2400, 57), (2650, 50)]:
        mv[t >= t0] = v
    q = np.full_like(t, 20.0)
    for t0, v in [(900, 24), (1900, 18), (3000, 22)]:
        q[t >= t0] = v
    q = q + rng.normal(0, 0.15, t.size)
    p = [-0.004, 15.0, 8.0]
    pdl = [[0.01, 5.0, 3.0]]
    pv = 50 + model_dev("I1D", p, pdl, t, mv - mv[0], [q - 20.0], h) + rng.normal(0, 0.1, t.size)
    sp = np.full_like(t, 50.0)
    return t, sp, pv, mv, q
