"""
Průvodce strukturami APC: kdy metodu použít (a kdy ne), příklady z praxe, kontrolní seznam předpokladů podle
skutečného stavu projektu (s tlačítky, která rovnou přepnou smyčku / záložku) a implementace v PCS 7 pomocí
standardních šablon a bloků knihovny APL.
"""
import html

import streamlit as st

from ....i18n import T
from ... import loops
from ...kit import card, head
from ...layout import section, side_first

ss = st.session_state
TAB_KEYS = {"data": "tab1", "model": "tab2", "tuning": "tab3", "live": "tab4_live", "apc": "tab5", "diag": "dk_diag_tab", "project": "tab_project",
            "audit": "tab7_audit"}


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


def action(a):
    """Identifikátor akce ze sdílených kontrol (pidtools.app.guides) → (popisek, callback, args) tlačítka."""
    if a is None or not isinstance(a, str):
        return a
    if a == "add_loop":
        return T("loop_add"), add_loop_and_go, ()
    if a.startswith("tab:"):
        tab = a[4:]
        return T("tgb_data" if tab == "data" else "g_btn_model"), goto, (None, tab)
    _, lid, tab = a.split(":")
    lid = int(lid)
    return (T("g_btn_data", n=loops.name(lid)) if tab == "data" else T("g_btn_model")), goto, (lid, tab)


def render(kind, checks, impl):
    """
    Průvodce strukturou (karta nahoře v pravém panelu, jako v návrhu; bez panelu na místě volání).
    checks: [(stav, text, akce)] – stav True (splněno) / False (chybí) / None (připomínka);
            akce = identifikátor ze sdílených kontrol (viz action) nebo None.
    impl:   markdown s implementací v PCS 7 (už s vypočtenými parametry), nebo None.
    """
    def body(side):
        exp = (section(side, T("g_side_title", m=T("apc_" + kind)), f"apc_guide|{kind}", expanded=True)
               if side is not None else st.expander(T("g_side_title", m=T("apc_" + kind)), expanded=True))
        with exp:
            st.markdown(T(f"g_{kind}_when"))
            st.markdown(T(f"g_{kind}_examples"))
            st.markdown(f"**{T('g_checklist')}**")
            for n, (ok, text, act_id) in enumerate(checks):
                ic = ":material/check_circle:" if ok else (":material/radio_button_unchecked:" if ok is False
                                                           else ":material/info:")
                st.markdown(f"{ic} {text}")
                act = action(act_id)
                if act and ok is not True:
                    label, cb, args = act
                    st.button(label, on_click=cb, args=args, key=f"g_act|{kind}|{n}", type="tertiary",
                              icon=":material/arrow_forward:")
            if impl:
                st.markdown(f"**{T('g_impl')}**")
                st.markdown(impl)
    side_first(body)


NEED2 = ("decouple", "override", "rga")         # struktury, které potřebují druhou smyčku projektu


def recommendations(items, loop_name):
    """
    Karta „Doporučení pro <smyčku>“: doporučené struktury se štítkem a odkazem Otevřít, nakonec struktury,
    které potřebují další smyčku (když je v projektu jen jedna).
    """
    with card("apcreco"):
        head(T("g_reco_for", n=loop_name), T("h_g_reco"))
        for n, (kind, text, other) in enumerate(items):
            r = st.columns([0.88, 0.12], vertical_alignment="center")
            r[0].markdown(f"<span class='pid-chip s0'>✓ {T('g_st_rec')}</span>&nbsp; <b>{html.escape(T('apc_' + kind))}</b>"
                          f" – {html.escape(text)}", unsafe_allow_html=True)
            shown = ss.get("apc_kind") == kind and (kind not in ("decouple", "override")
                                                     or ss.get(f"apc_{kind}_b") == other)
            if not shown:
                r[1].button(T("g_open_short"), key=f"g_reco|{kind}|{n}", on_click=goto, type="tertiary",
                            kwargs=dict(kind=kind, other=other))
        if not items:
            st.caption(T("g_reco_none"))
        if len(loops.ids()) < 2:
            st.markdown(f"<span class='pid-chip sn'>i {T('g_st_need2')}</span>&nbsp; "
                        + T("g_reco_need2_h", k=html.escape(", ".join(T("apc_" + k) for k in NEED2))),
                        unsafe_allow_html=True)
