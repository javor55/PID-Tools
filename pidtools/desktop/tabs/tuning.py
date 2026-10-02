"""
Záložka Ladění: blok PIDConL (rozsahy NormPV / NormMV, SampleTime, DiffGain, PropFacSP, DiffToFbk, limity …),
metoda a návrh (optimalizace na pozadí), sady 1 a 2, robustnost a simulace scénáře.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QGridLayout, QHBoxLayout, QLabel, QPushButton,
                               QScrollArea, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

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
        self.robust = QCheckBox(T("opt_robust"))
        self.robust.toggled.connect(self._robust_toggled)
        self.b_cmp = QPushButton(T("cmp_title"))
        self.b_cmp.clicked.connect(self._compare)
        box.addWidget(self.robust)
        box.addLayout(w.hbox(self.b_s1, self.b_s2, self.b_cmp))
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
        b_ev = QPushButton(T("dk_scen_edit"))
        b_ev.clicked.connect(self._edit_scenario)
        self.len_src = QLabel("")
        rl.addLayout(w.hbox(QLabel(T("sim_sp_from", u="PV")), self.sp0, QLabel(T("sim_sp_to", u="PV")), self.sp1,
                            QLabel(T("sim_len")), self.t_end, self.auto_len, b_sim, b_ev))
        rl.addWidget(self.len_src)
        self.chart, self.plots = w.stack(2, ["PV", "MV"], T("time_s"), heights=(0.62, 0.38))
        rl.addWidget(self.chart, 1)
        self.kpi = w.table([], [])
        self.kpi.setMaximumHeight(110)
        rl.addWidget(self.kpi)
        self.scen_note = w.note(T("dk_sp_step"))
        rl.addWidget(self.scen_note)
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
            self.robust.setChecked(bool(s.get("opt_robust")))
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

    def _robust_toggled(self, on):
        if not self._busy:
            self.s.set(opt_robust=on)
            self._compute()

    def _compare(self):
        s = self.s
        if s.model is None:
            return
        self.b_cmp.setEnabled(False)
        self.win.status(T("dk_optimizing"))

        def done(rows):
            self.b_cmp.setEnabled(True)
            self.win.status("")
            CompareDialog(self, rows).exec()
        w.run_task(lambda _p: s.compare_methods(), done, lambda e: (self.b_cmp.setEnabled(True), self.win.error(T(e))))

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
        if r[1]["Ms_worst"] is not None:
            rows.insert(1, [T("ms_worst"), r[1]["Ms_worst"], r[2]["Ms_worst"]])
        w.fill(self.rob, ["", T("set_1"), T("set_2")], rows)

    # ---- scénář
    def _edit_scenario(self):
        s = self.s
        if s.model is None:
            return
        T_end = self.t_end.value()
        dlg = ScenarioDialog(self, s, s.scen_rows(T_end), T_end)
        if dlg.exec() == QDialog.Accepted:
            s.set_scen_rows(dlg.rows(), T_end)
            dlg.apply_plant()
            self._simulate()

    def _scenario_changed(self, *_):
        if self._busy:
            return
        s = self.s
        s.sim_sp = (self.sp0.value(), self.sp1.value())
        rows = s.settings.get(s.scen_key)
        if rows:                       # vlastní scénář: „z → na“ přepíše první skok SP (jako ve webu)
            from ...app.scenario import set_sp_step
            rows, hit = set_sp_step(rows, s.sim_sp[1] - s.sim_sp[0])
            if hit:
                s.settings[s.scen_key] = rows
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
        self.scen_note.setText(T("dk_scen_custom") if s.settings.get(s.scen_key) else T("dk_sp_step"))
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


class CompareDialog(QDialog):
    """Srovnání všech metod (PI i PID): Gain, TI, TD, Ms, IAE, překmit, šum MV; vybraný řádek do sady 1 nebo 2."""

    def __init__(self, tab, rows):
        super().__init__(tab)
        self.tab, self.rows = tab, rows
        s = tab.s
        self.setWindowTitle(T("cmp_title"))
        self.resize(1100, 520)
        lay = QVBoxLayout(self)
        u_mv = s.get("u_mv") or "MV"
        mr = s.MR / 100
        self.table = w.table(
            [T("col_method"), T("ctrl_type"), "Gain", "TI [s]", "TD [s]", "Ms", T("iae_load"), T("iae_sp"),
             T("ovs_col"), T("noise_col", u=u_mv)],
            [[T("m_" + q["method"]) + (f" · {T('crit_' + q['crit'])}" if q["crit"] else ""), q["ctype"], q["Kc"], q["Ti"],
              q["Td"], q["Ms"], q["iae_load"], q["iae_sp"], q["ovs"], q["noise"] * mr if q["noise"] is not None else None]
             for q in rows])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        lay.addWidget(self.table)
        lay.addWidget(w.note(T("cmp_help")))
        b1, b2 = QPushButton(T("write_sel_s1")), QPushButton(T("write_sel_s2"))
        b1.clicked.connect(lambda: self._write(1))
        b2.clicked.connect(lambda: self._write(2))
        lay.addLayout(w.hbox(b1, b2))

    def _write(self, n):
        i = self.table.currentRow()
        if i < 0:
            return
        q = self.rows[i]
        self.tab.s.write_set(n, dict(Kc=q["Kc"], Ti=q["Ti"], Td=q["Td"]))
        self.tab.win.refresh()
        self.accept()


class ScenarioDialog(QDialog):
    """Události scénáře (cíl, typ, amplituda, začátek, konec, perioda, τ) a proces a ventil v simulaci."""

    COLS = ("on", "target", "type", "amp", "start", "end", "period", "tau")

    def __init__(self, tab, state, rows, T_end):
        from ...app import scenario as scn
        super().__init__(tab)
        self.s, self.scn = state, scn
        self.setWindowTitle(T("scen_title"))
        self.resize(980, 520)
        lay = QVBoxLayout(self)
        self.targets = scn.targets(len(state.c_d))
        self.tab = QTableWidget(0, len(self.COLS))
        self.tab.setHorizontalHeaderLabels([T("sc_" + c) for c in self.COLS])
        lay.addWidget(self.tab, 1)
        lay.addWidget(w.note(T("scen_help")))
        b_add, b_del, b_def = QPushButton("+"), QPushButton("−"), QPushButton(T("dk_scen_default"))
        b_add.clicked.connect(lambda: self._add(scn.row("SP", "step", 0.0, 0.0)))
        b_del.clicked.connect(lambda: self.tab.removeRow(self.tab.currentRow()))
        b_def.clicked.connect(self._default)
        lay.addLayout(w.hbox(b_add, b_del, b_def))
        u_pv, u_mv = state.get("u_pv") or "PV", state.get("u_mv") or "MV"
        st0 = state.plant()["Stic"] * state.MR / 100
        self.stic = w.spin(st0, 0.0, 1e12, 4)
        self.slip = w.spin(float(state.get("sim_J", 100.0)), 0.0, 100.0, 1)
        self.noise = w.spin(float(state.get("sim_noise", 0.0)), 0.0, 1e12, 4)
        lay.addWidget(w.group(T("plant_title"), w.form([(T("sim_stic", u=u_mv), self.stic), (T("sim_slip"), self.slip),
                                                        (T("sim_noise", u=u_pv), self.noise)])))
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.T_end = T_end
        for r in rows:
            self._add(r)

    def _tlabel(self, c):
        return T("tg_" + c) if c[0] != "M" else f"{T('tg_M')}: {self.s.c_d[int(c[1:])]}"

    def _add(self, r):
        i = self.tab.rowCount()
        self.tab.insertRow(i)
        it = QTableWidgetItem()
        it.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
        it.setCheckState(Qt.Checked if r[0] else Qt.Unchecked)
        self.tab.setItem(i, 0, it)
        self.tab.setCellWidget(i, 1, w.combo(self.targets, r[1], labels=[self._tlabel(c) for c in self.targets]))
        self.tab.setCellWidget(i, 2, w.combo(list(self.scn.TYPES), r[2], labels=[T("ty_" + c) for c in self.scn.TYPES]))
        for j in range(3, 8):
            self.tab.setItem(i, j, QTableWidgetItem("" if r[j] is None else f"{r[j]:.6g}"))

    def _default(self):
        self.tab.setRowCount(0)
        sp0, sp1 = self.s.sp_from_to()
        for r in self.scn.default_rows(sp1 - sp0, self.s.MR, len(self.s.c_d), self.T_end):
            self._add(r)

    def rows(self):
        out = []
        for i in range(self.tab.rowCount()):
            vals = []
            for j in range(3, 8):
                it = self.tab.item(i, j)
                try:
                    vals.append(float(it.text().replace(",", ".")) if it and it.text().strip() else None)
                except ValueError:
                    vals.append(None)
            out.append([self.tab.item(i, 0).checkState() == Qt.Checked, self.tab.cellWidget(i, 1).currentData(),
                        self.tab.cellWidget(i, 2).currentData()] + vals)
        return out

    def apply_plant(self):
        self.s.settings[self.s.stic_key] = self.stic.value()
        self.s.set(sim_J=self.slip.value(), sim_noise=self.noise.value())
