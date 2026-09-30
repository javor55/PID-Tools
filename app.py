"""
PID Tools – identifikace procesu a ladění regulátoru PIDConL (SIMATIC PCS 7 APL).
Spuštění:  streamlit run app.py
"""
import streamlit as st

st.set_page_config(page_title="PID Tools – PIDConL Tuner", page_icon="🎛️", layout="wide")

from pidtools.i18n import DEFAULT_LANG, T  # noqa: E402
from pidtools.ui import charts  # noqa: E402
from pidtools.ui.context import Ctx  # noqa: E402
from pidtools.ui.pages import (cascade, data, diagnostics, header, live, model, progress, project,  # noqa: E402
                               test_plan, tuning)
from pidtools.ui.theme import apply_theme  # noqa: E402

TABS = [("data", "tab1"), ("model", "tab2"), ("tuning", "tab3"), ("live", "tab4_live"),
        ("plan", "tab5"), ("cascade", "tab6"), ("project", "tab7")]


def main():
    if "lang" not in st.session_state:
        st.session_state.lang = DEFAULT_LANG
    apply_theme()
    charts.reset_report()
    ctx = Ctx()

    header.render(ctx)                       # nadpis, projekt, nápověda, nastavení, zdroj dat
    prog_ph = st.empty()                     # ukazatel postupu (vyplní se na konci)
    ctx.tabs = dict(zip([k for k, _ in TABS], st.tabs([T(lbl) for _, lbl in TABS])))

    data.render_setup(ctx)                   # sloupce, převzorkování, normování (potřebují všechny záložky)
    tuning.render_block(ctx)                 # konfigurace bloku PIDConL (potřebuje i záložka Data)
    header.render_status(ctx)

    data.render(ctx)
    model.render(ctx)
    tuning.render(ctx)
    live.render(ctx)
    diagnostics.render(ctx)
    test_plan.render(ctx)
    cascade.render(ctx)
    project.render(ctx)
    progress.render(ctx, prog_ph)


main()
