"""Sdílené typy API: stav úlohy."""
from pydantic import BaseModel


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
