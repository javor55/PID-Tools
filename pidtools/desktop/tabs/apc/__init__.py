"""
Záložka APC v desktopu: doporučení a pokročilé struktury pro aktivní smyčku – kaskáda, dopředná vazba, Smithův
prediktor, gain scheduling podle PV a podle regulační odchylky. Výpočty jsou v pidtools.app.apc.
Rozvazbení a override pracují s druhou smyčkou projektu (lišta smyček nahoře).
"""
from PySide6.QtWidgets import QTabWidget, QVBoxLayout, QWidget

from ....app import guides
from ....app.apc import recommend as reco
from ....i18n import T
from ... import widgets as w
from .cascade import CascadePanel
from .decouple import DecouplePanel
from .feedforward import FFPanel
from .gainsched import GainSchedPanel
from .gainsched_er import GainSchedErPanel
from .override import OverridePanel
from .smith import SmithPanel


class ApcTab(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win, self.s = win, win.state
        lay = QVBoxLayout(self)
        self.reco = w.note("")
        lay.addWidget(w.group(T("dk_apc_reco"), w.form([("", self.reco)])))
        self.tabs = QTabWidget()
        self.panels = [CascadePanel(win), FFPanel(win), DecouplePanel(win), OverridePanel(win), SmithPanel(win),
                       GainSchedPanel(win), GainSchedErPanel(win)]
        for p, key in zip(self.panels, ("apc_cascade", "apc_ff", "apc_decouple", "apc_override", "apc_smith",
                                        "apc_gainsched", "gs_x_er")):
            self.tabs.addTab(p, T(key))
        self.tabs.currentChanged.connect(lambda i: self.panels[i].refresh())
        lay.addWidget(self.tabs, 1)

    KINDS = ("cascade", "ff", "decouple", "override", "smith", "gainsched", "gainsched")

    def guide_extra(self):
        """Průvodce zvolenou strukturou (sdílený s webem): kdy použít, příklady, implementace v PCS 7."""
        p = self.panels[self.tabs.currentIndex()]
        kind = self.KINDS[self.tabs.currentIndex()]
        impl = p.impl() if hasattr(p, "impl") else None
        if impl is None:
            import re
            raw = T("g_impl_" + kind)
            impl = None if re.search(r"\{\w+\}", raw) else raw
        head = [(T("g_title", m=T("apc_" + kind)), "")]
        return head + guides.apc_sections(kind, impl)

    def refresh(self):
        s = self.s
        if s.model is None:
            self.reco.setText(T("need_model"))
            return
        rec = s.report_record()
        g = s.grid
        ts, pv, mv, d = s.segment()
        spread = reco.nl_spread(s.model[0], s.model[1], s.model[2], ts, pv, mv, d, g.Ts)
        items = reco.recommend(rec, self.win.project.others(), spread, any(x.get("use") for x in s.ff_state))
        self.reco.setText("  \n".join("💡 " + txt for _, txt, _ in items) or T("dk_apc_none"))
        self.panels[self.tabs.currentIndex()].refresh()
