"""
Projekt v desktopu: víc smyček nad jedním datovým souborem (každá má vlastní sloupce, rozsahy, model, ladění a APC).
Formát souboru je stejný jako ve webové aplikaci (app.project): záznam aktivní smyčky nahoře, „loops“ a „active“.
"""
from ..app import project as prj
from ..app.dataset import on_grid
from ..app.guess import guess_roles
from .state import LoopState


class Project:
    def __init__(self):
        self.loops = [LoopState()]
        self.active = 0

    @property
    def state(self):
        return self.loops[self.active]

    # ---- data (společná pro všechny smyčky)
    def _reset_to(self, ls):
        self.loops, self.active = [ls], 0

    def load_file(self, path):
        ls = LoopState()
        ls.load_file(path)
        self._reset_to(ls)

    def load_demo(self):
        ls = LoopState()
        ls.load_demo()
        self._reset_to(ls)

    def load_frame(self, df, name):
        """Data z tabulky (např. z OPC UA) – nový projekt s jednou smyčkou."""
        ls = LoopState()
        ls.load_frame(df, name)
        self._reset_to(ls)

    # ---- smyčky
    def names(self):
        return [ls.get("loop_tag") or str(ls.c_pv or f"#{i + 1}") for i, ls in enumerate(self.loops)]

    def add_loop(self):
        """Další smyčka ze stejných dat; PV se odhadne mimo PV ostatních smyček."""
        src = self.state
        if not src.has_data:
            return None
        ls = LoopState()
        ls.time_fmt, ls.unit = src.time_fmt, src.unit
        ls.load_frame(src.df, src.fname, src.layout)
        g = guess_roles(ls.sig.sigs, ls.sig.get, [x.c_pv for x in self.loops])
        ls.set_columns(g["pv"], g["mv"], g["sp"] or "—", [], g["pos"] or "—")
        ls.set(lang=src.get("lang"))
        self.loops.append(ls)
        self.active = len(self.loops) - 1
        return ls

    def add_loop_with(self, name, pv, mv, sp=None, pos=None):
        """Smyčka projektu se zadanými sloupci (např. z přehledu smyček)."""
        ls = self.add_loop()
        if ls is None:
            return None
        ls.set_columns(pv, mv, sp or "—", [], pos or "—")
        ls.set(loop_tag=name)
        return ls

    def remove_loop(self, i):
        if len(self.loops) > 1:
            del self.loops[i]
            self.active = min(self.active, len(self.loops) - 1)

    def others(self, include_without_model=False):
        """Ostatní smyčky jako záznamy pro APC (stejný tvar jako ui.loops.loop_data): [(index, záznam)]."""
        names = self.names()
        return [(i, dict(ls.report_record(), id=i + 1, name=names[i])) for i, ls in enumerate(self.loops)
                if i != self.active and ls.has_data and (include_without_model or ls.model is not None)]

    # ---- soubor projektu
    def to_project(self, include_data=False):
        recs = []
        for ls in self.loops:
            r = ls.to_project(False)
            for k in ("version", "fname"):
                r.pop(k, None)
            recs.append(r)
        act = self.state
        proj = dict(version=prj.PROJECT_VERSION, fname=act.fname, **recs[self.active])
        if len(self.loops) > 1:
            proj["loops"] = recs
            proj["active"] = self.active + 1
        if include_data and act.has_data:
            proj["data"] = act.to_project(True)["data"]
            cols = proj["data"]["cols"]
            for ls in self.loops:        # sloupce ostatních smyček na mřížce aktivní smyčky
                for c in [ls.c_pv, ls.c_mv, ls.c_sp, *ls.c_d]:
                    if c and c != "—" and str(c) not in cols and c in act.sig.sigs:
                        cols[str(c)] = on_grid(act.sig, act.grid, c, zoh=(c == ls.c_mv))
        return proj

    def save(self, path, include_data=True):
        with open(path, "w", encoding="utf-8") as f:
            f.write(prj.serialize_project(self.to_project(include_data)))

    def apply_project(self, proj):
        recs, act = prj.loop_records(proj)
        keep = self.state if self.state.has_data else None
        loops = []
        for rec in recs:
            ls = LoopState()
            if not rec.get("data") and keep is not None:       # projekt bez dat → data, která jsou načtená
                ls.time_fmt, ls.unit = keep.time_fmt, keep.unit
                ls.load_frame(keep.df, keep.fname, keep.layout)
            ls.apply_project(rec)
            loops.append(ls)
        self.loops, self.active = loops, act

    def load(self, path):
        with open(path, encoding="utf-8") as f:
            self.apply_project(prj.load_project(f.read()))

    # ---- protokol
    def report_html(self, meta, sections, chart_mode="inline"):
        from ..app import report
        from ..app.apc import recommend as reco
        recs, grids = [], {}
        for i, ls in enumerate(self.loops):
            if ls.model is None:
                continue
            r = dict(ls.report_record(), id=i + 1, name=self.names()[i], active=i == self.active)
            recs.append(r)
            grids[i + 1] = ls.grid
        act = self.state
        apc = {}
        if act.model is not None:
            apc["items"] = reco.recommend(act.report_record(), self.others(), None,
                                          any(d.get("use") for d in act.ff_state))

        def model_data(r):
            g = grids[r["id"]]
            return g.t, g.pv_e, g.mv_e, list(g.dists), g.Ts
        return report.build_report(recs, meta, sections, chart_mode, model_data, apc)
