"""Identifikace modelů z dat, hodnocení modelu a nejistota parametrů."""
import numpy as np
from scipy.optimize import least_squares

from .models import (MODELS, n_free, model_dev, predict, stiction_valve,
                     high_pass, spline_projector)
from .util import acf as _acf

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
        y, du, dD = high_pass(y, Th, h), high_pass(du, Th, h), [high_pass(d, Th, h) for d in dD]
    elif level == "high":
        proj = spline_projector(t, Th)

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
