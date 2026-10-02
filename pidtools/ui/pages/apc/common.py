"""
APC – společné konstanty, cache simulací a pomocné funkce stránek struktur.
"""
import numpy as np
import pandas as pd
import streamlit as st

from ....core import best_conzone, gs_sim
from ....core.apc import mimo2_sim, override_sim, smith_sim
from ....i18n import T
from ... import loops



ss = st.session_state
KINDS = ["cascade", "ff", "decouple", "override", "smith", "gainsched"]
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


def eng(rng):
    lo, hi = rng
    return lambda x: lo + np.asarray(x, float) * (hi - lo) / 100


def tchar(model):
    code, p = model[0], model[1]
    return p[-1] + (p[1] if code in ("P1D", "P2D", "I1D") else 0.0) + (p[2] if code == "P2D" else 0.0)


def grid(t_end, samp):
    h = float(min(samp, max(t_end / 6000, samp / 10)))
    n = int(t_end / h) + 1
    return h, n, np.arange(n) * h


def lab(name, rng_u):
    return f"{name} [{rng_u}]" if rng_u else name


def clean(ctrl):
    return {k: v for k, v in ctrl.items() if k not in ("FF", "FF_LL")}


def cross_model(x, y):
    """Model vlivu MV smyčky y na PV smyčky x [%PV_x / %MV_y] – z modelu měřené poruchy (sloupec MV_y)."""
    if y["c_mv"] in x["c_d"]:
        j = x["c_d"].index(y["c_mv"])
        if j < len(x["model"][2]):
            pd_ = list(x["model"][2][j])
            pd_[0] *= (y["mv_rng"][1] - y["mv_rng"][0]) / 100   # Kd je v %PV na jednotku MV_y
            return pd_
    return None


def gs_frame(tab):
    return pd.DataFrame([{T("gs_in"): name, **{T("gs_point", i=i + 1): float(f"{v:.4g}") if np.isfinite(v) else v
                                              for i, v in enumerate(vals)}, T("sm_apl_unit"): u}
                         for name, vals, u in tab])
