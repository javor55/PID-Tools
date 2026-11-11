"""
Profily regulátorů (E1, docs/cs/regulatory.md): soubory `.pidctrl` (JSON s `format` a `version`) a jejich načtení.

Balíček je list vrstev: nezávisí na zbytku `pidtools` (jen standardní knihovna), takže ho smí importovat `core`.
Předvolby dodané s aplikací jsou v `presets/`. Obecný regulátor, který profil vykonává, je `pidtools.core.controller`.
"""
from .loader import FORMAT, VERSION, load_preset, load_profile, parse_profile, presets

__all__ = ["FORMAT", "VERSION", "load_preset", "load_profile", "parse_profile", "presets"]
