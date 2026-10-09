"""
Jednotné rozložení záložek webu (stejné jako desktop): vlevo co největší plocha pro grafy a data, vpravo panel
nastavení se sbalitelnými sekcemi. Panel má vlastní posuvník (roluje nezávisle na grafech) a nahoře „Rozbalit vše /
Sbalit vše“ (přepíná sekce v prohlížeči, bez nového běhu). Stav sekcí si Streamlit pamatuje podle klíče.
"""
import threading
from types import SimpleNamespace

import streamlit as st

from ..i18n import T

SIDE = 1.0      # poměr šířek hlavní plocha : panel
MAIN = 2.7

_run = threading.local()


def reset():
    """Na začátku běhu: číslování panelů od nuly (klíče kontejnerů jsou pak mezi běhy stejné)."""
    _run.n = 0
    _run.pending = []
    _run.adopt, _run.slot = None, None


def side_first(fn):
    """
    Obsah nahoře v panelu (např. průvodce strukturou APC): do místa převzatého panelu (adopt), jinak ho vykreslí
    příští panel (workspace) jako první.
    """
    slot = getattr(_run, "slot", None)
    if slot is not None:
        fn(slot)
    else:
        _run.pending = getattr(_run, "pending", []) + [fn]


def adopt(ws):
    """Příští workspace() vrátí tento panel (stránka ho vytvořila dřív – nahoře v ní jsou společné prvky)."""
    _run.adopt, _run.slot = ws, ws.slot


def release():
    _run.adopt, _run.slot = None, None


def flush_pending(cont=None):
    """Nevyužitý obsah z side_first (žádný panel nenásledoval) vykreslí do cont / aktuálního místa."""
    fns, _run.pending = getattr(_run, "pending", []), []
    for fn in fns:
        if cont is not None:
            with cont:
                fn(None)
        else:
            fn(None)


def workspace(gap="medium"):
    """Rozdělí aktuální kontejner na (main, side). Volá se uvnitř záložky."""
    ad = getattr(_run, "adopt", None)
    if ad is not None:
        _run.adopt = None
        return ad
    mcol, col = st.columns([MAIN, SIDE], gap=gap)
    n = getattr(_run, "n", 0)
    _run.n = n + 1
    main = mcol.container(key=f"pidmain_{n}")
    side = col.container(key=f"pidside_{n}")
    side.html(f'<div class="pid-side-tools"><button type="button" data-pid-all="1">{T("side_expand_all")}</button>'
              f'<button type="button" data-pid-all="0">{T("side_collapse_all")}</button></div>')
    slot = side.container()
    fns, _run.pending = getattr(_run, "pending", []), []
    for fn in fns:
        fn(slot)
    return SimpleNamespace(main=main, side=side, slot=slot)


def section(parent, title, key, expanded=False, icon=None):
    """Sbalitelná sekce panelu nastavení (expander s pamětí stavu; výchozí sbalená – jsou vidět všechny možnosti)."""
    with parent:
        return st.expander(title, expanded=expanded, key=f"sec|{key}")      # bez ikon – jako v návrhu
