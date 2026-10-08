"""APC › Smithův prediktor: metoda a τc regulátoru, citlivost na chybu modelu, obecné hodnoty prediktoru, z čeho
výpočet vychází a hodnoty pro šablonu SmithPredictorControl."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from ....app.apc import smith as asm
from ....app.apc.common import tchar
from ....core import MODELS
from ....i18n import T
from ... import widgets as w
from .common import Panel


def tc_key(method, code, p):
    """Klíč τc v nastavení – u SIMC stejný jako dřív (projekty), u ostatních metod zvlášť."""
    return f"apc_sm_tc|{code}|{p[-1]:.4g}" if method == "SIMC" else f"apc_sm_tc|{method}|{code}|{p[-1]:.4g}"


class SmithPanel(Panel):
    _impl = None

    def impl(self):
        return self._impl

    def __init__(self, win):
        super().__init__(win, "apc_intro_smith")
        self._opt = {}                                   # výsledky robustní optimalizace podle zadání
        self.ctype = w.combo(["PI", "PID"])
        self.method = w.combo(list(asm.METHODS), labels=[T("sm_m_" + m) for m in asm.METHODS])
        w.tip(self.method, "h_sm_method")
        self.tc = w.spin(1.0, 0.001, 1e9, 4)
        w.tip(self.tc, "h_sm_tc")
        self.mg, self.mti, self.mtd = w.spin(1.0, -1e6, 1e6, 4), w.spin(100.0, 0.0, 1e9, 2), w.spin(0.0, 0.0, 1e9, 2)
        self.ek, self.et, self.eth = (w.spin(0.0, -90, 200, 1, 5, "%") for _ in range(3))
        for c in (self.ctype, self.method):
            c.currentIndexChanged.connect(self._changed)
        for sp in (self.tc, self.mg, self.mti, self.mtd, self.ek, self.et, self.eth):
            sp.valueChanged.connect(self._changed)
        self.b_tc = self.reset_button((self.tc,), lambda: (asm.tc_default(self.s.model[1], float(self.s.get("samp")),
                                                                           self.method.currentData()),), self._changed)
        self.b_man = self.reset_button((self.mg, self.mti, self.mtd),
                                       lambda: tuple(float(self.s.get(f"set2_{k}", d))
                                                     for k, d in (("gain", 1.0), ("ti", 100.0), ("td", 0.0))),
                                       self._changed)
        self.b_err = self.reset_button((self.ek, self.et, self.eth), lambda: (0.0, 0.0, 0.0), self._changed)
        self.frm = w.form([(T("sm_method"), self.method), (T("ctrl_type"), self.ctype), (T("sm_tc"), self.tc),
                           ("", self.b_tc), ("Gain", self.mg), ("TI [s]", self.mti), ("TD [s]", self.mtd),
                           ("", self.b_man), (T("sm_err_k"), self.ek), (T("sm_err_t"), self.et),
                           (T("sm_err_th"), self.eth), ("", self.b_err)])
        self.left.addWidget(w.group(T("apc_smith"), self.frm))
        self.ratio = w.note("")
        self.left.addWidget(self.ratio)
        self.basis = w.note("")
        self.left.addWidget(self.basis)
        self.gen = w.table([], [], stretch=False)
        self.gen.setMinimumHeight(260)
        self.left.addWidget(w.group(T("sm_gen_title"), w.form([("", self.gen)])))
        self.left.addWidget(w.note(T("sm_gen_help")))
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
        m = s.get("apc_sm_method", asm.DEFAULT_METHOD)
        self.method.setCurrentIndex(max(self.method.findData(m), 0))
        self.ctype.setCurrentIndex(self.ctype.findData(s.get("apc_sm_ct", "PI")))
        self._load_tc(code, p)
        man = s.get("apc_sm_man") or [s.get("set2_gain", 1.0), s.get("set2_ti", 100.0), s.get("set2_td", 0.0)]
        for sp, v in zip((self.mg, self.mti, self.mtd), man):
            sp.setValue(float(v))
        self._busy = False
        self._changed()

    def _load_tc(self, code, p):
        m = self.method.currentData()
        self.tc.setValue(float(self.s.get(tc_key(m, code, p), asm.tc_default(p, float(self.s.get("samp")), m))))

    def _rows_visible(self, method, ctype):
        f = self.frm
        f.setRowVisible(self.tc, method in ("SIMC", "Lambda"))
        f.setRowVisible(self.b_tc, method in ("SIMC", "Lambda"))
        for sp in (self.mg, self.mti, self.b_man):
            f.setRowVisible(sp, method == "manual")
        f.setRowVisible(self.mtd, method == "manual" and ctype == "PID")

    def controller(self, code, p, method, ctype, samp):
        s = self.s
        if method != "OPT":
            return asm.controller(code, p, method, ctype, self.tc.value(), samp, s.base_ctrl(),
                                  (self.mg.value(), self.mti.value(), self.mtd.value()))
        key = (code, tuple(p), ctype, samp, tuple(sorted(s.base_ctrl().items())))
        if key not in self._opt:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                self._opt[key] = asm.controller(code, p, "OPT", ctype, None, samp, s.base_ctrl())
            finally:
                QApplication.restoreOverrideCursor()
        return self._opt[key]

    def _changed(self, *_):
        s = self.s
        if self._busy or s.model is None:
            return
        code, p, _ = s.model
        method, ctype = self.method.currentData(), self.ctype.currentData()
        if method != s.get("apc_sm_method", asm.DEFAULT_METHOD):       # jiná metoda → její τc / λ
            s.settings["apc_sm_method"] = method
            self._busy = True
            self._load_tc(code, p)
            self._busy = False
        s.settings[tc_key(method, code, p)] = self.tc.value()
        s.settings["apc_sm_ct"] = ctype
        s.settings["apc_sm_man"] = [self.mg.value(), self.mti.value(), self.mtd.value()]
        self._rows_visible(method, ctype)
        samp = float(s.get("samp"))
        ratio = p[-1] / max(tchar((code, p)), 1e-9)
        self.ratio.setText(T("sm_ratio", r=f"{ratio:.2f}") + ("  \n⚠️ " + T("sm_integ") if MODELS[code]["integ"] else ""))
        r = self.controller(code, p, method, ctype, samp)
        plant = asm.plant_error(p, self.ek.value(), self.et.value(), self.eth.value())
        sim = asm.simulate(code, p, plant, s.base_ctrl(), s.set_ctrl(2), ctype, self.tc.value(), samp, r=r)
        for pl in self.plots:
            pl.clear()
        w.line(self.plots[0], sim["t"], s.EP(sim["sp"]), "SP", w.C_SP, 1.3, dash=True)
        tb, PVb, MVb = sim["pid"]
        tt, o = sim["smith"]
        w.line(self.plots[0], tb, s.EP(PVb), T("sm_pid"), w.C_SET1, 1.6, dash=True)
        w.line(self.plots[0], tt, s.EP(o["PV"]), T("sm_smith"), w.C_SET2, 2.2)
        w.line(self.plots[1], tb, s.EM(MVb), T("sm_pid"), w.C_SET1, 1.4, dash=True)
        w.line(self.plots[1], tt, s.EM(o["MV"]), T("sm_smith"), w.C_SET2, 1.8)
        f = s.PR / 100
        w.fill(self.kpi, [T("setting"), T("iae_sp"), T("iae_load")],
               [[T("sm_" + k), sim["iae"][k][0] * f, sim["iae"][k][1] * f] for k in ("pid", "smith")])
        if MODELS[code]["integ"]:
            for t in (self.vals, self.gen):
                w.fill(t, [""], [])
            self.basis.setText("")
            return
        _, pv_id, mv_id, _ = s.segment()
        pv_op, mv_op = asm.operating_point(pv_id, mv_id)
        u_pv, u_mv = s.get("u_pv") or "PV", s.get("u_mv") or "MV"
        self.basis.setText(asm.basis_text(code, p, s, pv_op, mv_op, samp, u_pv, u_mv))
        w.fill(self.gen, [T("sm_gen_par"), T("sm_apl_value"), T("sm_apl_unit")],
               [[T(k), v, u] for k, v, u in asm.general_rows(code, p, s, pv_op, mv_op, r, self.tc.value(), method, ctype,
                                                             u_pv, u_mv)])
        self.gen.resizeColumnsToContents()
        v, r_, rows = asm.values(code, p, s, pv_op, mv_op, ctype, self.tc.value(), samp, u_pv, u_mv, r=r)
        self._impl = T("g_impl_smith", k=f"{v['k']:.4g}", u=f"{u_pv}/{u_mv}", t=f"{v['lag']:.4g}",
                       th=f"{v['theta']:.4g}", pv0=f"{v['pv0']:.4g}", g=f"{r_['Kc']:.4g}", ti=f"{r_['Ti']:.4g}")
        w.fill(self.vals, [T("sm_apl_block"), T("sm_apl_input"), T("sm_apl_value"), T("sm_apl_unit")],
               [list(r_) for r_ in rows])
        self.vals.resizeColumnsToContents()
