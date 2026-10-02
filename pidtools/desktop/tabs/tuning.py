"""
Záložka Ladění: vlevo scénář v grafu (sady 1, 2 a návrh) s ukazateli, vpravo postup – 1 scénář (výchozí skok SP),
2 návrh parametrů, 3 sady a robustnost; ověření robustnosti, doporučení D složky a blok PIDConL ve sbalitelných
sekcích. Počítá se až tlačítkem Vypočítat (F5); po změně nastavení se výsledek označí jako neaktuální.
"""
import time

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QGridLayout, QLabel, QPushButton, QTableWidget,
                               QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from ...core import default_tc
from ...i18n import T
from .. import widgets as w
from ..layout import Workspace, caption
from .frequency import FrequencyView

CRITS = ["MIGO", "IAE", "ISE", "ITAE", "OVS"]
TARGETS = ["scen", "dist", "sp", "both"]
C_SUG = "#9333ea"


class TuningTab(Workspace):
    def __init__(self, win):
        super().__init__("tuning")
        self.win, self.s = win, win.state
        self._busy = True
        self._last = None          # poslední návrh
        self._result = None        # poslední simulace

        # ---- hlavní plocha: graf a ukazatele
        self.views = QTabWidget()
        page = QWidget()
        pl = QVBoxLayout(page)
        pl.setContentsMargins(0, 0, 0, 0)
        self.chart, self.plots = w.stack(3, ["PV", "MV", T("dists")], T("time_s"), heights=(0.55, 0.25, 0.2))
        pl.addWidget(self.chart, 1)
        self.kpi = w.table([], [])
        self.kpi.setMaximumHeight(118)
        pl.addWidget(self.kpi)
        self.views.addTab(page, T("dk_view_time"))
        self.freq = FrequencyView()
        self.views.addTab(self.freq, T("fq_title"))
        self.main.addWidget(self.views, 1)

        # ---- pevný pruh: výpočet a stav
        self.b_calc = QPushButton("▶  " + T("dk_calc") + "  (F5)")
        self.b_calc.setObjectName("primary")
        self.b_calc.setToolTip(T("dk_calc_help"))
        self.b_calc.clicked.connect(self.calculate)
        QShortcut(QKeySequence("F5"), self, activated=self.calculate, context=Qt.WidgetWithChildrenShortcut)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.top_bar(self.b_calc)
        self.top.addWidget(self.status)

        # ---- 1 · scénář
        self.kind = w.combo([])
        w.tip(self.kind, "dk_sc_kind_help")
        self.kind.currentIndexChanged.connect(self._kind_changed)
        self.sp0, self.sp1 = w.spin(0.0, -1e12, 1e12, 4), w.spin(0.0, -1e12, 1e12, 4)
        self.d_in, self.d_pv = w.spin(1.0, -1e12, 1e12, 4), w.spin(1.0, -1e12, 1e12, 4)
        self.auto_len = QCheckBox(T("dk_sim_auto"))
        self.auto_len.setChecked(True)
        self.t_end = w.spin(1000.0, 1.0, 1e9, 1)
        b_ev = QPushButton(T("dk_scen_edit"))
        b_ev.clicked.connect(self._edit_scenario)
        self.lab_sp0, self.lab_sp1 = QLabel(T("sim_sp_from", u="PV")), QLabel(T("sim_sp_to", u="PV"))
        self.lab_din, self.lab_dpv = QLabel(T("dk_sc_d_in", u="MV")), QLabel(T("dk_sc_d_pv", u="PV"))
        self.scen_form = w.form([(T("dk_sc_kind"), self.kind), (self.lab_sp0, self.sp0), (self.lab_sp1, self.sp1),
                                 (self.lab_din, self.d_in), (self.lab_dpv, self.d_pv), (T("sim_len"), self.t_end),
                                 ("", self.auto_len), ("", b_ev)])
        self.scen_note = caption("")
        self.len_src = caption("")
        sec = self.section(T("dk_sec_scen"), self.scen_form, "scen")
        sec.add(self.len_src)
        sec.add(self.scen_note)

        # ---- 2 · návrh
        self.method = w.combo([])
        self.ctype = w.combo(["PI", "PID"])
        self.tc = w.spin(1.0, 0.0, 1e9, 4)
        self.crit = w.combo(CRITS, labels=[T("crit_" + c) for c in CRITS])
        self.target = w.combo(TARGETS, labels=[T("tgt_" + c) for c in TARGETS])
        self.ms = w.combo([1.4, 1.6, 1.8, 2.0], 1.6, labels=["1.4", "1.6", "1.8", "2.0"])
        self.ovs = w.combo([0, 2, 5, 10], 2, labels=["0 %", "2 %", "5 %", "10 %"])
        self.noise = w.spin(1.0, 0.0, 1e12, 4)
        self.avg_dpv, self.avg_dmv = w.spin(1.0, 1e-9, 1e12, 4), w.spin(1.0, 1e-9, 1e12, 4)
        for c, k in ((self.method, "method_help"), (self.ctype, "h_ctype"), (self.tc, "tc_help"), (self.crit, "h_opt_crit"),
                     (self.target, "h_opt_target"), (self.ms, "opt_ms_help"), (self.ovs, "h_opt_ovs"),
                     (self.noise, "opt_noise_help"), (self.avg_dpv, "h_avg_dpv"), (self.avg_dmv, "avg_dmv_help")):
            w.tip(c, k)
        self.lab_ms, self.lab_ovs, self.lab_noise = QLabel(T("opt_ms")), QLabel(T("opt_ovs")), QLabel(T("opt_noise", u="MV"))
        self.lab_dpv, self.lab_dmv = QLabel(T("avg_dpv", u="PV")), QLabel(T("avg_dmv", u="MV"))
        self.lab_tc, self.lab_crit, self.lab_tgt = QLabel(T("tc")), QLabel(T("opt_crit")), QLabel(T("opt_target"))
        self.robust = QCheckBox(T("opt_robust"))
        w.tip(self.robust, "h_opt_robust")
        self.sug_form = mg = w.form([(T("method"), self.method), (T("ctrl_type"), self.ctype), (self.lab_tc, self.tc),
                     (self.lab_crit, self.crit), (self.lab_tgt, self.target), (self.lab_ms, self.ms),
                     (self.lab_ovs, self.ovs), (self.lab_noise, self.noise), (self.lab_dpv, self.avg_dpv),
                     (self.lab_dmv, self.avg_dmv), ("", self.robust)])
        self.desc = caption("")
        self.sug = w.note("")
        self.b_s1, self.b_s2 = QPushButton(T("write_s1")), QPushButton(T("write_s2"))
        self.b_s1.clicked.connect(lambda: self._write(1))
        self.b_s2.clicked.connect(lambda: self._write(2))
        self.b_cmp = QPushButton(T("cmp_title"))
        self.b_cmp.clicked.connect(self._compare)
        sec = self.section(T("dk_sec_sug"), mg, "sug")
        sec.add(self.desc)
        sec.add(self.sug)
        sec.add(w.hbox(self.b_s1, self.b_s2))
        sec.add(w.hbox(self.b_cmp))
        for c in (self.method, self.ctype, self.crit, self.target, self.ms, self.ovs):
            c.currentIndexChanged.connect(self._method_changed)
        for sp in (self.noise, self.avg_dpv, self.avg_dmv):
            sp.valueChanged.connect(self._method_changed)
        self.tc.valueChanged.connect(self._tc_changed)
        self.robust.toggled.connect(self._robust_toggled)

        # ---- 3 · sady a robustnost
        sg = QGridLayout()
        self.sets = {}
        for n in (1, 2):
            sg.addWidget(QLabel(T("set_" + str(n))), 0, n)
            for i, k in enumerate(("gain", "ti", "td")):
                sp = w.spin(0.0, -1e12, 1e12, 6)
                sp.valueChanged.connect(self._sets_changed)
                self.sets[(n, k)] = sp
                sg.addWidget(sp, i + 1, n)
        for i, lab in enumerate(("Gain", "TI [s]", "TD [s]")):
            sg.addWidget(QLabel(lab), i + 1, 0)
        self.rob = w.table(["", T("set_1"), T("set_2")], [])
        self.rob.setMinimumHeight(150)
        sec = self.section(T("dk_sec_sets"), sg, "sets")
        sec.add(self.rob)

        # ---- historie ladění
        self.hist = w.table([], [])
        self.hist.setSelectionBehavior(QTableWidget.SelectRows)
        self.hist.setSelectionMode(QTableWidget.SingleSelection)
        self.hist.setMinimumHeight(150)
        self.hist.setToolTip(T("dk_hist_help"))
        h1, h2, hd = QPushButton(T("dk_hist_s1")), QPushButton(T("dk_hist_s2")), QPushButton(T("dk_hist_del"))
        h1.clicked.connect(lambda: self._hist_restore(1))
        h2.clicked.connect(lambda: self._hist_restore(2))
        hd.clicked.connect(self._hist_delete)
        self.hist_sec = sec = self.section(T("dk_sec_hist"), self.hist, "hist", expanded=False)
        sec.add(w.hbox(h1, h2, hd))

        # ---- ověření robustnosti (zobrazení ve scénáři)
        self.c_robust, self.c_spread, self.c_ffcmp = QCheckBox(T("robust_on")), QCheckBox(T("spread_on")), QCheckBox(T("ff_cmp"))
        self.c_ffcmp.setChecked(True)
        box = QVBoxLayout()
        for c, k in ((self.c_robust, "h_robust_on"), (self.c_spread, "h_spread_on"), (self.c_ffcmp, "h_ff_cmp")):
            w.tip(c, k)
            c.toggled.connect(self._dirty)
            box.addWidget(c)
        self.section(T("dk_sec_verify"), box, "verify", expanded=False)

        # ---- doporučení D složky
        self.dadv = w.note("")
        self.section(T("d_title"), self.dadv, "dadv", expanded=False)

        # ---- blok PIDConL
        self.f = {}
        rows = [("pv_lo", "NormPV Low"), ("pv_hi", "NormPV High"), ("mv_lo", "NormMV Low"), ("mv_hi", "NormMV High"),
                ("samp", T("sampletime")), ("diffgain", "DiffGain"), ("propfac", "PropFacSP"), ("db", T("deadband")),
                ("mvl_lo", "MV_LoLim"), ("mvl_hi", "MV_HiLim"), ("pvfilt", T("pvfilt")),
                ("mvrate", T("mvrate", u="MV")), ("sprate", T("sprate", u="PV"))]
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
        self.db_mode = w.combo(["cont", "step"], labels=[T("db_cont"), T("db_step")])
        w.tip(self.db_mode, "db_mode_help")
        self.db_mode.currentIndexChanged.connect(self._block_changed)
        frm.insert(8, (T("db_mode"), self.db_mode))
        self.dfb = QCheckBox("DiffToFbk (" + T("dfb") + ")")
        w.tip(self.dfb, "h_dfb")
        self.dfb.toggled.connect(self._block_changed)
        frm.append(("", self.dfb))
        for k, key in (("pv_lo", "h_normpv"), ("pv_hi", "h_normpv"), ("mv_lo", "h_normmv"), ("mv_hi", "h_normmv"),
                       ("samp", "sampletime_help"), ("diffgain", "diffgain_help"), ("propfac", "pfb_help"),
                       ("db", "h_deadband"), ("mvl_lo", "h_mvlim"), ("mvl_hi", "h_mvlim"), ("pvfilt", "h_pvfilt"),
                       ("mvrate", "h_mvrate"), ("sprate", "h_sprate")):
            w.tip(self.f[k], key)
        self.section(T("dk_sec_block"), w.form(frm), "block", expanded=False)

        for sp in (self.sp0, self.sp1, self.t_end, self.d_in, self.d_pv):
            sp.valueChanged.connect(self._scenario_changed)
        self.auto_len.toggled.connect(self._scenario_changed)
        self._busy = False

    # ---- obnova (bez výpočtu)
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
            self.db_mode.setCurrentIndex(max(self.db_mode.findData(s.get("db_mode")), 0))
            self.robust.setChecked(bool(s.get("opt_robust")))
            for (n, k), sp in self.sets.items():
                sp.setValue(float(s.get(f"set{n}_{k}")))
            u_pv, u_mv = s.get("u_pv") or "PV", s.get("u_mv") or "MV"
            self.lab_sp0.setText(T("sim_sp_from", u=u_pv))
            self.lab_sp1.setText(T("sim_sp_to", u=u_pv))
            self.lab_din.setText(T("dk_sc_d_in", u=u_mv))
            self.lab_dpv.setText(T("dk_sc_d_pv", u=u_pv))
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
                self.ms.setCurrentIndex(max(self.ms.findData(float(s.get("opt_ms"))), 0))
                self.ovs.setCurrentIndex(max(self.ovs.findData(int(s.get("opt_ovs"))), 0))
                self.noise.setValue(float(s.get("opt_noise", round(0.01 * s.MR, 4))))
                self.avg_dpv.setValue(float(s.get("avg_dpv", round(0.1 * s.PR, 3))))
                self.avg_dmv.setValue(float(s.get("avg_dmv", round(0.1 * s.MR, 3))))
                adv = s.d_advice()
                val = (f"{T('tau_label')} = {adv['tau']:.2f}" if adv.get("tau") is not None else
                       f"{T('ratio_label')} = {adv['ratio']:.2f}" if adv.get("ratio") is not None else "")
                sig = s.sigma_pv()
                self.dadv.setText(f"**{adv['rec']}** — {T(adv['key'])}" + (f"  \n{val}" if val else "") +
                                  (f"  \n{T('noise_note', s=f'{sig * s.PR / 100:.3g}', u=u_pv)}" if sig > 0 else ""))
                kinds = [k for k in ("sp", "in", "pv", "sp_in", "meas", "replay", "custom")
                         if k not in ("meas", "replay") or s.c_d]
                self.kind.clear()
                for k in kinds:
                    self.kind.addItem(T("dk_sc_" + k), k)
                self.kind.setCurrentIndex(max(self.kind.findData(s.scen_kind), 0))
                d_in, d_pv, _ = s.scen_amps()
                self.d_in.setValue(d_in)
                self.d_pv.setValue(d_pv)
                self.c_spread.setEnabled(bool(s.unc_models()))
                sp0, sp1 = s.sp_from_to()
                self.sp0.setValue(sp0)
                self.sp1.setValue(sp1)
                self._tc_default()
        finally:
            self._busy = False
        self._enable()
        self._scen_fields()
        if s.model is None:
            self.sug.setText(T("need_model"))
            self.chart.clear()
            self.status.setText("")
            return
        self._robustness()
        self._history()
        if self._result is None or self._result.get("model") != s.model:
            self._result = None
            self.chart.clear()
            self.freq.clear()
            self.kpi.setRowCount(0)
            self.status.setText("ℹ️ " + T("dk_calc_hint"))
            self.status.setObjectName("")
        else:
            self._dirty()

    def _enable(self):
        m = self.method.currentData()
        opt, crit = m == "OPT", self.crit.currentData()
        for wd, on in ((self.tc, m in ("SIMC", "iSIMC", "Lambda")), (self.crit, opt), (self.target, opt and crit != "MIGO"),
                       (self.ms, opt), (self.ovs, opt and crit == "OVS"), (self.noise, opt and self.ctype.currentData() == "PID"),
                       (self.avg_dpv, m == "AVG"), (self.avg_dmv, m == "AVG")):
            wd.setVisible(on)
        for wd in (self.tc, self.crit, self.target, self.ms, self.ovs, self.noise, self.avg_dpv, self.avg_dmv):
            self.sug_form.setRowVisible(wd, not wd.isHidden())
        self.desc.setText((T("mdesc_" + m) + (f"  \n{T('cdesc_' + crit)}" if opt else "")) if m else "")

    def _scen_fields(self):
        k = self.kind.currentData() or "sp"
        for wd, lab, on in ((self.sp0, self.lab_sp0, k in ("sp", "sp_in", "custom", "in", "pv", "meas", "replay")),
                            (self.sp1, self.lab_sp1, k in ("sp", "sp_in", "custom")),
                            (self.d_in, self.lab_din, k in ("in", "sp_in")), (self.d_pv, self.lab_dpv, k == "pv")):
            self.scen_form.setRowVisible(wd, on)
        self.lab_sp0.setText(T("sim_sp_from" if k in ("sp", "sp_in", "custom") else "dk_sc_sp_level",
                               u=self.s.get("u_pv") or "PV"))
        self.t_end.setEnabled(not self.auto_len.isChecked() and k != "replay")
        self.auto_len.setEnabled(k != "replay")
        self.scen_note.setText(T("dk_sc_note_" + k))

    def _tc_default(self):
        s, m = self.s, self.method.currentData()
        if s.model is None or m not in ("SIMC", "iSIMC", "Lambda"):
            return
        code, p, _ = s.model
        tc0 = default_tc(code, p, float(s.get("samp")), m, self.ctype.currentData(), float(s.get("diffgain")))
        self.tc.setValue(float(s.get(f"tc|{code}|{m}|{self.ctype.currentData()}", tc0)))

    # ---- stav výsledku
    def _dirty(self, *_):
        if self._busy:
            return
        if self._result is None:
            self.status.setText("ℹ️ " + T("dk_calc_hint"))
            return
        self.status.setText("⚠️ " + T("dk_stale"))
        self.status.setStyleSheet("color:#b45309; font-weight:600")

    def _done(self, t0):
        self.status.setStyleSheet("")
        self.status.setText("✅ " + T("dk_calc_done", t=time.strftime("%H:%M:%S"), d=f"{time.time() - t0:.1f}"))

    # ---- návrh
    def _method_changed(self):
        if self._busy:
            return
        s = self.s
        s.set(**{f"method|{s.model[0]}": self.method.currentData(), "ctype": self.ctype.currentData(),
                 "opt_crit": self.crit.currentData(), "opt_target": self.target.currentData(),
                 "opt_ms": self.ms.currentData(), "opt_ovs": self.ovs.currentData(), "opt_noise": self.noise.value(),
                 "avg_dpv": self.avg_dpv.value(), "avg_dmv": self.avg_dmv.value()})
        self._busy = True
        self._tc_default()
        self._busy = False
        self._enable()
        self._dirty()

    def _tc_changed(self, *_):
        if self._busy or self.s.model is None:
            return
        m = self.method.currentData()
        if m in ("SIMC", "iSIMC", "Lambda"):
            self.s.settings[f"tc|{self.s.model[0]}|{m}|{self.ctype.currentData()}"] = self.tc.value()
        self._dirty()

    def _robust_toggled(self, on):
        if not self._busy:
            self.s.set(opt_robust=on)
            self._dirty()

    def calculate(self):
        """Návrh parametrů (optimalizace na pozadí) a simulace scénáře se sadami 1, 2 a návrhem."""
        s = self.s
        if s.model is None or not self.b_calc.isEnabled():
            return
        m = self.method.currentData()
        tc = self.tc.value() if m in ("SIMC", "iSIMC", "Lambda") else None
        t0 = time.time()
        self.b_calc.setEnabled(False)
        self.status.setStyleSheet("")
        self.status.setText("⏳ " + T("dk_optimizing" if m == "OPT" else "dk_calculating"))

        def fail(e):
            self.b_calc.setEnabled(True)
            self.status.setText("")
            self.win.error(T(str(e)))
        if m == "OPT":
            w.run_task(lambda _p: s.suggest(m, tc), lambda sug: self._after_sug(sug, t0), fail)
            return
        try:
            self._after_sug(s.suggest(m, tc), t0)
        except Exception as ex:
            fail(ex)

    def _after_sug(self, sug, t0):
        self.b_calc.setEnabled(True)
        self._show_sug(sug)
        self._simulate()
        self._done(t0)

    def _show_sug(self, sug):
        self._last = sug
        notes = "  \n".join("💡 " + T(k, **a) for k, a in sug.get("notes", []))
        warn = []
        if sug["Kc"] < 0:
            warn.append("↕️ " + T("warn_neg_gain"))
        s = self.s
        if s.model is not None and s.fit["res"][s.model[0]]["fit"] < 70:
            warn.append("⚠️ " + T("warn_low_fit"))
        self.sug.setText(f"**{T('dk_suggest')}:** Gain = {sug['Kc']:.4g} · TI = {sug['Ti']:.4g} s · "
                         f"TD = {sug['Td']:.4g} s" + ("  \n" + notes if notes else "")
                         + ("  \n" + "  \n".join(warn) if warn else ""))

    def _write(self, n):
        """Návrh do sady n; graf se hned přepočítá (návrh je už spočtený)."""
        if not self._last:
            return
        m = self.method.currentData()
        r = self._result or {}
        k = (r.get("kpis") or {}).get("sug")
        label = T("m_" + m) + (f" · {T('crit_' + self.crit.currentData())}" if m == "OPT" else "")
        self.s.write_set(n, self._last, log=dict(method=label, ctype=self.ctype.currentData(),
                                                 scen=self.kind.currentText(), iae=k["iae"] if k else None))
        self.win.refresh()
        if self._result is not None:
            self._simulate()
            self._done(time.time())

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
        s.set(**{k: sp.value() for k, sp in self.f.items()}, dfb=self.dfb.isChecked(), db_mode=self.db_mode.currentData())
        if s.rescale_if_needed():
            self.win.status(T("norm_rescaled"))
        self.win.refresh()

    def _sets_changed(self, *_):
        if self._busy:
            return
        self.s.set(**{f"set{n}_{k}": sp.value() for (n, k), sp in self.sets.items()})
        self._robustness()
        self._dirty()

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

    # ---- historie
    def _history(self):
        h = self.s.history()
        self.hist_sec.set_title(T("dk_sec_hist") + (f" ({len(h)})" if h else ""))
        w.fill(self.hist, [T("dk_hist_time"), T("dk_hist_set"), T("method"), T("ctrl_type"), T("dk_sc_kind"), "Gain",
                           "TI [s]", "TD [s]", "Ms", "IAE [%·s]"],
               [[e.get("time"), e.get("set"), e.get("method"), e.get("ctype", ""), e.get("scen", ""), e["Kc"], e["Ti"],
                 e["Td"], e.get("Ms"), e.get("iae")] for e in h])
        self.hist.resizeColumnsToContents()

    def _hist_restore(self, n):
        i = self.hist.currentRow()
        h = self.s.history()
        if 0 <= i < len(h):
            e = h[i]
            self.s.write_set(n, dict(Kc=e["Kc"], Ti=e["Ti"], Td=e["Td"]))
            self.win.refresh()
            self._dirty()

    def _hist_delete(self):
        i = self.hist.currentRow()
        h = self.s.history()
        if 0 <= i < len(h):
            del h[i]
            self.s.settings["tune_hist"] = h
            self._history()

    # ---- scénář
    def _kind_changed(self, *_):
        if self._busy:
            return
        self.s.set_scen_kind(self.kind.currentData())
        self._scen_fields()
        self._dirty()

    def _edit_scenario(self):
        s = self.s
        if s.model is None:
            return
        T_end = self.t_end.value()
        dlg = ScenarioDialog(self, s, s.scen_rows(T_end), T_end)
        if dlg.exec() == QDialog.Accepted:
            s.set_scen_rows(dlg.rows(), T_end)
            dlg.apply_plant()
            s.set_scen_kind("custom")
            self._busy = True
            self.kind.setCurrentIndex(max(self.kind.findData("custom"), 0))
            self._busy = False
            self._scen_fields()
            self._dirty()

    def _scenario_changed(self, *_):
        if self._busy:
            return
        s = self.s
        s.sim_sp = (self.sp0.value(), self.sp1.value())
        s.set(scen_d_in=self.d_in.value(), scen_d_pv=self.d_pv.value())
        rows = s.settings.get(s.scen_key)
        if rows and s.scen_kind == "custom":   # vlastní scénář: „z → na“ přepíše první skok SP (jako ve webu)
            from ...app.scenario import set_sp_step
            rows, hit = set_sp_step(rows, s.sim_sp[1] - s.sim_sp[0])
            if hit:
                s.settings[s.scen_key] = rows
        self._scen_fields()
        self._dirty()

    def _simulate(self):
        s = self.s
        if s.model is None:
            return
        r = s.simulate(None if self.auto_len.isChecked() else self.t_end.value(), self.c_robust.isChecked(),
                       self.c_spread.isChecked(), self.c_ffcmp.isChecked(), preview=self._last)
        r["model"] = s.model
        self._result = r
        self._busy = True
        self.t_end.setValue(r["T_end"])
        self._busy = False
        self.len_src.setText(T("sim_len_src_" + r["src"]) if r["src"] != "manual" else "")
        self.chart.clear()
        w.line(self.plots[0], r["t"], s.EP(r["sp"]), "SP", w.C_SP, 1.3, dash=True)
        rows = []
        for n, col, name in ((1, w.C_SET1, T("set_1")), (2, w.C_SET2, T("set_2")), ("sug", C_SUG, T("dk_sug_curve"))):
            if n not in r["runs"]:
                continue
            o, k = r["runs"][n], r["kpis"][n]
            if k is None:
                rows.append([name, T("dk_unstable"), "", "", "", ""])
                continue
            dash = n == 1
            wd = 1.6 if n == "sug" else 2.0
            w.line(self.plots[0], o["t"], s.EP(o["PV"]), name, col, wd, dash=dash)
            w.line(self.plots[1], o["t"], s.EM(o["MV"]), f"MV {name}", col, wd - 0.4, dash=dash)
            rows.append([name, k["iae"], k["maxdev"], k["mv_range"], k["mv_travel"], k["reversals"]])
        shown = set()
        for k, o in r["extra"]:                  # citlivost, bez FF, varianty z nejistoty
            col, dash, name = {"new_err": (w.C_SET2, True, T("new_err")), "set2_noff": ("#9aa5b1", True, T("set2_noff")),
                               "unc_variants": ("#86efac", False, T("unc_variants"))}[k]
            wd = 1.0 if k == "unc_variants" else 1.8
            w.line(self.plots[0], o["t"], s.EP(o["PV"]), None if k in shown else name, col, wd, dash)
            w.line(self.plots[1], o["t"], s.EM(o["MV"]), None, col, wd, dash)
            shown.add(k)
        sig = r["sig"]                           # poruchy scénáře (měřené v jejich jednotkách, IN a PV v jednotkách)
        has_d = False
        for i, (nm, d) in enumerate(zip(s.c_d, sig["dmeas"])):
            if (d != 0).any():
                w.line(self.plots[2], r["t"], d, str(nm), w.C_DIST[i % 4], 1.4)
                has_d = True
        if (sig["dmv"] != 0).any():
            w.line(self.plots[2], r["t"], sig["dmv"] * s.MR / 100, T("tg_IN"), "#a16207", 1.4)
            has_d = True
        if (sig["dpv"] != 0).any():
            w.line(self.plots[2], r["t"], sig["dpv"] * s.PR / 100, T("tg_PV"), "#7c3aed", 1.4)
            has_d = True
        self.chart.set_row_visible(2, has_d)
        self.chart.full_range()
        sets = [(T("set_1"), s.set_ctrl(1), w.C_SET1, True), (T("set_2"), s.set_ctrl(2), w.C_SET2, False)]
        if self._last is not None:
            sets.append((T("dk_sug_curve"), s.ctrl_of(self._last), C_SUG, False))
        self.freq.update(s.model[0], s.model[1], sets)
        lo, hi = s.EP(-25.0), s.EP(125.0)            # mimo rozsah NormPV ± 25 % jen ujíždějící (nestabilní) průběh
        self.chart.fit_y(0, min(lo, hi), max(lo, hi))
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
        self.tab.s.write_set(n, dict(Kc=q["Kc"], Ti=q["Ti"], Td=q["Td"]),
                             log=dict(method=T("m_" + q["method"]) + (f" · {T('crit_' + q['crit'])}" if q["crit"] else ""),
                                      ctype=q["ctype"], scen=T("cmp_title"), iae=None))
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
        self.vchar = QTableWidget(1, 10)
        self.vchar.setHorizontalHeaderLabels([f"{10 * i}–{10 * i + 10}" for i in range(10)])
        self.vchar.setVerticalHeaderLabels([T("vchar_gain")])
        self.vchar.setMaximumHeight(70)
        self.vchar.setToolTip(T("h_vchar"))
        for i, g_ in enumerate(state.get("vchar_last") or [1.0] * 10):
            self.vchar.setItem(0, i, QTableWidgetItem(f"{g_:.3g}"))
        lay.addWidget(w.group(T("plant_title"), w.form([(T("sim_stic", u=u_mv), self.stic), (T("sim_slip"), self.slip),
                                                        (T("sim_noise", u=u_pv), self.noise),
                                                        (T("vchar_title"), self.vchar)])))
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
        gains = []
        for i in range(10):
            try:
                gains.append(max(float(self.vchar.item(0, i).text().replace(",", ".")), 0.0))
            except (AttributeError, ValueError):
                gains.append(1.0)
        self.s.set(sim_J=self.slip.value(), sim_noise=self.noise.value(), vchar_last=gains)
