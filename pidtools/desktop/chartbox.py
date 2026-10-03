"""
Graf (jeden nebo několik pod sebou se společnou osou x) s nástroji: kurzor s odečtem hodnot všech křivek,
dva měřicí kurzory (Δt, ΔY), celý rozsah, export PNG / CSV, kopie do schránky, odpojení do samostatného okna.
Ovládání je klidné: kolečko zoomuje a tažení posouvá jen čas (osa x), osa y se sama přizpůsobí viditelným
datům; dvojklik = celý rozsah. Kliknutí na položku legendy křivku skryje / zobrazí.
"""
import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QApplication, QDialog, QFileDialog, QHBoxLayout, QLabel, QToolButton, QVBoxLayout,
                               QWidget)

from ..i18n import T

_CUR = pg.mkPen("#6b7280", width=1, style=Qt.DashLine)
_MEAS = (pg.mkPen("#d97706", width=1.5), pg.mkPen("#7c3aed", width=1.5))


def _setup(p):
    """Mřížka, legenda a zředění dlouhých průběhů (špičky zůstanou)."""
    p.showGrid(x=True, y=True, alpha=0.25)
    p.setDownsampling(auto=True, mode="peak")
    p.setClipToView(True)
    p.setMenuEnabled(False)
    for ax in ("left", "bottom"):
        p.getAxis(ax).enableAutoSIPrefix(False)   # žádné „(x0.001)“ u popisku osy
    p.hideButtons()
    p.setMouseEnabled(x=True, y=False)            # zoom a posun jen v čase
    p.vb.setAutoVisible(y=True)                   # osa y podle viditelného úseku
    p.enableAutoRange(axis="y")
    if p.legend is None:
        p.addLegend(offset=(8, 8), labelTextSize="8pt")


def _curves(p):
    """Pojmenované křivky grafu (bez pomocných čar)."""
    out = []
    for it in p.listDataItems():
        name = it.name()
        if not name or not it.isVisible():
            continue
        x, y = it.getOriginalDataset()
        if x is None or y is None or len(x) == 0:
            continue
        out.append((name, np.asarray(x, float), np.asarray(y, float)))
    return out


def _at(x, y, t):
    """Hodnota křivky v čase t (nejbližší vzorek; mimo rozsah None)."""
    if len(x) == 0 or t < x[0] - 1e-9 or t > x[-1] + 1e-9:
        return None
    i = int(np.clip(np.searchsorted(x, t), 1, len(x) - 1))
    j = i if abs(x[i] - t) < abs(x[i - 1] - t) else i - 1
    return float(y[j])


def _f(v):
    return "—" if v is None or not np.isfinite(v) else f"{v:.4g}"


class ChartBox(QWidget):
    """n grafů pod sebou; self.plots = [PlotItem]. U jednoho grafu se atributy předávají grafu (jako PlotWidget)."""

    def __init__(self, n=1, ylabels=(), xlabel=None, heights=None, title=None, tools=True):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(1)
        self.lw = pg.GraphicsLayoutWidget()
        self.plots = []
        for i in range(n):
            p = self.lw.addPlot(row=i, col=0)
            _setup(p)
            if i < len(ylabels) and ylabels[i]:
                p.setLabel("left", ylabels[i])
            if self.plots:
                p.setXLink(self.plots[0])
            self.plots.append(p)
        if title:
            self.plots[0].setTitle(title)
        if xlabel:
            self.plots[-1].setLabel("bottom", xlabel)
        self._stretch = [int(h * 100) for h in heights] if heights else [1] * n
        for i, h in enumerate(self._stretch):
            self.lw.ci.layout.setRowStretchFactor(i, h)
        self.bar = QHBoxLayout()
        self.bar.setContentsMargins(0, 0, 0, 0)
        self.readout = QLabel("")
        self.readout.setObjectName("readout")
        self.readout.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.b_full = self._tool(T("dk_chb_full"), "dk_ch_full")
        self.b_full.clicked.connect(self.full_range)
        self.b_cur = self._tool(T("dk_chb_cursor"), "dk_ch_cursor", checkable=True, checked=True)
        self.b_meas = self._tool(T("dk_chb_measure"), "dk_ch_measure", checkable=True)
        self.b_meas.toggled.connect(self._measure)
        for txt, key, fn in ((T("dk_chb_png"), "dk_ch_png", self.save_png), (T("dk_chb_csv"), "dk_ch_csv", self.save_csv),
                             (T("dk_chb_copy"), "dk_ch_copy", self.copy), (T("dk_chb_detach"), "dk_ch_detach",
                                                                           self.detach)):
            self._tool(txt, key).clicked.connect(fn)
        self.bar.addWidget(self.readout, 1)
        if tools:
            lay.addLayout(self.bar)
        lay.addWidget(self.lw, 1)
        self.vlines = []
        for p in self.plots:
            ln = pg.InfiniteLine(angle=90, movable=False, pen=_CUR)
            ln.setVisible(False)
            p.addItem(ln, ignoreBounds=True)
            self.vlines.append(ln)
        self.meas = []
        for p in self.plots:              # p.clear() smaže i čáry kurzorů → vrátit je zpět
            p.clear = self._keeping(p, p.clear)
        self._proxy = pg.SignalProxy(self.lw.scene().sigMouseMoved, rateLimit=30, slot=self._moved)
        self._dlg = None
        self.logx, self.xname = False, "t"
        self._ylim = {}                   # omezení osy y z fit_y (platí i pro Celý rozsah)
        for p in self.plots:
            p.vb.sigRangeChangedManually.connect(self._manual)
            p.scene().sigMouseClicked.connect(self._dbl)

    def _manual(self, *_):
        """Ruční zoom / posun: osa y dál sleduje viditelná data (i u grafů s omezením z fit_y)."""
        for p in self.plots:
            p.enableAutoRange(axis="y")

    def _dbl(self, ev):
        if ev.double():
            self.full_range()

    def set_logx(self, name="ω"):
        """Logaritmická osa x (kmitočet); kurzory a odečet hodnot pracují ve skutečných jednotkách."""
        self.logx, self.xname = True, name
        for p in self.plots:
            p.setLogMode(x=True, y=False)

    def _x(self, v):
        return 10 ** v if self.logx else v

    # ---- jako PlotWidget (jeden graf)
    def __getattr__(self, name):
        plots = self.__dict__.get("plots")
        if plots and len(plots) == 1 and hasattr(plots[0], name):
            return getattr(plots[0], name)
        raise AttributeError(name)

    def set_row_visible(self, i, on):
        """Skryje / zobrazí i-tý graf včetně jeho místa (ostatní se roztáhnou)."""
        lay = self.lw.ci.layout
        self.plots[i].setVisible(on)
        lay.setRowStretchFactor(i, self._stretch[i] if on else 0)
        lay.setRowMaximumHeight(i, 1e6 if on else 0)
        lay.setRowMinimumHeight(i, 0)

    def fit_y(self, i, lo, hi, margin=0.05):
        """Osa y grafu i podle křivek, ale nejvýš v mezích (lo, hi) – ujíždějící průběh nepřebije ostatní."""
        vals = [y[np.isfinite(y)] for _, _, y in _curves(self.plots[i])]
        vals = [v for v in vals if len(v)]
        if not vals:
            return
        a = max(min(float(v.min()) for v in vals), lo)
        b = min(max(float(v.max()) for v in vals), hi)
        if b <= a:
            return
        d = (b - a) * margin
        self._ylim[i] = (lo, hi, margin)
        self.plots[i].setYRange(a - d, b + d, padding=0)

    def getPlotItem(self):
        return self.plots[0]

    def _keeping(self, p, orig):
        def clear():
            keep = [it for it in p.items if it in self.vlines or any(it in m for m in self.meas)]
            orig()
            for it in keep:
                p.addItem(it, ignoreBounds=True)
        return clear

    def clear(self):
        """Smaže křivky všech grafů (pomocné čáry kurzorů zůstanou)."""
        self._ylim = {}
        for p in self.plots:
            p.clear()

    def _tool(self, text, key, checkable=False, checked=False):
        b = QToolButton()
        b.setText(text)
        b.setObjectName("chartTool")
        b.setToolTip(T(key))
        b.setAutoRaise(True)
        b.setCheckable(checkable)
        b.setChecked(checked)
        self.bar.addWidget(b)
        return b

    # ---- kurzor
    def _moved(self, evt):
        if not self.b_cur.isChecked():
            return
        pos = evt[0]
        for p in self.plots:
            if p.sceneBoundingRect().contains(pos):
                t = p.vb.mapSceneToView(pos).x()
                break
        else:
            for ln in self.vlines:
                ln.setVisible(False)
            return
        for ln in self.vlines:
            ln.setPos(t)
            ln.setVisible(True)
        if not self.b_meas.isChecked():
            self.readout.setText(self._values(self._x(t)))

    def _values(self, t):
        parts = [f"{self.xname} = {t:.4g}"]
        for p in self.plots:
            for name, x, y in _curves(p):
                v = _at(x, y, t)
                if v is not None:
                    parts.append(f"{name} = {_f(v)}")
        return "   ".join(parts)

    # ---- měření
    def _measure(self, on):
        for pair in self.meas:
            for p, ln in zip(self.plots, pair):
                p.removeItem(ln)
        self.meas = []
        if not on:
            self.readout.setText("")
            return
        vr = self.plots[0].vb.viewRange()[0]
        t1, t2 = vr[0] + 0.3 * (vr[1] - vr[0]), vr[0] + 0.6 * (vr[1] - vr[0])
        for t0, pen in zip((t1, t2), _MEAS):
            lines = []
            for p in self.plots:
                ln = pg.InfiniteLine(pos=t0, angle=90, movable=True, pen=pen)
                p.addItem(ln, ignoreBounds=True)
                lines.append(ln)
            for ln in lines:
                ln.sigPositionChanged.connect(lambda src, ls=lines: self._sync(src, ls))
            self.meas.append(lines)
        self._meas_text()

    def _sync(self, src, lines):
        x = src.value()
        for ln in lines:
            if ln is not src and abs(ln.value() - x) > 1e-12:
                ln.blockSignals(True)
                ln.setValue(x)
                ln.blockSignals(False)
        self._meas_text()

    def measured(self):
        """(t1, t2, [(křivka, y1, y2)]) měřicích kurzorů, nebo None."""
        if len(self.meas) != 2:
            return None
        t1, t2 = self._x(self.meas[0][0].value()), self._x(self.meas[1][0].value())
        rows = []
        for p in self.plots:
            for name, x, y in _curves(p):
                rows.append((name, _at(x, y, t1), _at(x, y, t2)))
        return t1, t2, rows

    def _meas_text(self):
        m = self.measured()
        if m is None:
            return
        t1, t2, rows = m
        x = self.xname
        parts = [f"{x}₁ = {t1:.4g}", f"{x}₂ = {t2:.4g}"] + ([f"{x}₂/{x}₁ = {t2 / t1:.4g}"] if self.logx and t1
                                                         else [f"Δ{x} = {t2 - t1:.4g}"])
        for name, a, b in rows:
            if a is not None and b is not None:
                parts.append(f"Δ{name} = {_f(b - a)}")
        self.readout.setText("   ".join(parts))

    # ---- rozsah, export
    def full_range(self):
        """Celý rozsah hned (meze z dat všech křivek, ne z ořezu na viditelný úsek)."""
        xs = [x[np.isfinite(x)] for p in self.plots for _, x, _ in _curves(p)]
        xs = [x[x > 0] if self.logx else x for x in xs]
        xs = [x for x in xs if len(x)]
        if xs:
            a, b = min(float(x.min()) for x in xs), max(float(x.max()) for x in xs)
            if self.logx:
                a, b = np.log10(a), np.log10(b)
            if b > a:
                self.plots[0].setXRange(a, b, padding=0.01)
        for i, p in enumerate(self.plots):
            if i in self._ylim:
                self.fit_y(i, *self._ylim[i])
                continue
            vals = [y[np.isfinite(y)] for _, _, y in _curves(p)]
            vals = [v for v in vals if len(v)]
            p.enableAutoRange(axis="y")
            if vals:
                lo, hi = min(float(v.min()) for v in vals), max(float(v.max()) for v in vals)
                d = (hi - lo) * 0.05 or max(abs(hi) * 0.05, 1e-6)
                p.setYRange(lo - d, hi + d, padding=0)
                p.enableAutoRange(axis="y")

    def save_png(self, path=None):
        if not path:
            path, _ = QFileDialog.getSaveFileName(self, T("dk_ch_png"), "chart.png", "PNG (*.png)")
        if path:
            self.lw.grab().save(path)
        return path

    def copy(self):
        QApplication.clipboard().setPixmap(self.lw.grab())

    def frame(self):
        """Data všech křivek jako DataFrame: společná osa → široký formát, jinak dlouhý (graf, křivka, t, y)."""
        import pandas as pd
        cur = [(i, n, x, y) for i, p in enumerate(self.plots) for n, x, y in _curves(p)]
        if not cur:
            return pd.DataFrame()
        x0 = cur[0][2]
        if all(len(x) == len(x0) and np.allclose(x, x0) for _, _, x, _ in cur):
            df = pd.DataFrame({"t": x0})
            for i, n, _, y in cur:
                col = n if n not in df else f"{n} ({i + 1})"
                df[col] = y
            return df
        return pd.concat([pd.DataFrame({"plot": i + 1, "series": n, "t": x, "value": y}) for i, n, x, y in cur],
                         ignore_index=True)

    def save_csv(self, path=None):
        if not path:
            path, _ = QFileDialog.getSaveFileName(self, T("dk_ch_csv"), "chart.csv", "CSV (*.csv)")
        if path:
            self.frame().to_csv(path, index=False)
        return path

    def detach(self):
        """Graf do samostatného okna (např. na druhý monitor); zavřením okna se vrátí zpět."""
        if self._dlg is not None:
            self._dlg.raise_()
            return
        dlg = QDialog(self.window())
        dlg.setWindowTitle(self.window().windowTitle())
        dlg.setWindowFlag(Qt.WindowMaximizeButtonHint, True)
        dlg.resize(1200, 750)
        QVBoxLayout(dlg).addWidget(self.lw)
        holder = QLabel(T("dk_ch_detached"))
        holder.setAlignment(Qt.AlignCenter)
        self.layout().addWidget(holder, 1)

        def back():
            holder.deleteLater()
            self.layout().addWidget(self.lw, 1)
            self._dlg = None
        dlg.finished.connect(back)
        self._dlg = dlg
        dlg.show()
