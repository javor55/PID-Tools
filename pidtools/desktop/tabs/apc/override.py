"""APC › Override: hlavní a omezující regulátor na jednom ventilu, výběr MIN/MAX s externím resetem."""
from ....app.apc import override as aov
from ....i18n import T
from ... import widgets as w
from .twoloop import TwoLoopPanel


class OverridePanel(TwoLoopPanel):
    kind = "override"

    def __init__(self, win):
        super().__init__(win, "apc_intro_override")
        self.sel = w.combo(["min", "max"], labels=[T("ov_min"), T("ov_max")])
        self.step = w.spin(0.0, -1e12, 1e12, 4)
        self.lim = w.spin(0.0, -1e12, 1e12, 4)
        self.sel.currentIndexChanged.connect(self._defaults)
        for sp in (self.step, self.lim):
            sp.valueChanged.connect(self._changed)
        self.left.addWidget(w.group(T("ov_select"), w.form([(T("ov_select"), self.sel), (T("dk_ov_step"), self.step),
                                                            (T("dk_ov_limit"), self.lim)])))
        self.res = w.note("")
        self.left.addWidget(self.res)
        self.left.addStretch(1)
        self.plots = self.chart(3, ("PV A", "PV B", "MV"), (0.36, 0.36, 0.28))
        self._pair_key = None

    def _defaults(self, *_):
        p = self.pair()
        if p is None or p[1]["model"] is None:
            return
        step, lim = aov.defaults(p[0], p[1], self.sel.currentData())
        self._busy = True
        self.step.setValue(step)
        self.lim.setValue(lim)
        self._busy = False
        self._changed()

    def update_pair(self, a, b):
        key = (b["name"], self.sel.currentData())
        if key != self._pair_key:            # nová dvojice → výchozí scénář
            self._pair_key = key
            self._defaults()
            return
        if b["c_mv"] != a["c_mv"]:
            self.need.setText("⚠️ " + T("ov_mv_differs", a=a["name"], b=b["name"], mva=a["c_mv"], mvb=b["c_mv"]))
        sel = self.sel.currentData()
        tt, o, o0 = aov.simulate(a, b, self.step.value(), self.lim.value(), sel)
        k = aov.kpis(a, b, o, o0, sel)

        def ea(x, r):
            return r[0] + x * (r[1] - r[0]) / 100
        for pl in self.plots:
            pl.clear()
        w.line(self.plots[0], tt, ea(o["SP_A"], a["pv_rng"]), "SP", w.C_SP, 1.3, dash=True)
        w.line(self.plots[0], tt, ea(o0["PV_A"], a["pv_rng"]), T("ov_without"), "#9aa5b1", 1.3, dash=True)
        w.line(self.plots[0], tt, ea(o["PV_A"], a["pv_rng"]), a["name"], w.C_PV, 2.0)
        w.line(self.plots[1], tt, ea(o["SP_B"], b["pv_rng"]), T("ov_limit_short"), "#dc2626", 1.3, dash=True)
        w.line(self.plots[1], tt, ea(o0["PV_B"], b["pv_rng"]), T("ov_without"), "#9aa5b1", 1.3, dash=True)
        w.line(self.plots[1], tt, ea(o["PV_B"], b["pv_rng"]), b["name"], "#7c3aed", 2.0)
        w.line(self.plots[2], tt, ea(o["U_A"], a["mv_rng"]), T("ov_out", n=a["name"]), w.C_PV, 1.1, dash=True)
        w.line(self.plots[2], tt, ea(o["U_B"], a["mv_rng"]), T("ov_out", n=b["name"]), "#7c3aed", 1.1, dash=True)
        w.line(self.plots[2], tt, ea(o["MV"], a["mv_rng"]), "MV", w.C_MV, 2.0)
        self.res.setText(f"{T('ov_peak', n=b['name'])}: **{k['peak']:.4g}** ({T('ov_without')}: {k['peak_without']:.4g})  \n"
                         f"{T('ov_time_b')}: {100 * k['share']:.0f} % · {T('ov_switches')}: {k['switches']}")
