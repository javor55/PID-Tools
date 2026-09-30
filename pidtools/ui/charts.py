"""Grafy: tvorba obrázků, zředění dlouhých průběhů, zobrazení a sběr grafů/tabulek pro report."""
import numpy as np
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

# obsah reportu sbíraný během jednoho běhu aplikace (nuluje se v app.py)
REPORT = {"figs": [], "tables": [], "notes": []}


def reset_report():
    REPORT.clear()
    REPORT.update({"figs": [], "tables": [], "notes": []})


def mkfig(n_rows, heights=None):
    return make_subplots(rows=n_rows, cols=1, shared_xaxes=True, vertical_spacing=0.035,
                         row_heights=heights or [1 / n_rows] * n_rows)


def decimate(x, y, n=4000):
    """Min-max zředění pro vykreslení: max. ~n bodů, špičky zůstanou zachované."""
    x, y = np.asarray(x), np.asarray(y, float)
    if len(x) <= n or not np.all(np.isfinite(y)):
        return x, y
    k = int(np.ceil(len(x) / (n / 2)))
    m = len(x) // k * k
    xr, yr = x[:m].reshape(-1, k), y[:m].reshape(-1, k)
    rows = np.arange(len(xr))
    i1, i2 = np.argmin(yr, 1), np.argmax(yr, 1)
    a, b = np.minimum(i1, i2), np.maximum(i1, i2)
    xs = np.column_stack([xr[rows, a], xr[rows, b]]).ravel()
    ys = np.column_stack([yr[rows, a], yr[rows, b]]).ravel()
    return np.r_[xs, x[m:]], np.r_[ys, y[m:]]


def tr(x, y, name, color, width=1.6, dash=None, shape=None, show=True, group=None, opacity=1.0):
    """Čárová stopa (u dlouhých průběhů zředěná a ve WebGL)."""
    x, y = decimate(x, y)
    cls = go.Scattergl if len(x) > 4000 else go.Scatter
    return cls(x=x, y=y, name=name, mode="lines", opacity=opacity, showlegend=show,
               legendgroup=group or name,
               line=dict(color=color, width=width, dash=dash, shape=shape or "linear"))


def style(fig, height, ytitles=(), xtitle=None, rev="keep"):
    """Výška, popisy os a uirevision (zachová přiblížení při změně parametrů)."""
    fig.update_layout(height=height, uirevision=rev)
    for i, t in enumerate(ytitles):
        fig.update_yaxes(title_text=t, row=i + 1, col=1)
    if xtitle and ytitles:
        fig.update_xaxes(title_text=xtitle, row=len(ytitles), col=1)
    elif xtitle:
        fig.update_xaxes(title_text=xtitle)
    return fig


def show(fig, key=None, fname="chart", select=False, report=None):
    """Zobrazí graf; s `report` ho zároveň zařadí do reportu."""
    if report:
        REPORT["figs"].append((report, fig))
    cfg = {"displaylogo": False, "modeBarButtonsToRemove": ["lasso2d", "autoScale2d"],
           "toImageButtonOptions": {"format": "png", "scale": 2, "filename": fname}}
    if select:
        return st.plotly_chart(fig, width="stretch", config=cfg, key=key, on_select="rerun", selection_mode="box")
    return st.plotly_chart(fig, width="stretch", config=cfg, key=key)
