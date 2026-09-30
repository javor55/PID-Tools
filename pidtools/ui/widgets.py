"""
Widgety se stavem v `st.session_state`.

Výchozí hodnota se zapíše do session state jen jednou; widget pak dostává jen klíč. Tím odpadá varování
Streamlitu o souběhu výchozí hodnoty a session state a hodnoty přežijí přepnutí jazyka i obnovu projektu.
"""
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
