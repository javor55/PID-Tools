"""Vzhled: barvy, CSS a šablona grafů Plotly.  Podporuje světlý i tmavý režim."""
import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

# ── Barvy stop (grafy) – shodné pro oba režimy ──────────────────────
C_PV, C_SP, C_MV = "#1f5fa8", "#9aa5b1", "#c2410c"
C_MODEL = {"P0D": "#94a3b8", "P1D": "#ea580c", "P2D": "#16a34a", "I0D": "#9333ea", "I1D": "#db2777"}
C_SET1, C_SET2 = "#64748b", "#15803d"
FONT = "Inter, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"

# Barvy, které na tmavém pozadí nefungují – vracejí se přes funkce:
C_DIST_BASE = ["#0f766e", "#7c3aed", "#a16207", "#334155"]
C_DIST_DARK = ["#2dd4bf", "#a78bfa", "#eab308", "#94a3b8"]
C_EDIT_LIGHT, C_EDIT_DARK = "#111827", "#e2e8f0"

# Zpětná kompatibilita – moduly, které neimportují _c_dist/_c_edit, dostanou výchozí (light).
C_DIST = C_DIST_BASE
C_EDIT = C_EDIT_LIGHT


def is_dark():
    """Vrací True, pokud je aktivní tmavý režim."""
    return st.session_state.get("theme", "light") == "dark"


def _c_dist():
    """Barvy poruchových veličin – theme-aware."""
    return C_DIST_DARK if is_dark() else C_DIST_BASE


def _c_edit():
    """Barva editované křivky – theme-aware."""
    return C_EDIT_DARK if is_dark() else C_EDIT_LIGHT


# ── Barvy přizpůsobené tmavému / světlému režimu ────────────────────
def _t(light, dark):
    """Vrátí barvu podle aktuálního tématu."""
    return dark if is_dark() else light


# ── CSS pro tmavý režim Streamlitu ──────────────────────────────────
_DARK_OVERRIDES = """
/* ── Streamlit dark-mode overrides ──────────────────────────────── */
:root, [data-testid="stAppViewContainer"], .stApp {
    --primary-color: #60a5fa;
    --background-color: #0f172a;
    --secondary-background-color: #1e293b;
    --text-color: #e2e8f0;
    color-scheme: dark;
}
.stApp, [data-testid="stAppViewContainer"] {
    background-color: #0f172a !important;
    color: #e2e8f0 !important;
}
[data-testid="stHeader"] {
    background-color: rgba(15,23,42,0.85) !important;
    backdrop-filter: blur(8px);
}
[data-testid="stSidebar"] {
    background-color: #1e293b !important;
}
/* Texty */
.stMarkdown, .stMarkdown p, .stMarkdown li, .stMarkdown span,
label, .stTextInput label, .stNumberInput label, .stSelectbox label,
.stRadio label, .stCheckbox label, .stSlider label,
[data-testid="stWidgetLabel"], [data-testid="stMarkdownContainer"],
[data-testid="stMarkdownContainer"] p {
    color: #e2e8f0 !important;
}
h1, h2, h3, h4, h5, h6 { color: #f1f5f9 !important; }
/* Kontejnery s rámečkem */
[data-testid="stVerticalBlock"] > div[data-testid="element-container"] > div[data-testid="stHorizontalBlock"],
div[data-testid="stExpander"],
.stTabs [data-baseweb="tab-panel"] {
    background-color: transparent;
}
div.stContainer > div[style*="border"] {
    border-color: #334155 !important;
}
/* Vstupní pole, selectboxy */
[data-baseweb="input"] input,
[data-baseweb="textarea"] textarea {
    background-color: #1e293b !important;
    color: #e2e8f0 !important;
    border-color: #334155 !important;
}
[data-baseweb="select"] > div {
    background-color: #1e293b !important;
    color: #e2e8f0 !important;
    border-color: #334155 !important;
}
[data-baseweb="popover"] > div {
    background-color: #1e293b !important;
    color: #e2e8f0 !important;
}
[data-baseweb="menu"] {
    background-color: #1e293b !important;
}
[data-baseweb="menu"] li {
    color: #e2e8f0 !important;
}
[data-baseweb="menu"] li:hover {
    background-color: #334155 !important;
}
/* Taby */
.stTabs [data-baseweb="tab-list"] {
    background-color: transparent;
    border-bottom-color: #334155;
}
.stTabs [data-baseweb="tab"] {
    color: #94a3b8 !important;
}
.stTabs [data-baseweb="tab"][aria-selected="true"] {
    color: #e2e8f0 !important;
}
/* Tlačítka */
.stButton > button,
[data-testid="stBaseButton-secondary"] {
    background-color: #1e293b !important;
    color: #e2e8f0 !important;
    border-color: #334155 !important;
}
[data-testid="stBaseButton-primary"] {
    background-color: #2563eb !important;
    color: #ffffff !important;
    border-color: #2563eb !important;
}
/* Popover */
[data-testid="stPopover"] > div {
    background-color: #1e293b !important;
    border-color: #334155 !important;
}
/* Alerty */
[data-testid="stAlert"] {
    background-color: #1e293b !important;
    color: #e2e8f0 !important;
}
/* Kontejner s rámečkem (st.container(border=True)) */
[data-testid="stVerticalBlockBorderWrapper"] {
    border-color: #334155 !important;
    background-color: rgba(30,41,59,0.5) !important;
}
/* File uploader */
[data-testid="stFileUploader"] section {
    background-color: #1e293b !important;
    border-color: #334155 !important;
}
[data-testid="stFileUploader"] section small {
    color: #94a3b8 !important;
}
/* Slider */
[data-testid="stSlider"] [data-baseweb="slider"] div[role="slider"] {
    background-color: #60a5fa !important;
}
/* Caption */
.stCaption, [data-testid="stCaptionContainer"] {
    color: #94a3b8 !important;
}
/* Toggle */
[data-testid="stToggle"] label span {
    color: #e2e8f0 !important;
}
/* Dataframe / Table */
[data-testid="stDataFrame"] {
    border-color: #334155 !important;
}
/* Segmented control */
[data-testid="stSegmentedControl"] button {
    background-color: #1e293b !important;
    color: #94a3b8 !important;
    border-color: #334155 !important;
}
[data-testid="stSegmentedControl"] button[aria-checked="true"] {
    background-color: #334155 !important;
    color: #e2e8f0 !important;
}
/* Number input */
[data-testid="stNumberInput"] input {
    background-color: #1e293b !important;
    color: #e2e8f0 !important;
    border-color: #334155 !important;
}
[data-testid="stNumberInput"] button {
    background-color: #1e293b !important;
    color: #94a3b8 !important;
    border-color: #334155 !important;
}
/* Divider */
[data-testid="stDivider"], hr {
    border-color: #334155 !important;
}
/* Radio */
.stRadio [data-baseweb="radio"] label {
    color: #e2e8f0 !important;
}
/* Expander */
[data-testid="stExpander"] {
    border-color: #334155 !important;
    background-color: rgba(30,41,59,0.5) !important;
}
[data-testid="stExpander"] summary {
    color: #e2e8f0 !important;
}
/* Download button */
[data-testid="stDownloadButton"] button {
    background-color: #1e293b !important;
    color: #e2e8f0 !important;
    border-color: #334155 !important;
}
"""


def _css():
    """Generuje CSS s barvami odpovídajícími aktuálnímu tématu."""
    # Metriky
    met_bg    = _t("#f4f7fb", "#1e293b")
    met_bord  = _t("#e2e8f0", "#334155")
    met_label = _t("#52606d", "#94a3b8")
    # Texty
    txt_muted = _t("#52606d", "#94a3b8")
    txt_base  = _t("#334155", "#cbd5e1")
    # Chipy – zelený (hotovo)
    ch0_bg, ch0_c, ch0_b = _t("#ecfdf3", "#052e16"), _t("#166534", "#4ade80"), _t("#bbf7d0", "#166534")
    # Chipy – žlutý (částečně)
    ch1_bg, ch1_c, ch1_b = _t("#fffbeb", "#451a03"), _t("#92400e", "#fbbf24"), _t("#fde68a", "#92400e")
    # Chipy – červený (chybí)
    ch2_bg, ch2_c, ch2_b = _t("#fef2f2", "#450a0a"), _t("#991b1b", "#f87171"), _t("#fecaca", "#991b1b")
    # Chipy – neutrální (neaktivní)
    chn_bg, chn_c, chn_b = _t("#f8fafc", "#1e293b"), _t("#64748b", "#94a3b8"), _t("#e2e8f0", "#334155")
    # Šipka / arrow
    arrow = _t("#cbd5e1", "#475569")

    dark_block = _DARK_OVERRIDES if is_dark() else ""

    return f"""
<style>
.block-container {{padding-top: 1.6rem; padding-bottom: 3rem; max-width: 1500px;}}
h1 {{font-weight: 650; letter-spacing: -0.01em; margin-bottom: 0.1rem;}}
h4 {{margin-top: 0.4rem; font-weight: 600;}}
[data-testid="stMetric"] {{background: {met_bg}; border: 1px solid {met_bord}; border-radius: 10px; padding: 0.55rem 0.9rem;}}
[data-testid="stMetricLabel"] p {{font-size: 0.82rem; color: {met_label};}}
[data-testid="stMetricValue"] {{font-size: 1.45rem; font-variant-numeric: tabular-nums;}}
.stTabs [data-baseweb="tab-list"] {{gap: 0.4rem;}}
.stTabs [data-baseweb="tab"] {{padding: 0.45rem 0.9rem; border-radius: 8px 8px 0 0;}}
.pid-status {{color: {txt_muted}; font-size: 0.9rem; margin-bottom: 0.6rem;}}
.pid-big {{font-size: 0.8rem; color: {txt_muted};}}
.pid-prog {{display: flex; flex-wrap: wrap; gap: 0.4rem; align-items: center; margin: 0.2rem 0 0.3rem 0;}}
.pid-chip {{border-radius: 999px; padding: 0.18rem 0.7rem; font-size: 0.85rem; border: 1px solid; white-space: nowrap;}}
.pid-chip.s0 {{background: {ch0_bg}; color: {ch0_c}; border-color: {ch0_b};}}
.pid-chip.s1 {{background: {ch1_bg}; color: {ch1_c}; border-color: {ch1_b};}}
.pid-chip.s2 {{background: {ch2_bg}; color: {ch2_c}; border-color: {ch2_b};}}
.pid-chip.sn {{background: {chn_bg}; color: {chn_c}; border-color: {chn_b};}}
.pid-arrow {{color: {arrow};}}
.pid-next {{color: {txt_base}; font-size: 0.9rem; margin-bottom: 0.4rem;}}
{dark_block}
</style>"""


def _plotly_tpl():
    """Vytvoří Plotly šablonu odpovídající aktuálnímu tématu."""
    dark = is_dark()
    base_tpl = "plotly_dark" if dark else "plotly_white"
    tpl = go.layout.Template(pio.templates[base_tpl])

    font_color  = "#e2e8f0" if dark else "#1f2933"
    grid_color  = "#334155" if dark else "#eef2f6"
    spike_color = "#64748b" if dark else "#94a3b8"
    paper_bg    = "rgba(0,0,0,0)"
    plot_bg     = "#0f172a" if dark else "#ffffff"

    tpl.layout.update(
        font=dict(family=FONT, size=12, color=font_color),
        margin=dict(l=8, r=8, t=36, b=8),
        hovermode="x unified", hoversubplots="axis",
        hoverlabel=dict(font=dict(family=FONT)),
        legend=dict(orientation="h", yanchor="bottom", y=1.01, x=0, bgcolor="rgba(0,0,0,0)"),
        paper_bgcolor=paper_bg,
        plot_bgcolor=plot_bg,
    )
    tpl.layout.xaxis.update(
        showspikes=True, spikemode="across", spikesnap="cursor",
        spikethickness=1, spikecolor=spike_color,
        gridcolor=grid_color, zeroline=False,
    )
    tpl.layout.yaxis.update(gridcolor=grid_color, zeroline=False)
    return tpl


# ── Hlavní funkce ────────────────────────────────────────────────────

def apply_theme():
    """CSS do stránky a výchozí šablona grafů.  Šablona se přegeneruje při změně tématu."""
    st.markdown(_css(), unsafe_allow_html=True)

    # Klíč se mění s tématem → šablona se přeregistruje
    tpl_key = "pidtuner_dark" if is_dark() else "pidtuner_light"
    if tpl_key not in pio.templates:
        pio.templates[tpl_key] = _plotly_tpl()
    if pio.templates.default != tpl_key:
        pio.templates.default = tpl_key
