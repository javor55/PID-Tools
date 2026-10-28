"""
API – projekt a smyčky (M8): uložení / načtení projektu (formát app.project, i starší verze s migrací),
smyčky projektu nad jedním souborem (seznam, přidání, odebrání, aktivní smyčka).
"""
import json

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from ..app import project as prj
from .data import WorkspaceInfo, info

MAX_PROJECT = 300 * 2 ** 20


class Loop(BaseModel):
    index: int
    name: str
    pv: str | None = None
    mv: str | None = None
    has_model: bool = False


class Loops(BaseModel):
    active: int
    loops: list[Loop]


class NewLoop(BaseModel):
    name: str | None = None
    pv: str | None = None
    mv: str | None = None
    sp: str | None = None
    pos: str | None = None


class Active(BaseModel):
    index: int


def _loops(p):
    names = p.names()
    return Loops(active=p.active, loops=[
        Loop(index=i, name=str(names[i]), pv=ls.c_pv, mv=ls.c_mv, has_model=ls.model is not None)
        for i, ls in enumerate(p.loops)])


def pending_router(enabled=True):
    """
    Projekt čekající na otevření (poklep na soubor `.pidproj` v okně desktopu): Rust ho vloží, rozhraní si ho vyzvedne
    a otevře do svého prostoru. Jedno místo, vyzvednutí ho vyprázdní. V týmovém režimu (enabled=False) se nedrží nic.
    """
    r = APIRouter(prefix="/pending-open", tags=["project"])
    box = {}

    @r.put("", status_code=204)
    async def put_pending(request: Request):
        """Uloží soubor projektu (obsah JSON) k otevření; kontroluje se až při otevření v prostoru."""
        if not enabled:
            raise HTTPException(403, "not available")
        raw = await request.body()
        if len(raw) > MAX_PROJECT:
            raise HTTPException(413, "project too large")
        box["raw"] = raw

    @r.get("", response_class=Response, responses={200: {"content": {"application/json": {}}}, 204: {}})
    def take_pending():
        """Vyzvedne čekající projekt (a vyprázdní místo); 204, když žádný není."""
        raw = box.pop("raw", None)
        if raw is None:
            return Response(status_code=204)
        return Response(raw, media_type="application/json")

    return r


def router(get_proj):
    r = APIRouter(prefix="/workspaces/{wid}", tags=["project"])

    @r.get("/project", response_class=Response,
           responses={200: {"content": {"application/json": {}}, "description": "project file (app.project)"}})
    def save(wid: str, data: bool = True):
        """Projekt jako soubor JSON (všechny smyčky; s daty, nebo bez nich)."""
        p = get_proj(wid)
        return Response(prj.serialize_project(p.to_project(include_data=data)), media_type="application/json",
                        headers={"Content-Disposition": f'attachment; filename="{prj.project_name("pidtools")}"'})

    @r.put("/project", response_model=WorkspaceInfo,
           openapi_extra={"requestBody": {"required": True, "content": {"application/json": {
               "schema": {"type": "object"}}}}})
    async def load(wid: str, request: Request):
        """Načtení projektu (i starší verze); projekt bez dat použije data, která jsou v prostoru načtená."""
        p = get_proj(wid)
        raw = await request.body()
        if len(raw) > MAX_PROJECT:
            raise HTTPException(413, "project too large")
        try:
            p.apply_project(prj.load_project(raw.decode("utf-8")))
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as ex:
            raise HTTPException(400, f"invalid project: {ex}") from ex
        return info(wid, p.state)

    @r.get("/loops", response_model=Loops)
    def loops(wid: str):
        return _loops(get_proj(wid))

    @r.post("/loops", response_model=Loops)
    def add_loop(wid: str, body: NewLoop):
        """Další smyčka ze stejných dat (sloupce zadané, nebo odhadnuté mimo PV ostatních smyček)."""
        p = get_proj(wid)
        if not p.state.has_data:
            raise HTTPException(409, "no data")
        if body.pv and body.mv:
            names = set(map(str, p.state.sig.sigs))
            bad = [c for c in (body.pv, body.mv, body.sp, body.pos) if c and c not in names]
            if bad:
                raise HTTPException(422, f"unknown signal: {', '.join(bad)}")
            p.add_loop_with(body.name or body.pv, body.pv, body.mv, body.sp, body.pos)
        else:
            ls = p.add_loop()
            if body.name:
                ls.set(loop_tag=body.name)
        return _loops(p)

    @r.put("/loops/active", response_model=Loops)
    def set_active(wid: str, body: Active):
        p = get_proj(wid)
        if not 0 <= body.index < len(p.loops):
            raise HTTPException(404, "loop not found")
        p.active = body.index
        return _loops(p)

    @r.delete("/loops/{index}", response_model=Loops)
    def remove_loop(wid: str, index: int):
        p = get_proj(wid)
        if not 0 <= index < len(p.loops):
            raise HTTPException(404, "loop not found")
        if len(p.loops) < 2:
            raise HTTPException(409, "last loop")
        p.remove_loop(index)
        return _loops(p)

    return r
