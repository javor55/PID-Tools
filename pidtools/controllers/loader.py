"""Načtení a kontrola profilu regulátoru (formát `.pidctrl`, JSON se `format` a `version`)."""
import json
import os

FORMAT = "pidctrl"
VERSION = 1                      # aktuální verze formátu; starší se převádějí řetězcem MIGRATIONS (verze → funkce)
PRESETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "presets")

MIGRATIONS = {}                  # {stará verze: funkce(profil) → profil o verzi výš}; zatím jen verze 1

_cache = {}


def parse_profile(data):
    """Zkontroluje slovník profilu (format, version, struktura, parametry) a vrátí ho převedený na aktuální verzi."""
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise ValueError(f"není profil regulátoru (chybí format = '{FORMAT}')")
    ver = data.get("version")
    if not isinstance(ver, int) or ver < 1:
        raise ValueError("profil regulátoru nemá platnou verzi")
    if ver > VERSION:
        raise ValueError(f"profil verze {ver} je novější než podporovaná {VERSION} – aktualizujte aplikaci")
    while ver < VERSION:
        data = MIGRATIONS[ver](data)
        ver = data["version"]
    for k in ("id", "structure", "params"):
        if k not in data:
            raise ValueError(f"profil regulátoru nemá položku '{k}'")
    roles = [p.get("role") for p in data["params"]]
    if len(set(roles)) != len(roles) or not all(isinstance(r, str) for r in roles):
        raise ValueError("role parametrů profilu musí být jedinečné")
    return data


def load_profile(path):
    """Načte profil ze souboru `.pidctrl` / `.json`."""
    with open(path, encoding="utf-8") as f:
        return parse_profile(json.load(f))


def presets():
    """Identifikátory dodaných předvoleb."""
    return sorted(f[:-5] for f in os.listdir(PRESETS) if f.endswith(".json"))


def load_preset(pid):
    """Dodaná předvolba podle id (např. 'pcs7_pidconl'); načtená jednou, vrací sdílený (nemeňte ho) slovník."""
    if pid not in _cache:
        _cache[pid] = load_profile(os.path.join(PRESETS, f"{pid}.json"))
    return _cache[pid]
