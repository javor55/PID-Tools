"""
APC – gain scheduling (blok GainSched): podle pracovního bodu (PV) z úseků dat a podle regulační odchylky (ER).
Pracovní bod = [x (PV %), u (MV %), fit, parametry modelu …].
"""
import numpy as np

from ... import core
from ...core import default_tc, detect_steps, find_segments, gs_er_table, gs_table, norm_factors, predict, tune
from ...i18n import T


def blocks(t, mv, Ts, settle):
    """Bloky dat mezi velkými přechody MV (změna pracovního bodu); začátek bloku bez přechodového děje."""
    try:
        st_ = detect_steps(mv, Ts)
    except Exception:
        return []
    if len(st_) < 3:
        return []
    sizes = np.abs([q["size"] for q in st_])
    big = sorted(q["i"] for q in st_ if abs(q["size"]) > 2.5 * np.median(sizes))
    edges = [0] + big + [len(t) - 1]
    out = []
    for a, b in zip(edges[:-1], edges[1:]):
        t0 = t[a] + (settle if a > 0 else 0.0)
        t1 = t[b] - Ts
        if t1 - t0 > 2 * settle:
            out.append((float(t0), float(t1)))
    return out


def auto_ranges(t, pv, mv, sp, Ts, has_sp, settle, n=3):
    """
    Návrh úseků pro pracovní body: bloky mezi velkými přechody MV, jinak shluky skoků (find_segments);
    z kandidátů se vyberou ty na nejnižší, prostřední a nejvyšší úrovni PV. Nouzově třetiny dat.
    """
    cands = blocks(t, mv, Ts, settle)
    if len(cands) < n:
        try:
            cands = [(float(g["start"]), float(g["end"])) for g in find_segments(t, mv, sp, Ts, has_sp, settle=settle)]
        except Exception:
            cands = []
    lv = []
    for a, b in cands:
        m = (t >= a) & (t <= b)
        if m.sum() > 10 and np.nanmax(mv[m]) - np.nanmin(mv[m]) > 0.2:
            lv.append((float(np.nanmean(pv[m])), (a, b)))
    lv.sort()
    if len(lv) >= n:
        pick = [lv[0], lv[len(lv) // 2], lv[-1]] if n == 3 else [lv[0], lv[-1]]
        return [r for _, r in pick]
    edges = np.linspace(t[0], t[-1], n + 1)
    return [(float(a), float(b)) for a, b in zip(edges[:-1], edges[1:])]


def key(code, ranges, norm):
    """Klíč identifikovaných bodů: model, úseky a rozsahy (pv_lo, pv_hi, mv_lo, mv_hi)."""
    return [code] + [round(x, 1) for r in ranges for x in r] + list(norm)


def rescale(old_key, new_key, pts):
    """Body přepočtené na nové rozsahy NormPV / NormMV, liší-li se klíč jen jimi; jinak None."""
    if not (isinstance(old_key, list) and len(old_key) == len(new_key) and old_key[:-4] == new_key[:-4]
            and old_key[-4:] != new_key[-4:]):
        return None
    o, n_ = old_key[-4:], new_key[-4:]
    fK = norm_factors(o, n_)[0]

    def conv(v, lo_o, hi_o, lo_n, hi_n):
        return ((lo_o + v * (hi_o - lo_o) / 100) - lo_n) / (hi_n - lo_n) * 100
    return [[conv(q[0], o[0], o[1], n_[0], n_[1]), conv(q[1], o[2], o[3], n_[2], n_[3]), q[2], q[3] * fK] + list(q[4:])
            for q in pts or []]


def fit_points(code, ranges, t, pv, mv, Ts, fit_model=core.fit_model):
    """Identifikace modelu v každém úseku → (body, None), nebo (None, chybová hláška)."""
    pts = []
    for i, (a, b) in enumerate(ranges):
        m = (t >= a) & (t <= b)
        tt, pv_, mv_ = t[m] - t[m][0], pv[m], mv[m]
        if m.sum() < 20 or np.nanmax(mv_) - np.nanmin(mv_) < 0.2:
            return None, T("gs_err_steps", i=i + 1)
        k = int(np.ceil(len(tt) / 2500))
        try:
            r = fit_model(code, tt[::k], pv_[::k], mv_[::k], Ts * k)
            fit = float(predict(code, r["p"], [], tt, pv_, mv_, [], Ts)[1])
        except Exception as ex:
            return None, f"{T('gs_point', i=i + 1)}: {T(str(ex))}"
        pts.append([float(np.nanmean(pv_)), float(np.nanmean(mv_)), fit] + [float(x) for x in r["p"]])
    return pts, None


def points(pts):
    """Body jako slovníky {x, u, fit, p}."""
    return [dict(x=q[0], u=q[1], fit=q[2], p=list(q[3:])) for q in pts or []]


def tune_point(code, p, method, ctype, samp, diffgain, tc_factor=1.0, ms=1.6, opt_migo=None):
    """Ladění jednoho bodu (stejná agresivita ve všech bodech): SIMC s násobkem τc, AMIGO nebo MIGO s limitem Ms."""
    if method == "AMIGO":
        return tune(code, p, "AMIGO", None, ctype, samp)
    r0 = tune(code, p, "SIMC", tc_factor * default_tc(code, p, samp, "SIMC", ctype, diffgain), ctype, samp)
    if method == "SIMC":
        return r0
    starts = ((r0["Kc"], r0["Ti"], r0["Td"]),)
    if opt_migo is not None:
        return opt_migo(code, tuple(p), ctype, samp, diffgain, ms, None, starts)
    return core.optimize_migo(code, list(p), ctype, samp, diffgain, ms, None, starts)


def table(pts, ep, u_pv="PV"):
    """
    Ladění bodů → tabulka pro blok GainSched [(vstup, hodnoty 1–3, jednotka)] a příznak doplnění třetího bodu.
    pts: body s klíči gain, ti, td; ep: převod PV % → jednotky.
    """
    rows, filled = gs_table(pts)
    tab = [("X1 … X3", [float(ep(q["x"])) for q in rows], u_pv),
           ("Gain1 … Gain3", [q["gain"] for q in rows], "–"),
           ("TI1 … TI3", [q["ti"] for q in rows], "s"),
           ("TD1 … TD3", [q["td"] for q in rows], "s")]
    return tab, filled


def er_table(E, k, ctrl, u_pv="PV"):
    """Tabulka pro GainSched podle regulační odchylky: od |ER| ≥ E [PV] platí zesílení k·Gain."""
    rows = gs_er_table(E, k, ctrl["Gain"], ctrl["TI"], ctrl.get("TD", 0.0))
    return [("X1 … X3 (ER)", [q["x"] for q in rows], u_pv), ("Gain1 … Gain3", [q["gain"] for q in rows], "–"),
            ("TI1 … TI3", [q["ti"] for q in rows], "s"), ("TD1 … TD3", [q["td"] for q in rows], "s")]


def k_max(code, p, ctrl, ms_lim=2.0, robustness=core.robustness):
    """Největší násobek zesílení k (krok 0,25), při kterém je smyčka stabilní a Ms ≤ ms_lim (0 = nesplní ani sada sama)."""
    best = 0.0
    for k in np.arange(1.0, 6.01, 0.25):
        rb = robustness(code, p, dict(ctrl, Gain=k * ctrl["Gain"]))
        if not (rb["stable"] and np.isfinite(rb["Ms"]) and rb["Ms"] <= ms_lim):
            break
        best = float(k)
    return best
