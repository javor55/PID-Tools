"""
Jednotné rozložení záložek webu (stejné jako desktop): vlevo co největší plocha pro grafy a data, vpravo panel
nastavení se sbalitelnými sekcemi. Stav sekcí si Streamlit pamatuje podle klíče (po dobu relace i v autosave).
"""
from types import SimpleNamespace

import streamlit as st

SIDE = 1.0      # poměr šířek hlavní plocha : panel
MAIN = 2.7


def workspace(gap="medium"):
    """Rozdělí aktuální kontejner na (main, side). Volá se uvnitř záložky."""
    main, side = st.columns([MAIN, SIDE], gap=gap)
    return SimpleNamespace(main=main, side=side)


def section(parent, title, key, expanded=True, icon=None):
    """Sbalitelná sekce panelu nastavení (expander s pamětí stavu)."""
    with parent:
        return st.expander(title, expanded=expanded, key=f"sec|{key}", icon=icon)
