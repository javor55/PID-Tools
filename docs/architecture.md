# Architecture

PID Tools is split into three layers. The aim is that the same computations and the same workflow can be used
by more than one frontend – today the Streamlit web app, later a desktop application for engineering stations.

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

## Web frontend (`pidtools/ui`)

Streamlit reruns the script on every interaction. `ui/context.py` (`Ctx`) carries the data of one run between the
tabs; widget state lives in the session state, several loops are snapshots of it (`ui/loops.py`). Pages read
widgets, call `app` and draw the results. The live simulation runs in the browser (`ui/static/live_engine.js`, a
port of `core/simulation.py`, checked against it by `tests/test_live_js.py`).

## Desktop frontend (`pidtools/desktop`)

`state.py` (`LoopState`) holds one loop – data, columns, ranges, identification segment, models, PIDConL block,
parameter sets, scenario – in a `settings` dictionary with the same keys as the web app, so projects are
interchangeable. It has no Qt dependency and is tested on its own. The windows (`main.py`, `tabs/`) only read and
change the state; identification and optimizations run in a background thread (`widgets.run_task`). Charts use
pyqtgraph. Start: `python -m pidtools.desktop`.

## Deployment

Streamlit Community Cloud deploys `app.py` from the repository and installs `requirements.txt`. Desktop-only
dependencies (Qt) belong to a separate requirements file so the cloud deployment stays unchanged.
