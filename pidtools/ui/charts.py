"""Grafy: tvorba obrázků, zředění dlouhých průběhů, zobrazení a sběr grafů/tabulek pro report."""
import threading

import streamlit as st

from ..app.plots import decimate, mkfig, style, tr  # noqa: F401
from .theme import plotly_template

# Stav jednoho běhu skriptu. Každá relace Streamlitu běží ve vlastním vlákně, proto thread-local
# (globální slovník by se mezi současně připojenými uživateli míchal).
_run = threading.local()


class _Report:
    """Obsah reportu sbíraný během jednoho běhu aplikace (nuluje se v app.py); chová se jako slovník."""

    def _d(self):
        if not hasattr(_run, "report"):
            _run.report = {"figs": [], "tables": [], "notes": []}
        return _run.report

    def __getitem__(self, k):
        return self._d()[k]

    def __setitem__(self, k, v):
        self._d()[k] = v

    def __contains__(self, k):
        return k in self._d()

    def get(self, k, default=None):
        return self._d().get(k, default)


REPORT = _Report()


def reset_report():
    _run.report = {"figs": [], "tables": [], "notes": []}
    _run.visible = [True]


class Page:
    """Obal záložky: grafy uvnitř neaktivní záložky se neodesílají do prohlížeče (výpočty běží dál)."""

    def __init__(self, tab):
        self.tab = tab

    def __enter__(self):
        _visible().append(self.tab.open is not False)
        return self.tab.__enter__()

    def __exit__(self, *exc):
        _visible().pop()
        return self.tab.__exit__(*exc)

    @property
    def open(self):
        return self.tab.open is not False


def _visible():
    if not hasattr(_run, "visible"):
        _run.visible = [True]
    return _run.visible


TIME_UNITS = ("auto", "s", "min", "h")


def _mark_time(fig):
    """Osa x v čase (popis „čas [s]“ / „zpoždění [s]“) → layout.meta.pt.time: popisky přepočítá chart_tools.js."""
    from ..i18n import T
    names = {T("time_s"), T("lag_s")}
    for k in fig.layout:
        if k.startswith("xaxis") and fig.layout[k].title.text in names:
            meta = fig.layout.meta if isinstance(fig.layout.meta, dict) else {}
            fig.layout.meta = dict(meta, pt=dict(time=True))
            return


def tools():
    """Nástroje grafů na stránce (časová osa v s / min / h, měřicí kurzory) – jednou za běh."""
    from ..i18n import T
    from .widgets import static_asset, v2_component
    comp = v2_component("pidtools_chart_tools", js=static_asset("chart_tools.js"))
    comp(key="chart_tools", data=dict(unit=st.session_state.get("chart_tunit") or "auto",
                                      txt=dict(measure=T("dk_chb_measure"), measure_tip=T("dk_ch_measure"))))


def show(fig, key=None, fname="chart", select=False, report=None):
    """Zobrazí graf; s `report` ho zároveň zařadí do reportu."""
    fig.layout.template = plotly_template()
    _mark_time(fig)
    if report:
        REPORT["figs"].append((report, fig))
    if not _visible()[-1]:
        return None
    cfg = {"displaylogo": False, "modeBarButtonsToRemove": ["lasso2d", "autoScale2d"],
           "toImageButtonOptions": {"format": "png", "scale": 2, "filename": fname}}
    if select:
        return st.plotly_chart(fig, width="stretch", config=cfg, key=key, on_select="rerun", selection_mode="box")
    return st.plotly_chart(fig, width="stretch", config=cfg, key=key)
