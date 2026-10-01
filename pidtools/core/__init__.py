"""
Výpočetní jádro (bez závislosti na Streamlitu).

Moduly:
  models          – struktury modelů, simulace odezvy, predikce
  identification  – fit modelů z dat, stikce, neměřené poruchy, hodnocení modelu, nejistota
  tuning          – pravidla ladění a optimalizace
  robustness      – kmitočtová analýza smyčky (Ms, GM, PM), šum MV
  simulation      – simulace PIDConL (dávková, kaskáda, živá)
  gainsched       – plánování parametrů PID podle pracovního bodu (blok GainSched)
  diagnostics     – diagnostika provozu, kvalita dat, úseky, nelinearita, plán testu
  demo            – ukázková data
"""
# veřejné rozhraní jádra (re-export)
# flake8: noqa
from .models import (MODELS, DIST_PARAMS, n_free, simulate, simulate_dist, model_dev, fit_percent, stiction_valve,
                     high_pass, spline_projector, dyn_scale, predict, predict_full, step_response)
from .identification import (fit_model, auto_th, fit_with_stiction, identify, model_metrics,
                             bootstrap_models)
from .robustness import loop_tf, is_stable, robustness, hf_gain, mv_noise
from .simulation import (ProcStep, PIDConL, Valve, valve_char_fn, pidconl_sim_full, pidconl_sim, cascade_sim,
                         LiveLoop, iae)
from .tuning import (integ_gain, default_tc, tune, ff_gain, d_advice, optimize_migo, closed_loop_steps,
                     overshoot_ratio, optimize_time, optimize_scenario, outer_with_inner)
from .diagnostics import (oscillation, stiction_ccf, valve_hysteresis, harris_index, loop_kpis, detect_steps,
                          data_quality, find_segments, local_gains, step_plan)
from .gainsched import gs_table, gs_er_table, gs_interp, gs_issues, SchedPlant, gs_sim, settled, best_conzone
from .demo import demo_data
