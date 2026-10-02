"""Společné prvky oken: grafy (pyqtgraph), číselná pole, tabulky a výpočty na pozadí."""
import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QObject, QRunnable, QSize, Qt, QThreadPool, Signal
from PySide6.QtGui import QValidator
from PySide6.QtWidgets import (QAbstractSpinBox, QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout,
                               QHeaderView, QLabel, QTableWidget, QTableWidgetItem, QWidget)

from ..app.plots import C_DIST, C_MV, C_PV, C_SET1, C_SET2, C_SP  # noqa: F401 (barvy pro okna)

pg.setConfigOptions(background="w", foreground="#1f2933", antialias=True)


# ---- grafy (ChartBox: kurzor, měření, export, odpojení do okna)
from .chartbox import ChartBox, _setup  # noqa: E402,F401


def plot(title=None, ylabel=None, xlabel=None):
    """Jeden graf s mřížkou, legendou a nástroji."""
    return ChartBox(1, [ylabel] if ylabel else (), xlabel, title=title)


def stack(n, ylabels=(), xlabel=None, heights=None):
    """n grafů pod sebou se společnou osou x. Vrací (widget, [grafy])."""
    box = ChartBox(n, ylabels, xlabel, heights)
    return box, box.plots


def line(p, x, y, name=None, color=C_PV, width=1.5, dash=False, step=False):
    """Čára do grafu p (u schodovitých průběhů MV „step“)."""
    pen = pg.mkPen(color=color, width=width, style=Qt.DashLine if dash else Qt.SolidLine)
    x, y = np.asarray(x, float), np.asarray(y, float)
    if step and len(x) > 1:
        return p.plot(np.r_[x, x[-1] + (x[-1] - x[-2])], y, stepMode="center", pen=pen, name=name)
    return p.plot(x, y, pen=pen, name=name)


# ---- vstupy
class Num(QDoubleSpinBox):
    """
    Kompaktní číselné pole: platné číslice místo pevných desetinných míst (5000, 24.19, 0.00123), tečka i čárka,
    šířka podle obsahu, ne podle rozsahu (±1e12 by pole zbytečně roztáhlo).
    """

    def textFromValue(self, v):
        return f"{v:.{max(self.decimals(), 4) + 1}g}"

    def valueFromText(self, text):
        t = text.replace(self.suffix(), "").replace(",", ".").replace(" ", "").strip()
        try:
            return float(t)
        except ValueError:
            return self.value()

    def validate(self, text, pos):
        t = text.replace(self.suffix(), "").replace(",", ".").replace(" ", "").strip()
        try:
            float(t)
            return QValidator.Acceptable, text, pos
        except ValueError:
            return QValidator.Intermediate, text, pos

    def sizeHint(self):
        h = super().sizeHint()
        return QSize(min(h.width(), 110), h.height())

    def minimumSizeHint(self):
        h = super().minimumSizeHint()
        return QSize(60, h.height())


def spin(value=0.0, lo=-1e12, hi=1e12, decimals=6, step=None, suffix=""):
    """Číselné pole bez šipek s rozumným krokem."""
    s = Num()
    s.setDecimals(decimals)
    s.setRange(lo, hi)
    s.setValue(float(value))
    s.setSingleStep(step if step else max(abs(float(value)) * 0.05, 0.01))
    s.setButtonSymbols(QAbstractSpinBox.NoButtons)
    s.setKeyboardTracking(False)
    if suffix:
        s.setSuffix(" " + suffix)
    return s


def combo(items, current=None, labels=None):
    """Výběr; items = hodnoty, labels = zobrazované texty (výchozí = hodnoty)."""
    c = QComboBox()
    for i, it in enumerate(items):
        c.addItem(str(labels[i]) if labels else str(it), it)
    if current in items:
        c.setCurrentIndex(list(items).index(current))
    return c


def group(title, layout=None):
    g = QGroupBox(title)
    if layout is not None:
        g.setLayout(layout)
    return g


def form(rows):
    """Formulář z dvojic (popisek, widget)."""
    f = QFormLayout()
    f.setRowWrapPolicy(QFormLayout.WrapLongRows)
    f.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
    for lab, w in rows:
        f.addRow(lab, w)
    return f


def hbox(*widgets, stretch=True):
    h = QHBoxLayout()
    for w in widgets:
        if isinstance(w, QWidget):
            h.addWidget(w)
        else:
            h.addLayout(w)
    if stretch:
        h.addStretch(1)
    return h


def table(headers, rows, stretch=True):
    """Tabulka jen pro čtení."""
    t = QTableWidget(len(rows), len(headers))
    fill(t, headers, rows)
    if stretch:
        t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    t.setEditTriggers(QTableWidget.NoEditTriggers)
    t.verticalHeader().setVisible(False)
    return t


def fill(t, headers, rows):
    t.clear()
    t.setColumnCount(len(headers))
    t.setRowCount(len(rows))
    t.setHorizontalHeaderLabels([str(h) for h in headers])
    for i, r in enumerate(rows):
        for j, v in enumerate(r):
            t.setItem(i, j, QTableWidgetItem(fmt(v)))


def fmt(v, d=4):
    if v is None:
        return "—"
    if isinstance(v, (float, np.floating)):
        return "∞" if np.isinf(v) else ("—" if not np.isfinite(v) else f"{v:.{d}g}")
    return str(v)


def note(text="", wrap=True):
    lab = QLabel(text)
    lab.setWordWrap(wrap)
    lab.setTextFormat(Qt.MarkdownText)
    return lab


# ---- výpočty na pozadí
class _Signals(QObject):
    done = Signal(object)
    failed = Signal(str)
    progress = Signal(float, str)


class Task(QRunnable):
    """Funkce na pozadí: fn(progress) → výsledek; done / failed se volají v hlavním vlákně (signály Qt)."""

    def __init__(self, fn):
        super().__init__()
        self.fn = fn
        self.signals = _Signals()

    def run(self):
        try:
            res = self.fn(lambda f, txt="": self.signals.progress.emit(float(f), txt))
        except Exception as ex:
            self.signals.failed.emit(str(ex))
            return
        self.signals.done.emit(res)


def _safe(fn, arg):
    """Výsledek pro okno, které mezitím mohlo zaniknout (přestavba po změně jazyka) – pak se zahodí."""
    if fn is None:
        return
    try:
        fn(arg)
    except RuntimeError:     # C++ objekt widgetu už neexistuje
        pass


_running = set()   # běžící úlohy – drží objekt signálů naživu, dokud se výsledek nedoručí do hlavního vlákna


def run_task(fn, on_done, on_failed=None, on_progress=None):
    t = Task(fn)
    t.setAutoDelete(False)
    _running.add(t)
    t.signals.done.connect(lambda r: (_running.discard(t), _safe(on_done, r)))
    t.signals.failed.connect(lambda e: (_running.discard(t), _safe(on_failed, e)))
    if on_progress:
        t.signals.progress.connect(on_progress)
    QThreadPool.globalInstance().start(t)
    return t


# ---- tabulka nad pandas.DataFrame (rychlá i pro desítky tisíc řádků)
from PySide6.QtCore import QAbstractTableModel, QModelIndex  # noqa: E402
from PySide6.QtWidgets import QTableView  # noqa: E402


class FrameModel(QAbstractTableModel):
    def __init__(self, df, index=False, parent=None):
        super().__init__(parent)
        self.df, self.show_index = df, index      # ne „index“ – to je metoda QAbstractTableModel

    def rowCount(self, parent=QModelIndex()):
        return len(self.df)

    def columnCount(self, parent=QModelIndex()):
        return len(self.df.columns)

    def data(self, idx, role=Qt.DisplayRole):
        if role == Qt.DisplayRole:
            return fmt(self.df.iat[idx.row(), idx.column()], 6)
        return None

    def headerData(self, i, orient, role=Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        if orient == Qt.Horizontal:
            return str(self.df.columns[i])
        return str(self.df.index[i]) if self.show_index else str(i + 1)


def frame_view(df, index=False):
    v = QTableView()
    v.setModel(FrameModel(df, index, v))      # rodič = pohled, jinak by model uvolnil Python a Qt by spadlo
    v.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
    return v


def tip(widget, key):
    """Nápověda k poli (stejné texty jako ve webu)."""
    from ..i18n import TEXTS, T
    if key in TEXTS["en"]:
        widget.setToolTip(T(key))
    return widget
