"""
APC – společné konstanty, cache simulací a pomocné funkce stránek struktur.
"""
import numpy as np
import pandas as pd
import streamlit as st

from ....core import best_conzone, gs_sim
from ....core.apc import mimo2_sim, override_sim, smith_sim
from ....i18n import T
from ....app.apc.common import clean, cross_model, eng, grid, tchar  # noqa: F401
from ... import loops



ss = st.session_state
KINDS = ["cascade", "ff", "decouple", "override", "smith", "gainsched", "split", "vpc", "ratio", "rga"]
C_B = "#7c3aed"          # druhá smyčka
C_REF = "#9aa5b1"        # srovnání (bez struktury)

mimo_sim = st.cache_data(show_spinner=False, max_entries=32)(mimo2_sim)
override_sim_c = st.cache_data(show_spinner=False, max_entries=32)(override_sim)
smith_sim_c = st.cache_data(show_spinner=False, max_entries=32)(smith_sim)
gs_sim_c = st.cache_data(show_spinner=False, max_entries=16)(gs_sim)
best_cz = st.cache_data(show_spinner=False, max_entries=16)(best_conzone)
C_PTS = ["#0e7490", "#b45309", "#7c3aed"]   # pracovní body 1–3



# ---------------------------------------------------------------- společné
def active_model(ctx):
    """Aktivní smyčka ve stejném tvaru jako loops.loop_data."""
    return dict(name=loops.name(loops.active()), model=ctx.model, ctrl=ctx.set2_ctrl, c_mv=ctx.c_mv, c_pv=ctx.c_pv,
                c_sp=ctx.c_sp,
                c_d=list(ctx.c_d), pv_rng=(ctx.pv_lo, ctx.pv_hi), mv_rng=(ctx.mv_lo, ctx.mv_hi), u_pv=ctx.u_pv,
                u_mv=ctx.u_mv)


def lab(name, rng_u):
    return f"{name} [{rng_u}]" if rng_u else name


def gs_frame(tab):
    return pd.DataFrame([{T("gs_in"): name, **{T("gs_point", i=i + 1): float(f"{v:.4g}") if np.isfinite(v) else v
                                              for i, v in enumerate(vals)}, T("sm_apl_unit"): u}
                         for name, vals, u in tab])
