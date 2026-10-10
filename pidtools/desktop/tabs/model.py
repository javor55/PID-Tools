"""
Záložka Model: úsek identifikace – společný úsek (tažením v grafu), nebo úseky podle vstupů (MV a každá porucha
vlastní úseky, vyřazení dat podle mezí) –, kvalita dat, nastavení a spuštění identifikace (na pozadí), srovnání
modelů, výběr modelu a struktur přenosů poruch, úprava parametrů a graf model vs. data (v úsecích i na celém záznamu).
"""
import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QProgressBar, QPushButton, QSplitter,
                               QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from ...app import model as mdl
from ...app import windows as wn
from ...core import DIST_FIELDS, MODELS, merge_windows, pd_z
from ...i18n import T
from .. import widgets as w
from ..layout import Workspace, caption

LEVEL_ICON = {0: "✅", 1: "⚠️", 2: "⛔"}
WIN_COLORS = ["#f59e0b", "#0d9488", "#7c3aed", "#db2777", "#0891b2"]     # MV, poruchy (jako ve webu)


class ModelTab(Workspace):
    def __init__(self, win):
        super().__init__("model")
        self.win, self.s = win, win.state

        # ---- hlavní plocha: jedna sada grafů (celý záznam s úsekem, model, MV, poruchy, rezidua),
        #      výsledky identifikace a doplňkové pohledy
        split = QSplitter(Qt.Vertical)
        split.setChildrenCollapsible(False)
        self.main.addWidget(split, 1)
        self.chart, self.plots = w.stack(4, ["PV", "MV", T("dk_dist_axis"), T("resid")], T("time_s"),
                                         heights=(0.42, 0.24, 0.18, 0.16))
        self.seg_chart, self.seg_plots = self.chart, self.plots       # úsek se vybírá přímo v grafu
        self.fit_chart, self.fit_plots = self.chart, self.plots
        self.region = pg.LinearRegionItem(brush=(31, 95, 168, 40))
        self.plots[0].addItem(self.region)
        self.region.sigRegionChangeFinished.connect(self._region_moved)
        split.addWidget(self.chart)
        mid = QWidget()
        ml = QVBoxLayout(mid)
        ml.setContentsMargins(0, 0, 0, 0)
        self.stale = w.note("")
        self.full_cb = QCheckBox(T("mw_r_full"))
        w.tip(self.full_cb, "h_mw_full")
        self.full_cb.toggled.connect(lambda *_: self._draw_fit())
        ml.addLayout(w.hbox(self.stale, self.full_cb))
        self.res = w.table(["", "FIT [%]", "NRMSE [%]", T("col_status"), ""], [])
        self.res.setMinimumHeight(90)
        ml.addWidget(self.res, 1)
        split.addWidget(mid)
        self.sub = QTabWidget()
        self.step_plot = w.plot(T("step_title"), "ΔPV", T("time_s"))
        self.sub.addTab(self.step_plot, T("step_title"))
        self.all_chart, self.all_plots = w.stack(2, ["PV", "MV"], T("time_s"), heights=(0.7, 0.3))
        self.sub.addTab(self.all_chart, T("compare_all"))
        tests = QWidget()
        tlay = QVBoxLayout(tests)
        self.eval_tab = w.table([], [])
        self.eval_tab.setMaximumHeight(200)
        self.eval_msg = w.note("")
        tlay.addWidget(self.eval_tab)
        tlay.addWidget(self.eval_msg)
        th = QHBoxLayout()
        self.acf_plot, self.ccf_plot = w.plot(T("eval_acf_t"), "", T("lag_s")), w.plot(T("eval_ccf_t"), "", T("lag_s"))
        th.addWidget(self.acf_plot)
        th.addWidget(self.ccf_plot)
        tlay.addLayout(th, 1)
        self.sub.addTab(tests, T("eval_title"))
        self.dist_plot = w.plot("", "ΔPV", T("time_s"))
        self.sub.addTab(self.dist_plot, T("dk_unmeasured"))
        self.val_index = self.sub.addTab(self._validation_page(), T("val_title"))
        self.win_index = self.sub.addTab(self._windows_page(), T("ms_cmp"))
        self.sub.currentChanged.connect(lambda i: self._validate() if i == self.val_index else None)
        split.addWidget(self.sub)
        split.setStretchFactor(0, 6)
        split.setStretchFactor(1, 1)
        split.setStretchFactor(2, 3)
        split.setSizes([560, 120, 300])

        # ---- pevný pruh: identifikace
        self.run = QPushButton("▶  " + T("run_fit"))
        self.run.setObjectName("primary")
        self.run.clicked.connect(self._identify)
        self.prog = QProgressBar()
        self.prog.setVisible(False)
        self.top_bar(self.run)
        self.top.addWidget(self.prog)

        # ---- 1 · úsek: společný, nebo podle vstupů
        self.wmode = w.combo(["common", "inputs"], labels=[T("mw_common"), T("mw_inputs")])
        w.tip(self.wmode, "h_mw_mode")
        self.wmode.currentIndexChanged.connect(self._wmode_changed)
        self.r_from, self.r_to = w.spin(0.0, 0, 1e9, 1), w.spin(0.0, 0, 1e9, 1)
        b_all = QPushButton(T("dk_whole"))
        b_all.clicked.connect(self._whole)
        for sp in (self.r_from, self.r_to):
            sp.valueChanged.connect(self._range_typed)
        self.common_box = QWidget()
        cl = QVBoxLayout(self.common_box)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.addLayout(w.form([(T("dk_from"), self.r_from), (T("dk_to"), self.r_to), ("", b_all)]))
        cl.addWidget(caption(T("dk_segment_help")))
        self.inputs_box = QWidget()          # úseky podle vstupů: tabulka (vstup, od, do) + přidat / odebrat
        il = QVBoxLayout(self.inputs_box)
        il.setContentsMargins(0, 0, 0, 0)
        self.win_tab = QTableWidget(0, 3)
        self.win_tab.verticalHeader().setVisible(False)
        self.win_tab.setSelectionBehavior(QTableWidget.SelectRows)
        self.win_tab.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.win_tab.setMinimumHeight(110)
        self.win_tab.itemChanged.connect(self._win_edited)
        self.win_in = w.combo([])
        b_add, b_del = QPushButton(T("dk_win_add")), QPushButton(T("mw_del"))
        b_add.clicked.connect(self._win_add)
        b_del.clicked.connect(self._win_del)
        il.addWidget(self.win_tab)
        il.addLayout(w.hbox(self.win_in, b_add, b_del))
        il.addWidget(caption(T("dk_win_help")))
        sec = self.section(T("dk_sec_segment"), w.form([(T("mw_mode"), self.wmode)]), "segment")
        sec.add(self.common_box)
        sec.add(self.inputs_box)
        self.quality = w.note("")
        sec.add(QLabel("<b>" + T("q_title") + "</b>"))
        sec.add(self.quality)

        # ---- vyřazení dat (úseky podle vstupů)
        self.excl_tab = QTableWidget(0, 4)
        self.excl_tab.verticalHeader().setVisible(False)
        self.excl_tab.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.excl_tab.itemChanged.connect(self._excl_edited)
        self.excl_tol = w.spin(0.5, 0.0, 20.0, 2)
        w.tip(self.excl_tol, "h_excl_tol")
        self.excl_tol.valueChanged.connect(self._excl_tol_changed)
        self.excl_note = caption("")
        self.excl_sec = self.section(T("excl_title"), caption(T("excl_intro")), "excl", expanded=True)
        self.excl_sec.add(self.excl_tab)
        self.excl_sec.add(w.form([(T("excl_tol"), self.excl_tol)]))
        self.excl_sec.add(self.excl_note)

        # ---- 2 · identifikace
        g = QGridLayout()
        self.chk = {}
        for i, c in enumerate(MODELS):
            cb = QCheckBox(T("model_" + c))
            self.chk[c] = cb
            g.addWidget(cb, i, 0)
        self.thmax = w.spin(100.0, 0, 1e9, 1)
        self.level = w.combo(["none", "medium", "high"], labels=[T("dl_" + x) for x in ("none", "medium", "high")])
        self.strength = w.spin(4, 1, 10, 0, 1)
        self.sign = w.combo(["auto", "pos", "neg"], labels=[T("gsg_" + x) for x in ("auto", "pos", "neg")])
        self.stic = QCheckBox(T("id_stic"))
        self.mode = w.combo(["open", "cl"], labels=[T("idm_open"), T("idm_cl")])
        w.tip(self.mode, "h_idm")
        self.mode_note = caption("")
        self.b_est = QPushButton(T("idm_est_btn"))
        w.tip(self.b_est, "h_idm_est")
        self.b_est.clicked.connect(self._estimate_set1)
        sec = self.section(T("dk_sec_ident"), w.form([(T("idm"), self.mode)]), "ident")
        sec.add(self.mode_note)
        sec.add(self.b_est)
        sec.add(g)
        sec.add(w.form([(T("thmax"), self.thmax), (T("dist_level"), self.level), (T("dist_strength"), self.strength),
                        (T("gain_sign"), self.sign), ("", self.stic)]))
        self.dk_box = QWidget()             # typ přenosu a směr účinku každé poruchy (pro identifikaci)
        self.dk_lay = QGridLayout(self.dk_box)
        self.dk_lay.setContentsMargins(0, 0, 0, 0)
        self._dk_for = None
        sec.add(self.dk_box)

        # ---- 3 · model pro ladění
        self.mcode = w.combo([])
        self.mcode.currentIndexChanged.connect(self._model_chosen)
        self.params = QTableWidget(0, 2)
        self.params.setMinimumHeight(120)
        self.params.setToolTip(T("fix_help"))
        self.params.itemChanged.connect(self._param_edited)
        b_reset = QPushButton(T("dk_reset"))
        b_reset.clicked.connect(self._reset)
        self.b_refit = QPushButton(T("refit"))
        w.tip(self.b_refit, "h_refit")
        self.b_refit.clicked.connect(self._refit)
        self.fit_lab = w.note("")
        sec = self.section(T("dk_sec_model"), w.form([(T("model_for_tuning"), self.mcode)]), "model")
        self.ds_box = QWidget()             # struktura přenosu každé poruchy po identifikaci (podle FIT)
        self.ds_lay = QGridLayout(self.ds_box)
        self.ds_lay.setContentsMargins(0, 0, 0, 0)
        sec.add(self.ds_box)
        self.ds_note = caption("")
        sec.add(self.ds_note)
        sec.add(QLabel(T("dk_params")))
        sec.add(self.params)
        self.params.setMinimumWidth(0)
        sec.add(w.hbox(self.b_refit, b_reset))
        sec.add(self.fit_lab)

        # ---- nejistota
        self.unc_n = w.spin(15, 5, 50, 0, 1)
        self.b_unc = QPushButton(T("unc_run"))
        self.b_unc.clicked.connect(self._bootstrap)
        self.unc_tab = w.table([], [])
        self.unc_tab.setMaximumHeight(130)
        sec = self.section(T("unc_title"), w.form([(T("unc_n"), w.hbox(self.unc_n, self.b_unc))]), "unc", expanded=False)
        sec.add(self.unc_tab)

        for c in self.chk.values():
            c.toggled.connect(self._settings_changed)
        for c in (self.level, self.sign):
            c.currentIndexChanged.connect(self._settings_changed)
        for c in (self.thmax, self.strength):
            c.valueChanged.connect(self._settings_changed)
        self.stic.toggled.connect(self._settings_changed)
        self.mode.currentIndexChanged.connect(self._mode_changed)
        self._busy = False

    # ---- obnova z stavu
    def refresh(self):
        s = self.s
        if not s.has_data:
            return
        self._busy = True
        try:
            g = s.grid
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
            self.mode.setCurrentIndex(max(self.mode.findData(s.get("id_mode") or "open"), 0))
            self.wmode.setCurrentIndex(max(self.wmode.findData(s.win_mode), 0))
            self.excl_tol.setValue(float(s.excl_tol))
        finally:
            self._busy = False
        inp = s.inputs_mode
        self.common_box.setVisible(not inp)
        self.inputs_box.setVisible(inp)
        self.excl_sec.setVisible(inp)
        self._fill_wins()
        self._fill_excl()
        self._fill_dkinds()
        self._quality()
        self._mode_note()
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
        self.stale.setText(("⚠️ " + T("warn_sig_changed")) if s.signals_changed else
                           ("⚠️ " + T("dk_model_stale")) if s.stale else "")
        if not s.fit or s.signals_changed:
            w.fill(self.res, [""], [[T("info_fit")]])
            self.mcode.clear()
            self._fill_dsel()
            self._fill_params()
            self._draw_fit()
            self._fill_windows_page()
            return
        ts, pv, mv, d = s.segment()
        live = s.live_fits()                  # shoda na aktuálních úsecích (úseky se mohly od identifikace změnit)
        n_w = len(merge_windows(s.win_idx, len(s.t))) if s.inputs_mode else 0     # překrývající se úseky se sloučí
        win_labels = [f"{T('ms_win')} {k + 1}" for k in range(n_w)]
        rows = []
        for q in mdl.summary(s.fit["res"], ts, pv, mv, d, s.grid.Ts):
            c = q["code"]
            pars = ", ".join(f"{n} = {v:.4g}" for n, v in zip(MODELS[c]["params"], q["p"]))
            r_ = s.fit["res"][c]
            cl_ = (f"PV {r_['fit_cl_pv']:.1f} / MV {r_['fit_cl_mv']:.1f}" if r_.get("method") == "cl"
                   and r_.get("fit_cl_pv") is not None else "—")
            row = [T("model_" + c), round(live[c], 1), round(q["NRMSE"], 2), T(f"st_{q['status']}"), cl_, pars,
                   ", ".join(wn.structs(c, r_)) or "—"]
            if win_labels:
                fits_ = s.window_fits(c) if r_.get("method") == "win" else []
                row += [round(f_, 1) if f_ is not None else None for f_ in fits_] + [None] * (len(win_labels) - len(fits_))
            rows.append(row)
        w.fill(self.res, [T("col_model"), "FIT [%]", "NRMSE [%]", T("col_status"), T("idm_fit_cl"), T("dk_params"),
                          T("dkind")] + win_labels, rows)
        self._busy = True
        try:
            self.mcode.clear()
            for c in s.fit["res"]:
                self.mcode.addItem(f"{T('model_' + c)} ({live[c]:.1f} %)", c)
            self.mcode.setCurrentIndex(max(self.mcode.findData(s.get("mcode")), 0))
        finally:
            self._busy = False
        self._fill_dsel()
        self._fill_params()
        self._draw_fit()
        self._show_unc()
        self._validate()
        self._fill_windows_page()

    def _fill_params(self):
        s = self.s
        m = s.model
        self._busy = True
        try:
            if m is None:
                self.params.setRowCount(0)
                return
            code, p, pdl = m
            r = s.fit["res"][code]
            names = list(MODELS[code]["params"])
            rows = list(names)
            vals = list(p)
            keys = [(f"ed|{code}|{i}", f"fx|{code}|{i}") for i in range(len(names))]
            for j, dn in enumerate(s.c_d):        # poruchy: parametry podle zvolené struktury
                z = pd_z(pdl[j])
                for n, i in DIST_FIELDS[wn.dsel(s.get, code, r, j)]:
                    rows.append(f"{n} ({dn})")
                    vals.append(z[i])
                    keys.append((f"ed|{code}|d{j}|{i}", f"fx|{code}|d{j}|{i}"))
            self.params.setRowCount(len(rows))         # parametry pod sebou: hodnota, zafixovat
            self.params.setVerticalHeaderLabels(rows)
            self.params.setHorizontalHeaderLabels([T("dk_value"), T("fix")])
            for j, (v, (ke, kf)) in enumerate(zip(vals, keys)):
                it0 = QTableWidgetItem(f"{v:.5g}")
                it0.setData(Qt.UserRole, ke)
                self.params.setItem(j, 0, it0)
                it = QTableWidgetItem()
                it.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
                it.setCheckState(Qt.Checked if s.get(kf) else Qt.Unchecked)
                it.setData(Qt.UserRole, kf)
                self.params.setItem(j, 1, it)
            self.params.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
            self.params.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
            hh = self.params.horizontalHeader().height() + 4
            self.params.setFixedHeight(hh + sum(self.params.rowHeight(i) for i in range(len(rows))))
        finally:
            self._busy = False

    # ---- typy přenosů poruch (před identifikací) a zvolené struktury (po ní)
    def _fill_dkinds(self):
        s = self.s
        key = (tuple(s.c_d), s.inputs_mode)
        if key != self._dk_for:              # nová sada poruch → nové řádky
            self._dk_for = key
            while self.dk_lay.count():
                it = self.dk_lay.takeAt(0)
                if it.widget():
                    it.widget().deleteLater()
            self._dk = []
            for j, dn in enumerate(s.c_d):
                cb = w.combo(list(mdl.DIST_CHOICES), labels=[T("dkind_" + x) if x in ("pv", "auto") else T("model_" + x)
                                                             for x in mdl.DIST_CHOICES])
                w.tip(cb, "h_dkind")
                sg_ = w.combo(["auto", "pos", "neg"], labels=["auto", "+", "−"])
                w.tip(sg_, "h_dsign")
                sg_.setVisible(s.inputs_mode)
                cb.currentIndexChanged.connect(lambda *_, d_=dn, c_=cb: self._dkind_changed(d_, c_))
                sg_.currentIndexChanged.connect(lambda *_, d_=dn, c_=sg_: self._dsign_changed(d_, c_))
                self.dk_lay.addWidget(QLabel(f"{T('dkind')} · {dn}"), j, 0)
                self.dk_lay.addWidget(cb, j, 1)
                self.dk_lay.addWidget(sg_, j, 2)
                self._dk.append((cb, sg_))
        self._busy = True
        try:
            for (cb, sg_), dn, k in zip(self._dk, s.c_d, s.dkinds()):
                cb.setCurrentIndex(max(cb.findData(k), 0))
                sg_.setCurrentIndex(max(sg_.findData(s.get(f"dsign|{dn}", "auto")), 0))
        finally:
            self._busy = False

    def _dkind_changed(self, dn, cb):
        if not self._busy:
            self.s.settings[f"dkind|{dn}"] = cb.currentData()
            self._results()

    def _dsign_changed(self, dn, cb):
        if not self._busy:
            self.s.settings[f"dsign|{dn}"] = cb.currentData()
            self._results()

    def _fill_dsel(self):
        s = self.s
        while self.ds_lay.count():
            it = self.ds_lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        m = s.model
        self.ds_note.setText("")
        if m is None:
            return
        code = m[0]
        r = s.fit["res"][code]
        notes = []
        for j, dn in enumerate(s.c_d):
            opts, fits = wn.dsel_options(code, r, j)
            idn = wn.dist_id(code, r, j)
            labels = [T("model_" + x) + (f" · FIT {fits[x]:.1f} %" if x in fits else "")
                      + (f" · {T('ms_dist_ident')}" if x == idn else "") for x in opts]
            cb = w.combo(opts, labels=labels)
            w.tip(cb, "h_dkind")
            cb.setCurrentIndex(max(cb.findData(wn.dsel(s.get, code, r, j)), 0))
            cb.currentIndexChanged.connect(lambda *_, j_=j, c_=cb, k_=code: self._dsel_changed(k_, j_, c_))
            self.ds_lay.addWidget(QLabel(f"{T('dkind')} · {dn}"), j, 0)
            self.ds_lay.addWidget(cb, j, 1)
            if j in set(r.get("dv_flat") or ()):
                notes.append(f"ℹ️ {dn}: {T('ms_dv_flat')}")
        self.ds_note.setText("  \n".join(notes))

    def _dsel_changed(self, code, j, cb):
        if self._busy:
            return
        self.s.choose_dist(code, j, cb.currentData())
        self.win.refresh()

    def _bootstrap(self):
        s = self.s
        if s.model is None:
            return
        self.b_unc.setEnabled(False)
        n = int(self.unc_n.value())

        def done(_):
            self.b_unc.setEnabled(True)
            self.win.status("")
            self.win.refresh()
        w.run_task(lambda prog: s.bootstrap(n, progress=lambda f: prog(f)), done,
                   lambda e: (self.b_unc.setEnabled(True), self.win.error(T(e))),
                   lambda f, _t: self.win.status(f"{T('unc_running')} {100 * f:.0f} %"))

    def _show_unc(self):
        s = self.s
        ps = s.unc_models()
        if not ps or s.model is None:
            w.fill(self.unc_tab, [""], [])
            return
        code, p, _ = s.model
        un = mdl.uncertainty(ps, p)
        w.fill(self.unc_tab, ["", T("unc_nominal"), T("unc_p05"), T("unc_p95"), T("unc_rel")],
               [[n, p[i], un["p05"][i], un["p95"][i], f"± {un['rel'][i]:.0f} %"]
                for i, n in enumerate(MODELS[code]["params"])])

    def _draw_record(self):
        """Celý záznam (PV, SP, MV, měřené poruchy) s úsekem / úseky podle vstupů; model se kreslí přes něj."""
        s = self.s
        self.chart.clear()
        g = s.grid
        if not s.inputs_mode:
            self.plots[0].addItem(self.region)
        if g.has_sp:
            w.line(self.plots[0], g.t, g.sp_e, "SP", w.C_SP, 1.2, dash=True)
        w.line(self.plots[0], g.t, g.pv_e, "PV", w.C_PV, 1.1)
        w.line(self.plots[1], g.t, g.mv_e, "MV", w.C_MV, 1.4)
        for i, (nm, d) in enumerate(zip(s.c_d, g.dists)):
            w.line(self.plots[2], g.t, d, str(nm), w.C_DIST[i % 4], 1.4)
        self.chart.set_row_visible(2, bool(s.c_d))
        if s.inputs_mode:
            self._draw_wins()

    def _draw_wins(self):
        """Úseky podle vstupů jako posuvné oblasti: MV v grafu MV, poruchy v grafu poruch; vyřazené části šedě."""
        s = self.s
        t_end = float(s.t[-1])
        for k, (inp, ws_) in enumerate(s.wins_s.items()):
            plot = self.plots[1] if inp == "MV" else self.plots[2]
            col = pg.mkColor(WIN_COLORS[k % len(WIN_COLORS)])
            for i, (a, b) in enumerate(ws_):
                fill = pg.mkColor(col)
                fill.setAlpha(45)
                reg = pg.LinearRegionItem((a, b), brush=fill, pen=pg.mkPen(col, width=1.5), bounds=(0, t_end))
                reg.setZValue(-10)
                reg.sigRegionChangeFinished.connect(lambda r_, inp_=inp, i_=i: self._win_moved(inp_, i_, r_))
                plot.addItem(reg)
        v = s.valid
        if v is not None and (~v).any():                     # vyřazené vzorky (mimo meze) šedě pod PV
            for a, b in wn.runs(~v, s.t)[:200]:
                it = pg.LinearRegionItem((a, b), movable=False, brush=(148, 163, 184, 70), pen=pg.mkPen(None))
                it.setZValue(-20)
                self.plots[0].addItem(it)

    def _draw_fit(self):
        s = self.s
        if not s.has_data:
            return
        self._draw_record()
        self.chart.set_row_visible(3, s.model is not None)
        if getattr(self, "_view_of", None) is not s.grid:        # nová data → celý záznam, jinak zoom zůstane
            self._view_of = s.grid
            self.chart.full_range()
        if s.model is None:
            self.fit_lab.setText("")
            return
        ev = s.evaluate()
        m = s.sel_mask
        t = s.t[m]
        code, p, pdl = s.model
        r = s.fit["res"][code]
        cv = s.model_curves()            # model v úsecích, nebo na celém záznamu (navazuje na data každých full_h)
        full = self.full_cb.isChecked()
        y_m = cv["full_all"] if full else cv["all"]
        w.line(self.plots[0], s.t, s.EP(y_m), T("model_" + code), "#ea580c", 2.2).setZValue(-1)   # PV navrchu
        w.line(self.plots[3], s.t, (s.pv - cv["all"]) * s.PR / 100, T("resid"), "#64748b", 1.0)
        self.full_cb.setToolTip(T("mw_r_full_tip", h=f"{cv['full_h']:.0f} s"))
        mm = ev["metrics"]
        edited = mdl.is_edited(p, pdl, r.get("stic", 0.0) or 0.0, r)
        live = s.live_fits()
        self.fit_lab.setText(f"**{T('fit_edit')}: {ev['fit']:.1f} %** · NRMSE {mm['NRMSE']:.2f} % · "
                             f"{T('col_status')}: {T('st_' + str(mm['status']))}"
                             + (f"  \n{T('fit_fit')}: {live[code]:.1f} %" if edited else ""))
        # přechodová charakteristika (nafitovaná a upravená)
        from ...core import predict, predict_windows, step_response
        self.step_plot.clear()
        ta, ya = step_response(code, r["p"])
        w.line(self.step_plot, ta, ya * s.PR / 100, T("fit"), "#ea580c", 2.2)
        if edited:
            tb, yb = step_response(code, p, horizon=ta[-1])
            w.line(self.step_plot, tb, yb * s.PR / 100, T("edited"), "#0891b2", 2.0, dash=True)
        self.step_plot.addItem(pg.InfiniteLine(pos=p[-1], angle=90, pen=pg.mkPen("#94a3b8", style=Qt.DotLine)))
        # všechny modely
        for pl in self.all_plots:
            pl.clear()
        ts, pv, mv, d = s.segment()
        w.line(self.all_plots[0], t, s.grid.pv_e[m], "PV", w.C_PV, 1.0)
        from ...app.colors import C_MODEL
        for c, rr in s.fit["res"].items():
            if rr.get("method") == "win" and s.inputs_mode:
                y = predict_windows(c, rr["p"], rr["pdl"], s.t, s.pv, s.mv, s.grid.Ts, list(s.grid.dists), s.win_idx,
                                    s.valid)[0][m]
            else:
                y = predict(c, rr["p"], rr["pdl"], ts, pv, mv, d, s.grid.Ts, rr.get("stic", 0.0))[0]
            w.line(self.all_plots[0], t, s.EP(y), f"{c} ({live[c]:.1f} %)", C_MODEL.get(c, "#888"), 1.8)
        w.line(self.all_plots[1], t, s.grid.mv_e[m], "MV", w.C_MV, 1.4)
        # testy reziduí
        segs = [(T("eval_id"), mm)]
        self._eval(segs)
        # neměřené poruchy
        self.dist_plot.clear()
        lvl = r.get("level", "none")
        pf = ev["pf"]
        if lvl == "high" and pf.get("dist") is not None:
            w.line(self.dist_plot, t, pf["dist"] * s.PR / 100, T("dl_est"), "#7c3aed", 2.0)
            self.dist_plot.setTitle(T("dl_view", th=f"{(r.get('Th') or 0):.0f}"))
        elif lvl == "medium":
            w.line(self.dist_plot, t, pf["pv"] * s.PR / 100, T("dl_filtered_pv"), w.C_PV, 1.3)
            w.line(self.dist_plot, t, pf["yhat"] * s.PR / 100, T("dl_filtered_model"), "#ea580c", 2.0)
            self.dist_plot.setTitle(T("dl_view", th=f"{(r.get('Th') or 0):.0f}"))
        else:
            self.dist_plot.setTitle(T("dl_desc_none"))

    def _eval(self, segs):
        """Tabulka hodnocení modelu (úsek identifikace, případně validační) a grafy ACF / CCF reziduí."""
        s = self.s
        u_pv = s.get("u_pv") or "PV"
        heads = [""] + [nm for nm, _ in segs]
        labels = ["FIT [%]", "NRMSE [%]", T("eval_iae", u=u_pv), "R²", T("eval_white"), T("eval_ccf"), T("col_status")]
        rows = []
        for i, lab in enumerate(labels):
            row = [lab]
            for _, q in segs:
                row.append([round(q["FIT"], 1), round(q["NRMSE"], 2), q["IAE"] * s.PR / 100, round(q["R2"], 3),
                            f"{100 * q['frac_acf']:.0f} %", f"{100 * q['frac_ccf']:.0f} %", T(f"st_{q['status']}")][i])
            rows.append(row)
        w.fill(self.eval_tab, heads, rows)
        mm = segs[0][1]
        msgs = [T("eval_st_" + str(mm["status"]))]
        msgs.append(T("eval_ccf_bad") if mm["frac_ccf"] > 0.2 else (T("eval_acf_bad") if mm["frac_acf"] > 0.5
                                                                    else T("eval_res_ok")))
        if len(segs) == 1:
            msgs.append(T("eval_no_val"))
        self.eval_msg.setText("  \n".join(msgs))
        import numpy as np
        for plot, key, start in ((self.acf_plot, "acf", 1), (self.ccf_plot, "ccf", 0)):
            plot.clear()
            vals = np.asarray(mm[key])
            lags = (np.arange(len(vals)) + start) * mm["lag_step"]
            bad = np.abs(vals) > mm["bound"]
            width = mm["lag_step"] * 0.8
            plot.addItem(pg.BarGraphItem(x=lags[~bad], height=vals[~bad], width=width, brush="#1f5fa8"))
            plot.addItem(pg.BarGraphItem(x=lags[bad], height=vals[bad], width=width, brush="#dc2626"))
            for sg_ in (1, -1):
                plot.addItem(pg.InfiniteLine(pos=sg_ * mm["bound"], angle=0, pen=pg.mkPen("#94a3b8", style=Qt.DotLine)))

    # ---- validace na jiném úseku
    def _validation_page(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        self.v_from, self.v_to = w.spin(0.0, 0, 1e9, 1), w.spin(0.0, 0, 1e9, 1)
        self.v_mode = w.combo(["pred", "cl"], labels=[T("val_pred"), T("val_cl")])
        self.v_which = w.combo(["cur", "new"], labels=[T("val_cur"), T("val_new")])
        self.v_res = w.note("")
        for c in (self.v_from, self.v_to):
            c.valueChanged.connect(self._validate)
        for c in (self.v_mode, self.v_which):
            c.currentIndexChanged.connect(self._validate)
        lay.addLayout(w.hbox(QLabel(T("dk_from")), self.v_from, QLabel(T("dk_to")), self.v_to, QLabel(T("val_mode")),
                             self.v_mode, QLabel(T("val_params")), self.v_which))
        lay.addWidget(self.v_res)
        self.v_chart, self.v_plots = w.stack(2, ["PV", "MV"], T("time_s"), heights=(0.62, 0.38))
        lay.addWidget(self.v_chart, 1)
        return page

    def _validate(self, *_):
        s = self.s
        if self._busy or s.model is None or self.sub.currentIndex() != self.val_index:
            return
        t = s.t
        if self.v_to.value() <= self.v_from.value():          # výchozí: celý záznam
            self._busy = True
            for sp in (self.v_from, self.v_to):
                sp.setRange(0, float(t[-1]))
            self.v_from.setValue(0.0)
            self.v_to.setValue(float(t[-1]))
            self._busy = False
        rv = (self.v_from.value(), self.v_to.value())
        sv, tv = mdl.segment(t, rv)
        for p in self.v_plots:
            p.clear()
        if len(tv) < 20:
            self.v_res.setText(T("err_short"))
            return
        code, p, pdl = s.model
        r = s.fit["res"][code]
        stic = r.get("stic", 0.0) or 0.0
        g = s.grid
        tt = t[sv]
        w.line(self.v_plots[0], tt, g.pv_e[sv], T("measured"), w.C_PV, 1.2)
        w.line(self.v_plots[1], tt, g.mv_e[sv], f"MV {T('measured')}", w.C_MV, 1.4)
        if self.v_mode.currentData() == "pred":
            from ...core import predict
            yv, fv = predict(code, p, pdl, tv, s.pv[sv], s.mv[sv], [d[sv] for d in g.dists], g.Ts, stic)
            w.line(self.v_plots[0], tt, s.EP(yv), T("prediction"), "#ea580c", 2.0)
            same = mdl.overlap(rv, s.rng) > 0.5
            if not same and sv.sum() > 50:            # hodnocení i na validačním úseku (jako ve webu)
                ev_v = mdl.evaluate(code, p, pdl, stic, r.get("level", "none"), r.get("Th"), tv, s.pv[sv], s.mv[sv],
                                    [d[sv] for d in g.dists], g.Ts)
                self._eval([(T("eval_id"), s.evaluate()["metrics"]), (T("eval_val"), ev_v["metrics"])])
            s.val_status = 1 if same else (0 if fv >= 70 else 2)
            self.v_res.setText(f"**{T('fit_pred')}: {fv:.1f} %**" + ("  \n" + T("dk_val_same") if same else ""))
            return
        if not g.has_sp:
            self.v_res.setText(T("need_sp"))
            return
        which = self.v_which.currentData()
        ctrl = dict(s.set_ctrl(1 if which == "cur" else 2), Stic=stic)
        vr = mdl.validate_cl(code, p, pdl, ctrl, tv, s.sp[sv], s.pv[sv], s.mv[sv], [d[sv] for d in g.dists], g.Ts,
                             float(s.get("samp")))
        if not vr["stable"]:
            self.v_res.setText(T("err_sim_unstable", n=T("val_" + which)))
            return
        if which == "cur":
            s.val_status = 0 if vr["fit_pv"] >= 60 else 2
        col = w.C_SET2 if which == "new" else w.C_SET1
        w.line(self.v_plots[0], tt, g.sp_e[sv], "SP", w.C_SP, 1.2, dash=True)
        w.line(self.v_plots[0], tt[0] + vr["t"], s.EP(vr["PV"]), T("simulated"), col, 2.0)
        w.line(self.v_plots[1], tt[0] + vr["t"], s.EM(vr["MV"]), f"MV {T('simulated')}", col, 1.8)
        self.v_res.setText(f"**{T('fit_pv')}: {vr['fit_pv']:.1f} %** · {T('fit_mv')}: {vr['fit_mv']:.1f} %  \n"
                           + T("val_cl_help") if which == "cur" else T("val_cl_help"))

    # ---- úseky podle vstupů a vyřazení dat
    def _fill_wins(self):
        s = self.s
        self._busy = True
        try:
            ins = wn.inputs(s.c_d)
            self.win_in.clear()
            for x in ins:
                self.win_in.addItem(x, x)
            rows = [(x, a, b) for x, ws_ in s.wins_s.items() for a, b in ws_]
            self.win_tab.setRowCount(len(rows))
            self.win_tab.setHorizontalHeaderLabels([T("dk_win_input"), T("dk_from"), T("dk_to")])
            for i, (x, a, b) in enumerate(rows):
                it = QTableWidgetItem(x)
                it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                it.setForeground(pg.mkColor(WIN_COLORS[ins.index(x) % len(WIN_COLORS)]))
                self.win_tab.setItem(i, 0, it)
                for jj, v in ((1, a), (2, b)):
                    self.win_tab.setItem(i, jj, QTableWidgetItem(f"{v:.6g}"))
        finally:
            self._busy = False

    def _wins_from_table(self):
        out = {}
        for i in range(self.win_tab.rowCount()):
            x = self.win_tab.item(i, 0).text()
            try:
                a = float(self.win_tab.item(i, 1).text().replace(",", "."))
                b = float(self.win_tab.item(i, 2).text().replace(",", "."))
            except (ValueError, AttributeError):
                continue
            out.setdefault(x, []).append([a, b])
        return out

    def _win_edited(self, *_):
        if self._busy:
            return
        s = self.s
        t_end = float(s.t[-1])
        W = {x: [] for x in wn.inputs(s.c_d)}
        for x, ws_ in self._wins_from_table().items():
            W[x] = [[max(0.0, min(a, b)), min(t_end, max(a, b))] for a, b in ws_ if abs(b - a) > 0]
        s.wins = W
        self.win.refresh()

    def _win_moved(self, inp, i, reg):
        if self._busy:
            return
        a, b = reg.getRegion()
        s = self.s
        W = s.wins_s
        if i < len(W.get(inp, [])):
            W[inp][i] = [max(0.0, float(a)), min(float(s.t[-1]), float(b))]
            s.wins = W
            self.win.refresh()

    def _win_add(self):
        s = self.s
        inp = self.win_in.currentData()
        if not inp:
            return
        W = s.wins_s
        t_end = float(s.t[-1])
        a = 0.4 * t_end if not W.get(inp) else min(max(b for _, b in W[inp]), 0.8 * t_end)
        W.setdefault(inp, []).append([a, min(t_end, a + 0.2 * t_end)])
        s.wins = W
        self.win.refresh()

    def _win_del(self):
        rows = sorted({i.row() for i in self.win_tab.selectedIndexes()}, reverse=True)
        if not rows:
            return
        self._busy = True
        for r_ in rows:
            self.win_tab.removeRow(r_)
        self._busy = False
        self._win_edited()

    def _fill_excl(self):
        s = self.s
        if not s.inputs_mode:
            return
        self._busy = True
        try:
            rows = s.excl_rows()
            self.excl_tab.setRowCount(len(rows))
            self.excl_tab.setHorizontalHeaderLabels(["", T("excl_on"), "Min", "Max"])
            for i, (nm, on, lo, hi, _) in enumerate(rows):
                it = QTableWidgetItem(nm)
                it.setFlags(Qt.ItemIsEnabled)
                self.excl_tab.setItem(i, 0, it)
                c = QTableWidgetItem()
                c.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
                c.setCheckState(Qt.Checked if on else Qt.Unchecked)
                self.excl_tab.setItem(i, 1, c)
                self.excl_tab.setItem(i, 2, QTableWidgetItem(f"{lo:.6g}"))
                self.excl_tab.setItem(i, 3, QTableWidgetItem(f"{hi:.6g}"))
            v = s.valid
            from ...app.timefmt import dur
            self.excl_note.setText(T("excl_count", d=dur(float((~v).sum() * s.grid.Ts)), p=f"{100 * (~v).mean():.1f}"))
        finally:
            self._busy = False

    def _excl_edited(self, *_):
        if self._busy:
            return
        s = self.s
        out = {}
        for i in range(self.excl_tab.rowCount()):
            nm = self.excl_tab.item(i, 0).text()
            try:
                lo = float(self.excl_tab.item(i, 2).text().replace(",", "."))
                hi = float(self.excl_tab.item(i, 3).text().replace(",", "."))
            except (ValueError, AttributeError):
                continue
            out[nm] = [self.excl_tab.item(i, 1).checkState() == Qt.Checked, lo, hi]
        s.excl = out
        self.win.refresh()

    def _excl_tol_changed(self, v):
        if not self._busy:
            self.s.excl_tol = float(v)
            self.win.refresh()

    def _wmode_changed(self, *_):
        if self._busy:
            return
        self.s.set(win_mode=self.wmode.currentData())
        self.win.refresh()

    # ---- porovnání: odhad po úsecích, struktury poruch, křížové ověření
    def _windows_page(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.addWidget(QLabel("<b>" + T("ms_win_tab") + "</b>"))
        self.wchk_tab = w.table([], [])
        self.wchk_tab.setMinimumHeight(90)
        lay.addWidget(self.wchk_tab)
        lay.addWidget(QLabel("<b>" + T("ms_cmp") + "</b>"))
        lay.addWidget(caption(T("ms_cmp_dv_note")))
        self.dcmp_tab = w.table([], [])
        self.dcmp_tab.setMinimumHeight(110)
        lay.addWidget(self.dcmp_tab)
        self.b_cv = QPushButton(T("cv_run"))
        w.tip(self.b_cv, "h_cv")
        self.b_cv.clicked.connect(self._cross_validate)
        self.cv_tab = w.table([], [])
        self.cv_tab.setMaximumHeight(140)
        lay.addLayout(w.hbox(self.b_cv))
        lay.addWidget(self.cv_tab)
        lay.addWidget(caption(T("cv_help")))
        return page

    def _fill_windows_page(self):
        s = self.s
        m = s.model
        if m is None:
            for t_ in (self.wchk_tab, self.dcmp_tab, self.cv_tab):
                w.fill(t_, [""], [])
            self.b_cv.setEnabled(False)
            return
        code = m[0]
        r = s.fit["res"][code]
        chk = r.get("dv_chk") or {}
        rows = []
        pname = MODELS[code]["params"][0]
        for a, b, k, f in chk.get("mv") or []:
            rows.append(["MV", f"{a:.0f} – {b:.0f} s", f"{pname} {w.fmt(k)}", None if f is None else round(f, 1)])
        win_ = chk.get("win") or {}
        for j, dn in enumerate(s.c_d):
            for a, b, k, f in win_.get(j, win_.get(str(j), [])) or []:
                rows.append([str(dn), f"{a:.0f} – {b:.0f} s", f"Kd {w.fmt(k)}", None if f is None else round(f, 1)])
        w.fill(self.wchk_tab, [T("dk_win_input"), T("ms_win"), T("ms_cmp_par"), "FIT [%]"],
               rows or [[T("ms_dv_chk_none"), "", "", ""]])
        rows = []
        for j, dn in enumerate(s.c_d):
            for st_, f, pd_ in wn.cmp_of(r, j):
                par = T(pd_) if f is None else " · ".join(f"{n} {w.fmt(pd_z(pd_)[i])}" for n, i in DIST_FIELDS[st_])
                rows.append([str(dn), T("model_" + st_), None if f is None else round(f, 1), par])
        w.fill(self.dcmp_tab, [T("dk_win_input"), T("ms_cmp_type"), "FIT [%]", T("ms_cmp_par")], rows)
        self.b_cv.setEnabled(s.inputs_mode and r.get("method") == "win" and len(s.win_idx) >= 2)
        cv = s.cv if (s.cv and s.cv.get("key") == s.fit_key()) else None
        w.fill(self.cv_tab, [T("col_model"), T("ms_cmp_cv")],
               [[T("model_" + c), " · ".join(f"{x:.1f}" for x in v) or "—"] for c, v in (cv or {}).get("res", {}).items()])

    def _cross_validate(self):
        s = self.s
        self.b_cv.setEnabled(False)
        self.win.status(T("fitting"))

        def done(_):
            self.win.status("")
            self._fill_windows_page()
        w.run_task(lambda prog: s.cross_validate(progress=lambda i, c: prog(i, c)), done,
                   lambda e: (self.b_cv.setEnabled(True), self.win.error(T(e))))

    def _refit(self):
        s = self.s
        if s.model is None:
            return
        code = s.model[0]
        fixed = s.fixed_from_settings(code)
        self.b_refit.setEnabled(False)
        self.win.status(T("fitting"))

        def done(_):
            self.b_refit.setEnabled(True)
            self.win.status(T("refit_done", n=len(fixed)))
            self.win.refresh()
        w.run_task(lambda _p: s.refit(code, fixed), done,
                   lambda e: (self.b_refit.setEnabled(True), self.win.error(f"{T('model_' + code)}: {T(e)}")))

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

    def _mode_changed(self, *_):
        if self._busy:
            return
        self.s.set(id_mode=self.mode.currentData())
        self._mode_note()

    def _mode_note(self):
        s = self.s
        self.b_est.setVisible(self.mode.currentData() == "cl" and s.has_data and s.grid.has_sp)
        if self.mode.currentData() != "cl":
            self.mode_note.setText(T("idm_open_note"))
            return
        if not s.grid.has_sp:
            self.mode_note.setText("⚠️ " + T("idm_need_sp"))
            return
        from ...app import closedloop as cl
        ex = cl.excitation(s.sp[s.sel_mask], s.pv[s.sel_mask], s.mv[s.sel_mask])
        g = [float(s.get(f"set1_{k}")) for k in ("gain", "ti", "td")]
        lines = [T("idm_cl_note", g=f"{g[0]:.4g}", ti=f"{g[1]:.4g}", td=f"{g[2]:.4g}")]
        if not ex["ok"]:
            lines.append("⚠️ " + T("idm_low_exc"))
        if s.model is not None:              # sedí Set 1 s regulátorem v záznamu? (simulace smyčky s modelem)
            code, p, pdl = s.model
            ts, pv, mv, d = s.segment()
            chk = cl.check_set1(code, p, pdl, ts, s.sp[s.sel_mask], pv, mv, d, s.grid.Ts, s.set_ctrl_plain(1))
            if not chk["ok"]:
                lines.append("⚠️ " + (T("idm_set1_bad", f=f"{chk['fit_pv']:.0f}") if chk["stable"]
                                      else T("idm_set1_unstable")))
            else:
                lines.append("✅ " + T("idm_set1_ok", f=f"{chk['fit_pv']:.0f}"))
        if getattr(self, "_est_msg", ""):
            lines.append(self._est_msg)
        self.mode_note.setText("  \n".join(lines))

    def _estimate_set1(self):
        """Set 1 = parametry PI regulátoru odhadnuté ze záznamu (úsek identifikace)."""
        s = self.s
        if not s.has_data or not s.grid.has_sp:
            return
        from ...app import closedloop as cl
        m = s.sel_mask
        est = cl.estimate_ctrl(s.sp[m], s.pv[m], s.mv[m], s.grid.Ts)
        if not est["ok"]:
            self._est_msg = "⚠️ " + T("idm_est_fail")
        else:
            s.set(set1_gain=est["gain"], set1_ti=est["ti"] if np.isfinite(est["ti"]) else 1e9, set1_td=0.0)
            self._est_msg = "ℹ️ " + T("idm_est_done", g=f"{est['gain']:.4g}", ti=f"{est['ti']:.4g}",
                                      r=f"{est['r2']:.2f}")
        self.win.refresh()
        self._mode_note()

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
        self.prog.setRange(0, len(s.get("chosen")) * (2 if (s.id_closed and not s.inputs_mode) else 1))
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
        if item.column() == 1:                   # zaškrtnutí „zafixovat“
            self.s.settings[item.data(Qt.UserRole)] = item.checkState() == Qt.Checked
            return
        try:
            v = float(item.text().replace(",", "."))
        except ValueError:
            self._fill_params()
            return
        key = item.data(Qt.UserRole)
        if not key:
            return
        self.s.settings[key] = v
        self.win.refresh()

    def _reset(self):
        if self.s.model is not None:
            self.s.reset_edits(self.s.model[0])
            self.win.refresh()
