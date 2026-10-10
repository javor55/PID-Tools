"""
Výpočty jádra s cache Streamlitu (stejné vstupy → okamžitý výsledek).
Stránky volají výpočty přes tento modul, ne přímo přes `pidtools.core`.
"""
import streamlit as st

from .. import core
from ..app import closedloop as app_cl
from ..app import tuning as app_tuning

# Limity drží paměť serveru (cache je společná pro všechny relace): 64 výsledků na funkci, nejdéle hodinu.
_cache = st.cache_data(show_spinner=False, max_entries=64, ttl="1h")

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
opt_migo = st.cache_data(show_spinner=False, max_entries=32, ttl="1h")(app_tuning.opt_migo)
opt_time = st.cache_data(show_spinner=False, max_entries=64, ttl="1h")(app_tuning.opt_time)
opt_scenario = st.cache_data(show_spinner=False, max_entries=16, ttl="1h")(app_tuning.opt_scenario)
identify_cl = st.cache_data(show_spinner=False, max_entries=16, ttl="1h")(app_cl.identify)


def _compare(code, p, pdl, base_ctrl, req, avg, sigma_pv, robust):
    """Srovnání všech metod ladění (tabulka „Všechny metody“) – optimalizace i simulace odezev jednou na vstupy."""
    from types import SimpleNamespace
    solvers = SimpleNamespace(opt_migo=opt_migo, opt_time=opt_time, opt_scenario=opt_scenario)
    return app_tuning.compare(code, list(p), [list(d) for d in pdl], dict(base_ctrl), req, avg, sigma_pv, robust,
                              solvers, robustness)


compare = st.cache_data(show_spinner=False, max_entries=16, ttl="1h")(_compare)
