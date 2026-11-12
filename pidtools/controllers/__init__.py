"""
Profily regulátorů (E1, E7, docs/cs/regulatory.md): soubory `.pidctrl` (JSON s `format` a `version`), jejich kontrola,
knihovna (předvolby + vlastní), jednotky parametrů a mapování kanonického PID na profil.

Balíček je list vrstev: nezávisí na zbytku `pidtools` (jen standardní knihovna), takže ho smí importovat `core`.
Předvolby dodané s aplikací jsou v `presets/`. Obecný regulátor, který profil vykonává, je `pidtools.core.controller`.
"""
from .library import Library, ProfileError, default_dir, dumps, summary, validate_profile
from .loader import FORMAT, VERSION, load_preset, load_profile, parse_profile, presets
from .mapping import canonical_to_profile, profile_to_canonical

__all__ = ["FORMAT", "VERSION", "Library", "ProfileError", "canonical_to_profile", "default_dir", "dumps",
           "load_preset", "load_profile", "parse_profile", "presets", "profile_to_canonical", "summary",
           "validate_profile"]
