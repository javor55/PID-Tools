"""Kontrola textů (TICKET-016): jazyky mají stejné klíče a zástupné `{x}`, žádný klíč není nepoužitý (mimo KEEP)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import i18n_check as chk  # noqa: E402

LANGS = chk.load_langs()


def test_same_keys_in_all_languages():
    assert len(LANGS) >= 2 and {"en", "cs"} <= set(LANGS)
    assert chk.missing_keys(LANGS) == {}


def test_same_placeholders():
    assert chk.placeholder_mismatch(LANGS) == []


def test_no_unused_keys():
    """Nový klíč musí být použit; smazaný kód nesmí nechat osiřelé texty. Skládaný klíč s neznámým prefixem
    patří do `MANUAL_PREFIXES`, jinak do `KEEP` (s důvodem)."""
    assert chk.unused_keys(LANGS) == []


def test_keep_has_only_existing_keys():
    assert set(chk.KEEP) <= set(LANGS["en"]), "KEEP obsahuje klíč, který už neexistuje"
    assert all(chk.KEEP.values()) and all(chk.MANUAL_PREFIXES.values())


def test_metadata_never_unused():
    assert not [k for k in chk.unused_keys(LANGS) if k.startswith("_")]
