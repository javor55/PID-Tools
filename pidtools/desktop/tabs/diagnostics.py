"""
Záložka Diagnostika: úsek provozních dat (tažením v grafu), výkon smyčky (srovnání dvou úseků), oscilace a stikce
(křížová korelace, fázový graf MV–PV), hystereze z polohy ventilu a nelinearita (lokální zesílení).
"""
import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QSplitter, QVBoxLayout, QWidget

from ...app import diagnostics as dg
from ...core import MODELS
from ...i18n import T
from .. import widgets as w


class DiagnosticsTab(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win, self.s = win, win.state
        lay = QVBoxLayout(self)
        split = QSplitter(Qt.Vertical)
        lay.addWidget(split)
        top = QWidget()
        tl = QHBoxLayout(top)
        self.chart, self.plots = w.stack(2, ["PV", "MV"], T("time_s"), heights=(0.6, 0.4))
        self.ra = pg.LinearRegionItem(brush=(31, 95, 168, 40))
        self.rb = pg.LinearRegionItem(brush=(194, 65, 12, 35))
        for r in (self.ra, self.rb):
            r.sigRegionChangeFinished.connect(self.update)
        tl.addWidget(self.chart, 3)
        side = QVBoxLayout()
        self.cmp = QCheckBox(T("perf_compare"))
        self.cmp.toggled.connect(self._cmp_toggled)
        self.integ = QCheckBox(T("diag_integ"))
        self.integ.toggled.connect(self.update)
        self.kpi = w.table([], [])
        side.addWidget(w.note(T("dk_diag_help")))
        side.addWidget(self.cmp)
        side.addWidget(self.integ)
        side.addWidget(w.group(T("perf_title"), w.form([("", self.kpi)])))
        tl.addLayout(side, 2)
        split.addWidget(top)
        bot = QWidget()
        bl = QHBoxLayout(bot)
        self.verdict = w.note("")
        left = QVBoxLayout()
        left.addWidget(w.group(T("dk_diag_valve"), w.form([("", self.verdict)])))
        self.nl = w.table([], [])
        left.addWidget(w.group(T("nl_title"), w.form([("", self.nl)])))
        bl.addLayout(left, 2)
        self.ccf = w.plot(T("ccf_title"), T("ccf"), T("lag_s"))
        self.phase = w.plot(T("phase_title"), "PV", "MV")
        bl.addWidget(self.ccf, 2)
        bl.addWidget(self.phase, 2)
        split.addWidget(bot)
        split.setSizes([380, 420])
        self._busy = False

    def refresh(self):
        s = self.s
        if not s.has_data:
            return
        g = s.grid
        self._busy = True
        for p in self.plots:
            p.clear()
        self.plots[0].addItem(self.ra)
        if g.has_sp:
            w.line(self.plots[0], g.t, g.sp_e, "SP", w.C_SP, 1.2, dash=True)
        w.line(self.plots[0], g.t, g.pv_e, "PV", w.C_PV, 1.2)
        w.line(self.plots[1], g.t, g.mv_e, "MV", w.C_MV, 1.4)
        T_ = float(g.t[-1])
        for r in (self.ra, self.rb):
            r.setBounds((0, T_))
        if self.ra.getRegion() == (0, 1) or self.ra.getRegion()[1] > T_:
            self.ra.setRegion((0, T_))
            self.rb.setRegion((T_ / 2, T_))
        if self.cmp.isChecked():
            self.plots[0].addItem(self.rb)
        self.integ.setChecked(bool(MODELS[s.model[0]]["integ"]) if s.model else self.integ.isChecked())
        self._busy = False
        self.update()

    def _cmp_toggled(self, on):
        if on:
            self.plots[0].addItem(self.rb)
        else:
            self.plots[0].removeItem(self.rb)
        self.update()

    def _mask(self, region):
        a, b = region.getRegion()
        return (self.s.t >= a) & (self.s.t <= b)

    def update(self, *_):
        s = self.s
        if self._busy or not s.has_data:
            return
        g = s.grid
        theta = (s.model[1][-1] if s.model else 5.0) + float(s.get("samp")) / 2
        lo, hi = float(s.M(s.get("mvl_lo", s.mv_lo))), float(s.M(s.get("mvl_hi", s.mv_hi)))
        cols, heads = [], [""]
        for name, reg in ((T("seg_a"), self.ra), (T("seg_b"), self.rb)):
            if reg is self.rb and not self.cmp.isChecked():
                continue
            m = self._mask(reg)
            if m.sum() < 100:
                continue
            k = dg.kpis(s, s.t[m], s.sp[m], s.pv[m], s.mv[m], g.Ts, lo, hi, theta, g.has_sp)
            heads.append(name)
            cols.append([k["std_e"], k["iae_h"], k["travel_h"], k["rev_h"], k["at_lim"], k["harris"],
                         T("yes_period", p=f"{k['osc']['period']:.0f}") if k["osc"]["osc"] else T("no")])
        u_pv, u_mv = s.get("u_pv") or "PV", s.get("u_mv") or "MV"
        labels = [T("kpi_std", u=u_pv), T("kpi_iae_h", u=u_pv), T("kpi_travel_h", u=u_mv), T("kpi_rev_h"),
                  T("kpi_at_lim"), T("kpi_harris"), T("kpi_osc")]
        w.fill(self.kpi, heads, [[lab] + [c[i] for c in cols] for i, lab in enumerate(labels)])
        m = self._mask(self.ra)
        if m.sum() < 100:
            self.verdict.setText(T("err_short"))
            return
        integ = self.integ.isChecked()
        v = dg.valve(s.sp[m], s.pv[m], s.mv[m], g.Ts, g.has_sp, integ)
        osc = v["osc"]
        lines = [T("osc_found", p=f"{osc['period']:.0f}", a=f"{osc['amp'] * s.PR / 100:.3g}", u=u_pv,
                   r=f"{osc['r']:.1f}") if osc["osc"] else T("osc_none")]
        if v["verdict"]:
            lines.append(T("stic_" + v["verdict"], r=f"{v['stic']['ratio']:.2f}"))
        if s.c_pos not in (None, "", "—"):
            from ...app.dataset import on_grid
            pos = on_grid(s.sig, g, s.c_pos)
            h = dg.hysteresis(g.mv_e[m], pos[m])
            lines.append(f"{T('hyst')}: " + ("—" if not np.isfinite(h) else f"{abs(h):.3g} {u_mv}"))
        self.verdict.setText("  \n".join(lines))
        self.ccf.clear()
        self.ccf.plot(v["stic"]["lags"], v["stic"]["ccf"], pen=pg.mkPen(w.C_PV, width=2))
        self.phase.clear()
        yy = np.gradient(s.pv[m], g.Ts) * s.PR / 100 if integ else s.EP(s.pv[m])
        self.phase.plot(s.EM(s.mv[m]), yy, pen=pg.mkPen("#cbd5e1", width=0.6), symbol="o", symbolSize=3,
                        symbolBrush=w.C_PV, symbolPen=None)
        self.phase.setLabel("left", "dPV/dt" if integ else "PV")
        if s.model is None:
            w.fill(self.nl, [""], [[T("need_model")]])
            return
        ts, pv, mv, d = s.segment()
        lg, spread = dg.nonlinearity(s.model, ts, pv, mv, d, g.Ts)
        rows = [[f"{q['t']:.0f}", float(s.EM(q["mv_from"])), float(s.EM(q["mv_to"])), "↑" if q["dmv"] > 0 else "↓",
                 q["gain"], q["ratio"]] for q in lg]
        w.fill(self.nl, [T("nl_time"), T("nl_from"), T("nl_to"), T("nl_dir"), T("nl_gain"), T("nl_ratio")], rows)
        if spread and spread > 1.5:
            self.verdict.setText(self.verdict.text() + "  \n⚠️ " + T("nl_warn", s=f"{spread:.1f}"))
