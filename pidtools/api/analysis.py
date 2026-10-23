"""
API – diagnostika, doporučení APC a protokol (M11): KPI a ventil úseku, hystereze, nelinearita, doporučené
struktury APC pro aktivní smyčku a protokol z ladění (HTML, jako v obou dnešních rozhraních).
"""
from typing import Literal

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from ..app import report as rpt
from ..app.apc import recommend as reco
from .data import _plain


class Diagnostics(BaseModel):
    a: float
    b: float
    kpis: dict
    valve: dict
    hysteresis: float | None = None
    nonlinearity: dict | None = None


class Recommendation(BaseModel):
    kind: str
    text: str
    other: int | None = None


class ReportReq(BaseModel):
    meta: dict = {}
    sections: list[str] = list(rpt.SECTIONS)
    chart_mode: Literal["inline", "cdn"] = "inline"


def router(get_proj):
    r = APIRouter(prefix="/workspaces/{wid}", tags=["diagnostics"])

    def need_data(wid):
        ws = get_proj(wid).state
        if not ws.has_data:
            raise HTTPException(409, "no data")
        return ws

    @r.get("/diagnostics", response_model=Diagnostics)
    def diagnostics(wid: str, a: float | None = None, b: float | None = None, integ: bool | None = None):
        """Diagnostika úseku (výchozí: úsek identifikace); integ = integrační proces (výchozí podle modelu)."""
        ws = need_data(wid)
        a, b = (a, b) if a is not None and b is not None else ws.rng
        if (ws.range_mask(a, b)).sum() < 100:
            raise HTTPException(422, "segment too short")
        integ = bool(integ) if integ is not None else bool(ws.model and ws.model[0].startswith("I"))
        nl = ws.nonlinearity()
        h = ws.hysteresis(a, b)
        return Diagnostics(a=a, b=b, kpis=_plain(ws.diag_kpis(a, b)), valve=_plain(ws.valve(a, b, integ)),
                           hysteresis=_plain(h), nonlinearity=_plain(dict(gains=nl[0], spread=nl[1])) if nl else None)

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
