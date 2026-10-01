"""
Výpočty jádra s cache Streamlitu (stejné vstupy → okamžitý výsledek).
Stránky volají výpočty přes tento modul, ne přímo přes `pidtools.core`.
"""
import numpy as np
import streamlit as st

from .. import core

_cache = st.cache_data(show_spinner=False, max_entries=256)

pidconl_sim = _cache(core.pidconl_sim)
pidconl_sim_full = _cache(core.pidconl_sim_full)
robustness = _cache(core.robustness)
cascade_sim = _cache(core.cascade_sim)
loop_kpis = _cache(core.loop_kpis)
local_gains = _cache(core.local_gains)
fit_model = _cache(core.fit_model)
identify = _cache(core.identify)
settling_time = _cache(core.settling_time)


@st.cache_data(show_spinner=False, max_entries=64)
def opt_migo(code, p, ctype, samp, dg, ms, hf, starts, extra=(), pvf=0.0):
    return core.optimize_migo(code, list(p), ctype, samp, dg, ms, hf, starts, [list(e) for e in extra], pvf)


@st.cache_data(show_spinner=False, max_entries=128)
def opt_time(code, p, ctype, samp, dg, crit, target, ms, hf, starts, extra=(), ovs=0.02, pfb=False, dfb=True,
             pvf=0.0, rate=0.0, sp_amp=1.0, d_amp=1.0):
    return core.optimize_time(code, list(p), ctype, samp, dg, crit, target, ms, hf, starts, [list(e) for e in extra],
                              ovs, pfb, dfb, pvf, rate, sp_amp, d_amp)


@st.cache_data(show_spinner=False, max_entries=32)
def opt_scenario(code, p, pdl, ctype, ctrl_base, crit, h, sp, pv0, mv0, dmeas, dist_mv, dist_pv, ms, hf, starts,
                 extra=(), ovs=0.02):
    return core.optimize_scenario(code, list(p), [list(d) for d in pdl], ctype, dict(ctrl_base), crit, h,
                                  np.asarray(sp), pv0, mv0, [np.asarray(d) for d in dmeas], np.asarray(dist_mv),
                                  np.asarray(dist_pv), ms, hf, starts, [list(e) for e in extra], ovs)
