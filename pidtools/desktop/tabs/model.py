"""
Záložka Model: úsek identifikace (tažením v grafu), kvalita dat, nastavení a spuštění identifikace (na pozadí),
srovnání modelů, výběr modelu pro ladění, úprava parametrů a graf model vs. data.
"""
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QGridLayout, QHBoxLayout, QLabel, QProgressBar, QPushButton, QSplitter,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from ...app import model as mdl
from ...core import DIST_PARAMS, MODELS
from ...i18n import T
from .. import widgets as w

LEVEL_ICON = {0: "✅", 1: "⚠️", 2: "⛔"}


class ModelTab(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win, self.s = win, win.state
        lay = QVBoxLayout(self)
        split = QSplitter(Qt.Vertical)
        lay.addWidget(split)

        # ---- úsek identifikace
        top = QWidget()
        tl = QHBoxLayout(top)
        self.seg_chart, self.seg_plots = w.stack(2, ["PV", "MV"], T("time_s"), heights=(0.6, 0.4))
        self.region = pg.LinearRegionItem(brush=(31, 95, 168, 40))
        self.seg_plots[0].addItem(self.region)
        self.region.sigRegionChangeFinished.connect(self._region_moved)
        tl.addWidget(self.seg_chart, 3)
        side = QVBoxLayout()
        self.r_from, self.r_to = w.spin(0.0, 0, 1e9, 1), w.spin(0.0, 0, 1e9, 1)
        b_all = QPushButton(T("dk_whole"))
        b_all.clicked.connect(self._whole)
        for sp in (self.r_from, self.r_to):
            sp.valueChanged.connect(self._range_typed)
        side.addWidget(w.group(T("seg_title"), w.form([(T("dk_from"), self.r_from), (T("dk_to"), self.r_to),
                                                       ("", b_all)])))
        side.addWidget(w.note(T("dk_segment_help")))
        self.quality = w.note("")
        side.addWidget(w.group(T("q_title"), w.form([("", self.quality)])))
        side.addStretch(1)
        tl.addLayout(side, 1)
        split.addWidget(top)

        # ---- identifikace
        mid = QWidget()
        ml = QVBoxLayout(mid)
        g = QGridLayout()
        self.chk = {}
        for i, c in enumerate(MODELS):
            cb = QCheckBox(T("model_" + c))
            self.chk[c] = cb
            g.addWidget(cb, 0, i)
        self.thmax = w.spin(100.0, 0, 1e9, 1)
        self.level = w.combo(["none", "medium", "high"], labels=[T("dl_" + x) for x in ("none", "medium", "high")])
        self.strength = w.spin(4, 1, 10, 0, 1)
        self.sign = w.combo(["auto", "pos", "neg"], labels=[T("gsg_" + x) for x in ("auto", "pos", "neg")])
        self.stic = QCheckBox(T("id_stic"))
        self.run = QPushButton(T("run_fit"))
        self.run.setDefault(True)
        self.run.clicked.connect(self._identify)
        self.prog = QProgressBar()
        self.prog.setVisible(False)
        ml.addWidget(w.group(T("id_title"), g))
        ml.addLayout(w.hbox(QLabel(T("thmax")), self.thmax, QLabel(T("dist_level")), self.level,
                            QLabel(T("dist_strength")), self.strength, QLabel(T("gain_sign")), self.sign, self.stic,
                            self.run, self.prog))
        self.stale = w.note("")
        ml.addWidget(self.stale)
        self.res = w.table(["", "FIT [%]", "NRMSE [%]", T("col_status"), ""], [])
        self.res.setMaximumHeight(170)
        ml.addWidget(self.res)
        split.addWidget(mid)

        # ---- vybraný model
        bot = QWidget()
        bl = QHBoxLayout(bot)
        left = QVBoxLayout()
        self.mcode = w.combo([])
        self.mcode.currentIndexChanged.connect(self._model_chosen)
        self.params = QTableWidget(0, 0)
        self.params.setMaximumHeight(110)
        self.params.itemChanged.connect(self._param_edited)
        b_reset = QPushButton(T("dk_reset"))
        b_reset.clicked.connect(self._reset)
        self.fit_lab = w.note("")
        left.addWidget(w.group(T("model_for_tuning"), w.form([("", self.mcode)])))
        left.addWidget(w.group(T("dk_params"), w.form([("", self.params), ("", b_reset)])))
        left.addWidget(self.fit_lab)
        left.addStretch(1)
        bl.addLayout(left, 1)
        self.fit_chart, self.fit_plots = w.stack(2, ["PV", "MV"], T("time_s"), heights=(0.65, 0.35))
        bl.addWidget(self.fit_chart, 2)
        split.addWidget(bot)
        split.setSizes([300, 260, 320])

        for c in self.chk.values():
            c.toggled.connect(self._settings_changed)
        for c in (self.level, self.sign):
            c.currentIndexChanged.connect(self._settings_changed)
        for c in (self.thmax, self.strength):
            c.valueChanged.connect(self._settings_changed)
        self.stic.toggled.connect(self._settings_changed)
        self._busy = False

    # ---- obnova z stavu
    def refresh(self):
        s = self.s
        if not s.has_data:
            return
        self._busy = True
        try:
            g = s.grid
            for p in self.seg_plots:
                p.clear()
            self.seg_plots[0].addItem(self.region)
            if g.has_sp:
                w.line(self.seg_plots[0], g.t, g.sp_e, "SP", w.C_SP, 1.2, dash=True)
            w.line(self.seg_plots[0], g.t, g.pv_e, "PV", w.C_PV, 1.2)
            w.line(self.seg_plots[1], g.t, g.mv_e, "MV", w.C_MV, 1.4)
            self.region.setBounds((0, float(g.t[-1])))
            self.region.setRegion(s.rng)
            for sp in (self.r_from, self.r_to):
                sp.setRange(0, float(g.t[-1]))
            self.r_from.setValue(s.rng[0])
            self.r_to.setValue(s.rng[1])
            for c, cb in self.chk.items():
                cb.setChecked(c in s.get("chosen"))
            self.thmax.setValue(float(s.get("thmax")))
            self.level.setCurrentIndex(self.level.findData(s.get("dist_level")))
            self.strength.setValue(float(s.get("dist_strength")))
            self.sign.setCurrentIndex(self.sign.findData(s.get("gain_sign")))
            self.stic.setChecked(bool(s.get("id_stic")))
        finally:
            self._busy = False
        self._quality()
        self._results()

    def _quality(self):
        q = self.s.quality()
        if not q:
            self.quality.setText("—")
            return
        lines = [f"{LEVEL_ICON[q['level']]} **{T('q_level' + str(q['level']))}**"]
        def fa(ar):    # čísla v hláškách jako ve webu
            return {k: ((f"{v:.0f}" if abs(v) >= 100 else f"{v:.3g}") if isinstance(v, float) else v) for k, v in ar.items()}
        lines += [f"{LEVEL_ICON[lv]} {T(k, **fa(a))}" for k, lv, a in sorted(q["checks"], key=lambda c: -c[1])]
        self.quality.setText("  \n".join(lines))

    def _results(self):
        s = self.s
        self.stale.setText(("⚠️ " + T("dk_model_stale")) if s.stale else "")
        if not s.fit:
            w.fill(self.res, [""], [[T("info_fit")]])
            self.mcode.clear()
            self._draw_fit()
            return
        ts, pv, mv, d = s.segment()
        rows = []
        for q in mdl.summary(s.fit["res"], ts, pv, mv, d, s.grid.Ts):
            pars = ", ".join(f"{n} = {v:.4g}" for n, v in zip(MODELS[q["code"]]["params"], q["p"]))
            rows.append([T("model_" + q["code"]), round(q["FIT"], 1), round(q["NRMSE"], 2), T(f"st_{q['status']}"), pars])
        w.fill(self.res, [T("col_model"), "FIT [%]", "NRMSE [%]", T("col_status"), T("dk_params")], rows)
        self._busy = True
        try:
            self.mcode.clear()
            for c, r in s.fit["res"].items():
                self.mcode.addItem(f"{T('model_' + c)} ({r['fit']:.1f} %)", c)
            self.mcode.setCurrentIndex(max(self.mcode.findData(s.get("mcode")), 0))
        finally:
            self._busy = False
        self._fill_params()
        self._draw_fit()

    def _fill_params(self):
        s = self.s
        m = s.model
        self._busy = True
        try:
            if m is None:
                self.params.setRowCount(0)
                return
            code, p, pdl = m
            names = list(MODELS[code]["params"])
            cols = names + [f"{n} ({dn})" for dn in s.c_d for n in DIST_PARAMS]
            vals = list(p) + [v for d in pdl for v in d]
            self.params.setColumnCount(len(cols))
            self.params.setRowCount(1)
            self.params.setHorizontalHeaderLabels(cols)
            for j, v in enumerate(vals):
                self.params.setItem(0, j, QTableWidgetItem(f"{v:.5g}"))
        finally:
            self._busy = False

    def _draw_fit(self):
        for p in self.fit_plots:
            p.clear()
        s = self.s
        if s.model is None:
            self.fit_lab.setText("")
            return
        ev = s.evaluate()
        m = s.sel_mask
        t = s.t[m]
        w.line(self.fit_plots[0], t, s.EP(ev["y_plot"]), T("model_" + s.model[0]), "#ea580c", 2.4)
        w.line(self.fit_plots[0], t, s.grid.pv_e[m], "PV", w.C_PV, 1.0)
        w.line(self.fit_plots[1], t, s.grid.mv_e[m], "MV", w.C_MV, 1.4)
        mm = ev["metrics"]
        self.fit_lab.setText(f"**{T('fit_edit')}: {ev['fit']:.1f} %** · NRMSE {mm['NRMSE']:.2f} % · "
                             f"{T('col_status')}: {T('st_' + str(mm['status']))}")

    # ---- akce
    def _region_moved(self):
        if self._busy:
            return
        a, b = self.region.getRegion()
        self.s.rng = (max(0.0, float(a)), min(float(b), float(self.s.t[-1])))
        self.win.refresh()

    def _range_typed(self):
        if self._busy:
            return
        a, b = self.r_from.value(), self.r_to.value()
        if b > a:
            self.s.rng = (a, b)
            self.win.refresh()

    def _whole(self):
        self.s.rng = (0.0, float(self.s.t[-1]))
        self.win.refresh()

    def _settings_changed(self, *_):
        if self._busy:
            return
        self.s.set(chosen=[c for c, cb in self.chk.items() if cb.isChecked()], thmax=self.thmax.value(),
                   dist_level=self.level.currentData(), dist_strength=self.strength.value(),
                   gain_sign=self.sign.currentData(), id_stic=self.stic.isChecked())
        self._results()

    def _identify(self):
        s = self.s
        if not s.get("chosen"):
            return
        self.run.setEnabled(False)
        self.prog.setVisible(True)
        self.prog.setRange(0, len(s.get("chosen")))
        self.win.status(T("dk_identifying"))

        def work(progress):
            return s.identify(progress=lambda i, c: progress(i, T("model_" + c)))

        def done(errs):
            self.run.setEnabled(True)
            self.prog.setVisible(False)
            self.win.status("")
            for c, ex in errs:
                self.win.error(f"{T('model_' + c)}: {T(ex)}")
            self.win.refresh()

        def failed(msg):
            self.run.setEnabled(True)
            self.prog.setVisible(False)
            self.win.error(T(msg))

        w.run_task(work, done, failed, lambda f, txt: (self.prog.setValue(int(f)), self.win.status(
            f"{T('dk_identifying')} {txt}")))

    def _model_chosen(self):
        if self._busy:
            return
        self.s.set(mcode=self.mcode.currentData())
        self.win.refresh(skip=None)

    def _param_edited(self, item):
        if self._busy or self.s.model is None:
            return
        code = self.s.model[0]
        n = len(MODELS[code]["params"])
        j = item.column()
        try:
            v = float(item.text().replace(",", "."))
        except ValueError:
            self._fill_params()
            return
        key = f"ed|{code}|{j}" if j < n else f"ed|{code}|d{(j - n) // 3}|{(j - n) % 3}"
        self.s.settings[key] = v
        self.win.refresh()

    def _reset(self):
        if self.s.model is not None:
            self.s.reset_edits(self.s.model[0])
            self.win.refresh()
