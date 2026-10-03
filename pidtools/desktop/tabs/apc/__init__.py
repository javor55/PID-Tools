"""
Záložka APC v desktopu: doporučení a pokročilé struktury pro aktivní smyčku – kaskáda, dopředná vazba, Smithův
prediktor, gain scheduling podle PV a podle regulační odchylky. Výpočty jsou v pidtools.app.apc.
Rozvazbení a override pracují s druhou smyčkou projektu (lišta smyček nahoře).
"""
import numpy as np
from PySide6.QtWidgets import QTabWidget, QVBoxLayout, QWidget

from ....app import feedforward as ffm
from ....app import guides
from ....app.apc import decouple as adec
from ....app.apc import gainsched as ags
from ....app.apc import recommend as reco
from ....app.apc.common import tchar
from ....core import MODELS, gs_issues, robustness
from ....core.apc import smith_apl
from ....i18n import T
from ... import widgets as w
from .cascade import CascadePanel
from .decouple import DecouplePanel
from .feedforward import FFPanel
from .gainsched import GainSchedPanel
from .gainsched_er import GainSchedErPanel
from .override import OverridePanel
from .more import RatioPanel, RgaPanel, SplitRangePanel, VpcPanel
from .smith import SmithPanel
from ....app.apc import rgan
from ...help import checklist_markdown
from ...layout import Section


class _LazyPanels:
    """Seznam panelů APC, které vznikají až při prvním přístupu (panel se vloží do připravené stránky záložky)."""

    def __init__(self, tabs, win, classes):
        self.tabs, self.win, self.classes = tabs, win, classes
        self.items = [None] * len(classes)

    def __len__(self):
        return len(self.classes)

    def __getitem__(self, i):
        if self.items[i] is None:
            p = self.items[i] = self.classes[i](self.win)
            self.tabs.widget(i).layout().addWidget(p)
        return self.items[i]

    def __iter__(self):
        return (self[i] for i in range(len(self)))

    def created(self):
        return [p for p in self.items if p is not None]


class ApcTab(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win, self.s = win, win.state
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 0)
        self.reco = w.note("")
        self.reco.linkActivated.connect(self._open)
        lay.addWidget(Section(T("dk_sec_reco"), self.reco, "apc/reco"))
        self.tabs = QTabWidget()
        # panely se vytvoří až při prvním otevření (rychlejší start aplikace)
        self.panels = _LazyPanels(self.tabs, win, (CascadePanel, FFPanel, DecouplePanel, OverridePanel, SmithPanel,
                                                   GainSchedPanel, GainSchedErPanel, SplitRangePanel, VpcPanel,
                                                   RatioPanel, RgaPanel))
        for key in ("apc_cascade", "apc_ff", "apc_decouple", "apc_override", "apc_smith", "apc_gainsched", "gs_x_er",
                    "apc_split", "apc_vpc", "apc_ratio", "apc_rga"):
            page = QWidget()
            QVBoxLayout(page).setContentsMargins(0, 0, 0, 0)
            self.tabs.addTab(page, T(key))
        self.tabs.currentChanged.connect(lambda i: self.panels[i].refresh())
        lay.addWidget(self.tabs, 1)

    _spread = None
    KINDS = ("cascade", "ff", "decouple", "override", "smith", "gainsched", "gainsched", "split", "vpc", "ratio",
             "rga")
    GUIDE_KINDS = ("cascade", "ff", "decouple", "override", "smith", "gainsched", "gs_er", "split", "vpc", "ratio",
                   "rga")

    def guide_extra(self):
        """Průvodce zvolenou strukturou (sdílený s webem): kdy použít, příklady, kontroly, implementace v PCS 7."""
        p = self.panels[self.tabs.currentIndex()]
        kind = self.GUIDE_KINDS[self.tabs.currentIndex()]
        impl = p.impl() if hasattr(p, "impl") else None
        if impl is None:
            import re
            raw = T("g_impl_" + kind)
            impl = None if re.search(r"\{\w+\}", raw) else raw
        head = [(T("g_title", m=T("apc_" + kind)), "")]
        secs = guides.apc_sections(kind, impl)
        chk = self.structure_checks(kind)
        if chk:
            secs.insert(2, ("", checklist_markdown(chk)))
        return head + secs

    def structure_checks(self, kind):
        """Kontrolní seznam zvolené struktury (sdílený s webem, pidtools.app.guides)."""
        s, pr = self.s, self.win.project
        name = pr.names()[pr.active]
        if s.model is None:
            return guides.apc_no_model(name)
        a = dict(s.report_record(), name=name)
        code, p, pdl = s.model
        integ = MODELS[code]["integ"]
        if kind == "cascade":
            return guides.apc_cascade(a, pr.others(include_without_model=True))
        if kind in ("split", "vpc"):
            return guides.apc_actuators(a, kind)
        if kind == "ratio":
            return guides.apc_ratio(a, len(pr.others()))
        if kind == "rga":
            recs = [a] + [r for _, r in pr.others()]
            n_cross = int(rgan.matrix(recs)[1].sum() - len(recs)) if len(recs) > 1 else 0
            return guides.apc_rga(a, len(recs), n_cross)
        if kind == "ff":
            return guides.apc_ff(a, [str(x) for x in s.c_d] if pdl else [],
                                 ffm.design(code, p, pdl, s.ff_state) if pdl else [], p)
        if kind == "smith":
            th_lag = 0.0 if integ else smith_apl(p, s.PR, s.MR, 0.0, 0.0)["th_lag"]
            return guides.apc_smith(a, integ, p[-1] / max(tchar((code, p)), 1e-9), th_lag)
        if kind == "gainsched":
            pts = ags.points(s.get("gs_pts") or [])
            stale = bool(pts) and s.get("gs_key") != ags.key(code, [tuple(x) for x in self.panels[5]._ranges()], s.norm)
            return guides.apc_gainsched(a, integ, self._spread, pts, stale,
                                        gs_issues(pts) if len(pts) >= 2 else [])
        if kind == "gs_er":
            set2 = {k: v for k, v in s.set_ctrl(2).items() if k not in ("FF", "FF_LL")}
            rb = robustness(code, list(p), dict(set2, Gain=float(s.get("gs_er_k", 2.0)) * set2["Gain"]))
            return guides.apc_gs_er(a, rb["Ms"] if rb["stable"] and np.isfinite(rb["Ms"]) else np.inf)
        pn = self.panels[self.KINDS.index(kind)]
        others = pr.others(include_without_model=True)
        if not others:
            return guides.apc_need_loop(a)
        bi = pn.other.currentData()
        if bi is None:
            bi = others[0][0]
        b = dict(others)[bi]
        if b["model"] is None:
            return guides.apc_need_loop(a)[:1] + guides.apc_no_model(b["name"], bi)
        if kind == "override":
            return guides.apc_override(a, b, bi)
        dz = adec.design(a, b)
        return guides.apc_decouple(a, b, pr.active, bi, dz["xab"], dz["xba"])

    def _open(self, link):
        """Doporučení → otevřít strukturu (u rozvazbení / override i s doporučenou druhou smyčkou)."""
        _, kind, other = link.split(":", 2)
        i = self.KINDS.index(kind)
        self.tabs.setCurrentIndex(i)
        p = self.panels[i]
        combo = getattr(p, "other", None) or getattr(p, "iloop", None)
        if other and combo is not None and combo.findData(int(other)) >= 0:
            combo.setCurrentIndex(combo.findData(int(other)))

    def refresh(self):
        s = self.s
        if s.model is None:
            self.reco.setText(T("need_model"))
            return
        rec = s.report_record()
        g = s.grid
        ts, pv, mv, d = s.segment()
        spread = self._spread = reco.nl_spread(s.model[0], s.model[1], s.model[2], ts, pv, mv, d, g.Ts)
        items = reco.recommend(rec, self.win.project.others(), spread, any(x.get("use") for x in s.ff_state))
        self.reco.setText("  \n".join(f"💡 {txt} — [{T('g_open', m=T('apc_' + k))}](apc:{k}:{o if o is not None else ''})"
                                      for k, txt, o in items) or T("dk_apc_none"))
        self.panels[self.tabs.currentIndex()].refresh()
