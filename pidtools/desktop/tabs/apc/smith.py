"""APC › Smithův prediktor: τc, typ regulátoru, citlivost na chybu modelu, hodnoty pro šablonu SmithPredictorControl."""
from ....app.apc import smith as asm
from ....app.apc.common import tchar
from ....core import MODELS
from ....i18n import T
from ... import widgets as w
from .common import Panel


class SmithPanel(Panel):
    def __init__(self, win):
        super().__init__(win, "apc_intro_smith")
        self.ctype = w.combo(["PI", "PID"])
        self.tc = w.spin(1.0, 0.001, 1e9, 4)
        self.ek, self.et, self.eth = (w.spin(0.0, -90, 200, 1, 5, "%") for _ in range(3))
        for c in (self.ctype,):
            c.currentIndexChanged.connect(self._changed)
        for sp in (self.tc, self.ek, self.et, self.eth):
            sp.valueChanged.connect(self._changed)
        self.left.addWidget(w.group(T("apc_smith"), w.form([
            (T("ctrl_type"), self.ctype), (T("sm_tc"), self.tc), (T("sm_err_k"), self.ek), (T("sm_err_t"), self.et),
            (T("sm_err_th"), self.eth)])))
        self.ratio = w.note("")
        self.left.addWidget(self.ratio)
        self.vals = w.table([], [], stretch=False)
        self.vals.setMinimumHeight(220)
        self.left.addWidget(w.group(T("sm_apl_title"), w.form([("", self.vals)])))
        self.left.addWidget(w.note(T("sm_apl_note")))
        self.left.addStretch(1)
        self.plots = self.chart()
        self.kpi = self.table(100)

    def refresh(self):
        s = self.s
        if s.model is None:
            return
        code, p, _ = s.model
        self._busy = True
        key = f"apc_sm_tc|{code}|{p[-1]:.4g}"
        self.tc.setValue(float(s.get(key, asm.tc0(p, float(s.get("samp"))))))
        self.ctype.setCurrentIndex(self.ctype.findData(s.get("apc_sm_ct", "PI")))
        self._busy = False
        self._changed()

    def _changed(self, *_):
        s = self.s
        if self._busy or s.model is None:
            return
        code, p, _ = s.model
        s.settings[f"apc_sm_tc|{code}|{p[-1]:.4g}"] = self.tc.value()
        s.settings["apc_sm_ct"] = self.ctype.currentData()
        ratio = p[-1] / max(tchar((code, p)), 1e-9)
        self.ratio.setText(T("sm_ratio", r=f"{ratio:.2f}") + ("  \n⚠️ " + T("sm_integ") if MODELS[code]["integ"] else ""))
        plant = asm.plant_error(p, self.ek.value(), self.et.value(), self.eth.value())
        r = asm.simulate(code, p, plant, s.base_ctrl(), s.set_ctrl(2), self.ctype.currentData(), self.tc.value(),
                         float(s.get("samp")))
        for pl in self.plots:
            pl.clear()
        w.line(self.plots[0], r["t"], s.EP(r["sp"]), "SP", w.C_SP, 1.3, dash=True)
        tb, PVb, MVb = r["pid"]
        tt, o = r["smith"]
        w.line(self.plots[0], tb, s.EP(PVb), T("sm_pid"), w.C_SET1, 1.6, dash=True)
        w.line(self.plots[0], tt, s.EP(o["PV"]), T("sm_smith"), w.C_SET2, 2.2)
        w.line(self.plots[1], tb, s.EM(MVb), T("sm_pid"), w.C_SET1, 1.4, dash=True)
        w.line(self.plots[1], tt, s.EM(o["MV"]), T("sm_smith"), w.C_SET2, 1.8)
        f = s.PR / 100
        w.fill(self.kpi, [T("setting"), T("iae_sp"), T("iae_load")],
               [[T("sm_" + k), r["iae"][k][0] * f, r["iae"][k][1] * f] for k in ("pid", "smith")])
        if MODELS[code]["integ"]:
            w.fill(self.vals, [""], [])
            return
        _, pv_id, mv_id, _ = s.segment()
        pv_op, mv_op = asm.operating_point(pv_id, mv_id)
        _, _, rows = asm.values(code, p, s, pv_op, mv_op, self.ctype.currentData(), self.tc.value(),
                                float(s.get("samp")), s.get("u_pv") or "PV", s.get("u_mv") or "MV")
        w.fill(self.vals, [T("sm_apl_block"), T("sm_apl_input"), T("sm_apl_value"), T("sm_apl_unit")],
               [list(r_) for r_ in rows])
        self.vals.resizeColumnsToContents()
