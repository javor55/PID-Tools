"""
Desktopová aplikace PID Tools (Qt): okno se záložkami Data, Model, Ladění; menu Soubor (data, ukázka, projekt,
protokol), jazyk a nápověda. Spuštění: python -m pidtools.desktop
"""
import sys
from pathlib import Path

from PySide6.QtCore import QSettings, QThreadPool
from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
                               QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit, QTabWidget)

from .. import __version__, i18n
from ..app.report import SECTIONS, STATUSES
from ..i18n import T
from .state import LoopState
from .tabs.apc import ApcTab
from .tabs.data import DataTab
from .tabs.live import LiveTab
from .tabs.model import ModelTab
from .tabs.tuning import TuningTab

ORG, APP = "PID Tools", "PID Tools desktop"


class MainWindow(QMainWindow):
    def __init__(self, state=None, prefs=None):
        super().__init__()
        self.state = state or LoopState()
        self.prefs = prefs if prefs is not None else QSettings(ORG, APP)   # jazyk, poslední složka
        i18n.set_lang(self.prefs.value("lang", self.state.get("lang", "en")))
        self.resize(1400, 900)
        self.build()

    # ---- sestavení (znovu po změně jazyka)
    def build(self):
        self.setWindowTitle(T("dk_title"))
        self.menuBar().clear()
        m = self.menuBar().addMenu(T("dk_file"))
        for key, fn, sc in (("dk_open_data", self.open_data, "Ctrl+O"), ("dk_demo", self.open_demo, None),
                            (None, None, None),
                            ("dk_open_project", self.open_project, "Ctrl+Shift+O"),
                            ("dk_save_project", self.save_project, "Ctrl+S"),
                            ("dk_export_report", self.export_report, "Ctrl+P"),
                            (None, None, None), ("dk_quit", self.close, "Ctrl+Q")):
            if key is None:
                m.addSeparator()
                continue
            a = QAction(T(key), self)
            if sc:
                a.setShortcut(sc)
            a.triggered.connect(fn)
            m.addAction(a)
        v = self.menuBar().addMenu(T("dk_view"))
        lm = v.addMenu(T("dk_lang"))
        grp = QActionGroup(self)
        for code, name in (("en", "English"), ("cs", "Čeština")):
            a = QAction(name, self, checkable=True)
            a.setChecked(i18n.lang() == code)
            a.triggered.connect(lambda _=False, c=code: self.set_lang(c))
            grp.addAction(a)
            lm.addAction(a)
        h = self.menuBar().addMenu(T("dk_help"))
        a = QAction(T("dk_about"), self)
        a.triggered.connect(lambda: QMessageBox.about(self, T("dk_about"), T("dk_about_text", v=__version__)))
        h.addAction(a)
        cur = self.tabs.currentIndex() if hasattr(self, "tabs") else 0
        self.tabs = QTabWidget()
        self.pages = [DataTab(self), ModelTab(self), TuningTab(self), LiveTab(self), ApcTab(self)]
        for p, key in zip(self.pages, ("tab1", "tab2", "tab3", "tab4_live", "tab5")):
            self.tabs.addTab(p, T(key))
        self.tabs.setCurrentIndex(cur)
        # živá simulace převezme aktuální sady, když se na ni přepne (úpravy v Ladění ji jinak nerestartují)
        self.tabs.currentChanged.connect(lambda i: self.pages[i].refresh() if isinstance(self.pages[i], (LiveTab, ApcTab))
                                         else None)
        self.setCentralWidget(self.tabs)
        self.refresh()

    def set_lang(self, code):
        i18n.set_lang(code)
        self.state.set(lang=code)
        self.prefs.setValue("lang", code)
        self.build()

    def refresh(self, skip=None):
        """Překreslí záložky ze stavu (po změně dat, sloupců, úseku, modelu, parametrů)."""
        has = self.state.has_data
        for i in range(1, self.tabs.count()):
            self.tabs.setTabEnabled(i, has)
        for p in self.pages:
            if p is not skip:
                p.refresh()

    def closeEvent(self, ev):
        QThreadPool.globalInstance().waitForDone(30000)    # dokončit výpočty na pozadí před zavřením
        super().closeEvent(ev)

    # ---- hlášení
    def status(self, text):
        self.statusBar().showMessage(text, 0 if text else 1)

    def error(self, text):
        QMessageBox.warning(self, T("dk_error"), str(text))

    def _dir(self):
        return self.prefs.value("dir", str(Path.home()))

    def _remember(self, path):
        self.prefs.setValue("dir", str(Path(path).parent))

    # ---- soubor
    def open_data(self):
        path, _ = QFileDialog.getOpenFileName(self, T("dk_open_data"), self._dir(), "Data (*.csv *.txt *.xlsx *.xls)")
        if path:
            self._remember(path)
            try:
                self.state.load_file(path)
            except Exception as ex:
                self.error(T("err_data", ex=T(str(ex))))
            self.tabs.setCurrentIndex(0)
            self.refresh()

    def open_demo(self):
        self.state.load_demo()
        self.tabs.setCurrentIndex(0)
        self.refresh()

    def open_project(self):
        path, _ = QFileDialog.getOpenFileName(self, T("dk_open_project"), self._dir(), "PID Tools (*.json)")
        if path:
            self._remember(path)
            try:
                self.state.load_project(path)
                i18n.set_lang(self.prefs.value("lang", "en"))
            except Exception as ex:
                self.error(str(ex))
            self.refresh()

    def save_project(self):
        name = (self.state.get("loop_tag") or "pidtools_project") + ".json"
        path, _ = QFileDialog.getSaveFileName(self, T("dk_save_project"), str(Path(self._dir()) / name),
                                              "PID Tools (*.json)")
        if path:
            self._remember(path)
            self.state.save_project(path, include_data=True)
            self.status(T("dk_saved", f=path))

    def export_report(self):
        if self.state.model is None:
            self.error(T("rp_no_model"))
            return
        dlg = ReportDialog(self, self.state)
        if dlg.exec() != QDialog.Accepted:
            return
        name = (self.state.get("loop_tag") or "pidtools_report") + ".html"
        path, _ = QFileDialog.getSaveFileName(self, T("dk_export_report"), str(Path(self._dir()) / name), "HTML (*.html)")
        if path:
            self._remember(path)
            html = self.state.report_html(dlg.meta(), SECTIONS, "inline")
            Path(path).write_text(html, encoding="utf-8")
            self.status(T("dk_saved", f=path))


class ReportDialog(QDialog):
    """Hlavička protokolu (zařízení, autor, stav, poznámka) – hodnoty se pamatují v projektu."""

    def __init__(self, parent, state):
        super().__init__(parent)
        self.s = state
        self.setWindowTitle(T("dk_report_meta"))
        f = QFormLayout(self)
        self.plant, self.author = QLineEdit(state.get("rep_plant", "")), QLineEdit(state.get("rep_author", ""))
        self.st = QComboBox()
        for k in STATUSES:
            self.st.addItem(T("rp_st_" + k), k)
        self.st.setCurrentIndex(max(self.st.findData(state.get("rep_status", "draft")), 0))
        self.comment = QPlainTextEdit(state.get("rep_comment", ""))
        f.addRow(T("rp_plant"), self.plant)
        f.addRow(T("rp_author"), self.author)
        f.addRow(T("rp_status"), self.st)
        self.comment.setPlaceholderText(T("rp_comment_ph"))
        f.addRow(T("rep_comment"), self.comment)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        f.addRow(bb)

    def meta(self):
        m = dict(plant=self.plant.text(), author=self.author.text(), status=self.st.currentData(),
                 comment=self.comment.toPlainText())
        self.s.set(rep_plant=m["plant"], rep_author=m["author"], rep_status=m["status"], rep_comment=m["comment"])
        return m


def run(argv=None):
    """Spuštění aplikace; volitelně s cestou k datům nebo projektu (.json)."""
    argv = sys.argv if argv is None else argv
    app = QApplication.instance() or QApplication(argv)
    app.setApplicationName(APP)
    win = MainWindow()
    if len(argv) > 1:
        p = argv[1]
        try:
            (win.state.load_project if p.lower().endswith(".json") else win.state.load_file)(p)
        except Exception as ex:
            win.error(str(ex))
        win.refresh()
    win.show()
    return app.exec()
