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
                  muted="#52606d", accent="#1f5fa8", accent_bg="#eaf2fb", ctl="#c3ccd6"),
    "dark": dict(bg="#0b1220", card="#111a2e", side="#0f172a", line="#26324a", soft="#1c2740", text="#e2e8f0",
                 muted="#94a3b8", accent="#60a5fa", accent_bg="rgba(96,165,250,0.12)", ctl="#3b4a63"),
}

_CSS = """
<style>
:root {--pid-bg: %(bg)s; --pid-card: %(card)s; --pid-side: %(side)s; --pid-line: %(line)s; --pid-soft: %(soft)s;
    --pid-text: %(text)s; --pid-muted: %(muted)s; --pid-accent: %(accent)s; --pid-accent-bg: %(accent_bg)s; --pid-ctl: %(ctl)s;}
[data-testid="stApp"] {background: var(--pid-bg);}
/* Streamlit přes horní okraj kreslí průhlednou lištu – kliky propustit k hlavičce aplikace, kromě menu ⋮ */
[data-testid="stHeader"], [data-testid="stHeader"] [data-testid="stToolbar"] {background: transparent;
    pointer-events: none !important;}
[data-testid="stHeader"] [data-testid="stMainMenu"], [data-testid="stHeader"] [data-testid="stToolbarActions"] *
    {pointer-events: auto !important;}
/* rám jako v návrhu: bílá hlavička se záložkami přes celou šířku, pod ní plocha s grafy a panel vpravo až k okraji */
.block-container {padding: 0 !important; max-width: 100%%;}
[data-testid="stMainBlockContainer"] > [data-testid="stVerticalBlock"] {gap: 0 !important;}
code, [data-testid="stMetricValue"], [data-testid="stDataFrame"] {font-variant-numeric: tabular-nums;}
h1 {font-weight: 600; letter-spacing: 0; margin: 0; padding: 0 !important; font-size: 18px !important;
    line-height: 1.4 !important; white-space: nowrap;}
h4 {margin-top: 0.4rem; font-weight: 600;}
.pid-logo {display: flex; align-items: center; gap: 8px; font-size: 18px; line-height: 1; white-space: nowrap;
    font-weight: 500; letter-spacing: -0.01em;}
.pid-logo img {width: 26px; height: 26px; display: block;}
.pid-logo b {font-weight: 700; color: var(--pid-accent);}

/* běží výpočet (Streamlit ukazuje stavový widget): pohyblivý pruh pod hlavičkou a kurzor „pracuji“ */
@keyframes pidbusy {0%% {background-position: -40%% 0;} 100%% {background-position: 140%% 0;}}
body:has([data-testid="stStatusWidget"]) .st-key-main_tab > div > [role="tablist"]::after {content: ""; position: absolute;
    left: 0; right: 0; bottom: -1px; height: 3px; z-index: 50; pointer-events: none;
    background: linear-gradient(90deg, transparent 0%%, var(--pid-accent) 50%%, transparent 100%%) no-repeat;
    background-size: 40%% 100%%; animation: pidbusy 1.1s linear infinite;}
.st-key-main_tab > div > [role="tablist"] {position: relative;}
body:has([data-testid="stStatusWidget"]) [data-testid="stMain"] {cursor: progress;}

/* hlavička: název · smyčky · souhrn dat … Projekt, Nastavení, ? (vpravo místo pro menu ⋮ Streamlitu) */
.st-key-pid_header {background: var(--pid-card); padding: 12px 3.4rem 0 24px; gap: 10px 16px !important;}
.st-key-pid_header .pid-sub {font-size: 11px; color: var(--pid-muted); white-space: nowrap; overflow: hidden;
    text-overflow: ellipsis;}
.st-key-pid_header > [data-testid="stElementContainer"]:has(.pid-sub) {flex: 1 1 0; min-width: 0;}
.st-key-pid_header button {min-height: 0 !important; padding: 5px 12px !important; border-color: #c3ccd6;
    background: var(--pid-card);}
.st-key-pid_header button p {font-size: 12px !important;}
.st-key-pid_loops button p {font-size: 11px !important;}
.st-key-pid_loops [data-baseweb="select"] > div {height: 30px; font-weight: 600; background: var(--pid-card);
    border: 1px solid #c3ccd6;}
.st-key-pid_header [data-testid="stPopover"] button [data-testid="stIconMaterial"]:last-child {display: none;}
.st-key-pid_help button p {font-weight: 600;}
[data-testid="stPopoverBody"]:has(.st-key-pid_guide) {width: min(760px, 90vw); max-height: 80vh;}
.pid-sub {color: var(--pid-muted); font-size: 11px;}

/* záložky: navazují na hlavičku, modré podtržení 3 px, „Projekt a report“ vpravo */
.stTabs [role="tablist"] {gap: 4px;}
.stTabs [data-testid="stTab"] {padding: 10px 14px; color: var(--pid-muted); height: auto;}
.stTabs [data-testid="stTab"] p {font-size: 13px; font-weight: 400;}
.stTabs [data-testid="stTab"][aria-selected="true"] {color: var(--pid-accent);}
.stTabs [data-testid="stTab"][aria-selected="true"] p {font-weight: 600;}
.st-key-main_tab > div > [role="tablist"] {background: var(--pid-card); border-bottom: 1px solid var(--pid-line);
    padding: 10px 3.4rem 0 24px; width: 100%%; margin: 0;}
.st-key-main_tab > div > [role="tablist"] [data-baseweb="tab-highlight"],
.st-key-main_tab > div > [role="tablist"] [data-testid="stTabHighlight"] {height: 3px;}
.st-key-main_tab > div > [role="tablist"] > [data-testid="stTab"]:last-child {margin-left: auto;}
.st-key-main_tab > div > [role="tabpanel"] {padding: 0 0 0 24px;}


/* karty (jako v návrhu): bílá, rámeček 1 px, zaoblení 10 px, nadpis 15 px tučně, šipka vlevo, bez ikon */
[data-testid="stExpander"] details {border-radius: 10px; border: 1px solid var(--pid-line); background: var(--pid-card);}
[data-testid="stExpander"] summary {background: transparent; border-radius: 10px; padding: 12px 14px;}
[data-testid="stExpander"] summary p {font-size: 14px !important; font-weight: 600;}
[data-testid="stExpander"] summary [data-testid="stExpanderIconExpandMore"],
[data-testid="stExpander"] summary [data-testid="stExpanderIconChevronRight"] {color: #9aa5b1; font-size: 16px;}
[data-testid="stExpander"] details[open] summary {border-radius: 10px 10px 0 0;}
[data-testid="stExpanderDetails"] {padding: 12px 14px 14px 14px !important;}
/* doplněk nadpisu karty (:gray[…], např. FIT) vpravo, písmem s pevnou šířkou */
[data-testid="stExpander"] summary [data-testid="stMarkdownContainer"] p:has(> span) {display: flex;
    justify-content: space-between; align-items: baseline; gap: 8px; width: 100%%;}
[data-testid="stExpander"] summary [data-testid="stMarkdownContainer"]:has(p > span) {flex: 1;}
[data-testid="stExpander"] summary p > span {font-family: 'IBM Plex Mono', monospace; font-size: 11px; font-weight: 400;
    margin-left: auto;}
/* hlavní akce panelu (Identifikovat model, Ověřit v Živé simulaci …): velké modré tlačítko */
[class*="st-key-pid_cta"] button {min-height: 44px !important; border-radius: 10px !important;}
[class*="st-key-pid_cta"] button p {font-size: 14px !important; font-weight: 600;}
[data-testid="stVerticalBlockBorderWrapper"], .stVerticalBlock[data-testid="stVerticalBlock"][class*="st-key-pid_card"]
    {background: var(--pid-card); border-radius: 10px;}
[data-testid="stLayoutWrapper"] > [data-testid="stVerticalBlock"][class*="st-key-pid_card"],
[data-testid="stVerticalBlock"][class*="st-key-pid_card"] {border: 1px solid var(--pid-line); padding: 10px 14px;}
[class*="st-key-pid_card"] [data-testid="stVerticalBlock"][class*="st-key-pid_card"],
[class*="st-key-pidside_"] [data-testid="stVerticalBlock"][class*="st-key-pid_card"],
[data-testid="stDialog"] [data-testid="stVerticalBlock"][class*="st-key-pid_card"] {border: 0; padding: 0;
    background: transparent;}

/* pole a ovládací prvky (jen desktop, myš): 13 px, bílé pole s rámečkem jako v návrhu */
[data-testid="stNumberInputContainer"], [data-testid="stTextInputRootElement"], [data-testid="stTextAreaRootElement"],
[data-testid="stSelectbox"] > div:not([data-testid]), [data-testid="stMultiSelect"] > div:not([data-testid]),
[data-testid="stDateInput"] > div:not([data-testid]), [data-testid="stTimeInput"] > div:not([data-testid])
    {min-height: 0; background: var(--pid-card) !important; border: 1px solid var(--pid-ctl) !important;
    border-radius: 6px !important;}
[data-testid="stNumberInputContainer"], [data-testid="stTextInputRootElement"],
[data-testid="stSelectbox"] > div:not([data-testid]) {height: 28px; min-height: 28px;}
[data-testid="stMultiSelect"] > div:not([data-testid]) {min-height: 28px;}
[data-testid="stSelectbox"] > div:not([data-testid]) *, [data-testid="stTextInputField"],
[data-testid="stTextAreaRootElement"] textarea {font-size: 12px; background: transparent !important;}
[data-testid="stTextInputRootElement"]:focus-within, [data-testid="stNumberInputContainer"]:focus-within,
[data-testid="stSelectbox"] > div:not([data-testid]):focus-within {border-color: var(--pid-accent) !important;}
[data-testid="stNumberInputContainer"] [data-baseweb="input"] {border: 0 !important; height: auto;}
[data-testid="stNumberInputContainer"] input, [data-baseweb="input"] input, [data-baseweb="select"] {font-size: 12px;}
[data-testid="stNumberInputContainer"] input, [data-baseweb="input"] input {padding: 4px 8px; background: transparent;}
[data-baseweb="base-input"], [data-baseweb="select"] > div > div, [data-baseweb="textarea"] textarea
    {background: transparent !important;}
/* řádek „popisek | pole“: popisek na střed výšky pole, žádné okraje navíc */
[data-testid="stHorizontalBlock"]:has(.pid-plab) [data-testid="stElementContainer"] {margin: 0;}
/* vlastní HTML prvky (pid-…): bez záporného spodního okraje, který Streamlit dává textu (posouval popisky) */
[data-testid="stMarkdownContainer"]:has(> [class^="pid-"]), [data-testid="stMarkdownContainer"]:has(> [class*=" pid-"])
    {margin-bottom: 0 !important;}
.pid-plab {line-height: 20px;}
[data-testid="stNumberInputContainer"] button {display: none;}
.stButton button, .stDownloadButton button, [data-testid="stPopover"] > div > button, [data-testid="stFormSubmitButton"] button
    {min-height: 28px; padding: 4px 10px; border-radius: 6px; border-color: var(--pid-ctl);}
.stButton button[kind="primary"], .stDownloadButton button[kind="primary"] {border-color: transparent;}
.stButton button p, .stDownloadButton button p, [data-testid="stPopover"] button p {font-size: 12px;}
[data-testid="stButtonGroup"] [role="radiogroup"], [data-testid="stButtonGroup"] [role="group"] {gap: 0 !important;}
[data-testid="stButtonGroup"] button {min-height: 28px; padding: 4px 10px; border-radius: 0; border-color: var(--pid-ctl);
    margin-left: -1px;}
[data-testid="stButtonGroup"] button:first-child {border-radius: 8px 0 0 8px; margin-left: 0;}
[data-testid="stButtonGroup"] button:last-child {border-radius: 0 8px 8px 0;}
[data-testid="stButtonGroup"] button:only-child {border-radius: 8px;}
[data-testid="stButtonGroup"] button[aria-checked="true"], [data-testid="stButtonGroup"] button[aria-pressed="true"]
    {background: var(--pid-accent) !important; color: #fff !important; border-color: var(--pid-accent) !important;
    position: relative; z-index: 1;}
[data-testid="stButtonGroup"] button[aria-checked="true"] p, [data-testid="stButtonGroup"] button[aria-pressed="true"] p {color: #fff !important; font-weight: 500;}
[data-testid="stButtonGroup"] button p {font-size: 12px;}
[data-testid="stWidgetLabel"] {min-height: 0; margin-bottom: 4px;}
[data-testid="stWidgetLabel"] p {font-size: 12px; color: var(--pid-muted);}
[data-testid="stCheckbox"] label {min-height: 0;}
[data-testid="stCheckbox"] label p {font-size: 12px;}
[data-testid="stCaptionContainer"] p {font-size: 11px; color: var(--pid-muted);}
[data-testid="stMarkdownContainer"] p, [data-testid="stMarkdownContainer"] li {font-size: 12px;}
[data-testid="stMainBlockContainer"] [data-testid="stVerticalBlock"] {gap: 12px;}

/* panel nastavení vpravo až k okraji: šedé pozadí, rámeček vlevo, vlastní posuvník, rozbalit / sbalit vše */
[data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] > [data-testid="stVerticalBlock"] > [data-testid="stLayoutWrapper"] > [class*="st-key-pidside_"])
    {gap: 16px !important;}
[data-testid="stColumn"]:has(> [data-testid="stVerticalBlock"] > [data-testid="stLayoutWrapper"] > [class*="st-key-pidside_"])
    {align-self: stretch;}
[data-testid="stLayoutWrapper"]:has(> [class*="st-key-pidside_"]) {position: sticky; top: 0; align-self: flex-start;
    width: 100%%;}
[class*="st-key-pidside_"] {flex: 0 0 auto !important; height: calc(100vh - var(--pid-top, 98px)) !important;
    max-height: calc(100vh - var(--pid-top, 98px)); overflow-y: auto; overflow-x: hidden;
    padding: 16px 24px 32px 4px; background: var(--pid-side); border-left: 1px solid var(--pid-line);
    margin-left: 0; box-sizing: border-box; padding-left: 14px;}
[class*="st-key-pidmain_"] {padding: 16px 0 32px 0;}
/* plocha a panel rolují nezávisle (výška okna pod hlavičkou, --pid-top měří chart_tools.js) */
[data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] > [data-testid="stVerticalBlock"] > [data-testid="stLayoutWrapper"] > [class*="st-key-pidside_"])
    {flex: 0 0 auto !important; height: calc(100vh - var(--pid-top, 98px)) !important;
    max-height: calc(100vh - var(--pid-top, 98px)); overflow: hidden; align-items: stretch;}
[data-testid="stColumn"]:has(> [data-testid="stVerticalBlock"] > [data-testid="stLayoutWrapper"] > [class*="st-key-pidmain_"])
    {height: 100%%; max-height: 100%%; overflow-y: auto; overflow-x: hidden; padding-right: 4px;}
[data-testid="stColumn"]:has(> [data-testid="stVerticalBlock"] > [data-testid="stLayoutWrapper"] > [class*="st-key-pidside_"])
    {height: 100%%; max-height: 100%%; overflow: hidden;}
[class*="st-key-pidside_"] [data-testid="stVerticalBlock"] {gap: 12px;}
[class*="st-key-pidside_"] [data-testid="stExpanderDetails"] [data-testid="stVerticalBlock"] {gap: 8px;}
[class*="st-key-pidside_"] [data-testid="stHorizontalBlock"] {gap: 8px; align-items: center;}
/* přepínače v panelu se vždy vejdou: tlačítka si dělí šířku, delší text se zalomí */
[class*="st-key-pidside_"] [data-testid="stButtonGroup"], [class*="st-key-pidside_"] [data-testid="stButtonGroup"] > div
    {max-width: 100%%; min-width: 0;}
[class*="st-key-pidside_"] [data-testid="stButtonGroup"] [role="radiogroup"],
[class*="st-key-pidside_"] [data-testid="stButtonGroup"] [role="group"] {flex-wrap: nowrap; width: 100%%;}
[class*="st-key-pidside_"] [data-testid="stButtonGroup"] button {flex: 1 1 auto; min-width: 0; padding: 3px 6px;
    height: auto;}
[class*="st-key-pidside_"] [data-testid="stButtonGroup"] button p, [class*="st-key-pidside_"] .stButton button p,
[class*="st-key-pidside_"] .stDownloadButton button p {white-space: normal; line-height: 1.2; word-break: normal;
    overflow-wrap: normal;}
[class*="st-key-pidside_"] .stButton button, [class*="st-key-pidside_"] .stDownloadButton button {height: auto;}
.pid-plab {font-size: 12px; font-weight: 400; color: var(--pid-muted); white-space: nowrap; display: flex; align-items: center; gap: 0.3rem;}
/* výběr struktury APC jako záložky s podtržením */
.st-key-pid_apckind {background: var(--pid-card); border: 1px solid var(--pid-line); border-radius: 10px; padding: 0 8px;}
.st-key-pid_apckind [data-testid="stButtonGroup"] [role="radiogroup"] {gap: 4px !important; flex-wrap: wrap;}
.st-key-pid_apckind [data-testid="stButtonGroup"] button {border: 0 !important; border-radius: 0 !important;
    background: transparent !important; padding: 10px 10px 7px !important; border-bottom: 3px solid transparent !important;
    margin: 0 !important;}
.st-key-pid_apckind [data-testid="stButtonGroup"] button p {color: var(--pid-muted) !important; font-size: 13px !important;}
.st-key-pid_apckind [data-testid="stButtonGroup"] button[aria-checked="true"] {border-bottom-color: var(--pid-accent) !important;}
.st-key-pid_apckind [data-testid="stButtonGroup"] button[aria-checked="true"] p {color: var(--pid-accent) !important;
    font-weight: 600;}
/* nadpis karty hlavní plochy, dlaždice hodnot (pidtools.ui.kit) */
.pid-chead {display: flex; align-items: center; gap: 8px; flex-wrap: wrap; min-height: 24px;}
.pid-chead .t {font-size: 14px; font-weight: 600;}
.pid-chead .n {font-size: 11px; color: var(--pid-muted);}
.pid-chead .r {margin-left: auto; font-size: 11px; color: var(--pid-muted);}
.pid-chead .q, .pid-plab .q {display: inline-flex; width: 20px; height: 20px; border-radius: 50%%; border: 1px solid #9aa5b1;
    font-size: 11px; font-weight: 600; align-items: center; justify-content: center; color: #3e4c59; cursor: help;
    background: var(--pid-card);}
.pid-tiles {display: grid; gap: 8px;}
.pid-tile {border: 1px solid var(--pid-line); border-radius: 8px; padding: 6px 4px; text-align: center;
    background: var(--pid-side);}
.pid-tile .l {font-size: 11px; color: var(--pid-muted);}
.pid-tile .v {font-family: 'IBM Plex Mono', monospace; font-size: 16px; font-weight: 500; line-height: 1.25;}
.pid-tile .s {font-size: 11px; color: var(--pid-muted);}
.pid-tile.ok {background: #e9f7ef; border-color: #9fd8b4;}
.pid-tile.warn {background: #fff4dc; border-color: #f2c46d;}
.pid-tile.bad {background: #fde8e8; border-color: #f5a3a3;}
.pid-big-val {font-family: 'IBM Plex Mono', monospace; font-size: 12px; font-weight: 600; color: #7c3aed;}
.pid-unit {font-size: 11px; color: var(--pid-muted); white-space: nowrap;}
.pid-src {font-size: 11px; color: var(--pid-muted); margin: -4px 0 0 0;}
.pid-side-tools {display: flex; justify-content: flex-end; gap: 0.8rem; font-size: 11px; margin: 0 0.1rem 0.1rem 0;}
.pid-side-tools button {font: inherit; border: 0; background: transparent; color: var(--pid-accent); padding: 0;
    cursor: pointer;}

[data-testid="stMetric"] {background: var(--pid-card); border: 1px solid var(--pid-line); border-radius: 10px;
    padding: 0.55rem 0.9rem;}
[data-testid="stMetricLabel"] p {font-size: 11px; color: var(--pid-muted);}
[data-testid="stMetricValue"] {font-size: 18px; font-family: 'IBM Plex Mono', monospace;}
.pid-status {color: var(--pid-muted); font-size: 0.85rem; margin-bottom: 0.4rem;}
.pid-big {font-size: 0.8rem; opacity: 0.75;}
.pid-prog {display: flex; flex-wrap: wrap; gap: 0.4rem; align-items: center; margin: 0.2rem 0 0.3rem 0;}
.pid-chip {border-radius: 999px; padding: 0.18rem 0.7rem; font-size: 0.82rem; border: 1px solid; white-space: nowrap;}
.pid-chip.s0 {background: rgba(34,197,94,0.13); color: #2f6f3e; border-color: rgba(34,197,94,0.4);}
.pid-chip.s1 {background: rgba(234,179,8,0.15); color: #8a4b00; border-color: rgba(234,179,8,0.45);}
.pid-chip.s2 {background: rgba(239,68,68,0.13); color: #b91c1c; border-color: rgba(239,68,68,0.4);}
.pid-chip.sn {background: rgba(128,128,128,0.08); color: var(--pid-muted); border-color: rgba(128,128,128,0.3);}
.pid-arrow {opacity: 0.4;}
.pid-formula {font-family: 'IBM Plex Mono', monospace; font-size: 12px; margin: 0 0 2px 0;}
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
