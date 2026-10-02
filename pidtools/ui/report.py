"""
Protokol z ladění ve webové aplikaci: záznamy smyček z běhu a snímků, data pro graf modelu a hodnoty APC
aktivní smyčky; HTML sestaví pidtools.app.report.
"""
import streamlit as st

from ..app.report import SECTIONS, STATUSES  # noqa: F401
from ..app.report import build_report as _build
from ..core import MODELS
from . import loops

ss = st.session_state


# ---------------------------------------------------------------- data smyček
def loop_records(ctx):
    """Smyčky projektu (aktivní z aktuálního běhu, ostatní ze snímků) – jen ty s modelem."""
    out = []
    for i in loops.ids():
        r = loops.loop_data(i, ctx.fname)
        r["id"], r["active"] = i, i == loops.active()
        if r["active"]:
            r.update(model=ctx.model, ctrl=ctx.set2_ctrl, ctrl1=ctx.set1_ctrl, rng=tuple(ctx.rng),
                     c_pv=ctx.c_pv, c_mv=ctx.c_mv, c_sp=ctx.c_sp, c_d=list(ctx.c_d),
                     pv_rng=(ctx.pv_lo, ctx.pv_hi), mv_rng=(ctx.mv_lo, ctx.mv_hi), u_pv=ctx.u_pv, u_mv=ctx.u_mv)
            fit = ss.get("fit") or {}
            r["fit"] = fit.get("res", {}).get(ctx.model[0], {}).get("fit") if ctx.model else None
        if r["model"] is not None and r["ctrl"] is not None and r["ctrl1"] is not None:
            out.append(r)
    return out


def build_report(ctx, meta, sections, chart_mode="inline"):
    """Report jako HTML text pro aktuální projekt (viz pidtools.app.report.build_report)."""
    from .pages.apc import gs_values, recommend, smith_values   # až zde – stránka APC importuje moduly UI
    recs = loop_records(ctx)

    def model_data(r):
        if ctx.t is None:
            return None
        if r["active"]:
            return ctx.t, ctx.pv_e, ctx.mv_e, list(ctx.dists), ctx.Ts
        return (ctx.t, ctx.on_grid(r["c_pv"]), ctx.on_grid(r["c_mv"], zoh=True), [ctx.on_grid(c) for c in r["c_d"]],
                ctx.Ts)

    apc = {}
    act = next((r for r in recs if r["active"]), None)
    if act is not None and "apc" in sections:
        apc["items"] = recommend(ctx)
        integ = MODELS[act["model"][0]]["integ"]
        if not integ and any(k == "smith" for k, _, _ in apc["items"]):
            try:
                apc["smith"] = smith_values(ctx)[2]
            except Exception:
                pass
        try:
            gv = gs_values(ctx) if not integ else None
        except Exception:
            gv = None
        if gv:
            apc["gs"] = (gv[1], ss.get("gs_x") == "er")
    return _build(recs, meta, sections, chart_mode, model_data, apc)
