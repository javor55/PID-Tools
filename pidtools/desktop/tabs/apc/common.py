"""Společné prvky panelů APC v desktopu: stejné rozložení jako ostatní záložky (graf vlevo, nastavení vpravo)."""
from PySide6.QtWidgets import QGroupBox, QPushButton

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

    def reset_button(self, widgets, defaults, after):
        """
        Tlačítko „Původní hodnoty“: widgets = číselná pole, defaults() = jejich vypočtené / výchozí hodnoty,
        after() přepočítá panel. Bez ručních úprav je tlačítko neaktivní.
        """
        b = QPushButton(T("apc_reset"))
        b.setToolTip(T("h_apc_reset"))
        widgets = list(widgets)

        def click():
            vals = self._defaults_of(defaults)
            if vals is None:
                return
            busy, self._busy = self._busy, True
            try:
                for wd, v in zip(widgets, vals):
                    wd.setValue(float(v))
            finally:
                self._busy = busy
            after()
            self.sync_resets()
        b.clicked.connect(click)
        for wd in widgets:
            wd.valueChanged.connect(lambda *_: self.sync_resets())
        self.__dict__.setdefault("_resets", []).append((b, widgets, defaults))
        return b

    @staticmethod
    def _defaults_of(defaults):
        try:
            return list(defaults())
        except Exception:                    # bez modelu / dat: nic k obnovení
            return None

    def sync_resets(self):
        """Tlačítka „Původní hodnoty“ aktivní jen u sekcí s ručně změněnými hodnotami."""
        for b, widgets, defaults in self.__dict__.get("_resets", []):
            vals = self._defaults_of(defaults)
            b.setEnabled(vals is not None and any(
                abs(wd.value() - round(float(v), wd.decimals())) > 0.6 * 10 ** -wd.decimals() + 1e-9 * abs(float(v))
                for wd, v in zip(widgets, vals) if v is not None))     # hodnota bez výchozí (chybí model) se nehodnotí

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
