# Changelog

## Unreleased

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
- Application layer `pidtools/app` shared by all frontends (workflow, project format, protocol) – preparation for a
  desktop version for engineering stations; the web app is unchanged.
- APC page split into one module per structure.

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
