"""
APC › Kaskáda: model vnitřní smyčky (ručně nebo z dat), ladění vnitřní a vnější smyčky, oddělení rychlostí,
simulace kaskády. Aktivní smyčka je vnější.
"""
from PySide6.QtWidgets import QPushButton, QStackedWidget, QWidget

from ....app.apc import cascade as acas
from ....core import MODELS, default_tc
from ....i18n import T
from ... import widgets as w
from .common import Panel

METHODS = ["SIMC", "AMIGO", "OPT"]


class CascadePanel(Panel):
    def __init__(self, win):
        super().__init__(win, "cas_intro")
        self.src = w.combo(["loop", "manual", "data"], labels=[T("cas_src_loop"), T("cas_src_manual"), T("cas_src_data")])
        self.src.currentIndexChanged.connect(self._src_changed)
        self.stack = QStackedWidget()
        lp = QWidget()
        self.iloop = w.combo([])
        self.iloop.currentIndexChanged.connect(self._update)
        self.iloop_lab = w.note("")
        lp.setLayout(w.form([(T("cas_iloop"), self.iloop), ("", self.iloop_lab)]))
        self.stack.addWidget(lp)
        man = QWidget()
        self.k, self.t1, self.t2, self.th = (w.spin(v, lo, 1e9, 4) for v, lo in ((1.0, -1e9), (5.0, 1e-3), (0.0, 0.0),
                                                                                (1.0, 0.0)))
        man.setLayout(w.form([("K", self.k), ("T1 [s]", self.t1), ("T2 [s]", self.t2), ("θ [s]", self.th)]))
        dat = QWidget()
        self.ipv, self.imv = w.combo([]), w.combo([])
        self.ilo, self.ihi = w.spin(0.0, -1e12, 1e12, 4), w.spin(100.0, -1e12, 1e12, 4)
        b_fit = QPushButton(T("cas_fit"))
        b_fit.clicked.connect(self._fit_inner)
        self.fit_lab = w.note("")
        dat.setLayout(w.form([(T("cas_ipv"), self.ipv), (T("cas_imv"), self.imv), (T("cas_ilo"), self.ilo),
                              (T("cas_ihi"), self.ihi), ("", b_fit), ("", self.fit_lab)]))
        self.stack.addWidget(man)
        self.stack.addWidget(dat)
        self.left.addWidget(w.group(T("cas_inner"), w.form([(T("cas_src"), self.src), ("", self.stack)])))
        self.im = w.combo(METHODS, labels=[T("m_" + m) for m in METHODS])
        self.samp_i = w.spin(1.0, 0.001, 1e6, 3)
        self.tci = w.spin(1.0, 0.001, 1e9, 4)
        self.left.addWidget(w.group(T("cas_inner_tune"), w.form([(T("method"), self.im), (T("cas_samp"), self.samp_i),
                                                                  (T("tc"), self.tci)])))
        self.om = w.combo(METHODS, labels=[T("m_" + m) for m in METHODS])
        self.oct = w.combo(["PI", "PID"])
        self.tco = w.spin(1.0, 0.001, 1e9, 4)
        self.left.addWidget(w.group(T("cas_outer_tune"), w.form([(T("method"), self.om), (T("ctrl_type"), self.oct),
                                                                  (T("tc"), self.tco)])))
        self.res = w.note("")
        self.left.addWidget(self.res)
        self.left.addStretch(1)
        for c in (self.im, self.om, self.oct):
            c.currentIndexChanged.connect(self._update)
        for sp in (self.k, self.t1, self.t2, self.th, self.samp_i, self.tci, self.tco):
            sp.valueChanged.connect(self._update)
        self.plots = self.chart(3, ("PV", T("cas_inner_pct"), T("cas_valve_pct")), (0.45, 0.3, 0.25))
        self.inner_fit = None
        self._tc_manual = {"i": False, "o": False}

    def refresh(self):
        s = self.s
        if s.model is None:
            return
        self._busy = True
        cur = self.iloop.currentData()
        self.iloop.clear()
        for i, rec in self.win.project.others(include_without_model=True):
            self.iloop.addItem(rec["name"], i)
        if cur is not None and self.iloop.findData(cur) >= 0:
            self.iloop.setCurrentIndex(self.iloop.findData(cur))
        if self.iloop.count() == 0 and self.src.currentData() == "loop":
            self.src.setCurrentIndex(1)
            self.stack.setCurrentIndex(1)
        sigs = s.sig.sigs
        for c in (self.ipv, self.imv):
            cur = c.currentData()
            c.clear()
            for sg in sigs:
                c.addItem(str(sg), sg)
            if cur in sigs:
                c.setCurrentIndex(sigs.index(cur))
        self.samp_i.setValue(float(s.get("cas_samp", s.get("samp"))))
        self._busy = False
        self._update()

    def _src_changed(self):
        self.stack.setCurrentIndex(self.src.currentIndex())
        self._update()

    def _inner(self):
        if self.src.currentData() == "loop":
            i = self.iloop.currentData()
            m = self.win.project.loops[i].model if i is not None else None
            if m is None:
                self.iloop_lab.setText(T("cas_loop_nomodel", n=self.iloop.currentText()) if i is not None else "")
                return None
            pars = ", ".join(f"{n} = {v:.4g}" for n, v in zip(MODELS[m[0]]["params"], m[1]))
            self.iloop_lab.setText(T("cas_loop_model", n=self.iloop.currentText(), m=T("model_" + m[0]), p=pars))
            return m[0], list(m[1])
        if self.src.currentData() == "manual":
            return acas.manual_inner(self.k.value(), self.t1.value(), self.t2.value(), self.th.value())
        if self.inner_fit:
            return self.inner_fit["code"], list(self.inner_fit["p"])
        return None

    def _fit_inner(self):
        from ....app.dataset import on_grid
        s = self.s
        m = s.sel_mask
        ts, _, _, _ = s.segment()
        ipv = (on_grid(s.sig, s.grid, self.ipv.currentData())[m] - self.ilo.value()) / max(self.ihi.value() - self.ilo.value(), 1e-9) * 100
        imv = s.M(on_grid(s.sig, s.grid, self.imv.currentData(), zoh=True)[m])
        best, errs = acas.fit_inner(ts, ipv, imv, s.grid.Ts)
        for e in errs:
            self.win.error(T(e))
        if best:
            self.inner_fit = best
            pars = ", ".join(f"{n} = {v:.4g}" for n, v in zip(MODELS[best["code"]]["params"], best["p"]))
            self.fit_lab.setText(T("cas_inner_fit", m=T("model_" + best["code"]), f=f"{best['fit']:.1f}", p=pars))
        self._update()

    def _update(self, *_):
        s = self.s
        if self._busy or s.model is None:
            return
        inner = self._inner()
        if inner is None:
            self.res.setText(T("cas_need_inner"))
            return
        ci, pi = inner
        samp, dg = float(s.get("samp")), float(s.get("diffgain"))
        samp_i = self.samp_i.value()
        s.settings["cas_samp"] = samp_i
        self._busy = True
        if self.im.currentData() == "SIMC" and self.sender() is not self.tci:
            self.tci.setValue(default_tc(ci, pi, samp_i))
        self._busy = False
        si = acas.tune_loop(ci, pi, self.im.currentData(), "PI", samp_i, dg,
                            self.tci.value() if self.im.currentData() == "SIMC" else None)
        ictrl = acas.inner_ctrl(si, dg, samp_i)
        t63, tc_eff = acas.inner_response(ci, pi, ictrl, samp_i)
        co, po = acas.outer_model(s.model, tc_eff, pi[-1])
        oct_ = self.oct.currentData()
        self._busy = True
        if self.om.currentData() == "SIMC" and self.sender() is not self.tco:
            self.tco.setValue(default_tc(co, po, samp, "SIMC", oct_, dg))
        self._busy = False
        tco = self.tco.value() if self.om.currentData() == "SIMC" else None
        so = acas.tune_loop(co, po, self.om.currentData(), oct_, samp, dg, tco)
        octrl = dict(s.base_ctrl(), Gain=so["Kc"], TI=so["Ti"], TD=so["Td"], MV_Lo=0.0, MV_Hi=100.0)
        sep = acas.separation(tco, so, t63)
        self.res.setText(
            f"**{T('cas_inner')}:** Gain = {si['Kc']:.4g}, TI = {si['Ti']:.4g} s · {T('cas_t63')} {t63:.3g} s  \n"
            f"**{T('cas_outer_tune')}:** Gain = {so['Kc']:.4g}, TI = {so['Ti']:.4g} s, TD = {so['Td']:.4g} s  \n"
            f"{T('cas_sep')}: {sep:.1f}×" + ("  \n⚠️ " + T("cas_sep_warn") if sep < 4 else ""))
        ts, oc, ok = acas.simulate(inner, ictrl, (s.model[0], s.model[1]), octrl, samp, samp_i, po, co, tco)
        for pl in self.plots:
            pl.clear()
        if not ok:
            self.res.setText(self.res.text() + "  \n⛔ " + T("err_sim_unstable", n=T("apc_cascade")))
            return
        w.line(self.plots[0], ts, s.EP(oc[:, 0]), "SP", w.C_SP, 1.3, dash=True)
        w.line(self.plots[0], ts, s.EP(oc[:, 1]), T("cas_pv_o"), w.C_PV, 2.0)
        w.line(self.plots[1], ts, oc[:, 2], T("cas_sp_i"), w.C_SP, 1.3, dash=True)
        w.line(self.plots[1], ts, oc[:, 3], T("cas_pv_i"), w.C_SET2, 2.0)
        w.line(self.plots[2], ts, oc[:, 4], T("cas_valve"), w.C_MV, 1.8)
