"""
Zpět / znovu pro změny nastavení smyčky (FEATURE-006). Zásobník patří projektu (`Project.history`), neukládá se do
souboru projektu a zaniká s pracovním prostorem.

Krok nese jen rozdíl: hodnoty změněných klíčů nastavení před a po (`MISSING` = klíč před změnou / po ní neexistoval)
a u změny úseku identifikace dvojici `rng_before` / `rng_after`. Krok patří smyčce s indexem `loop`; návrat se
aplikuje na ni, i když je mezitím aktivní jiná. Zásobník se nemaže při přepnutí aktivní smyčky (krok index nese),
maže se tam, kde se mění stav, který krok nezná (načtení dat, projektu, sloupců, identifikace, hromadné akce,
odebrání smyčky) – viz `CLEARING` pro cesty API.

Po sobě jdoucí změny téhož souboru klíčů do `MERGE_S` sekund se sloučí do jednoho kroku (before z prvního, after
z posledního), takže tažení posuvníku nebo psaní čísla nezaplní zásobník. Po `undo` se při nové změně `redo` maže.
"""
import copy
import re
import time
from dataclasses import dataclass, field
from typing import Any

from .. import i18n
from . import project as prj

LIMIT = 50                  # nejvyšší počet kroků v zásobníku
MERGE_S = 2.0               # změny téhož klíče v tomto odstupu [s] jsou jeden krok
SIM_SP = "sim_sp"           # SP scénáře není v nastavení, ale atribut smyčky: v kroku vystupuje jako pseudo-klíč
RNG = "@rng"                # pseudo-klíč změny úseku (jen pro porovnání množin klíčů při sloučení)


class _Missing:
    """Hodnota „klíč neexistuje“ (jiná než None, která je platná hodnota nastavení)."""
    def __repr__(self):
        return "MISSING"

    def __deepcopy__(self, memo):
        return self


MISSING: Any = _Missing()

# klíče, které jsou jen stav rozhraní nebo se zapisují samy (historie, záznamy) – změna přes PATCH krok nevytvoří
UI_KEYS = frozenset({"dview", "mview", "diagview", "plot_h", "chart_tunit", "lang", "live_runs", "audit_loops", "vchar_last",
                     "tune_hist", "sim_len_u_set"})
UI_PREFIXES = ("method|", "batch_sug|")

# cesty API (za `/workspaces/{wid}/`), jejichž úspěšné volání zásobník vyprázdní: mění stav mimo krok (data, sloupce,
# zdroje, model, regulátor) nebo smyčky projektu. Zkoumá je middleware API (`api/__init__.py`).
CLEARING = re.compile(
    r"^(data/|layout$|columns$|range/common$|sources|time-grid$|loops/(\d+(/mapping)?|import)$|project$|autosave/restore$|"
    r"recent/[^/]+/open$|windows|model/|controller$|batch$|journal/[^/]+/restore$|opc/history$)")


class UndoError(Exception):
    """Návrat nejde provést; `status` je kód HTTP (409 = není co vracet / krok už neplatí)."""
    def __init__(self, status, text):
        super().__init__(text)
        self.status, self.text = status, text


@dataclass
class Step:
    loop: int                                   # index smyčky, ke které krok patří
    before: dict                                # {klíč: hodnota | MISSING} před změnou (SIM_SP: dvojice | None)
    after: dict                                 # totéž po změně (stejné klíče jako `before`)
    rng_before: tuple | None = None             # úsek identifikace před / po (jen u změny úseku)
    rng_after: tuple | None = None
    t: float = 0.0                              # čas poslední změny v kroku (pro sloučení)

    @property
    def keys(self):
        return frozenset(self.before) | ({RNG} if self.rng_before is not None else frozenset())

    @property
    def noop(self):
        return self.before == self.after and self.rng_before == self.rng_after


@dataclass
class Snap:
    """Stav smyčky před změnou (hluboká kopie nastavení)."""
    settings: dict
    sim_sp: Any
    rng: Any


def take(ws) -> Snap:
    """Snímek smyčky před zápisem; po zápisu se předá `History.record`."""
    rng = getattr(ws, "rng", None)
    return Snap(copy.deepcopy(ws.settings), getattr(ws, "sim_sp", None), None if rng is None else tuple(rng))


def is_ui_key(k):
    return k in UI_KEYS or str(k).startswith(UI_PREFIXES)


# ---- popisek kroku (krátký text pro `title` tlačítka; jazyk podle požadavku)
def _num(v):
    s = f"{float(v):.6g}".replace("-", "−")
    return s.replace(".", i18n.decimal())


def _val(v):
    if v is MISSING or v is None:
        return "—"
    if isinstance(v, bool):
        return "✓" if v else "✗"
    if isinstance(v, (int, float)):
        return _num(v)
    if isinstance(v, (list, tuple)):
        return "[" + "; ".join(_val(x) for x in v) + "]" if len(v) <= 4 and all(
            isinstance(x, (int, float)) for x in v) else f"[{len(v)}]"
    return str(v)


_SET_KEY = re.compile(r"^set([12])_(gain|ti|td)$")
_PARAM = {"gain": "Gain", "ti": "TI", "td": "TD"}


def _part(k, a, b):
    """Popis změny jednoho klíče: „Set 1 Gain −2 → −1.5“, „Robustness Ms 1.6 → 1.8“."""
    m = _SET_KEY.match(k)
    name = f"{i18n.T('set_' + m.group(1))} {_PARAM[m.group(2)]}" if m else (
        i18n.T("undo_scen_sp") if k == SIM_SP else
        i18n.T("undo_scen_rows") if k.startswith("scen_df|") else i18n.T("scenario") if k == "scen_kind" else i18n.T(k))
    if k.startswith("scen_df|"):
        return name
    return f"{name} {_val(a)} → {_val(b)}"


def label(step: Step) -> str:
    parts = []
    skip = set()
    if "scen_kind" in step.before:
        skip.add("scen2")                                  # druh scénáře zapisuje i `scen2`, popisek stačí jednou
    for k in sorted(step.before):
        if k in skip or k == "tune_hist" or k == "set2_defined" and any(_SET_KEY.match(x) for x in step.before) or k.endswith("|tend"):
            continue
        parts.append(_part(k, step.before[k], step.after[k]))
    if step.rng_before is not None and step.rng_after is not None:
        parts.insert(0, i18n.T("undo_segment", a=_num(step.rng_before[0]), b=_num(step.rng_before[1]),
                               c=_num(step.rng_after[0]), d=_num(step.rng_after[1])))
    if not parts:
        parts = [", ".join(sorted(step.before)) or "?"]
    return "; ".join(parts[:2]) + (f" (+{len(parts) - 2})" if len(parts) > 2 else "")


@dataclass
class History:
    undo: list[Step] = field(default_factory=list)
    redo: list[Step] = field(default_factory=list)
    clock: Any = time.monotonic                 # zdroj času [s]; testy ho podvrhují
    _last: Step | None = None                   # poslední zapsaný krok (jen na ten se sloučí další změna)

    def clear(self):
        self.undo.clear()
        self.redo.clear()
        self._last = None

    # ---- zápis kroku
    def record(self, proj, snap: Snap, ws, skip=lambda k: False):
        """
        Porovná smyčku `ws` (aktivní smyčka projektu) se snímkem před zápisem a uloží rozdíl jako krok. Beze změny
        hodnot krok nevznikne. Klíče, pro které `skip(klíč)` platí, se nezapisují.
        """
        before, after = {}, {}
        for k in set(snap.settings) | set(ws.settings):
            if skip(k):
                continue
            a, b = snap.settings.get(k, MISSING), ws.settings.get(k, MISSING)
            if a != b:
                before[k], after[k] = a, copy.deepcopy(b)
        sp = getattr(ws, "sim_sp", None)
        if snap.sim_sp != sp:
            before[SIM_SP], after[SIM_SP] = snap.sim_sp, sp
        rng = getattr(ws, "rng", None)
        rb, ra = (snap.rng, tuple(rng)) if rng is not None and snap.rng != tuple(rng) else (None, None)
        step = Step(proj.active, before, after, rb, ra)
        if step.noop or (not before and rb is None):
            return None
        now = self.clock()
        top = self.undo[-1] if self.undo else None
        if top is not None and top is self._last and top.loop == step.loop and top.keys == step.keys \
                and now - top.t <= MERGE_S:
            top.after, top.rng_after, top.t = step.after, step.rng_after, now      # before a rng_before zůstávají z prvního
            if top.noop:                                                           # výsledek je původní stav: krok zaniká
                self.undo.pop()
                self._last = None
            self.redo.clear()
            return top
        step.t = now
        self.undo.append(step)
        del self.undo[:-LIMIT]
        self.redo.clear()
        self._last = step
        return step

    # ---- návrat
    def labels(self, proj):
        """(popisek posledního kroku zpět, popisek kroku znovu); u kroku jiné než aktivní smyčky se přidá její název."""
        def one(stack):
            if not stack:
                return None
            s = stack[-1]
            names = proj.names()
            return label(s) + (f" · {names[s.loop]}" if s.loop != proj.active and s.loop < len(names) else "")
        return one(self.undo), one(self.redo)

    def pop(self, proj, redo: bool):
        """Provede poslední krok zpět (`redo=False`) nebo znovu; vrací ho. Chyba = `UndoError` (409), zásobníky se
        nezmění, jen krok, který už nejde použít (smyčka zanikla, hodnoty neprojdou kontrolou), se zahodí."""
        src, dst = (self.redo, self.undo) if redo else (self.undo, self.redo)
        if not src:
            raise UndoError(409, "nothing to redo" if redo else "nothing to undo")
        step = src[-1]
        try:
            self._apply(proj, step, step.after if redo else step.before, step.rng_after if redo else step.rng_before)
        except UndoError:
            src.pop()                                                  # krok se přeskočí
            self._last = None
            raise
        src.pop()
        dst.append(step)
        del dst[:-LIMIT]
        self._last = None                                              # po návratu se další změna se stejným klíčem neslučuje
        return step

    @staticmethod
    def _apply(proj, step, values, rng):
        if not 0 <= step.loop < len(proj.loops):
            raise UndoError(409, "the loop of this step no longer exists")
        ws = proj.loops[step.loop]
        patch = {k: v for k, v in values.items() if v is not MISSING and k != SIM_SP}
        errs = prj.validate_settings(patch, ws.settings)               # stejná kontrola jako u běžné změny
        if errs:
            raise UndoError(409, f"step skipped, value no longer valid: {errs[0]}")
        if rng is not None:
            if not ws.has_data or not 0 <= rng[0] < rng[1] <= float(ws.t[-1]) + 1e-9:
                raise UndoError(409, "step skipped, segment is outside the record")
        for k, v in values.items():
            if k == SIM_SP:
                ws.sim_sp = None if v is None else tuple(v)
            elif v is MISSING:
                ws.settings.pop(k, None)
            else:
                ws.settings[k] = copy.deepcopy(v)
        if rng is not None:
            ws.rng = tuple(rng)
