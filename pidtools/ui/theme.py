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


# ── CSS vlastních prvků ───────────────────────────────────────────────
# Barvy návrhu (světlé / tmavé téma). Plochy jsou bílé karty na šedém pozadí, panel nastavení vpravo má vlastní
# posuvník (roluje nezávisle na grafech).
_PALETTE = {
    "light": dict(bg="#eef1f5", card="#ffffff", side="#f6f8fa", line="#d7dde5", soft="#e5e9ef", text="#1f2933",
                  muted="#52606d", accent="#1f5fa8", accent_bg="#eaf2fb"),
    "dark": dict(bg="#0b1220", card="#111a2e", side="#0f172a", line="#26324a", soft="#1c2740", text="#e2e8f0",
                 muted="#94a3b8", accent="#60a5fa", accent_bg="rgba(96,165,250,0.12)"),
}

_CSS = """
<style>
:root {--pid-bg: %(bg)s; --pid-card: %(card)s; --pid-side: %(side)s; --pid-line: %(line)s; --pid-soft: %(soft)s;
    --pid-text: %(text)s; --pid-muted: %(muted)s; --pid-accent: %(accent)s; --pid-accent-bg: %(accent_bg)s;}
[data-testid="stApp"] {background: var(--pid-bg);}
/* Streamlit přes horní okraj kreslí průhlednou lištu – kliky propustit k hlavičce aplikace, kromě menu ⋮ */
[data-testid="stHeader"], [data-testid="stHeader"] [data-testid="stToolbar"] {background: transparent;
    pointer-events: none !important;}
[data-testid="stHeader"] [data-testid="stMainMenu"], [data-testid="stHeader"] [data-testid="stToolbarActions"] *
    {pointer-events: auto !important;}
.block-container {padding-top: 0.6rem; padding-bottom: 1rem; padding-left: 1.2rem; padding-right: 1.2rem;
    max-width: 100%%;}
code, [data-testid="stMetricValue"], [data-testid="stDataFrame"] {font-variant-numeric: tabular-nums;}
h1 {font-weight: 600; letter-spacing: -0.01em; margin: 0; padding: 0 !important; font-size: 1.45rem !important;}
h4 {margin-top: 0.4rem; font-weight: 600;}

/* hlavička */
.st-key-pid_header {background: var(--pid-card); border: 1px solid var(--pid-line); border-radius: 10px;
    padding: 0.5rem 3rem 0.5rem 0.9rem;}
.pid-sub {color: var(--pid-muted); font-size: 0.82rem;}

/* záložky: modré podtržení, „Projekt a report“ vpravo */
.stTabs [role="tablist"] {gap: 0.2rem;}
.stTabs [data-testid="stTab"] {padding: 0.6rem 0.85rem; color: var(--pid-muted);}
.stTabs [data-testid="stTab"] p {font-size: 0.93rem; font-weight: 500;}
.stTabs [data-testid="stTab"][aria-selected="true"] {color: var(--pid-accent);}
.stTabs [data-testid="stTab"][aria-selected="true"] p {font-weight: 600;}
.st-key-main_tab > div > [role="tablist"] {background: var(--pid-card); border: 1px solid var(--pid-line);
    border-radius: 10px; padding: 0 0.6rem; width: 100%%;}
.st-key-main_tab > div > [role="tablist"] > [data-testid="stTab"]:last-child {margin-left: auto;}

/* karty: sekce panelu a ohraničené kontejnery */
[data-testid="stExpander"] details {border-radius: 10px; border: 1px solid var(--pid-line); background: var(--pid-card);}
[data-testid="stExpander"] summary {background: transparent; border-radius: 10px; padding-top: 0.45rem;
    padding-bottom: 0.45rem; font-weight: 600;}
[data-testid="stExpander"] details[open] summary {border-radius: 10px 10px 0 0;}
[data-testid="stExpanderDetails"] {padding-top: 0.3rem;}
[data-testid="stVerticalBlockBorderWrapper"], .stVerticalBlock[data-testid="stVerticalBlock"][class*="st-key-pid_card"]
    {background: var(--pid-card); border-radius: 10px;}
[class*="st-key-pidside_"] [data-testid="stExpander"] p, [class*="st-key-pidside_"] [data-testid="stExpander"] label
    {font-size: 0.9rem;}

/* jen desktop (velké displeje, myš): jemnější a nižší pole i tlačítka v celé aplikaci */
[data-testid="stNumberInputContainer"], [data-baseweb="input"], [data-baseweb="select"] > div
    {min-height: 0; height: 2.15rem;}
[data-testid="stNumberInputContainer"] input, [data-baseweb="input"] input {padding-top: 0.2rem; padding-bottom: 0.2rem;}
[data-testid="stNumberInputContainer"] button {width: 1.6rem;}
.stButton button, .stDownloadButton button, [data-testid="stPopover"] button {min-height: 2.15rem; padding: 0.2rem 0.8rem;}
[data-testid="stButtonGroup"] button {min-height: 2rem; padding: 0.15rem 0.75rem;}
[data-testid="stWidgetLabel"] {min-height: 0; margin-bottom: 0.15rem;}
[data-testid="stCheckbox"] label {min-height: 0;}
[data-testid="stCheckbox"] label > span:first-child {width: 1rem; height: 1rem;}
[data-testid="stMainBlockContainer"] [data-testid="stVerticalBlock"] {gap: 0.65rem;}

/* panel nastavení vpravo: vlastní posuvník, rozbalit / sbalit vše */
[data-testid="stLayoutWrapper"]:has(> [class*="st-key-pidside_"]) {position: sticky; top: 0.5rem; align-self: flex-start;
    width: 100%%;}
[class*="st-key-pidside_"] {max-height: calc(100vh - 1rem); overflow-y: auto; overflow-x: hidden;
    padding: 0.2rem 0.45rem 1rem 0.2rem; background: var(--pid-side); border-left: 1px solid var(--pid-line);
    border-radius: 0 10px 10px 0;}
/* kompaktní panel (jako v návrhu): nižší pole, menší písmo a mezery, bez šipek u čísel */
[class*="st-key-pidside_"] [data-testid="stVerticalBlock"] {gap: 0.45rem;}
[class*="st-key-pidside_"] [data-testid="stExpanderDetails"] {padding: 0.15rem 0.85rem 0.75rem 0.85rem;}
[class*="st-key-pidside_"] [data-testid="stExpander"] summary {padding: 0.4rem 0.85rem; font-size: 0.9rem;}
[class*="st-key-pidside_"] [data-testid="stWidgetLabel"] {min-height: 0; margin-bottom: 0.1rem;}
[class*="st-key-pidside_"] [data-testid="stWidgetLabel"] p, [class*="st-key-pidside_"] [data-testid="stMarkdownContainer"] p
    {font-size: 0.82rem;}
[class*="st-key-pidside_"] [data-testid="stCaptionContainer"] p {font-size: 0.76rem; line-height: 1.35;}
[class*="st-key-pidside_"] [data-testid="stNumberInputContainer"], [class*="st-key-pidside_"] [data-baseweb="input"],
[class*="st-key-pidside_"] [data-baseweb="select"] > div {min-height: 0; height: 2rem;}
[class*="st-key-pidside_"] [data-testid="stNumberInputContainer"] input, [class*="st-key-pidside_"] [data-baseweb="input"] input,
[class*="st-key-pidside_"] [data-baseweb="select"] {font-size: 0.82rem; font-family: 'IBM Plex Mono', monospace;}
[class*="st-key-pidside_"] [data-testid="stNumberInputContainer"] button {display: none;}
[class*="st-key-pidside_"] [data-testid="stButtonGroup"] button {min-height: 1.9rem; padding: 0.1rem 0.7rem; font-size: 0.8rem;}
[class*="st-key-pidside_"] [data-testid="stButtonGroup"] button p {font-size: 0.8rem;}
[class*="st-key-pidside_"] .stButton button {min-height: 2rem; padding: 0.2rem 0.75rem;}
[class*="st-key-pidside_"] .stButton button p {font-size: 0.82rem;}
[class*="st-key-pidside_"] [data-testid="stCheckbox"] {min-height: 0;}
[class*="st-key-pidside_"] [data-testid="stHorizontalBlock"] {gap: 0.5rem; align-items: center;}
.pid-plab {font-size: 0.82rem; font-weight: 500; white-space: nowrap; display: flex; align-items: center; gap: 0.3rem;}
.pid-plab .q {display: inline-flex; width: 1.05rem; height: 1.05rem; border-radius: 50%%; border: 1px solid #9aa5b1;
    font-size: 0.68rem; font-weight: 600; align-items: center; justify-content: center; color: var(--pid-muted); cursor: help;}
.pid-unit {font-size: 0.76rem; color: var(--pid-muted); white-space: nowrap;}
.pid-src {font-size: 0.78rem; color: var(--pid-muted); margin: -0.2rem 0 0.2rem 0;}
.pid-side-tools {display: flex; justify-content: flex-end; gap: 0.8rem; font-size: 0.78rem; margin: 0 0.1rem 0.1rem 0;}
.pid-side-tools button {font: inherit; border: 0; background: transparent; color: var(--pid-accent); padding: 0;
    cursor: pointer;}

[data-testid="stMetric"] {background: var(--pid-card); border: 1px solid var(--pid-line); border-radius: 10px;
    padding: 0.55rem 0.9rem;}
[data-testid="stMetricLabel"] p {font-size: 0.82rem; color: var(--pid-muted);}
[data-testid="stMetricValue"] {font-size: 1.45rem; font-family: 'IBM Plex Mono', monospace;}
.pid-status {color: var(--pid-muted); font-size: 0.85rem; margin-bottom: 0.4rem;}
.pid-big {font-size: 0.8rem; opacity: 0.75;}
.pid-prog {display: flex; flex-wrap: wrap; gap: 0.4rem; align-items: center; margin: 0.2rem 0 0.3rem 0;}
.pid-chip {border-radius: 999px; padding: 0.18rem 0.7rem; font-size: 0.82rem; border: 1px solid; white-space: nowrap;}
.pid-chip.s0 {background: rgba(34,197,94,0.13); color: #2f6f3e; border-color: rgba(34,197,94,0.4);}
.pid-chip.s1 {background: rgba(234,179,8,0.15); color: #8a4b00; border-color: rgba(234,179,8,0.45);}
.pid-chip.s2 {background: rgba(239,68,68,0.13); color: #b91c1c; border-color: rgba(239,68,68,0.4);}
.pid-chip.sn {background: rgba(128,128,128,0.08); color: var(--pid-muted); border-color: rgba(128,128,128,0.3);}
.pid-arrow {opacity: 0.4;}
.pid-formula {font-family: 'IBM Plex Mono', monospace; font-size: 0.85rem; padding: 0.35rem 0.6rem; border-radius: 6px;
    background: var(--pid-side); border: 1px solid var(--pid-soft); margin-bottom: 0.5rem;}
.pid-dq {display: grid; grid-template-columns: 1.6rem minmax(9rem, 14rem) minmax(0, 1fr); gap: 0.2rem 0.8rem;
    align-items: start; padding: 0.45rem 0; border-bottom: 1px solid var(--pid-soft); font-size: 0.88rem;}
.pid-dq:last-child {border-bottom: 0;}
.pid-dq-ic {width: 1.25rem; height: 1.25rem; border-radius: 50%%; border: 1px solid; font-size: 0.75rem; font-weight: 600;
    display: inline-flex; align-items: center; justify-content: center;}
.pid-dq-n {font-weight: 500;}
.pid-dq-r {font-family: 'IBM Plex Mono', monospace; font-size: 0.82rem;}
.pid-dq-w {display: block; color: var(--pid-muted); font-size: 0.8rem; margin-top: 0.1rem;}
.pid-next {opacity: 0.85; font-size: 0.9rem; margin-bottom: 0.4rem;}
</style>"""


def palette():
    """Barvy návrhu pro aktuální téma Streamlitu (světlé / tmavé)."""
    try:
        kind = st.context.theme.type or "light"
    except Exception:
        kind = "light"
    return _PALETTE.get(kind, _PALETTE["light"])


# ── Šablony grafů ─────────────────────────────────────────────────────
def plotly_template():
    """Šablona grafů v aplikaci: šablona „streamlit“ (barvy doplní prohlížeč podle tématu) + rozvržení."""
    if "pidtuner" not in pio.templates:
        base = pio.templates["streamlit"] if "streamlit" in pio.templates else pio.templates["plotly_white"]
        pio.templates["pidtuner"] = _layout(go.layout.Template(base))
    return pio.templates["pidtuner"]


def apply_theme():
    """CSS vlastních prvků do stránky (barvy podle tématu)."""
    st.markdown(_CSS % palette(), unsafe_allow_html=True)
