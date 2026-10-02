"""
APC – doporučení struktur podle modelů a vazeb mezi smyčkami projektu, kontroly pro průvodce.
"""

from ....i18n import T
from ... import cache, loops
from ... import ff as ffmod
from ...widgets import model_name
from . import guide
from ....app.apc import recommend as app_reco
from .common import active_model


# ---------------------------------------------------------------- doporučení a kontroly
def recommend(ctx):
    """Struktury, které by mohly aktivní smyčce pomoct – podle modelů a vazeb mezi smyčkami projektu."""
    code, p, pdl = ctx.model
    others = [(i, loops.loop_data(i, ctx.fname)) for i in loops.ids() if i != loops.active()]
    ff_on = bool(pdl) and any(d["use"] for d in ffmod.design(code, p, pdl))
    return app_reco.recommend(active_model(ctx), others, nl_spread(ctx), ff_on)


def nl_spread(ctx):
    """Poměr největšího a nejmenšího lokálního zesílení na úseku identifikace (None = nelze určit)."""
    code, p, pdl = ctx.model
    return app_reco.nl_spread(code, p, pdl, ctx.ts_id, ctx.pv_id, ctx.mv_id, ctx.d_id, ctx.Ts, cache.local_gains)


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
