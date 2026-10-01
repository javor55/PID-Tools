"""
Widgety se stavem v `st.session_state`.

Výchozí hodnota se zapíše do session state jen jednou; widget pak dostává jen klíč. Tím odpadá varování
Streamlitu o souběhu výchozí hodnoty a session state a hodnoty přežijí přepnutí jazyka i obnovu projektu.
"""
import functools
import os

import numpy as np
import streamlit as st

from ..i18n import T

ss = st.session_state


def num(label, key, default, container=st, **kw):
    """number_input."""
    if key not in ss:
        ss[key] = float(default)
    return container.number_input(label, key=key, **kw)


def sel(cont, label, opts, idx, key, **kw):
    """selectbox s výchozím indexem."""
    if ss.get(key) not in opts:
        ss[key] = opts[idx]
    return cont.selectbox(label, opts, key=key, **kw)


def seg(cont, label, opts, default, key, **kw):
    """segmented_control; vrací None, pokud uživatel volbu zruší (volající doplní výchozí)."""
    if key not in ss or ss[key] not in opts:
        ss[key] = default
    return cont.segmented_control(label, opts, key=key, **kw)


def sld(cont, label, lo, hi, default, key, **kw):
    """slider; hodnota mimo nový rozsah se vrátí na výchozí."""
    v = ss.get(key)
    if v is None or not isinstance(v, (int, float)) or not (lo <= v <= hi):
        ss[key] = default
    return cont.slider(label, lo, hi, key=key, **kw)


def tog(cont, label, default, key, **kw):
    """toggle."""
    if key not in ss:
        ss[key] = bool(default)
    return cont.toggle(label, key=key, **kw)


def fmt(v, d=4):
    """Číslo na d platných míst, nekonečno jako ∞."""
    return "∞" if v is None or not np.isfinite(v) else f"{v:.{d}g}"


def notes_text(notes):
    """Poznámky z jádra [(klíč textu, argumenty)] → text v aktuálním jazyce."""
    return " ".join(T(k, **a) for k, a in notes)


def model_name(code):
    return T("model_" + code)


# ---- komponenty st.components.v2 (JS přímo na stránce)
_STATIC = os.path.join(os.path.dirname(__file__), "static")
_V2 = {}


@functools.lru_cache(maxsize=None)
def static_asset(name):
    """Obsah souboru z pidtools/ui/static (čte se jednou)."""
    with open(os.path.join(_STATIC, name), encoding="utf-8") as f:
        return f.read()


def v2_component(name, **kw):
    """
    Komponenta v2 zaregistrovaná v aktuálním runtime (každý runtime – i každá instance AppTest – má vlastní registr;
    opakovaná registrace se stejným názvem by jen vypisovala varování).
    """
    from streamlit.components.v2 import get_bidi_component_manager
    mgr = get_bidi_component_manager()
    key = (id(mgr), name)
    if key not in _V2 or mgr.get(name) is None:
        _V2[key] = st.components.v2.component(name, **kw)
    return _V2[key]


# ---- stav widgetů mezi běhy, kdy se nevykreslí
_NO_KEEP = ("up_file", "proj_up", "live_sim")


def keep_widget_state():
    """
    Přepíše hodnoty widgetů do session state jako běžné klíče (volá se na začátku každého běhu).

    Streamlit zahodí stav widgetu, který se v některém běhu nevykreslí – např. při přepnutí zdroje na Soubor před
    nahráním souboru (`st.stop`) nebo na zavřené záložce. Klíč pak ještě chvíli „existuje“, takže `num()` nezapíše
    výchozí hodnotu, a widget začne od nuly (rozsahy 0–0, SampleTime 0 …). Zápis `ss[k] = ss[k]` ho udrží.
    Tlačítka s klíčem musí mít prefix ze SKIP_PREFIX (např. „g_“) – jejich hodnotu Streamlit zapsat nedovolí.
    """
    from .loops import _restorable
    for k in list(ss.keys()):
        if k in _NO_KEEP or str(k).startswith("_"):
            continue
        try:
            v = ss[k]
            if _restorable(k, v):
                ss[k] = v
        except Exception:
            pass
