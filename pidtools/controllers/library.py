"""
Knihovna profilů (docs/cs/regulatory.md § 8): dodané předvolby (jen ke čtení) + vlastní profily ve složce uživatele,
kontrola profilu s užitečnými hláškami, uložení a načtení `.pidctrl`.

Složka vlastních profilů: proměnná prostředí `PIDTOOLS_CONTROLLERS_DIR`, jinak uživatelská konfigurační složka
(Windows `%APPDATA%\\pidtools\\controllers`, macOS `~/Library/Application Support/pidtools/controllers`, jinak
`$XDG_CONFIG_HOME` nebo `~/.config`). Soubor se jmenuje `<id>.pidctrl`.
"""
import copy
import json
import os
import re
import sys
import unicodedata

from . import units
from .loader import FORMAT, VERSION, load_preset, parse_profile, presets

__all__ = ["Library", "ProfileError", "default_dir", "dumps", "summary", "validate_profile"]

ENV_DIR = "PIDTOOLS_CONTROLLERS_DIR"
EXT = ".pidctrl"
_ID = re.compile(r"^[a-z0-9][a-z0-9_\-]{0,63}$")
_KIND = {"Kc": "gain", "Kp": "gain", "Ti": "integral", "Td": "derivative", "N": "filter"}


class ProfileError(ValueError):
    """Neplatný profil; `problems` = [{path, message}] (cesta k položce, např. 'params[2].range')."""

    def __init__(self, problems):
        self.problems = problems
        super().__init__("; ".join(f"{p['path']}: {p['message']}" if p["path"] else p["message"] for p in problems))


def default_dir():
    """Složka vlastních profilů (viz modul)."""
    if os.environ.get(ENV_DIR):
        return os.environ[ENV_DIR]
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "pidtools", "controllers")


def validate_profile(data):
    """Kontrola profilu (schéma); vrací seznam problémů [{path, message}], prázdný = platný. Neověřuje názvy částí
    v registrech `core.controller` (to dělá překlad `Profile`)."""
    try:
        data = parse_profile(data)
    except ValueError as ex:
        return [dict(path="", message=str(ex))]
    bad = []

    def add(path, msg):
        bad.append(dict(path=path, message=msg))

    if not isinstance(data["id"], str) or not _ID.match(data["id"]):
        add("id", "id musí být malá písmena, číslice, '_' nebo '-' (max. 64 znaků)")
    if not isinstance(data.get("name", ""), str) or not data.get("name"):
        add("name", "chybí název profilu")
    if not isinstance(data["structure"], dict):
        add("structure", "struktura musí být objekt")
    ver = data.get("verification")
    if ver is not None and (not isinstance(ver, dict) or ver.get("status") not in ("verified", "unverified")):
        add("verification.status", "stav ověření je 'verified' nebo 'unverified'")
    if not isinstance(data["params"], list):
        add("params", "parametry musí být seznam")
        return bad
    keys = []
    for i, p in enumerate(data["params"]):
        at = f"params[{i}]"
        if not isinstance(p, dict) or not isinstance(p.get("key"), str) or not isinstance(p.get("role"), str):
            add(at, "parametr musí mít textové položky 'key' a 'role'")
            continue
        keys.append(p["key"])
        rng = p.get("range")
        if rng is not None and not (isinstance(rng, list) and len(rng) == 2 and all(isinstance(x, (int, float)) for x in rng)
                                    and rng[0] <= rng[1]):
            add(f"{at}.range", "rozsah musí být [min, max] s min ≤ max")
        rep = p.get("repr")
        if rep is not None:
            kind = _KIND.get(p["role"])
            if kind is None:
                add(f"{at}.repr", f"role '{p['role']}' nemá jednotky k výběru")
            elif rep not in units.REPRS[kind]:
                add(f"{at}.repr", f"neznámá varianta '{rep}' (známé: {', '.join(units.REPRS[kind])})")
    if len(set(keys)) != len(keys):
        add("params", "klíče parametrů musí být jedinečné")
    return bad


def check(data):
    """Vrátí platný profil převedený na aktuální verzi, jinak ProfileError s problémy."""
    bad = validate_profile(data)
    if bad:
        raise ProfileError(bad)
    return parse_profile(data)


def dumps(data):
    """Profil jako text souboru `.pidctrl` (JSON)."""
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def summary(data, tag):
    """Řádek seznamu knihovny: id, výrobce, název, štítek (preset / custom), příznak ověření."""
    return dict(id=data["id"], vendor=data.get("vendor", ""), name=data.get("name", data["id"]), tag=tag,
                verified=(data.get("verification") or {}).get("status") == "verified")


def _slug(name):
    plain = unicodedata.normalize("NFKD", name.lower()).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9]+", "_", plain).strip("_")
    return s[:48] or "profil"


class Library:
    """Předvolby (jen ke čtení) a vlastní profily ve složce `folder` (výchozí `default_dir()`)."""

    def __init__(self, folder=None):
        self.folder = folder or default_dir()

    def _path(self, pid):
        return os.path.join(self.folder, pid + EXT)

    def custom_ids(self):
        if not os.path.isdir(self.folder):
            return []
        return sorted(f[:-len(EXT)] for f in os.listdir(self.folder) if f.endswith(EXT))

    def is_preset(self, pid):
        return pid in presets()

    def list(self):
        out = [summary(load_preset(i), "preset") for i in presets()]
        for i in self.custom_ids():
            try:
                out.append(summary(self.get(i), "custom"))
            except (ValueError, OSError):
                continue                                  # poškozený soubor knihovnu nerozbije
        return out

    def get(self, pid):
        """Profil podle id (kopie); KeyError, když neexistuje."""
        if pid in presets():
            return copy.deepcopy(load_preset(pid))
        if pid not in self.custom_ids():
            raise KeyError(pid)
        with open(self._path(pid), encoding="utf-8") as f:
            return parse_profile(json.load(f))

    def _new_id(self, name):
        base = "custom_" + _slug(name)
        taken = set(presets()) | set(self.custom_ids())
        pid, n = base, 2
        while pid in taken:
            pid, n = f"{base}_{n}", n + 1
        return pid

    def _write(self, data):
        os.makedirs(self.folder, exist_ok=True)
        with open(self._path(data["id"]), "w", encoding="utf-8") as f:
            f.write(dumps(data))

    def create_custom(self, source_id, name=None):
        """„Vytvořit vlastní“: kopie předvolby / vlastního profilu pod novým id; vlastní profil je vždy neověřený."""
        data = self.get(source_id)
        data["name"] = name or f"{data.get('name', source_id)} (vlastní)"
        data["id"] = self._new_id(data["name"])
        data["derived_from"] = source_id
        data["verification"] = dict(status="unverified", note="Vlastní profil – neověřeno proti manuálu.")
        data.pop("test", None)
        self._write(check(data))
        return data

    def update(self, pid, data):
        """Změní vlastní profil (id zůstává); předvolbu nelze měnit (PermissionError)."""
        if self.is_preset(pid):
            raise PermissionError(pid)
        if pid not in self.custom_ids():
            raise KeyError(pid)
        data = dict(data, id=pid)
        self._write(check(data))
        return data

    def delete(self, pid):
        if self.is_preset(pid):
            raise PermissionError(pid)
        if pid not in self.custom_ids():
            raise KeyError(pid)
        os.remove(self._path(pid))

    def import_profile(self, data):
        """Import `.pidctrl`: id zůstane, kolidující (s předvolbou / vlastním) dostane nové; štítek je vždy custom."""
        data = copy.deepcopy(check(data))
        if data["id"] in presets() or data["id"] in self.custom_ids():
            data["id"] = self._new_id(data.get("name", data["id"]))
        self._write(data)
        return data

    def export_profile(self, pid):
        """Text souboru `.pidctrl` s hlavičkou `format` / `version` (aktuální)."""
        data = self.get(pid)
        data["format"], data["version"] = FORMAT, VERSION
        return dumps(data)
