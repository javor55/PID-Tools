"""
Grafy Plotly bez vazby na UI: barvy stop, společné rozvržení, šablona reportu, zředění dlouhých průběhů,
tvorba obrázků. Používá je webová aplikace (pidtools.ui) i protokol (pidtools.app.report).
"""
import numpy as np
import plotly.graph_objects as go
import plotly.io as pio
from plotly.subplots import make_subplots

# ── Barvy stop (grafy) – čitelné na světlém i tmavém pozadí ──────────
from .colors import C_DIST, C_EDIT, C_MODEL, C_MV, C_PV, C_SET1, C_SET2, C_SP  # noqa: E402,F401
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
    if len(x) <= n:
        return x, y
    k = int(np.ceil(len(x) / (n / 2)))
    m = len(x) // k * k
    xr, yr = x[:m].reshape(-1, k), y[:m].reshape(-1, k)
    rows = np.arange(len(xr))
    fin = np.isfinite(yr)              # mezery (NaN) zůstanou mezerami: blok bez hodnot dá NaN, jinak min/max hodnot
    i1 = np.argmin(np.where(fin, yr, np.inf), 1)
    i2 = np.argmax(np.where(fin, yr, -np.inf), 1)
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


C_SUG = "#9333ea"


def freq_figs(res, sets, height=620):
    """
    Frekvenční analýza (web, protokol): (Bode – |L| a ∠L, Nyquist s kružnicí Ms, citlivost |S| a |T|).
    res = app.frequency.compare(...), sets = [(název, barva, čárkovaně)].
    """
    from . import frequency as fq
    from ..i18n import T
    bode = mkfig(2, [0.5, 0.5])
    nyq = go.Figure()
    sens = go.Figure()
    cx, cy = fq.ms_circle()
    nyq.add_trace(go.Scatter(x=cx, y=cy, mode="lines", name=f"Ms = {fq.MS_TARGET}",
                             line=dict(color="#f59e0b", dash="dash", width=1.2)))
    ux, uy = fq.ms_circle(1.0)
    nyq.add_trace(go.Scatter(x=ux, y=uy, mode="lines", showlegend=False, line=dict(color="#d1d5db", width=1)))
    nyq.add_trace(go.Scatter(x=[-1], y=[0], mode="markers", showlegend=False,
                             marker=dict(symbol="cross-thin", size=14, line=dict(color="#dc2626", width=2))))
    for name, col, dash in sets:
        r = res[name]
        d = "dot" if dash else None
        bode.add_trace(go.Scatter(x=r["w"], y=r["mag_db"], name=name, legendgroup=name, line=dict(color=col, dash=d)), 1, 1)
        bode.add_trace(go.Scatter(x=r["w"], y=r["phase_deg"], name=name, legendgroup=name, showlegend=False,
                                  line=dict(color=col, dash=d)), 2, 1)
        L = r["L"]
        k = np.abs(L) < 6
        nyq.add_trace(go.Scatter(x=L.real[k], y=L.imag[k], name=name, line=dict(color=col, dash=d)))
        sens.add_trace(go.Scatter(x=r["w"], y=fq.db(r["S"]), name=f"|S| {name}", legendgroup=name,
                                  line=dict(color=col, dash=d, width=2)))
        sens.add_trace(go.Scatter(x=r["w"], y=fq.db(r["T"]), name=f"|T| {name}", legendgroup=name,
                                  line=dict(color=col, dash="dash", width=1)))
    bode.add_hline(y=0, line=dict(color="#9ca3af", dash="dash", width=1), row=1, col=1)
    bode.add_hline(y=-180, line=dict(color="#9ca3af", dash="dash", width=1), row=2, col=1)
    bode.update_xaxes(type="log")
    style(bode, height, [T("fq_mag"), T("fq_phase")], T("fq_w"), rev="bode")
    bode.update_layout(hovermode="x unified")
    bode.update_yaxes(range=[fq.phase_floor(res), 30], row=2, col=1)
    nyq.update_layout(height=height * 0.62, uirevision="nyq", hovermode="closest",
                      xaxis=dict(range=[-2.5, 1.0], title="Re L"),
                      yaxis=dict(range=[-2.0, 1.5], title="Im L", scaleanchor="x", scaleratio=1))
    sens.update_xaxes(type="log", title=T("fq_w"))
    sens.update_layout(height=height * 0.62, yaxis_title="dB", uirevision="sens",
                       hovermode="x unified")
    return bode, nyq, sens


def freq_table(res, names):
    """Tabulka rezerv: [(název, Ms, GM, PM, ωc, ω180, šířka pásma, 2π/ω_bw, stabilní)]."""
    from . import frequency as fq
    rows = []
    for n in names:
        r = res[n]
        bw = fq.bandwidth(r)
        rows.append((n, r["Ms"], r["GM"], r["PM"], r["wc"], r["w180"], bw, 2 * np.pi / bw if bw else None, r["stable"]))
    return rows
