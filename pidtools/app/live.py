"""
Živá simulace pro frontend, který ji počítá sám (desktop): jedna nebo dvě smyčky (sada 1 a 2) nad core.LiveLoop,
ruční / automatický režim, SP, poruchy na vstupu i výstupu procesu, změna procesu, šum PV a ukazatele od poslední
události. Vše uvnitř v % rozsahů regulátoru; vstupy a výstupy pro uživatele v inženýrských jednotkách přes Scaling.
(Webová aplikace počítá živou simulaci v prohlížeči – ui/static/live_engine.js; konfigurace pro ni: web_config.)
"""
import json

import numpy as np

from ..core import LiveLoop
from ..i18n import T
from .apc.common import tchar
from .colors import C_MV, C_PV, C_SET1, C_SET2, C_SP, FONT


def step_h(code, p, samp):
    """Krok simulace: nejvýš SampleTime, jemnější u rychlých procesů."""
    return float(min(samp, max(tchar((code, p)) / 400, samp / 10)))


class LiveSession:
    """
    Živá simulace sad regulátoru na stejném procesu. sets: {název: ctrl}; plant: dict(Noise, Stic, …) v %.
    Proces lze změnit (K a θ jako násobek modelu) – smyčky se pak spustí znovu z pracovního bodu.
    """

    def __init__(self, sc, model, sets, pv0, mv0, plant=None, window=None):
        self.sc, self.model, self.sets = sc, model, dict(sets)
        self.pv0, self.mv0 = float(pv0), float(mv0)
        self.plant = dict(plant or {})
        code, p, _ = model
        self.h = step_h(code, p, min(c["SampleTime"] for c in self.sets.values()))
        self.window = window or max(60 * tchar((code, p)), 600 * self.h)
        self.k_fac, self.th_fac = 1.0, 1.0
        self.sp, self.auto, self.u_man = self.pv0, True, self.mv0
        self.d_in, self.d_out = 0.0, 0.0
        self.shape = dict(kind="step", period=60.0, t0=0.0)    # tvar poruch: step, ramp, sine, random, pulse
        self._rnd, self._rnd_val, self._rnd_k = np.random.default_rng(1), 0.0, -1
        self.events = []
        self.reset()

    # ---- stav
    def reset(self):
        code, p, _ = self.model
        q = list(p)
        q[0] *= self.k_fac
        q[-1] *= self.th_fac
        n_hist = int(self.window / self.h) + 2
        self.loops = {n: LiveLoop(code, q, c, self.h, self.pv0, self.mv0, self.plant, history=n_hist)
                      for n, c in self.sets.items()}
        self.t = 0.0
        self.mark = 0.0
        self.events = []

    def set_process(self, k_fac=1.0, th_fac=1.0):
        self.k_fac, self.th_fac = float(k_fac), float(th_fac)
        self.reset()

    def set_tuning(self, sets):
        """Nové parametry sad za běhu (bez rázu výstupu)."""
        for n, c in sets.items():
            self.sets[n] = c
            if n in self.loops:
                self.loops[n].set_tuning(c)

    def event(self, label):
        """Událost (změna SP, poruchy, režimu) – od ní se počítají ukazatele."""
        self.events.append((self.t, label))
        self.mark = self.t

    # ---- vstupy v inženýrských jednotkách
    def set_sp(self, sp_e):
        self.sp = float(self.sc.P(sp_e))
        self.event("SP")

    def set_mode(self, auto, u_man_e=None):
        self.auto = bool(auto)
        if u_man_e is not None:
            self.u_man = float(self.sc.M(u_man_e))
        self.event("A" if auto else "M")

    def set_dist(self, d_in_e=None, d_out_e=None, kind=None, period=None):
        """
        Porucha na vstupu procesu [jednotky MV] a na výstupu [jednotky PV] (amplitudy) a její tvar: step (skok),
        ramp (náběh za periodu), sine (sinus s periodou), random (náhodná změna každou periodu), pulse (pulz délky
        poloviny periody, opakovaně).
        """
        if d_in_e is not None:
            self.d_in = float(d_in_e) / self.sc.MR * 100
        if d_out_e is not None:
            self.d_out = float(d_out_e) / self.sc.PR * 100
        if kind is not None:
            self.shape["kind"] = kind
        if period is not None:
            self.shape["period"] = max(float(period), 1e-3)
        self.shape["t0"] = self.t
        self._rnd = np.random.default_rng(int(self.t * 1000) % 2 ** 31)
        self._rnd_val, self._rnd_k = 0.0, -1
        self.event("D")

    def _shape(self, t):
        """Násobek amplitudy poruchy v čase t (0 … 1, u sinu −1 … 1)."""
        k, per, t0 = self.shape["kind"], self.shape["period"], self.shape["t0"]
        x = t - t0
        if k == "ramp":
            return min(max(x / per, 0.0), 1.0)
        if k == "sine":
            return float(np.sin(2 * np.pi * x / per))
        if k == "pulse":
            return 1.0 if (x % per) < per / 2 else 0.0
        if k == "random":
            n = int(x // per)
            if n != self._rnd_k:
                self._rnd_k, self._rnd_val = n, float(self._rnd.uniform(-1, 1))
            return self._rnd_val
        return 1.0

    # ---- běh
    def advance(self, seconds):
        """Posun o seconds; u proměnných poruch po krocích (≤ 1/40 periody), aby tvar zůstal zachovaný."""
        k = self.shape["kind"]
        chunk = seconds if k == "step" else max(self.h, min(seconds, self.shape["period"] / 40))
        done = 0.0
        while done < seconds - 1e-9:
            dt = min(chunk, seconds - done)
            f = self._shape(self.t + dt / 2) if k != "step" else 1.0
            for lp in self.loops.values():
                lp.advance(dt, self.sp, self.auto, self.u_man, self.d_in * f, self.d_out * f)
            self.t = next(iter(self.loops.values())).t
            done += dt

    def to_frame(self):
        """Průběhy všech sad v jednotkách (export CSV)."""
        import pandas as pd
        cols = {}
        for n in self.loops:
            d = self.series(n)
            cols.setdefault("t [s]", d["t"])
            cols.setdefault("SP", d["SP"])
            cols[f"PV {n}"], cols[f"MV {n}"] = d["PV"], d["MV"]
        m = min(len(v) for v in cols.values())
        return pd.DataFrame({k: v[-m:] for k, v in cols.items()})

    def series(self, n):
        """Průběhy sady n v inženýrských jednotkách: dict(t, SP, PV, MV)."""
        hi = self.loops[n].hist
        return dict(t=np.asarray(hi["t"]), SP=self.sc.EP(np.asarray(hi["SP"])), PV=self.sc.EP(np.asarray(hi["PV"])),
                    MV=self.sc.EM(np.asarray(hi["MV"])))

    def kpis(self, n):
        """Ukazatele sady n od poslední události: IAE [PV·s], max. odchylka [PV], dráha MV [MV]."""
        hi = self.loops[n].hist
        t = np.asarray(hi["t"])
        m = t >= self.mark
        if m.sum() < 2:
            return None
        e = (np.asarray(hi["SP"])[m] - np.asarray(hi["PV"])[m]) * self.sc.PR / 100
        mv = np.asarray(hi["MV"])[m] * self.sc.MR / 100
        return dict(iae=float(np.sum(np.abs(e)) * self.h), maxdev=float(np.max(np.abs(e))),
                    travel=float(np.abs(np.diff(mv)).sum()))


SPEEDS = [1, 5, 20, 100, 500]
_LV_KEYS = ("compare", "advanced", "sec_tune", "apply", "revert", "tune_hint", "gain", "sec_dist", "dist_type", "dist_loc",
            "dt_step", "dt_ramp", "dt_sine", "dt_random", "dt_pulse", "loc_in", "loc_out", "dist_amp", "dist_sigma",
            "dist_short", "pp_step", "pp_ramp", "pp_sine", "pp_random", "pp_pulse", "pulse_go", "sec_meas", "noise", "pvf",
            "meas_hint", "sec_plant", "pk", "pt", "pth", "stic", "plant_hint", "sec_view", "window", "win_auto",
            "view_hint", "zoomed", "kpi_since", "kpi_maxdev", "kpi_over", "kpi_settle", "kpi_travel", "ev_tune",
            "ev_set", "ev_dist", "ev_applied", "chart", "kpi_title", "kpi_note", "sec_mode", "both_run", "lcmp")


def ctrl_js(c):
    """Parametry regulátoru pro JS (nekonečno → null, jen potřebné klíče)."""
    keys = ("Gain", "TI", "TD", "DiffGain", "SampleTime", "PropFacSP", "PropFbk", "DiffFbk", "DeadBand", "DbMode", "MV_Lo",
            "MV_Hi", "PVFilt", "MVRate", "SPRate")
    out = {}
    for k in keys:
        if k in c:
            v = c[k]
            out[k] = None if isinstance(v, float) and not np.isfinite(v) else (
                float(v) if isinstance(v, (int, float, np.floating)) and not isinstance(v, bool) else v)
    return out


def block_summary(samp, diffgain, propfac, dfb, g, ti, td):
    """Shrnutí bloku PIDConL a sady 1 pro panel simulace."""
    return T("blk_summary", s=f"{samp:g}", dg=f"{diffgain:g}", p=f"{propfac:g}", d="✓" if dfb else "✗", g=f"{g:.4g}",
             ti=f"{ti:.4g}", td=f"{td:.4g}")


def web_config(*, model, samp, pv0, mv0, set1, set2, plant, pv_rng, mv_rng, u_pv, u_mv, pvfilt, height, scope,
               summary, lang):
    """
    Konfigurace živé simulace pro prohlížeč (live_ui.js): model, sady 1 a 2, rozsahy, jednotky, okno, rychlosti,
    proces a ventil, barvy a texty (v aktuálním jazyce T). pv0, mv0 = pracovní bod v % rozsahů; scope = identita
    simulace v prohlížeči (soubor a smyčka; z ní a z modelu vzniká sim_id, pod kterým se drží stav).
    """
    mcode, p, _ = model
    (pv_lo, pv_hi), (mv_lo, mv_hi) = pv_rng, mv_rng
    lags = (p[1] if mcode in ("P1D", "P2D", "I1D") else 0.0) + (p[2] if mcode == "P2D" else 0.0)
    window = float(np.clip(12 * (p[-1] + lags + samp), 60.0, 7200.0))
    plant = {k: (float(v) if isinstance(v, (int, float, np.floating)) else v)
             for k, v in (plant or {}).items() if k in ("Stic", "SticJ", "ValveChar", "Noise")}
    h = float(min(samp, max(0.05, samp / 5)))
    PR = pv_hi - pv_lo
    cfg = dict(code=mcode, p=[float(v) for v in p], h=h, pv0=float(pv0), mv0=float(mv0), plant=plant, window=window,
               speeds=SPEEDS, speed0=next((v for v in SPEEDS if v >= window / 90), SPEEDS[-1]),  # okno za ~1,5 min
               sets={"1": ctrl_js(set1), "2": ctrl_js(set2)},
               pv_lo=float(pv_lo), pv_hi=float(pv_hi), mv_lo=float(mv_lo), mv_hi=float(mv_hi),
               u_pv=u_pv or "", u_mv=u_mv or "", lab_pv=f"PV [{u_pv}]" if u_pv else "PV",
               lab_mv=f"MV [{u_mv}]" if u_mv else "MV", font=FONT,
               labels=dict(start=T("live_start"), pause=T("live_pause"), reset=T("live_reset"),
                           lspeed=T("live_speed"), lset=T("live_active"), lmode=T("live_mode"),
                           set1=T("set_1"), set2=T("set_2"), lsp=T("live_sp", u=u_pv or "PV"),
                           lmv=T("live_mv", u=u_mv or "MV"), ld=T("live_dist", u=u_mv or "MV"),
                           d0=T("live_d0"), valve=T("valve_pos"), time=T("time_s"), read=T("live_read")))
    cfg.update(
        sim_id=f"{scope}|{mcode}|{[round(float(v), 6) for v in p]}|{h}|{json.dumps(plant)}|"
               f"{pv_lo}|{pv_hi}|{mv_lo}|{mv_hi}",
        ch=int(height), noise0=float(plant.get("Noise", 0.0) * PR / 100), pvf0=float(pvfilt or 0.0),
        pvf_max=float(max(10 * samp, 0.5 * (lags + p[-1]), 5.0)),
        dist_p0=float(max(4 * (lags + p[-1]), 10 * samp)), dist_pmax=float(max(40 * (lags + p[-1]), 100 * samp)),
        decimal="," if lang == "cs" else ".",
        light=dict(pv=C_PV, sp=C_SP, mv=C_MV, set1=C_SET1, set2=C_SET2, dist="#7c3aed", event="#b45309", acc="#1f5fa8"),
        dark=dict(pv="#60a5fa", sp="#9aa5b1", mv="#fb923c", set1="#94a3b8", set2="#4ade80", dist="#a78bfa",
                  event="#fbbf24", acc="#60a5fa"))
    cfg["labels"].update({k: T("lv_" + k) for k in _LV_KEYS})
    cfg["labels"].update(blk=summary, desc=T("live_sim_desc"), help=T("live_help"))
    return cfg


def web_config_ws(ws):
    """web_config ze stavu pracovního prostoru (API); stejné hodnoty jako ze Streamlitu."""
    from .. import i18n
    mask = ws.sel_mask
    pv_id, mv_id = ws.pv[mask], ws.mv[mask]
    pv0 = float(np.nanmedian(ws.sp[mask])) if ws.grid.has_sp else float(pv_id[0])
    g = ws.get
    summary = block_summary(float(g("samp")), float(g("diffgain")), float(g("propfac")), bool(g("dfb")),
                            float(g("set1_gain", 1.0)), float(g("set1_ti", 100.0)), float(g("set1_td", 0.0)))
    return web_config(model=ws.model, samp=float(g("samp")), pv0=pv0, mv0=float(mv_id[0]), set1=ws.set_ctrl(1),
                      set2=ws.set_ctrl(2), plant=ws.plant(), pv_rng=(ws.pv_lo, ws.pv_hi), mv_rng=(ws.mv_lo, ws.mv_hi),
                      u_pv=g("u_pv", ""), u_mv=g("u_mv", ""), pvfilt=float(g("pvfilt", 0.0)),
                      height=g("plot_h", 460), scope=f"{ws.fname}|0", summary=summary, lang=i18n.lang())
