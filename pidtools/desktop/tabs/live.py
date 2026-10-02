"""
Záložka Živá simulace: smyčka běží v reálném čase (zrychleně) – režim Auto / Ruční, SP, ruční MV, poruchy na vstupu
i výstupu procesu, šum PV, změna procesu (K, θ), srovnání sad 1 a 2, ukazatele od poslední události.
"""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QPushButton, QSlider, QVBoxLayout, QWidget

from ...app.live import LiveSession
from ...i18n import T
from .. import widgets as w

TICK_MS = 50


class LiveTab(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win, self.s = win, win.state
        self.sess = None
        lay = QVBoxLayout(self)
        # ---- ovládání
        self.b_run = QPushButton("▶")
        self.b_run.setCheckable(True)
        self.b_run.toggled.connect(self._run_toggled)
        b_reset = QPushButton(T("dk_lv_reset"))
        b_reset.clicked.connect(self.restart)
        self.speed = QSlider(Qt.Horizontal)
        self.speed.setRange(0, 100)
        self.speed.setValue(40)
        self.speed_lab = QLabel("")
        self.speed.valueChanged.connect(self._speed_label)
        self.cmp = QCheckBox(T("dk_lv_compare"))
        self.cmp.setChecked(True)
        self.cmp.toggled.connect(self.restart)
        lay.addLayout(w.hbox(self.b_run, b_reset, QLabel(T("dk_lv_speed")), self.speed, self.speed_lab, self.cmp))

        self.auto = QCheckBox("Auto")
        self.auto.setChecked(True)
        self.auto.toggled.connect(self._mode)
        self.sp = w.spin(0.0, -1e12, 1e12, 4)
        self.sp.valueChanged.connect(lambda v: self.sess and self.sess.set_sp(v))
        self.man = w.spin(0.0, -1e12, 1e12, 4)
        self.man.valueChanged.connect(self._mode)
        self.d_in = w.spin(0.0, -1e12, 1e12, 4)
        self.d_out = w.spin(0.0, -1e12, 1e12, 4)
        for sp in (self.d_in, self.d_out):
            sp.valueChanged.connect(self._dist)
        self.noise = w.spin(0.0, 0.0, 1e12, 4)
        self.k_fac = w.spin(1.0, 0.05, 20.0, 3, 0.1)
        self.th_fac = w.spin(1.0, 0.0, 20.0, 3, 0.1)
        for sp in (self.noise, self.k_fac, self.th_fac):
            sp.valueChanged.connect(self.restart)
        self.lab_sp, self.lab_man = QLabel("SP"), QLabel(T("dk_lv_man"))
        self.lab_din, self.lab_dout = QLabel(T("dk_lv_din")), QLabel(T("dk_lv_dout"))
        self.lab_noise = QLabel(T("dk_lv_noise"))
        row = QHBoxLayout()
        for wd in (self.auto, self.lab_sp, self.sp, self.lab_man, self.man, self.lab_din, self.d_in, self.lab_dout,
                   self.d_out, self.lab_noise, self.noise, QLabel(T("dk_lv_kfac")), self.k_fac,
                   QLabel(T("dk_lv_thfac")), self.th_fac):
            row.addWidget(wd)
        row.addStretch(1)
        lay.addLayout(row)
        self.chart, self.plots = w.stack(2, ["PV", "MV"], T("time_s"), heights=(0.62, 0.38))
        lay.addWidget(self.chart, 1)
        self.kpi = w.table([], [])
        self.kpi.setMaximumHeight(100)
        lay.addWidget(self.kpi)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self._curves = {}
        self._speed_label()

    # ---- životní cyklus
    def refresh(self):
        """Nové parametry sad nebo model → simulace znovu od pracovního bodu (běh zůstane zastavený)."""
        s = self.s
        if s.model is None:
            self.b_run.setChecked(False)
            self.sess = None
            return
        u_pv, u_mv = s.get("u_pv") or "PV", s.get("u_mv") or "MV"
        self.lab_sp.setText(f"SP [{u_pv}]")
        self.lab_man.setText(f"{T('dk_lv_man')} [{u_mv}]")
        self.lab_din.setText(f"{T('dk_lv_din')} [{u_mv}]")
        self.lab_dout.setText(f"{T('dk_lv_dout')} [{u_pv}]")
        self.lab_noise.setText(f"{T('dk_lv_noise')} [{u_pv}]")
        self.restart()

    def restart(self, *_):
        s = self.s
        if s.model is None:
            return
        _, _, mv_id, _ = s.segment()
        sp0 = s.sp_from_to()[0]
        sets = {1: s.set_ctrl(1), 2: s.set_ctrl(2)} if self.cmp.isChecked() else {2: s.set_ctrl(2)}
        sets = {n: {k: v for k, v in c.items() if k not in ("FF", "FF_LL")} for n, c in sets.items()}
        plant = dict(Noise=self.noise.value() / s.PR * 100, Seed=7)
        self.sess = LiveSession(s, s.model, sets, float(s.P(sp0)), float(mv_id[0]), plant)
        self.sess.set_process(self.k_fac.value(), self.th_fac.value())
        for sp, v in ((self.sp, sp0), (self.man, float(s.EM(mv_id[0])))):
            sp.blockSignals(True)
            sp.setValue(v)
            sp.blockSignals(False)
        self.sess.set_mode(self.auto.isChecked(), self.man.value())
        self.sess.set_dist(self.d_in.value(), self.d_out.value())
        for p in self.plots:
            p.clear()
        self._curves = {}
        self.draw()

    def _run_toggled(self, on):
        self.b_run.setText("⏸" if on else "▶")
        if on and self.sess is None:
            self.restart()
        if on:
            self.timer.start(TICK_MS)
        else:
            self.timer.stop()

    def _speed(self):
        return float(10 ** (self.speed.value() / 100 * 2.7))      # 1× … 500×

    def _speed_label(self):
        self.speed_lab.setText(f"{self._speed():.0f}×")

    def tick(self):
        if self.sess is None:
            return
        self.sess.advance(self._speed() * TICK_MS / 1000)
        self.draw()

    # ---- vstupy
    def _mode(self, *_):
        if self.sess:
            self.sess.set_mode(self.auto.isChecked(), self.man.value())

    def _dist(self, *_):
        if self.sess:
            self.sess.set_dist(self.d_in.value(), self.d_out.value())

    # ---- kreslení
    def draw(self):
        sess = self.sess
        if sess is None:
            return
        cols = {1: w.C_SET1, 2: w.C_SET2}
        for n in sess.loops:
            d = sess.series(n)
            if not len(d["t"]):
                continue
            if n not in self._curves:
                c = {}
                if not self._curves:
                    c["sp"] = w.line(self.plots[0], d["t"], d["SP"], "SP", w.C_SP, 1.3, dash=True)
                c["pv"] = w.line(self.plots[0], d["t"], d["PV"], T(f"set_{n}"), cols[n], 2.0, dash=n == 1)
                c["mv"] = w.line(self.plots[1], d["t"], d["MV"], f"MV {T(f'set_{n}')}", cols[n], 1.6, dash=n == 1)
                self._curves[n] = c
            c = self._curves[n]
            if "sp" in c:
                c["sp"].setData(d["t"], d["SP"])
            c["pv"].setData(d["t"], d["PV"])
            c["mv"].setData(d["t"], d["MV"])
        rows = []
        for n in sess.loops:
            k = sess.kpis(n)
            rows.append([T(f"set_{n}")] + ([k["iae"], k["maxdev"], k["travel"]] if k else ["—"] * 3))
        u_pv, u_mv = self.s.get("u_pv") or "PV", self.s.get("u_mv") or "MV"
        w.fill(self.kpi, [T("setting"), f"IAE [{u_pv}·s]", T("kpi_maxdev", u=u_pv), T("kpi_mvtravel", u=u_mv)], rows)
