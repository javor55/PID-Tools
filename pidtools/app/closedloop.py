"""
Identifikace z dat se smyčkou v AUTO (uzavřená smyčka) – nepřímá metoda se známým regulátorem.

Při běžném provozu regulátor sám reaguje na šum a poruchy, takže MV a PV nejsou nezávislé a fit MV → PV
(otevřená smyčka) dává zkreslený model – typicky menší zesílení a kratší zpoždění. Nepřímá metoda proto hledá
model procesu tak, aby simulace celé smyčky – blok PIDConL s parametry, se kterými smyčka v záznamu běžela (Set 1),
naměřená žádaná hodnota a měřené poruchy – reprodukovala naměřené PV i MV. Šum regulátorem neprochází do
odhadu, potřebné buzení dodávají změny SP (nebo měřené poruchy).

Vše v % rozsahů (NormPV / NormMV); časy v s od začátku úseku.
"""
import numpy as np
from ..core.identification import least_squares

from .. import core
from ..core import MODELS

BAD = 1e3        # reziduum nestabilní simulace


def excitation(sp, pv, mv):
    """
    Posouzení dat pro identifikaci v uzavřené smyčce: dict(sp_moves, sp_span, mv_span, ok).
    Potřebné buzení = změny SP (aspoň dvě výrazné), jinak je model určený jen šumem.
    """
    sp = np.asarray(sp, float)
    span = float(np.nanmax(sp) - np.nanmin(sp)) if len(sp) else 0.0
    d = np.abs(np.diff(sp)) if len(sp) > 1 else np.zeros(0)
    thr = max(0.1 * span, 1e-6)
    moves = int(np.sum(d > thr))
    mv_span = float(np.nanmax(mv) - np.nanmin(mv)) if len(mv) else 0.0
    return dict(sp_moves=moves, sp_span=span, mv_span=mv_span, ok=bool(span > 0.5 and moves >= 1 and mv_span > 0.5))


def _grid(ts, sp, pv, mv, d, h):
    n = int(ts[-1] / h) + 1
    tg = np.arange(n) * h
    return (tg, np.interp(tg, ts, sp), np.interp(tg, ts, pv), np.interp(tg, ts, mv),
            [np.interp(tg, ts, np.asarray(x, float) - float(x[0])) for x in d])


def simulate(code, p, pdl, ts, sp, pv, mv, d, Ts, ctrl, sim=core.pidconl_sim):
    """Simulace smyčky na záznamu (SP a poruchy z dat): (t, PV, MV), nebo None při nestabilitě."""
    h = min(Ts, ctrl["SampleTime"])
    tg, spg, _, _, dg = _grid(ts, sp, pv, mv, d, h)
    try:
        tt, _, P, M = sim(code, list(p), pdl, h, spg, float(pv[0]), float(mv[0]), ctrl, dg)
    except Exception:
        return None
    if not (np.all(np.isfinite(P)) and np.abs(P).max() < 1e5):
        return None
    return tt, P, M


def _nfit(y, yhat):
    return float(100.0 * (1 - np.linalg.norm(y - yhat) / max(np.linalg.norm(y - np.mean(y)), 1e-12)))


def identify(code, p0, pdl, ts, sp, pv, mv, d, Ts, ctrl, theta_max=None, w_mv=0.5, n_theta=7, max_pts=1500,
             sim=core.pidconl_sim, progress=None):
    """
    Model procesu z dat v uzavřené smyčce. p0 = počáteční odhad (např. z identifikace v otevřené smyčce),
    pdl = modely měřených poruch (ponechají se), ctrl = regulátor ze záznamu (blok PIDConL + Set 1).
    w_mv = váha shody MV vůči PV. Vrací dict(code, p, pdl, fit_pv, fit_mv, cost, method="cl").
    """
    ctrl = {k: v for k, v in ctrl.items() if k not in ("FF", "FF_LL")}
    ts, sp, pv, mv = (np.asarray(x, float) for x in (ts, sp, pv, mv))
    h = min(Ts, ctrl["SampleTime"])
    tg, spg, pvg, mvg, dg = _grid(ts, sp, pv, mv, d, h)
    idx = np.unique(np.linspace(0, len(tg) - 1, min(max_pts, len(tg))).astype(int))
    s_pv, s_mv = max(np.std(pvg), 1e-6), max(np.std(mvg), 1e-6)
    nf = len(MODELS[code]["params"]) - 1                 # parametry bez zpoždění
    sgn = 1.0 if p0[0] >= 0 else -1.0
    span = float(ts[-1])
    theta_max = float(theta_max) if theta_max else 0.4 * span
    calls = [0]

    def unpack(x, th):
        return [sgn * float(np.exp(x[0]))] + [float(np.exp(v)) for v in x[1:nf]] + [float(th)]

    def resid(x, th):
        calls[0] += 1
        if progress and calls[0] % 25 == 0:
            progress(calls[0])
        try:
            _, _, P, M = sim(code, unpack(x, th), pdl, h, spg, float(pvg[0]), float(mvg[0]), ctrl, dg)
        except Exception:
            return np.full(2 * len(idx), BAD)
        if not (np.all(np.isfinite(P)) and np.abs(P).max() < 1e5):
            return np.full(2 * len(idx), BAD)
        return np.r_[(P[idx] - pvg[idx]) / s_pv, w_mv * (M[idx] - mvg[idx]) / s_mv]

    x0 = np.log(np.maximum(np.abs(np.r_[p0[0], p0[1:nf]]), 1e-6))
    lb, ub = x0 - np.log(50.0), x0 + np.log(50.0)
    th0 = float(np.clip(p0[-1], 0.0, theta_max))
    ths = np.unique(np.clip(np.r_[th0 * np.array([0.5, 0.75, 1.0, 1.3, 1.7]), h, th0 + 4 * h], 0.0, theta_max))
    ths = ths[np.linspace(0, len(ths) - 1, min(n_theta, len(ths))).astype(int)]
    cache = {}

    def fit_th(th, x_start, nfev=30):
        """Nejlepší ostatní parametry pro dané zpoždění (zpoždění je v simulaci po krocích h → hledá se zvlášť)."""
        key = round(float(th) / h)
        if key not in cache:
            try:
                r = least_squares(lambda x: resid(x, th), x_start, bounds=(lb, ub), max_nfev=nfev, diff_step=0.03)
                cache[key] = (float(r.cost), r.x, float(th))
            except Exception:
                cache[key] = (np.inf, x_start, float(th))
        return cache[key]

    best = min((fit_th(th, x0) for th in ths), key=lambda c_: c_[0])
    if not np.isfinite(best[0]):
        raise ValueError("err_fit_failed")
    step = max(h, round(0.02 * max(best[2], h) / h) * h)
    for _ in range(40):                                    # lokální hledání zpoždění po krocích
        cands = [fit_th(min(max(best[2] + k * step, 0.0), theta_max), best[1], 20) for k in (-1, 1)]
        c = min(cands, key=lambda c_: c_[0])
        if c[0] < best[0] - 1e-12:
            best = c
        elif step > h:
            step = max(h, round(step / 2 / h) * h)
        else:
            break
    try:                                                   # závěrečné doladění ostatních parametrů
        r = least_squares(lambda x: resid(x, best[2]), best[1], bounds=(lb, ub), max_nfev=60, diff_step=0.01)
        if r.cost < best[0]:
            best = (float(r.cost), r.x, best[2])
    except Exception:
        pass
    cost, xb, thb = best
    p = unpack(xb, thb)
    if code == "P2D" and p[2] > p[1]:
        p[1], p[2] = p[2], p[1]
    out = dict(code=code, p=p, pdl=[list(x) for x in pdl], cost=float(cost), method="cl", fit_pv=None, fit_mv=None,
               nfev=calls[0])
    s = simulate(code, p, pdl, ts, sp, pv, mv, d, Ts, ctrl, sim)
    if s is not None:
        tt, P, M = s
        out.update(fit_pv=_nfit(pv, np.interp(ts, tt, P)), fit_mv=_nfit(mv, np.interp(ts, tt, M)))
    return out


def as_result(r_open, r_cl, predict_fit):
    """
    Výsledek identifikace (stejný tvar jako core.identify) s modelem z uzavřené smyčky. r_open = výsledek otevřené
    smyčky (úroveň poruch, stikce …), predict_fit = shoda nového modelu na datech (pro tabulku modelů).
    """
    r = dict(r_open)
    r.update(p=list(r_cl["p"]), pdl=[list(x) for x in r_cl["pdl"]], fit=float(predict_fit), method="cl",
             fit_cl_pv=r_cl["fit_pv"], fit_cl_mv=r_cl["fit_mv"], p_open=list(r_open["p"]))
    return r
