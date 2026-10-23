"""
API – OPC UA, jen čtení (M11): procházení a hledání v adresním prostoru serveru, načtení historie vybraných
uzlů do pracovního prostoru (úloha). Do serveru se nic nezapisuje. Volitelná závislost asyncua.
"""
import datetime as dt

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..app import opc
from .common import JobInfo, job_info


class Server(BaseModel):
    url: str
    user: str | None = None
    password: str | None = None
    timeout: float = 10.0


class Browse(Server):
    node_id: str | None = None
    parent_path: str = ""


class Find(Server):
    text: str
    node_id: str | None = None


class Node(BaseModel):
    node_id: str
    name: str
    path: str
    is_var: bool


class History(Server):
    nodes: dict[str, str]                 # {node_id: tag}
    start: dt.datetime
    end: dt.datetime


def read_history(url, user, password, timeout, nodes, start, end, progress=None):
    """Úloha: historie uzlů → dlouhá tabulka (Tag, Time, Value); uzly bez historie v atributu `empty`."""
    with opc.Connection(url, user, password, timeout) as c:
        series = c.history(list(nodes), start, end,
                           (lambda i, n: progress(i / max(len(nodes), 1), str(n))) if progress else None)
    df = opc.to_frame(series, nodes)
    return df, [nodes[n] for n, (ts, _) in series.items() if not ts]


def _conn(body):
    if not opc.available():
        raise HTTPException(501, "asyncua not installed")
    return opc.Connection(body.url, body.user, body.password, body.timeout)


def router(get_proj, jobs):
    r = APIRouter(tags=["opcua"])

    @r.get("/opc/available", response_model=bool)
    def available():
        return opc.available()

    @r.post("/opc/browse", response_model=list[Node])
    def browse(body: Browse):
        """Podřízené uzly (výchozí: složka Objects)."""
        try:
            with _conn(body) as c:
                return [Node(**vars(it)) for it in c.children(body.node_id, body.parent_path)]
        except HTTPException:
            raise
        except Exception as ex:
            raise HTTPException(502, f"OPC UA: {ex}") from ex

    @r.post("/opc/find", response_model=list[Node])
    def find(body: Find):
        """Proměnné, jejichž cesta obsahuje text (např. „FIC101“)."""
        try:
            with _conn(body) as c:
                return [Node(**vars(it)) for it in c.find(body.text, body.node_id)]
        except HTTPException:
            raise
        except Exception as ex:
            raise HTTPException(502, f"OPC UA: {ex}") from ex

    @r.post("/workspaces/{wid}/opc/history", response_model=JobInfo)
    def history(wid: str, body: History):
        """Historie vybraných uzlů (úloha) → data pracovního prostoru (nový projekt s jednou smyčkou)."""
        if not opc.available():
            raise HTTPException(501, "asyncua not installed")
        if not body.nodes:
            raise HTTPException(422, "no nodes")
        get_proj(wid)

        def done(out):
            df, _empty = out
            if df.empty:
                raise ValueError("opc_empty")
            get_proj(wid).load_frame(df, "OPC UA")
        jid = jobs.submit(read_history, body.url, body.user, body.password, body.timeout, body.nodes, body.start,
                          body.end, timeout=600, on_done=done)
        return job_info(jobs, jid)

    return r
