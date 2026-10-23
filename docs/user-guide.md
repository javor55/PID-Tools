# User guide

This guide goes through the application tab by tab. In addition, every tab has its own **guide** (📖 at the top of
the tab) with the procedure, the choice of methods and a checklist based on the state of your project. Terms are
explained in the **Glossary** under *Help*.

- [Before you start](#before-you-start) · [Top bar](#top-bar) · [1 · Data](#1--data) · [2 · Model](#2--model) ·
  [3 · PIDConL tuning](#3--pidconl-tuning) · [4 · Live simulation](#4--live-simulation) · [5 · APC](#5--apc) ·
  [6 · Project & report](#6--project--report) · [FAQ](#faq)

---

## Before you start

**What data you need.** A record of the loop with **PV** (controlled variable), **MV** (controller output) and
ideally **SP**. The best source for identification is a **step test in manual**: 2–4 MV steps of 3–10 % from steady
state, each held until PV settles (roughly 4× the time constant plus the dead time). Operating data in auto with SP
steps work too, but the model tends to be less accurate. If a measurable disturbance (inflow, inlet temperature)
has a strong effect on PV, export it as well.

**Sampling.** The data period should be at least 10× shorter than the process time constant. A historian with
compression (deadband) creates "staircases" – the app warns about it; ask for uncompressed data for identification
if possible.

**File format.** CSV or Excel. Supported layouts:

| Layout | Example |
|---|---|
| Common time | `Time;TIC101.PV;TIC101.MV;TIC101.SP` |
| Time per variable | `Time PV;PV;Time MV;MV;…` (each variable has its own time stamps; the app aligns them on a common grid) |
| Long format | `Tag;Time;Value` (typical historian export) |

Time can be a number (s, min, h) or a date and time in ISO, Czech (`1.10.2026 14:05:00`), US or European format.
Separator, decimal comma and encoding (UTF-8, UTF-16, windows-1250) are detected automatically.

---

## Top bar

- **Project** – loop label (tag) and loading of a saved project (JSON).
- **Help** – how to proceed, glossary and *About* (version, disclaimer, data handling).
- **Settings** – language (English / Czech) and chart height. Light / dark theme in the ⋮ menu › Settings.
- **Data bar** – data source (**File**, **Demo**, **Project**), data summary (samples, period, ranges) and the
  loop switcher.
- **Another loop** – adds a loop to the project. Loops share the file; each has its own columns, model, tuning and
  APC settings. Loops from one export can be combined into a cascade, decoupling or override.

---

## 1 · Data

1. **Columns and units** – check the layout, time format and the pre-filled **PV, MV, SP** columns. Optionally add
   **measured disturbances** and the **valve position** (position feedback – for valve diagnostics). Enter the PV
   and MV units. *The controller range NormPV / NormMV is set in the Tuning tab.*
2. **Preview of loaded data** – the table after resampling, statistics and the original file with detected types.
3. **Record viewer** – every signal of the file as recorded (no resampling), for analysing a CSV on its own
   (web; the desktop app follows):
   - **panels**: PV + SP, MV and disturbances to start with; the list on the left shows every signal – tick it to show
     it, pick its panel (or a new one), colour and unit (*⋯*). The **Y scale** of every signal is set with the button
     next to it (*auto*) or by clicking its Y axis: auto from the view, auto from the whole record, or fixed min / max. In a panel every signal has its own
     Y axis, or tick **shared Y axis**. Panels can be moved up / down and resized by dragging their bottom edge;
   - **zoom X and Y independently**: wheel = time, **Shift + wheel** = Y of the panel, wheel over a Y axis = that axis
     only; drag = pan time (**Shift** = pan Y), drag a Y axis = pan that axis; **Zoom ⬚ / X / Y** = select with the
     mouse; double-click = full time and automatic Y; **Back / Forward** (Backspace) step through the zoom history;
     the strip under the time axis is an overview of the whole record (drag the frame);
   - **Auto Y** follows the view or the whole record; **Curve** as a line or steps (held values); zoomed in close the
     samples are drawn as points;
   - **cursors** like on an oscilloscope: C1 / C2 (drag, click moves the nearest, ← / → = one sample) with the times,
     Δt, 1/Δt and for every signal the values, Δ, Δ/Δt and min / max / mean / σ between the cursors;
     **horizontal cursors** H1 / H2 for the chosen signal (click its name) with ΔH;
   - **table** of the values in the view (a click on a row puts C1 there), **CSV** of the view or of the span between
     the cursors;
   - **calculated signals** (*+ ƒ Calculated signal* in the list): a formula over other signals, e.g. `SP - PV`,
     `lag(TT101, 30)` or `avg([FT 1], 60)` – operators, `abs`, `min`, `max`, `clip`, `if`, filter `lag`, moving
     average `avg`, derivative `der`, `diff`, integral `integ`, `delay`, time `t`. A calculated signal works like any
     other (panels, cursors, table, CSV, analysis); the formula language is safe (no program code is run);
   - **Analysis** under the chart:
     - **Events** – found automatically and marked in the chart: MV, SP and disturbance steps, state changes (signals
       with a few values, e.g. mode), MV at 0 / 100 %, a live signal that stops changing, data gaps; a click on a row
       or ◀ ⚑ / ⚑ ▶ in the toolbar jumps to the event;
     - **Step response** between the cursors (*Find next step* places them): gain K, dead time θ and time constant T
       (two-point method), rise time, overshoot, settling time; for an integrating process the integrating gain;
     - **Correlation** of a target (PV) with every other signal over the view or between the cursors: the strongest
       correlation and its lag – which signals influence the PV and how late (*auto* uses increments, or target
       increments against values for integrating processes);
     - **XY plot** of two signals (points coloured by time, linear regression) – e.g. MV against the valve position
       (hysteresis, stiction) or PV against MV (static characteristic);
     - **Compare spans** – several spans (the view or between the cursors) drawn over each other from their start,
       optionally as Δ from the start value;
   - the layout (panels, colours, scales, cursors, calculated signals, analysis settings) is saved with the project.
   *The identification segment is selected in the Model tab.*
4. **Operating diagnostics** (bottom of the tab) – on a selected operating segment:
   - **loop performance**: standard deviation and IAE of the control error, MV travel and reversals, time at a limit,
     Harris index (how far the loop is from the theoretical minimum variance);
   - **oscillation** (period, regularity) and **valve stiction** (MV–PV cross-correlation, phase plot);
   - **valve hysteresis** from the valve position (if available);
   - **nonlinearity**: the local gain for each MV step – if they differ by more than 1.5×, one parameter set does
     not fit everywhere (link to gain scheduling);
   - **compare with a second segment** – e.g. performance before and after retuning.

---

## 2 · Model

1. **Identification segment** – a common segment, or segments per input (the MV and every disturbance have their
   own); drag the handles in the chart or type the numbers (web and desktop work the same). Below it the **data quality for identification**: number,
   direction and spacing of steps, settling after the last step, signal-to-noise ratio, historian compression,
   sampling, MV at or beyond a limit, SP ramps. Each warning says what to do about it.
   **Identification data** (above *Identify*): *Automatic from the record* (default) recognises when the MV is moved by
   a person (manual, MAN – steps) and when by the controller (AUTO – the MV follows the error) and shows the share of
   AUTO in the segment. When AUTO prevails and the SP changes, closed-loop identification is used; otherwise MV → PV.
   An MV → PV model from data with the loop in AUTO is biased (typically the dead time is missing and the tuning comes
   out absurdly aggressive) – the app warns and offers *Narrow to the manual span* or *Identify in closed loop*.
2. **Models** – choose which structures to try (default: all; the best fit is offered). Integrating models are for
   processes that do not settle (level). A slow process with almost no dead time is flagged as a probable
   identification error; the Tuning tab also warns when the loop gain K·Gain is very high or the proposal differs
   more than 20× from the current Set 1.
3. **Identification settings**:
   - *Max. θ* – upper limit of the dead time;
   - *Unmeasured disturbances* – none / medium (filter of slow changes) / strong (slow disturbance estimated
     together with the model);
   - *Gain sign* – automatic / positive / negative (e.g. an outflow valve);
   - *Identify stiction* – estimates the valve stiction band together with the model.
4. **Identify** – the result is a table of models (FIT, NRMSE, rating, parameters) and a chart of model vs. data.
   Select the model for tuning.
5. **Checks** – residuals (should look like noise), comparison of all models, **manual parameter editing** with the
   option to fix parameters and refit the rest (e.g. a known dead time).
6. **Model uncertainty** – bootstrap: spread of parameters and responses; used for robust tuning and simulation
   spread.
7. **Model validation** – the model on another data segment and a replay of the loop with Set 1 (does the
   simulation match how the loop actually ran).

The model belongs to the specific data and segment; when the data change, the app warns that a new identification
is needed. A change of the controller range only rescales the model.

---

## 3 · PIDConL tuning

1. **PIDConL block** – configure exactly as in PCS 7:
   - **Controller range NormPV / NormMV** – the range of the block, not of the data (e.g. 0–300 °C). Gain is
     dimensionless (error in % of NormPV, MV in % of NormMV), so it depends directly on the range;
   - SampleTime (OB cycle), DiffGain, PropFacSP (setpoint weight of P, 0–1), D on feedback (DiffToFbk), deadband,
     MV limits;
   - loop elements: PV filter, MV rate, SP ramp.
2. **D-action recommendation** – from the ratio of dead time and time constants (PI vs. PID).
3. **Method** – SIMC, iSIMC, Lambda, AMIGO, averaging, optimization (see [Methods](methods.md)).
4. **Parameter sets** – **Set 1** = current faceplate parameters (reference), **Set 2** = new proposal (button
   *Write to Set 2*). Robustness table: Ms, GM, PM, MV noise, optionally the worst Ms over the model uncertainty.
5. **Compare all methods** (expander) – all methods side by side with Ms and IAE; a selection can be written to
   a set.
6. **Scenario simulation** – **SP from → to** (start and target setpoint in PV units) and the simulation length,
   by default **automatic** from the closed-loop settling time (4×, so the loop settles between the events; event
   times scale with it). Your own events (step, ramp, sine, pulses, noise on SP, process input, PV or
   a measured disturbance) or a **replay of the measured disturbances**. Process and valve in simulation: stiction,
   valve characteristic in bands, PV noise. Optionally sensitivity to model error, spread over the model
   uncertainty and **compare without feedforward**. Indicator table: IAE, max. deviation, MV range and travel,
   valve reversals.
7. **Download result (CSV)**.

Feedforward is configured in APC; the Tuning tab only shows its status, and it applies to all simulations.

---

## 4 · Live simulation

The loop runs directly in the browser – changes take effect immediately.

- **Auto / Manual**, SP changes, manual MV, speed 1–500×;
- **comparison of sets** (Set 1 vs. Set 2 at once), writing modified parameters back to the sets;
- **disturbances**: step, ramp, sine, random, pulse – at the process input or output;
- **measurement**: PV noise and filter;
- **process change** (K, T, θ, stiction) – how the loop copes with model error;
- indicators since the last event (IAE, max. deviation, overshoot, settling time, MV travel), window length,
  events in the chart, CSV / PNG export.

---

## 5 · APC

At the top there are **recommendations** based on the models and the couplings between the loops of the project.
Every structure has a guide (*when to use and when not, examples, checklist, implementation in PCS 7*), a simulation
of the benefit and values for the APL templates – see [Implementation in PCS 7](pcs7.md).

| Structure | What you do in the app |
|---|---|
| **Cascade** | inner loop from another loop of the project, from data or entered manually; tuning of the inner and outer loop, check of the speed separation, simulation |
| **Feedforward** | static / dynamic FF for each measured disturbance, gain in MV units for the FFwd input, limits, simulation of a disturbance step without FF / static / dynamic |
| **Decoupling** | RGA and pairing advice, decouplers (static and lead-lag) from cross-coupling models, simulation with SP changes of both loops |
| **Override** | main and limiting loop on one valve, MIN/MAX selector with external reset, simulation showing when the limit takes over |
| **Smith predictor** | choice of τc, sensitivity to model error (gain, time constants, dead time), values for the SmithPredictorControl template in engineering units incl. the PV0 offset |
| **Gain scheduling** | by **PV**: three operating points from data segments, a model and tuning at each, table for the GainSched block, simulation on a nonlinear process. By **ER**: higher gain at large error, safe multiple, comparison with the ConZone control zone |

---

## 6 · Project & report

- **Save project** – saves all loops, models, tuning and APC settings, optionally the data (JSON file). Load it in
  the top bar under *Project*.
- **Tuning protocol (report)** – plant, author, status, comment, choice of sections (model, tuning, response, APC,
  sign-off); charts embedded (works offline) or loaded from the internet (smaller file). Downloaded as HTML; to PDF
  via *Print › Save as PDF*.

---

## FAQ

**Do I need a step test?** No, but it is the best source. Operating data in auto with SP steps also work; data
without changes (just noise) do not give a reliable model – the data-quality check will tell you.

**Where do I set the PV range?** In Tuning › PIDConL block (NormPV / NormMV). Data stay in real units; the range
determines how Gain is scaled.

**Why is Set 1 "unstable"?** Set 1 is meant to be the current faceplate setting. As long as it contains the default
placeholder values, the app reminds you to enter them.

**I have several loops in one export.** Add them with *Another loop*; each selects its own columns.

**Is the controller tuned differently when I use feedforward?** No. Feedforward does not change the stability of
the loop – the controller is tuned as usual and the feedforward is designed afterwards.

**How do I transfer the result to PCS 7?** The parameter table in Tuning (and in the protocol) corresponds to the
PIDConL inputs; values for the APC templates are in the individual structures – see
[Implementation in PCS 7](pcs7.md).
