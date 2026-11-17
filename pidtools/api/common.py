"""Sdílené typy API: stav úlohy."""
from typing import cast

from pydantic import BaseModel

from ..core import MODELS


def model_params(code: str) -> list[str]:
    """Názvy parametrů modelu (hodnoty slovníku MODELS jsou smíšené, mypy je vidí jako object)."""
    return list(cast(list[str], MODELS[code]["params"]))


class JobInfo(BaseModel):
    id: str
    state: str
    progress: float
    text: str
    error: str | None = None
    cached: bool = False
    created: float
    started: float | None = None
    finished: float | None = None


def job_info(jobs, jid):
    return JobInfo(**jobs.status(jid))
