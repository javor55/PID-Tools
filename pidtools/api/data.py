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
from ..app.dataio import ROWS, TIME_FORMATS, read_table
from ..app.dataset import UNITS, guess_col

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


class LayoutInfo(Layout):
    """Aktuální čtení tabulky: rozložení a sloupce (odhad, pokud nejsou zadané), sloupce tabulky a možnosti výběru."""
    default_layout: Literal["wide", "long", "pairs"] = "wide"
    table_columns: list[str] = []
    time_columns: list[str] = []
    time_note: str = ""
    row_dt: float = 1.0
    rows_mark: str = ROWS
    time_formats: list[str] = list(TIME_FORMATS)
    units: list[str] = list(UNITS)


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


class DqCheck(BaseModel):
    """Jedna kontrola kvality dat (záložka Data): stav, klíče textů dq_<id>_name / _why, výsledek `res` s argumenty."""
    id: str
    status: Literal["ok", "warn", "info"]
    res: str
    args: dict = {}


class DataQuality(BaseModel):
    usable: bool
    counts: dict[str, int]
    checks: list[DqCheck]


class StatRow(BaseModel):
    name: str
    role: Literal["PV", "MV", "SP", "DV"]
    min: float | None = None
    max: float | None = None
    mean: float | None = None
    std: float | None = None


class PreviewCol(BaseModel):
    label: str
    role: Literal["PV", "MV", "SP", "DV", "POS"]


class PreviewRow(BaseModel):
    i: int                                   # pořadí vzorku (od 1)
    t: float                                 # čas od začátku [s]
    dt: str | None = None                    # datum a čas, když má záznam hodiny
    v: list[float | None]                    # hodnoty ve sloupcích `columns`
    notes: list[str] = []                    # id kontrol Kvality dat s upozorněním ve vzorku


class Preview(BaseModel):
    """Část tabulky po převzorkování (jako Celý náhled): řádky `offset` … `offset + len(rows)` z `total` po filtru."""
    columns: list[PreviewCol]
    total: int
    n_all: int
    offset: int
    Ts: float
    n_warn: int
    n_mv: int
    rows: list[PreviewRow]


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


def layout_info(ws):
    """Rozložení tabulky jako ho ukazuje desktop: sloupce času / tagu / hodnoty doplněné odhadem."""
    from ..app.dataio import time_columns
    from ..app.dataset import default_layout
    cols = [str(c) for c in ws.df.columns]
    src = [str(c) for c in ws.sig.time_src]
    c_tag, c_val = ws.c_tag, ws.c_val
    if ws.layout == "long":
        c_tag = c_tag or cols[guess_col(cols, ["tag", "name", "název", "variable"])]
        c_val = c_val or cols[guess_col(cols, ["value", "hodnota", "val"], 2)]
    return LayoutInfo(
        layout=ws.layout, time_fmt=ws.time_fmt, unit=ws.unit, c_time=src[0] if ws.layout in ("wide", "long") and src else None,
        c_tag=c_tag, c_val=c_val, row_dt=float(ws.row_dt), default_layout=default_layout(ws.df), table_columns=cols,
        time_columns=[str(c) for c in time_columns(ws.df)], time_note=ws.sig.time_note)


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


def _checks(ws):
    """Kontroly kvality dat podle záznamu a rozsahů (stejné volání jako Streamlit)."""
    from ..app import quality as dq
    g = ws.grid
    pv_rng, mv_rng = (ws.pv_lo, ws.pv_hi), (ws.mv_lo, ws.mv_hi)
    if not (pv_rng[1] > pv_rng[0] and mv_rng[1] > mv_rng[0]):
        pv_rng, mv_rng = (0.0, 100.0), (0.0, 100.0)
    return dq.check_all(ws.sig.t_all, ws.sig.get(ws.c_pv), ws.sig.get(ws.c_mv), g.Ts, g.pv_e, g.mv_e, g.dists,
                        [str(c) for c in ws.c_d], pv_rng, mv_rng,
                        (float(ws.get("mvl_lo", ws.mv_lo)), float(ws.get("mvl_hi", ws.mv_hi))))


def _preview_frame(ws):
    """(sloupce, matice hodnot [n × k], datum a čas nebo None)."""
    import pandas as pd
    from ..app.dataset import on_grid
    g = ws.grid
    cols, vals = [PreviewCol(label=f"PV · {ws.c_pv}", role="PV"), PreviewCol(label=f"MV · {ws.c_mv}", role="MV")], \
        [g.pv_e, g.mv_e]
    if g.has_sp:
        cols.append(PreviewCol(label=f"SP · {ws.c_sp}", role="SP"))
        vals.append(g.sp_e)
    for nm, d in zip(ws.c_d, g.dists):
        cols.append(PreviewCol(label=str(nm), role="DV"))
        vals.append(d)
    if ws.c_pos not in (None, "", "—"):
        cols.append(PreviewCol(label=str(ws.c_pos), role="POS"))
        vals.append(on_grid(ws.sig, g, ws.c_pos))
    dt = None
    if ws.sig.origin is not None:
        dt = (ws.sig.origin + pd.to_timedelta(g.t + g.T0, unit="s")).strftime("%Y-%m-%d %H:%M:%S.%f").str[:-3].to_numpy()
    return cols, np.column_stack([np.asarray(v, float) for v in vals]), dt


def _num(x):
    return float(x) if np.isfinite(x) else None


def router(get_proj, max_upload=MAX_UPLOAD):
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
        if int(request.headers.get("content-length") or 0) > max_upload:      # velké tělo se ani nečte
            raise HTTPException(413, "file too large")
        raw = await request.body()
        if len(raw) > max_upload:
            raise HTTPException(413, "file too large")
        try:
            p.load_frame(read_table(name, raw), name)
        except (ValueError, KeyError, IndexError) as ex:
            _err(ex)
        return info(wid, p.state)

    @r.get("/layout", response_model=LayoutInfo)
    def get_layout(wid: str):
        """Jak je tabulka přečtená (rozložení, formát a jednotka času, sloupce) a z čeho jde vybírat."""
        return layout_info(need_data(wid))

    @r.put("/layout", response_model=WorkspaceInfo)
    def set_layout(wid: str, body: Layout):
        ws = need_data(wid)
        keep, settings = dict(ws.__dict__), dict(ws.settings)
        try:
            ws.set_layout(**body.model_dump())
        except (ValueError, KeyError, IndexError) as ex:
            ws.__dict__.update(keep)               # nečitelné rozložení nechá předchozí čtení beze změny
            ws.settings = settings
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

    @r.get("/dataquality", response_model=DataQuality)
    def dataquality(wid: str):
        """Kontroly kvality dat záznamu před identifikací (vzorkování, mezery, komprese, rozlišení, šum, meze, buzení)."""
        from ..app import quality as dq
        ws = need_data(wid)
        try:
            checks = _checks(ws)
        except Exception as ex:
            raise _err(ex)
        cnt, usable = dq.summary(checks)
        return DataQuality(usable=usable, counts=cnt, checks=[
            DqCheck(id=c.id, status=c.status, res=c.res, args=_plain(c.args)) for c in checks])

    @r.get("/datastats", response_model=list[StatRow])
    def datastats(wid: str):
        """Min / max / průměr / σ veličin smyčky na mřížce po převzorkování (inženýrské jednotky)."""
        from ..app.dataset import stats
        ws = need_data(wid)
        roles = {"PV": "PV", "MV": "MV", "SP": "SP"}
        return [StatRow(name=n, role=roles.get(n, "DV"), min=_num(a), max=_num(b), mean=_num(m), std=_num(sd))
                for n, a, b, m, sd in stats(ws.grid, ws.c_d)]

    def _preview_rows(ws, flt):
        from ..app import quality as dq
        checks = _checks(ws)
        cols, vals, dt = _preview_frame(ws)
        n = len(ws.t)
        warn = dq.warn_mask(checks, n)
        mvch = np.r_[False, np.abs(np.diff(ws.grid.mv_e)) > 1e-9]
        idx = np.arange(n)
        sel = idx[warn] if flt == "warn" else idx[mvch] if flt == "mv" else idx
        return checks, cols, vals, dt, sel, int(warn.sum()), int(mvch.sum())

    @r.get("/preview", response_model=Preview)
    def preview(wid: str, offset: int = 0, limit: Annotated[int, Query(ge=1, le=2000)] = 200,
                filter: Literal["all", "warn", "mv"] = "all", t: float | None = None):
        """Tabulka po převzorkování po částech (Celý náhled): filtr řádků, od času `t` [s] (přepíše `offset`)."""
        ws = need_data(wid)
        try:
            checks, cols, vals, dt, sel, n_warn, n_mv = _preview_rows(ws, filter)
        except Exception as ex:
            raise _err(ex)
        if t is not None:
            offset = int(np.searchsorted(ws.t[sel], t))
        offset = max(0, min(offset, max(len(sel) - 1, 0)))
        part = sel[offset:offset + limit]
        notes = {i: [] for i in part.tolist()}
        for c in checks:
            if c.mask is not None and len(c.mask) == len(ws.t):
                for i in part[np.asarray(c.mask, bool)[part]].tolist():
                    notes[i].append(c.id)
        rows = [PreviewRow(i=int(i) + 1, t=float(ws.t[i]), dt=None if dt is None else str(dt[i]),
                           v=[_num(x) for x in vals[i]], notes=notes[int(i)]) for i in part]
        return Preview(columns=cols, total=len(sel), n_all=len(ws.t), offset=offset, Ts=float(ws.grid.Ts), n_warn=n_warn,
                       n_mv=n_mv, rows=rows)

    @r.get("/preview/csv")
    def preview_csv(wid: str):
        """Celá tabulka po převzorkování jako CSV (středník, desetinná čárka)."""
        import io
        import pandas as pd
        ws = need_data(wid)
        cols, vals, dt = _preview_frame(ws)
        out = {"t [s]": ws.t}
        if dt is not None:
            out["datetime"] = dt
        out.update({c.label: vals[:, j] for j, c in enumerate(cols)})
        buf = io.StringIO()
        pd.DataFrame(out).to_csv(buf, index=False, sep=";", decimal=",")
        return Response(buf.getvalue().encode("utf-8-sig"), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": 'attachment; filename="data_resampled.csv"'})

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

