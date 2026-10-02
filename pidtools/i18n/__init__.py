"""
Lokalizace (cs, en). Texty jsou ve slovnících `cs.TEXTS` a `en.TEXTS` se stejnými klíči.
`T(key, **kw)` vrací text v aktuálním jazyce, chybějící klíč se vrací beze změny.

Jazyk určuje frontend: buď nastaví jazyk přímo (`set_lang`, desktop), nebo zaregistruje funkci, která ho vrací
(`set_lang_provider`, web – jazyk z session state). Modul sám nezávisí na žádném UI frameworku.
"""
from . import cs, en

TEXTS = {"cs": cs.TEXTS, "en": en.TEXTS}
DEFAULT_LANG = "en"

_lang = DEFAULT_LANG
_provider = None


def set_lang(code):
    """Pevně nastavený jazyk (pokud není zaregistrovaný poskytovatel)."""
    global _lang
    _lang = code if code in TEXTS else DEFAULT_LANG


def set_lang_provider(fn):
    """Funkce bez argumentů vracející kód jazyka (např. ze session state webové aplikace); None = zrušit."""
    global _provider
    _provider = fn


def lang():
    if _provider is not None:
        code = _provider()
        return code if code in TEXTS else DEFAULT_LANG
    return _lang


def T(key, **kw):
    s = TEXTS[lang()].get(key, TEXTS["en"].get(key, key))
    return s.format(**kw) if kw else s
