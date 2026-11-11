"""
API – průvodce záložky (E2): postup, kontrolní seznam podle živého stavu projektu, tabulky „která volba kdy“
a slovníček. Obsah i kontroly jsou v app.guides (sdílí je desktop a web), zde jen tenký obal s typy pro OpenAPI.
"""
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..app import guides

GuideTab = Literal["data", "model", "tuning", "apc", "live", "diag", "loops", "project"]


class GuideStep(BaseModel):
    title: str
    text: str                       # markdown


class GuideAction(BaseModel):
    """Tlačítko u položky seznamu: přepnout záložku a případně skočit na prvek (data-testid)."""
    tab: str
    target: str | None = None
    label: str


class GuideCheck(BaseModel):
    ok: Literal["ok", "warn", "todo"]     # splněno / vyžaduje pozornost / ještě neprovedeno
    text: str
    action: GuideAction | None = None


class GuideTable(BaseModel):
    title: str
    md: str                         # markdown (tabulky v zápisu GitHub, odstavce)


class GlossaryItem(BaseModel):
    term: str
    text: str


class Guide(BaseModel):
    tab: GuideTab
    title: str
    intro: str                      # „K čemu“ (markdown)
    steps: list[GuideStep]
    checklist: list[GuideCheck]
    tables: list[GuideTable]
    tips: str                       # tipy z praxe (markdown)
    glossary: list[GlossaryItem]


def router(get_proj):
    r = APIRouter(prefix="/workspaces/{wid}", tags=["guide"])

    @r.get("/guide/{tab}", response_model=Guide)
    def guide_get(wid: str, tab: str):
        """Průvodce záložky; kontrolní seznam se počítá ze stavu aktivní smyčky (data, model, sady, Ms, projekt …)."""
        if tab not in guides.GUIDE_TABS:
            raise HTTPException(404, "tab not found")
        return guides.guide(tab, guides.state_of(get_proj(wid)))

    return r
