"""
Záchranná kopie projektu (autosave) a seznam nedávných projektů (E10-B) ve složce uživatelských dat: `PIDTOOLS_DATA_DIR`,
jinak `pidtools` v datové složce uživatele (Windows `%LOCALAPPDATA%`, macOS `~/Library/Application Support`, jinak
`$XDG_DATA_HOME` nebo `~/.local/share`). V týmovém režimu po uživatelích (stejné dělení jako nastavení).
Kopie je jeden soubor `recovery.pidproj` s popisem `recovery.json`; nedávné projekty jsou kopie souborů `.pidproj`
(`recent/<id>.pidproj`) a seznam `recent.json` (nejvýš MAX_RECENT, stejný název nahradí starší).
"""
import json
import os
import secrets
import sys
import time

from .appsettings import user_dir

ENV_DIR = "PIDTOOLS_DATA_DIR"
MAX_RECENT = 8
MAX_SNAPSHOT = 64 * 2 ** 20


def data_dir():
    if os.environ.get(ENV_DIR):
        return os.environ[ENV_DIR]
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(base, "pidtools")


def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data if isinstance(data, bytes) else data.encode("utf-8"))
    os.replace(tmp, path)


def _read_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


class UserData:
    """Záchranná kopie a nedávné projekty jednoho uživatele (nebo desktopu, když `user` je None)."""

    def __init__(self, base=None):
        self.base = base or data_dir()

    def dir(self, user=None):
        return user_dir(self.base, user)

    # ---- záchranná kopie
    def save_recovery(self, raw, meta, user=None):
        d = self.dir(user)
        meta = dict(meta, at=time.time(), bytes=len(raw))
        _write(os.path.join(d, "recovery.pidproj"), raw)
        _write(os.path.join(d, "recovery.json"), json.dumps(meta))
        return meta

    def recovery(self, user=None):
        """Popis záchranné kopie (`at`, `name`, `loops`, `bytes`), nebo None."""
        d = self.dir(user)
        meta = _read_json(os.path.join(d, "recovery.json"), None)
        if not meta or not os.path.isfile(os.path.join(d, "recovery.pidproj")):
            return None
        return meta

    def recovery_raw(self, user=None):
        with open(os.path.join(self.dir(user), "recovery.pidproj"), "rb") as f:
            return f.read()

    def clear_recovery(self, user=None):
        for n in ("recovery.pidproj", "recovery.json"):
            try:
                os.remove(os.path.join(self.dir(user), n))
            except OSError:
                pass

    # ---- nedávné projekty
    def _list_path(self, user):
        return os.path.join(self.dir(user), "recent.json")

    def recent(self, user=None):
        out = [e for e in _read_json(self._list_path(user), []) if isinstance(e, dict) and e.get("id")]
        return sorted(out, key=lambda e: -e.get("at", 0))

    def add_recent(self, raw, name, loops, user=None):
        """Zapíše projekt mezi nedávné (kopie souboru, pokud není větší než MAX_SNAPSHOT); vrací položku."""
        keep = []
        for e in self.recent(user):
            if e.get("name") == name:
                self._drop_file(e["id"], user)
            else:
                keep.append(e)
        rid = secrets.token_hex(6)
        snap = len(raw) <= MAX_SNAPSHOT
        if snap:
            _write(os.path.join(self.dir(user), "recent", rid + ".pidproj"), raw)
        e = dict(id=rid, name=name, at=time.time(), loops=int(loops), bytes=len(raw), snapshot=snap)
        keep.insert(0, e)
        for old in keep[MAX_RECENT:]:
            self._drop_file(old["id"], user)
        _write(self._list_path(user), json.dumps(keep[:MAX_RECENT]))
        return e

    def _drop_file(self, rid, user):
        try:
            os.remove(os.path.join(self.dir(user), "recent", rid + ".pidproj"))
        except OSError:
            pass

    def recent_raw(self, rid, user=None):
        """Obsah kopie nedávného projektu; KeyError, když položka nebo kopie neexistuje."""
        if not any(e["id"] == rid and e.get("snapshot") for e in self.recent(user)):
            raise KeyError(rid)
        with open(os.path.join(self.dir(user), "recent", rid + ".pidproj"), "rb") as f:
            return f.read()

    def remove_recent(self, rid, user=None):
        items = self.recent(user)
        rest = [e for e in items if e["id"] != rid]
        if len(rest) == len(items):
            return False
        self._drop_file(rid, user)
        _write(self._list_path(user), json.dumps(rest))
        return True


class NullUserData(UserData):
    """Veřejný režim: nic se neukládá (žádná záchranná kopie ani nedávné projekty), na disk se nesahá."""

    def __init__(self):
        super().__init__(base="")

    def save_recovery(self, raw, meta, user=None):
        return dict(meta, at=time.time(), bytes=len(raw))

    def recovery(self, user=None):
        return None

    def recovery_raw(self, user=None):
        raise KeyError("recovery")

    def clear_recovery(self, user=None):
        pass

    def recent(self, user=None):
        return []

    def add_recent(self, raw, name, loops, user=None):
        return None

    def recent_raw(self, rid, user=None):
        raise KeyError(rid)

    def remove_recent(self, rid, user=None):
        return False
