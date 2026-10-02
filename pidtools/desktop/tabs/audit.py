"""
Záložka Přehled smyček: více smyček z jednoho souboru. Vpravo tabulka smyček (PV / MV / SP / poloha – návrh
z názvů tagů, uživatel jen opraví), vlevo pořadí smyček podle problémů, společné oscilace a graf vybrané smyčky.
Výpočty v pidtools.app.audit; definice smyček se ukládají do projektu (audit_loops).
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QLabel, QPushButton, QTableWidget, QTableWidgetItem

from ...app import audit
from ...i18n import T
from .. import widgets as w
from ..layout import Workspace, caption

COLS = ("name", "pv", "mv", "sp", "pos", "theta", "integ")


class AuditTab(Workspace):
    def __init__(self, win):
        super().__init__("audit", side_width=460)
        self.win, self.s = win, win.state
        self.res = []
        # ---- hlavní plocha
        self.rank = w.table([], [])
        self.rank.setSelectionBehavior(QTableWidget.SelectRows)
        self.rank.setSelectionMode(QTableWidget.SingleSelection)
        self.rank.itemSelectionChanged.connect(self._show_loop)
        self.rank.setMinimumHeight(180)
        self.main.addWidget(self.rank, 2)
        self.common = w.note("")
        self.main.addWidget(self.common)
        self.chart, self.plots = w.stack(2, ["PV", "MV"], T("time_s"), heights=(0.6, 0.4))
        self.main.addWidget(self.chart, 3)
        # ---- pevný pruh
        b_run = QPushButton("▶  " + T("au_run"))
        b_run.setObjectName("primary")
        b_run.clicked.connect(self.analyse)
        b_prop = QPushButton(T("au_propose"))
        b_prop.clicked.connect(self.propose)
        self.top_bar(b_run, b_prop)
        self.status = caption("")
        self.top.addWidget(self.status)
        # ---- smyčky
        self.tab = QTableWidget(0, len(COLS))
        self.tab.setHorizontalHeaderLabels([T("au_c_" + c) for c in COLS])
        self.tab.setMinimumHeight(260)
        sec = self.section(T("au_sec_loops"), caption(T("au_loops_help")), "loops")
        sec.add(self.tab)
        b_add, b_del, b_open = QPushButton("+"), QPushButton("−"), QPushButton(T("au_open_loop"))
        b_add.clicked.connect(lambda: self._add_row(audit.LoopDef("", "", "")))
        b_del.clicked.connect(lambda: self.tab.removeRow(self.tab.currentRow()))
        b_open.clicked.connect(self.open_as_loop)
        w.tip(b_open, "au_open_help")
        sec.add(w.hbox(b_add, b_del, b_open))
        # ---- rozsah
        self.a, self.b = w.spin(0.0, 0, 1e9, 1), w.spin(0.0, 0, 1e9, 1)
        self.whole = QCheckBox(T("au_whole"))
        self.whole.setChecked(True)
        self.whole.toggled.connect(lambda on: (self.a.setEnabled(not on), self.b.setEnabled(not on)))
        self.a.setEnabled(False)
        self.b.setEnabled(False)
        self.section(T("au_sec_window"), w.form([("", self.whole), (T("dk_from"), self.a), (T("dk_to"), self.b)]),
                     "window", expanded=False)
        sec = self.section(T("au_sec_help"), w.note(T("au_help")), "help", expanded=False)
        sec.add(QLabel(""))

    # ---- tabulka smyček
    def _sigs(self):
        s = self.s
        return list(s.sig.sigs) if s.has_data else []

    def _combo(self, value, optional):
        items = (["—"] if optional else []) + self._sigs()
        c = w.combo(items, value if value in items else ("—" if optional else None))
        return c

    def _add_row(self, d):
        i = self.tab.rowCount()
        self.tab.insertRow(i)
        self.tab.setItem(i, 0, QTableWidgetItem(d.name))
        for j, (k, opt) in enumerate((("pv", False), ("mv", False), ("sp", True), ("pos", True)), start=1):
            self.tab.setCellWidget(i, j, self._combo(getattr(d, k), opt))
        th = d.extra.get("theta")
        self.tab.setItem(i, 5, QTableWidgetItem("" if th is None else f"{th:g}"))
        it = QTableWidgetItem()
        it.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
        it.setCheckState(Qt.Checked if d.integ else Qt.Unchecked)
        self.tab.setItem(i, 6, it)

    def loops(self):
        out = []
        for i in range(self.tab.rowCount()):
            cell = [self.tab.cellWidget(i, j).currentData() for j in range(1, 5)]
            pv, mv, sp, pos = [None if v in (None, "—") else v for v in cell]
            if not pv or not mv:
                continue
            name = (self.tab.item(i, 0).text() if self.tab.item(i, 0) else "") or str(pv)
            th_t = self.tab.item(i, 5).text().replace(",", ".").strip() if self.tab.item(i, 5) else ""
            try:
                extra = {"theta": float(th_t)} if th_t else {}
            except ValueError:
                extra = {}
            integ = self.tab.item(i, 6).checkState() == Qt.Checked if self.tab.item(i, 6) else False
            out.append(audit.LoopDef(name=name, pv=pv, mv=mv, sp=sp, pos=pos, integ=integ, extra=extra))
        return out

    def _fill(self, loops):
        self.tab.setRowCount(0)
        for d in loops:
            self._add_row(d)
        self.tab.resizeColumnsToContents()

    def propose(self):
        s = self.s
        if not s.has_data:
            return
        self._fill(audit.propose(s.sig.sigs, s.sig.get))

    def refresh(self):
        s = self.s
        if not s.has_data:
            return
        if self.tab.rowCount() == 0:
            saved = audit.from_records(s.get("audit_loops"), self._sigs())
            self._fill(saved or audit.propose(s.sig.sigs, s.sig.get))
        T_ = float(s.grid.t[-1])
        self.a.setRange(0, T_)
        self.b.setRange(0, T_)
        if self.b.value() == 0:
            self.b.setValue(T_)

    # ---- výpočet
    def analyse(self):
        s = self.s
        loops = self.loops()
        if not s.has_data or not loops:
            return
        s.settings["audit_loops"] = audit.to_records(loops)
        win = None if self.whole.isChecked() else (self.a.value(), self.b.value())
        self.status.setText("⏳ " + T("dk_calculating"))
        w.run_task(lambda _p: audit.analyse(s.sig, loops, s.ts_user, win), self._done,
                   lambda e: (self.status.setText(""), self.win.error(T(e))))

    def _done(self, res):
        self.res = res
        rows = []
        for i, r in enumerate(res):
            if not r["ok"]:
                rows.append([i + 1, r["name"], "—", T(r["err"] or "err_fit_failed")] + [""] * 9)
                continue
            k = r["kpis"]
            probs = ", ".join(T("au_p_" + p) for p, _ in r["problems"]) or "✓ " + T("au_ok")
            rows.append([i + 1, r["name"], r["score"], probs, k["std_e"], k["iae_h"], k["travel_h"], k["rev_h"],
                         k["at_lim"], k["frozen"], f"{k['period']:.0f}" if k["period"] else "—",
                         T("stic_short_" + k["stic"]) if k["stic"] else "—",
                         "—" if k["harris"] is None else f"{k['harris']:.2f}"])
        w.fill(self.rank, ["#", T("au_c_name"), T("au_score"), T("au_problems"), T("au_std"), T("au_iae"),
                           T("au_travel"), T("au_rev"), T("au_lim"), T("au_frozen"), T("au_period"), T("au_stic"),
                           T("kpi_harris")], rows)
        self.rank.resizeColumnsToContents()
        groups = audit.common_oscillations(res)
        self.common.setText("  \n".join(
            "🔁 " + T("au_common", p=f"{g['period']:.0f}", l=", ".join(g["loops"]), s=g["source"])
            + (" " + T("au_common_stic") if g["by_stiction"] else "") for g in groups) or T("au_common_none"))
        self.status.setText(T("au_done", n=len(res), b=sum(1 for r in res if r["score"] > 0)))
        if res:
            self.rank.selectRow(0)

    def _show_loop(self):
        i = self.rank.currentRow()
        if not (0 <= i < len(self.res)) or not self.res[i]["ok"]:
            return
        r = self.res[i]
        self.chart.clear()
        if r["sp"] is not None:
            w.line(self.plots[0], r["t"], r["sp"], "SP", w.C_SP, 1.2, dash=True)
        w.line(self.plots[0], r["t"], r["pv"], "PV", w.C_PV, 1.3)
        w.line(self.plots[1], r["t"], r["mv"], "MV", w.C_MV, 1.4)
        self.plots[0].setTitle(r["name"])
        self.chart.full_range()

    def open_as_loop(self):
        """Vybraná smyčka se otevře jako smyčka projektu (identifikace, ladění …)."""
        i = self.tab.currentRow()
        loops = self.loops()
        names = [self.tab.item(k, 0).text() if self.tab.item(k, 0) else "" for k in range(self.tab.rowCount())]
        if not (0 <= i < self.tab.rowCount()):
            return
        d = next((x for x in loops if x.name == (names[i] or x.pv)), None)
        if d is None:
            return
        self.win.project.add_loop_with(d.name, d.pv, d.mv, d.sp, d.pos)
        self.win.build()
        self.win.tabs.setCurrentIndex(1)
