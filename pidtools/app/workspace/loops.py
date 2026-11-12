"""
Projekt: víc smyček nad zdroji dat (každá má vlastní sloupce, rozsahy, model, ladění a APC). Zdroje (soubory, OPC UA),
mapování rolí smyček a společná časová mřížka jsou v `app.domain` a `app.workspace.sources`; `Workspace` zůstává
fasádou výpočtů jedné smyčky. Formát souboru (app.project, verze 3): záznam aktivní smyčky nahoře, „loops“, „active“,
„sources“ a „time_grid“; starší soubory se při otevření převedou migrací.
"""
from .. import project as prj
from .. import journal as jr
from ..domain import Snapshot, migrate_project
from ..domain.model import FORMAT, VERSION, TimeGrid
from ..domain.model import Project as DomainProject
from ..guess import guess_roles
from . import Workspace
from .sources import SourceRT, SourcesMixin, embedded_frame


class Project(SourcesMixin):
    def __init__(self):
        self.loops = [Workspace()]
        self.active = 0
        self.sources = []                 # [SourceRT] – zdroje dat (app.workspace.sources)
        self.time_grid = TimeGrid()       # společná časová mřížka více zdrojů
        self.journal = []                 # [Snapshot] – deník ladění (app.journal)

    @property
    def state(self):
        return self.loops[self.active]

    # ---- data (společná pro všechny smyčky)
    def _reset_to(self, ls, kind=None):
        self.loops, self.active, self.sources, self.journal = [ls], 0, [], []
        self.sync()                       # tabulka smyčky se stane jediným zdrojem
        if kind and self.sources:
            self.sources[0].src.kind = kind

    def load_file(self, path):
        ls = Workspace()
        ls.load_file(path)
        self._reset_to(ls)

    def load_demo(self):
        ls = Workspace()
        ls.load_demo()
        self._reset_to(ls)

    def load_frame(self, df, name, kind=None):
        """Data z tabulky (např. z OPC UA) – nový projekt s jednou smyčkou a jedním zdrojem (druh podle `kind`)."""
        ls = Workspace()
        ls.load_frame(df, name)
        self._reset_to(ls, kind)

    # ---- smyčky
    def names(self):
        return [ls.get("loop_tag") or str(ls.c_pv or f"#{i + 1}") for i, ls in enumerate(self.loops)]

    def add_loop(self):
        """Další smyčka ze stejných dat; PV se odhadne mimo PV ostatních smyček."""
        src = self.state
        if not src.has_data:
            return None
        self.sync()
        ls = Workspace()
        ls.time_fmt, ls.unit, ls.ts_user = src.time_fmt, src.unit, src.ts_user
        ls.origin_hint, ls.merged_df = src.origin_hint, src.merged_df
        ls.load_frame(src.df, src.fname, src.layout, c_time=src.c_time, c_tag=src.c_tag, c_val=src.c_val,
                      row_dt=src.row_dt)
        ls.src_ids, ls.name_refs = list(src.src_ids), dict(src.name_refs)
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
        """Soubor projektu verze 3: záznam aktivní smyčky, smyčky se `spec`, zdroje (s daty) a časová mřížka."""
        self.sync()
        recs = []
        for i, ls in enumerate(self.loops):
            r = ls.to_project(False)
            for k in ("version", "fname"):
                r.pop(k, None)
            r["spec"] = self.loop_spec(i).to_dict()
            recs.append(r)
        act = self.state
        proj = dict(version=VERSION, format=FORMAT, fname=act.fname, **recs[self.active])
        if len(self.loops) > 1:
            proj["loops"] = recs
            proj["active"] = self.active + 1
        used = {}                                       # sloupce zdrojů, které používá nějaká role (ukládají se jen ty)
        for i in range(len(self.loops)):
            for ref in self.loop_spec(i).roles.refs():
                used.setdefault(ref.source_id, []).append(ref.column)
        proj["sources"] = [rt.to_dict(include_data, list(dict.fromkeys(used.get(rt.id, [])))) for rt in self.sources]
        proj["time_grid"] = self.time_grid.to_dict()
        if self.journal:
            proj["journal"] = [sn.to_dict() for sn in self.journal]
        return proj

    def save(self, path, include_data=True):
        with open(path, "w", encoding="utf-8") as f:
            f.write(prj.serialize_project(self.to_project(include_data)))

    def apply_project(self, proj):
        """
        Obnova projektu libovolné verze (starší se převedou migrací). Zdroje s uloženými daty se načtou z projektu;
        projekt bez dat použije data, která jsou v projektu načtená (podle názvu zdroje, jinak podle pořadí).
        """
        proj = migrate_project(proj)
        dom = DomainProject.from_dict(proj)
        self.sync()
        keep = list(self.sources)
        rts = []
        for k, (src, sd) in enumerate(zip(dom.sources, proj["sources"])):
            if sd.get("data"):
                df, origin = embedded_frame(sd["data"])
                rts.append(SourceRT(src, df, origin))
                continue
            old = next((r for r in keep if r.src.name == src.name), keep[k] if k < len(keep) else None)
            if old is None and keep:
                old = keep[0]
            rts.append(SourceRT(src, old.df if old else None, old.origin if old else None))
            if old is not None:                                 # data a čtení tabulky podle původního souboru
                src.name, src.options = old.src.name, dict(old.src.options)
        recs, act = prj.loop_records(proj)
        self.sources, self.time_grid = rts, dom.time_grid
        loops = []
        for rec, spec in zip(recs, dom.loops):
            ls = Workspace()
            ids = list(dict.fromkeys(r.source_id for r in spec.roles.refs())) or [rts[0].id if rts else None]
            if ids[0] is not None and all(self.rt(i).df is not None for i in ids):
                ts = rec.get("tag", "")
                emb = self.rt(ids[0]).src.data.embedded and len(ids) == 1
                self._feed(ls, ids, fname=f"project|{ts}" if emb else None)
                inv = {v: k for k, v in ls.name_refs.items()}
                mp = dict(rec.get("map") or {})
                for key, ref in (("c_pv", spec.roles.pv), ("c_mv", spec.roles.mv), ("c_sp", spec.roles.sp),
                                 ("c_pos", spec.roles.pos)):
                    if ref in inv:
                        mp[key] = inv[ref]
                if all(r in inv for r in spec.roles.dv):
                    mp["c_d"] = [inv[r] for r in spec.roles.dv]
                rec = {**rec, "map": mp}
            ls.apply_project(rec)
            ls.extra = dict(description=spec.description, mode=spec.roles.mode.to_dict() if spec.roles.mode else None,
                            cascade_to=spec.cascade_to)
            loops.append(ls)
        self.loops, self.active = loops, act
        self.journal = [Snapshot.from_dict(d) for d in proj.get("journal") or []]
        jr.migrate_live_runs(self)           # starší souhrny živé simulace (live_runs) → záznamy deníku

    def load(self, path):
        with open(path, encoding="utf-8") as f:
            self.apply_project(prj.load_project(f.read()))

    # ---- protokol
    def report_html(self, meta, sections, chart_mode="inline", ab=None):
        from .. import report
        from ..apc import recommend as reco
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
        ctx = jr.report_ctx(self, recs, sections, ab)
        return report.build_report(recs, meta, sections, chart_mode, model_data, apc, ctx)
