"""
APC › Gain scheduling podle pracovního bodu (PV): úseky dat pro body, model a ladění v každém bodě, tabulka pro
blok GainSched a simulace na nelineárním procesu (jedna sada vs. scheduling).
"""
import numpy as np
from PySide6.QtWidgets import QPushButton, QTableWidget, QTableWidgetItem

from ....app.apc import gainsched as ags
from ....app.apc.common import tchar
from ....core import MODELS
from ....i18n import T
from ... import widgets as w
from .common import Panel

METHODS = ["SIMC", "AMIGO", "OPT"]


class GainSchedPanel(Panel):
    def impl(self):
        return T("g_impl_gainsched", u=self.s.get("u_pv") or "PV")

    def __init__(self, win):
        super().__init__(win, "apc_intro_gainsched")
        self.n = w.combo([2, 3], 3)
        self.ranges = QTableWidget(3, 2)
        self.ranges.setMaximumHeight(130)
        b_auto = QPushButton(T("gs_auto"))
        b_auto.clicked.connect(self._auto)
        self.b_fit = QPushButton(T("dk_gs_fit"))
        self.b_fit.clicked.connect(self._fit)
        self.left.addWidget(w.group(T("dk_gs_points"), w.form([(T("dk_gs_n"), self.n), ("", self.ranges),
                                                              ("", w.hbox(b_auto, self.b_fit))])))
        self.method = w.combo(METHODS, labels=[T("m_" + m) for m in METHODS])
        self.ctype = w.combo(["PI", "PID"])
        self.tcf = w.spin(1.0, 0.1, 10.0, 2, 0.1)
        self.ms = w.spin(1.6, 1.2, 2.5, 2, 0.1)
        for c in (self.method, self.ctype):
            c.currentIndexChanged.connect(self._retune)
        for sp in (self.tcf, self.ms):
            sp.valueChanged.connect(self._retune)
        b_reset = self.reset_button((self.tcf, self.ms), lambda: (1.0, 1.6), self._retune)
        self.left.addWidget(w.group(T("method"), w.form([(T("method"), self.method), (T("ctrl_type"), self.ctype),
                                                         (T("dk_gs_tcf"), self.tcf), ("Ms", self.ms), ("", b_reset)])))
        self.vals = w.table([], [], stretch=False)
        self.vals.setMinimumHeight(150)
        self.left.addWidget(w.group(T("dk_gs_table"), w.form([("", self.vals)])))
        self.msg = w.note("")
        self.left.addWidget(self.msg)
        self.left.addStretch(1)
        self.plots = self.chart(3, ("PV", "MV", "Gain"), (0.5, 0.27, 0.23))
        self.kpi = self.table(120)

    # ---- body
    def _ranges(self):
        out = []
        for i in range(self.ranges.rowCount()):
            try:
                out.append((float(self.ranges.item(i, 0).text()), float(self.ranges.item(i, 1).text())))
            except (AttributeError, ValueError):
                pass
        return out

    def _show_ranges(self, rg):
        self.ranges.setRowCount(len(rg))
        self.ranges.setHorizontalHeaderLabels([T("dk_from"), T("dk_to")])
        for i, (a, b) in enumerate(rg):
            self.ranges.setItem(i, 0, QTableWidgetItem(f"{a:.0f}"))
            self.ranges.setItem(i, 1, QTableWidgetItem(f"{b:.0f}"))

    def _auto(self):
        s = self.s
        g = s.grid
        rg = ags.auto_ranges(g.t, s.pv, s.mv, s.sp, g.Ts, g.has_sp, 4 * tchar(s.model), int(self.n.currentData()))
        self._show_ranges(rg)

    def refresh(self):
        s = self.s
        if s.model is None:
            return
        if MODELS[s.model[0]]["integ"]:         # scheduling je navržený pro samoregulační procesy
            self.msg.setText("⚠️ " + T("gs_integ"))
            return
        if not self._ranges():
            rg = [tuple(s.get(f"gs_r{i + 1}")) for i in range(3) if s.get(f"gs_r{i + 1}")]
            if rg:
                self._show_ranges(rg)
            else:
                self._auto()
        self._retune()

    def _fit(self):
        s = self.s
        rg = self._ranges()
        code = s.model[0]
        g = s.grid
        for i, r in enumerate(rg):
            s.settings[f"gs_r{i + 1}"] = list(r)
        self.b_fit.setEnabled(False)
        self.win.status(T("dk_identifying"))

        def done(res):
            self.b_fit.setEnabled(True)
            self.win.status("")
            pts, err = res
            if err:
                self.win.error(err)
                return
            s.settings["gs_pts"] = pts
            s.settings["gs_key"] = ags.key(code, rg, s.norm)
            self._retune()

        w.run_task(lambda _p: ags.fit_points(code, rg, g.t, s.pv, s.mv, g.Ts), done, self.win.error)

    # ---- ladění bodů, tabulka a simulace
    def _retune(self, *_):
        s = self.s
        if self._busy or s.model is None or MODELS[s.model[0]]["integ"]:
            return
        pts_raw = s.get("gs_pts")
        if s.get("gs_key") and pts_raw:
            new = ags.rescale(s.get("gs_key"), ags.key(s.model[0], [tuple(x) for x in self._ranges()], s.norm), pts_raw)
            if new is not None:
                s.settings["gs_pts"], pts_raw = new, new
        pts = ags.points(pts_raw)
        if len(pts) < 2:
            self.msg.setText(T("dk_gs_need"))
            for pl in self.plots:
                pl.clear()
            return
        code = s.model[0]
        m = self.method.currentData()
        for q in pts:
            r = ags.tune_point(code, q["p"], m, self.ctype.currentData(), float(s.get("samp")),
                               float(s.get("diffgain")), self.tcf.value(), self.ms.value())
            q.update(gain=float(r["Kc"]), ti=float(r["Ti"]) if r["Ti"] > 0 else np.inf, td=float(r["Td"]))
        tab, filled = ags.table(pts, s.EP, s.get("u_pv") or "PV")
        w.fill(self.vals, [T("gs_in"), "1", "2", "3", T("sm_apl_unit")], [[nm, *vals, u] for nm, vals, u in tab])
        self.vals.resizeColumnsToContents()
        self.msg.setText(T("dk_gs_fits", f=", ".join(f"{q['fit']:.0f} %" for q in pts)) +
                         ("  \n" + T("dk_gs_filled") if filled else ""))
        sim = ags.simulate_pv(code, pts, s.base_ctrl(), s.set_ctrl(2), float(s.get("samp")))
        for pl in self.plots:
            pl.clear()
        t, sp = sim["t"], sim["sp"]
        tf, of = sim["fixed"]
        ts_, os_ = sim["sched"]
        w.line(self.plots[0], t, s.EP(sp), "SP", w.C_SP, 1.3, dash=True)
        w.line(self.plots[0], tf, s.EP(of["PV"]), T("gs_fixed"), w.C_SET1, 1.6, dash=True)
        w.line(self.plots[0], ts_, s.EP(os_["PV"]), T("gs_sched"), w.C_SET2, 2.0)
        w.line(self.plots[1], tf, s.EM(of["MV"]), T("gs_fixed"), w.C_SET1, 1.4, dash=True)
        w.line(self.plots[1], ts_, s.EM(os_["MV"]), T("gs_sched"), w.C_SET2, 1.6)
        w.line(self.plots[2], tf, of["Gain"], T("gs_fixed"), w.C_SET1, 1.4, dash=True)
        w.line(self.plots[2], ts_, os_["Gain"], T("gs_sched"), w.C_SET2, 1.6)
        f = s.PR / 100
        w.fill(self.kpi, [T("gs_step"), T("gs_iae_fixed"), T("gs_iae_sched")],
               [[f"{float(s.EP(a)):.4g} → {float(s.EP(b)):.4g}", i1 * f, i2 * f] for a, b, i1, i2 in sim["iae"]])
