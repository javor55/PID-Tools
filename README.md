# PID Tools (PIDConL Tuner)

🌟 **[Live Application Here!](https://pidtools.streamlit.app/)** 🌟

**PID Tools** is an interactive web application built with Python and Streamlit for process model identification from
measured data and for tuning PID controllers. It is tailored to the **PIDConL** block of **SIMATIC PCS 7 APL**, but the
methods apply to other industrial controllers as well.

## ✨ Main features
- **Data:** CSV/Excel (also long historian format), automatic resampling, compression check, data quality rating,
  automatic search for step-test segments.
- **Identification:** models P0D, P1D, P2D, I0D, I1D with dead time and measured disturbances; suppression of unmeasured
  disturbances, forced gain sign, simultaneous valve stiction identification, fixing of known parameters, bootstrap
  uncertainty; detailed model evaluation (FIT, NRMSE, IAE, R², residual tests) and validation on another segment.
- **Tuning:** SIMC, iSIMC, Lambda, AMIGO, averaging level control, numerical optimization (MIGO, IAE, ISE, ITAE,
  overshoot limit, whole simulation scenario) – always with a robustness constraint (Ms). Two parameter sets (Set 1 /
  Set 2), comparison of all methods, feedforward (static and lead-lag).
- **Simulation:** PIDConL (ideal form, D filter, P/D on PV, deadband, MV limits and rate, SP ramp, PV filter,
  anti-windup, bumpless transfer), valve stiction and characteristic, PV noise, event scenarios, live real-time simulation.
- **Diagnostics, test plan, cascade tuning, project files (JSON) and HTML report**, Czech and English UI.

## 🛠 Running
Windows: run **`start.bat`**. Otherwise:
```bash
pip install -r requirements.txt
streamlit run app.py
```

## 🧪 Tests
```bash
pip install -r requirements-dev.txt
python -m pytest            # core (fast) + whole application via Streamlit AppTest (~4 min)
python -m pytest tests/test_core.py tests/test_basic.py   # core only
```

## 📁 Structure
```
app.py                     entry point – builds the page from the modules below
pidtools/
  core/                    computation, no Streamlit dependency
    models.py              model structures, response simulation, prediction
    identification.py      fitting, stiction, unmeasured disturbances, evaluation, uncertainty
    tuning.py              tuning rules and optimizations
    robustness.py          frequency analysis (stability, Ms, GM, PM), MV noise
    simulation.py          PIDConL / valve / process step engine (batch, cascade, live)
    diagnostics.py         loop performance, oscillation, stiction, data quality, segments, test plan
    demo.py, util.py
  i18n/                    texts: cs.py, en.py, T()
  ui/                      Streamlit UI
    context.py             Ctx – data shared between tabs in one run
    widgets.py charts.py theme.py dataio.py cache.py project.py
    pages/                 one module per tab: header, data, model, tuning, live, diagnostics,
                           test_plan, cascade, project, progress
tests/                     pytest: core, whole app (AppTest), legacy project file
```
All process quantities inside the core are in % of the scaling ranges (NormPV, NormMV), so process gain and controller
Gain are dimensionless as in PIDConL.
