"""
Kontext jednoho běhu aplikace – data a výsledky, které si záložky předávají.

Pořadí plnění odpovídá pořadí vykreslení: horní panel → sloupce a normování (Data) → konfigurace bloku
(Ladění) → záložky Data, Model, Ladění, Živá simulace, Diagnostika, Kaskáda, Projekt → ukazatel postupu.
Veličiny PV, SP, MV jsou v % normovacích rozsahů (NormPV, NormMV), poruchy v inženýrských jednotkách.
"""
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

from ..app.loop import Scaling, set_ctrl
from ..i18n import T
from .charts import mkfig, style, tr
from .theme import C_MV, C_PV, C_SP, _c_dist


@dataclass
class Ctx(Scaling):
    # ---- horní panel
    df: Any = None                 # načtená tabulka
    fname: str = ""                # identita souboru (klíče widgetů)
    ckey: str = ""                 # klíč cache pro načtení
    status_ph: Any = None          # místo pro souhrn dat
    H: int = 460                   # výška grafů
    tabs: dict = field(default_factory=dict)
    PROG: dict = field(default_factory=dict)
    gph: dict = field(default_factory=dict)      # záložky s průvodcem (vykreslí pages.guides na konci běhu)
    help_ph: object = None                       # místo v nápovědě „?“ hlavičky pro průvodce aktivní záložky
    active_tab: str = "data"                     # klíč aktivní záložky
    dq: Any = None                 # hodnocení kvality dat vybraného úseku   # stav kroků postupu (0 ok, 1 výhrada, 2 problém, None nehotovo)
    # ---- data a výběr sloupců
    t_all: Any = None
    sigs: list = field(default_factory=list)
    get: Callable = None           # sloupec → pole čísel
    long_fmt: bool = False
    t_origin: Any = None           # pd.Timestamp času 0 (u časů zadaných datem), jinak None
    c_pv: str = ""
    c_mv: str = ""
    c_sp: str = "—"
    c_d: list = field(default_factory=list)
    c_pos: str = "—"
    t: Any = None                  # společná časová mřížka [s]
    Ts: float = 1.0
    T0: float = 0.0
    pv_raw: Any = None
    pv_e: Any = None               # PV, MV, SP v inženýrských jednotkách
    mv_e: Any = None
    sp_e: Any = None
    dists: list = field(default_factory=list)
    pos_e: Any = None
    has_sp: bool = False
    # ---- normování
    norm_ok: bool = True
    sim_sp0: float = 0.0
    pv_lo: float = 0.0
    pv_hi: float = 100.0
    mv_lo: float = 0.0
    mv_hi: float = 100.0
    u_pv: str = ""
    u_mv: str = "%"
    pv: Any = None                 # PV, MV, SP v %
    mv: Any = None
    sp: Any = None
    # ---- blok PIDConL
    samp: float = 1.0
    diffgain: float = 5.0
    propfac: float = 1.0
    dfb: bool = True
    pvfilt: float = 0.0
    mvl_lo: float = 0.0
    mvl_hi: float = 100.0
    base_ctrl: dict = field(default_factory=dict)
    block_summary: str = ""
    # ---- úsek identifikace
    rng: tuple = (0.0, 0.0)
    sel_mask: Any = None
    ts_id: Any = None
    pv_id: Any = None
    mv_id: Any = None
    d_id: list = field(default_factory=list)
    # ---- úseky podle vstupů
    win_mode: str = "common"       # "common" = jeden úsek pro všechny vstupy, "inputs" = úseky podle vstupů
    win_idx: list = field(default_factory=list)      # [(i0, i1)] indexy úseků (všechny vstupy)
    wins_s: dict = field(default_factory=dict)       # {vstup: [(od, do) s]}
    valid: Any = None              # vzorky do fitu (vyřazení podle mezí)
    excl_key: Any = None
    # ---- model
    model: Any = None              # (kód, parametry, parametry poruch)
    model_stic: float = 0.0
    model_level: str = "none"
    model_Th: Any = None
    sigma_pv: float = 0.0
    unc_models: list = field(default_factory=list)
    # ---- ladění
    set1_ctrl: Any = None
    set2_ctrl: Any = None
    plant: dict = field(default_factory=dict)

    @property
    def lab_pv(self):
        return f"PV [{self.u_pv}]" if self.u_pv else "PV"

    @property
    def lab_mv(self):
        return f"MV [{self.u_mv}]" if self.u_mv else "MV"

    @property
    def lab_t(self):
        return T("time_s")

    def on_grid(self, col, zoh=False):
        """Libovolný sloupec převzorkovaný na společnou časovou mřížku t."""
        v = self.get(col)
        m = np.isfinite(self.t_all) & np.isfinite(v)
        tv, cv = self.t_all[m], v[m]
        o = np.argsort(tv)
        tv, cv = tv[o], cv[o]
        if len(tv) < 2:
            return np.full_like(self.t, np.nan)
        if zoh:
            j = np.clip(np.searchsorted(tv, self.t + self.T0, side="right") - 1, 0, len(tv) - 1)
            return cv[j]
        return np.interp(self.t + self.T0, tv, cv)

    def data_fig(self, ts, sel_mask=None, extra_pv=(), resid=None, height=None):
        """Graf dat: PV (+SP, + další průběhy), volitelně rezidua, MV a měřené poruchy."""
        nr = 2 + (1 if self.dists else 0) + (1 if resid is not None else 0)
        hs = {2: [0.64, 0.36], 3: [0.5, 0.25, 0.25], 4: [0.44, 0.16, 0.2, 0.2]}[nr]
        f = mkfig(nr, hs)
        g = (lambda a: a[sel_mask]) if sel_mask is not None else (lambda a: a)
        if self.has_sp:
            f.add_trace(tr(ts, self.EP(g(self.sp)), "SP", C_SP, 1.4, "dash"), 1, 1)
        f.add_trace(tr(ts, self.EP(g(self.pv)), "PV", C_PV, 1.3), 1, 1)
        for name, y, col, dash in extra_pv:
            f.add_trace(tr(ts, self.EP(y), name, col, 2.2, dash), 1, 1)
        row = 2
        ytit = [self.lab_pv]
        if resid is not None:
            for name, y, col, dash in extra_pv:
                f.add_trace(tr(ts, (g(self.pv) - y) * self.PR / 100, f"{T('resid')} {name}", col, 1.2, dash,
                               show=False, group=name), row, 1)
            ytit.append(T("resid"))
            row += 1
        f.add_trace(tr(ts, self.EM(g(self.mv)), "MV", C_MV, 1.6, shape="hv"), row, 1)
        ytit.append(self.lab_mv)
        row += 1
        for i, (nm, d) in enumerate(zip(self.c_d, self.dists)):
            f.add_trace(tr(ts, g(d), str(nm), _c_dist()[i % 4], 1.4), row, 1)
        if self.dists:
            ytit.append(T("dists"))
        return style(f, height or (self.H + (90 if self.dists else 0) + (80 if resid is not None else 0)), ytit,
                     self.lab_t)

    def set_ctrl(self, n, ff=(), ffll=()):
        """Parametry sady n (1 nebo 2) z session state jako slovník pro simulaci."""
        import streamlit as st
        ss = st.session_state
        g = ss.get(f"set{n}_gain", 1.0)
        ti = ss.get(f"set{n}_ti", 100.0)
        td = ss.get(f"set{n}_td", 0.0)
        return set_ctrl(self.base_ctrl, g, ti, td, ff, ffll)
