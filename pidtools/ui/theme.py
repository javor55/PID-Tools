"""Vzhled: barvy, CSS a šablona grafů Plotly."""
import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

C_PV, C_SP, C_MV = "#1f5fa8", "#9aa5b1", "#c2410c"
C_DIST = ["#0f766e", "#7c3aed", "#a16207", "#334155"]
C_MODEL = {"P0D": "#94a3b8", "P1D": "#ea580c", "P2D": "#16a34a", "I0D": "#9333ea", "I1D": "#db2777"}
C_SET1, C_SET2, C_EDIT = "#64748b", "#15803d", "#111827"
FONT = "Inter, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"

CSS = """
<style>
.block-container {padding-top: 1.6rem; padding-bottom: 3rem; max-width: 1500px;}
h1 {font-weight: 650; letter-spacing: -0.01em; margin-bottom: 0.1rem;}
h4 {margin-top: 0.4rem; font-weight: 600;}
[data-testid="stMetric"] {background: #f4f7fb; border: 1px solid #e2e8f0; border-radius: 10px; padding: 0.55rem 0.9rem;}
[data-testid="stMetricLabel"] p {font-size: 0.82rem; color: #52606d;}
[data-testid="stMetricValue"] {font-size: 1.45rem; font-variant-numeric: tabular-nums;}
.stTabs [data-baseweb="tab-list"] {gap: 0.4rem;}
.stTabs [data-baseweb="tab"] {padding: 0.45rem 0.9rem; border-radius: 8px 8px 0 0;}
.pid-status {color: #52606d; font-size: 0.9rem; margin-bottom: 0.6rem;}
.pid-big {font-size: 0.8rem; color: #52606d;}
.pid-prog {display: flex; flex-wrap: wrap; gap: 0.4rem; align-items: center; margin: 0.2rem 0 0.3rem 0;}
.pid-chip {border-radius: 999px; padding: 0.18rem 0.7rem; font-size: 0.85rem; border: 1px solid; white-space: nowrap;}
.pid-chip.s0 {background: #ecfdf3; color: #166534; border-color: #bbf7d0;}
.pid-chip.s1 {background: #fffbeb; color: #92400e; border-color: #fde68a;}
.pid-chip.s2 {background: #fef2f2; color: #991b1b; border-color: #fecaca;}
.pid-chip.sn {background: #f8fafc; color: #64748b; border-color: #e2e8f0;}
.pid-arrow {color: #cbd5e1;}
.pid-next {color: #334155; font-size: 0.9rem; margin-bottom: 0.4rem;}
</style>"""


def apply_theme():
    """CSS do stránky a výchozí šablona grafů (šablona se registruje jen jednou)."""
    st.markdown(CSS, unsafe_allow_html=True)
    if "pidtuner" not in pio.templates:
        tpl = go.layout.Template(pio.templates["plotly_white"])
        tpl.layout.update(font=dict(family=FONT, size=12, color="#1f2933"), margin=dict(l=8, r=8, t=36, b=8),
                          hovermode="x unified", hoversubplots="axis", hoverlabel=dict(font=dict(family=FONT)),
                          legend=dict(orientation="h", yanchor="bottom", y=1.01, x=0, bgcolor="rgba(0,0,0,0)"))
        tpl.layout.xaxis.update(showspikes=True, spikemode="across", spikesnap="cursor", spikethickness=1,
                                spikecolor="#94a3b8", gridcolor="#eef2f6", zeroline=False)
        tpl.layout.yaxis.update(gridcolor="#eef2f6", zeroline=False)
        pio.templates["pidtuner"] = tpl
    if pio.templates.default != "pidtuner":
        pio.templates.default = "pidtuner"
