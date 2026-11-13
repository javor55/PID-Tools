"""Texty (pidtools/i18n/*.json): angličtina výchozí a úplná, čeština úplná, další jazyky doplněné z angličtiny."""
import json
import re
import string

from pidtools import i18n

FIELD = re.compile(r"\{(\w*)(?:[:!][^}]*)?\}")


def test_same_keys():
    assert set(i18n.RAW["cs"]) == set(i18n.RAW["en"])               # čeština je úplný překlad (bez doplňování)
    assert len(i18n.RAW["cs"]) > 1000


def test_languages_default_english_and_fallback():
    assert i18n.DEFAULT_LANG == "en" and i18n.LANGS[0] == "en"
    langs = {c: (n, cv) for c, n, cv in i18n.languages()}
    assert langs["en"] == ("English", 1.0) and langs["cs"] == ("Čeština", 1.0)
    for code in i18n.LANGS:                                         # neúplný jazyk: chybějící klíče anglicky
        assert set(i18n.TEXTS[code]) >= set(i18n.RAW["en"])
        assert i18n.TEXTS[code][i18n.DECIMAL_KEY] in (".", ",")
    assert i18n.decimal("cs") == "," and i18n.decimal("en") == "."


def test_same_placeholders_and_valid_format():
    fmt = string.Formatter()
    for k, cs in i18n.RAW["cs"].items():
        en = i18n.TEXTS["en"][k]
        assert sorted(FIELD.findall(cs)) == sorted(FIELD.findall(en)), k
        for s in (cs, en):
            list(fmt.parse(s))                        # nevyvážené závorky → ValueError
            assert all(isinstance(v, str) for v in (cs, en)), k


def test_files_are_plain_json():
    """Soubory čte i TypeScript rozhraní: platné JSON, objekt řetězců."""
    for code in i18n.LANGS:
        with open(i18n.DIR / f"{code}.json", encoding="utf-8") as f:
            d = json.load(f)
        assert isinstance(d, dict) and all(isinstance(v, str) for v in d.values())


def test_format_specs():
    """Zástupné hodnoty s formátem (např. {tc:.4g}) se vyplní."""
    i18n.set_lang("cs")
    try:
        assert "1.235" in i18n.T("note_avg", tc=1.23456)
    finally:
        i18n.set_lang("en")
