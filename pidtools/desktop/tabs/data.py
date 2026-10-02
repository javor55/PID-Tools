"""Záložka Data: rozložení tabulky, sloupce PV / MV / SP / poruchy / poloha, jednotky a graf celého záznamu."""
from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout, QWidget
from PySide6.QtCore import Qt

from ...app.dataio import TIME_FORMATS
from ...app.dataset import LAYOUTS, UNITS
from ...i18n import T
from .. import widgets as w


class DataTab(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win, self.s = win, win.state
        lay = QVBoxLayout(self)
        self.info = w.note(T("dk_no_data"))
        lay.addWidget(self.info)
        top = QHBoxLayout()
        # rozložení a čas
        self.layout_c = w.combo(LAYOUTS, labels=[T("layout_" + x) for x in LAYOUTS])
        self.tfmt = w.combo(TIME_FORMATS, labels=[T("tf_" + x) for x in TIME_FORMATS])
        self.tunit = w.combo(list(UNITS))
        top.addWidget(w.group(T("cols_title"), w.form([(T("layout"), self.layout_c), (T("time_fmt"), self.tfmt),
                                                       (T("time_unit"), self.tunit)])))
        # sloupce
        self.c_pv, self.c_mv, self.c_sp, self.c_pos = w.combo([]), w.combo([]), w.combo([]), w.combo([])
        self.c_d = QListWidget()
        self.c_d.setMaximumHeight(90)
        top.addWidget(w.group("PV / MV / SP", w.form([("PV", self.c_pv), ("MV", self.c_mv), (T("col_sp"), self.c_sp),
                                                     (T("col_pos"), self.c_pos)])), 2)
        top.addWidget(w.group(T("col_dist"), w.form([("", self.c_d)])), 2)
        # jednotky
        self.u_pv, self.u_mv = QLineEdit(), QLineEdit()
        self.tag = QLineEdit()
        top.addWidget(w.group(T("sb_units"), w.form([(T("unit_pv"), self.u_pv), (T("unit_mv"), self.u_mv),
                                                     ("Tag", self.tag)])))
        lay.addLayout(top)
        self.chart, self.plots = w.stack(3, ["PV", "MV", T("dists")], T("time_s"), heights=(0.5, 0.3, 0.2))
        lay.addWidget(self.chart, 1)
        for c in (self.layout_c, self.tfmt, self.tunit):
            c.currentIndexChanged.connect(self._layout_changed)
        for c in (self.c_pv, self.c_mv, self.c_sp, self.c_pos):
            c.currentIndexChanged.connect(self._cols_changed)
        self.c_d.itemChanged.connect(self._cols_changed)
        for e, k in ((self.u_pv, "u_pv"), (self.u_mv, "u_mv"), (self.tag, "loop_tag")):
            e.editingFinished.connect(lambda e=e, k=k: (self.s.set(**{k: e.text()}), self.win._build_loopbar(),
                                                        self.win.refresh(skip=self)))
        self._busy = False

    def refresh(self):
        s = self.s
        if not s.has_data:
            return
        self._busy = True
        try:
            for c, v in ((self.layout_c, s.layout), (self.tfmt, s.time_fmt), (self.tunit, s.unit)):
                c.setCurrentIndex(max(c.findData(v), 0))
            sigs = s.sig.sigs
            for c, items, cur in ((self.c_pv, sigs, s.c_pv), (self.c_mv, sigs, s.c_mv),
                                  (self.c_sp, ["—"] + sigs, s.c_sp), (self.c_pos, ["—"] + sigs, s.c_pos)):
                c.clear()
                for it in items:
                    c.addItem(str(it), it)
                c.setCurrentIndex(max(c.findData(cur), 0))
            self.c_d.clear()
            for sg in sigs:
                if sg in (s.c_pv, s.c_mv, s.c_sp):
                    continue
                it = QListWidgetItem(str(sg))
                it.setData(Qt.UserRole, sg)
                it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
                it.setCheckState(Qt.Checked if sg in s.c_d else Qt.Unchecked)
                self.c_d.addItem(it)
            self.u_pv.setText(s.get("u_pv", ""))
            self.u_mv.setText(s.get("u_mv", ""))
            self.tag.setText(s.get("loop_tag", ""))
        finally:
            self._busy = False
        g = s.grid
        self.info.setText(T("dk_loaded", f=s.fname, n=len(g.t), ts=g.Ts,
                            d=f"{g.t[-1]:.0f} s" + (f" ({s.sig.origin:%d.%m.%Y %H:%M})" if s.sig.origin is not None else "")))
        for p in self.plots:
            p.clear()
        pv, mv = self.plots[0], self.plots[1]
        if g.has_sp:
            w.line(pv, g.t, g.sp_e, "SP", w.C_SP, 1.3, dash=True)
        w.line(pv, g.t, g.pv_e, "PV", w.C_PV, 1.3)
        w.line(mv, g.t, g.mv_e, "MV", w.C_MV, 1.5)
        for i, (nm, d) in enumerate(zip(s.c_d, g.dists)):
            w.line(self.plots[2], g.t, d, str(nm), w.C_DIST[i % 4], 1.3)
        self.plots[0].setLabel("left", f"PV [{s.get('u_pv')}]" if s.get("u_pv") else "PV")
        self.plots[1].setLabel("left", f"MV [{s.get('u_mv')}]" if s.get("u_mv") else "MV")
        self.plots[2].setVisible(bool(s.c_d))

    def _layout_changed(self):
        if self._busy or not self.s.has_data:
            return
        try:
            self.s.set_layout(self.layout_c.currentData(), self.tfmt.currentData(), self.tunit.currentData())
        except Exception as ex:
            self.win.error(T("err_data", ex=T(str(ex))))
        self.win.refresh()

    def _cols_changed(self, *_):
        if self._busy or not self.s.has_data:
            return
        d = [self.c_d.item(i).data(Qt.UserRole) for i in range(self.c_d.count())
             if self.c_d.item(i).checkState() == Qt.Checked]
        try:
            self.s.set_columns(self.c_pv.currentData(), self.c_mv.currentData(), self.c_sp.currentData(), d,
                               self.c_pos.currentData())
        except Exception as ex:
            self.win.error(T("err_data", ex=ex))
        self.win.refresh()
