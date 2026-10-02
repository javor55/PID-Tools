"""
APC – doporučení struktur podle modelů a vazeb mezi smyčkami projektu, kontroly pro průvodce.
"""
import numpy as np

from ....core import (MODELS)
from ....core.apc import rga2
from ....i18n import T
from ... import cache, loops
from ... import ff as ffmod
from ...widgets import model_name
from . import guide
from .common import active_model, cross_model, tchar


# ---------------------------------------------------------------- doporučení a kontroly
def recommend(ctx):
    """Struktury, které by mohly aktivní smyčce pomoct – podle modelů a vazeb mezi smyčkami projektu."""
    items = []
    code, p = ctx.model[0], ctx.model[1]
    lags = tchar((code, p)) - p[-1]
    ratio = p[-1] / max(p[-1] + lags, 1e-9)
    if ratio >= 0.5 and not MODELS[code]["integ"]:
        items.append(("smith", T("g_reco_smith", r=f"{ratio:.2f}"), None))
    spread = nl_spread(ctx)
    if spread is not None and spread > 1.5:
        items.append(("gainsched", T("g_reco_gs", s=f"{spread:.1f}"), None))
    a = active_model(ctx)
    for i in loops.ids():
        if i == loops.active():
            continue
        b = loops.loop_data(i, ctx.fname)
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
    pdl = ctx.model[2]
    if pdl and not any(d["use"] for d in ffmod.design(code, p, pdl)):   # volitelné – až za strukturami smyček
        items.append(("ff", T("g_reco_ff", d=", ".join(map(str, ctx.c_d))), None))
    seen, out = set(), []
    for it in items:
        if it[:2] not in seen:
            seen.add(it[:2])
            out.append(it)
    return out


def nl_spread(ctx):
    """Poměr největšího a nejmenšího lokálního zesílení na úseku identifikace (None = nelze určit)."""
    code, p, pdl = ctx.model[0], ctx.model[1], ctx.model[2]
    if MODELS[code]["integ"] or ctx.ts_id is None:
        return None
    try:
        lg = cache.local_gains(code, p, pdl, ctx.ts_id, ctx.pv_id, ctx.mv_id, ctx.d_id, ctx.Ts)
    except Exception:
        return None
    if len(lg) < 2:
        return None
    g = np.abs([q["gain"] for q in lg])
    return float(np.max(g) / max(np.min(g), 1e-12))


def chk_model_a(ctx):
    return True, T("g_chk_model_ok", n=loops.name(loops.active()), m=model_name(ctx.model[0])), None


def checks_cascade(ctx):
    if ctx.model is None:
        return [(False, T("g_chk_model", n=loops.name(loops.active())), (T("g_btn_model"), guide.goto, (None, "model")))]
    checks = [chk_model_a(ctx)]
    others = [(i, loops.loop_data(i, ctx.fname)) for i in loops.ids() if i != loops.active()]
    with_model = [b["name"] for _, b in others if b["model"] is not None]
    if with_model:
        checks.append((True, T("g_chk_cas_inner", n=", ".join(with_model)), None))
    else:
        checks.append((None, T("g_chk_cas_noinner"), (T("loop_add"), guide.add_loop_and_go, ())))
    inner = [b["name"] for _, b in others if b["c_sp"] not in (None, "—") and b["c_sp"] == ctx.c_mv]
    checks.append((True, T("g_chk_cas_mvsp_ok", mv=ctx.c_mv, n=", ".join(inner)), None) if inner
                  else (None, T("g_chk_cas_mvsp", mv=ctx.c_mv), None))
    checks.append((None, T("g_chk_cas_speed"), None))
    return checks
