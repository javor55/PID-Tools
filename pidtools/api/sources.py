"""
API – zdroje dat, společná časová mřížka a signály pro Trendy (plán v2, E3).

Zdroj = soubor (CSV / XLSX / TXT) nebo záznam z OPC UA s rozvržením, časovým pásmem, posunem a vlastním vzorkováním.
Smyčky projektu skládají svá data ze zdrojů (mapování rolí: api/mapping.py); `/time-grid` určuje, jak se zdroje
skládají na společnou mřížku. `/signals/trend` vrací zředěná data všech signálů zdrojů (min / max po skupinách),
statistiku a hodnoty v čase kurzorů; binární `/signals` (api/data.py) zůstává pro prohlížeč jednoho záznamu smyčky.
"""
from typing import Annotated

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from ..app.domain import registry as sreg
from ..app.domain import trend
from ..app.domain.model import SourceRef, TimeGrid
from .data import _err


class SourceKind(BaseModel):
    """Druh zdroje z registru: id, popis v jazyce odpovědi a schéma voleb čtení."""
    id: str
    description: str
    params: dict


class TimeGridBody(BaseModel):
    """Společná časová mřížka: `overlap` (společný úsek) / `union`, ruční perioda [s], práh mezery [s]."""
    mode: str = "overlap"
    period: float | None = None
    max_gap: float | None = None
    gap_factor: float = 5.0


class SourceOptions(BaseModel):
    """Čtení tabulky zdroje (stejné volby jako rozložení dat smyčky)."""
    layout: str | None = None
    time_fmt: str | None = None
    unit: str | None = None
    c_time: str | None = None
    c_tag: str | None = None
    c_val: str | None = None
    row_dt: float | None = None


class SourceInfo(SourceOptions):
    id: str
    name: str
    kind: str
    timezone: str | None = None
    offset_s: float = 0.0
    sampling_s: float | None = None
    rows: int = 0
    columns: list[str] = []
    period: float | None = None             # perioda vzorkování [s] (vlastní, jinak z dat)
    start: float | None = None              # začátek a konec na společné ose zdrojů [s od nejdřívějšího zdroje]
    end: float | None = None
    has_clock: bool = False                 # soubor má hodiny (datum a čas), ne jen číselný čas
    used_by: list[int] = []                 # smyčky (od 0), jejichž role používají sloupce zdroje
    loaded: bool = True                     # tabulka je načtená (projekt bez dat ji nemá)


class Common(BaseModel):
    start: float
    end: float
    duration: float


class Sources(BaseModel):
    sources: list[SourceInfo]
    kinds: list[SourceKind]
    time_grid: TimeGridBody
    common: Common | None = None            # společný úsek všech zdrojů (None = nepřekrývají se nebo žádná data)
    origin: str | None = None               # čas 0 společné osy jako ISO text, když zdroje mají hodiny


class SourcePatch(BaseModel):
    """Změna zdroje; zadané pole (i `null`) se změní, nezadané zůstane."""
    name: str | None = None
    layout: str | None = None
    time_fmt: str | None = None
    unit: str | None = None
    c_time: str | None = None
    c_tag: str | None = None
    c_val: str | None = None
    row_dt: float | None = None
    timezone: str | None = None
    offset_s: float | None = None
    sampling_s: float | None = None


class SignalStats(BaseModel):
    min: float | None = None
    max: float | None = None
    mean: float | None = None
    std: float | None = None
    count: int = 0
    missing: int = 0


class TrendSeries(BaseModel):
    ref: str                                # `zdroj:sloupec`
    source: str
    column: str
    t: list[float]                          # čas na společné ose zdrojů [s]
    v: list[float]
    n_raw: int                              # platných vzorků v úseku před zředěním
    decimated: bool
    stats: SignalStats
    at: list[float | None] = []             # hodnoty v časech kurzorů (None = mimo záznam nebo v mezeře)


class Trend(BaseModel):
    a: float
    b: float
    n: int
    cursors: list[float]
    origin: str | None = None
    series: list[TrendSeries]


class AxisRange(BaseModel):
    """Úsek na společné ose zdrojů [s] (kurzory A–B v Trendech)."""
    a: float
    b: float


class LoopRange(BaseModel):
    """Úsek přepočtený na čas aktivní smyčky; `offset` = čas 0 smyčky na společné ose [s]."""
    a: float
    b: float
    offset: float


def loop_offset(p, ws):
    """Čas 0 záznamu aktivní smyčky na společné ose zdrojů [s] (z hodin, jinak z posunu zdroje PV / MV + začátek mřížky)."""
    shifts, _spans, origin = p.axis()
    t0 = float(ws.grid.T0)
    org = getattr(ws.sig, "origin", None)
    if org is not None and origin is not None:
        return (pd.Timestamp(org) - pd.Timestamp(origin)).total_seconds() + t0
    roles = p.loop_spec(p.active).roles
    first = roles.pv or roles.mv
    return t0 + (shifts.get(first.source_id, 0.0) if first is not None else 0.0)


def _num(x):
    return None if x is None or not np.isfinite(x) else float(x)


def _grid(tg):
    return TimeGridBody(mode=tg.mode, period=tg.period, max_gap=tg.max_gap, gap_factor=tg.gap_factor)


def source_info(p, rt, axis):
    """Popis zdroje a údaje z dat (sloupce, perioda, rozsah na společné ose)."""
    src, loaded = rt.src, rt.df is not None
    opt = {k: src.options.get(k) for k in SourceOptions.model_fields}
    info = SourceInfo(id=src.id, name=src.name, kind=src.kind, timezone=src.timezone, offset_s=float(src.offset_s),
                      sampling_s=src.sampling_s, rows=int(len(rt.df)) if loaded else src.data.rows, loaded=loaded, **opt)
    info.used_by = [i for i in range(len(p.loops))
                    if any(r.source_id == src.id for r in p.loop_spec(i).roles.refs())]
    if loaded:
        sig = rt.signals()
        info.columns = [str(c) for c in sig.sigs]
        info.period = _num(rt.period())
        info.has_clock = sig.origin is not None
        if src.id in axis[1]:
            info.start, info.end = axis[1][src.id]
        info.layout = info.layout or rt.layout()
    return info


def overview(p):
    p.sync()
    axis = p.axis()
    spans = list(axis[1].values())
    common = None
    if spans and len(spans) == len([r for r in p.sources if r.df is not None]):
        a, b = max(s[0] for s in spans), min(s[1] for s in spans)
        if b > a:
            common = Common(start=a, end=b, duration=b - a)
    return Sources(sources=[source_info(p, rt, axis) for rt in p.sources], origin=axis[2], common=common,
                   kinds=[SourceKind(**d) for d in sreg.SOURCES.describe()], time_grid=_grid(p.time_grid))


def router(get_proj, max_upload):
    r = APIRouter(prefix="/workspaces/{wid}", tags=["sources"])

    def source_of(p, sid):
        try:
            return p.rt(sid)
        except KeyError:
            raise HTTPException(404, "source not found") from None

    @r.get("/sources", response_model=Sources)
    def list_sources(wid: str):
        """Zdroje dat projektu s časovými údaji, použitím ve smyčkách, společným úsekem a druhy zdrojů z registru."""
        return overview(get_proj(wid))

    @r.post("/sources", response_model=SourceInfo,
            openapi_extra={"requestBody": {"required": True, "content": {"application/octet-stream": {
                "schema": {"type": "string", "format": "binary"}}}}})
    async def add_source(wid: str, request: Request, name: Annotated[str, Query(description="file name (extension)")],
                         kind: str | None = None, layout: str | None = None, time_fmt: str | None = None,
                         unit: str | None = None, c_time: str | None = None, c_tag: str | None = None,
                         c_val: str | None = None, row_dt: float | None = None, timezone: str | None = None,
                         offset_s: float = 0.0, sampling_s: float | None = None):
        """Nový zdroj ze souboru (tělo požadavku; druh podle přípony, nebo `kind`) s volbami čtení a časovými údaji."""
        p = get_proj(wid)
        if kind is not None and kind not in sreg.SOURCES:
            raise HTTPException(422, f"unknown source kind: {kind}")
        if int(request.headers.get("content-length") or 0) > max_upload:
            raise HTTPException(413, "file too large")
        raw = await request.body()
        if len(raw) > max_upload:
            raise HTTPException(413, "file too large")
        opts = dict(layout=layout, time_fmt=time_fmt, unit=unit, c_time=c_time, c_tag=c_tag, c_val=c_val, row_dt=row_dt)
        try:
            rt = p.add_source(name, raw=raw, kind=kind, options=opts, timezone=timezone, offset_s=offset_s,
                              sampling_s=sampling_s)
        except (ValueError, KeyError, IndexError) as ex:
            _err(ex)
        return source_info(p, rt, p.axis())

    @r.get("/sources/{sid}", response_model=SourceInfo)
    def get_source(wid: str, sid: str):
        p = get_proj(wid)
        p.sync()
        return source_info(p, source_of(p, sid), p.axis())

    @r.patch("/sources/{sid}", response_model=SourceInfo)
    def patch_source(wid: str, sid: str, body: SourcePatch):
        """Časové pásmo (IANA), posun [s], vlastní vzorkování [s], název a čtení tabulky; smyčky ze zdroje se přeskládají."""
        p = get_proj(wid)
        p.sync()
        source_of(p, sid)
        patch = {k: getattr(body, k) for k in body.model_fields_set}
        try:
            rt = p.update_source(sid, **patch)
        except (ValueError, KeyError, IndexError) as ex:
            _err(ex)
        return source_info(p, rt, p.axis())

    @r.delete("/sources/{sid}", status_code=204)
    def delete_source(wid: str, sid: str):
        """Odebere zdroj, který nepoužívá žádná role smyčky (jinak 409)."""
        p = get_proj(wid)
        p.sync()
        source_of(p, sid)
        try:
            p.remove_source(sid)
        except ValueError as ex:
            raise HTTPException(409, str(ex.args[0])) from ex

    @r.get("/time-grid", response_model=TimeGridBody)
    def get_time_grid(wid: str):
        return _grid(get_proj(wid).time_grid)

    @r.put("/time-grid", response_model=TimeGridBody)
    def put_time_grid(wid: str, body: TimeGridBody):
        """Společná mřížka: překryv / sjednocení, ruční perioda vzorkování, práh mezery; smyčky se přeskládají."""
        p = get_proj(wid)
        try:
            tg = TimeGrid(**body.model_dump())
            tg.check()
            p.set_time_grid(tg)
        except (ValueError, KeyError, IndexError) as ex:
            _err(ex)
        return _grid(p.time_grid)

    @r.get("/signals/trend", response_model=Trend)
    def signals_trend(wid: str, names: Annotated[list[str] | None, Query(description="`zdroj:sloupec`; bez zadání všechny")] = None,
                      a: float | None = None, b: float | None = None,
                      n: Annotated[int, Query(ge=10, le=20000, description="skupin pro zředění")] = 1000,
                      at: Annotated[list[float] | None, Query(description="časy kurzorů [s]")] = None):
        """
        Signály všech zdrojů na společné ose [s od nejdřívějšího zdroje]: zředěné na min / max po skupinách (špičky
        zůstanou), statistika v úseku `a`–`b` a hodnoty v časech kurzorů `at` (interpolace, v mezeře `null`).
        """
        p = get_proj(wid)
        p.sync()
        shifts, spans, origin = p.axis()
        try:
            refs = [SourceRef.parse(x) for x in names] if names else p.column_refs()
        except ValueError:
            raise HTTPException(422, "names must be `source:column`") from None
        if not spans:
            raise HTTPException(409, "no data")
        lo, hi = min(s[0] for s in spans.values()), max(s[1] for s in spans.values())
        a_, b_ = (lo if a is None else a), (hi if b is None else b)
        if not b_ > a_:
            raise HTTPException(422, "range")
        out = []
        for ref in refs:
            rt = source_of(p, ref.source_id)
            if rt.df is None or ref.source_id not in shifts:
                raise HTTPException(409, "no data")
            sig = rt.signals()
            if ref.column not in sig.sigs:
                raise HTTPException(404, f"unknown signal: {ref}")
            t, v = sig.t_all + shifts[ref.source_id], sig.get(ref.column)
            tt, vv = trend.decimate(t, v, a_, b_, n)
            raw = len(trend.window(t, v, a_, b_)[0])
            out.append(TrendSeries(ref=str(ref), source=ref.source_id, column=ref.column, t=tt.tolist(),
                                   v=vv.tolist(), n_raw=raw, decimated=len(tt) < raw,
                                   stats=SignalStats(**trend.stats(t, v, a_, b_)),
                                   at=[_num(trend.value_at(t, v, x)) for x in at or []]))
        return Trend(a=a_, b=b_, n=n, cursors=list(at or []), origin=origin, series=out)

    @r.put("/range/common", response_model=LoopRange)
    def set_range_common(wid: str, body: AxisRange):
        """
        Úsek z Trendů (společná osa zdrojů) jako identifikační úsek aktivní smyčky: přepočte se na čas záznamu smyčky
        a ořízne na něj (úsek mimo záznam = 422).
        """
        p = get_proj(wid)
        p.sync()
        ws = p.state
        if not ws.has_data:
            raise HTTPException(409, "no data")
        off = loop_offset(p, ws)
        a, b = sorted((body.a - off, body.b - off))
        a, b = max(a, 0.0), min(b, float(ws.t[-1]))
        if not b > a:
            raise HTTPException(422, "range outside the record")
        ws.rng = (a, b)
        return LoopRange(a=a, b=b, offset=off)

    return r
