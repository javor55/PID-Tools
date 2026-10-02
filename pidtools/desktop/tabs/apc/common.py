"""Společné prvky panelů APC v desktopu."""
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from .... import i18n
from ....i18n import T
from ... import widgets as w


class Panel(QWidget):
    """Panel struktury: nahoře popis, vlevo nastavení, vpravo graf a tabulky."""

    def __init__(self, win, intro_key=None):
        super().__init__()
        self.win, self.s = win, win.state
        lay = QVBoxLayout(self)
        if intro_key and intro_key in i18n.TEXTS["en"]:
            lay.addWidget(w.note(T(intro_key)))
        row = QHBoxLayout()
        self.left = QVBoxLayout()
        self.right = QVBoxLayout()
        row.addLayout(self.left, 2)
        row.addLayout(self.right, 5)
        lay.addLayout(row, 1)
        self._busy = False

    def chart(self, n=2, labels=("PV", "MV"), heights=(0.62, 0.38)):
        c, plots = w.stack(n, list(labels), T("time_s"), heights=heights)
        self.right.addWidget(c, 1)
        return plots

    def table(self, height=130):
        t = w.table([], [])
        t.setMaximumHeight(height)
        self.right.addWidget(t)
        return t

    def ready(self):
        return self.s.model is not None and self.isVisible()
