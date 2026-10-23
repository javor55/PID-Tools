"""
API – data smyčky (M7): načtení souboru / ukázky, rozložení tabulky, sloupce, úsek, nastavení, signály binárně,
kvalita dat a režim smyčky (MAN / AUTO).
"""
from typing import Annotated, Literal

import numpy as np
from fastapi import APIRouter, Body, HTTPException, Query, Request, Response
from pydantic import BaseModel

from ..app import project as prj
from ..app import signalpack
from ..app.dataio import read_table

MAX_UPLOAD = 200 * 2 ** 20          # největší nahraný soubor [B]


class WorkspaceInfo(BaseModel):
    id: str
    has_data: bool
    fname: str
    columns: list[str]
    pv: str | None = None
    mv: str | None = None
    sp: str | None = None
    dists: list[str] = []
    pos: str | None = None
    n: int = 0
    Ts: float | None = None
    duration: float | None = None
    rng: list[float] | None = None
    layout: str = "wide"
    time_note: str = ""
    origin: str | None = None


class Layout(BaseModel):
    layout: Literal["wide", "long", "pairs"] = "wide"
    time_fmt: str | None = None
    unit: str | None = None
    c_time: str | None = None
    c_tag: str | None = None
    c_val: str | None = None
    row_dt: float | None = None


class Columns(BaseModel):
    pv: str
    mv: str
    sp: str | None = None
    dists: list[str] = []
    pos: str | None = None


class Range(BaseModel):
    a: float
    b: float


class Check(BaseModel):
    key: str
    level: int
    args: dict = {}


class Quality(BaseModel):
    level: int
    checks: list[Check]
    snr: float | None = None
    sigma: float | None = None
    n_steps: int | None = None


class Run(BaseModel):
    a: float
    b: float
    kind: Literal["man", "auto"]


class LoopMode(BaseModel):
    frac: float
    runs: list[Run]
    auto_frac: float
    effective: Literal["open", "cl"]
    mv_modes: list[Literal["man", "auto"]]
    set1_ok: bool


def _none(c):
    return None if c in (None, "", "—") else str(c)


def info(wid, ws):
    has = bool(ws.has_data)
    sig = ws.sig
    return WorkspaceInfo(
        id=wid, has_data=has, fname=ws.fname or "", columns=[str(c) for c in (sig.sigs if sig is not None else [])],
        pv=_none(ws.c_pv), mv=_none(ws.c_mv), sp=_none(ws.c_sp), dists=[str(d) for d in ws.c_d], pos=_none(ws.c_pos),
        n=len(ws.t) if has else 0, Ts=float(ws.grid.Ts) if has else None,
        duration=float(ws.t[-1]) if has else None, rng=[float(x) for x in ws.rng] if has else None,
        layout=ws.layout, time_note=getattr(sig, "time_note", "") if sig is not None else "",
        origin=str(sig.origin) if sig is not None and sig.origin is not None else None)


def _plain(x):
    """Výsledek výpočtu → JSON (numpy → Python, NaN / ∞ → None)."""
    if isinstance(x, dict):
        return {str(k): _plain(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_plain(v) for v in x]
    if isinstance(x, np.ndarray):
        return _plain(x.tolist())
    if isinstance(x, np.generic):
        x = x.item()
    if isinstance(x, float) and not np.isfinite(x):
        return None
    return x


def _err(ex):
    """Chyba načtení / výpočtu → 400 s klíčem textu (frontend ho přeloží), nebo textem chyby."""
    raise HTTPException(400, str(ex.args[0]) if ex.args else type(ex).__name__) from ex


def router(get_proj):
    r = APIRouter(prefix="/workspaces/{wid}", tags=["data"])

    def get_ws(wid):
        return get_proj(wid).state

    def need_data(wid):
        ws = get_ws(wid)
        if not ws.has_data:
            raise HTTPException(409, "no data")
        return ws

    @r.post("/data/demo", response_model=WorkspaceInfo)
    def load_demo(wid: str):
        p = get_proj(wid)
        p.load_demo()
        return info(wid, p.state)

    @r.post("/data/file", response_model=WorkspaceInfo,
            openapi_extra={"requestBody": {"required": True, "content": {"application/octet-stream": {
                "schema": {"type": "string", "format": "binary"}}}}})
    async def load_file(wid: str, request: Request,
                        name: Annotated[str, Query(description="file name (extension)")]):
        """Soubor (CSV / Excel / text) jako tělo požadavku; formát podle přípony v `name`."""
        p = get_proj(wid)
        raw = await request.body()
        if len(raw) > MAX_UPLOAD:
            raise HTTPException(413, "file too large")
        try:
            p.load_frame(read_table(name, raw), name)
        except (ValueError, KeyError, IndexError) as ex:
            _err(ex)
        return info(wid, p.state)

    @r.put("/layout", response_model=WorkspaceInfo)
    def set_layout(wid: str, body: Layout):
        ws = need_data(wid)
        try:
            ws.set_layout(**body.model_dump())
        except (ValueError, KeyError, IndexError) as ex:
            _err(ex)
        return info(wid, ws)

    @r.put("/columns", response_model=WorkspaceInfo)
    def set_columns(wid: str, body: Columns):
        ws = need_data(wid)
        names = set(map(str, ws.sig.sigs))
        bad = [c for c in [body.pv, body.mv, body.sp, body.pos, *body.dists] if c and c not in names]
        if bad:
            raise HTTPException(422, f"unknown signal: {', '.join(bad)}")
        try:
            ws.set_columns(body.pv, body.mv, body.sp or "—", body.dists, body.pos or "—")
        except (ValueError, KeyError, IndexError) as ex:
            _err(ex)
        return info(wid, ws)

    @r.put("/range", response_model=WorkspaceInfo)
    def set_range(wid: str, body: Range):
        ws = need_data(wid)
        a, b = sorted((float(body.a), float(body.b)))
        if not (0 <= a < b <= float(ws.t[-1]) + 1e-9):
            raise HTTPException(422, "range outside the record")
        ws.rng = (a, b)
        return info(wid, ws)

    @r.get("/settings", response_model=dict)
    def get_settings(wid: str):
        """Nastavení smyčky (klíče jako v projektu)."""
        ws = get_ws(wid)
        return {k: prj.jsonable(v) for k, v in ws.settings.items() if prj.is_state_key(k)}

    @r.patch("/settings", response_model=dict)
    def patch_settings(wid: str, body: Annotated[dict, Body()]):
        """Změna nastavení – jen klíče, které patří do projektu (app.project.is_state_key)."""
        ws = get_ws(wid)
        bad = [k for k in body if not prj.is_state_key(k)]
        if bad:
            raise HTTPException(422, f"unknown setting: {', '.join(map(str, bad))}")
        ws.set(**body)
        return get_settings(wid)

    @r.get("/signals", response_class=Response,
           responses={200: {"content": {"application/octet-stream": {}},
                            "description": "app.signalpack.frame: [uint32 LE length][JSON description][Float64 times, "
                                           "Float32 values]"}})
    def signals(wid: str, names: Annotated[list[str] | None, Query()] = None, source: Literal["raw", "grid"] = "raw",
                cap: Annotated[int, Query(ge=1000)] = signalpack.CAP):
        """
        Signály binárně. raw = ze souboru bez převzorkování (všechny, nebo `names`); grid = převzorkované na periodu
        smyčky (pv, mv, sp, d0, d1 …, valid) – na nich běží identifikace.
        """
        ws = need_data(wid)
        if source == "raw":
            sel = [str(n) for n in (names or ws.sig.sigs)]
            p = signalpack.pack(sel, ws.sig.t_all, ws.sig.get, cap)
        else:
            g = ws.grid
            cols = {"pv": g.pv_e, "mv": g.mv_e}
            if g.has_sp:
                cols["sp"] = g.sp_e
            cols.update({f"d{j}": d for j, d in enumerate(g.dists)})
            if ws.valid is not None:
                cols["valid"] = ws.valid.astype(float)
            sel = [n for n in (names or cols) if n in cols]
            p = signalpack.pack(sel, g.t, cols.__getitem__, cap)
        return Response(signalpack.frame(p), media_type="application/octet-stream")

    @r.get("/quality", response_model=Quality)
    def quality(wid: str, a: float | None = None, b: float | None = None):
        """Kvalita dat úseku (výchozí: úsek identifikace)."""
        ws = need_data(wid)
        q = ws.quality(a, b) if a is not None and b is not None else ws.quality()
        if q is None:
            raise HTTPException(400, "quality failed")
        return Quality(level=int(q["level"]), checks=[Check(key=k, level=int(lv), args=_plain(ar))
                                                       for k, lv, ar in q["checks"]],
                       snr=q.get("snr"), sigma=q.get("sigma"), n_steps=q.get("n_steps"))

    @r.get("/loopmode", response_model=LoopMode)
    def loopmode(wid: str):
        """Úseky MAN / AUTO záznamu, podíl AUTO v úseku identifikace a použitý režim identifikace."""
        ws = need_data(wid)
        det = ws.loop_det()
        return LoopMode(frac=det["frac"], runs=[Run(a=a, b=b, kind=k) for a, b, k in det["runs"]],
                        auto_frac=ws.auto_frac(), effective=ws.id_mode_eff, mv_modes=ws.mv_modes(),
                        set1_ok=ws.set1_ok)

    @r.get("/compression", response_model=list[str])
    def compression(wid: str):
        """Upozornění na kompresi historianu (nepravidelné vzorky, opakované hodnoty)."""
        return [str(x) for x in (need_data(wid).compression() or [])]

    return r

