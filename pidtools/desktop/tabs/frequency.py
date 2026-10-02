"""
Frekvenční analýza v záložce Ladění: Bodeho diagram otevřené smyčky, Nyquistův diagram s kružnicí Ms,
citlivostní funkce |S| a |T| a tabulka rezerv pro sady 1, 2 a návrh. Výpočty v pidtools.app.frequency.
"""
import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QSplitter, QVBoxLayout, QWidget

from ...app import frequency as fq
from ...i18n import T
from .. import widgets as w
from ..layout import caption

_REF = pg.mkPen("#9ca3af", width=1, style=Qt.DashLine)


class FrequencyView(QWidget):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        v = QSplitter(Qt.Vertical)
        top = QSplitter(Qt.Horizontal)
        self.bode, self.bode_plots = w.stack(2, [T("fq_mag"), T("fq_phase")], T("fq_w"), heights=(0.5, 0.5))
        self.bode.set_logx()
        self.bode_plots[0].setTitle(T("fq_bode"))
        self.nyq = w.plot(T("fq_nyquist"), "Im L", "Re L")
        self.nyq.b_cur.setChecked(False)
        self.nyq.getPlotItem().setAspectLocked(True)
        top.addWidget(self.bode)
        top.addWidget(self.nyq)
        top.setSizes([620, 420])
        bot = QSplitter(Qt.Horizontal)
        self.sens = w.plot(T("fq_sens"), "dB", T("fq_w"))
        self.sens.set_logx()
        box = QWidget()
        bl = QVBoxLayout(box)
        bl.setContentsMargins(0, 0, 0, 0)
        self.tab = w.table([], [])
        bl.addWidget(self.tab, 1)
        bl.addWidget(caption(T("fq_help")))
        bot.addWidget(self.sens)
        bot.addWidget(box)
        bot.setSizes([620, 420])
        v.addWidget(top)
        v.addWidget(bot)
        v.setSizes([520, 330])
        lay.addWidget(v)

    def clear(self):
        for c in (self.bode, self.nyq, self.sens):
            c.clear()
        self.tab.setRowCount(0)

    def update(self, code, p, sets):
        """sets: [(název, ctrl, barva, čárkovaně)]."""
        self.clear()
        res = fq.compare(code, p, {name: c for name, c, _, _ in sets})
        mag, ph = self.bode_plots
        mag.addItem(pg.InfiniteLine(pos=0, angle=0, pen=_REF), ignoreBounds=True)
        ph.addItem(pg.InfiniteLine(pos=-180, angle=0, pen=_REF), ignoreBounds=True)
        nq = self.nyq.getPlotItem()
        cx, cy = fq.ms_circle()
        nq.plot(cx, cy, pen=pg.mkPen("#f59e0b", width=1.2, style=Qt.DashLine), name=f"Ms = {fq.MS_TARGET}")
        ux, uy = fq.ms_circle(1.0)
        nq.plot(ux, uy, pen=pg.mkPen("#d1d5db", width=1))
        nq.plot([-1], [0], pen=None, symbol="+", symbolSize=14, symbolPen=pg.mkPen("#dc2626", width=2))
        rows = []
        for name, _, col, dash in sets:
            r = res[name]
            wd = 2.0
            w.line(mag, r["w"], r["mag_db"], name, col, wd, dash)
            w.line(ph, r["w"], r["phase_deg"], name, col, wd, dash)
            L = r["L"]
            keep = np.abs(L) < 6                        # Nyquist jen v okolí −1 (nízké kmitočty jdou do nekonečna)
            w.line(nq, L.real[keep], L.imag[keep], name, col, wd, dash)
            w.line(self.sens.getPlotItem(), r["w"], fq.db(r["S"]), f"|S| {name}", col, wd, dash)
            w.line(self.sens.getPlotItem(), r["w"], fq.db(r["T"]), f"|T| {name}", col, 1.0, True)
            for x, pt in ((r["wc"], mag), (r["w180"], ph)):
                if x:
                    pt.addItem(pg.InfiniteLine(pos=np.log10(x), angle=90, pen=pg.mkPen(col, width=0.8,
                                                                                     style=Qt.DotLine)))
            bw = fq.bandwidth(r)
            rows.append([name, r["Ms"], r["GM"], r["PM"], r["wc"], r["w180"], bw,
                         2 * np.pi / bw if bw else None, T("yes") if r["stable"] else T("dk_unstable")])
        ph.setYRange(fq.phase_floor(res), 30, padding=0)
        nq.setXRange(-2.5, 1.0, padding=0)
        nq.setYRange(-2.0, 1.5, padding=0)
        w.fill(self.tab, ["", "Ms", "GM", "PM [°]", "ωc [rad/s]", "ω180 [rad/s]", T("fq_bw"), T("fq_tbw"),
                          T("fq_stable")], rows)
        self.tab.resizeColumnsToContents()
        return res
