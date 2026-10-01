"""
Průvodce strukturami APC: kdy metodu použít (a kdy ne), příklady z praxe, kontrolní seznam předpokladů podle
skutečného stavu projektu (s tlačítky, která rovnou přepnou smyčku / záložku) a implementace v PCS 7 pomocí
standardních šablon a bloků knihovny APL.
"""
import streamlit as st

from ...i18n import T
from .. import loops

ss = st.session_state
TAB_KEYS = {"data": "tab1", "model": "tab2", "tuning": "tab3", "live": "tab4_live", "apc": "tab5", "project": "tab6"}


def goto(loop_id=None, tab=None, kind=None, other=None):
    """Callback tlačítek: přepnout smyčku, záložku, strukturu APC a druhou smyčku (před vykreslením widgetů)."""
    if loop_id is not None:
        loops.switch(loop_id)
    if tab:
        ss["main_tab"] = T(TAB_KEYS[tab])
    if kind:
        ss["apc_kind"] = kind
        if other is not None and kind in ("decouple", "override"):
            ss[f"apc_{kind}_b"] = other


def add_loop_and_go():
    loops.add()
    ss["main_tab"] = T("tab1")


def render(kind, checks, impl):
    """
    checks: [(stav, text, akce)] – stav True (splněno) / False (chybí) / None (připomínka);
            akce = (popisek, callback, args) nebo None.
    impl:   markdown s implementací v PCS 7 (už s vypočtenými parametry), nebo None.
    Průvodce je ve výchozím stavu sbalený.
    """
    with st.expander(T("g_title", m=T("apc_" + kind)), expanded=False, icon=":material/menu_book:"):
        c1, c2 = st.columns(2, gap="large")
        c1.markdown(T(f"g_{kind}_when"))
        c2.markdown(T(f"g_{kind}_examples"))
        st.markdown(f"**{T('g_checklist')}**")
        for n, (ok, text, action) in enumerate(checks):
            r = st.columns([0.05, 0.7, 0.25], vertical_alignment="center")
            r[0].markdown(":material/check_circle:" if ok else (":material/radio_button_unchecked:" if ok is False
                                                                 else ":material/info:"))
            r[1].markdown(text)
            if action and ok is not True:
                label, cb, args = action
                r[2].button(label, on_click=cb, args=args, key=f"g_act|{kind}|{n}", width="stretch",
                            icon=":material/arrow_forward:")
        if impl:
            st.markdown(f"**{T('g_impl')}**")
            st.markdown(impl)


def recommendations(items):
    """Doporučené struktury pro aktivní smyčku: [(druh, text, druhá smyčka)] → řádky s tlačítky „otevřít“."""
    if not items:
        return
    with st.container(border=True):
        st.markdown(f"**{T('g_reco_title')}**")
        for n, (kind, text, other) in enumerate(items):
            r = st.columns([0.78, 0.22], vertical_alignment="center")
            r[0].markdown(f":material/lightbulb: {text}")
            shown = ss.get("apc_kind") == kind and (kind not in ("decouple", "override")
                                                     or ss.get(f"apc_{kind}_b") == other)
            if not shown:
                r[1].button(T("g_open", m=T("apc_" + kind)), key=f"g_reco|{kind}|{n}", on_click=goto,
                            kwargs=dict(kind=kind, other=other), width="stretch")
