"""
Projekt a protokol: uložení a obnovení smyčky ze záznamu projektu (formát app.project), protokol (M4d).
"""
import numpy as np
import pandas as pd

from .. import project as prj
from . import DEFAULTS  # definované v __init__ před importem částí


class ProjectMixin:
    """Část pracovního prostoru – metody pracují se stavem Workspace (self)."""

    # ---- projekt
    def to_project(self, include_data=False):
        state = {k: prj.jsonable(v) for k, v in self.settings.items() if prj.is_state_key(k) and v is not None}
        rec = dict(tag=self.get("loop_tag", ""), state=state,
                   map=dict(c_pv=self.c_pv, c_mv=self.c_mv, c_sp=self.c_sp, c_d=list(self.c_d), c_pos=self.c_pos),
                   ranges={"id": list(self.rng), "val": list(self.rng)}, ff=list(self.ff_state))
        fit = prj.fit_record(self.fit)
        if fit:
            rec["fit"] = fit
        if self.wins or self.excl:                    # úseky podle vstupů a vyřazení dat (jako web)
            rec["windows"] = prj.jsonable(dict(wins=self.wins_s, excl=dict(self.excl), tol=float(self.excl_tol)))
        proj = dict(version=prj.PROJECT_VERSION, fname=self.fname, **rec)
        if include_data and self.has_data:
            g = self.grid
            cols = {"t_s": g.t, str(self.c_pv): g.pv_e, str(self.c_mv): g.mv_e}
            if g.has_sp:
                cols[str(self.c_sp)] = g.sp_e
            for nm, d in zip(self.c_d, g.dists):
                cols[str(nm)] = d
            proj["data"] = {"cols": cols}
        return proj

    def save_project(self, path, include_data=True):
        with open(path, "w", encoding="utf-8") as f:
            f.write(prj.serialize_project(self.to_project(include_data)))

    def apply_project(self, proj):
        """Obnova z projektu (aktivní smyčka). Data z projektu, jsou-li uložená; jinak zůstanou načtená data."""
        recs, act = prj.loop_records(proj)
        rec = recs[act]
        if proj.get("data"):
            cols = proj["data"]["cols"]
            self.load_frame(pd.DataFrame({k: np.asarray(v, float) for k, v in cols.items()}),
                            f"project|{proj.get('tag', '')}", layout="wide")
        self.settings = dict(DEFAULTS, **prj.migrate_state(rec.get("state", {})))
        mp = rec.get("map", {})
        if self.has_data and mp.get("c_pv") in self.sig.sigs and mp.get("c_mv") in self.sig.sigs:
            self.set_columns(mp["c_pv"], mp["c_mv"], mp.get("c_sp", "—"),
                             [c for c in mp.get("c_d", []) if c in self.sig.sigs], mp.get("c_pos", "—"))
        rg = (rec.get("ranges") or {}).get("id")
        if rg and self.has_data:
            self.rng = (float(rg[0]), float(rg[1]))
        self.ff_state = rec.get("ff") or []
        win = rec.get("windows") or {}
        self.wins = {str(k): [[float(a), float(b)] for a, b in v] for k, v in (win.get("wins") or {}).items()}
        self.excl = {str(k): list(v) for k, v in (win.get("excl") or {}).items()}
        self.excl_tol = float(win.get("tol", 0.5))
        if rec.get("fit"):
            self.fit = dict(res=rec["fit"]["res"], dnames=list(rec["fit"]["dnames"]), key="__restore__")
            if self.has_data:
                self.fit["key"] = self.fit_key()

    def load_project(self, path):
        with open(path, encoding="utf-8") as f:
            self.apply_project(prj.load_project(f.read()))

    # ---- protokol
    def report_record(self):
        """Záznam smyčky pro app.report."""
        return dict(id=1, name=self.get("loop_tag") or str(self.c_pv), active=True, model=self.model,
                    ctrl=self.set_ctrl(2), ctrl1=self.set_ctrl(1), rng=tuple(self.rng),
                    fit=self.fit["res"][self.model[0]]["fit"] if self.model else None,
                    c_pv=self.c_pv, c_mv=self.c_mv, c_sp=self.c_sp, c_d=list(self.c_d), pv_rng=(self.pv_lo, self.pv_hi),
                    mv_rng=(self.mv_lo, self.mv_hi), u_pv=self.get("u_pv", ""), u_mv=self.get("u_mv", ""))

    def report_html(self, meta, sections, chart_mode="inline"):
        from .. import report
        from ..apc import recommend as reco
        g = self.grid
        rec = self.report_record()
        apc = dict(items=reco.recommend(rec, [], None, any(d.get("use") for d in self.ff_state)))
        return report.build_report([rec], meta, sections, chart_mode,
                                   lambda r: (g.t, g.pv_e, g.mv_e, list(g.dists), g.Ts), apc)
