"""
Záložka Ladění: blok PIDConL (rozsahy NormPV / NormMV, SampleTime, DiffGain, PropFacSP, DiffToFbk, limity …),
metoda a návrh (optimalizace na pozadí), sady 1 a 2, robustnost a simulace scénáře.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSplitter,
                               QVBoxLayout, QWidget)

from ...core import default_tc
from ...i18n import T
from .. import widgets as w

CRITS = ["MIGO", "IAE", "ISE", "ITAE", "OVS"]
TARGETS = ["dist", "sp", "both"]


class TuningTab(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win, self.s = win, win.state
        lay = QHBoxLayout(self)
        split = QSplitter(Qt.Horizontal)
        lay.addWidget(split)
        left = QWidget()
        ll = QVBoxLayout(left)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(left)
        scroll.setMinimumWidth(500)
        split.addWidget(scroll)

        # ---- blok PIDConL
        self.f = {}
        rows = [("pv_lo", "NormPV Low"), ("pv_hi", "NormPV High"), ("mv_lo", "NormMV Low"), ("mv_hi", "NormMV High"),
                ("samp", T("sampletime")), ("diffgain", "DiffGain"), ("propfac", "PropFacSP"), ("db", T("deadband")),
                ("mvl_lo", "MV_LoLim"), ("mvl_hi", "MV_HiLim"), ("pvfilt", T("pvfilt")),
                ("mvrate", T("mvrate", u="MV"))]
        frm = []
        for k, lab in rows:
            sp = w.spin(0.0, -1e12, 1e12, 6)
            if k == "propfac":
                sp.setRange(0.0, 1.0)
                sp.setSingleStep(0.1)
            if k in ("samp", "diffgain"):
                sp.setMinimum(0.001)
            self.f[k] = sp
            frm.append((lab, sp))
            sp.valueChanged.connect(self._block_changed)
        self.dfb = QCheckBox("DiffToFbk (" + T("dfb") + ")")
        self.dfb.toggled.connect(self._block_changed)
        frm.append(("", self.dfb))
        ll.addWidget(w.group("PIDConL", w.form(frm)))

        # ---- metoda a návrh
        self.method = w.combo([])
        self.ctype = w.combo(["PI", "PID"])
        self.tc = w.spin(1.0, 0.0, 1e9, 4)
        self.crit = w.combo(CRITS, labels=[T("crit_" + c) for c in CRITS])
        self.target = w.combo(TARGETS, labels=[T("tgt_" + c) for c in TARGETS])
        self.sug = w.note("")
        self.b_s1, self.b_s2 = QPushButton(T("write_s1")), QPushButton(T("write_s2"))
        self.b_s1.clicked.connect(lambda: self._write(1))
        self.b_s2.clicked.connect(lambda: self._write(2))
        self.desc = w.note("")
        mg = w.form([(T("method"), self.method), (T("ctrl_type"), self.ctype), (T("tc"), self.tc),
                     (T("opt_crit"), self.crit), (T("opt_target"), self.target)])
        box = QVBoxLayout()
        box.addLayout(mg)
        box.addWidget(self.desc)
        box.addWidget(self.sug)
        box.addLayout(w.hbox(self.b_s1, self.b_s2))
        ll.addWidget(w.group(T("calc_title"), box))
        for c in (self.method, self.ctype, self.crit, self.target):
            c.currentIndexChanged.connect(self._method_changed)
        self.tc.valueChanged.connect(self._compute)

        # ---- sady
        sg = QGridLayout()
        self.sets = {}
        for n in (1, 2):
            sg.addWidget(QLabel(f"**{T('set_' + str(n))}**".replace("**", "")), 0, n)
            for i, k in enumerate(("gain", "ti", "td")):
                sp = w.spin(0.0, -1e12, 1e12, 6)
                sp.valueChanged.connect(self._sets_changed)
                self.sets[(n, k)] = sp
                sg.addWidget(sp, i + 1, n)
        for i, lab in enumerate(("Gain", "TI [s]", "TD [s]")):
            sg.addWidget(QLabel(lab), i + 1, 0)
        ll.addWidget(w.group(T("sets_title"), sg))
        self.rob = w.table(["", T("set_1"), T("set_2")], [])
        self.rob.setMinimumHeight(150)
        ll.addWidget(w.group(T("robust_title"), w.form([("", self.rob)])))
        ll.addStretch(1)

        # ---- scénář
        right = QWidget()
        rl = QVBoxLayout(right)
        self.sp0, self.sp1 = w.spin(0.0, -1e12, 1e12, 4), w.spin(0.0, -1e12, 1e12, 4)
        self.auto_len = QCheckBox(T("dk_sim_auto"))
        self.auto_len.setChecked(True)
        self.t_end = w.spin(1000.0, 1.0, 1e9, 1)
        b_sim = QPushButton(T("dk_run_sim"))
        b_sim.clicked.connect(self._simulate)
        self.len_src = QLabel("")
        rl.addLayout(w.hbox(QLabel(T("sim_sp_from", u="PV")), self.sp0, QLabel(T("sim_sp_to", u="PV")), self.sp1,
                            QLabel(T("sim_len")), self.t_end, self.auto_len, b_sim))
        rl.addWidget(self.len_src)
        self.chart, self.plots = w.stack(2, ["PV", "MV"], T("time_s"), heights=(0.62, 0.38))
        rl.addWidget(self.chart, 1)
        self.kpi = w.table([], [])
        self.kpi.setMaximumHeight(110)
        rl.addWidget(self.kpi)
        rl.addWidget(w.note(T("dk_sp_step")))
        split.addWidget(right)
        split.setSizes([520, 880])
        for sp in (self.sp0, self.sp1, self.t_end):
            sp.valueChanged.connect(self._scenario_changed)
        self.auto_len.toggled.connect(self._scenario_changed)
        self._busy = False
        self._last = None

    # ---- obnova
    def refresh(self):
        s = self.s
        if not s.has_data:
            return
        self._busy = True
        try:
            for k, sp in self.f.items():
                v = s.get(k)
                if v is None and k in ("mvl_lo", "mvl_hi"):
                    v = s.mv_lo if k == "mvl_lo" else s.mv_hi
                sp.setValue(float(v))
            self.dfb.setChecked(bool(s.get("dfb")))
            for (n, k), sp in self.sets.items():
                sp.setValue(float(s.get(f"set{n}_{k}")))
            if s.model is not None:
                ms = s.methods()
                self.method.clear()
                for m in ms:
                    self.method.addItem(T("m_" + m), m)
                cur = s.get(f"method|{s.model[0]}", "SIMC")
                self.method.setCurrentIndex(max(self.method.findData(cur), 0))
                self.ctype.setCurrentIndex(self.ctype.findData(s.get("ctype")))
                self.crit.setCurrentIndex(max(self.crit.findData(s.get("opt_crit")), 0))
                self.target.setCurrentIndex(max(self.target.findData(s.get("opt_target")), 0))
                sp0, sp1 = s.sp_from_to()
                self.sp0.setValue(sp0)
                self.sp1.setValue(sp1)
                self._tc_default()
        finally:
            self._busy = False
        self._enable()
        if s.model is None:
            self.sug.setText(T("need_model"))
            for p in self.plots:
                p.clear()
            return
        self._compute()
        self._robustness()
        self._simulate()

    def _enable(self):
        m = self.method.currentData()
        self.tc.setEnabled(m in ("SIMC", "iSIMC", "Lambda"))
        self.crit.setEnabled(m == "OPT")
        self.target.setEnabled(m == "OPT" and self.crit.currentData() != "MIGO")
        self.desc.setText(T("mdesc_" + m) if m else "")

    def _tc_default(self):
        s, m = self.s, self.method.currentData()
        if s.model is None or m not in ("SIMC", "iSIMC", "Lambda"):
            return
        code, p, _ = s.model
        tc0 = default_tc(code, p, float(s.get("samp")), m, self.ctype.currentData(), float(s.get("diffgain")))
        self.tc.setValue(float(s.get(f"tc|{code}|{m}|{self.ctype.currentData()}", tc0)))

    # ---- návrh
    def _method_changed(self):
        if self._busy:
            return
        s = self.s
        s.set(**{f"method|{s.model[0]}": self.method.currentData(), "ctype": self.ctype.currentData(),
                 "opt_crit": self.crit.currentData(), "opt_target": self.target.currentData()})
        self._busy = True
        self._tc_default()
        self._busy = False
        self._enable()
        self._compute()

    def _compute(self):
        if self._busy or self.s.model is None:
            return
        s, m = self.s, self.method.currentData()
        tc = self.tc.value() if m in ("SIMC", "iSIMC", "Lambda") else None
        if tc is not None:
            s.settings[f"tc|{s.model[0]}|{m}|{self.ctype.currentData()}"] = tc
        if m == "OPT":
            self.sug.setText(T("dk_optimizing"))
            self.b_s1.setEnabled(False)
            self.b_s2.setEnabled(False)
            w.run_task(lambda _p: s.suggest(m, tc), self._show_sug, lambda e: self.win.error(T(e)))
        else:
            try:
                self._show_sug(s.suggest(m, tc))
            except Exception as ex:
                self.win.error(T(str(ex)))

    def _show_sug(self, sug):
        self._last = sug
        self.b_s1.setEnabled(True)
        self.b_s2.setEnabled(True)
        notes = "  \n".join("💡 " + T(k, **a) for k, a in sug.get("notes", []))
        self.sug.setText(f"**{T('dk_suggest')}:** Gain = {sug['Kc']:.4g} · TI = {sug['Ti']:.4g} s · "
                         f"TD = {sug['Td']:.4g} s" + ("  \n" + notes if notes else ""))

    def _write(self, n):
        if self._last:
            self.s.write_set(n, self._last)
            self.win.refresh()

    # ---- blok a sady
    def _block_changed(self, *_):
        if self._busy:
            return
        s = self.s
        s.set(**{k: sp.value() for k, sp in self.f.items()}, dfb=self.dfb.isChecked())
        if s.rescale_if_needed():
            self.win.status(T("norm_rescaled"))
        self.win.refresh()

    def _sets_changed(self, *_):
        if self._busy:
            return
        self.s.set(**{f"set{n}_{k}": sp.value() for (n, k), sp in self.sets.items()})
        self._robustness()
        self._simulate()

    def _robustness(self):
        s = self.s
        if s.model is None:
            return
        r = {n: s.set_metrics(n) for n in (1, 2)}
        mr = s.MR / 100
        rows = [[T("ms"), r[1]["Ms"], r[2]["Ms"]], [T("gm"), r[1]["GM"], r[2]["GM"]], [T("pm"), r[1]["PM"], r[2]["PM"]],
                [T("noise_col", u=s.get("u_mv") or "MV"), r[1]["noise"] * mr, r[2]["noise"] * mr],
                ["", *(("" if r[n]["stable"] else T("dk_unstable")) for n in (1, 2))]]
        w.fill(self.rob, ["", T("set_1"), T("set_2")], rows)

    # ---- scénář
    def _scenario_changed(self, *_):
        if self._busy:
            return
        self.s.sim_sp = (self.sp0.value(), self.sp1.value())
        self._simulate()

    def _simulate(self):
        s = self.s
        if s.model is None:
            return
        self.t_end.setEnabled(not self.auto_len.isChecked())
        try:
            r = s.simulate(None if self.auto_len.isChecked() else self.t_end.value())
        except Exception as ex:
            self.win.error(T(str(ex)))
            return
        self._busy = True
        self.t_end.setValue(r["T_end"])
        self._busy = False
        self.len_src.setText(T("sim_len_src_" + r["src"]) if r["src"] != "manual" else "")
        for p in self.plots:
            p.clear()
        w.line(self.plots[0], r["t"], s.EP(r["sp"]), "SP", w.C_SP, 1.3, dash=True)
        rows = []
        for n, col in ((1, w.C_SET1), (2, w.C_SET2)):
            o = r["runs"][n]
            k = r["kpis"][n]
            if k is None:
                rows.append([T(f"set_{n}"), T("dk_unstable"), "", "", "", ""])
                continue
            w.line(self.plots[0], o["t"], s.EP(o["PV"]), T(f"set_{n}"), col, 2.0, dash=n == 1)
            w.line(self.plots[1], o["t"], s.EM(o["MV"]), f"MV {T(f'set_{n}')}", col, 1.6, dash=n == 1)
            rows.append([T(f"set_{n}"), k["iae"], k["maxdev"], k["mv_range"], k["mv_travel"], k["reversals"]])
        u_pv, u_mv = s.get("u_pv") or "PV", s.get("u_mv") or "MV"
        w.fill(self.kpi, [T("setting"), "IAE [%·s]", T("kpi_maxdev", u=u_pv), T("kpi_mvrange", u=u_mv),
                          T("kpi_mvtravel", u=u_mv), T("kpi_rev")], rows)
