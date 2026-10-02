"""
Přehled smyček (audit): více smyček z jednoho souboru – uživatel jen označí, který signál je PV, MV, SP (a poloha
ventilu) které smyčky; návrh se udělá z názvů tagů (FIC101.PV, FIC101.MV, FIC101.SP …).

Pro každou smyčku: výkon (odchylka, IAE, pohyb MV, změny směru, čas v limitu), oscilace, podezření na stikci,
Harrisův index se zpožděním odhadnutým z dat, zamrzlé MV (ruční režim). Smyčky se seřadí podle závažnosti
problémů; smyčky kmitající se stejnou periodou se seskupí (společná oscilace) s odhadem zdroje.

Rozsahy pro % (NormPV / NormMV): zadané, jinak PV z rozsahu dat (s rezervou) a MV 0–100.
"""
from dataclasses import dataclass, field

import numpy as np

from ..core import harris_index, oscillation
from .dataset import to_grid
from .diagnostics import valve
from .guess import guess_roles, loop_tag

SEVERITY = {"osc": 3, "stic": 3, "sat": 2, "sat_hi": 3, "harris": 1, "harris_hi": 2, "travel": 1, "frozen": 1,
            "noise": 1}


@dataclass
class LoopDef:
    """Smyčka v přehledu: názvy sloupců a volitelné rozsahy (None = odhad)."""
    name: str
    pv: str
    mv: str
    sp: str = None
    pos: str = None
    pv_rng: tuple = None
    mv_rng: tuple = None
    integ: bool = False
    extra: dict = field(default_factory=dict)


def propose(sigs, get=None):
    """Návrh smyček podle tagů v názvech: skupiny se stejným tagem smyčky, v nich role PV / MV / SP / poloha."""
    groups = {}
    for c in sigs:
        tag = loop_tag(c)
        if tag:
            groups.setdefault(tag, []).append(c)
    out = []
    for tag, cols in groups.items():
        if len(cols) < 2:
            continue
        r = guess_roles(cols, get)
        if r["pv"] and r["mv"] and r["pv"] != r["mv"]:
            out.append(LoopDef(name=tag.upper(), pv=r["pv"], mv=r["mv"], sp=r["sp"], pos=r["pos"]))
    return out


def _rng(v, given):
    if given and given[1] > given[0]:
        return float(given[0]), float(given[1])
    lo, hi = float(np.nanmin(v)), float(np.nanmax(v))
    pad = max(0.1 * (hi - lo), 1e-6)
    return lo - pad, hi + pad


def delay_estimate(mv, pv, h, max_lag):
    """
    Zpoždění z dat: posun největší vzájemné korelace změn MV a PV (0 … max_lag) [s], jen je-li korelace
    významná (jinak None – např. šum bez buzení nebo čistě periodické signály s nejednoznačným posunem).
    """
    a, b = np.diff(np.asarray(mv, float)), np.diff(np.asarray(pv, float))
    if len(a) < 50 or np.std(a) < 1e-12 or np.std(b) < 1e-12:
        return None
    a, b = (a - a.mean()) / a.std(), (b - b.mean()) / b.std()
    n = len(a)
    L = int(min(max_lag / h, n // 4))
    c = np.array([abs(float(np.dot(a[:n - k], b[k:]))) / (n - k) for k in range(L + 1)])
    k = int(np.argmax(c))
    if c[k] < 4 / np.sqrt(n) or c[k] < 2 * np.median(c):
        return None
    return float(k * h)


def analyse_loop(sig, d, Ts_user=None, window=None):
    """
    Jedna smyčka: dict(name, ok, err, Ts, t, pv, mv, sp (inženýrské jednotky), kpis…, problems [(klíč, závažnost)],
    score). window = (od, do) [s] nebo None.
    """
    out = dict(name=d.name, ok=False, err=None, problems=[], score=0)
    try:
        g = to_grid(sig, d.pv, d.mv, d.sp, (), Ts_user)
    except Exception as ex:
        out["err"] = str(ex)
        return out
    t, h = g.t, g.Ts
    m = np.ones_like(t, bool) if not window else (t >= window[0]) & (t <= window[1])
    if m.sum() < 50:
        out["err"] = "err_short"
        return out
    t, pv_e, mv_e = t[m] - t[m][0], g.pv_e[m], g.mv_e[m]
    sp_e = g.sp_e[m] if g.has_sp else None
    plo, phi = _rng(np.r_[pv_e, sp_e if sp_e is not None else pv_e], d.pv_rng)
    mlo, mhi = d.mv_rng if d.mv_rng and d.mv_rng[1] > d.mv_rng[0] else (0.0, 100.0)
    P = lambda x: (np.asarray(x, float) - plo) / (phi - plo) * 100          # noqa: E731
    M = lambda x: (np.asarray(x, float) - mlo) / (mhi - mlo) * 100          # noqa: E731
    pv, mv = P(pv_e), M(mv_e)
    sp = P(sp_e) if sp_e is not None else None
    e = (sp - pv) if sp is not None else (pv - np.mean(pv))
    hours = max(t[-1] / 3600, 1e-9)
    dmv = np.diff(mv)
    thr = max(1e-6, 0.05 * np.std(dmv)) if len(dmv) else 1e-6
    sg = np.sign(dmv[np.abs(dmv) > thr])
    rev_h = (int(np.sum(sg[1:] != sg[:-1])) if len(sg) > 1 else 0) / hours
    at_lim = float(np.mean((mv <= 0.5) | (mv >= 99.5)) * 100)
    frozen = float(np.mean(np.abs(dmv) < 1e-9) * 100) if len(dmv) else 0.0
    v = valve(sp if sp is not None else pv, pv, mv, h, sp is not None, d.integ)
    osc = v["osc"] if v["osc"]["osc"] else oscillation(e, h)
    theta = d.extra.get("theta")
    if theta is None:               # u kmitající smyčky je posun korelace jednoznačný jen do půl periody
        cap = min(0.05 * t[-1], 600.0, 0.4 * osc["period"] if osc["osc"] else np.inf)
        theta = delay_estimate(mv, pv, h, cap)
    harris = harris_index(e, theta / h + 1) if theta is not None and np.std(e) > 1e-9 else None
    k = dict(std_e=float(np.std(e)) * (phi - plo) / 100, std_e_pct=float(np.std(e)),
             iae_h=float(np.sum(np.abs(e)) * h / hours) * (phi - plo) / 100, travel_h=float(np.sum(np.abs(dmv)) / hours),
             rev_h=float(rev_h), at_lim=at_lim, frozen=frozen, harris=None if harris is None else float(harris), theta=theta,
             osc=bool(osc["osc"]), period=float(osc["period"]) if osc["osc"] else None,
             amp=float(osc["amp"]) * (phi - plo) / 100 if osc["osc"] else None,
             stic=v["verdict"], stic_ratio=float(v["stic"]["ratio"]) if np.isfinite(v["stic"]["ratio"]) else None)
    probs = []
    if k["osc"]:
        probs.append("osc")
    if k["stic"] == "likely":
        probs.append("stic")
    if at_lim > 20:
        probs.append("sat_hi")
    elif at_lim > 5:
        probs.append("sat")
    if harris is not None and np.isfinite(harris) and harris > 0.8:
        probs.append("harris_hi")
    elif harris is not None and np.isfinite(harris) and harris > 0.5:
        probs.append("harris")
    if rev_h > 120:
        probs.append("travel")
    if frozen > 90:
        probs.append("frozen")
    out.update(ok=True, Ts=h, t=t, pv=pv_e, mv=mv_e, sp=sp_e, pv_rng=(plo, phi), mv_rng=(mlo, mhi), kpis=k,
               problems=[(p, SEVERITY[p]) for p in probs], score=int(sum(SEVERITY[p] for p in probs)))
    return out


def analyse(sig, loops, Ts_user=None, window=None, progress=None):
    """Všechny smyčky, seřazené od nejhorší (skóre, pak odchylka v % rozsahu)."""
    res = []
    for i, d in enumerate(loops):
        if progress:
            progress(i, d.name)
        res.append(analyse_loop(sig, d, Ts_user, window))
    return sorted(res, key=lambda r: (-r["score"], -(r["kpis"]["std_e_pct"] if r["ok"] else -1)))


def common_oscillations(res, tol=0.12):
    """
    Smyčky kmitající se stejnou periodou (± tol): [dict(period, loops, source)]. Zdroj = smyčka s podezřením na
    stikci, jinak s největší relativní amplitudou (oscilace se šíří od zdroje dál a slábne).
    """
    osc = [r for r in res if r["ok"] and r["kpis"]["osc"]]
    osc.sort(key=lambda r: r["kpis"]["period"])
    groups = []
    for r in osc:
        p = r["kpis"]["period"]
        for g in groups:
            if abs(p - g["period"]) <= tol * g["period"]:
                g["members"].append(r)
                g["period"] = float(np.mean([m["kpis"]["period"] for m in g["members"]]))
                break
        else:
            groups.append(dict(period=p, members=[r]))
    out = []
    for g in groups:
        if len(g["members"]) < 2:
            continue
        st = [m for m in g["members"] if m["kpis"]["stic"] == "likely"]
        src = (st or sorted(g["members"], key=lambda m: -m["kpis"]["std_e_pct"]))[0]
        out.append(dict(period=g["period"], loops=[m["name"] for m in g["members"]], source=src["name"],
                        by_stiction=bool(st)))
    return out


def to_records(loops):
    """Smyčky přehledu pro projekt (JSON)."""
    return [dict(name=d.name, pv=d.pv, mv=d.mv, sp=d.sp, pos=d.pos, theta=d.extra.get("theta"), integ=d.integ)
            for d in loops]


def from_records(recs, sigs=None):
    """Smyčky z projektu; s `sigs` vynechá ty, jejichž PV nebo MV v datech není."""
    out = []
    for r in recs or []:
        if not isinstance(r, dict) or not r.get("pv") or not r.get("mv"):
            continue
        if sigs is not None and (r["pv"] not in sigs or r["mv"] not in sigs):
            continue
        out.append(LoopDef(name=str(r.get("name") or r["pv"]), pv=r["pv"], mv=r["mv"],
                           sp=r.get("sp") if r.get("sp") not in ("", "—") else None,
                           pos=r.get("pos") if r.get("pos") not in ("", "—") else None, integ=bool(r.get("integ")),
                           extra={"theta": r.get("theta")} if r.get("theta") is not None else {}))
    return out
