"""
Lokalizace. Každý jazyk je soubor `<kód>.json` v této složce (`en.json`, `cs.json`, …) – jediný zdroj pro Python
(výpočty, protokol, report) i pro rozhraní v TypeScriptu. Zástupné hodnoty mají tvar Pythonu `{název}`, případně
s formátem `{název:.4g}`.

Výchozí jazyk je angličtina a je úplná; ostatní jazyky se načtou automaticky podle souborů ve složce. Nový jazyk =
nový soubor (např. `es.json`) s přeloženými klíči a položkou `_lang_name` (vlastní název jazyka, „Español“);
chybějící klíče se doplní z angličtiny, takže překlad může být i neúplný.
`T(key, **kw)` vrací text v aktuálním jazyce, chybějící klíč se vrací beze změny.

Jazyk určuje frontend: buď nastaví jazyk přímo (`set_lang`, desktop), nebo zaregistruje funkci, která ho vrací
(`set_lang_provider`, web – jazyk požadavku). Modul sám nezávisí na žádném UI frameworku.
"""
import json
import re
from pathlib import Path

DIR = Path(__file__).resolve().parent
DEFAULT_LANG = "en"
NAME_KEY = "_lang_name"                       # vlastní název jazyka v jeho souboru („Čeština“)
DECIMAL_KEY = "_decimal"                      # desetinný oddělovač jazyka („,“ / „.“)


def _load(code):
    with open(DIR / f"{code}.json", encoding="utf-8") as f:
        return json.load(f)


def _discover():
    codes = sorted(p.stem for p in DIR.glob("*.json") if re.fullmatch(r"[a-z]{2,3}(-[A-Za-z0-9]{2,8})?", p.stem))
    return tuple([DEFAULT_LANG] + [c for c in codes if c != DEFAULT_LANG])


LANGS = _discover()
RAW = {code: _load(code) for code in LANGS}                         # jen to, co je v souboru (kontrola úplnosti)
TEXTS = {code: {**RAW[DEFAULT_LANG], **RAW[code]} for code in LANGS}  # doplněno z angličtiny


def languages():
    """[(kód, vlastní název, podíl přeložených klíčů 0–1)], angličtina první."""
    ref = [k for k in RAW[DEFAULT_LANG] if not k.startswith("_")]
    return [(c, RAW[c].get(NAME_KEY, c), sum(k in RAW[c] for k in ref) / max(1, len(ref))) for c in LANGS]


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
    s = TEXTS[lang()].get(key, key)
    return s.format(**kw) if kw else s


def decimal(code=None):
    """Desetinný oddělovač jazyka (výchozí aktuální jazyk)."""
    return TEXTS.get(code or lang(), TEXTS[DEFAULT_LANG]).get(DECIMAL_KEY, ".")
