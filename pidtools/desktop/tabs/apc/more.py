"""
APC › další struktury v desktopu: split range, regulace polohy ventilu (VPC), poměrová regulace s křížovým
omezením a interakce N×N (RGA). Výpočty v pidtools.app.apc (splitrange, vpc, ratio, rgan).
"""
import numpy as np
from PySide6.QtWidgets import QPushButton, QVBoxLayout, QWidget

from ....app.apc import ratio as aratio
from ....app.apc import rgan
from ....app.apc import splitrange as asr
from ....app.apc import vpc as avpc
from ....core import MODELS
from ....i18n import T
from ... import widgets as w
from .common import Panel


class ModelFields(QWidget):
    """Parametry modelu druhého akčního členu (stejný typ modelu jako smyčka)."""

    def __init__(self, on_change):
        super().__init__()
        self.code, self.sp, self.p0 = None, [], []
        self.lay = w.form([])
        self.reset = QPushButton(T("apc_reset"))           # zpět na výchozí model (z modelu smyčky)
        self.reset.setToolTip(T("h_apc_reset"))
        self.reset.clicked.connect(self._reset)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addLayout(self.lay)
        outer.addWidget(self.reset)
        self.on_change = on_change

    def set_model(self, code, p):
        if code != self.code:
            while self.lay.rowCount():
                self.lay.removeRow(0)
            self.sp = []
            for n in MODELS[code]["params"]:
                s = w.spin(0.0, -1e9, 1e9, 6)
                s.valueChanged.connect(self.on_change)
                s.valueChanged.connect(self._sync)
                self.lay.addRow(n, s)
                self.sp.append(s)
            self.code = code
        self.p0 = [float(v) for v in p]
        for s, v in zip(self.sp, p):
            s.blockSignals(True)
            s.setValue(float(v))
            s.blockSignals(False)
        self._sync()

    def _sync(self, *_):
        self.reset.setEnabled(any(abs(s.value() - round(v, s.decimals())) > 10 ** -s.decimals()
                                  for s, v in zip(self.sp, self.p0)))

    def _reset(self):
        for s, v in zip(self.sp, self.p0):
            s.blockSignals(True)
            s.setValue(v)
            s.blockSignals(False)
        self._sync()
        self.on_change()

    def model(self):
        p = [s.value() for s in self.sp]
        for i in range(1, len(p)):
            p[i] = max(p[i], 0.0)
        return self.code, p


def _pv(s, x):
    return s.EP(x)


class SplitRangePanel(Panel):
    _impl = None

    def impl(self):
        return self._impl

    def __init__(self, win):
        super().__init__(win, "apc_intro_split")
        self.mode = w.combo(["opposite", "sequence"], labels=[T("sr_opposite"), T("sr_sequence")])
        self.b0 = w.spin(50.0, 1.0, 99.0, 3)
        self.gap = w.spin(0.0, -20.0, 20.0, 3)
        for c in (self.mode,):
            c.currentIndexChanged.connect(self._defaults)
        for sp in (self.b0, self.gap):
            sp.valueChanged.connect(self._changed)
        w.tip(self.b0, "h_sr_b0")
        w.tip(self.gap, "h_sr_gap")
        b_reset = self.reset_button((self.b0, self.gap), lambda: (50.0, 0.0), self._changed)
        self.left.addWidget(w.group(T("sr_setup"), w.form([(T("sr_mode"), self.mode), (T("sr_b0"), self.b0),
                                                           (T("sr_gap"), self.gap), ("", b_reset)])))
        self.va = ModelFields(self._changed)
        self.left.addWidget(w.group(T("sr_valve_a"), w.form([("", self.va)])))
        self.res = w.note("")
        self.left.addWidget(self.res)
        self.halves = w.table([], [], stretch=False)
        self.halves.setMinimumHeight(110)
        self.left.addWidget(self.halves)
        self.plots = self.chart(3, ("PV", T("sr_u"), T("sr_valves")), (0.45, 0.27, 0.28))
        self.kpi = self.table(100)
        self._key = None

    def refresh(self):
        s = self.s
        if s.model is None:
            return
        key = (s.model[0], tuple(s.model[1]))
        if key != self._key:
            self._key = key
            self._defaults()
        else:
            self._changed()

    def _defaults(self, *_):
        s = self.s
        if s.model is None:
            return
        gb = asr.valve_b(s.model, self.b0.value())
        self.va.set_model(*asr.default_a(gb, self.mode.currentData()))
        self._changed()

    def _changed(self, *_):
        s = self.s
        if s.model is None or self.va.code is None:
            return
        mode, b0 = self.mode.currentData(), self.b0.value()
        gb, ga = asr.valve_b(s.model, b0), self.va.model()
        bstar = asr.balanced(ga[1][0], gb[1][0])
        ctrl = s.set_ctrl(2)
        lo0, up0 = asr.eff_gains(ga[1][0], gb[1][0], b0, mode)
        lo1, up1 = asr.eff_gains(ga[1][0], gb[1][0], bstar, mode)
        corr = s.model[1][0] / up1 if up1 else 1.0
        self.res.setText(T("sr_result", b=f"{bstar:.1f}", lo=f"{lo0:.3g}", up=f"{up0:.3g}", k=f"{up1:.3g}",
                           f=f"{corr:.3g}"))
        h0, h1 = asr.halves(ga, gb, ctrl, b0, mode), asr.halves(ga, gb, ctrl, bstar, mode)
        w.fill(self.halves, ["", T("sr_lower"), T("sr_upper")],
               [[f"{T('sr_now')} (b = {b0:.0f} %)", *(f"K {k:.3g} · Ms {m:.2f}" + ("" if st else " ⚠") for k, m, st in h0)],
                [f"{T('sr_new')} (b = {bstar:.0f} %)", *(f"K {k:.3g} · Ms {m:.2f}" + ("" if st else " ⚠") for k, m, st in h1)]])
        self.halves.resizeColumnsToContents()
        self._impl = T("g_impl_split", b=f"{bstar:.1f}", g=f"{self.gap.value():.3g}")
        runs, amp = asr.simulate(ga, gb, ctrl, b0, bstar, mode, self.gap.value(), float(s.get("samp")))
        for pl in self.plots:
            pl.clear()
        (t0, o0), (t1, o1) = runs["now"], runs["new"]
        w.line(self.plots[0], t1, _pv(s, o1["SP"]), "SP", w.C_SP, 1.3, dash=True)
        w.line(self.plots[0], t0, _pv(s, o0["PV"]), T("sr_now"), w.C_SET1, 1.6, dash=True)
        w.line(self.plots[0], t1, _pv(s, o1["PV"]), T("sr_new"), w.C_SET2, 2.0)
        w.line(self.plots[1], t0, o0["U"], T("sr_now"), w.C_SET1, 1.3, dash=True)
        w.line(self.plots[1], t1, o1["U"], T("sr_new"), w.C_SET2, 1.6)
        w.line(self.plots[2], t1, o1["VA"], T("sr_va"), "#0891b2", 1.6)
        w.line(self.plots[2], t1, o1["VB"], T("sr_vb"), w.C_MV, 1.6)
        rows = []
        for key, nm in (("now", T("sr_now")), ("new", T("sr_new"))):
            k = asr.kpis(runs[key], s.PR)
            rows.append([nm, k["iae"], k["maxdev"], k["rev"]])
        w.fill(self.kpi, [T("setting"), f"IAE [{s.get('u_pv') or 'PV'}·s]", T("kpi_maxdev", u=s.get("u_pv") or "PV"),
                          T("kpi_rev")], rows)


class VpcPanel(Panel):
    _impl = None

    def impl(self):
        return self._impl

    def __init__(self, win):
        super().__init__(win, "apc_intro_vpc")
        self.m2 = ModelFields(self._changed)
        self.left.addWidget(w.group(T("vpc_mv2"), w.form([("", self.m2)])))
        self.sp_vpc = w.spin(50.0, 5.0, 95.0, 2)
        self.factor = w.spin(5.0, 1.0, 30.0, 2, 0.5)
        self.d = w.spin(35.0, -100.0, 100.0, 2)
        for sp, k in ((self.sp_vpc, "h_vpc_sp"), (self.factor, "h_vpc_factor"), (self.d, "h_vpc_d")):
            sp.valueChanged.connect(self._changed)
            w.tip(sp, k)
        b_reset = self.reset_button((self.sp_vpc, self.factor, self.d), lambda: (50.0, 5.0, 35.0), self._changed)
        self.left.addWidget(w.group(T("vpc_setup"), w.form([(T("vpc_sp"), self.sp_vpc), (T("vpc_factor"), self.factor),
                                                            (T("vpc_d"), self.d), ("", b_reset)])))
        self.res = w.note("")
        self.left.addWidget(self.res)
        self.plots = self.chart(3, ("PV", "MV1", "MV2"), (0.4, 0.3, 0.3))
        self.kpi = self.table(100)
        self._key = None

    def refresh(self):
        s = self.s
        if s.model is None:
            return
        key = (s.model[0], tuple(s.model[1]))
        if key != self._key:
            self._key = key
            self.m2.set_model(*avpc.default_mv2(s.model))
        self._changed()

    def _changed(self, *_):
        s = self.s
        if s.model is None or self.m2.code is None:
            return
        g1, g2 = (s.model[0], list(s.model[1])), self.m2.model()
        ctrl1 = s.set_ctrl(2)
        cv, p, tc = avpc.tune_vpc(g1, g2, ctrl1, s.base_ctrl(), self.factor.value())
        self.res.setText(T("vpc_result", g=f"{cv['Gain']:.4g}", ti=f"{cv['TI']:.4g}", k=f"{p[0]:.3g}", t=f"{p[1]:.4g}",
                           th=f"{p[2]:.4g}", tc=f"{tc:.4g}"))
        self._impl = T("g_impl_vpc", sp=f"{self.sp_vpc.value():.3g}", g=f"{cv['Gain']:.4g}", ti=f"{cv['TI']:.4g}")
        runs = avpc.simulate(g1, g2, ctrl1, cv, self.d.value(), self.sp_vpc.value(), float(s.get("samp")))
        for pl in self.plots:
            pl.clear()
        (t0, o0), (t1, o1) = runs["off"], runs["on"]
        w.line(self.plots[0], t1, _pv(s, o1["SP"]), "SP", w.C_SP, 1.3, dash=True)
        w.line(self.plots[0], t0, _pv(s, o0["PV"]), T("vpc_off"), w.C_SET1, 1.6, dash=True)
        w.line(self.plots[0], t1, _pv(s, o1["PV"]), T("vpc_on"), w.C_SET2, 2.0)
        w.line(self.plots[1], t0, o0["MV1"], T("vpc_off"), w.C_SET1, 1.3, dash=True)
        w.line(self.plots[1], t1, o1["MV1"], T("vpc_on"), w.C_MV, 1.8)
        w.line(self.plots[1], t1, np.full_like(t1, self.sp_vpc.value()), T("vpc_sp_short"), "#9aa5b1", 1.0, dash=True)
        w.line(self.plots[2], t1, o1["MV2"], T("vpc_on"), "#7c3aed", 1.8)
        rows = []
        for key, nm in (("off", T("vpc_off")), ("on", T("vpc_on"))):
            k = avpc.kpis(runs[key], s.PR)
            rows.append([nm, k["iae"], k["at_lim"], k["reserve"]])
        w.fill(self.kpi, [T("setting"), f"IAE [{s.get('u_pv') or 'PV'}·s]", T("vpc_at_lim"), T("vpc_reserve")], rows)


class RatioPanel(Panel):
    _impl = None

    def impl(self):
        return self._impl

    def __init__(self, win):
        super().__init__(win, "apc_intro_ratio")
        self.src = w.combo([])
        self.src.currentIndexChanged.connect(self._src_changed)
        self.air = ModelFields(self._changed)
        self.left.addWidget(w.group(T("ra_air"), w.form([(T("ra_src"), self.src), ("", self.air)])))
        self.R = w.spin(1.2, 0.01, 100.0, 4, 0.05)
        self.step = w.spin(15.0, -50.0, 50.0, 2)
        for sp, k in ((self.R, "h_ra_R"), (self.step, "h_ra_step")):
            sp.valueChanged.connect(self._changed)
            w.tip(sp, k)
        b_reset = self.reset_button((self.R, self.step), lambda: (1.2, 15.0), self._changed)
        self.left.addWidget(w.group(T("ra_setup"), w.form([(T("ra_R"), self.R), (T("ra_step"), self.step),
                                                           ("", b_reset)])))
        self.res = w.note("")
        self.left.addWidget(self.res)
        self.plots = self.chart(2, (T("ra_flows"), "λ"), (0.62, 0.38))
        self.kpi = self.table(100)
        self._key = None

    def refresh(self):
        s = self.s
        if s.model is None:
            return
        cur = self.src.currentData()
        self.src.blockSignals(True)
        self.src.clear()
        self.src.addItem(T("ra_manual"), None)
        for i, rec in self.win.project.others():
            self.src.addItem(rec["name"], i)
        k = self.src.findData(cur)
        self.src.setCurrentIndex(max(k, 0))
        self.src.blockSignals(False)
        key = (s.model[0], tuple(s.model[1]))
        if key != self._key:
            self._key = key
            self._src_changed()
        else:
            self._changed()

    def _src_changed(self, *_):
        s = self.s
        if s.model is None:
            return
        i = self.src.currentData()
        if i is None:
            self.air.set_model(*aratio.default_air(s.model))
        else:
            rec = dict(self.win.project.others())[i]
            self.air.set_model(rec["model"][0], list(rec["model"][1]))
        self._changed()

    def _changed(self, *_):
        s = self.s
        if s.model is None or self.air.code is None:
            return
        gf, ga = (s.model[0], list(s.model[1])), self.air.model()
        ctrl = s.set_ctrl(2)
        i = self.src.currentData()
        ctrl_a = self.win.project.loops[i].set_ctrl(2) if i is not None else ctrl
        R = self.R.value()
        runs = aratio.simulate(gf, ga, ctrl, ctrl_a, R, self.step.value(), float(s.get("samp")))
        self._impl = T("g_impl_ratio", r=f"{R:.4g}")
        for pl in self.plots:
            pl.clear()
        (tc, oc), (tp, op) = runs["cross"], runs["plain"]
        w.line(self.plots[0], tc, oc["D"], T("ra_demand"), w.C_SP, 1.3, dash=True)
        w.line(self.plots[0], tc, oc["PVF"], T("ra_fuel"), w.C_MV, 2.0)
        w.line(self.plots[0], tc, oc["PVA"] / R, T("ra_air_r"), "#0891b2", 2.0)
        w.line(self.plots[0], tp, op["PVA"] / R, T("ra_air_r") + " – " + T("ra_plain"), "#9aa5b1", 1.3, dash=True)
        w.line(self.plots[1], tc, oc["LAM"], T("ra_cross"), w.C_SET2, 2.0)
        w.line(self.plots[1], tp, op["LAM"], T("ra_plain"), w.C_SET1, 1.4, dash=True)
        w.line(self.plots[1], tc, np.ones_like(tc), "λ = 1", "#dc2626", 1.0, dash=True)
        rows = []
        kc, kp = aratio.kpis(runs["cross"], s.PR), aratio.kpis(runs["plain"], s.PR)
        for k, nm in ((kp, T("ra_plain")), (kc, T("ra_cross"))):
            rows.append([nm, k["lam_min"], k["t_rich"], k["iae"]])
        w.fill(self.kpi, [T("setting"), T("ra_lam_min"), T("ra_t_rich"), T("ra_iae")], rows)
        self.res.setText(T("ra_result", a=f"{kp['lam_min']:.3f}", b=f"{kc['lam_min']:.3f}"))


class RgaPanel(Panel):
    def __init__(self, win):
        super().__init__(win, "apc_intro_rga")
        self.res = w.note("")
        self.left.addWidget(self.res)
        self.k = w.table([], [])
        self.l_tab = w.table([], [])
        self.right.addWidget(w.note("**" + T("rga_k") + "**"))
        self.right.addWidget(self.k, 1)
        self.right.addWidget(w.note("**" + T("rga_l") + "**"))
        self.right.addWidget(self.l_tab, 1)

    def records(self):
        pr = self.win.project
        a = dict(self.s.report_record(), name=pr.names()[pr.active])
        return [a] + [rec for _, rec in pr.others()]

    def refresh(self):
        s = self.s
        if s.model is None:
            return
        recs = self.records()
        if len(recs) < 2:
            self.res.setText("⚠️ " + T("apc_need_loop"))
            return
        r = rgan.analyse(recs)
        heads = [""] + [f"{T('rga_mv')} {mv}" for mv in r["mvs"]]
        w.fill(self.k, heads, [[n] + [("" if r["known"][i, j] else "? ") + f"{r['K'][i, j]:.3g}" for j in range(len(recs))]
                                for i, n in enumerate(r["names"])])
        w.fill(self.l_tab, heads, [[n] + [r["L"][i, j] for j in range(len(recs))] for i, n in enumerate(r["names"])])
        txt = [f"**NI = {r['NI']:.3g}**" if np.isfinite(r["NI"]) else ""]
        if r["pairing"] is not None:
            txt.append(T("rga_pairing") + ": " + ", ".join(f"{n} ← {r['mvs'][j]}" for n, j in zip(r["names"], r["pairing"])))
        txt += [T(k) for k in r["advice"]]
        self.res.setText("  \n".join(x for x in txt if x))
