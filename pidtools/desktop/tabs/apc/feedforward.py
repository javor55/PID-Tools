"""APC › Dopředná vazba: nastavení pro každou měřenou poruchu, ověření skokem poruchy, hodnoty pro PIDConL (FFwd)."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHeaderView, QLabel, QTableWidget, QTableWidgetItem

from ....app import feedforward as ffm
from ....app.apc import feedforward as aff
from ....i18n import T
from ... import widgets as w
from .common import Panel

COLS = ("use", "dyn", "gain", "lead", "lag", "delay")


class FFPanel(Panel):
    def __init__(self, win):
        super().__init__(win, "apc_intro_ff")
        self.tab = QTableWidget(len(COLS), 0)          # parametry pod sebou, sloupec = měřená porucha
        self.tab.itemChanged.connect(self._edited)
        self.left.addWidget(w.group(T("dk_ff_setup"), w.form([("", self.tab)])))
        self.jsel = w.combo([])
        self.step = w.spin(1.0, -1e12, 1e12, 4)
        self.jsel.currentIndexChanged.connect(self._default_step)
        self.step.valueChanged.connect(self._simulate)
        self.left.addWidget(w.group(T("ff_sim_title"), w.form([(T("ff_sim_dist"), self.jsel), (T("dk_ff_step"), self.step)])))
        self.vals = w.note("")
        self.left.addWidget(w.group(T("ff_tab_title"), w.form([("", self.vals)])))
        self.left.addStretch(1)
        self.plots = self.chart()
        self.kpi = self.table(110)
        self.right.addWidget(QLabel(T("ff_sim_help")))

    def _design(self):
        code, p, pdl = self.s.model
        return ffm.design(code, p, pdl, self.s.ff_state)

    def refresh(self):
        s = self.s
        if s.model is None or not s.model[2]:
            self.tab.setColumnCount(0)
            self.vals.setText(T("ff_need_dist"))
            return
        des = self._design()
        self._busy = True
        try:
            self.tab.setColumnCount(len(des))
            self.tab.setVerticalHeaderLabels([T("ff_col_" + c) for c in COLS])
            self.tab.setHorizontalHeaderLabels([str(x) for x in s.c_d])
            self.tab.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            for i, d in enumerate(des):
                for j, c in enumerate(COLS):
                    it = QTableWidgetItem()
                    if c in ("use", "dyn"):
                        it.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
                        it.setCheckState(Qt.Checked if d[c] else Qt.Unchecked)
                    else:
                        it.setText(f"{d[c]:.5g}")
                    self.tab.setItem(j, i, it)
            self.tab.setFixedHeight(self.tab.horizontalHeader().height() + 4
                                    + sum(self.tab.rowHeight(r) for r in range(len(COLS))))
            cur = self.jsel.currentIndex()
            self.jsel.clear()
            for i, dn in enumerate(s.c_d):
                self.jsel.addItem(str(dn), i)
            self.jsel.setCurrentIndex(max(cur, 0))
        finally:
            self._busy = False
        self._default_step()

    def _edited(self, *_):
        if self._busy:
            return
        des = self._design()
        for i, d in enumerate(des):
            for j, c in enumerate(COLS):
                it = self.tab.item(j, i)
                if it is None:
                    continue
                if c in ("use", "dyn"):
                    d[c] = it.checkState() == Qt.Checked
                else:
                    try:
                        d[c] = float(it.text().replace(",", "."))
                    except ValueError:
                        pass
        self.s.ff_state = ffm.state(des)
        self._simulate()

    def _default_step(self, *_):
        s = self.s
        if self._busy or s.model is None or not s.model[2] or self.jsel.currentData() is None:
            return
        dd = s.grid.dists[self.jsel.currentData()]
        span = float(dd.max() - dd.min()) if len(dd) else 1.0
        self._busy = True
        self.step.setValue(float(f"{(span / 2 or 1.0):.3g}"))
        self._busy = False
        self._simulate()

    def _simulate(self, *_):
        s = self.s
        if self._busy or s.model is None or not s.model[2] or self.jsel.currentData() is None:
            return
        code, p, pdl = s.model
        des = self._design()
        t, outs = aff.simulate(code, p, pdl, s.set_ctrl(2), des, self.jsel.currentData(), self.step.value(),
                               float(s.get("samp")))
        kp = aff.sim_kpis(t, outs, s.PR)
        for pl in self.plots:
            pl.clear()
        rows = []
        for key, col, dash in (("none", "#9aa5b1", True), ("static", w.C_SET1, True), ("dynamic", w.C_SET2, False)):
            o = outs[key]
            w.line(self.plots[0], t, s.EP(o["PV"]), T("ff_" + key), col, 1.8, dash)
            w.line(self.plots[1], t, s.EM(o["MV"]), T("ff_" + key), col, 1.5, dash)
            rows.append([T("ff_" + key), kp[key]["iae"], kp[key]["maxdev"]])
        w.fill(self.kpi, [T("setting"), T("iae_load"), T("ff_maxdev")], rows)
        tab = aff.rows(s.c_d, s.grid.dists, des, s.MR, s.get("u_mv") or "MV")
        self.vals.setText("  \n".join(f"**{dn}**  \n" + "  \n".join(f"{a} = {w.fmt(v)} {u}" for a, v, u in r)
                                      for dn, r in tab) or T("ff_none_on"))
