"""
Dialog OPC UA (jen čtení): připojení k serveru, procházení adresního prostoru a hledání tagů, výběr proměnných,
načtení historie (HistoryRead) nebo záznam živých hodnot → data projektu. Do serveru se nic nezapisuje.
"""
import datetime as dt

from PySide6.QtCore import QDateTime, Qt
from PySide6.QtWidgets import (QDateTimeEdit, QDialog, QDialogButtonBox, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QProgressBar, QPushButton, QSplitter, QTreeWidget, QTreeWidgetItem,
                               QVBoxLayout, QWidget)

from ..app import opc
from ..i18n import T
from . import widgets as w

ROLE_ID, ROLE_PATH, ROLE_VAR, ROLE_LOADED = Qt.UserRole, Qt.UserRole + 1, Qt.UserRole + 2, Qt.UserRole + 3


class OpcDialog(QDialog):
    def __init__(self, win):
        super().__init__(win)
        self.win, self.conn, self.df = win, None, None
        self.setWindowTitle(T("opc_title"))
        self.resize(1000, 680)
        lay = QVBoxLayout(self)
        lay.addWidget(w.note(T("opc_intro")))
        p = win.prefs
        self.url = QLineEdit(p.value("opc_url", "opc.tcp://localhost:4840"))
        self.user, self.pw = QLineEdit(p.value("opc_user", "")), QLineEdit()
        self.pw.setEchoMode(QLineEdit.Password)
        self.sec = QLineEdit(p.value("opc_sec", ""))
        self.sec.setPlaceholderText("Basic256Sha256,SignAndEncrypt,cert.pem,key.pem")
        w.tip(self.sec, "h_opc_sec")
        b_conn = QPushButton(T("opc_connect"))
        b_conn.clicked.connect(self.connect)
        self.state = QLabel("")
        lay.addLayout(w.form([(T("opc_url"), self.url), (T("opc_user"), w.hbox(self.user, QLabel(T("opc_pw")), self.pw)),
                              (T("opc_sec"), self.sec), ("", w.hbox(b_conn, self.state))]))
        split = QSplitter(Qt.Horizontal)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        self.search = QLineEdit()
        self.search.setPlaceholderText(T("opc_search_ph"))
        b_find = QPushButton(T("opc_find"))
        b_find.clicked.connect(self.find)
        self.search.returnPressed.connect(self.find)
        ll.addLayout(w.hbox(self.search, b_find, stretch=False))
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([T("opc_node"), "NodeId"])
        self.tree.itemExpanded.connect(self._expand)
        self.tree.itemDoubleClicked.connect(self._pick_item)
        ll.addWidget(self.tree, 1)
        split.addWidget(left)
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(QLabel(T("opc_selected")))
        self.sel = QListWidget()
        rl.addWidget(self.sel, 1)
        b_add, b_rm = QPushButton("→ " + T("opc_add")), QPushButton(T("opc_remove"))
        b_add.clicked.connect(lambda: [self._pick_item(i) for i in self.tree.selectedItems()])
        b_rm.clicked.connect(lambda: [self.sel.takeItem(self.sel.row(i)) for i in self.sel.selectedItems()])
        rl.addLayout(w.hbox(b_add, b_rm))
        self.tree.setSelectionMode(QTreeWidget.ExtendedSelection)
        self.sel.setSelectionMode(QListWidget.ExtendedSelection)
        split.addWidget(right)
        split.setSizes([600, 380])
        lay.addWidget(split, 1)
        now = QDateTime.currentDateTime()
        self.t_from, self.t_to = QDateTimeEdit(now.addSecs(-8 * 3600)), QDateTimeEdit(now)
        for e in (self.t_from, self.t_to):
            e.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
            e.setCalendarPopup(True)
        b_hist = QPushButton(T("opc_history"))
        b_hist.clicked.connect(self.read_history)
        self.period, self.dur = w.spin(1.0, 0.05, 3600, 3), w.spin(10.0, 0.1, 1440, 2)
        b_rec = QPushButton(T("opc_record"))
        b_rec.clicked.connect(self.record)
        self.b_stop = QPushButton(T("opc_stop"))
        self.b_stop.setEnabled(False)
        self.b_stop.clicked.connect(lambda: setattr(self, "_stop", True))
        lay.addLayout(w.hbox(QLabel(T("dk_from")), self.t_from, QLabel(T("dk_to")), self.t_to, b_hist))
        lay.addLayout(w.hbox(QLabel(T("opc_period")), self.period, QLabel(T("opc_duration")), self.dur, b_rec,
                             self.b_stop))
        self.prog = QProgressBar()
        self.prog.setVisible(False)
        self.info = QLabel("")
        lay.addLayout(w.hbox(self.prog, self.info))
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self._stop = False

    # ---- připojení a procházení
    def connect(self):
        if self.conn is not None:
            self.conn.close()
            self.conn = None
        try:
            self.conn = opc.Connection(self.url.text().strip(), self.user.text().strip() or None, self.pw.text(),
                                       security=self.sec.text().strip() or None)
            self.conn.connect()
        except Exception as ex:
            self.conn = None
            self.state.setText("⛔ " + T("opc_failed", e=str(ex)))
            return
        p = self.win.prefs
        p.setValue("opc_url", self.url.text().strip())
        p.setValue("opc_user", self.user.text().strip())
        p.setValue("opc_sec", self.sec.text().strip())
        self.state.setText("✅ " + T("opc_connected"))
        self.tree.clear()
        self._fill(self.tree.invisibleRootItem(), None, "")

    def _fill(self, parent, node_id, path):
        for it in self.conn.children(node_id, path):
            item = QTreeWidgetItem([("📈 " if it.is_var else "📁 ") + it.name, it.node_id])
            item.setData(0, ROLE_ID, it.node_id)
            item.setData(0, ROLE_PATH, it.path)
            item.setData(0, ROLE_VAR, it.is_var)
            if not it.is_var:
                item.setChildIndicatorPolicy(QTreeWidgetItem.ShowIndicator)
            parent.addChild(item)

    def _expand(self, item):
        if item.data(0, ROLE_LOADED) or self.conn is None:
            return
        item.setData(0, ROLE_LOADED, True)
        try:
            self._fill(item, item.data(0, ROLE_ID), item.data(0, ROLE_PATH))
        except Exception as ex:
            self.state.setText("⚠️ " + str(ex))

    def find(self):
        if self.conn is None:
            return
        self.tree.clear()
        for it in self.conn.find(self.search.text().strip()):
            item = QTreeWidgetItem(["📈 " + it.path, it.node_id])
            item.setData(0, ROLE_ID, it.node_id)
            item.setData(0, ROLE_PATH, it.path)
            item.setData(0, ROLE_VAR, True)
            self.tree.addTopLevelItem(item)

    def _pick_item(self, item, *_):
        if not item.data(0, ROLE_VAR):
            return
        nid = item.data(0, ROLE_ID)
        if any(self.sel.item(i).data(ROLE_ID) == nid for i in range(self.sel.count())):
            return
        li = QListWidgetItem(item.data(0, ROLE_PATH))
        li.setData(ROLE_ID, nid)
        self.sel.addItem(li)

    def selected(self):
        return {self.sel.item(i).data(ROLE_ID): self.sel.item(i).text() for i in range(self.sel.count())}

    # ---- čtení
    def _busy(self, on):
        self.prog.setVisible(on)
        self.b_stop.setEnabled(on)

    def read_history(self):
        names = self.selected()
        if self.conn is None or not names:
            return
        a = self.t_from.dateTime().toPython().astimezone(dt.timezone.utc)
        b = self.t_to.dateTime().toPython().astimezone(dt.timezone.utc)
        self._busy(True)
        self.prog.setRange(0, len(names))
        conn = self.conn
        w.run_task(lambda prog: conn.history(list(names), a, b, lambda i, n: prog(i, n)),
                   lambda h: self._loaded(h, names), self._failed,
                   lambda f, txt: (self.prog.setValue(int(f)), self.info.setText(txt)))

    def record(self):
        names = self.selected()
        if self.conn is None or not names:
            return
        self._stop = False
        self._busy(True)
        self.prog.setRange(0, 100)
        conn, per, dur = self.conn, self.period.value(), self.dur.value() * 60
        w.run_task(lambda prog: conn.record(list(names), per, dur, lambda f, k: prog(100 * f, str(k)),
                                            lambda: self._stop),
                   lambda h: self._loaded(h, names), self._failed,
                   lambda f, txt: (self.prog.setValue(int(f)), self.info.setText(T("opc_samples", n=txt))))

    def _failed(self, e):
        self._busy(False)
        self.info.setText("⛔ " + str(e))

    def _loaded(self, series, names):
        self._busy(False)
        df = opc.to_frame(series, names)
        empty = [names[n] for n, (ts, _) in series.items() if not ts]
        if df.empty:
            self.info.setText("⚠️ " + T("opc_empty"))
            return
        self.df = df
        if empty:
            self.win.error(T("opc_some_empty", t=", ".join(empty)))
        self.accept()

    def done(self, r):
        if self.conn is not None:
            self.conn.close()
            self.conn = None
        super().done(r)
