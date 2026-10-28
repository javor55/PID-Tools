"""
API – diagnostika, doporučení APC a protokol (M11): KPI a ventil úseku, hystereze, nelinearita, doporučené
struktury APC pro aktivní smyčku a protokol z ladění (HTML, jako v obou dnešních rozhraních).
"""
from typing import Literal

import numpy as np
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from ..app import report as rpt
from ..app.apc import recommend as reco
from ..core import MODELS
from .data import _plain

MAX_SCATTER = 3000          # bodů fázového grafu a grafu polohy (rovnoměrně zředěné)


class Scatter(BaseModel):
    x: list[float | None]
    y: list[float | None]


class Diagnostics(BaseModel):
    a: float
    b: float
    integ: bool
    kpis: dict
    valve: dict
    hysteresis: float | None = None
    nonlinearity: dict | None = None
    phase: Scatter
    position: Scatter | None = None


class Recommendation(BaseModel):
    kind: str
    text: str
    other: int | None = None


class ReportReq(BaseModel):
    meta: dict = {}
    sections: list[str] = list(rpt.SECTIONS)
    chart_mode: Literal["inline", "cdn"] = "inline"


def _scatter(xy):
    """Dvojice polí → zředěné body pro graf (None = bez dat)."""
    if xy is None:
        return None
    x, y = (np.asarray(v, float) for v in xy)
    if len(x) > MAX_SCATTER:
        i = np.linspace(0, len(x) - 1, MAX_SCATTER).astype(int)
        x, y = x[i], y[i]
    return Scatter(**_plain(dict(x=x, y=y)))


def _nonlinearity(ws):
    """Lokální zesílení (rozšířené o MV v jednotkách), rozptyl, zesílení modelu a název prvního parametru."""
    nl = ws.nonlinearity()
    if not nl:
        return None
    lg, spread = nl
    gains = [dict(q, from_e=float(ws.EM(q["mv_from"])), to_e=float(ws.EM(q["mv_to"]))) for q in lg]
    code, p, _ = ws.model
    return _plain(dict(gains=gains, spread=spread, ref=p[0], param=MODELS[code]["params"][0],
                       integ=bool(MODELS[code]["integ"])))


def router(get_proj):
    r = APIRouter(prefix="/workspaces/{wid}", tags=["diagnostics"])

    def need_data(wid):
        ws = get_proj(wid).state
        if not ws.has_data:
            raise HTTPException(409, "no data")
        return ws

    @r.get("/diagnostics", response_model=Diagnostics)
    def diagnostics(wid: str, a: float | None = None, b: float | None = None, integ: bool | None = None):
        """
        Diagnostika úseku (výchozí: úsek identifikace); integ = integrační proces (výchozí nastavení diag_integ, jinak podle modelu). Fázový graf
        MV–PV a MV–poloha jsou zředěné na MAX_SCATTER bodů; nelinearita se počítá z úseku identifikace.
        """
        ws = need_data(wid)
        a, b = (a, b) if a is not None and b is not None else ws.rng
        if (ws.range_mask(a, b)).sum() < 100:
            raise HTTPException(422, "segment too short")
        if integ is None:           # nastavení diag_integ (volba v rozhraní), jinak podle modelu
            integ = ws.get("diag_integ")
        integ = bool(integ) if integ is not None else bool(ws.model and ws.model[0].startswith("I"))
        h = ws.hysteresis(a, b)
        return Diagnostics(a=a, b=b, integ=integ, kpis=_plain(ws.diag_kpis(a, b)), valve=_plain(ws.valve(a, b, integ)),
                           hysteresis=_plain(h), nonlinearity=_nonlinearity(ws),
                           phase=_scatter(ws.phase(a, b, integ)), position=_scatter(ws.pos_scatter(a, b)))

    @r.get("/apc/recommend", response_model=list[Recommendation])
    def recommend(wid: str):
        """Doporučené struktury APC pro aktivní smyčku (s ohledem na ostatní smyčky projektu)."""
        p = get_proj(wid)
        ws = p.state
        if ws.model is None:
            raise HTTPException(409, "no model")
        items = reco.recommend(ws.report_record(), p.others(), None, any(d.get("use") for d in ws.ff_state))
        return [Recommendation(kind=k, text=t, other=o) for k, t, o in items]

    @r.post("/report", response_class=Response,
            responses={200: {"content": {"text/html": {}}, "description": "tuning protocol (HTML)"}})
    def report(wid: str, body: ReportReq):
        """Protokol z ladění (HTML): smyčky s modelem, sady, odezvy, APC, podpisy."""
        p = get_proj(wid)
        if p.state.model is None:
            raise HTTPException(409, "no model")
        bad = [s for s in body.sections if s not in rpt.SECTIONS]
        if bad:
            raise HTTPException(422, f"unknown section: {', '.join(bad)}")
        html = p.report_html(body.meta, body.sections, body.chart_mode)
        return Response(html, media_type="text/html")

    return r
