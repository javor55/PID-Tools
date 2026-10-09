"""
Kvalita dat smyčky (záložka Data): automatické kontroly záznamu před identifikací – vzorkování, mezery, komprese
historianu, rozlišení, šum, PV mimo rozsah měření, MV na mezi, buzení MV a poruch, nezávislost MV a poruch.

Každá kontrola vrací stav ("ok" = v pořádku, "warn" = aplikace s tím počítá / pozor, "info" = informace o záznamu),
klíč textu (dq_<id>_name / _why) a výsledek (dq_<id>_<varianta> s argumenty). Sdílené webem i desktopem.
Masky (na mřížce po převzorkování) označují vzorky s upozorněním – zvýrazní se v náhledu dat.
"""
from dataclasses import dataclass, field

import numpy as np

from ..core.diagnostics import detect_steps
from .timefmt import dur


@dataclass
class Check:
    id: str                       # klíč kontroly → texty dq_<id>_name, dq_<id>_why
    status: str                   # "ok" | "warn" | "info"
    res: str                      # klíč textu výsledku
    args: dict = field(default_factory=dict)
    mask: object = None           # bool pole na mřížce (vzorky s upozorněním) nebo None


def _g(v):
    """Číslo pro text: 4 platné číslice, desetinná čárka doplní překlad (zde jen formát)."""
    return f"{v:.4g}"


def _runs(mask):
    """Délky souvislých úseků True v masce."""
    m = np.asarray(mask, bool)
    if not m.any():
        return np.array([], int)
    d = np.diff(np.r_[0, m.astype(int), 0])
    return np.where(d == -1)[0] - np.where(d == 1)[0]


def _resolution(x):
    """Nejmenší nenulová změna signálu (rozlišení / kvantizace)."""
    x = np.asarray(x, float)
    d = np.abs(np.diff(x[np.isfinite(x)]))
    d = d[d > 1e-12]
    return float(d.min()) if len(d) else np.nan


def _events(x, Ts, frac=0.3, win=60.0):
    """Počet výrazných změn signálu: posun o víc než frac rozsahu během okna win [s] (souvislé změny jako jedna)."""
    x = np.asarray(x, float)
    ok = np.isfinite(x)
    if ok.sum() < 5:
        return 0
    x = np.interp(np.arange(len(x)), np.where(ok)[0], x[ok])
    rng = float(np.ptp(x))
    if rng <= 0:
        return 0
    k = max(1, int(round(win / max(Ts, 1e-9))))
    if len(x) <= k:
        return 0
    big = np.abs(x[k:] - x[:-k]) > frac * rng
    return len(_runs(big))


def check_all(t_raw, pv_raw, mv_raw, Ts, pv, mv, dists=(), dist_names=(), pv_rng=(0.0, 100.0), mv_rng=(0.0, 100.0),
              mv_lim=None):
    """
    t_raw, pv_raw, mv_raw – původní data (čas v s, před převzorkováním); pv, mv, dists – na mřížce s periodou Ts
    (inženýrské jednotky); pv_rng / mv_rng – rozsahy měření (NormPV / NormMV); mv_lim – meze MV regulátoru (inž.).
    Vrací seznam Check.
    """
    out = []
    t_raw = np.asarray(t_raw, float)
    pv, mv = np.asarray(pv, float), np.asarray(mv, float)
    pv_span = max(pv_rng[1] - pv_rng[0], 1e-12)
    mv_span = max(mv_rng[1] - mv_rng[0], 1e-12)

    # 1 · vzorkování původních dat
    tt = np.sort(t_raw[np.isfinite(t_raw)])
    dt = np.diff(tt)
    dt = dt[dt > 0]
    med = float(np.median(dt)) if len(dt) else float(Ts)
    irregular = len(dt) > 10 and np.std(dt) / med > 1.0
    out.append(Check("samp", "warn" if irregular else "ok", "dq_samp_irr" if irregular else "dq_samp_ok",
                     dict(ts=_g(med), n=f"{len(tt):,}".replace(",", " "))))

    # 2 · mezery a chybějící hodnoty
    gaps = dt[dt > 5 * med] if len(dt) else np.array([])
    nan = int(np.sum(~np.isfinite(np.asarray(pv_raw, float)))) + int(np.sum(~np.isfinite(np.asarray(mv_raw, float))))
    if len(gaps) or nan:
        out.append(Check("gaps", "warn", "dq_gaps_found", dict(n=len(gaps), d=dur(float(gaps.max())) if len(gaps) else "–",
                                                              nan=nan)))
    else:
        out.append(Check("gaps", "ok", "dq_gaps_none"))

    # 3 · komprese historianu (PV se mění jen v malé části vzorků)
    pr = np.asarray(pv_raw, float)
    pr = pr[np.isfinite(pr)]
    chg = float(np.mean(np.diff(pr) != 0)) * 100 if len(pr) > 20 else 100.0
    out.append(Check("comp", "warn" if chg < 50 else "ok", "dq_comp_yes" if chg < 50 else "dq_comp_no",
                     dict(p=f"{chg:.0f}")))

    # 4 · rozlišení (kvantizace)
    rp, rm = _resolution(pv_raw), _resolution(mv_raw)
    coarse = np.isfinite(rp) and rp > 0.01 * pv_span
    parts = dict(pv=_g(rp) if np.isfinite(rp) else "–", mv=_g(rm) if np.isfinite(rm) else "–")
    out.append(Check("res", "warn" if coarse else "ok", "dq_res_coarse" if coarse else "dq_res_ok", parts))

    # 5 · šum PV a špičky (na mřížce)
    d = np.diff(pv[np.isfinite(pv)])
    sig = float(1.4826 * np.median(np.abs(d - np.median(d)))) if len(d) > 5 else 0.0
    # špička = skok PV větší než 10 σ šumu a zároveň než 2 % rozsahu
    spikes = int(np.sum((np.abs(d) > 10 * sig) & (np.abs(d) > 0.02 * pv_span))) if len(d) else 0
    out.append(Check("noise", "warn" if spikes else "ok", "dq_noise_spikes" if spikes else "dq_noise_ok",
                     dict(s=_g(sig), p=f"{sig / pv_span * 100:.2g}", n=spikes)))

    # 6 · PV mimo rozsah měření
    tol = 1e-9 * pv_span
    m_pv = (pv < pv_rng[0] - tol) | (pv > pv_rng[1] + tol)
    if m_pv.any():
        out.append(Check("pvrng", "warn", "dq_pvrng_out",
                         dict(d=dur(float(m_pv.sum() * Ts)), lo=_g(float(np.nanmin(pv))), hi=_g(float(np.nanmax(pv)))),
                         mask=m_pv))
    else:
        out.append(Check("pvrng", "ok", "dq_pvrng_ok"))

    # 7 · MV na mezi (meze MV bloku PIDConL, jinak rozsah); dlouho na svém maximu / minimu = možná mez (informace)
    lo_, hi_ = mv_lim if mv_lim is not None else mv_rng
    mtol = 0.002 * mv_span
    m_lim = (mv <= lo_ + mtol) | (mv >= hi_ - mtol)
    if m_lim.any():
        out.append(Check("mvlim", "warn", "dq_mvlim_range", dict(d=dur(float(m_lim.sum() * Ts))), mask=m_lim))
    else:
        plateau = None
        if np.isfinite(mv).any() and np.ptp(mv[np.isfinite(mv)]) > 10 * mtol:
            med = float(np.nanmedian(mv))
            for ext in (np.nanmax(mv), np.nanmin(mv)):
                if abs(ext - med) <= 0.02 * mv_span:        # běžný pracovní bod, ne mez
                    continue
                r = _runs(np.abs(mv - ext) <= mtol)
                if len(r) and r.max() >= max(20, int(30 / max(Ts, 1e-9))):
                    plateau = (ext, float(r.max() * Ts))
                    break
        if plateau:
            out.append(Check("mvlim", "info", "dq_mvlim_plateau", dict(v=_g(plateau[0]), d=dur(plateau[1]))))
        else:
            out.append(Check("mvlim", "ok", "dq_mvlim_ok"))

    # 8 · pohyb MV: skoky (buzení pro identifikaci) a nejdelší klid
    steps = detect_steps(mv, Ts, thr=max(0.002 * mv_span, 1e-9))
    still = _runs(np.r_[np.abs(np.diff(mv)) <= 1e-9 * mv_span, False])
    longest = float(still.max() * Ts) if len(still) else 0.0
    out.append(Check("mvexc", "info" if steps else "warn", "dq_mvexc_steps" if steps else "dq_mvexc_none",
                     dict(n=len(steps), d=dur(longest))))

    # 9 · buzení měřených poruch
    for name, dv in zip(dist_names, dists):
        ne = _events(dv, Ts)
        out.append(Check("dvexc", "info" if ne else "warn", "dq_dvexc_steps" if ne else "dq_dvexc_none",
                         dict(name=name, n=ne)))

    # 10 · nezávislost MV a poruch (vliv na PV jde oddělit jen když se nemění současně)
    for name, dv in zip(dist_names, dists):
        a, b = np.diff(mv), np.diff(np.asarray(dv, float))
        ok = np.isfinite(a) & np.isfinite(b)
        r = float(np.corrcoef(a[ok], b[ok])[0, 1]) if ok.sum() > 10 and np.std(a[ok]) > 0 and np.std(b[ok]) > 0 else 0.0
        out.append(Check("indep", "warn" if abs(r) > 0.5 else "ok", "dq_indep_bad" if abs(r) > 0.5 else "dq_indep_ok",
                         dict(name=name, r=f"{r:.2f}")))
    return out


def summary(checks):
    """Počty (ok, warn, info) a celkový verdikt: vhodné pro identifikaci, pokud MV nebo porucha má buzení."""
    cnt = {k: sum(c.status == k for c in checks) for k in ("ok", "warn", "info")}
    usable = any(c.id in ("mvexc", "dvexc") and c.status == "info" for c in checks)
    return cnt, usable


def warn_mask(checks, n):
    """Sjednocená maska vzorků s upozorněním (pro zvýraznění v náhledu)."""
    m = np.zeros(n, bool)
    for c in checks:
        if c.mask is not None and len(c.mask) == n:
            m |= c.mask
    return m
