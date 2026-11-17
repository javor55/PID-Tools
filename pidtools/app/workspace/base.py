"""
Typová kostra pracovního prostoru (TICKET-018): atributy a členy, které si mixiny (data, ident, tuning, …) navzájem
půjčují přes `self`. Za běhu zde nic není kromě anotací atributů (bez hodnot); deklarace členů jiných mixinů jsou
jen pro kontrolu typů (`TYPE_CHECKING`) a skutečné metody mixinů je při běhu přebíjejí.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypedDict

import numpy as np
import pandas as pd

from ..dataset import Grid, Signals
from ..loop import Scaling


class FitState(TypedDict):
    """`Workspace.fit`: výsledky identifikace modelů."""
    res: dict[str, dict[str, Any]]      # {kód modelu: výsledek fitu}
    dnames: list[str]                   # názvy poruch, pro které se fitovalo
    key: Any                            # klíč vstupů fitu (fit_key, nebo "__restore__") – pozná zastaralý výsledek


class UncState(TypedDict):
    """`Workspace.unc`: nejistota modelu (bootstrap)."""
    code: str                           # kód modelu
    key: object                         # klíč vstupů, pro které nejistota platí
    ps: list[Any]                       # parametry variant modelu


class CvState(TypedDict):
    """`Workspace.cv`: křížové ověření."""
    key: Any
    res: dict[str, list[float]]         # {kód modelu: [FIT]}


class WsBase(Scaling):
    """Atributy `Workspace` (přiřazují se v `Workspace.__init__`)."""
    settings: dict[str, Any]
    df: pd.DataFrame | None
    fname: str
    layout: str
    time_fmt: str
    unit: str
    c_time: str | None
    c_tag: str | None
    c_val: str | None
    ts_user: float | None
    row_dt: float
    sig: Signals        # před načtením dat None (viz Workspace.__init__); přístup až po `has_data`
    origin_hint: pd.Timestamp | None
    src_ids: list[str]
    name_refs: dict[str, Any]
    merged_df: pd.DataFrame | None
    extra: dict[str, Any]
    grid: Grid          # před načtením dat None (viz Workspace.__init__); přístup až po `has_data`
    c_pv: str | None
    c_mv: str | None
    c_sp: str
    c_d: list[str]
    c_pos: str
    rng: tuple[float, float]
    fit: FitState | None
    ff_state: list[Any]
    controller: dict[str, Any] | None
    sim_sp: tuple[float, float] | None
    val_status: tuple[Any, int] | None   # (otisk modelu, 0 dobrá / 1 stejný úsek / 2 slabá) – viz _remember_validation
    unc: UncState | None
    smith_opt: dict[Any, Any]
    apc_loops: dict[Any, Any]
    wins: dict[str, list[list[float]]]
    excl: dict[str, list[Any]]
    excl_tol: float
    cv: CvState | None

    def fit_res(self) -> dict[str, dict[str, Any]]:
        """Výsledky identifikace {kód: výsledek}; volat až po identifikaci (jinak chyba místo TypeError)."""
        if self.fit is None:
            raise RuntimeError("identifikace ještě neproběhla")
        return self.fit["res"]

    if TYPE_CHECKING:
        # členy ostatních mixinů a Workspace, které se používají napříč mixiny
        def get(self, k: str, default: Any = None) -> Any: ...
        def set(self, **kw: Any) -> None: ...

        pv_lo: float
        pv_hi: float
        mv_lo: float
        mv_hi: float

        @property
        def has_data(self) -> bool: ...
        @property
        def t(self) -> np.ndarray: ...
        @property
        def pv(self) -> np.ndarray: ...
        @property
        def mv(self) -> np.ndarray: ...
        @property
        def sp(self) -> np.ndarray: ...
        @property
        def inputs_mode(self) -> bool: ...
        @property
        def wins_s(self) -> dict[str, list[list[float]]]: ...
        @property
        def win_idx(self) -> Any: ...
        @property
        def id_rng(self) -> tuple[float, float]: ...
        @property
        def sel_mask(self) -> np.ndarray: ...
        @property
        def valid(self) -> Any: ...
        @property
        def model(self) -> Any: ...
        @property
        def norm(self) -> tuple[float, float, float, float]: ...
        @property
        def excl_key(self) -> Any: ...
        def fit_key(self) -> tuple[Any, ...]: ...
        def val_rng(self) -> tuple[float, float]: ...
        def set_wins(self, inp: Any, wins: Any) -> None: ...
        def set_ctrl(self, n: int) -> dict[str, Any]: ...
        def load_frame(self, df: pd.DataFrame, name: str, layout: str | None = None, sig: Signals | None = None,
                       **opts: Any) -> None: ...
        def set_columns(self, c_pv: str | None, c_mv: str | None, c_sp: str = "—", c_d: Any = (),
                        c_pos: str = "—") -> None: ...
        def dkinds(self) -> list[str]: ...
        def dsigns(self) -> list[int]: ...
        def segment(self) -> Any: ...
        def evaluate(self) -> Any: ...
        def unc_models(self) -> Any: ...
        def set_ctrl_plain(self, n: Any) -> Any: ...
        def work_ctrl(self) -> Any: ...
