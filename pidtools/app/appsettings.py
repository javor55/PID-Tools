"""
Globální nastavení aplikace (E10-B): jeden soubor JSON v uživatelské konfigurační složce (desktop) nebo po uživatelích
(týmový režim); `format` / `version` pro pozdější migrace. Platí pro všechny projekty; projekt může prahy diagnostiky
přepsat vlastními (`tri_thr`). Soubor nenese tajemství – připojení OPC / historian jen jako adresy (endpointy).

Složka: proměnná `PIDTOOLS_CONFIG_DIR`, jinak `pidtools` v konfigurační složce uživatele (Windows `%APPDATA%`,
macOS `~/Library/Application Support`, jinak `$XDG_CONFIG_HOME` nebo `~/.config`). Logo reportu je soubor vedle nastavení.
"""
import copy
import hashlib
import json
import os
import re
import sys

from . import triage

FORMAT, VERSION = "pidtools.settings", 1
ENV_DIR = "PIDTOOLS_CONFIG_DIR"
FILE = "settings.json"
LOGO_EXTS = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "svg": "image/svg+xml"}   # svg: jen čtení starých souborů
UPLOAD_LOGO_EXTS = ("png", "jpg", "jpeg")                  # nově se přijímá jen rastr (SVG může nést skripty)
MAX_LOGO = 1_000_000
_ID = re.compile(r"^[a-z0-9][a-z0-9_\-]{0,63}$")

DEFAULTS = {
    "general": {"autosave_min": 1, "embed_data": True},
    "appearance": {"language": "", "theme": "", "font_size": "m"},
    "charts": {"height": 220, "time_unit": "auto", "decimal": "auto", "ti_unit": "s", "gain_view": "kc"},
    "diagnostics": {"thresholds": {}},
    "defaults": {"controller": "pcs7_pidconl", "sim": {"ctype": "PI", "opt_ms": 1.6, "opt_ovs": 2, "opt_robust": False}},
    "journal": {"author": "", "require_note": False},
    "report": {"company": "", "language": "app", "header": "", "footer": "", "logo": ""},
    "connections": {"opc": [], "historians": {"pcs7": "", "deltav": "", "pi": ""}},
    "controller_tests": {},
}
CHOICES = {
    ("general", "autosave_min"): (0, 1, 5, 15, 30), ("appearance", "language"): ("", "cs", "en"),
    ("appearance", "theme"): ("", "system", "light", "dark"), ("appearance", "font_size"): ("s", "m", "l", "xl"),
    ("charts", "time_unit"): ("auto", "s", "min", "h", "clock"), ("charts", "decimal"): ("auto", "comma", "dot"),
    ("charts", "ti_unit"): ("s", "min"), ("charts", "gain_view"): ("kc", "pb"),
    ("report", "language"): ("app", "cs", "en"),
}
SIM_CTYPES = ("PI", "PID", "PD")
MAX_OPC = 20


def config_dir():
    """Základní konfigurační složka aplikace (viz modul)."""
    if os.environ.get(ENV_DIR):
        return os.environ[ENV_DIR]
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "pidtools")


def user_dir(base, user=None):
    """Složka uživatele: bez uživatele (desktop) přímo `base`, v týmovém režimu `base/users/<jméno>-<otisk>`."""
    if user is None:
        return base
    slug = re.sub(r"[^A-Za-z0-9._-]", "_", str(user))[:40].strip(".") or "u"
    return os.path.join(base, "users", f"{slug}-{hashlib.sha256(str(user).encode()).hexdigest()[:8]}")


def _num(v, lo, hi, default, cast=float):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v:
        return default
    return cast(min(max(v, lo), hi))


def _text(v, n):
    return v.strip()[:n] if isinstance(v, str) else ""


def _opc(items):
    out, seen = [], set()
    for it in items if isinstance(items, list) else []:
        if not isinstance(it, dict):
            continue
        url, name = _text(it.get("url"), 300), _text(it.get("name"), 80)
        if not name or not url.lower().startswith("opc.tcp://") or name in seen:
            continue
        seen.add(name)
        out.append({"name": name, "url": url})
    return out[:MAX_OPC]


def _memos(d):
    out = {}
    for k, v in (d if isinstance(d, dict) else {}).items():
        if isinstance(k, str) and _ID.match(k) and isinstance(v, dict):
            out[k] = {"verdict": _text(v.get("verdict"), 40), "text": _text(v.get("text"), 300), "at": _text(v.get("at"), 40),
                      **{n: _num(v.get(n), 0, 999, 0, int) for n in ("ok", "warn", "fail")}}
    return out


def normalize(raw):
    """Libovolný slovník → platné nastavení: neznámé položky se zahodí, špatné hodnoty nahradí výchozí, čísla se ořežou."""
    raw = raw if isinstance(raw, dict) else {}
    out = copy.deepcopy(DEFAULTS)

    def sec(name):
        v = raw.get(name)
        return v if isinstance(v, dict) else {}

    for (s, k), allowed in CHOICES.items():
        v = sec(s).get(k)
        if v in allowed and not isinstance(v, bool):
            out[s][k] = v
    g, c = sec("general"), sec("charts")
    out["general"]["embed_data"] = g["embed_data"] if isinstance(g.get("embed_data"), bool) else True
    out["charts"]["height"] = _num(c.get("height"), 120, 1000, 220, int)
    out["diagnostics"]["thresholds"] = triage.merge_thresholds(sec("diagnostics").get("thresholds"))
    d = sec("defaults")
    ctl = d.get("controller")
    out["defaults"]["controller"] = ctl if isinstance(ctl, str) and _ID.match(ctl) else DEFAULTS["defaults"]["controller"]
    sim = d.get("sim") if isinstance(d.get("sim"), dict) else {}
    o = out["defaults"]["sim"]
    o["ctype"] = sim.get("ctype") if sim.get("ctype") in SIM_CTYPES else "PI"
    o["opt_ms"] = _num(sim.get("opt_ms"), 1.1, 2.5, 1.6)
    o["opt_ovs"] = _num(sim.get("opt_ovs"), 0, 50, 2, int)
    o["opt_robust"] = sim.get("opt_robust") is True
    j, r = sec("journal"), sec("report")
    out["journal"] = {"author": _text(j.get("author"), 80), "require_note": j.get("require_note") is True}
    logo = r.get("logo")
    out["report"].update(company=_text(r.get("company"), 120), header=_text(r.get("header"), 300), footer=_text(r.get("footer"), 300),
                         logo=logo if isinstance(logo, str) and re.fullmatch(r"logo\.(png|jpg|jpeg|svg)", logo) else "")
    conn = sec("connections")
    out["connections"]["opc"] = _opc(conn.get("opc"))
    hist = conn.get("historians") if isinstance(conn.get("historians"), dict) else {}
    for k in out["connections"]["historians"]:
        out["connections"]["historians"][k] = _text(hist.get(k), 300)
    out["controller_tests"] = _memos(raw.get("controller_tests"))
    return out


def export_text(settings):
    return json.dumps(dict(format=FORMAT, version=VERSION, settings=settings), ensure_ascii=False, indent=1)


def parse_export(text):
    """Text souboru nastavení → nastavení (ValueError při cizím formátu nebo novější verzi)."""
    try:
        data = json.loads(text)
    except (ValueError, TypeError) as ex:
        raise ValueError(f"not JSON: {ex}") from ex
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise ValueError("not a PID Tools settings file")
    if not isinstance(data.get("version"), int) or data["version"] > VERSION:
        raise ValueError("unsupported settings version")
    return normalize(data.get("settings"))


class SettingsStore:
    """Soubor nastavení (+ logo) po uživatelích; bez uživatele (desktop) přímo v konfigurační složce."""

    def __init__(self, base=None):
        self.base = base or config_dir()

    def dir(self, user=None):
        return user_dir(self.base, user)

    def load(self, user=None):
        try:
            with open(os.path.join(self.dir(user), FILE), encoding="utf-8") as f:
                return normalize(json.load(f).get("settings"))
        except (OSError, ValueError, AttributeError):
            return normalize({})

    def save(self, settings, user=None):
        s = normalize(settings)
        d = self.dir(user)
        os.makedirs(d, exist_ok=True)
        tmp = os.path.join(d, FILE + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(dict(format=FORMAT, version=VERSION, settings=s), f, ensure_ascii=False, indent=1)
        os.replace(tmp, os.path.join(d, FILE))
        return s

    def reset(self, user=None):
        self.clear_logo(user)
        return self.save({}, user)

    # ---- logo reportu
    def logo_path(self, user=None):
        name = self.load(user)["report"]["logo"]
        p = os.path.join(self.dir(user), name) if name else ""
        return p if p and os.path.isfile(p) else None

    def clear_logo(self, user=None):
        for e in LOGO_EXTS:
            try:
                os.remove(os.path.join(self.dir(user), f"logo.{e}"))
            except OSError:
                pass

    def put_logo(self, data, ext, user=None):
        """Uloží logo (png / jpg do 1 MB; SVG ne – může nést skripty) a zapíše jeho název do nastavení; vrací nové nastavení."""
        ext = ext.lower().lstrip(".")
        if ext not in UPLOAD_LOGO_EXTS:
            raise ValueError("logo must be png or jpg")
        if not data or len(data) > MAX_LOGO:
            raise ValueError("logo is empty or larger than 1 MB")
        self.clear_logo(user)
        os.makedirs(self.dir(user), exist_ok=True)
        with open(os.path.join(self.dir(user), f"logo.{ext}"), "wb") as f:
            f.write(data)
        s = self.load(user)
        s["report"]["logo"] = f"logo.{ext}"
        return self.save(s, user)

    def drop_logo(self, user=None):
        self.clear_logo(user)
        s = self.load(user)
        s["report"]["logo"] = ""
        return self.save(s, user)


class MemorySettingsStore(SettingsStore):
    """
    Veřejný režim: nastavení jen v paměti po relacích, nikdy na disk (bez loga a bez připojení k OPC / historianům;
    velikost omezuje `normalize`). `drop(user)` při vypršení relace.
    """

    def __init__(self):
        super().__init__(base="")
        self._d = {}

    def load(self, user=None):
        return normalize(self._d.get(user))

    def save(self, settings, user=None):
        s = normalize(settings)
        s["connections"] = copy.deepcopy(DEFAULTS["connections"])
        s["report"]["logo"] = ""
        self._d[user] = s
        return s

    def reset(self, user=None):
        self._d.pop(user, None)
        return self.load(user)

    def logo_path(self, user=None):
        return None

    def clear_logo(self, user=None):
        pass

    def put_logo(self, data, ext, user=None):
        raise ValueError("logo_disabled")

    def drop_logo(self, user=None):
        return self.load(user)

    def drop(self, user):
        self._d.pop(user, None)


def new_project_defaults(settings, controller=None):
    """
    Výchozí hodnoty pro nový projekt / smyčku z nastavení: `controller` (profil, který `Project` vloží do nové smyčky;
    None = výchozí PIDConL), `settings` (volby simulace a ladění smyčky), `tri_thr` (prahy diagnostiky, jen když se liší).
    """
    sim = settings["defaults"]["sim"]
    thr = settings["diagnostics"]["thresholds"]
    return {"controller": controller,
            "settings": dict(ctype=sim["ctype"], opt_ms=sim["opt_ms"], opt_ovs=sim["opt_ovs"], opt_robust=sim["opt_robust"]),
            "tri_thr": None if thr == triage.default_thresholds() else json.dumps(thr)}
