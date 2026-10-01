# Methods

An overview of what the application computes and how to read the results. The formulas are for orientation – the
exact implementations are in `pidtools/core/`.

- [Scaling](#scaling) · [Models](#models) · [Identification](#identification) · [Model evaluation](#model-evaluation) ·
  [PIDConL controller](#pidconl-controller) · [Tuning methods](#tuning-methods) · [Optimization](#optimization) ·
  [Robustness](#robustness) · [Simulation](#simulation) · [Diagnostics](#diagnostics) · [APC structures](#apc-structures) ·
  [References](#references)

---

## Scaling

PIDConL computes the control error in % of the **NormPV** range and the output in % of the **NormMV** range, which
is why Gain is dimensionless. The application works the same way internally: PV and MV are converted to % of the
controller ranges, the process gain is in %/%. The physical model (e.g. °C per % MV) does not depend on the range –
only its expression changes (K[%/%] = K[°C/%] · MV range / PV range). The proposed Gain, however, is valid only for
the given range, so the range must match the block. When the range is changed, the app rescales the model; no new
identification is needed.

---

## Models

All models have a dead time θ. Times are in seconds.

| Model | Transfer function | Typical process |
|---|---|---|
| Zero order | K·e^(−θs) | process very fast compared with the sampling (flow, pressure) |
| First order (FOPDT) | K·e^(−θs) / (T1·s + 1) | most self-regulating processes (temperature, pressure, concentration) |
| Second order (SOPDT) | K·e^(−θs) / ((T1·s + 1)(T2·s + 1)) | two significant lags (heat exchanger + sensor), S-shaped response |
| Integrating | Ki·e^(−θs) / s | level, position – the process does not settle |
| Integrating + first order | Ki·e^(−θs) / (s·(T1·s + 1)) | level with a slow actuator or sensor |

**Measured disturbances** have their own first-order-plus-dead-time model (Kd, Tp, θd) – integrating for
integrating processes. They improve the identification (the effect of the disturbance is not confused with the
effect of MV) and enable feedforward design.

**Choosing a model:** the simplest model with a good fit. Second order only if the fit improves clearly or the
response is markedly S-shaped. An integrating model for processes that do not settle at constant MV.

---

## Identification

Parameters are found by least squares: the simulated response of the model to the measured MV (and disturbances) is
compared with the measured PV. The dead time is searched on a grid and then refined. Options:

- **Unmeasured disturbances**
  - *none* – clean step-test data;
  - *medium* – the data are high-pass filtered before the fit; slow drift is removed, step responses remain;
  - *strong* – a slow unmeasured disturbance is estimated together with the model (smoothed curve). For integrating
    processes separating a disturbance from the effect of MV is inherently difficult – it is better to measure it.
- **Gain sign** – force positive / negative (when the data do not determine it clearly).
- **Valve stiction** – stick-slip model: the valve stays put until MV moves away from its position by more than the
  band S, then it jumps. The band S is estimated together with the model.
- **Fixed parameters** – known values (e.g. dead time from the pipe length) are fixed, the rest is refitted.
- **Uncertainty (bootstrap)** – the identification is repeated on data with resampled blocks of residuals; the spread
  of the parameters shows how precisely the model is determined. Used for robust optimization and simulation spread.

---

## Model evaluation

| Indicator | Meaning |
|---|---|
| **FIT %** | 100 · (1 − ‖y − ŷ‖ / ‖y − ȳ‖); ≥ 90 excellent, 80–90 good, 70–80 usable with cautious tuning, < 70 better repeat the test or choose another segment |
| **NRMSE** | root mean square error normalized by the data range |
| **R²** | share of explained variance |
| **Residuals – autocorrelation** | residuals should be "white"; strong autocorrelation = missing dynamics or a disturbance |
| **Residuals × ΔMV** | correlation of residuals with MV changes = the model does not explain the effect of MV (wrong structure or dead time) |

Always validate the model on **another segment** of data. A good fit on the identification segment alone is not
enough.

---

## PIDConL controller

Ideal (parallel) form, identical to PIDConL:

  MV = Gain · ( e + 1/TI · ∫e dt + TD · de/dt )

- The D action is filtered with the time constant TD / DiffGain.
- Optional **P on feedback** and **D on feedback** (acting on PV only, not on SP steps) – a smaller MV kick on SP
  changes.
- Deadband (continuous or step), MV limits with anti-windup, MV rate limit, SP ramp, PV filter, control zone
  (ConZone), feedforward (FFwd) and bumpless switching.
- **SampleTime**: a discrete controller adds roughly half a period to the dead time – the proposals take this into
  account (θ + SampleTime/2).

Rules that design a controller in series form (some PID) are converted to the ideal form of PIDConL.

---

## Tuning methods

Notation: K, T1, T2, θ – model (self-regulating), Ki – integrating; τc (λ) – desired closed-loop time constant.

### SIMC (Skogestad 2003)
Analytical rules with one parameter τc; default τc = θ ("tight" control), larger τc = slower and more robust.

- first order: Gain = T1 / (K·(τc + θ)), TI = min(T1, 4·(τc + θ))
- second order: PI with the "half rule" (T2/2 added to T1 and θ), PID with TD = T2
- integrating: Gain = 1 / (Ki·(τc + θ)), TI = 4·(τc + θ)

**When:** universal default, a good compromise between speed and robustness.

### iSIMC (Grimholt & Skogestad 2018)
SIMC shifted by θ/3: Gain = (T1 + θ/3) / (K·(τc + θ)), TI = min(T1 + θ/3, 4·(τc + θ)), for PID TD = θ/3.
**When:** self-regulating processes with significant dead time, where SIMC is needlessly cautious.

### Lambda / IMC
Response without overshoot with time constant λ (default 3θ). TI = T1 (cancellation of the process pole);
for integrating processes Gain = (2λ + θ) / (Ki·(λ + θ)²), TI = 2λ + θ.
**When:** calm and predictable response, interacting loops; rejects input disturbances more slowly.

### AMIGO (Åström & Hägglund 2004)
Rules derived by optimization for robustness Ms ≈ 1.4, without a tuning parameter.
**When:** safe first setting, uncertain or time-varying process.

### Averaging level control
The calmest controller that keeps the level within the allowed deviation ΔPV for the largest flow change ΔMV:
Gain = ΔMV / ΔPV, TI = 4 / (Ki·Gain).
**When:** surge tanks – the outflow should be smooth, the level may vary.

### D-action recommendation
Based on the normalized dead time θ/(θ + T): for lag-dominant processes (small θ/(θ+T)) PI is enough; in the middle
range D speeds up control; for dead-time-dominant processes D does not help. For second order D compensates the
second time constant. D amplifies noise – the app shows the MV noise.

---

## Optimization

Numerical search for Gain, TI (and TD) directly on the model, **taking the actual block into account** (SampleTime,
DiffGain, P/D on feedback, PV filter, MV rate) and always with the robustness constraint **Ms ≤ target** (plus
Mt ≤ target, for PID TD ≤ TI/4, optionally an MV noise limit).

| Criterion | What it minimizes | When |
|---|---|---|
| **MIGO** | maximizes the integral gain Gain/TI = smallest integrated error after a disturbance | best disturbance rejection at guaranteed robustness; default |
| **IAE** | ∫\|e\| dt | balanced compromise between speed and damping |
| **ISE** | ∫e² dt | mainly large deviations matter; more aggressive control |
| **ITAE** | ∫t·\|e\| dt | short settling, little ringing |
| **IAE + overshoot limit** | IAE with a penalty for overshoot above a limit | PV must not overshoot SP |

The time criteria are evaluated on the response to a **disturbance**, an **SP change**, **both**, or directly on
your **simulation scenario** (events, measured disturbances, valve, noise). The *robust* option searches for
parameters that satisfy Ms for all model variants from the uncertainty.

---

## Robustness

| Indicator | Meaning | Recommendation |
|---|---|---|
| **Ms** | maximum of the sensitivity function \|1/(1+L)\|; how close the loop is to instability | 1.4 very robust · 1.6 usual · 2.0 borderline |
| **GM** | gain margin – how much the gain may grow before instability | > 2 |
| **PM** | phase margin | > 45° |
| **MV noise** | standard deviation of MV caused by PV noise (high-frequency gain of the controller) | depends on the valve; watch it with PID |

Ms also guarantees minimum margins: GM ≥ Ms/(Ms − 1) and PM ≥ 2·arcsin(1/(2·Ms)). For Ms = 1.6 this is GM ≥ 2.7
and PM ≥ 36°, for Ms = 1.4 GM ≥ 3.5 and PM ≥ 42°. If the process changes more than these margins can absorb
(nonlinearity), choose a lower Ms or gain scheduling.

---

## Simulation

All simulations (batch, cascade and live) use a single step-by-step model of the PIDConL controller with all
elements of the block, plus:

- the process according to the model, measured disturbances through their models;
- **valve**: stiction (band, jump), characteristic in 10 % bands;
- PV noise, disturbances at the process input and output, event scenarios;
- the live simulation in the browser is a JavaScript port of the same computation (agreement verified by tests).

---

## Diagnostics

| Indicator | Method | How to read it |
|---|---|---|
| **Loop performance** | σ and IAE of the error, MV travel and reversals, time at a limit | compare before / after retuning |
| **Harris index** | minimum variance from an AR model of the error and the dead time | close to 1 = at the limit, small = room for improvement |
| **Oscillation** | autocorrelation (Thornhill) – period and regularity r | r > 1 = regular oscillation |
| **Stiction** | MV–PV cross-correlation (Horch), phase plot | odd correlation (ρ(0) ≈ 0) indicates stiction; even rather tuning or an external disturbance |
| **Valve hysteresis** | MV vs. position feedback | size of backlash / stiction in MV units |
| **Nonlinearity** | local gain for each MV step vs. the global model | ratio > 1.5 = one parameter set does not fit everywhere |

Oscillation caused by stiction does not disappear with retuning (only its period changes) – fix the valve, or
use a cascade on the valve position.

---

## APC structures

### Cascade
The outer controller sets the SP of the inner one. The inner loop is tuned first (fast, often PI or P); the outer
loop sees the closed inner loop approximately as a first-order lag with its effective time constant. **Speed
separation** at least 4–5× – otherwise the loops excite each other. Benefit: disturbances in the inner loop
(pressure, flow) and valve nonlinearity are handled before they reach the main variable.

### Feedforward
Ideal element FF = −Gdisturbance / Gprocess = −(Kd/K) · (T·s + 1)/(Tp·s + 1) · e^−(θd − θ)·s.
The **static** part (−Kd/K) does most of the work, the **dynamic** part (lead-lag, delay) corrects the different
speeds. If the disturbance acts faster than MV (θd < θ), the ideal element would have to anticipate – the lag is
shortened by the missing lead time; with a large difference static FF remains. **The controller is not tuned
differently because of feedforward** – FF is outside the feedback loop and does not change its stability; tune the
controller as usual and design the FF afterwards. Commission with reduced gain (50–80 %).

### 2×2 decoupling
**RGA** λ11 = K11·K22 / (K11·K22 − K12·K21) shows the strength of the interaction and whether the pairing is right:
λ ≈ 1 weak interaction (no decoupling needed), 0.5–0.8 or 1.25–2 moderate, > 2 strong, < 0.5 or negative =
consider swapping the MV–PV pairing. A **decoupler** is feedforward from the MV of the other loop:
D = −G12 / G11 (static or lead-lag).

### Override
Two controllers on one valve with a MIN or MAX selector: the main controller controls normally, the limiting one
takes over when its variable reaches a limit (pressure, temperature, load). The inactive controller tracks the
actual output through **external reset feedback** – no windup, bumpless takeover.

### Smith predictor
The controller sees a prediction of PV without dead time: PV + (model without delay − model with delay)·MV. It is
tuned as if there were no dead time. The benefit is mainly for θ/(θ+T) ≳ 0.5. It is sensitive to dead-time errors:
an underestimated θ leads to oscillation, an overestimated one is tolerated. Not suitable for integrating processes
(permanent offset under a permanent disturbance).

### Gain scheduling
The GainSched block interpolates Gain, TI and TD linearly between three points X1 < X2 < X3; outside them it holds
the end values.
- **X = PV** – compensates a nonlinear process: a model is identified and a controller tuned with the same robustness
  at each operating point. Verified on a nonlinear process built from the point models (gain by MV, dynamics by PV).
- **X = ER** (control error) – a deliberately nonlinear controller: points −E, 0, +E; normal tuning around SP,
  k × Gain at large error. The loop with k × Gain must be robust by itself (the app checks Ms ≤ 2), otherwise
  sustained oscillation results.
- **Control zone ConZone** (PIDConL) – outside the zone MV goes to a limit, inside normal control. A narrow zone
  makes the loop oscillate between the limits, a wide one overshoots after re-entry; the app searches the width by
  simulation. The simulation assumes a bumpless return to control – check the behaviour in your APL version.

---

## References

- S. Skogestad: *Simple analytic rules for model reduction and PID controller tuning*, J. Process Control, 2003.
- C. Grimholt, S. Skogestad: *Optimal PI and PID control of first-order plus delay processes and evaluation of
  the original and improved SIMC rules*, J. Process Control, 2018.
- K. J. Åström, T. Hägglund: *Revisiting the Ziegler–Nichols step response method for PID control* (AMIGO),
  J. Process Control, 2004; *Advanced PID Control*, ISA, 2006.
- T. J. Harris: *Assessment of control loop performance*, Can. J. Chem. Eng., 1989.
- N. F. Thornhill et al.: *Detection of multiple oscillations in control loops*, J. Process Control, 2003.
- A. Horch: *A simple method for detection of stiction in control valves*, Control Eng. Practice, 1999.
- E. H. Bristol: *On a new measure of interaction for multivariable process control* (RGA), IEEE TAC, 1966.
- Siemens: SIMATIC PCS 7 Advanced Process Library – documentation and application examples (Smith Predictor,
  entry 37361207; PID Tuning with Gain Scheduling, entry 38755162).
