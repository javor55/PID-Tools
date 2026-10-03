"""
Záložka Přehled smyček: více smyček z jednoho souboru. Vpravo tabulka smyček (PV / MV / SP / poloha – návrh
z názvů tagů, uživatel jen opraví), vlevo pořadí smyček podle problémů, společné oscilace a graf vybrané smyčky.
Výpočty v pidtools.app.audit; definice smyček se ukládají do projektu (audit_loops).
"""
from PySide6.QtWidgets import QCheckBox, QLabel, QLineEdit, QListWidget, QPushButton, QTableWidget

from ...app import audit
from ...i18n import T
from .. import widgets as w
from ..layout import Workspace, caption

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
        self.top_bar(b_run)
        self.status = caption("")
        self.top.addWidget(self.status)
        # ---- smyčky: seznam a pod ním nastavení vybrané smyčky (pole pod sebou – do panelu se vejdou)
        self.recs = []
        self.list = QListWidget()
        self.list.setMinimumHeight(90)
        self.list.setMaximumHeight(180)
        self.list.currentRowChanged.connect(self._load_form)
        sec = self.section(T("au_sec_loops"), caption(T("au_loops_help")), "loops", expanded=True)
        sec.add(self.list)
        b_add, b_del, b_prop = QPushButton(T("au_add")), QPushButton(T("au_del")), QPushButton(T("au_propose"))
        b_add.clicked.connect(self._add)
        b_del.clicked.connect(self._delete)
        b_prop.clicked.connect(self.propose)
        sec.add(w.hbox(b_add, b_del, b_prop))
        self.f_name = QLineEdit()
        self.f_pv, self.f_mv, self.f_sp, self.f_pos = w.combo([]), w.combo([]), w.combo([]), w.combo([])
        self.f_theta = w.spin(0.0, 0.0, 1e9, 4)
        w.tip(self.f_theta, "au_theta_help")
        self.f_integ = QCheckBox(T("au_c_integ"))
        self.form = w.form([(T("au_c_name"), self.f_name), (T("au_c_pv"), self.f_pv), (T("au_c_mv"), self.f_mv),
                            (T("au_c_sp"), self.f_sp), (T("au_c_pos"), self.f_pos), (T("au_c_theta"), self.f_theta),
                            ("", self.f_integ)])
        sec.add(self.form)
        b_open = QPushButton(T("au_open_loop"))
        b_open.clicked.connect(self.open_as_loop)
        w.tip(b_open, "au_open_help")
        sec.add(b_open)
        self.f_name.editingFinished.connect(self._store)
        for c in (self.f_pv, self.f_mv, self.f_sp, self.f_pos):
            c.currentIndexChanged.connect(self._store)
        self.f_theta.valueChanged.connect(self._store)
        self.f_integ.toggled.connect(self._store)
        self._busy = False
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

    # ---- seznam smyček
    def _sigs(self):
        s = self.s
        return list(s.sig.sigs) if s.has_data else []

    def _fill(self, loops):
        self.recs = audit.to_records(loops)
        self._fill_list(0)

    def _fill_list(self, cur=0):
        self._busy = True
        self.list.clear()
        for r in self.recs:
            self.list.addItem(str(r["name"] or r["pv"]))
        sigs = self._sigs()
        for c, opt in ((self.f_pv, False), (self.f_mv, False), (self.f_sp, True), (self.f_pos, True)):
            c.clear()
            for it in (["—"] if opt else []) + sigs:
                c.addItem(str(it), it)
        self._busy = False
        if self.recs:
            self.list.setCurrentRow(min(max(cur, 0), len(self.recs) - 1))
            self._load_form(self.list.currentRow())

    def _load_form(self, i):
        if self._busy or not (0 <= i < len(self.recs)):
            return
        r = self.recs[i]
        self._busy = True
        self.f_name.setText(str(r["name"] or ""))
        for c, v in ((self.f_pv, r["pv"]), (self.f_mv, r["mv"]), (self.f_sp, r["sp"] or "—"), (self.f_pos, r["pos"] or "—")):
            c.setCurrentIndex(max(c.findData(v), 0))
        self.f_theta.setValue(float(r["theta"] or 0.0))
        self.f_integ.setChecked(bool(r["integ"]))
        self._busy = False

    def _store(self, *_):
        i = self.list.currentRow()
        if self._busy or not (0 <= i < len(self.recs)):
            return
        sp, pos = self.f_sp.currentData(), self.f_pos.currentData()
        self.recs[i].update(name=self.f_name.text().strip(), pv=self.f_pv.currentData(), mv=self.f_mv.currentData(),
                            sp=None if sp in (None, "—") else sp, pos=None if pos in (None, "—") else pos,
                            theta=self.f_theta.value() or None, integ=self.f_integ.isChecked())
        self.list.item(i).setText(str(self.recs[i]["name"] or self.recs[i]["pv"]))

    def _add(self):
        sigs = self._sigs()
        if not sigs:
            return
        self.recs.append(dict(name=f"{T('au_c_name')} {len(self.recs) + 1}", pv=sigs[0], mv=sigs[min(1, len(sigs) - 1)],
                              sp=None, pos=None, theta=None, integ=False))
        self._fill_list(len(self.recs) - 1)

    def _delete(self):
        i = self.list.currentRow()
        if 0 <= i < len(self.recs):
            self.recs.pop(i)
            self._fill_list(i - 1)

    def loops(self):
        return audit.from_records(self.recs, self._sigs())

    def propose(self):
        s = self.s
        if not s.has_data:
            return
        self._fill(audit.propose(s.sig.sigs, s.sig.get))

    def refresh(self):
        s = self.s
        if not s.has_data:
            return
        if not self.recs:
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
        i = self.list.currentRow()
        if not (0 <= i < len(self.recs)):
            return
        d = next(iter(audit.from_records([self.recs[i]], self._sigs())), None)
        if d is None:
            return
        self.win.project.add_loop_with(d.name, d.pv, d.mv, d.sp, d.pos)
        self.win.build()
        self.win.tabs.setCurrentIndex(1)
