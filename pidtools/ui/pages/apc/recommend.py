"""
APC – doporučení struktur podle modelů a vazeb mezi smyčkami projektu, kontroly pro průvodce.
"""

from ... import cache, loops
from ... import ff as ffmod
from ....app import guides as app_guides
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


def rec_a(ctx):
    """Minimální záznam aktivní smyčky pro sdílené kontroly (pidtools.app.guides)."""
    return dict(name=loops.name(loops.active()), model=ctx.model, c_mv=ctx.c_mv)


def checks_cascade(ctx):
    others = [(i, loops.loop_data(i, ctx.fname)) for i in loops.ids() if i != loops.active()]
    return app_guides.apc_cascade(rec_a(ctx), others)
