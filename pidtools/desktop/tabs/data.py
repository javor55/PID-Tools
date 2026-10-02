"""Záložka Data: rozložení tabulky, sloupce PV / MV / SP / poruchy / poloha, jednotky a graf celého záznamu."""
from PySide6.QtWidgets import (QCheckBox, QDialog, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QPushButton, QTabWidget, QVBoxLayout, QWidget)
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
        self.c_time, self.c_tag, self.c_val = w.combo([]), w.combo([]), w.combo([])
        self.ts_man = QCheckBox(T("ts_manual"))
        self.ts_val = w.spin(1.0, 0.001, 1e6, 4)
        self.tdet = QLabel("")
        w.tip(self.layout_c, "h_layout"), w.tip(self.tfmt, "h_time_fmt"), w.tip(self.tunit, "time_unit_help")
        w.tip(self.ts_man, "h_ts_manual")
        self.lab_time, self.lab_tag, self.lab_val = QLabel(T("col_time")), QLabel(T("col_tag")), QLabel(T("col_value"))
        tf = w.form([(T("layout"), self.layout_c), (self.lab_time, self.c_time), (self.lab_tag, self.c_tag),
                     (self.lab_val, self.c_val), (T("time_fmt"), self.tfmt), (T("time_unit"), self.tunit),
                     (self.ts_man, self.ts_val), ("", self.tdet)])
        top.addWidget(w.group(T("cols_title"), tf))
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
        self.warn = w.note("")
        b_prev = QPushButton(T("prev_title"))
        b_prev.clicked.connect(self._preview)
        row = w.hbox(b_prev)
        row.insertWidget(0, self.warn, 1)
        lay.addLayout(row)
        self.chart, self.plots = w.stack(3, ["PV", "MV", T("dists")], T("time_s"), heights=(0.5, 0.3, 0.2))
        lay.addWidget(self.chart, 1)
        for c in (self.layout_c, self.tfmt, self.tunit, self.c_time, self.c_tag, self.c_val):
            c.currentIndexChanged.connect(self._layout_changed)
        self.ts_man.toggled.connect(self._ts_changed)
        self.ts_val.valueChanged.connect(self._ts_changed)
        w.tip(self.c_pv, "h_pv"), w.tip(self.c_mv, "h_mv"), w.tip(self.c_sp, "h_sp"), w.tip(self.c_pos, "h_pos")
        w.tip(self.c_d, "col_dist_help")
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
            cols = list(s.df.columns)
            src = s.sig.time_src
            for c, cur, vis in ((self.c_time, src[0] if s.layout == "wide" and src else None, s.layout == "wide"),
                                (self.c_tag, s.c_tag, s.layout == "long"), (self.c_val, s.c_val, s.layout == "long")):
                c.clear()
                for col in cols:
                    c.addItem(str(col), col)
                if cur in cols:
                    c.setCurrentIndex(cols.index(cur))
                c.setVisible(vis)
            if s.layout == "long":
                self.c_time.setVisible(True)
                if src and src[0] in cols:
                    self.c_time.setCurrentIndex(cols.index(src[0]))
                if s.c_tag is None or s.c_val is None:          # odhad pro zobrazení
                    from ...app.dataset import guess_col
                    self.c_tag.setCurrentIndex(guess_col(cols, ["tag", "name", "název", "variable"]))
                    self.c_val.setCurrentIndex(guess_col(cols, ["value", "hodnota", "val"], 2))
            for lab, c in ((self.lab_time, self.c_time), (self.lab_tag, self.c_tag), (self.lab_val, self.c_val)):
                lab.setVisible(not c.isHidden())
            self.ts_man.setChecked(s.ts_user is not None)
            self.ts_val.setEnabled(s.ts_user is not None)
            self.ts_val.setValue(float(s.ts_user or s.grid.Ts))
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
        from ...app.dataio import TIME_FORMATS, detect_time_format
        kinds = {detect_time_format(s.df[c])[0] for c in s.sig.time_src if c in s.df.columns}
        self.tdet.setText(T("time_detected", f=", ".join(T("tf_" + k) if k in TIME_FORMATS else str(k)
                                                          for k in sorted(kinds, key=str))))
        warns = s.compression()
        self.warn.setText("  \n".join("⚠️ " + x for x in warns))
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

    def _ts_changed(self, *_):
        if self._busy or not self.s.has_data:
            return
        self.ts_val.setEnabled(self.ts_man.isChecked())
        self.s.ts_user = self.ts_val.value() if self.ts_man.isChecked() else None
        self.s.update_grid()
        self.win.refresh()

    def _preview(self):
        if self.s.has_data:
            PreviewDialog(self, self.s).exec()

    def _layout_changed(self):
        if self._busy or not self.s.has_data:
            return
        lay = self.layout_c.currentData()
        try:
            same = lay == self.s.layout
            self.s.set_layout(lay, self.tfmt.currentData(), self.tunit.currentData(),
                              self.c_time.currentData() if same and lay in ("wide", "long") else None,
                              self.c_tag.currentData() if same and lay == "long" else None,
                              self.c_val.currentData() if same and lay == "long" else None)
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


class PreviewDialog(QDialog):
    """Náhled dat: tabulka po převzorkování (export CSV), statistika, původní soubor s rozpoznanými typy sloupců."""

    def __init__(self, parent, s):
        super().__init__(parent)
        self.setWindowTitle(T("prev_title"))
        self.resize(1000, 620)
        res, stats, kinds = s.preview()
        self.res = res
        lay = QVBoxLayout(self)
        tabs = QTabWidget()
        p1 = QWidget()
        l1 = QVBoxLayout(p1)
        l1.addWidget(QLabel(T("prev_result_help", n=len(res), ts=f"{s.grid.Ts:.4g}")))
        l1.addWidget(w.frame_view(res), 1)
        b = QPushButton(T("prev_dl"))
        b.clicked.connect(self._export)
        l1.addWidget(b)
        tabs.addTab(p1, T("prev_result"))
        tabs.addTab(w.frame_view(stats.rename(columns={"min": T("prev_min"), "max": T("prev_max"), "mean": T("prev_mean"),
                                                       "NaN": T("prev_nan")}), index=True), T("prev_stats"))
        p3 = QWidget()
        l3 = QVBoxLayout(p3)
        l3.addWidget(QLabel(T("prev_raw_help", n=len(s.df), c=len(s.df.columns))))
        import pandas as pd
        kt = pd.DataFrame({c: [(T("prev_k_time") + (f" ({T('tf_' + k[1])})" if k[1] else "")) if k[0] == "time"
                               else T("prev_k_" + k[0]), int(s.df[c].isna().sum())] for c, k in kinds.items()},
                          index=[T("prev_type"), T("prev_nan")])
        v = w.frame_view(kt, index=True)
        v.setMaximumHeight(110)
        l3.addWidget(v)
        l3.addWidget(w.frame_view(s.df.head(500)), 1)
        tabs.addTab(p3, T("prev_raw"))
        lay.addWidget(tabs)

    def _export(self):
        path, _ = QFileDialog.getSaveFileName(self, T("prev_dl"), "data_resampled.csv", "CSV (*.csv)")
        if path:
            self.res.to_csv(path, index=False, sep=";", decimal=",")
