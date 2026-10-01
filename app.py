"""
PID Tools – identifikace procesu a ladění regulátoru PIDConL (SIMATIC PCS 7 APL).
Spuštění:  streamlit run app.py
"""
import streamlit as st

st.set_page_config(page_title="PID Tools – PIDConL Tuner", page_icon="🎛️", layout="wide")

from pidtools.i18n import DEFAULT_LANG, TEXTS, T  # noqa: E402
from pidtools.ui import autosave, charts, loops  # noqa: E402
from pidtools.ui.guess import loop_tag  # noqa: E402
from pidtools.ui.context import Ctx  # noqa: E402
from pidtools.ui.pages import (apc, data, diagnostics, guides, header, live, model, project,  # noqa: E402
                               tuning)
from pidtools.ui.theme import apply_theme  # noqa: E402
from pidtools.ui.widgets import keep_widget_state  # noqa: E402

TABS = [("data", "tab1"), ("model", "tab2"), ("tuning", "tab3"), ("live", "tab4_live"),
        ("cascade", "tab5"), ("project", "tab6")]


def main():
    if "lang" not in st.session_state:
        st.session_state.lang = DEFAULT_LANG
    keep_widget_state()                      # stav widgetů přežije běh, kdy se nevykreslí (zdroj bez dat …)
    apply_theme()
    charts.reset_report()
    ctx = Ctx()

    header.render(ctx)                       # nadpis, projekt, nápověda, nastavení, zdroj dat
    # výběr záložky je uložený jako popisek → po přepnutí jazyka ho převést na popisek v novém jazyce
    cur = st.session_state.get("main_tab")
    for _, lbl in TABS:
        if cur in (TEXTS[lg][lbl] for lg in TEXTS):
            st.session_state["main_tab"] = T(lbl)
    # on_change="rerun": prohlížeč posílá výběr záložky → grafy se posílají jen pro aktivní záložku
    tabs = st.tabs([T(lbl) for _, lbl in TABS], key="main_tab", on_change="rerun")
    ctx.tabs = {k: charts.Page(tab) for (k, _), tab in zip(TABS, tabs)}

    data.render_setup(ctx)                   # sloupce, převzorkování, normování (potřebují všechny záložky)
    tuning.render_block(ctx)                 # konfigurace bloku PIDConL (potřebuje i záložka Data)
    header.render_status(ctx)

    data.render(ctx)
    model.render(ctx)
    tuning.render(ctx)
    live.render(ctx)
    diagnostics.render(ctx)
    apc.render(ctx)
    project.render(ctx)
    loops.save_info(ctx, loop_tag(ctx.c_pv).upper())   # souhrn smyčky pro přepínač a kaskádu
    autosave.save(ctx)                                  # průběžné uložení do prohlížeče
    guides.render_all(ctx)                              # průvodci záložek (s výsledky tohoto běhu)


main()
