"""
Doménový model projektu (plán v2, E3): zdroje dat, mapování smyček a nastavení společné časové mřížky.

Jen popis, žádná data: dataclasses se (de)serializují do JSON slovníků s explicitním `format` a `version`
a nenesou pandas objekty ani pole numpy (data zdrojů drží běhová vrstva `app.workspace.sources`, do souboru
se ukládají vedle popisu zdroje jako `sources[i].data`).

    Project → Source[] (soubor / OPC, rozvržení, časové pásmo, posun, vlastní vzorkování)
            → LoopSpec[] (tag, popis, role → SourceRef, rozsahy NormPV / NormMV, kaskáda)
            → TimeGrid (překryv / sjednocení, ruční perioda, práh mezer)
"""
from dataclasses import dataclass, field

from ...i18n import T

FORMAT = "pidtools.project"
VERSION = 3                      # verze souboru projektu (v1, v2 = starší, otevírají se migrací – domain.migrate)

SOURCE_OPTIONS = ("layout", "time_fmt", "unit", "c_time", "c_tag", "c_val", "row_dt")   # čtení tabulky zdroje
ROLES = ("pv", "sp", "mv", "pos", "mode")                                                # role s jedním signálem
GRID_MODES = ("overlap", "union")


def _bad(what):
    return ValueError(T("err_project_format", what=what))


def _num(v, what, none=True):
    if v is None and none:
        return None
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise _bad(what)
    return float(v)


@dataclass
class DataRef:
    """Odkaz na data zdroje: kam patří (`file` – nahraný soubor, `opc` – záznam z OPC UA, `embedded` – uložená
    v projektu) a otisk pro kontrolu, že jde o tytéž hodnoty."""
    kind: str = "embedded"
    name: str = ""
    rows: int = 0
    sha256: str | None = None

    def to_dict(self):
        return dict(kind=self.kind, name=self.name, rows=self.rows, sha256=self.sha256)

    @classmethod
    def from_dict(cls, d):
        d = d or {}
        return cls(kind=str(d.get("kind", "embedded")), name=str(d.get("name", "")), rows=int(d.get("rows") or 0),
                   sha256=d.get("sha256"))


@dataclass
class Source:
    """Zdroj dat: soubor (CSV / XLSX / TXT) nebo záznam z OPC UA."""
    id: str
    name: str
    kind: str = "csv"                                    # id v registru zdrojů (domain.registry.SOURCES)
    options: dict = field(default_factory=dict)          # klíče SOURCE_OPTIONS (rozvržení, sloupce času, jednotka)
    timezone: str | None = None                          # časové pásmo hodin v souboru (IANA), None = UTC
    offset_s: float = 0.0                                # posun času zdroje [s] (kladný = záznam je později)
    sampling_s: float | None = None                      # vlastní perioda vzorkování [s] (bez času v souboru, mřížka)
    data: DataRef = field(default_factory=DataRef)

    def to_dict(self):
        return dict(id=self.id, name=self.name, kind=self.kind, options={k: v for k, v in self.options.items()
                                                                          if v is not None},
                    timezone=self.timezone, offset_s=self.offset_s, sampling_s=self.sampling_s,
                    data_ref=self.data.to_dict())

    @classmethod
    def from_dict(cls, d):
        if not isinstance(d, dict) or not d.get("id"):
            raise _bad("source")
        opt = d.get("options") or {}
        if not isinstance(opt, dict):
            raise _bad("source.options")
        return cls(id=str(d["id"]), name=str(d.get("name") or d["id"]), kind=str(d.get("kind") or "csv"),
                   options={k: opt[k] for k in SOURCE_OPTIONS if k in opt}, timezone=d.get("timezone") or None,
                   offset_s=_num(d.get("offset_s", 0.0), "source.offset_s", none=False),
                   sampling_s=_num(d.get("sampling_s"), "source.sampling_s"), data=DataRef.from_dict(d.get("data_ref")))


@dataclass(frozen=True)
class SourceRef:
    """Odkaz na sloupec zdroje: `zdroj › sloupec`. Jeden sloupec smí být v rolích více smyček."""
    source_id: str
    column: str

    def to_dict(self):
        return dict(source=self.source_id, column=self.column)

    @classmethod
    def from_dict(cls, d):
        if not isinstance(d, dict) or "source" not in d or "column" not in d:
            raise _bad("ref")
        return cls(str(d["source"]), str(d["column"]))

    def __str__(self):
        return f"{self.source_id}:{self.column}"

    @classmethod
    def parse(cls, text):
        """`zdroj:sloupec` (id zdroje nemá dvojtečku, sloupec ji mít smí)."""
        sid, sep, col = str(text).partition(":")
        if not sep or not sid or not col:
            raise _bad("ref")
        return cls(sid, col)


@dataclass
class Roles:
    """Role signálů smyčky: PV, SP, MV, poloha ventilu, režim AUTO / MAN a měřené poruchy DV."""
    pv: SourceRef | None = None
    sp: SourceRef | None = None
    mv: SourceRef | None = None
    pos: SourceRef | None = None
    mode: SourceRef | None = None
    dv: list[SourceRef] = field(default_factory=list)

    def refs(self):
        """Všechny použité odkazy (pořadí PV, SP, MV, poloha, režim, DV)."""
        return [r for r in (self.pv, self.sp, self.mv, self.pos, self.mode, *self.dv) if r is not None]

    def to_dict(self):
        out = {k: getattr(self, k).to_dict() if getattr(self, k) else None for k in ROLES}
        out["dv"] = [r.to_dict() for r in self.dv]
        return out

    @classmethod
    def from_dict(cls, d):
        d = d or {}
        kw = {k: SourceRef.from_dict(d[k]) if d.get(k) else None for k in ROLES}
        return cls(dv=[SourceRef.from_dict(x) for x in d.get("dv") or []], **kw)


@dataclass
class LoopSpec:
    """Popis smyčky: tag, popis, mapování rolí, rozsahy a vazba kaskády."""
    tag: str = ""
    description: str = ""
    roles: Roles = field(default_factory=Roles)
    norm_pv: tuple[float, float] | None = None           # NormPV (dolní, horní mez PV v jednotkách PV)
    norm_mv: tuple[float, float] | None = None           # NormMV
    cascade_to: int | None = None                        # index podřazené smyčky, jejíž SP řídí tato (hlavní) smyčka

    def to_dict(self):
        return dict(tag=self.tag, description=self.description, roles=self.roles.to_dict(),
                    norm_pv=list(self.norm_pv) if self.norm_pv else None,
                    norm_mv=list(self.norm_mv) if self.norm_mv else None, cascade_to=self.cascade_to)

    @classmethod
    def from_dict(cls, d):
        d = d or {}

        def rng(k):
            v = d.get(k)
            if v is None:
                return None
            if not isinstance(v, (list, tuple)) or len(v) != 2:
                raise _bad(k)
            return (_num(v[0], k, none=False), _num(v[1], k, none=False))
        c = d.get("cascade_to")
        return cls(tag=str(d.get("tag") or ""), description=str(d.get("description") or ""),
                   roles=Roles.from_dict(d.get("roles")), norm_pv=rng("norm_pv"), norm_mv=rng("norm_mv"),
                   cascade_to=None if c is None else int(c))


@dataclass
class TimeGrid:
    """
    Společná časová mřížka více zdrojů: `overlap` = jen společný úsek (výchozí), `union` = od nejdřívějšího po
    nejpozdější vzorek (mimo úsek zdroje NaN). Perioda: ruční `period` [s], jinak nejjemnější perioda zdrojů.
    Mezera ve zdroji delší než `max_gap` [s] (výchozí `gap_factor` × perioda zdroje) se do mřížky nepřenáší (NaN).
    """
    mode: str = "overlap"
    period: float | None = None
    max_gap: float | None = None
    gap_factor: float = 5.0

    def to_dict(self):
        return dict(mode=self.mode, period=self.period, max_gap=self.max_gap, gap_factor=self.gap_factor)

    @classmethod
    def from_dict(cls, d):
        d = d or {}
        g = cls(mode=str(d.get("mode") or "overlap"), period=_num(d.get("period"), "time_grid.period"),
                max_gap=_num(d.get("max_gap"), "time_grid.max_gap"),
                gap_factor=_num(d.get("gap_factor", 5.0), "time_grid.gap_factor", none=False))
        g.check()
        return g

    def check(self):
        if self.mode not in GRID_MODES:
            raise _bad("time_grid.mode")
        for k in ("period", "max_gap"):
            v = getattr(self, k)
            if v is not None and not v > 0:
                raise _bad(f"time_grid.{k}")
        if not self.gap_factor > 0:
            raise _bad("time_grid.gap_factor")


@dataclass
class Project:
    sources: list[Source] = field(default_factory=list)
    loops: list[LoopSpec] = field(default_factory=list)
    active: int = 0
    time_grid: TimeGrid = field(default_factory=TimeGrid)

    def source(self, sid):
        for s in self.sources:
            if s.id == sid:
                return s
        raise KeyError(sid)

    def next_source_id(self):
        n = 1
        ids = {s.id for s in self.sources}
        while f"s{n}" in ids:
            n += 1
        return f"s{n}"

    def to_dict(self):
        """Popis projektu bez dat a bez výpočetního stavu smyček; `active` se počítá od 1 jako v souboru projektu."""
        return dict(format=FORMAT, version=VERSION, sources=[s.to_dict() for s in self.sources],
                    loops=[dict(spec=lp.to_dict()) for lp in self.loops], active=self.active + 1,
                    time_grid=self.time_grid.to_dict())

    @classmethod
    def from_dict(cls, d):
        """
        Z JSON slovníku verze 3 (starší soubory nejdřív přes `domain.migrate.migrate_project`). Smyčky: seznam
        `loops` se záznamy, které nesou `spec`; jednosmyčkový soubor má `spec` přímo nahoře.
        """
        if not isinstance(d, dict) or d.get("format") != FORMAT:
            raise _bad("format")
        if int(d.get("version", 0)) > VERSION:
            raise ValueError(T("err_project_newer", v=d.get("version")))
        recs = d.get("loops") or [d]
        p = cls(sources=[Source.from_dict(s) for s in d.get("sources") or []],
                loops=[LoopSpec.from_dict(r.get("spec")) for r in recs],
                active=min(max(int(d.get("active") or 1), 1), len(recs)) - 1,
                time_grid=TimeGrid.from_dict(d.get("time_grid")))
        ids = [s.id for s in p.sources]
        if len(set(ids)) != len(ids):
            raise _bad("sources")
        return p
