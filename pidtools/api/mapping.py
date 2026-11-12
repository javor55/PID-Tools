"""
API – mapování smyček na zdroje (plán v2, E3): role PV / SP / MV / poloha / DV / režim → `zdroj › sloupec`, rozsahy
NormPV / NormMV, tag, popis a vazba kaskády; návrh smyček podle názvů tagů a import mapování z CSV.
Smyčky se číslují od 0 jako u `/loops`.
"""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..app.domain import suggest as sg
from ..app.domain.model import LoopSpec, Roles, SourceRef
from .data import _err

MAX_CSV = 5 * 2 ** 20


class Ref(BaseModel):
    """Sloupec zdroje: `zdroj › sloupec`."""
    source: str
    column: str


class RolesBody(BaseModel):
    pv: Ref | None = None
    sp: Ref | None = None
    mv: Ref | None = None
    pos: Ref | None = None
    mode: Ref | None = None
    dv: list[Ref] = []


class LoopMapping(BaseModel):
    """Mapování smyčky. `norm_pv` / `norm_mv` = [dolní, horní] mez v jednotkách signálu; `cascade_to` = index podřazené smyčky."""
    tag: str = ""
    description: str = ""
    roles: RolesBody = RolesBody()
    norm_pv: list[float] | None = Field(None, min_length=2, max_length=2)
    norm_mv: list[float] | None = Field(None, min_length=2, max_length=2)
    cascade_to: int | None = None
    index: int | None = None                  # jen v odpovědi: pořadí smyčky
    sources: list[str] = []                   # jen v odpovědi: zdroje, ze kterých jsou data smyčky
    has_data: bool = True                     # jen v odpovědi


class SuggestBody(BaseModel):
    source_ids: list[str] | None = None       # jen sloupce těchto zdrojů (výchozí všechny)
    apply: bool = False                       # navržené úplné smyčky rovnou přidat do projektu


class Suggested(BaseModel):
    tag: str
    roles: RolesBody
    via: str                                  # pcs7 / deltav / dot / guess / csv
    complete: bool                            # má PV a MV
    description: str = ""


class Suggestions(BaseModel):
    loops: list[Suggested]
    unused: list[Ref]                         # sloupce, které se k žádné smyčce nepodařilo přiřadit
    warnings: list[str] = []
    applied: list[int] = []                   # indexy přidaných smyček (jen s `apply`)


def _ref(r):
    return None if r is None else Ref(source=r.source_id, column=r.column)


def _unref(r):
    return None if r is None else SourceRef(r.source, r.column)


def roles_body(roles: Roles):
    return RolesBody(pv=_ref(roles.pv), sp=_ref(roles.sp), mv=_ref(roles.mv), pos=_ref(roles.pos), mode=_ref(roles.mode),
                     dv=[_ref(x) for x in roles.dv])


def to_spec(m: LoopMapping):
    r = m.roles
    return LoopSpec(tag=m.tag, description=m.description,
                    roles=Roles(pv=_unref(r.pv), sp=_unref(r.sp), mv=_unref(r.mv), pos=_unref(r.pos),
                                mode=_unref(r.mode), dv=[_unref(x) for x in r.dv]),
                    norm_pv=tuple(m.norm_pv) if m.norm_pv else None, norm_mv=tuple(m.norm_mv) if m.norm_mv else None,
                    cascade_to=m.cascade_to)


def mapping_of(p, i):
    s = p.loop_spec(i)
    return LoopMapping(tag=s.tag, description=s.description, roles=roles_body(s.roles),
                       norm_pv=list(s.norm_pv) if s.norm_pv else None, norm_mv=list(s.norm_mv) if s.norm_mv else None,
                       cascade_to=s.cascade_to, index=i, sources=list(p.loops[i].src_ids), has_data=p.loops[i].has_data)


def _suggested(s):
    return Suggested(tag=s.tag, roles=roles_body(s.roles), via=s.via, complete=s.complete, description=s.description)


def router(get_proj):
    r = APIRouter(prefix="/workspaces/{wid}", tags=["loops"])

    def loop_of(p, index):
        if not 0 <= index < len(p.loops):
            raise HTTPException(404, "loop not found")
        return p.loops[index]

    def add_found(p, found):
        """Úplné návrhy, jejichž PV ještě nepoužívá žádná smyčka, přidá jako nové smyčky (první bezejmennou smyčku jen pojmenuje)."""
        applied = []
        for s in found:
            if not s.complete:
                continue
            used = [lp.roles.pv for lp in (p.loop_spec(i) for i in range(len(p.loops)))]
            if s.roles.pv in used:
                i = used.index(s.roles.pv)
                if not p.loops[i].get("loop_tag"):
                    spec = p.loop_spec(i)
                    spec.tag = s.tag
                    spec.description = spec.description or s.description
                    p.set_loop_spec(i, spec)
                continue
            p.add_loop_from_spec(s.to_spec())
            applied.append(len(p.loops) - 1)
        return applied

    @r.get("/loops/mappings", response_model=list[LoopMapping])
    def mappings(wid: str):
        """Mapování všech smyček (tabulka smyček záložky Zdroje a smyčky)."""
        p = get_proj(wid)
        p.sync()
        return [mapping_of(p, i) for i in range(len(p.loops))]

    @r.get("/loops/{index}/mapping", response_model=LoopMapping)
    def get_mapping(wid: str, index: int):
        p = get_proj(wid)
        loop_of(p, index)
        p.sync()
        return mapping_of(p, index)

    @r.put("/loops/{index}/mapping", response_model=LoopMapping)
    def put_mapping(wid: str, index: int, body: LoopMapping):
        """
        Nastaví role smyčky na sloupce zdrojů. Zdroje rolí určí data smyčky (jeden zdroj přímo, víc zdrojů složených
        na společnou mřížku); PV a MV jsou povinné. Při chybě (neznámý zdroj / sloupec, žádný překryv) zůstane
        smyčka beze změny.
        """
        p = get_proj(wid)
        loop_of(p, index)
        try:
            p.set_loop_spec(index, to_spec(body))
        except (ValueError, KeyError, IndexError) as ex:
            _err(ex)
        return mapping_of(p, index)

    @r.post("/loops/suggest", response_model=Suggestions)
    def suggest(wid: str, body: SuggestBody):
        """
        Návrh smyček podle názvů tagů ve zdrojích (`TIC101.PV / .SP / .OUT`, PCS 7 `…/PV_Out`, DeltaV `…/PV.CV`,
        jinak odhad podle slov v názvu). S `apply` se úplné smyčky přidají do projektu.
        """
        p = get_proj(wid)
        p.sync()
        found, unused = sg.suggest(p.column_refs(set(body.source_ids) if body.source_ids is not None else None))
        applied = []
        try:
            applied = add_found(p, found) if body.apply else []
        except (ValueError, KeyError, IndexError) as ex:
            _err(ex)
        return Suggestions(loops=[_suggested(s) for s in found], unused=[_ref(x) for x in unused], applied=applied)

    @r.post("/loops/import", response_model=Suggestions,
            openapi_extra={"requestBody": {"required": True, "content": {"text/csv": {
                "schema": {"type": "string"}}}}})
    async def import_mapping(wid: str, request: Request, apply: bool = False):
        """
        Mapování z CSV (tělo; hlavička `loop, role, source, column`, volitelně `description`): role PV, SP, MV, pos, mode,
        DV (opakovatelná), `source` = id nebo název zdroje. Nepoužitelné řádky se přeskočí s varováním.
        S `apply` se úplné smyčky přidají do projektu.
        """
        p = get_proj(wid)
        p.sync()
        raw = await request.body()
        if len(raw) > MAX_CSV:
            raise HTTPException(413, "file too large")
        try:
            found, warns = sg.parse_mapping_csv(raw, p.source_tuples())
            applied = add_found(p, found) if apply else []
        except (ValueError, KeyError, IndexError) as ex:
            _err(ex)
        return Suggestions(loops=[_suggested(s) for s in found], unused=[], warnings=warns, applied=applied)

    return r
