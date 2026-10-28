# Architecture

PID Tools is split into three layers. The aim is that the same computations and the same workflow can be used
by more than one frontend – today the Streamlit web app, later a desktop application for engineering stations.

A plan to replace both frontends with one TypeScript UI over a Python API (web and fully offline desktop) is in
[docs/cs/plan-jednotne-ui.md](cs/plan-jednotne-ui.md) (Czech), milestones in [docs/cs/milniky.md](cs/milniky.md).

```
frontend   pidtools/ui (Streamlit, web)   pidtools/desktop (Qt, engineering station)
              │                                   │
application   pidtools/app  – workflow, project format, report      (no UI framework)
              │
core          pidtools/core – identification, tuning, simulation, APC  (numpy / scipy)
```

## Rules

- `core` knows nothing about the application: it works in % of the controller ranges (NormPV, NormMV), with arrays
  and plain dictionaries.
- `app` holds everything a frontend would otherwise have to re-implement: unit scaling, the PIDConL block
  configuration and parameter sets, identification settings and rescaling, tuning proposals and comparison,
  the scenario, feedforward, the APC structures, the project file and the protocol. Functions take explicit
  arguments (no session state) and return plain data.
- Expensive calls (identification, optimizations, simulations) are passed in as parameters where a frontend wants
  to cache them – e.g. `app.tuning.suggest(..., solvers=...)`, `app.model.identify(..., fn=...)`. The web app
  passes `st.cache_data` wrappers from `ui/cache.py`; a desktop app can use its own cache or none.
- `i18n.T()` has no UI dependency: the web app registers a language provider (session state), a desktop app calls
  `i18n.set_lang()`.
- `app.report` and `app.plots` use Plotly (the protocol is an HTML file with Plotly charts); the rest of `app`,
  `core` and `i18n` must import without Streamlit, Plotly or Qt (`tests/test_app_layer.py`).
- The project file (`app.project`) is shared – a project saved in one frontend opens in the other.
- `pidtools/api` (FastAPI, `requirements-api.txt`) wraps the workspace for the future single UI. It listens on
  127.0.0.1 with a token for the desktop. `openapi.json` next to it is generated
  (`python -m pidtools.api --openapi pidtools/api/openapi.json`) and checked by a test.
- `pidtools/api/sidecar.py` runs the API as a standalone program for the Tauri window (`--port 0 --token --parent-pid`,
  one `PIDTOOLS_READY {json}` line on stdout, exits with its parent, `--smoke` self-test). `tools/build_sidecar.py`
  packs it with PyInstaller (onedir, no Qt / Streamlit, named `pidtools-api-<target triple>`); CI: `sidecar.yml`.
- `frontend/` (React + TypeScript, Vite) is the future single UI over the API. `npm run build` writes it to
  `pidtools/api/ui`, which the API serves at `/`. Types come from `openapi.json`, and CI builds and tests it.
  See `frontend/README.md`.
- Long computations for the API run as jobs (`app.jobs`): one process per job, progress, cancel, timeout and a
  result cache by input key.
- Golden cases (`tools/golden.py`, `tests/golden/`, checked by `tests/test_golden.py`) hold the results of the
  whole workflow on a fixed data set. A deliberate change of results is regenerated with
  `python tools/golden.py --update` and explained in the PR.

## Web frontend (`pidtools/ui`)

Streamlit reruns the script on every interaction. `ui/context.py` (`Ctx`) carries the data of one run between the
tabs; widget state lives in the session state, several loops are snapshots of it (`ui/loops.py`). Pages read
widgets, call `app` and draw the results. The live simulation runs in the browser (`ui/static/live_engine.js`, a
port of `core/simulation.py`, checked against it by `tests/test_live_js.py`). Every tab uses the same layout as
the desktop: `ui/layout.workspace()` splits it into the main area and the settings panel, `ui/layout.section()`
adds a collapsible section whose state Streamlit keeps by key.

Shared modules added for both frontends: `app.frequency` (Bode, Nyquist, sensitivity), `app.closedloop`
(identification with the loop in AUTO), `app.audit` (loop overview), `app.apc.splitrange`, `app.apc.vpc`,
`app.apc.ratio`, `app.apc.rgan` and `app.opc` (OPC UA, read only; optional dependency `asyncua`, part of
`requirements-desktop.txt`, so the cloud deployment is unchanged).

## Desktop frontend (`pidtools/desktop`)

The state lives in the application layer, **`pidtools.app.workspace`**:
- `Workspace` holds one loop: data, columns, ranges, identification segment, models, PIDConL block, parameter sets,
  scenario and diagnostics.
- Its settings are a `settings` dictionary with the same keys as the web app, so projects are interchangeable.
- It is split by area into mixins: `data`, `ident`, `tuning`, `analysis` and `project`.
- `workspace.loops.Project` holds the loops of a project over one data file.

Both have no UI dependency. They are used by the desktop (`desktop/state.py` `LoopState` and `desktop/project.py`
are aliases), by the golden cases and later by the API. The windows (`main.py`, `tabs/`) only read and change the
state; identification and optimizations run in a background thread (`widgets.run_task`). Charts use
pyqtgraph. Start: `python -m pidtools.desktop`.

Every tab is a `layout.Workspace`: the main area on the left (`main` – charts, tables) and a settings panel on the
right (`section()` adds a collapsible `layout.Section`; expanded state and panel width are stored in `QSettings`).
Charts are `chartbox.ChartBox` (one or more plots with a shared time axis, cursor read-out, measuring cursors,
PNG / CSV export, detachable window); `widgets.plot()` and `widgets.stack()` create them.

## Deployment

Streamlit Community Cloud deploys `app.py` from the repository and installs `requirements.txt`. Desktop-only
dependencies (Qt) belong to a separate requirements file so the cloud deployment stays unchanged.
