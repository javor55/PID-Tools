# Changelog

## Unreleased

- Data: WinCC trend exports (UTF-16, `;`, pairs `X Time` / `X ValueY`) load; empty columns (unused trend curves)
  are skipped and the signals are named after the curve (`PV_Out`, not `PV_Out ValueY`). Loading long records is
  faster (time format detected on a sample, fast CSV parser when the separator is clear).
- Web: long records (e.g. 24 h at 1 s) no longer make every interaction take 15+ s – the automatically found
  segments are drawn into the chart at once (at most 40 shaded); charts thin out curves with gaps too.

## 3.2.1 beta – faster desktop start, set 1 check for closed-loop identification

**Beta:** for testing; please report problems.

- Closed-loop identification (loop in AUTO, web and desktop): warning when set 1 does not match the controller in
  the record (the loop simulated with the model and set 1 fits PV < 50 % or is unstable), and the button
  **Estimate set 1 from the record** (PI controller from the MV moves against the error, least squares).
- Desktop starts faster: SciPy and Plotly are loaded only when first needed, and a splash screen with the icon
  appears at once.
- Desktop charts: the cursor readout no longer resizes the charts (e.g. in the frequency analysis).

## 3.2.0 beta 1 – Windows application (installer), UI feedback, data loading

**Beta:** first build of the Windows installer and the separate web offline package – please report problems.

- Data: files whose time is not recognised (or does not change) open with one row = one sample; the sample period
  per row is set under File layout and time (s, ms, min, h). Times with month names (Aug-04-07 20:47:20) are
  recognised; CSV exports with whole lines in quotes (IP.21 via Excel) are unwrapped; empty rows are skipped.
- Desktop starts about twice as fast (APC panels are created on first use; the offline package ships bytecode).
- Desktop charts: text buttons (Full range, Cursor, Measure, PNG, CSV, Copy, Window); Full range shows the whole
  record at once; zoom and pan in time only with the y axis following the visible data; double-click = full range.
- Model (desktop and web): one chart set – record with the segment, model, residuals and measured disturbances;
  editable parameters one per row.
- Tuning: the PIDConL block is section 1 and NormPV / NormMV are estimated from the data while still at the
  0–100 default; the scenario with the current sets is shown immediately; the default suggestion is optimisation,
  PI, IAE + overshoot limit, set-point step and disturbance.
- Side panel sections start collapsed; feedforward parameters one per row.
- Data: statistics of the loop signals (min, max, mean, σ) in the side panel (desktop and web).
- Desktop: the mouse wheel no longer changes number fields and drop-down lists (the panel scrolls instead).
- Loop overview: a list of loops with the selected loop's settings one per row (instead of a wide table) on the web
  and in the desktop; loops are found also with suffixes after the role (".PV IP_ANALOGMAP") and, without tags,
  one loop is proposed from the column roles (CV / MV / SP); loop names keep the original tag spelling.
- Desktop: switching to APC no longer freezes the window – simulations of very slow processes are limited to a
  bounded number of steps (feedforward, gain scheduling, cascade, split range, VPC, ratio and the report).
- Live simulation (desktop and web): in AUTO the MV field is greyed out and shows the live MV, in MAN the SP field
  is greyed out; switching to MAN keeps the current MV (bumpless).
- Windows: the desktop application is a classic Windows application with its own icon – installer
  `PID-Tools-<version>-setup.exe` (current user, no admin rights, Start menu, uninstall in Settings) and portable
  ZIP with `PID Tools.exe`; the web app has its own offline package (`PID-Tools-<version>-web-win64-offline.zip`,
  with the OPC UA source). Application icon in the desktop window and the browser tab.
- Tuning: explanation of where SP, process input and PV (output) events act, in the scenario and the event editor.
- Live simulation pauses when another tab (or browser tab) is shown or the window is minimised.
- Several loops (web and desktop): a new loop gets its own name (Loop n) and opens on the Data tab to choose its
  signals; the loop can be renamed directly (web: ⋮ menu next to the loop switch, desktop: Rename loop).
- Desktop tuning: editing set 1 / 2 updates the scenario chart at once; TI and TD cannot be negative.
- Desktop diagnostics: nonlinearity chart (local gain vs. MV), verdict and a link to gain scheduling, as on the web.

## 3.1.0 – frequency analysis, loop overview, OPC UA, APC extensions

**Development**
- Offline package for Windows contains the desktop application (`PID-Tools-desktop.bat`, PySide6-Essentials).
- Fix: the gain sign options in the Model tab showed the gain-scheduling button text.
- Desktop application (preview, `python -m pidtools.desktop`, PySide6 + pyqtgraph): Data, Model, Tuning with the
  scenario and method comparison, model validation and uncertainty, live simulation, APC (cascade, feedforward,
  decoupling, override, Smith predictor, gain scheduling by PV and ER), operating diagnostics, several loops,
  projects interchangeable with the web app, tuning protocol export, help window with tab guides (content shared
  with the web app), autosave with restore on the next start, clickable APC recommendations.
- APC structure checklists computed in the shared layer – identical on the web and in the desktop.
- Desktop layout: every tab has the largest possible area for charts and data on the left and a settings panel
  on the right with collapsible sections (state and panel width are remembered); compact number fields.
- Desktop tuning: scenario first (default setpoint step; load or output disturbance, measured disturbance step,
  replay of measured disturbances, custom events), then the suggestion; nothing is computed until **Calculate (F5)**,
  changes mark the result as out of date; the suggestion is shown as a third curve before it is written to a set;
  the optimisation targets the scenario by default; tuning history with return to a set (saved in the project).
- Desktop charts: cursor with the values of all curves, two measuring cursors (Δt, ΔY), full range, PNG / CSV
  export, copy to clipboard, separate window (second monitor), hiding curves via the legend.
- Desktop: recent files, drag and drop of data and project files, Ctrl+1…7 tab shortcuts, remembered window size,
  keyboard shortcut overview in Help.
- Frequency analysis (Bode, Nyquist with the Ms circle, |S| and |T|, bandwidth) of set 1, set 2 and the suggestion –
  web and desktop.
- Closed-loop identification from data with the loop in AUTO (SP changes): indirect method simulating the whole
  loop with the controller from the record; the open-loop model is shown for comparison.
- Loop overview (tab 7): several loops from one file, ranking by problems, common oscillations and their source,
  opening a loop as a project loop.
- APC: split range, valve position control, ratio with cross-limiting, N×N interaction (RGA, Niederlinski index,
  recommended pairing).
- OPC UA (read only): browsing, history and live recording in the desktop; OPC UA data source in the local web.
- Web interface in the desktop layout: charts on the left, settings in collapsible sections on the right on every
  tab; tuning with scenario presets and Calculate; Model, Data with diagnostics, APC, live simulation and project.
- Application layer `pidtools/app` shared by all frontends (workflow, project format, protocol) – preparation for a
  desktop version for engineering stations; the web app is unchanged.
- APC page split into one module per structure.
- Deployment readiness: CI workflow with lint and tests on every push, user-supplied names escaped in HTML
  output, no Session State warnings in the web, the demo preselects its measured disturbance.

## 3.0.0 – first release for sharing within a team

**Data**
- Preview of loaded data, a time column per variable, long format (tag, time, value), time in ISO, Czech, US and
  European formats, PV / MV / SP role guessing from tag names.
- CSV encodings: UTF-8, UTF-16 (WinCC, Excel "Unicode text") and windows-1250; support for older `.xls` files.
- Safe switching between demo, file and project (settings are not reset, a model belongs to its data, the uploaded
  file is remembered).
- Controller range NormPV / NormMV moved to the PIDConL block in Tuning; warnings when the data lie outside the range
  or it is still the default 0–100; a range change only rescales the model.

**Tuning and simulation**
- Live simulation directly in the browser: smooth, comparison of sets, various disturbance shapes, noise and filter,
  process change, indicators, events, CSV / PNG export.
- "Set 2 without feedforward" comparison in the scenario; ConZone control zone in the PIDConL simulation.

**APC**
- Cascade, feedforward (moved from Tuning; gain in MV units for FFwd, simulation without / static / dynamic), 2×2
  decoupling (RGA, decouplers), override with external reset, Smith predictor (values for the SmithPredictorControl
  template), gain scheduling by PV and by control error.
- Structure recommendations from the models and couplings between loops, guides with implementation using APL
  templates.

**Project and protocol**
- Several loops in one project, one-click project save, autosave in the browser.
- Tuning protocol (HTML → PDF) for all loops: what to set in PCS 7, robustness, expected response, APC, sign-off.

**User interface and documentation**
- Native light / dark theme, guides in all tabs (collapsed by default), updated help with glossary and an *About*
  section (version, disclaimer, data handling).
- Documentation in `docs/` (user guide, methods, implementation in PCS 7, deployment; Czech version in `docs/cs`),
  new README.
- Operation: Streamlit telemetry off, developer options hidden, `Dockerfile` for an internal server, fixed
  devcontainer, bounded library versions.

## 2.0.0
- Identification of models with dead time and measured disturbances, PIDConL tuning (SIMC, iSIMC, Lambda, AMIGO,
  averaging, optimization), robustness, scenario simulation, diagnostics, project and report, Czech and English UI.
