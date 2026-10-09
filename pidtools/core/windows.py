"""
Identifikace z úseků podle vstupů.

Každý vstup (MV a každá měřená porucha DV) má vlastní úseky, kde se zřetelně měnil; model se fituje společně přes
sjednocení všech úseků:  PV = G_MV · MV + Σ G_DVj · DVj.
  - v každém úseku se simuluje odchylka od jeho začátku (vstupy i PV), takže úseky nemusí navazovat,
  - každý úsek má vlastní počáteční stav PV (posun) a u integračních přenosů i vlastní drift,
    které se v každém kroku dopočtou lineárně (nezvyšují počet hledaných parametrů),
  - vzorky mimo platnou masku (PV / MV / DV mimo meze, saturace …) se do ceny nepočítají, simulace přes ně běží dál.
Typ přenosu poruchy: 0 = podle procesu (integrační, je-li integrační model MV), 1 = samoregulační, 2 = integrační;
uloží se jako 4. prvek parametrů poruchy [Kd, Tp, θd, typ] (simulate_dist ho respektuje).
"""
import numpy as np

from .identification import least_squares
from .models import MODELS, model_dev, n_free


def merge_windows(wins, n):
    """Indexové úseky [(i0, i1)] seřazené, oříznuté na 0…n a sloučené, pokud se překrývají nebo dotýkají."""
    out = []
    for a, b in sorted((max(0, int(a)), min(n, int(b))) for a, b in wins):
        if b - a < 3:
            continue
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


class _Win:
    """Jeden úsek: časy od začátku, odchylky vstupů a PV, platné vzorky a projekce odstraňující posun (a drift)."""

    def __init__(self, t, pv, mv, dists, valid, i0, i1, k, integ):
        sl = slice(i0, i1, k)
        self.t = t[sl] - t[i0]
        self.y = pv[sl] - pv[i0]
        self.du = mv[sl] - mv[i0]
        self.dD = [d[sl] - d[i0] for d in dists]
        self.v = valid[sl] if valid is not None else np.ones(len(self.t), bool)
        A = np.ones((len(self.t), 1))
        if integ:
            A = np.column_stack([A, self.t])
        Av = A[self.v]
        self.A, self.pinv = A, (np.linalg.pinv(Av) if len(Av) >= A.shape[1] else None)

    def proj(self, r):
        """Rezidua po odečtení nejlepšího posunu (a driftu) – jen platné vzorky."""
        rv = r[self.v]
        if self.pinv is None:
            return rv
        return rv - self.A[self.v] @ (self.pinv @ rv)


def _windows(t, pv, mv, dists, valid, wins, k, integ):
    return [_Win(t, pv, mv, dists, valid, a, b, k, integ) for a, b in wins]


def _pdl_of(z, nf, nd, dkind):
    return [[float(v) for v in z[nf + 1 + 3 * j: nf + 4 + 3 * j]] + ([int(dkind[j])] if dkind[j] else [])
            for j in range(nd)]


def fit_windows(code, t, pv, mv, h, dists=(), wins=(), valid=None, theta_max=None, fixed=None, sign=0, dsign=None,
                dkind=None, n_grid=12):
    """
    Společný fit modelu MV → PV a modelů poruch přes úseky `wins` [(i0, i1)] (indexy do t).
    valid ..... bool pole délky t – vzorky, které se počítají do ceny (None = všechny)
    fixed ..... {"p0": …, "p{nf}" = θ, "d{j}_{i}": …} zafixované parametry
    sign ...... znaménko zesílení MV (0 auto, ±1 vynucené); dsign – totéž pro každou poruchu
    dkind ..... typ přenosu každé poruchy (0 podle procesu, 1 samoregulační, 2 integrační)
    Vrací dict(code, p, pdl, fit, fits (každý úsek), wins, level="none", Th=None, stic=0, fixed).
    """
    t, pv, mv = np.asarray(t, float), np.asarray(pv, float), np.asarray(mv, float)
    dists = [np.asarray(d, float) for d in dists]
    nd = len(dists)
    dsign = list(dsign or [0] * nd)
    dkind = list(dkind or [0] * nd)
    fixed = dict(fixed or {})
    wins = merge_windows(wins, len(t))
    if not wins:
        raise ValueError("err_no_windows")
    integ = MODELS[code]["integ"]
    d_integ = [integ if not dk else dk == 2 for dk in dkind]
    nf = n_free(code)
    span = max(t[b - 1] - t[a] for a, b in wins)
    total = sum(t[b - 1] - t[a] for a, b in wins)
    theta_max = max(theta_max if theta_max else 0.4 * span, h)
    tmin, Tmax = 0.2 * h, 20 * total
    any_integ = integ or any(d_integ)
    W = _windows(t, pv, mv, dists, valid, wins, 1, any_integ)
    if all(np.allclose(w.du, 0) for w in W) and all(np.allclose(d, 0) for w in W for d in w.dD):
        raise ValueError("err_mv_const")

    # počáteční zesílení regresí na derivaci (integrační přenos) / odchylce (samoregulační) – úseky pod sebou
    cols, tgt = [], []
    for w in W:
        if integ:      # cíl dPV/dt: MV přímo, integrační porucha přímo, samoregulační porucha svou derivací
            g = np.gradient(w.y, h)
            dc = [d if di else np.gradient(d, h) for d, di in zip(w.dD, d_integ)]
        else:          # cíl PV: MV přímo, samoregulační porucha přímo, integrační porucha svým integrálem
            g = w.y
            dc = [np.cumsum(d) * h if di else d for d, di in zip(w.dD, d_integ)]
        cols.append(np.column_stack([w.du] + dc)[w.v])
        tgt.append(g[w.v])
    A, b = np.vstack(cols), np.concatenate(tgt)
    A_c = A - A.mean(0)
    coef = np.linalg.lstsq(A_c, b - b.mean(), rcond=None)[0] if len(b) > A.shape[1] else np.zeros(A.shape[1])
    g0, kd0 = float(coef[0]), [float(c) for c in coef[1:]]
    if sign and np.sign(g0) != sign:
        g0 = -g0 if g0 != 0 else sign * 1e-3
    if abs(g0) < 1e-12:
        g0 = 1e-3 * (sign or 1)
    for j, s in enumerate(dsign):
        if s and np.sign(kd0[j]) != s:
            kd0[j] = -kd0[j] if kd0[j] != 0 else s * 1e-3
    T0 = span / 10

    names = [f"p{i}" for i in range(nf)] + [f"p{nf}"] + [f"d{j}_{i}" for j in range(nd) for i in range(3)]
    th_idx = nf
    lb = [0.0 if sign > 0 else -np.inf] + [tmin] * (nf - 1) + [0.0]
    ub = [0.0 if sign < 0 else np.inf] + [Tmax] * (nf - 1) + [theta_max]
    for j in range(nd):
        lb += [0.0 if dsign[j] > 0 else -np.inf, tmin, 0.0]
        ub += [0.0 if dsign[j] < 0 else np.inf, Tmax, theta_max]
    lb, ub = np.array(lb, float), np.array(ub, float)
    starts = {1: [[g0]], 2: [[g0, T0], [g0, T0 / 5]], 3: [[g0, T0, T0 / 3], [g0, T0 / 3, T0 / 10]]}[nf]
    dist0 = []
    for k in kd0:
        dist0 += [k, T0 / 3, min(h, theta_max / 2)]
    fixed_mask = np.array([n in fixed for n in names])
    zfix = np.array([float(fixed.get(n, 0.0)) for n in names])
    free_nt = np.where(~fixed_mask & (np.arange(len(names)) != th_idx))[0]
    th_free = not fixed_mask[th_idx]

    def make_resid(Ws, hk):
        def resid(z):
            p = [float(v) for v in z[:nf + 1]]
            pdl = _pdl_of(z, nf, nd, dkind)
            return np.concatenate([w.proj(w.y - model_dev(code, p, pdl, w.t, w.du, w.dD, hk)) for w in Ws])
        return resid

    n_all = sum(b - a for a, b in wins)
    k_g = max(1, int(np.ceil(n_all / 600)))
    resid = make_resid(W, h)
    resid_g = make_resid(_windows(t, pv, mv, dists, valid, wins, k_g, any_integ), h * k_g) if k_g > 1 else resid

    def make_z(x, th):
        z = zfix.copy()
        z[free_nt] = x
        if th_free:
            z[th_idx] = th
        return z

    cands = []
    thetas = np.linspace(0, theta_max, max(3, n_grid)) if th_free else [zfix[th_idx]]
    for th in thetas:
        for s0 in starts:
            z0 = np.where(fixed_mask, zfix, np.r_[s0, 0.0, dist0])
            x0 = np.clip(z0[free_nt], lb[free_nt], ub[free_nt])
            if not len(x0):
                cands.append((0.5 * np.sum(resid_g(make_z(x0, th)) ** 2), x0, th))
                continue
            try:
                r = least_squares(lambda x: resid_g(make_z(x, th)), x0, bounds=(lb[free_nt], ub[free_nt]), max_nfev=150)
            except Exception:
                continue
            cands.append((r.cost, r.x, th))
    if not cands:
        raise ValueError("err_fit_failed")

    def refine(x, th):
        best = (0.5 * np.sum(resid(make_z(x, th)) ** 2), x, th)
        if not len(x):
            return best
        try:
            if th_free:
                lb2, ub2 = np.r_[lb[free_nt], 0.0], np.r_[ub[free_nt], theta_max]
                r = least_squares(lambda w: resid(make_z(w[:-1], w[-1])), np.clip(np.r_[x, th], lb2, ub2),
                                  bounds=(lb2, ub2), max_nfev=300)
                cand = (r.cost, r.x[:-1], r.x[-1])
            else:
                r = least_squares(lambda x_: resid(make_z(x_, th)), x, bounds=(lb[free_nt], ub[free_nt]), max_nfev=150)
                cand = (r.cost, r.x, th)
            return cand if cand[0] <= best[0] else best
        except Exception:
            return best

    top, seen = [], set()
    for c in sorted(cands, key=lambda c: c[0]):
        if c[2] not in seen:
            seen.add(c[2])
            top.append(c)
        if len(top) == 3:
            break
    _, xb, thb = min((refine(x, th) for _, x, th in top), key=lambda c: c[0])
    z = make_z(xb, thb)
    p = [float(v) for v in z[:nf + 1]]
    pdl = _pdl_of(z, nf, nd, dkind)
    if code == "P2D" and p[2] > p[1] and "p1" not in fixed and "p2" not in fixed:
        p[1], p[2] = p[2], p[1]
    fits = window_fits(code, p, pdl, W, h)
    num = sum(np.sum(w.proj(w.y - model_dev(code, p, pdl, w.t, w.du, w.dD, h)) ** 2) for w in W)
    den = sum(np.sum((w.y[w.v] - w.y[w.v].mean()) ** 2) for w in W if w.v.any())
    fit = float(100.0 * (1 - np.sqrt(num / den))) if den > 0 else float("nan")
    return dict(code=code, p=p, pdl=pdl, fit=fit, fits=fits, wins=[list(map(int, w)) for w in wins], level="none",
                Th=None, stic=0.0, fixed=sorted(fixed))


def window_fits(code, p, pdl, W, h):
    """Shoda modelu v každém úseku [%] (po odečtení posunu / driftu úseku, jen platné vzorky)."""
    out = []
    for w in W:
        r = w.proj(w.y - model_dev(code, p, pdl, w.t, w.du, w.dD, h))
        yv = w.y[w.v]
        den = np.linalg.norm(yv - yv.mean()) if len(yv) else 0.0
        out.append(float(100.0 * (1 - np.linalg.norm(r) / den)) if den > 0 else float("nan"))
    return out


def predict_windows(code, p, pdl, t, pv, mv, h, dists, wins, valid=None):
    """
    Predikce PV v úsecích (s nejlepším posunem / driftem úseku) → (pole NaN mimo úseky, shody úseků [%],
    celková shoda přes všechny úseky [%]).
    """
    t, pv, mv = np.asarray(t, float), np.asarray(pv, float), np.asarray(mv, float)
    dists = [np.asarray(d, float) for d in dists]
    integ = MODELS[code]["integ"] or any(len(d) > 3 and d[3] == 2 for d in pdl)
    out = np.full(len(t), np.nan)
    fits, num, den_all = [], 0.0, 0.0
    for a, b in merge_windows(wins, len(t)):
        w = _Win(t, pv, mv, dists, valid, a, b, 1, integ)
        dev = model_dev(code, p, pdl, w.t, w.du, w.dD, h)
        r = w.y - dev
        c = w.pinv @ r[w.v] if w.pinv is not None else np.zeros(w.A.shape[1])
        out[a:b] = pv[a] + dev + w.A @ c
        yv = w.y[w.v]
        den = np.linalg.norm(yv - yv.mean()) if len(yv) else 0.0
        rr = w.proj(r)
        fits.append(float(100.0 * (1 - np.linalg.norm(rr) / den)) if den > 0 else float("nan"))
        num, den_all = num + float(np.sum(rr ** 2)), den_all + den ** 2
    overall = float(100.0 * (1 - np.sqrt(num / den_all))) if den_all > 0 else float("nan")
    return out, fits, overall


def cross_validate(code, t, pv, mv, h, dists, wins, valid=None, **kw):
    """Křížové ověření: pro každý úsek fit na ostatních úsecích a shoda na něm [%] (jen při ≥ 2 úsecích)."""
    wins = merge_windows(wins, len(t))
    if len(wins) < 2:
        return []
    out = []
    for i, w in enumerate(wins):
        rest = wins[:i] + wins[i + 1:]
        try:
            r = fit_windows(code, t, pv, mv, h, dists, rest, valid, n_grid=6, **kw)
            out.append(predict_windows(code, r["p"], r["pdl"], t, pv, mv, h, dists, [w], valid)[1][0])
        except Exception:
            out.append(float("nan"))
    return out
