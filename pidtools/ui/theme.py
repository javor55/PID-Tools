"""
Vzhled: barvy stop, drobné CSS a šablony grafů Plotly.

Světlé a tmavé téma řeší Streamlit nativně (barvy v `.streamlit/config.toml`, přepínání v menu ⋮ → Settings).
Aplikace proto nepotřebuje vědět, které téma je aktivní:
  – CSS vlastních prvků používá poloprůhledné barvy, které fungují na obou pozadích,
  – grafy vycházejí ze šablony „streamlit“, jejíž barvy (pozadí, písmo, mřížka) doplní prohlížeč podle tématu,
  – barvy stop jsou zvolené tak, aby byly čitelné na světlém i tmavém pozadí.
"""
import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

from ..app.plots import (C_DIST, C_EDIT, C_MODEL, C_MV, C_PV, C_SET1, C_SET2, C_SP, FONT, _layout,  # noqa: F401
                         report_template)


def _c_dist():
    """Barvy měřených poruch."""
    return C_DIST


def _c_edit():
    """Barva ručně upraveného modelu."""
    return C_EDIT


# ── CSS vlastních prvků (nezávislé na tématu) ─────────────────────────
_CSS = """
<style>
.block-container {padding-top: 1.2rem; padding-bottom: 2rem; padding-left: 1.2rem; padding-right: 1.2rem;
    max-width: 100%;}
[data-testid="stExpander"] details {border-radius: 6px; border-color: rgba(128,128,128,0.25);}
[data-testid="stExpander"] summary {background: rgba(128,128,128,0.10); border-radius: 6px; padding-top: 0.35rem;
    padding-bottom: 0.35rem; font-weight: 600;}
[data-testid="stExpander"] details[open] summary {border-radius: 6px 6px 0 0;}
[data-testid="stExpanderDetails"] {padding-top: 0.5rem;}
[data-testid="stColumn"] [data-testid="stExpander"] p, [data-testid="stColumn"] [data-testid="stExpander"] label
    {font-size: 0.9rem;}
h1 {font-weight: 650; letter-spacing: -0.01em; margin-bottom: 0.1rem;}
h4 {margin-top: 0.4rem; font-weight: 600;}
[data-testid="stMetric"] {background: rgba(128,128,128,0.06); border: 1px solid rgba(128,128,128,0.22);
    border-radius: 10px; padding: 0.55rem 0.9rem;}
[data-testid="stMetricLabel"] p {font-size: 0.82rem; opacity: 0.75;}
[data-testid="stMetricValue"] {font-size: 1.45rem; font-variant-numeric: tabular-nums;}
.stTabs [data-baseweb="tab-list"] {gap: 0.35rem; border-bottom: 2px solid rgba(128,128,128,0.22);}
.stTabs [data-baseweb="tab"] {padding: 0.6rem 1.2rem; border-radius: 8px 8px 0 0; font-size: 0.95rem;
    font-weight: 500; letter-spacing: 0.01em;}
.stTabs [data-baseweb="tab"][aria-selected="true"] {font-weight: 650; background: rgba(128,128,128,0.08);}
.pid-status {opacity: 0.75; font-size: 0.9rem; margin-bottom: 0.6rem;}
.pid-big {font-size: 0.8rem; opacity: 0.75;}
.pid-prog {display: flex; flex-wrap: wrap; gap: 0.4rem; align-items: center; margin: 0.2rem 0 0.3rem 0;}
.pid-chip {border-radius: 999px; padding: 0.18rem 0.7rem; font-size: 0.85rem; border: 1px solid; white-space: nowrap;}
.pid-chip.s0 {background: rgba(34,197,94,0.13); color: #16a34a; border-color: rgba(34,197,94,0.4);}
.pid-chip.s1 {background: rgba(234,179,8,0.15); color: #ca8a04; border-color: rgba(234,179,8,0.45);}
.pid-chip.s2 {background: rgba(239,68,68,0.13); color: #dc2626; border-color: rgba(239,68,68,0.4);}
.pid-chip.sn {background: rgba(128,128,128,0.08); opacity: 0.75; border-color: rgba(128,128,128,0.3);}
.pid-arrow {opacity: 0.4;}
.pid-next {opacity: 0.85; font-size: 0.9rem; margin-bottom: 0.4rem;}
</style>"""


# ── Šablony grafů ─────────────────────────────────────────────────────
def plotly_template():
    """Šablona grafů v aplikaci: šablona „streamlit“ (barvy doplní prohlížeč podle tématu) + rozvržení."""
    if "pidtuner" not in pio.templates:
        base = pio.templates["streamlit"] if "streamlit" in pio.templates else pio.templates["plotly_white"]
        pio.templates["pidtuner"] = _layout(go.layout.Template(base))
    return pio.templates["pidtuner"]


def apply_theme():
    """CSS vlastních prvků do stránky."""
    st.markdown(_CSS, unsafe_allow_html=True)
