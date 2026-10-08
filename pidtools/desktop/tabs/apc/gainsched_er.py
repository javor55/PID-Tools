"""
APC › Gain scheduling podle regulační odchylky (ER): vyšší zesílení při velké odchylce (rychlejší návrat
z okrajových stavů), bezpečný násobek k, srovnání s řídicím pásmem ConZone.
"""
from ....app.apc import gainsched as ags
from ....core import MODELS
from ....i18n import T
from ... import widgets as w
from .common import Panel


class GainSchedErPanel(Panel):
    def __init__(self, win):
        super().__init__(win, "gs_er_intro")
        self.E = w.spin(5.0, 0.0, 1e12, 4)
        self.k = w.spin(2.0, 1.0, 6.0, 2, 0.25)
        self.spstep = w.spin(10.0, -1e12, 1e12, 4)
        self.d = w.spin(10.0, -100, 100, 3)
        for sp in (self.E, self.k, self.spstep, self.d):
            sp.valueChanged.connect(self._simulate)
        self.kmax = w.note("")
        self.left.addWidget(w.group(T("gs_x_er"), w.form([
            (T("dk_gser_E", u="PV"), self.E), (T("dk_gser_k"), self.k), (T("dk_gser_sp", u="PV"), self.spstep),
            (T("dk_gser_d"), self.d),
            ("", self.reset_button((self.E, self.k, self.spstep, self.d),
                                   lambda: (round(0.05 * self.s.PR, 6), 2.0, round(0.2 * self.s.PR, 6), 10.0),
                                   self._simulate))])))
        self.left.addWidget(self.kmax)
        self.vals = w.table([], [], stretch=False)
        self.vals.setMinimumHeight(150)
        self.left.addWidget(w.group(T("dk_gs_table"), w.form([("", self.vals)])))
        self.cz = w.note("")
        self.left.addWidget(self.cz)
        self.left.addStretch(1)
        self.plots = self.chart(3, ("PV", "MV", "Gain"), (0.5, 0.27, 0.23))
        self.kpi = self.table(130)

    def refresh(self):
        s = self.s
        if s.model is None:
            return
        self._busy = True
        self.E.setValue(float(s.get("gs_er_E", round(0.05 * s.PR, 6))))
        self.k.setValue(float(s.get("gs_er_k", 2.0)))
        self.spstep.setValue(float(s.get("gs_er_spstep", round(0.2 * s.PR, 6))))
        self.d.setValue(float(s.get("gs_er_d", 10.0)))
        self._busy = False
        code, p, _ = s.model
        km = ags.k_max(code, p, s.set_ctrl(2))
        self.kmax.setText(T("dk_gser_kmax", k=f"{km:g}"))
        self._simulate()

    def _simulate(self, *_):
        s = self.s
        if self._busy or s.model is None:
            return
        if MODELS[s.model[0]]["integ"]:          # scheduling je navržený pro samoregulační procesy
            self.cz.setText("⚠️ " + T("gs_integ"))
            return
        s.set(gs_er_E=self.E.value(), gs_er_k=self.k.value(), gs_er_spstep=self.spstep.value(), gs_er_d=self.d.value())
        code, p, _ = s.model
        set2 = {k: v for k, v in s.set_ctrl(2).items() if k not in ("FF", "FF_LL")}
        step_pct = float(max(-45, min(45, self.spstep.value() / s.PR * 100)))
        r = ags.simulate_er(code, p, set2, self.E.value() / s.PR * 100, self.k.value(), step_pct, self.d.value(),
                            float(s.get("samp")))
        tab = ags.er_table(self.E.value(), self.k.value(), set2, s.get("u_pv") or "PV")
        w.fill(self.vals, [T("gs_in"), "1", "2", "3", T("sm_apl_unit")], [[nm, *vals, u] for nm, vals, u in tab])
        self.vals.resizeColumnsToContents()
        for pl in self.plots:
            pl.clear()
        t, sp = r["t"], r["sp"]
        w.line(self.plots[0], t, s.EP(sp), "SP", w.C_SP, 1.3, dash=True)
        rows = []
        for key, (tt, o), col, dash in (("gs_fixed", r["fixed"], w.C_SET1, True), ("gs_er_sched", r["sched"], w.C_SET2, False)):
            w.line(self.plots[0], tt, s.EP(o["PV"]), T(key), col, 1.8, dash)
            w.line(self.plots[1], tt, s.EM(o["MV"]), T(key), col, 1.5, dash)
            w.line(self.plots[2], tt, o["Gain"], T(key), col, 1.5, dash)
            rows.append((T(key), ags.er_kpis(t, sp, r["tp"], o, set2, s.PR)))
        if r["zone"] is not None:
            o = r["zone"]
            w.line(self.plots[0], t, s.EP(o["PV"]), T("gs_er_cz"), "#7c3aed", 1.6, True)
            w.line(self.plots[1], t, s.EM(o["MV"]), T("gs_er_cz"), "#7c3aed", 1.4, True)
            rows.append((T("gs_er_cz"), ags.er_kpis(t, sp, r["tp"], o, set2, s.PR)))
            self.cz.setText(T("gs_er_cz_best", w=f"{r['cz'] * s.PR / 100:.4g}", u=s.get("u_pv") or "PV"))
        else:
            self.cz.setText(T("gs_er_cz_none"))
        w.fill(self.kpi, [T("setting"), T("iae_sp"), T("iae_load"), T("gs_er_maxdev"), T("gs_er_sat"),
                          T("gs_er_settled")],
               [[nm, q["iae_sp"], q["iae_d"], q["maxdev"], f"{100 * q['sat']:.0f} %", "✓" if q["settled"] else "✗"]
                for nm, q in rows])
