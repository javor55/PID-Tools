"""
Obecný registr (plán v2, kap. 7): rozšíření = přidat položku, ne upravit kód na pěti místech.
Každá položka má id, klíč popisu v i18n, schéma parametrů a funkci; zdroje dat (app.domain.registry) a další
registry (metody ladění, formáty exportu …) ho používají stejně.
"""
from dataclasses import dataclass, field
from typing import Any, Callable

from ..i18n import T


@dataclass(frozen=True)
class Entry:
    id: str
    desc: str                                  # klíč popisu v pidtools/i18n/*.json
    fn: Callable
    params: dict = field(default_factory=dict)   # schéma parametrů {název: {"type", "default", "desc" (klíč i18n)}}
    meta: dict = field(default_factory=dict)     # další údaje položky registru (přípony souborů, ukázka pro test …)

    def describe(self):
        """Popis položky pro API / UI: id, text v aktuálním jazyce, schéma parametrů s přeloženými popisy."""
        params = {k: {**v, "desc": T(v["desc"]) if v.get("desc") else ""} for k, v in self.params.items()}
        return dict(id=self.id, description=T(self.desc), params=params)


class Registry:
    def __init__(self, name):
        self.name = name
        self._items: dict[str, Entry] = {}

    def register(self, id, desc, fn=None, params=None, **meta):
        """Zaregistruje položku; použití i jako dekorátor: `@REG.register("csv", "src_csv")`."""
        def add(f):
            if id in self._items:
                raise ValueError(f"{self.name}: duplicate id {id}")
            self._items[id] = Entry(id, desc, f, dict(params or {}), dict(meta))
            return f
        return add(fn) if fn is not None else add

    def get(self, id) -> Entry:
        try:
            return self._items[id]
        except KeyError:
            raise KeyError(f"{self.name}: unknown id {id}") from None

    def __contains__(self, id):
        return id in self._items

    def ids(self):
        return list(self._items)

    def items(self) -> list[Entry]:
        return list(self._items.values())

    def describe(self) -> list[dict[str, Any]]:
        return [e.describe() for e in self._items.values()]
