"""
Desktopová aplikace PID Tools (Qt): okno se záložkami Data, Model, Ladění, Živá simulace, APC; lišta smyček projektu;
menu Soubor (data, ukázka, projekt, protokol), jazyk a nápověda. Spuštění: python -m pidtools.desktop
"""
import sys
from pathlib import Path

from PySide6.QtCore import QSettings, QThreadPool
from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QLabel,
                               QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit, QTabWidget, QToolBar)

from .. import __version__, i18n
from ..app.report import SECTIONS, STATUSES
from ..i18n import T
from ..app import guides
from .help import HelpWindow, general_markdown, guide_state, tab_markdown
from .project import Project
from .tabs.apc import ApcTab
from .tabs.data import DataTab
from .tabs.diagnostics import DiagnosticsTab
from .tabs.live import LiveTab
from .tabs.model import ModelTab
from .tabs.tuning import TuningTab

ORG, APP = "PID Tools", "PID Tools desktop"


class MainWindow(QMainWindow):
    def __init__(self, state=None, prefs=None, project=None):
        super().__init__()
        self.project = project or Project()
        if state is not None:
            self.project.loops = [state]
        self.prefs = prefs if prefs is not None else QSettings(ORG, APP)   # jazyk, poslední složka
        i18n.set_lang(self.prefs.value("lang", self.state.get("lang", "en")))
        self.resize(1400, 900)
        self.loopbar = QToolBar()
        self.loopbar.setMovable(False)
        self.addToolBar(self.loopbar)
        self.build()

    @property
    def state(self):
        """Aktivní smyčka projektu."""
        return self.project.state

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
        g = QAction(T("dk_help_guide"), self)
        g.setShortcut("F1")
        g.triggered.connect(self.show_guide)
        h.addAction(g)
        gh = QAction(T("dk_help_general"), self)
        gh.triggered.connect(lambda: self.help_window().show_markdown(general_markdown()))
        h.addAction(gh)
        a = QAction(T("dk_about"), self)
        a.triggered.connect(lambda: QMessageBox.about(self, T("dk_about"), T("dk_about_text", v=__version__)))
        h.addAction(a)
        cur = self.tabs.currentIndex() if hasattr(self, "tabs") else 0
        self.tabs = QTabWidget()
        self.pages = [DataTab(self), ModelTab(self), TuningTab(self), LiveTab(self), ApcTab(self), DiagnosticsTab(self)]
        for p, key in zip(self.pages, ("tab1", "tab2", "tab3", "tab4_live", "tab5", "dk_diag_tab")):
            self.tabs.addTab(p, T(key))
        self.tabs.setCurrentIndex(cur)
        # živá simulace převezme aktuální sady, když se na ni přepne (úpravy v Ladění ji jinak nerestartují)
        self.tabs.currentChanged.connect(lambda i: self.pages[i].refresh() if isinstance(self.pages[i], (LiveTab, ApcTab))
                                         else None)
        self.setCentralWidget(self.tabs)
        self._build_loopbar()
        self.refresh()

    # ---- smyčky projektu
    def _build_loopbar(self):
        bar = self.loopbar
        bar.clear()
        bar.addWidget(QLabel(" " + T("dk_loop") + " "))
        self.loop_combo = QComboBox()
        for i, n in enumerate(self.project.names()):
            self.loop_combo.addItem(n, i)
        self.loop_combo.setCurrentIndex(self.project.active)
        self.loop_combo.currentIndexChanged.connect(self.switch_loop)
        bar.addWidget(self.loop_combo)
        a = QAction(T("loop_add"), self)
        a.triggered.connect(self.add_loop)
        a.setEnabled(self.state.has_data)
        bar.addAction(a)
        r = QAction(T("dk_loop_remove"), self)
        r.triggered.connect(self.remove_loop)
        r.setEnabled(len(self.project.loops) > 1)
        bar.addAction(r)
        bar.addSeparator()
        gd = QAction("📖 " + T("dk_help_btn"), self)
        gd.setToolTip(T("dk_help_guide") + " (F1)")
        gd.triggered.connect(self.show_guide)
        bar.addAction(gd)

    # ---- nápověda (samostatné okno, sdílený obsah s webem)
    TAB_GUIDES = ("data", "model", "tuning", "live", "apc", "diag")

    def help_window(self):
        if getattr(self, "_help", None) is None:
            self._help = HelpWindow(self)
        return self._help

    def show_guide(self):
        """Průvodce aktuální záložky (u APC i průvodce zvolenou strukturou)."""
        i = self.tabs.currentIndex()
        key = self.TAB_GUIDES[i] if i < len(self.TAB_GUIDES) else "data"
        extra = self.pages[i].guide_extra() if hasattr(self.pages[i], "guide_extra") else ()
        self.help_window().show_markdown(tab_markdown(key, guide_state(self), extra), guides.title(key))

    def do_action(self, act):
        """Akce z kontrolního seznamu průvodce: přepnout záložku, přidat smyčku."""
        if act == "add_loop":
            self.add_loop()
        elif act.startswith("tab:"):
            tab = act.split(":", 1)[1]
            if tab in self.TAB_GUIDES:
                self.tabs.setCurrentIndex(self.TAB_GUIDES.index(tab))

    def switch_loop(self, i):
        if i < 0 or i == self.project.active:
            return
        self.project.active = i
        self.build()

    def add_loop(self):
        if self.project.add_loop() is not None:
            self.tabs.setCurrentIndex(0)
            self.build()

    def remove_loop(self):
        self.project.remove_loop(self.project.active)
        self.build()

    def set_lang(self, code):
        i18n.set_lang(code)
        self.state.set(lang=code)
        self.prefs.setValue("lang", code)
        self.build()

    def refresh(self, skip=None):
        """Překreslí záložky ze stavu (po změně dat, sloupců, úseku, modelu, parametrů)."""
        has = self.state.has_data
        if hasattr(self, "loop_combo"):          # názvy smyček (tag nebo PV) se mění v záložce Data
            for i, n in enumerate(self.project.names()):
                self.loop_combo.setItemText(i, n)
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
                self.project.load_file(path)
            except Exception as ex:
                self.error(T("err_data", ex=T(str(ex))))
            self.tabs.setCurrentIndex(0)
            self.build()

    def open_demo(self):
        self.project.load_demo()
        self.tabs.setCurrentIndex(0)
        self.build()

    def open_project(self):
        path, _ = QFileDialog.getOpenFileName(self, T("dk_open_project"), self._dir(), "PID Tools (*.json)")
        if path:
            self._remember(path)
            try:
                self.project.load(path)
            except Exception as ex:
                self.error(str(ex))
            self.build()

    def save_project(self):
        name = (self.state.get("loop_tag") or "pidtools_project") + ".json"
        path, _ = QFileDialog.getSaveFileName(self, T("dk_save_project"), str(Path(self._dir()) / name),
                                              "PID Tools (*.json)")
        if path:
            self._remember(path)
            self.project.save(path, include_data=True)
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
            html = self.project.report_html(dlg.meta(), SECTIONS, "inline")
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
            (win.project.load if p.lower().endswith(".json") else win.project.load_file)(p)
        except Exception as ex:
            win.error(str(ex))
        win.build()
    win.show()
    return app.exec()
