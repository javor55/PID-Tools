"""APC – dopředná vazba: hodnoty pro PIDConL (FFwd) a lead-lag v jednotkách MV."""
import numpy as np

from ...i18n import T
from .. import feedforward as ffm


def rows(c_d, dists, des, mv_range, u_mv="MV"):
    """Hodnoty do PCS 7 pro zapnuté poruchy: [(porucha, [(parametr, hodnota, jednotka)])] v jednotkách MV."""
    out = []
    for j, (dn, d) in enumerate(zip(c_d, des)):
        if not d["use"]:
            continue
        g = ffm.eng_gain(d["gain"], mv_range)
        dd = dists[j]
        span = float(np.nanmax(dd) - np.nanmin(dd)) if len(dd) else 0.0
        lim = float(min(mv_range, 1.5 * abs(g) * span)) if span > 0 else float(mv_range)
        r = [(T("ff_p_gain"), g, f"{u_mv} / 1 {dn}")]
        if d["dyn"]:
            lead, lag, delay = ffm.lead_lag(d)
            if lag > 0:
                r += [(T("ff_p_lead"), lead, "s"), (T("ff_p_lag"), lag, "s")]
            if delay > 0:
                r.append((T("ff_p_delay"), delay, "s"))
        r += [("PIDConL.FFwdHiLim", lim, u_mv), ("PIDConL.FFwdLoLim", -lim, u_mv)]
        out.append((str(dn), r))
    return out


def simulate(code, p, pdl, ctrl, des, j, step, samp, sim=None):
    """
    Skok měřené poruchy j (step v jejích jednotkách v 10 % délky) se sadou ctrl: bez dopředné vazby, se statickou
    a s dynamickou. Vrací (čas, {"none" | "static" | "dynamic": výsledek simulace}).
    """
    from ...core import pidconl_sim_full
    from .common import clean, grid
    sim = sim or pidconl_sim_full
    pdm = pdl[j]
    t_end = 12 * (max(p[-1], pdm[2]) + sum(p[1:-1]) + pdm[1]) + 50 * samp
    h, n, t = grid(t_end, samp)
    dm = [np.where((t >= 0.1 * t_end) & (i == j), float(step), 0.0) for i in range(len(pdl))]
    sp = np.full(n, 50.0)
    dsel = dict(des[j], use=True)
    variants = {"none": ([0.0] * len(pdl), [(0.0, 0.0, 0.0)] * len(pdl)),
                "static": ffm.to_ctrl([dsel if i == j else des[i] for i in range(len(des))], only=j, dyn=False),
                "dynamic": ffm.to_ctrl([dict(dsel, dyn=True) if i == j else des[i] for i in range(len(des))], only=j,
                                       dyn=True)}
    out = {k: sim(code, p, [list(x) for x in pdl], h, sp, 50.0, 50.0, dict(clean(ctrl), FF=ff, FF_LL=ffl), dm)
           for k, (ff, ffl) in variants.items()}
    return t, out


def sim_kpis(t, out, pv_range):
    """IAE a max. odchylka PV [jednotky PV] pro varianty simulace."""
    from ...core import iae
    sp = np.full(len(t), 50.0)
    return {k: dict(iae=float(iae(t, sp, o["PV"]) * pv_range / 100),
                    maxdev=float(np.max(np.abs(o["PV"] - 50.0)) * pv_range / 100)) for k, o in out.items()}
