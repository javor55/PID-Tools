"""APC – doporučení struktur, které by mohly smyčce pomoct, podle modelů a vazeb mezi smyčkami projektu."""
import numpy as np

from ... import core
from ...core import MODELS
from ...core.apc import rga2
from ...i18n import T
from .common import cross_model, tchar


def delay_ratio(code, p):
    """Podíl dopravního zpoždění v charakteristickém čase (≥ 0,5 → kandidát na Smithův prediktor)."""
    lags = tchar((code, p)) - p[-1]
    return p[-1] / max(p[-1] + lags, 1e-9)


def nl_spread(code, p, pdl, ts_id, pv_id, mv_id, d_id, Ts, local_gains=core.local_gains):
    """Poměr největšího a nejmenšího lokálního zesílení na úseku identifikace (None = nelze určit)."""
    if MODELS[code]["integ"] or ts_id is None:
        return None
    try:
        lg = local_gains(code, p, pdl, ts_id, pv_id, mv_id, d_id, Ts)
    except Exception:
        return None
    if len(lg) < 2:
        return None
    g = np.abs([q["gain"] for q in lg])
    return float(np.max(g) / max(np.min(g), 1e-12))


def recommend(a, others, spread=None, ff_on=True):
    """
    Doporučené struktury pro smyčku a: [(druh, text, id druhé smyčky nebo None)].
    others: [(id, záznam smyčky)] ostatních smyček projektu; spread: výsledek nl_spread;
    ff_on: zda je dopředná vazba už zapnutá (jinak se při měřených poruchách nabídne).
    """
    items = []
    code, p = a["model"][0], a["model"][1]
    ratio = delay_ratio(code, p)
    if ratio >= 0.5 and not MODELS[code]["integ"]:
        items.append(("smith", T("g_reco_smith", r=f"{ratio:.2f}"), None))
    if spread is not None and spread > 1.5:
        items.append(("gainsched", T("g_reco_gs", s=f"{spread:.1f}"), None))
    for i, b in others:
        if b["c_sp"] not in (None, "—") and b["c_sp"] == a["c_mv"]:
            items.append(("cascade", T("g_reco_cascade", a=a["name"], b=b["name"]), i))
        if b["c_mv"] == a["c_mv"]:
            items.append(("override", T("g_reco_override", a=a["name"], b=b["name"], mv=a["c_mv"]), i))
        if b["model"] is not None and (b["c_mv"] in a["c_d"] or a["c_mv"] in b["c_d"]):
            xab, xba = cross_model(a, b), cross_model(b, a)
            lam = rga2(a["model"][1][0], xab[0] if xab else 0.0, xba[0] if xba else 0.0, b["model"][1][0])
            if not np.isfinite(lam) or abs(lam - 1) > 0.2:
                items.append(("decouple", T("g_reco_decouple", a=a["name"], b=b["name"],
                                            l="∞" if not np.isfinite(lam) else f"{lam:.2f}"), i))
    if a["model"][2] and not ff_on:   # volitelné – až za strukturami smyček
        items.append(("ff", T("g_reco_ff", d=", ".join(map(str, a["c_d"]))), None))
    seen, out = set(), []
    for it in items:
        if it[:2] not in seen:
            seen.add(it[:2])
            out.append(it)
    return out
