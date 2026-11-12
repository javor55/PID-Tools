"""
Snímek deníku ladění (plán v2, E10): neměnný záznam stavu jedné smyčky (data, mapování, modely, regulátor, nastavení bloku,
sady, metoda, scénář, výsledky, APC) s verzí formátu. Obsah (`content`) se po vytvoření nemění a hlídá ho otisk SHA-256;
měnit se smí jen to, co vzniká v čase: stav (Návrh → Nasazeno → Ověřeno / Zamítnuto) s historií, poznámky a přílohy.
Soubor projektu nese snímky v klíči `journal` (formát `pidtools.journal.snapshot`, verze 1).
"""
import copy
import hashlib
import json
from dataclasses import dataclass, field

from ...i18n import T

FORMAT = "pidtools.journal.snapshot"
VERSION = 1
STATUSES = ("draft", "deployed", "verified", "rejected")
KINDS = ("manual", "restore", "live", "live_migrated")
_FROZEN = ("id", "loop", "v", "created", "author", "kind", "label", "app_version", "content", "sha256")


def _bad(what):
    return ValueError(T("err_project_format", what=what))


def content_hash(content):
    """SHA-256 kanonického JSON obsahu snímku."""
    return hashlib.sha256(json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                                     allow_nan=False).encode("utf-8")).hexdigest()


@dataclass
class Snapshot:
    id: str
    loop: str
    v: int
    created: str
    author: str
    content: dict
    kind: str = "manual"
    label: str = ""
    app_version: str = ""
    sha256: str = ""
    status: str = "draft"
    history: list = field(default_factory=list)       # [{status, when, author, note}]
    notes: list = field(default_factory=list)         # [{when, author, text}]
    attachments: list = field(default_factory=list)   # [{id, name, mime, size, when, author, desc, data (base64)}]

    def __post_init__(self):
        object.__setattr__(self, "content", copy.deepcopy(self.content))
        if not self.sha256:
            object.__setattr__(self, "sha256", content_hash(self.content))
        if self.status not in STATUSES:
            raise _bad("journal.status")
        object.__setattr__(self, "_ready", True)

    def __setattr__(self, k, v):
        if k in _FROZEN and getattr(self, "_ready", False):
            raise AttributeError(f"snapshot is immutable: {k}")
        object.__setattr__(self, k, v)

    @property
    def name(self):
        return f"{self.loop} v{self.v}"

    def verify(self):
        """Obsah odpovídá otisku (snímek nebyl upraven mimo aplikaci)."""
        return content_hash(self.content) == self.sha256

    def set_status(self, status, when, author, note=""):
        if status not in STATUSES:
            raise ValueError(T("err_journal_status", status=status))
        self.history.append(dict(status=status, when=when, author=author, note=note))
        self.status = status

    def to_dict(self, light=False):
        """Pro soubor projektu; `light` bez obsahu a dat příloh (seznam)."""
        d = dict(format=FORMAT, version=VERSION, id=self.id, loop=self.loop, v=self.v, created=self.created,
                 author=self.author, kind=self.kind, label=self.label, app_version=self.app_version, sha256=self.sha256,
                 status=self.status, history=copy.deepcopy(self.history), notes=copy.deepcopy(self.notes))
        if light:
            d["attachments"] = [{k: v for k, v in a.items() if k != "data"} for a in self.attachments]
        else:
            d["attachments"] = copy.deepcopy(self.attachments)
            d["content"] = copy.deepcopy(self.content)
        return d

    @classmethod
    def from_dict(cls, d):
        d = migrate_snapshot(d)
        try:
            return cls(id=str(d["id"]), loop=str(d["loop"]), v=int(d["v"]), created=str(d["created"]),
                       author=str(d.get("author") or "local"), content=dict(d["content"]),
                       kind=str(d.get("kind") or "manual"), label=str(d.get("label") or ""),
                       app_version=str(d.get("app_version") or ""), sha256=str(d.get("sha256") or ""),
                       status=str(d.get("status") or "draft"), history=list(d.get("history") or []),
                       notes=list(d.get("notes") or []), attachments=list(d.get("attachments") or []))
        except (KeyError, TypeError, ValueError) as ex:
            raise _bad("journal") from ex


STEPS = {}        # verze → funkce dict → dict (zatím je jen verze 1)


def migrate_snapshot(d):
    if not isinstance(d, dict) or d.get("format") != FORMAT:
        raise _bad("journal.format")
    v = int(d.get("version") or 1)
    if v > VERSION:
        raise ValueError(T("err_project_newer", v=v))
    while v < VERSION:
        d = STEPS[v](d)
        v = int(d["version"])
    return d
