"""
Výpočty jádra s cache Streamlitu (stejné vstupy → okamžitý výsledek).
Stránky volají výpočty přes tento modul, ne přímo přes `pidtools.core`.
"""
import streamlit as st

from .. import core
from ..app import closedloop as app_cl
from ..app import tuning as app_tuning

_cache = st.cache_data(show_spinner=False, max_entries=256)

pidconl_sim = _cache(core.pidconl_sim)
pidconl_sim_full = _cache(core.pidconl_sim_full)
robustness = _cache(core.robustness)
cascade_sim = _cache(core.cascade_sim)
loop_kpis = _cache(core.loop_kpis)
local_gains = _cache(core.local_gains)
fit_model = _cache(core.fit_model)
identify = _cache(core.identify)
fit_windows = _cache(core.fit_windows)
predict_windows = _cache(core.predict_windows)
cross_validate = _cache(core.cross_validate)
settling_time = _cache(core.settling_time)


# optimalizace ladění (pidtools.app.tuning) – hashovatelné argumenty
opt_migo = st.cache_data(show_spinner=False, max_entries=64)(app_tuning.opt_migo)
opt_time = st.cache_data(show_spinner=False, max_entries=128)(app_tuning.opt_time)
opt_scenario = st.cache_data(show_spinner=False, max_entries=32)(app_tuning.opt_scenario)
identify_cl = st.cache_data(show_spinner=False, max_entries=32)(app_cl.identify)
