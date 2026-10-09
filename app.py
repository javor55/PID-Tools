"""
PID Tools – identifikace procesu a ladění regulátoru PIDConL (SIMATIC PCS 7 APL).
Spuštění:  streamlit run app.py
"""
from pathlib import Path

import streamlit as st

_ICON = Path(__file__).with_name("pidtools") / "assets" / "icon.png"
st.set_page_config(page_title="PID Tools – PIDConL Tuner", page_icon=str(_ICON) if _ICON.exists() else "🎛️",
                   layout="wide")

from pidtools.i18n import DEFAULT_LANG, TEXTS, T  # noqa: E402
from pidtools.i18n import set_lang_provider  # noqa: E402
from pidtools.ui import autosave, charts, layout, loops  # noqa: E402
from pidtools.app.guess import loop_tag  # noqa: E402
from pidtools.ui.context import Ctx  # noqa: E402
from pidtools.ui.pages import (apc, audit, data, diagnostics, guides, header, live, model,  # noqa: E402
                               project, tuning)
from pidtools.ui.theme import apply_theme  # noqa: E402
from pidtools.ui.widgets import keep_widget_state  # noqa: E402

set_lang_provider(lambda: st.session_state.get("lang", DEFAULT_LANG))

# „Projekt a report“ není krok postupu – je poslední a CSS ho odsune doprava (jako tlačítko v hlavičce desktopu)
TABS = [("data", "tab1"), ("model", "tab2"), ("tuning", "tab3"), ("live", "tab4_live"),
        ("cascade", "tab5"), ("diag", "dk_diag_tab"), ("audit", "tab7_audit"), ("project", "tab_project")]


def main():
    if "lang" not in st.session_state:
        st.session_state.lang = DEFAULT_LANG
    keep_widget_state()                      # stav widgetů přežije běh, kdy se nevykreslí (zdroj bez dat …)
    apply_theme()
    charts.reset_report()
    layout.reset()
    ctx = Ctx()

    header.render(ctx)                       # nadpis, smyčky, projekt, nastavení, nápověda
    charts.tools()                           # časová osa v min / h a měřicí kurzory u všech grafů
    # výběr záložky je uložený jako popisek → po přepnutí jazyka ho převést na popisek v novém jazyce
    cur = st.session_state.get("main_tab")
    for _, lbl in TABS:
        if cur in (TEXTS[lg][lbl] for lg in TEXTS):
            st.session_state["main_tab"] = T(lbl)
    # on_change="rerun": prohlížeč posílá výběr záložky → grafy se posílají jen pro aktivní záložku
    tabs = st.tabs([T(lbl) for _, lbl in TABS], key="main_tab", on_change="rerun")
    ctx.tabs = {k: charts.Page(tab) for (k, _), tab in zip(TABS, tabs)}

    data.open_workspace(ctx)                 # záložka Data: plocha a panel (zdroj dat je jeho první sekce)
    header.render_source(ctx)                # zdroj dat → ctx.df (bez dat výzva k nahrání a konec běhu)
    data.render_setup(ctx)                   # sloupce, převzorkování, jednotky (potřebují všechny záložky)
    tuning.render_block(ctx)                 # konfigurace bloku PIDConL vč. NormPV/NormMV (potřebuje i záložka Data)
    if not ctx.norm_ok:                      # neplatný rozsah regulátoru – opraví se v bloku PIDConL (už vykreslen)
        st.stop()
    header.render_status(ctx)

    data.render(ctx)
    model.render(ctx)
    tuning.render(ctx)
    live.render(ctx)
    diagnostics.render(ctx)
    apc.render(ctx)
    project.render(ctx)
    audit.render(ctx)
    loops.save_info(ctx, loop_tag(ctx.c_pv).upper())   # souhrn smyčky pro přepínač a kaskádu
    autosave.save(ctx)                                  # průběžné uložení do prohlížeče
    guides.render_all(ctx)                              # průvodci záložek (s výsledky tohoto běhu)


main()
