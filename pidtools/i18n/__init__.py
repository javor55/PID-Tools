"""
Lokalizace (cs, en). Texty jsou ve slovnících `cs.TEXTS` a `en.TEXTS` se stejnými klíči.
`T(key, **kw)` vrací text v jazyce z `st.session_state.lang` (výchozí angličtina), chybějící klíč se vrací beze změny.
"""
import streamlit as st

from . import cs, en

TEXTS = {"cs": cs.TEXTS, "en": en.TEXTS}
DEFAULT_LANG = "en"


def lang():
    return st.session_state.get("lang", DEFAULT_LANG)


def T(key, **kw):
    s = TEXTS[lang()].get(key, TEXTS["en"].get(key, key))
    return s.format(**kw) if kw else s
