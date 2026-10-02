"""Společné prvky panelů APC v desktopu: stejné rozložení jako ostatní záložky (graf vlevo, nastavení vpravo)."""
from PySide6.QtWidgets import QGroupBox

from .... import i18n
from ....i18n import T
from ... import widgets as w
from ...layout import Workspace


class _Side:
    """Panel nastavení pro kód panelů: skupina (QGroupBox s nadpisem) → sbalitelná sekce, ostatní prvky pod ni."""

    def __init__(self, ws, kind):
        self.ws, self.kind, self.n, self.last = ws, kind, 0, None

    def addWidget(self, wd):
        if isinstance(wd, QGroupBox) and wd.title():
            title = wd.title()
            wd.setTitle("")
            wd.setFlat(True)
            wd.setStyleSheet("QGroupBox { border: none; margin-top: 0; padding-top: 0; }")
            self.n += 1
            self.last = self.ws.section(title, wd, f"{self.kind}{self.n}")
        elif self.last is not None:
            self.last.add(wd)
        else:
            self.ws.side_widget(wd)

    def addLayout(self, lay):
        if self.last is not None:
            self.last.add(lay)
        else:
            self.ws.side.insertLayout(self.ws.side.count() - 1, lay)

    def addStretch(self, *_):
        pass


class Panel(Workspace):
    """Panel struktury: vlevo graf a tabulky (self.right), vpravo popis a nastavení (self.left) ve sekcích."""

    def __init__(self, win, intro_key=None):
        super().__init__("apc")
        self.win, self.s = win, win.state
        kind = type(self).__name__.replace("Panel", "").lower()
        if intro_key and intro_key in i18n.TEXTS["en"]:
            self.section(T("dk_sec_about"), w.note(T(intro_key)), f"apc/{kind}/about", expanded=False)
        self.left = _Side(self, f"apc/{kind}/")
        self.right = self.main
        self._busy = False

    def chart(self, n=2, labels=("PV", "MV"), heights=(0.62, 0.38)):
        c, plots = w.stack(n, list(labels), T("time_s"), heights=heights)
        self.right.addWidget(c, 1)
        self.chart_box = c
        return plots

    def table(self, height=130):
        t = w.table([], [])
        t.setMaximumHeight(height)
        self.right.addWidget(t)
        return t

    def ready(self):
        return self.s.model is not None and self.isVisible()
