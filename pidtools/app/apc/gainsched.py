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


def simulate_pv(code, pts, base_ctrl, set2, samp, sim=None):
    """
    Nelineární proces z pracovních bodů: SP postupně do všech bodů a zpět, v každém úseku porucha na vstupu.
    Jedna sada (set2) vs. gain scheduling (pts s laděním gain, ti, td). Vrací dict(t, sp, seq, k_seg,
    fixed = (čas, výsledek), sched = (čas, výsledek), iae = [(z, na, IAE jedna sada, IAE scheduling)] v %·s).
    """
    from ...core import gs_sim, iae
    from .common import clean, grid, tchar
    sim = sim or gs_sim
    xs = sorted(q["x"] for q in pts)
    seq = xs + [xs[0]]
    tp = max(12 * tchar((code, q["p"])) for q in pts) + 50 * samp
    h, nn, t = grid(tp * len(seq), samp)
    k_seg = np.minimum((t // tp).astype(int), len(seq) - 1)
    sp = np.array(seq)[k_seg]
    d = np.where((t % tp) >= 0.55 * tp, 5.0, 0.0)
    rows3 = gs_table(pts)[0]
    sched = {k: [q[kq] for q in rows3] for k, kq in (("X", "x"), ("gain", "gain"), ("ti", "ti"), ("td", "td"))}
    plant = [dict(x=q["x"], u=q["u"], p=q["p"]) for q in pts]
    tf, of = sim(code, plant, clean(set2), None, h, sp, d)
    ts_, os_ = sim(code, plant, dict(clean(base_ctrl), Gain=sched["gain"][0], TI=sched["ti"][0], TD=sched["td"][0]),
                   sched, h, sp, d)
    out = []
    for i, x in enumerate(seq[1:], start=1):
        m = k_seg == i
        out.append((seq[i - 1], x, iae(t[m], sp[m], of["PV"][m]), iae(t[m], sp[m], os_["PV"][m])))
    return dict(t=t, sp=sp, seq=seq, k_seg=k_seg, fixed=(tf, of), sched=(ts_, os_), iae=out)


def simulate_er(code, p, set2, E_pct, k, step_pct, d_mv, samp, sim=None, best_cz=None):
    """
    Gain scheduling podle regulační odchylky: skok SP (step_pct %) a pak porucha na vstupu (d_mv %). Jedna sada vs.
    scheduling podle ER vs. nejlepší řídicí pásmo ConZone. Vrací dict(t, sp, tp, fixed, sched, cz, scan, zone)
    – průběhy jako (čas, výsledek), zone = výsledek s ConZone nebo None.
    """
    from ...core import best_conzone, gs_sim
    from .common import grid, tchar
    sim, best_cz = sim or gs_sim, best_cz or best_conzone
    tp = 15 * tchar((code, p)) + 50 * samp
    h, nn, t = grid(2 * tp, samp)
    sp = np.where(t >= 0.05 * tp, 50.0 + step_pct, 50.0)
    d = np.where(t >= tp, float(d_mv), 0.0)
    plant = [dict(x=50.0, u=50.0, p=p)]
    rows = gs_er_table(E_pct, k, set2["Gain"], set2["TI"], set2.get("TD", 0.0))
    sched = {kk: [q[kq] for q in rows] for kk, kq in (("X", "x"), ("gain", "gain"), ("ti", "ti"), ("td", "td"))}
    fixed = sim(code, plant, set2, None, h, sp, d)
    sch = sim(code, plant, set2, sched, h, sp, d, "er")
    widths = tuple(float(f) * abs(step_pct) for f in (0.15, 0.3, 0.45, 0.6, 0.75, 0.9))
    cz, scan = best_cz(code, plant, set2, h, sp, d, widths)
    zone = sim(code, plant, dict(set2, ConZone=cz), None, h, sp, d)[1] if cz else None
    return dict(t=t, sp=sp, tp=tp, fixed=fixed, sched=sch, cz=cz, scan=scan, zone=zone)


def er_kpis(t, sp, tp, o, ctrl, pv_range):
    """Ukazatele simulace podle ER: IAE skoku SP a poruchy, max. odchylka po poruše [PV], podíl času na limitu MV,
    ustálení."""
    from ...core import iae, settled
    a, b = t < tp, t >= tp
    f = pv_range / 100
    sat = np.mean((o["MV"] <= ctrl.get("MV_Lo", 0) + 1e-6) | (o["MV"] >= ctrl.get("MV_Hi", 100) - 1e-6))
    return dict(iae_sp=float(iae(t[a], sp[a], o["PV"][a]) * f), iae_d=float(iae(t[b], sp[b], o["PV"][b]) * f),
                maxdev=float(np.max(np.abs(sp[b] - o["PV"][b])) * f), sat=float(sat), settled=bool(settled(t, sp, o["PV"])))
