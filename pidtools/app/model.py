"""
Model procesu: identifikace podle nastavení, přepočet při změně rozsahu regulátoru, úpravy parametrů,
hodnocení, validace na jiném úseku a nejistota.

Data úseku (ts, pv, mv v %, d = měřené poruchy) jsou na společné mřížce s periodou Ts. Výsledek identifikace
jednoho modelu je slovník core.identify (p, pdl, fit, fit_raw, level, Th, stic, fixed).
"""
from dataclasses import dataclass

import numpy as np

from .. import core
from ..core import MODELS, dyn_scale, model_metrics, norm_factors, predict, predict_full, rescale_fit

NORM = slice(4, 8)   # pozice pv_lo, pv_hi, mv_lo, mv_hi v klíči identifikace
SIGN = {"auto": 0, "pos": 1, "neg": -1}


@dataclass
class IdSettings:
    """Nastavení identifikace (záložka Model)."""
    chosen: tuple = tuple(MODELS)
    th_max: float = None
    dist_level: str = "none"       # neměřené poruchy: none / medium / high
    dist_strength: float = 4.0
    gain_sign: str = "auto"        # auto / pos / neg
    id_stic: bool = False


def decimation(n, target=2500):
    """Krok decimace pro fit (nejvýš ~target vzorků; shoda se počítá na plných datech)."""
    return int(np.ceil(n / target))


def fit_key(fname, rng, s, norm, Ts, c_pv, c_mv, c_d, long_fmt):
    """Klíč identifikace: data, úsek, nastavení a rozsahy – jiný klíč = model k jiným datům nebo nastavení."""
    return (fname, rng, tuple(s.chosen), s.th_max, *norm, Ts, c_pv, c_mv, tuple(c_d), long_fmt, s.dist_level,
            s.dist_strength, s.gain_sign, s.id_stic)


def only_norm_changed(old, new):
    """Klíč identifikace se liší jen normovacími rozsahy (data, úsek i nastavení stejné)."""
    return (isinstance(old, tuple) and len(old) == len(new) and old != new
            and old[:NORM.start] == new[:NORM.start] and old[NORM.stop:] == new[NORM.stop:])


def rescale_results(res, old_norm, new_norm):
    """
    Modely přepočtené na nové rozsahy NormPV / NormMV: model v reálných jednotkách je stejný – mění se jen K v %/%,
    Kd a stikce v %; časy zůstávají. Vrací (výsledky, (fK, fKd, fS)) – faktory pro ruční úpravy a nejistotu.
    """
    return {c: rescale_fit(r, old_norm, new_norm) for c, r in res.items()}, norm_factors(old_norm, new_norm)


# ---- struktura přenosu poruch (stejné struktury jako MV: P0D … I1D)
DIST_CHOICES = ("pv", "auto") + tuple(core.DIST_STRUCTS)
_DIST_ALIAS = {"self": "P1D", "integ": "I1D"}      # starší volby typu (projekty)


def dist_structs(code, dkinds, nd):
    """
    Volby typu přenosu poruch → struktury pro fit: „pv“ = stejná struktura jako model MV, „auto“ = None (vybere se
    nejlepší), jinak struktura P0D … I1D.
    """
    out = []
    for j in range(nd):
        k = dkinds[j] if dkinds is not None and j < len(dkinds) else "pv"
        k = _DIST_ALIAS.get(k, k)
        out.append(code if k == "pv" else None if k == "auto" else k)
    return out


def compare_dists(fit, r, j, structs):
    """
    Struktury přenosu poruchy j porovnané fitem jen jejích parametrů (model MV a ostatní poruchy pevné):
    [(struktura, FIT, parametry poruchy | text chyby)]. fit(struktury, zafixované) → výsledek fitu.
    """
    fixed = {f"p{i}": float(v) for i, v in enumerate(r["p"])}
    for jj, d in enumerate(r["pdl"]):
        if jj != j:
            fixed.update({f"d{jj}_{i}": v for i, v in enumerate(core.pd_z(d))})
    out = []
    for st_ in core.DIST_STRUCTS:
        s2 = list(structs)
        s2[j] = st_
        try:
            q = fit(tuple(s2), fixed)
            out.append((st_, float(q["fit"]), core.pd_full(q["pdl"][j])))
        except Exception as ex:
            out.append((st_, None, str(ex)))
    return out


def fit_dists(fit, code, structs):
    """
    Fit modelu se strukturami poruch: None = vybrat nejlepší (první fit se strukturou jako MV, porovnání struktur
    každé takové poruchy, pak společný fit s vybranými – ponechá se lepší). Výsledek má „dv_cmp“ {j: porovnání}
    pro každou poruchu (výběr typu v kartě poruchy).
    """
    init = tuple(st_ or code for st_ in structs)
    r = dict(fit(init, None))
    flat = set(r.get("dv_flat") or ())
    chosen, cmp = list(init), {}
    for j in range(len(structs)):
        if j in flat:
            continue
        cmp[j] = compare_dists(fit, r, j, chosen)
        ok = [c for c in cmp[j] if c[1] is not None]
        if structs[j] is None and ok:
            chosen[j] = max(ok, key=lambda c: c[1])[0]
    if tuple(chosen) != init:
        try:
            r2 = dict(fit(tuple(chosen), None))
            if r2["fit"] >= r["fit"]:
                r = r2
        except Exception:
            pass
    r["dv_cmp"] = cmp
    return r


def identify(code, ts, pv, mv, Ts, d, s, fixed=None, stic_fixed=None, fn=core.identify, d_full=None, dkinds=None):
    """
    Identifikace jednoho modelu podle nastavení s (fn = core.identify nebo jeho varianta s cache). d_full – poruchy
    v celém záznamu: porucha, která se v úseku prakticky nemění, dostane nulový účinek (jinak by její parametry
    vyšly libovolné); její index je ve výsledku v „dv_flat“. dkinds – typ přenosu každé poruchy (DIST_CHOICES).
    """
    flat = core.flat_inputs(d, d_full) if d_full is not None else []
    fx = {k: 0.0 for j in flat for k in (f"d{j}_0", f"d{j}_1", f"d{j}_2", f"d{j}_3")}
    base = {**fx, **(fixed or {})}

    def fit(structs, fx2):
        return fn(code, ts, pv, mv, Ts, d, s.th_max, fixed={**base, **(fx2 or {})} or None, stic_fixed=stic_fixed,
                  level=s.dist_level, strength=float(s.dist_strength), sign=SIGN[s.gain_sign], id_stic=s.id_stic,
                  k=decimation(len(ts)), dstruct=structs)
    r = fit_dists(fit, code, dist_structs(code, dkinds, len(d)))
    return dict(r, dv_flat=flat) if flat else r


def identify_all(ts, pv, mv, Ts, d, s, fn=core.identify, progress=None, d_full=None, dkinds=None):
    """Identifikace všech zvolených modelů. Vrací (výsledky {kód: výsledek}, chyby [(kód, text)])."""
    res, errs = {}, []
    for i, c in enumerate(s.chosen):
        if progress:
            progress(i, c)
        try:
            res[c] = identify(c, ts, pv, mv, Ts, d, s, fn=fn, d_full=d_full, dkinds=dkinds)
        except Exception as ex:
            errs.append((c, str(ex)))
    return res, errs


def identify_cl_all(res, ts, sp, pv, mv, Ts, d, ctrl, s, progress=None, fn=None):
    """
    Doladění modelů z otevřené smyčky nepřímou identifikací v uzavřené smyčce (smyčka v AUTO, buzení změnami SP,
    regulátor ze záznamu = blok PIDConL + Set 1). Vrací (výsledky {kód: výsledek}, chyby [(kód, text)]); výsledek
    má stejný tvar jako core.identify, navíc method="cl", fit_cl_pv / fit_cl_mv a p_open (model z otevřené smyčky).
    """
    from . import closedloop as cl
    fn = fn or cl.identify
    out, errs = {}, []
    for i, (c, r) in enumerate(res.items()):
        if progress:
            progress(i, c)
        try:
            rc = fn(c, r["p"], r["pdl"], ts, sp, pv, mv, d, Ts, ctrl, s.th_max)
            fit = core.predict_full(c, rc["p"], rc["pdl"], ts, pv, mv, d, Ts, r.get("stic") or 0.0, r.get("level", "none"),
                                    r.get("Th"))["fit"]
            out[c] = cl.as_result(r, rc, fit)
        except Exception as ex:
            out[c] = r
            errs.append((c, str(ex)))
    return out, errs


# ---- identifikace z úseků podle vstupů (MV a každá porucha vlastní úseky, vyřazení dat podle mezí)


def valid_mask(n, signals, limits, tol):
    """
    Vzorky, které se počítají do fitu: signals [(pole, rozsah)] a limits [(zap, min, max)] ve stejném pořadí
    (PV, MV, poruchy). Vyřadí se vzorky na mezi nebo za ní (tolerance tol % rozsahu).
    """
    m = np.ones(n, bool)
    for (x, span), (on, lo, hi) in zip(signals, limits):
        if not on:
            continue
        x = np.asarray(x, float)
        e = tol / 100.0 * max(float(span), 1e-12)
        if lo is not None and np.isfinite(lo):
            m &= ~(x <= lo + e)
        if hi is not None and np.isfinite(hi):
            m &= ~(x >= hi - e)
        m &= np.isfinite(x)
    return m


def identify_windows(code, t, pv, mv, Ts, d, wins, valid, s, dkinds, dsigns, fixed=None, fn=core.fit_windows):
    """
    Identifikace jednoho modelu z úseků (indexy do celého záznamu). dkinds – typ přenosu každé poruchy
    (DIST_CHOICES: „pv“ = struktura jako MV, „auto“ = nejlepší z P0D … I1D, nebo daná struktura).
    """
    wins_t = tuple(map(tuple, wins))

    def fit(structs, fx2):
        return fn(code, t, pv, mv, Ts, d, wins_t, valid, s.th_max, {**(fixed or {}), **(fx2 or {})} or None,
                  SIGN[s.gain_sign], tuple(dsigns), None, 12, structs)
    r = fit_dists(fit, code, dist_structs(code, dkinds, len(d)))
    return dict(r, method="win", stic=0.0, fit_raw=r["fit"])


def identify_windows_all(t, pv, mv, Ts, d, wins, valid, s, dkinds, dsigns, fn=core.fit_windows, progress=None):
    """Identifikace všech zvolených modelů z úseků. Vrací (výsledky {kód: výsledek}, chyby [(kód, text)])."""
    res, errs = {}, []
    for i, c in enumerate(s.chosen):
        if progress:
            progress(i, c)
        try:
            res[c] = identify_windows(c, t, pv, mv, Ts, d, wins, valid, s, dkinds, dsigns, fn=fn)
        except Exception as ex:
            errs.append((c, str(ex)))
    return res, errs


def best(res):
    """Model s nejlepší shodou."""
    return max(res, key=lambda c: res[c]["fit"])


def fixed_params(p, p_fix, pdl, pdl_fix):
    """Zafixované parametry pro dofitování: {"p<i>": hodnota, "d<j>_<i>": hodnota}."""
    out = {f"p{i}": float(v) for i, (v, f) in enumerate(zip(p, p_fix)) if f}
    for j, (d, fx) in enumerate(zip(pdl, pdl_fix)):
        out.update({f"d{j}_{i}": float(v) for i, (v, f) in enumerate(zip(d, fx)) if f})
    return out


def clamp(p, pdl):
    """Upravené parametry v platném rozsahu (časové konstanty > 0, zpoždění ≥ 0)."""
    p = [float(v) for v in p]
    for i in range(1, len(p)):
        p[i] = max(p[i], 1e-6) if i < len(p) - 1 else max(p[i], 0.0)
    pdl = [[float(v) for v in d] for d in pdl]
    for d in pdl:                    # Tp / Tp2 = 0 = struktura bez dané setrvačnosti (P0D, I0D …)
        d[1] = max(d[1], 0.0)
        d[2] = max(d[2], 0.0)
        if len(d) > 4:
            d[4] = max(d[4], 0.0)
    return p, pdl


def is_edited(p, pdl, stic, r):
    """Liší se upravený model od nafitovaného?"""
    a3 = np.ravel([core.pd_z(d) for d in pdl])            # typ přenosu poruchy (4. prvek) se neupravuje
    b3 = np.ravel([core.pd_z(d) for d in r["pdl"]])
    return (not np.allclose(p, r["p"]) or (bool(r["pdl"]) and (a3.shape != b3.shape or not np.allclose(a3, b3)))
            or abs(stic - (r.get("stic") or 0.0)) > 1e-9)


def summary(res, ts, pv, mv, d, Ts):
    """Srovnání modelů: [{code, FIT, NRMSE, status, p, pdl, stic, fit_raw}] (shoda podle nastavení identifikace)."""
    out = []
    for c, r in res.items():
        pf = predict_full(c, r["p"], r["pdl"], ts, pv, mv, d, Ts, r.get("stic", 0.0), r.get("level", "none"), r.get("Th"))
        mm = model_metrics(pf["pv"], pf["yhat"], mv, Ts, dyn_scale(c, r["p"]))
        out.append(dict(code=c, FIT=mm["FIT"], NRMSE=mm["NRMSE"], status=mm["status"], p=list(r["p"]), pdl=r["pdl"],
                        stic=r.get("stic") or 0.0, fit_raw=r.get("fit_raw", r["fit"])))
    return out


def warnings(res, t_end, th_max):
    """Podezřelé výsledky: [(klíč textu, kód)] – časová konstanta delší než záznam, θ na horní mezi."""
    out = []
    for c, r in res.items():
        if c in ("P1D", "P2D") and r["p"][1] > t_end:
            out.append(("warn_long_T", c))
        if th_max and r["p"][-1] >= 0.98 * th_max and "p" + str(len(r["p"]) - 1) not in r.get("fixed", []):
            out.append(("warn_theta_max", c))
    return out


def evaluate(code, p, pdl, stic, level, Th, ts, pv, mv, d, Ts):
    """
    Hodnocení modelu na úseku: dict(pf = predict_full, fit, metrics, sigma_pv = bílý šum PV [%] z reziduí,
    y_plot = průběh pro graf v jednotkách PV – u „medium“ model s optimálním posunem na surových datech).
    """
    pf = predict_full(code, p, pdl, ts, pv, mv, d, Ts, stic, level, Th)
    y_plot = pf["yhat"] if level != "medium" else predict(code, p, pdl, ts, pv, mv, d, Ts, stic)[0]
    return dict(pf=pf, fit=pf["fit"], metrics=model_metrics(pf["pv"], pf["yhat"], mv, Ts, dyn_scale(code, p)),
                sigma_pv=float(np.std(np.diff(pf["pv"] - pf["yhat"])) / np.sqrt(2)), y_plot=y_plot)


def segment(t, rv):
    """Maska úseku (od, do) a čas od jeho začátku."""
    sv = (t >= rv[0]) & (t <= rv[1])
    return sv, (t[sv] - t[sv][0]) if sv.any() else t[sv]


def overlap(rv, rng):
    """Podíl úseku rv, který se překrývá s úsekem identifikace rng."""
    return max(0.0, min(rv[1], rng[1]) - max(rv[0], rng[0])) / max(rv[1] - rv[0], 1e-9)


def nfit(a, b):
    """Shoda průběhů [%] (NRMSE vůči rozptylu měření)."""
    return float(100 * (1 - np.linalg.norm(a - b) / max(np.linalg.norm(a - a.mean()), 1e-12)))


def validate_cl(code, p, pdl, ctrl, tv, sp, pv, mv, dists, Ts, samp, sim=core.pidconl_sim):
    """
    Přehrání smyčky na záznamu: simulace se sadou ctrl, SP a měřené poruchy z dat. Vrací dict(t, PV, MV, stable,
    fit_pv, fit_mv) – shody vůči měření (smysluplné pro sadu, se kterou smyčka v záznamu běžela).
    """
    h = min(Ts, samp)
    n = int(tv[-1] / h) + 1
    tg = np.arange(n) * h
    spg = np.interp(tg, tv, sp)
    dg = [np.interp(tg, tv, d_ - d_[0]) for d_ in dists]
    tt, _, Pv, Mv = sim(code, p, pdl, h, spg, float(pv[0]), float(mv[0]), ctrl, dg)
    ok = bool(np.all(np.isfinite(Pv)) and np.abs(Pv).max() < 1e5)
    out = dict(t=tt, PV=Pv, MV=Mv, stable=ok, fit_pv=None, fit_mv=None)
    if ok:
        out.update(fit_pv=nfit(pv, np.interp(tv, tt, Pv)), fit_mv=nfit(mv, np.interp(tv, tt, Mv)))
    return out


def uncertainty(ps, nominal):
    """Rozptyl parametrů z bootstrapu: dict(p05, p95, rel = ± polovina rozpětí 5–95 % vůči nominálu [%])."""
    arr = np.array(ps)
    p05, p95 = np.percentile(arr, 5, axis=0), np.percentile(arr, 95, axis=0)
    rel = [100 * (p95[i] - p05[i]) / 2 / max(abs(nominal[i]), 1e-12) for i in range(arr.shape[1])]
    return dict(p05=list(p05), p95=list(p95), rel=rel)
