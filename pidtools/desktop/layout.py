"""
Jednotné rozložení záložek desktopu: vlevo co největší plocha pro grafy a data, vpravo panel nastavení se
sbalitelnými sekcemi. Stav sekcí (sbaleno / rozbaleno) a šířka panelu se pamatují v uživatelském nastavení.
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QAbstractScrollArea, QFrame, QHBoxLayout, QLabel, QScrollArea, QSizePolicy, QSplitter, QToolButton,
                               QVBoxLayout, QWidget)

PREFS = None          # QSettings hlavního okna (nastaví MainWindow); bez něj se nic nepamatuje
SIDE_WIDTH = 380      # výchozí šířka panelu nastavení [px]


def _pref(key, default):
    if PREFS is None:
        return default
    v = PREFS.value(key, default)
    return v


def _set_pref(key, value):
    if PREFS is not None:
        PREFS.setValue(key, value)


class Section(QWidget):
    """Sbalitelná sekce: záhlaví s šipkou a obsah (widget nebo layout)."""

    toggled = Signal(bool)

    def __init__(self, title, content=None, key=None, expanded=True):
        super().__init__()
        self.key = f"sec/{key}" if key else None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.head = QToolButton()
        self.head.setText(title)
        self.head.setCheckable(True)
        self.head.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.head.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.head.setObjectName("sectionHead")
        lay.addWidget(self.head)
        self.body = QFrame()
        self.body.setObjectName("sectionBody")
        self.body_lay = QVBoxLayout(self.body)
        self.body_lay.setContentsMargins(6, 4, 4, 6)
        self.body_lay.setSpacing(4)
        lay.addWidget(self.body)
        if content is not None:
            self.add(content)
        on = _pref(self.key, "true" if expanded else "false") in (True, "true") if self.key else expanded
        self.head.toggled.connect(self._toggle)
        self.head.setChecked(on)
        self._toggle(on)

    def add(self, content):
        if isinstance(content, QAbstractScrollArea):      # tabulky se do šířky panelu vejdou (mají vlastní posuvník)
            content.setSizePolicy(QSizePolicy.Ignored, content.sizePolicy().verticalPolicy())
            content.setMinimumWidth(0)
        if isinstance(content, QWidget):
            self.body_lay.addWidget(content)
        else:
            self.body_lay.addLayout(content)
        return content

    def set_title(self, title):
        self.head.setText(title)

    def is_expanded(self):
        return self.head.isChecked()

    def expand(self, on=True):
        self.head.setChecked(on)

    def _toggle(self, on):
        self.head.setArrowType(Qt.DownArrow if on else Qt.RightArrow)
        self.body.setVisible(on)
        if self.key:
            _set_pref(self.key, "true" if on else "false")
        self.toggled.emit(on)


class Workspace(QWidget):
    """
    Záložka: vlevo hlavní plocha (self.main – grafy, tabulky), vpravo posuvný panel nastavení (self.side)
    se sekcemi. Nad sekcemi může být pevný pruh s tlačítky (top_bar), který se neposouvá.
    """

    def __init__(self, key, side_width=SIDE_WIDTH):
        super().__init__()
        self.key = key
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        self.split = QSplitter(Qt.Horizontal)
        self.split.setChildrenCollapsible(False)
        lay.addWidget(self.split)
        left = QWidget()
        self.main = QVBoxLayout(left)
        self.main.setContentsMargins(0, 0, 0, 0)
        self.main.setSpacing(4)
        self.split.addWidget(left)
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(4)
        self.top = QVBoxLayout()
        self.top.setSpacing(4)
        rl.addLayout(self.top)
        inner = QWidget()
        inner.setObjectName("sidePanel")
        self.side = QVBoxLayout(inner)
        self.side.setContentsMargins(0, 0, 4, 0)
        self.side.setSpacing(6)
        self.side.addStretch(1)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll.setWidget(inner)
        rl.addWidget(self.scroll, 1)
        right.setMinimumWidth(260)
        self.split.addWidget(right)
        self.split.setStretchFactor(0, 1)
        self.split.setStretchFactor(1, 0)
        w = int(_pref(f"split/{key}", side_width) or side_width)
        self.split.setSizes([1400 - w, w])
        self.split.splitterMoved.connect(lambda *_: _set_pref(f"split/{key}", self.split.sizes()[1]))

    def section(self, title, content=None, key=None, expanded=True):
        """Přidá sbalitelnou sekci do panelu nastavení."""
        s = Section(title, content, f"{self.key}/{key}" if key else None, expanded)
        self.side.insertWidget(self.side.count() - 1, s)
        return s

    def side_widget(self, widget):
        """Nesbalitelný prvek v panelu (např. poznámka)."""
        self.side.insertWidget(self.side.count() - 1, widget)
        return widget

    def top_bar(self, *widgets):
        """Pevný pruh nad sekcemi (hlavní tlačítka záložky)."""
        h = QHBoxLayout()
        for wd in widgets:
            if isinstance(wd, QWidget):
                h.addWidget(wd)
            else:
                h.addLayout(wd)
        self.top.addLayout(h)
        return h


def caption(text):
    """Malý šedý popisek."""
    lab = QLabel(text)
    lab.setObjectName("caption")
    lab.setWordWrap(True)
    lab.setTextFormat(Qt.MarkdownText)
    return lab


STYLE = """
QWidget { font-size: 9pt; }
QToolButton#sectionHead { font-weight: 600; text-align: left; padding: 4px 6px; border: none;
    background: palette(midlight); border-radius: 3px; }
QToolButton#sectionHead:hover { background: palette(light); }
QFrame#sectionBody { border: none; }
QLabel#caption { color: #6b7280; font-size: 8pt; }
QGroupBox { margin-top: 10px; padding-top: 4px; }
QGroupBox::title { subcontrol-origin: margin; left: 6px; padding: 0 3px; }
QTabBar::tab { padding: 4px 10px; }
QTableView, QTableWidget { font-size: 8.5pt; }
QPushButton#primary { font-weight: 600; padding: 4px 12px; }
QToolButton#chartTool { padding: 1px 6px; }
QLabel#readout { font-family: Consolas, 'DejaVu Sans Mono', monospace; font-size: 8pt; color: #374151; }
QLabel#stale { color: #b45309; font-weight: 600; }
"""
