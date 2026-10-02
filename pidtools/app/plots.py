"""
Grafy Plotly bez vazby na UI: barvy stop, společné rozvržení, šablona reportu, zředění dlouhých průběhů,
tvorba obrázků. Používá je webová aplikace (pidtools.ui) i protokol (pidtools.app.report).
"""
import numpy as np
import plotly.graph_objects as go
import plotly.io as pio
from plotly.subplots import make_subplots

# ── Barvy stop (grafy) – čitelné na světlém i tmavém pozadí ──────────
C_PV, C_SP, C_MV = "#1f5fa8", "#9aa5b1", "#c2410c"
C_MODEL = {"P0D": "#94a3b8", "P1D": "#ea580c", "P2D": "#16a34a", "I0D": "#9333ea", "I1D": "#db2777"}
C_SET1, C_SET2 = "#64748b", "#15803d"
C_DIST = ["#0d9488", "#8b5cf6", "#ca8a04", "#64748b"]
C_EDIT = "#0891b2"
FONT = "Inter, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"


def _layout(tpl):
    """Společné rozvržení grafů (bez barev pozadí, písma a mřížky – ty určuje téma)."""
    tpl.layout.update(
        font=dict(family=FONT, size=12),
        margin=dict(l=8, r=8, t=36, b=8),
        hovermode="x unified", hoversubplots="axis",
        hoverlabel=dict(font=dict(family=FONT)),
        legend=dict(orientation="h", yanchor="bottom", y=1.01, x=0, bgcolor="rgba(0,0,0,0)"),
    )
    tpl.layout.xaxis.update(showspikes=True, spikemode="across", spikesnap="cursor", spikethickness=1,
                            zeroline=False)
    tpl.layout.yaxis.update(zeroline=False)
    return tpl


def report_template():
    """Šablona grafů v HTML reportu (samostatný soubor bez Streamlitu → pevné světlé barvy)."""
    if "pidtuner_report" not in pio.templates:
        tpl = _layout(go.layout.Template(pio.templates["plotly_white"]))
        tpl.layout.update(font=dict(color="#1f2933"), paper_bgcolor="#ffffff", plot_bgcolor="#ffffff")
        tpl.layout.xaxis.update(gridcolor="#f0f0f0", spikecolor="#94a3b8")
        tpl.layout.yaxis.update(gridcolor="#f0f0f0")
        pio.templates["pidtuner_report"] = tpl
    return pio.templates["pidtuner_report"]


def mkfig(n_rows, heights=None):
    return make_subplots(rows=n_rows, cols=1, shared_xaxes=True, vertical_spacing=0.035,
                         row_heights=heights or [1 / n_rows] * n_rows)


def _short(a):
    """Zaokrouhlení na ~6 platných číslic (vůči maximu) – kratší JSON pro prohlížeč, na grafu nepoznatelné."""
    a = np.asarray(a)
    if a.dtype.kind != "f" or not len(a):
        return a
    m = np.nanmax(np.abs(a)) if np.any(np.isfinite(a)) else 0.0
    if not np.isfinite(m) or m == 0:
        return a
    return np.round(a, int(np.clip(5 - np.floor(np.log10(m)), 0, 15)))


def decimate(x, y, n=2000):
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
    return cls(x=_short(x), y=_short(y), name=name, mode="lines", opacity=opacity, showlegend=show,
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
