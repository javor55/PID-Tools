# PID Tools

**Process identification from plant data and tuning of the PIDConL controller (SIMATIC PCS 7 APL) – including
advanced process control (APC) structures.**

A web application for process and automation engineers. From a historian or PCS 7 export it identifies a process
model, proposes controller parameters, shows their robustness and expected behaviour, and creates a tuning protocol
stating exactly what to set in PCS 7. The methods apply to industrial PID controllers in general; terminology,
controller structure and implementation steps follow the **PIDConL** block and the templates of the **APL** library.

- **Online:** <https://pidtools.streamlit.app/> (public instance – see [Data and security](#data-and-security))
- **Documentation:** [User guide](docs/user-guide.md) · [Methods](docs/methods.md) ·
  [Implementation in PCS 7](docs/pcs7.md) · [Deployment](docs/deployment.md) · [Changelog](CHANGELOG.md)
- The user interface is in **English and Czech** (Settings › Language). Czech documentation: [docs/cs](docs/cs/README.md).

---

## What it is for

| Task | What the app does |
|---|---|
| **Retuning a loop** | identifies a model from a step test or operating data, proposes PI/PID and compares it with the current settings (robustness and simulation) |
| **Loop oscillates / is sluggish** | operating diagnostics: loop performance, oscillation, valve stiction, nonlinearity – shows whether retuning helps or the problem is elsewhere |
| **APC design** | cascade, feedforward, 2×2 decoupling, override, Smith predictor, gain scheduling – with guidance on *when to use* and values for the APL templates |
| **Documenting the change** | tuning protocol (HTML → PDF): original and new parameters, robustness, expected response, models, sign-off |

## Main features

- **Data** – CSV / Excel from a historian or PCS 7: common time column, a time column per variable, or long format
  (tag, time, value); time as a number or a date in ISO, Czech, US or European format; UTF-8, UTF-16 and
  windows-1250 encodings. PV / MV / SP are pre-filled from tag names. Data-quality check (historian compression,
  number and size of steps, noise) and automatic search for segments suitable for identification. **OPC UA**
  (read only, local / desktop version): browse the server, read the history of chosen tags or record live values.
- **Identification** – zero-, first-, second-order and integrating models, all with dead time and with models of
  measured disturbances; suppression of unmeasured disturbances, forced gain sign, valve stiction estimation, fixing
  of known parameters, model uncertainty (bootstrap), validation on another segment and detailed evaluation
  (FIT, residuals). **Closed-loop identification** from normal operation with the loop in AUTO (SP changes,
  indirect method with the controller from the record).
- **PIDConL tuning** – SIMC, iSIMC, Lambda, AMIGO, averaging level control and numerical optimization (MIGO, IAE,
  ISE, ITAE, overshoot limit, the whole scenario), always with a robustness constraint (Ms). Block configuration as
  in PCS 7 (NormPV/NormMV, SampleTime, DiffGain, PropFacSP, D on feedback, deadband, MV limits and rate, PV filter, SP ramp).
  Two parameter sets (current / new), comparison of all methods, scenario simulation with valve, stiction and noise
  (scenario first – setpoint step, load or output disturbance, measured disturbances, custom events – the suggestion
  is calculated on request and shown next to both sets), **frequency analysis** (Bode, Nyquist with the Ms circle,
  sensitivity |S| and |T|, bandwidth) and a tuning history.
- **Live simulation** in the browser – smooth, instant response to SP, manual MV, disturbances and noise, up to 500×
  speed.
- **APC** – cascade, feedforward (static and lead-lag), 2×2 decoupling (RGA, decouplers), override (MIN/MAX
  selector with external reset), Smith predictor, gain scheduling by PV or by control error, **split range**
  (balanced breakpoint), **valve position control** (small and large actuator), **ratio with cross-limiting**
  (fuel / air) and **N×N interaction** (RGA, Niederlinski index, pairing); each with a guide, a simulation of the
  benefit and values for the implementation.
- **Loop overview** – many loops from one file: mark PV / MV / SP of each loop (proposed from the tag names), the
  loops are ranked by their problems (oscillation, stiction, saturation, Harris index, valve wear, manual mode) and
  common oscillations are grouped with their likely source.
- **Several loops in one project** (e.g. the inner and outer loop of a cascade from one export).
- **Project file** (JSON) with models, tuning and optionally data.
- **Tuning protocol** (HTML, print to PDF) for all loops of the project.
- **A guide in every tab** – purpose, procedure, which method to choose when, practical tips and a checklist based
  on the state of your project.

## Quick start

### Online
Open <https://pidtools.streamlit.app/>, choose **Demo** and go through tabs 1–6 – each has its own guide (📖).

### Locally (Windows)
1. Install [Python 3.11](https://www.python.org/downloads/) (tick *Add Python to PATH*).
2. Download the repository (*Code › Download ZIP*) and unzip it.
3. Run **`start.bat`** – it installs the libraries and opens the app in the browser (<http://localhost:8501>).

### Windows application and offline PC (USB)
From Releases / Actions artifacts: **`PID-Tools-<version>-setup.exe`** installs the desktop application for the current
user (Start menu, no admin rights), **`PID-Tools-<version>-desktop-win64-portable.zip`** runs it without installing
(`PID Tools.exe`), and **`PID-Tools-<version>-web-win64-offline.zip`** runs the web app in the browser on the PC
(`PID-Tools.bat`) – no internet needed. See [docs/deployment.md](docs/deployment.md#offline-pc-usb).

### Desktop application (preview)

The same computations as a desktop window without a browser – for engineering stations (Windows 10/11):

```bash
pip install -r requirements.txt -r requirements-desktop.txt
python -m pidtools.desktop                 # optionally: python -m pidtools.desktop data.csv | project.json
```

Data, Model (validation, uncertainty), Tuning (method comparison, scenario simulation), live simulation, APC (cascade,
feedforward, decoupling, override, Smith predictor, gain scheduling by PV and by control error), operating
diagnostics, several loops in one project, projects (the same JSON files as the web app) and the tuning protocol.
For Windows it is available as an installer and as a portable ZIP (`PID Tools.exe`) – see
[Deployment](docs/deployment.md).

### Locally (Linux / macOS)
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Details, running on an internal server and updates: [docs/deployment.md](docs/deployment.md).

## Workflow in brief

1. **Data** – upload an export, check the PV / MV / SP columns (and measured disturbances, if any) and select
   a segment with clear MV changes (step test in manual) or SP changes (in auto).
2. **Model** – run the identification, pick a model with a good fit, check the residuals and validate it on
   another segment.
3. **Tuning** – configure the PIDConL block as in PCS 7 (above all the **range NormPV / NormMV**), enter the current
   faceplate parameters into Set 1, choose a method and take the new proposal into Set 2. Compare Ms and the
   simulation.
4. **Live simulation** – try both sets interactively.
5. **APC** – look at the recommendations; advanced structures are optional.
6. **Project & report** – save the project and create the tuning protocol.

In detail: [User guide](docs/user-guide.md).

## Methods in brief

**Models** (all with dead time θ): zero order (K), first order (K, T1 – FOPDT), second order (K, T1, T2 – SOPDT),
integrating (Ki) and integrating with first order (Ki, T1). Chosen by fit and by whether the process settles.

| Tuning method | When to use it |
|---|---|
| **SIMC** | universal default; one parameter τc (default = θ, larger = slower and more robust) |
| **iSIMC** | self-regulating process with significant dead time, where SIMC is needlessly cautious |
| **Lambda (IMC)** | calm response without overshoot, interacting loops; rejects disturbances more slowly |
| **AMIGO** | safe first setting without a tuning parameter (Ms ≈ 1.4); uncertain or time-varying process |
| **Averaging** | surge tanks – smooth outflow, the level may vary within limits |
| **Optimization** | a validated model and the aim to get the most out of it; MIGO (fastest disturbance rejection at given robustness), IAE / ISE / ITAE, overshoot limit, or directly your scenario |

**Robustness:** Ms (maximum sensitivity) 1.4 very robust, 1.6 usual, 2.0 borderline; plus gain margin (GM), phase
margin (PM) and MV noise.

| APC structure | When to use it |
|---|---|
| **Cascade** | the disturbance passes through a faster measurable variable (flow, pressure); valve stiction or nonlinearity |
| **Feedforward** | a measured disturbance with a strong effect on PV; tune the controller as usual, feedforward afterwards |
| **2×2 decoupling** | two loops affect each other (RGA far from 1) |
| **Override** | one valve, a main task plus a limit on another variable (pressure, temperature, load) |
| **Smith predictor** | dead time dominates (θ/(θ+T) ≳ 0.5) and is constant |
| **Gain scheduling** | nonlinear process over a wide range (by PV) or a faster return from large deviations (by ER) |

All methods, criteria and indicators explained: [docs/methods.md](docs/methods.md).

## Data and security

- Uploaded data are processed on the server running the app **only for the session** and are not stored (no writes
  to disk, no calls to external services, Streamlit telemetry is switched off).
- The web app does not store work in progress; save it as a project file (JSON).
- OPC UA access is **read only** – the application never writes to the server.
- The public instance runs on Streamlit Community Cloud. If you may not upload plant data to a third-party server,
  run the app **locally or on an internal server** ([docs/deployment.md](docs/deployment.md)).

## Disclaimer

The results are **proposals derived from a model**, which is always only an approximation of the process. Review the
parameters before deployment, introduce changes gradually and verify them on the plant according to your site rules.
The user is responsible for deployment. Parameter names of APL blocks may differ between library versions – check
them in the documentation of your version.

## License

[MIT](LICENSE) – free to use, modify and share, provided the copyright notice is kept. The software is provided
without any warranty.

## For developers

```bash
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest                                          # everything (~9 min, whole app via Streamlit AppTest)
python -m pytest tests/test_core.py tests/test_basic.py   # computation core only (fast)
```

```
app.py                     entry point of the web app (Streamlit Community Cloud deploys this file)
pidtools/
  core/                    computations – numpy/scipy only
    models.py              model structures, response simulation, prediction
    identification.py      model fitting, stiction, unmeasured disturbances, evaluation, uncertainty, range rescaling
    tuning.py              tuning rules and optimizations
    robustness.py          frequency analysis (stability, Ms, GM, PM), MV noise
    simulation.py          PIDConL / valve / process step by step (batch, cascade, live)
    apc.py                 decoupling (RGA), override, Smith predictor, feedforward design
    gainsched.py           gain scheduling (GainSched block), control zone
    diagnostics.py         loop performance, oscillation, stiction, data quality, segments, nonlinearity
    demo.py, util.py
  app/                     application layer – workflow shared by all frontends, no UI framework
    dataio.py guess.py     data loading, time parsing, resampling, PV/MV/SP role guessing
    dataset.py             table layouts (common time, time per variable, long format) → common time grid
    loop.py                NormPV/NormMV scaling, PIDConL block configuration, parameter sets
    model.py               identification settings, rescaling, edits, evaluation, validation, uncertainty
    tuning.py              methods, proposals (rules and optimizations), comparison, robustness of sets
    scenario.py            scenario events → signals, automatic length, plant, indicators
    feedforward.py         feedforward defaults and simulation parameters
    apc/                   one module per structure: recommend, cascade, feedforward, decouple, override,
                           smith, gainsched
    project.py             project file format (JSON)
    report.py plots.py     tuning protocol (HTML) and Plotly figure helpers
  i18n/                    texts: cs.py, en.py, T() – the frontend sets the language
  ui/                      Streamlit web frontend (widgets, session state, caching, charts)
  desktop/                 Qt desktop frontend (PySide6, pyqtgraph): state.py (one loop, no Qt), main.py, tabs/
    context.py             Ctx – data shared by the tabs within one run
    loops.py               several loops in a project (state snapshots, switching)
    static/                live simulation in the browser (live_engine.js = port of core/simulation.py)
    pages/                 one module per tab: header, data, model, tuning, live, diagnostics, project, guides,
                           apc/ (one module per structure)
tests/                     pytest: core, app layer, whole app (AppTest), data loading, loops, APC
tools/                     offline package for Windows (build_offline.py, smoke_test.py)
docs/                      user documentation (English; Czech in docs/cs), architecture.md
```

Layers: `core` ← `app` ← frontend (`ui` today; a desktop frontend can reuse `core` and `app` unchanged). `core`,
`app` (except the Plotly-based `report.py` and `plots.py`) and `i18n` must not import Streamlit or Qt – a test
checks it. See [docs/architecture.md](docs/architecture.md).

Inside the core all process quantities are in % of the controller ranges (NormPV, NormMV), so the process gain and
the controller Gain are dimensionless as in PIDConL. Data and results are shown to the user in real units.
Code comments are in Czech.
