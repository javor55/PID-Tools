"""
Identifikace z úseků podle vstupů a struktury přenosů poruch – společné pro webovou a desktopovou aplikaci.

Úseky {vstup: [[od, do] s]}: „MV“ a název každé měřené poruchy. Stav ručních úprav se čte funkcí get(klíč, výchozí)
(web: session_state.get, desktop: LoopState.get) se stejnými klíči: ed|kód|d{j}|i (parametry poruchy ve vektoru
fitu Kd, Tp, θd, Tp2) a dsel|kód|j (zvolená struktura poruchy po identifikaci).
"""
import numpy as np

from .. import core
from ..core import DIST_FIELDS, MODELS, dist_struct, dyn_scale, merge_windows, pd_full, pd_z, struct_setup


# ---- úseky
def inputs(c_d):
    """Vstupy s vlastními úseky: MV a měřené poruchy."""
    return ["MV"] + [str(c) for c in c_d]


def with_defaults(W, c_d, rng0):
    """Úseky doplněné pro všechny vstupy: MV začíná společným úsekem, poruchy bez úseků."""
    W = dict(W or {})
    for inp in inputs(c_d):
        W.setdefault(inp, [[float(rng0[0]), float(rng0[1])]] if inp == "MV" else [])
    return {k: [[float(a), float(b)] for a, b in v] for k, v in W.items() if k in inputs(c_d)}


def indices(t, W, c_d, step):
    """Indexové úseky pro identifikaci [(i0, i1)] a rozpětí všech úseků (od, do) nebo None."""
    idx = []
    for x in inputs(c_d):
        for a, b in W.get(x, []):
            if b - a > step:
                idx.append((int(np.searchsorted(t, a)), int(np.searchsorted(t, b, side="right"))))
    if not idx:
        return idx, None
    return idx, (float(t[min(a for a, _ in idx)]), float(t[min(len(t), max(b for _, b in idx)) - 1]))


def runs(mask, t):
    """Souvislé úseky, kde je maska pravdivá: [(od, do) s] (nejvýš 300)."""
    m = np.asarray(mask, bool)
    if not m.any():
        return []
    d = np.diff(np.r_[0, m.astype(int), 0])
    a, b = np.where(d == 1)[0], np.where(d == -1)[0]
    return [(float(t[i]), float(t[min(j, len(t) - 1)])) for i, j in zip(a[:300], b[:300])]


def owner_fits(t, wins_s, win_idx, fits):
    """{vstup: [FIT úseků]} – shody úseků (pořadí sloučených úseků) přiřazené vstupu, kterému úsek patří."""
    out, owners = {}, []
    for x, ws_ in wins_s.items():
        for a, _ in ws_:
            owners.append((int(np.searchsorted(t, a)), x))
    for k, (a, b) in enumerate(merge_windows(win_idx, len(t))):
        if k >= len(fits):
            break
        for i_, x in owners:
            if a <= i_ < b:
                out.setdefault(x, []).append(fits[k])
    return out


def full_horizon(T_end, code, p):
    """Po jak dlouhé době model na celém záznamu navazuje na data [s]: 8× dynamika, 5 min … třetina záznamu."""
    return float(min(max(8 * dyn_scale(code, p), 300.0), max(float(T_end) / 3, 300.0)))


def model_curves(code, p, pdl, stic, t, pv, mv, dists, Ts, valid=None, win_idx=None, seg=None,
                 pw=core.predict_windows, pr=core.predict):
    """
    Průběhy modelu v % PV na celém záznamu (NaN mimo úseky): „all“ (MV + poruchy), „mv“ (jen MV), „dv“ (jen poruchy)
    v úsecích, „full_*“ přes celý záznam (model navazuje na naměřenou PV každých full_h – posun, u integračních
    i drift – jinak by integrační proces s neznámou rovnovážnou MV během dlouhého záznamu ujel).
    win_idx = úseky podle vstupů; jinak seg = (maska úseku, ts, pv, mv, poruchy úseku, průběh modelu na úseku).
    """
    p0 = [0.0] + list(p[1:])
    pdl0 = [[0.0] + list(d[1:]) for d in pdl]
    out = {}
    if win_idx is not None:
        out["all"] = pw(code, p, pdl, t, pv, mv, Ts, dists, win_idx, valid)[0]
        if dists:
            out["mv"] = pw(code, p, pdl0, t, pv, mv, Ts, dists, win_idx, valid)[0]
            out["dv"] = pw(code, p0, pdl, t, pv, mv, Ts, dists, win_idx, valid)[0]
    else:
        mask, ts_s, pv_s, mv_s, d_s, y_s = seg

        def on_seg(y):
            yy = np.full(len(t), np.nan)
            yy[mask] = y
            return yy
        out["all"] = on_seg(y_s)
        if dists:
            out["mv"] = on_seg(pr(code, p, pdl0, ts_s, pv_s, mv_s, d_s, Ts, stic)[0])
            out["dv"] = on_seg(pr(code, p0, pdl, ts_s, pv_s, mv_s, d_s, Ts, stic)[0])
    H = full_horizon(t[-1], code, p)
    n_h = max(int(round(H / Ts)), 10)
    tiles = [(i, min(i + n_h, len(t))) for i in range(0, len(t), n_h)]

    def tiled(p_, pdl_):
        return pw(code, p_, pdl_, t, pv, mv, Ts, dists, tiles, valid)[0]
    out["full_all"] = tiled(p, pdl)
    if dists:
        out["full_mv"], out["full_dv"] = tiled(p, pdl0), tiled(p0, pdl)
    out["full_h"] = H
    return out


# ---- kontrolní odhady po úsecích
def fixed_all(r, skip=()):
    """Zafixované parametry výsledku r (MV i poruchy, vektor fitu) kromě názvů ve `skip`."""
    fx = {f"p{i}": float(v) for i, v in enumerate(r["p"])}
    for jj, d in enumerate(r["pdl"]):
        fx.update({f"d{jj}_{i}": float(v) for i, v in enumerate(pd_z(d))})
    return {k: v for k, v in fx.items() if k not in skip}


def structs(code, r):
    """Struktury přenosů poruch výsledku r."""
    return tuple(dist_struct(MODELS[code]["integ"], d) for d in r["pdl"])


def _gain_per_window(code, r, t, pv, mv, Ts, dists, wins, valid, dsigns, free, pick, fw):
    out = []
    fixed = fixed_all(r, (free,))
    for a, b in wins:
        i0, i1 = int(np.searchsorted(t, a)), int(np.searchsorted(t, b, side="right"))
        try:
            q = fw(code, t, pv, mv, Ts, dists, ((i0, i1),), valid, None, fixed, 0, tuple(dsigns), None, 4,
                   structs(code, r))
            out.append((float(a), float(b), float(pick(q)), float(q["fit"])))
        except Exception:
            out.append((float(a), float(b), None, None))
    return out


def window_checks(code, r, t, pv, mv, Ts, dists, wins_s, valid, dsigns, c_d, fw=core.fit_windows):
    """
    Kontrolní odhady (při identifikaci a dofitování): zesílení MV a každé poruchy zvlášť v každém jejich úseku
    (ostatní parametry pevné) – dict(mv=[(od, do, K, FIT)], win={j: [(od, do, Kd, FIT)]}).
    """
    return dict(mv=_gain_per_window(code, r, t, pv, mv, Ts, dists, wins_s.get("MV", []), valid, dsigns, "p0",
                                    lambda q: q["p"][0], fw),
                win={j: _gain_per_window(code, r, t, pv, mv, Ts, dists, wins_s.get(str(dn), []), valid, dsigns,
                                         f"d{j}_0", lambda q, j_=j: q["pdl"][j_][0], fw)
                     for j, dn in enumerate(c_d)})


# ---- struktura přenosu poruchy po identifikaci (výběr podle FIT, ruční úpravy)
def cmp_of(r, j):
    """Porovnání struktur přenosu poruchy j z identifikace [(struktura, FIT, parametry | chyba)] (i z projektu)."""
    c = r.get("dv_cmp") or {}
    return c.get(j, c.get(str(j))) or []


def dist_id(code, r, j):
    """Identifikovaná struktura přenosu poruchy j."""
    return dist_struct(MODELS[code]["integ"], r["pdl"][j])


def dsel(get, code, r, j):
    """Zvolená struktura přenosu poruchy j (výběr v kartě poruchy; jinak identifikovaná)."""
    v = get(f"dsel|{code}|{j}", None)
    return v if v in DIST_FIELDS else dist_id(code, r, j)


def dsel_options(code, r, j):
    """Struktury k výběru (identifikovaná a ty z porovnání s FIT) a jejich FIT."""
    fits = {st_: f_ for st_, f_, _ in cmp_of(r, j) if f_ is not None}
    opts = list(fits) or [dist_id(code, r, j)]
    if dist_id(code, r, j) not in opts:
        opts = [dist_id(code, r, j)] + opts
    return opts, fits


def dsel_pd(get, code, r, j):
    """Parametry poruchy j pro zvolenou strukturu: identifikované, nebo z porovnání struktur."""
    sel = dsel(get, code, r, j)
    if sel != dist_id(code, r, j):
        for st_, f_, pd_ in cmp_of(r, j):
            if st_ == sel and f_ is not None:
                return pd_full(pd_)
    return pd_full(r["pdl"][j])


def dist_from_ed(get, code, r, j):
    """Parametry poruchy j [Kd, Tp, θd, typ, Tp2] ze zvolené struktury a polí parametrů (ed|kód|d{j}|i)."""
    sel = dsel(get, code, r, j)
    z = pd_z(dsel_pd(get, code, r, j))
    z = [float(get(f"ed|{code}|d{j}|{i}", v)) for i, v in enumerate(z)]
    kind, fix = struct_setup(sel)
    for i, v in fix.items():
        z[i] = v
    return [z[0], z[1], z[2], kind, z[3]]


def fit_signals_ok(key, fname, c_pv, c_mv):
    """Patří identifikace s klíčem `key` k vybraným signálům (soubor, PV, MV)? Starší klíč bez nich = ano."""
    if not isinstance(key, tuple) or len(key) < 11:
        return True
    return key[0] == fname and key[9] == c_pv and key[10] == c_mv


def flat_kinds(choice):
    """Volba typu poruchy ze starší verze (self / integ) → struktura; ostatní beze změny."""
    return {"self": "P1D", "integ": "I1D"}.get(choice, choice)
