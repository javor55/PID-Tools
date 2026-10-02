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
