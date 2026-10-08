"""APC › Rozvazbení 2×2: RGA a párování, decouplery (statické / dynamické), simulace změn SP obou smyček."""
from ....app.apc import decouple as adec
from ....core.apc import rga_advice
from ....i18n import T
from ... import widgets as w
from .twoloop import TwoLoopPanel


class DecouplePanel(TwoLoopPanel):
    kind = "decouple"

    def __init__(self, win):
        super().__init__(win, "apc_intro_decouple")
        self.dtype = w.combo(["static", "dyn"], "dyn", labels=[T("dec_static"), T("dec_dyn")])
        self.amp_a, self.amp_b = w.spin(5.0, -100, 100, 3), w.spin(5.0, -100, 100, 3)
        self.dtype.currentIndexChanged.connect(self._changed)
        for sp in (self.amp_a, self.amp_b):
            sp.valueChanged.connect(self._changed)
        b_reset = self.reset_button((self.amp_a, self.amp_b), lambda: (5.0, 5.0), self._changed)
        self.left.addWidget(w.group(T("dec_type"), w.form([(T("dec_type"), self.dtype), ("SP A [%]", self.amp_a),
                                                           ("SP B [%]", self.amp_b), ("", b_reset)])))
        self.rga = w.note("")
        self.left.addWidget(self.rga)
        self.prm = w.table([], [], stretch=False)
        self.prm.setMinimumHeight(110)
        self.left.addWidget(w.group(T("dec_params"), w.form([("", self.prm)])))
        self.left.addStretch(1)
        self.plots = self.chart(3, ("PV A", "PV B", "MV"), (0.36, 0.36, 0.28))
        self.kpi = self.table(110)

    def update_pair(self, a, b):
        dz = adec.design(a, b)
        if dz["xab"] is None and dz["xba"] is None:
            self.rga.setText("⚠️ " + T("dec_need_cross", a=a["name"], b=b["name"], mva=a["c_mv"], mvb=b["c_mv"]))
            for pl in self.plots:
                pl.clear()
            return
        lam = dz["lam"]
        self.rga.setText(f"**RGA λ₁₁ = {lam:.2f}**  \n" + T(rga_advice(lam), a=a["name"], b=b["name"], mva=a["c_mv"],
                                                             mvb=b["c_mv"]))
        ca = {k: v for k, v in a["ctrl"].items() if k not in ("FF", "FF_LL")}
        cb = {k: v for k, v in b["ctrl"].items() if k not in ("FF", "FF_LL")}
        runs = adec.simulate(dz, ca, cb, self.amp_a.value(), self.amp_b.value())
        tt, o_ref = runs["none"]
        _, o = runs[self.dtype.currentData()]

        def ea(x, r):
            return r[0] + x * (r[1] - r[0]) / 100
        for pl in self.plots:
            pl.clear()
        w.line(self.plots[0], tt, ea(o["SP_A"], a["pv_rng"]), "SP", w.C_SP, 1.3, dash=True)
        w.line(self.plots[0], tt, ea(o_ref["PV_A"], a["pv_rng"]), T("dec_without"), "#9aa5b1", 1.3, dash=True)
        w.line(self.plots[0], tt, ea(o["PV_A"], a["pv_rng"]), a["name"], w.C_PV, 2.0)
        w.line(self.plots[1], tt, ea(o["SP_B"], b["pv_rng"]), "SP", w.C_SP, 1.3, dash=True)
        w.line(self.plots[1], tt, ea(o_ref["PV_B"], b["pv_rng"]), T("dec_without"), "#9aa5b1", 1.3, dash=True)
        w.line(self.plots[1], tt, ea(o["PV_B"], b["pv_rng"]), b["name"], "#7c3aed", 2.0)
        w.line(self.plots[2], tt, ea(o["MV_A"], a["mv_rng"]), f"MV {a['name']}", w.C_MV, 1.6)
        w.line(self.plots[2], tt, ea(o["MV_B"], b["mv_rng"]), f"MV {b['name']}", w.C_SET2, 1.6)
        w.fill(self.kpi, [T("dec_variant"), f"IAE {a['name']}", f"IAE {b['name']}"],
               [[T("dec_" + v), ia, ib] for v, ia, ib in adec.iae_table(runs, a, b)])
        w.fill(self.prm, [T("dec_path"), T("dec_gain_pct"), T("dec_gain_eng"), "Lead [s]", "Lag [s]", T("ff_delay")],
               [[f"{src} → MV {dst}", g, ge, ld, lg, dl] for src, dst, g, ge, ld, lg, dl in adec.params(dz, a, b)])
        self.prm.resizeColumnsToContents()
