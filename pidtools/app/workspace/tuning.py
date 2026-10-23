"""
Ladění a simulace: blok PIDConL a sady parametrů, dopředná vazba, metody a návrh ladění, porovnání metod,
robustnost sad a scénář (M4c).
"""
import numpy as np

from ...core import pidconl_sim_full
from .. import feedforward as ffm
from .. import scenario as scn
from .. import tuning as tun
from ..loop import block_ctrl, set_ctrl


class TuningMixin:
    """Část pracovního prostoru – metody pracují se stavem Workspace (self)."""

    def compare_methods(self):
        """Srovnání všech metod a kritérií pro PI i PID (app.tuning.compare)."""
        code, p, pdl = self.model
        avg = (10.0, 10.0) if "AVG" in tun.methods(code, p) else None
        req = tun.Request(ms=float(self.get("opt_ms")), target=self.get("opt_target"),
                          ovs=float(self.get("opt_ovs")) / 100)
        return tun.compare(code, p, pdl, self.base_ctrl(), req, avg, self.sigma_pv(),
                           tun.robust_models(p, self.unc_models(), bool(self.get("opt_robust"))))

    # ---- blok PIDConL a sady
    def base_ctrl(self):
        lo = self.get("mvl_lo", self.mv_lo)
        hi = self.get("mvl_hi", self.mv_hi)
        return block_ctrl(self, float(self.get("samp")), float(self.get("diffgain")), float(self.get("propfac")),
                          bool(self.get("dfb")), float(self.get("db")), self.get("db_mode"), lo, hi,
                          float(self.get("pvfilt")), float(self.get("mvrate")), float(self.get("sprate")))

    def ff(self):
        code, p, pdl = self.model
        des = ffm.design(code, p, pdl, self.ff_state)
        return ffm.to_ctrl(des)

    def set_ctrl_plain(self, n):
        """Sada n bez dopředné vazby (regulátor ze záznamu pro identifikaci v uzavřené smyčce)."""
        return set_ctrl(self.base_ctrl(), float(self.get(f"set{n}_gain")), float(self.get(f"set{n}_ti")),
                        float(self.get(f"set{n}_td")), [], [])

    def set_ctrl(self, n):
        ff, ffll = self.ff() if self.model else ([], [])
        return set_ctrl(self.base_ctrl(), float(self.get(f"set{n}_gain")), float(self.get(f"set{n}_ti")),
                        float(self.get(f"set{n}_td")), ff, ffll)

    def methods(self):
        code, p, _ = self.model
        return tun.methods(code, p)

    def request(self, method=None, tc=None):
        m = method or self.get(f"method|{self.get('mcode')}", tun.DEFAULT_METHOD)
        avg = None
        if m == "AVG":      # změna PV a MV pro průměrování (výchozí 10 % rozsahů, jako ve webu)
            avg = (float(self.get("avg_dpv", 0.1 * self.PR)) / self.PR * 100,
                   float(self.get("avg_dmv", 0.1 * self.MR)) / self.MR * 100)
        hf = None
        if self.get("ctype") == "PID":           # limit šumu MV [jednotky MV] → limit VF zesílení
            hf = tun.hf_max(float(self.get("opt_noise", 0.01 * self.MR)), self.MR, self.sigma_pv())
        return tun.Request(m, self.get("ctype"), tc, avg, float(self.get("opt_ms")), hf, self.get("opt_crit"),
                           self.get("opt_target"), float(self.get("opt_ovs")) / 100)

    def suggest(self, method=None, tc=None, solvers=tun.SOLVERS):
        code, p, pdl = self.model
        robust = tun.robust_models(p, self.unc_models(), bool(self.get("opt_robust")))
        req = self.request(method, tc)
        scen = self.scen_built() if (req.method == "OPT" and req.target == "scen") else None
        return tun.suggest(code, p, pdl, self.base_ctrl(), req, robust, scen, solvers)

    def d_advice(self):
        """Doporučení D složky (PI / PID) podle poměru zpoždění a časových konstant."""
        from ...core import d_advice
        code, p, _ = self.model
        return d_advice(code, tun.p_eff(p, float(self.get("samp"))))

    def write_set(self, n, s, log=None):
        """Parametry do sady n; log = popis pro historii ladění (metoda, scénář, IAE…), None = nezaznamenávat."""
        self.set(**{f"set{n}_gain": float(s["Kc"]), f"set{n}_ti": float(s["Ti"]), f"set{n}_td": float(s["Td"])})
        if log is not None:
            import datetime as _dt
            m = self.set_metrics(n) if self.model is not None else {}
            ms = m.get("Ms") if m.get("stable") else None
            entry = dict(time=_dt.datetime.now().strftime("%Y-%m-%d %H:%M"), set=n, Kc=float(s["Kc"]), Ti=float(s["Ti"]),
                         Td=float(s["Td"]), model=self.get("mcode"), Ms=None if ms is None else float(ms), **log)
            self.settings["tune_hist"] = [entry] + list(self.get("tune_hist") or [])[:49]

    def history(self):
        """Historie ladění (nejnovější první): [dict(time, set, method, scen, Kc, Ti, Td, Ms, iae, model)]."""
        return [e for e in (self.get("tune_hist") or []) if isinstance(e, dict) and "Kc" in e]

    def set_metrics(self, n):
        code, p, _ = self.model
        return tun.set_metrics(code, p, self.set_ctrl(n), self.sigma_pv(), self.unc_models())

    def sigma_pv(self):
        try:
            return self.evaluate()["sigma_pv"]
        except Exception:
            return 0.0

    # ---- scénář
    def sp_from_to(self):
        if self.sim_sp:
            return self.sim_sp
        m = self.sel_mask
        sp0 = float(self.EP(np.nanmedian(self.sp[m]) if self.grid.has_sp else self.pv[m][0]))
        return float(f"{sp0:.5g}"), float(f"{sp0 + 0.05 * self.PR:.5g}")

    def sim_length(self):
        code, p, _ = self.model
        samp = float(self.get("samp"))
        r = tun.suggest(code, p, [], self.base_ctrl(), tun.Request("SIMC", self.get("ctype")))
        prop = dict(self.base_ctrl(), Gain=r["Kc"], TI=r["Ti"] if r["Ti"] > 0 else np.inf, TD=r["Td"])
        ts, _, _, _ = self.segment()
        return scn.auto_length(code, p, (self.set_ctrl(1), self.set_ctrl(2), prop), scn.t_char(code, p, 0, samp),
                               samp, ts)

    @property
    def scen_key(self):
        """Klíč událostí scénáře – stejný jako ve webu (projekt nese vlastní scénář)."""
        return f"scen_df|{self.get('mcode')}|{len(self.c_d)}"

    @property
    def scen_kind(self):
        """Druh scénáře (scenario.PRESETS); bez volby: vlastní události, jsou-li uložené (projekt z webu), jinak skok SP."""
        return scn.preset_kind(self.get("scen_kind"), self.get("scen2"), bool(self.settings.get(self.scen_key)),
                               bool(self.c_d))

    def set_scen_kind(self, kind):
        self.set(scen_kind=kind, scen2="replay" if kind == "replay" else "custom")

    def scen_amps(self):
        """Amplitudy poruch předvoleb: (vstup [MV], výstup [PV], [měřené poruchy])."""
        d_in = float(self.get("scen_d_in") or round(0.05 * self.MR, 4))
        d_pv = float(self.get("scen_d_pv") or round(0.05 * self.PR, 4))
        meas = scn.meas_amps(self.segment()[3]) if self.c_d and self.has_data else []
        return d_in, d_pv, meas

    def scen_rows(self, T_end):
        """Události scénáře: předvolba, nebo vlastní (časy přepočtené na aktuální délku)."""
        kind = self.scen_kind
        sp0, sp1 = self.sp_from_to()
        if kind not in ("custom", "replay"):
            d_in, d_pv, meas = self.scen_amps()
            return scn.preset_rows(kind, sp1 - sp0, d_in, d_pv, meas, T_end)
        rows = self.settings.get(self.scen_key)
        if not rows:
            return scn.preset_rows("sp", sp1 - sp0, 0, 0, [], T_end)
        t_prev = self.settings.get(self.scen_key + "|tend")
        if t_prev and abs(T_end / t_prev - 1) > 0.02:
            rows = scn.rescale_times(rows, T_end / t_prev)
            self.settings[self.scen_key] = rows
        self.settings[self.scen_key + "|tend"] = T_end
        return rows

    def set_scen_rows(self, rows, T_end):
        if rows is None:
            self.settings.pop(self.scen_key, None)
        else:
            self.settings[self.scen_key] = [list(r) for r in rows]
            self.settings[self.scen_key + "|tend"] = T_end

    @property
    def stic_key(self):
        return f"sim_S|{self.get('mcode')}|desktop"

    def plant(self):
        """Proces a ventil v simulaci: stikce [MV] (výchozí z identifikace), skluz [%], šum PV [PV], charakteristika."""
        code = self.get("mcode")
        st0 = (self.fit["res"][code].get("stic") or 0.0) * self.MR / 100 if self.fit and code in self.fit["res"] else 0.0
        return scn.plant(float(self.get(self.stic_key, st0)), float(self.get("sim_J", 100.0)),
                         float(self.get("sim_noise", 0.0)), self.get("vchar_last") or [1.0] * 10, self.PR, self.MR)

    def _scenario_inputs(self, T_end=None):
        """Průběhy scénáře: vlastní události, nebo přehrání naměřených poruch (scen2 = „replay“, jako ve webu)."""
        samp = float(self.get("samp"))
        src = "manual"
        replay = self.scen_kind == "replay"
        ts_id, _, mv_id, d_id = self.segment()
        if replay:
            T_end, src = float(ts_id[-1]), "data"
        elif T_end is None:
            T_end, src = self.sim_length()
        sp0, _ = self.sp_from_to()
        pv0 = float(self.P(sp0))
        h, ts = scn.grid(samp, T_end)
        rows = [] if replay else self.scen_rows(T_end)
        sig = scn.signals(rows, ts, h, T_end, self.PR, self.MR, pv0, len(self.c_d))
        if replay:
            sig["dmeas"] = scn.replay_dists(ts, ts_id, d_id)
        return dict(h=h, ts=ts, T_end=T_end, src=src, rows=rows, sig=sig, pv0=pv0, mv0=float(mv_id[0]))

    def scen_built(self):
        """Scénář pro optimalizaci „na scénáři“ (stejný tvar jako ve webu)."""
        x = self._scenario_inputs()
        g = x["sig"]
        return dict(mcode=self.get("mcode"), h=x["h"], sp=g["sp"], pv0=x["pv0"], mv0=x["mv0"], dmeas=g["dmeas"],
                    dmv=g["dmv"], dpv=g["dpv"], plant=self.plant(), sp_amp=g["sp_amp"] or 5.0, d_amp=g["d_amp"] or 5.0)

    def ctrl_of(self, sug):
        """Regulátor z návrhu (Kc, Ti, Td) s blokem PIDConL a dopřednou vazbou aktivní smyčky."""
        ff, ffll = self.ff() if self.model else ([], [])
        return set_ctrl(self.base_ctrl(), float(sug["Kc"]), float(sug["Ti"]), float(sug["Td"]), ff, ffll)

    def simulate(self, T_end=None, robust=False, spread=False, ff_cmp=False, preview=None):
        """
        Scénář pro obě sady: dict(t, sp, runs = {1, 2: výsledek}, kpis, T_end, src, rows, extra = [(klíč, výsledek)]).
        robust: sada 2 na procesu s chybou modelu (K × 1,3, θ × 1,5); spread: sada 2 na variantách z nejistoty;
        ff_cmp: sada 2 bez dopředné vazby; preview: návrh (Kc, Ti, Td) jako třetí průběh runs["sug"].
        """
        code, p, pdl = self.model
        x = self._scenario_inputs(T_end)
        sig, h = x["sig"], x["h"]
        plant = self.plant()

        def run(ctrl, pp=p):
            return pidconl_sim_full(code, pp, pdl, h, sig["sp"], x["pv0"], x["mv0"], dict(ctrl, **plant), sig["dmeas"],
                                    sig["dmv"], sig["dpv"])
        runs, kp = {}, {}
        for n in (1, 2):
            runs[n] = run(self.set_ctrl(n))
            kp[n] = scn.kpis(runs[n], self.PR, self.MR) if scn.stable(runs[n]) else None
        if preview is not None:
            runs["sug"] = run(self.ctrl_of(preview))
            kp["sug"] = scn.kpis(runs["sug"], self.PR, self.MR) if scn.stable(runs["sug"]) else None
        extra = []
        if robust:
            pp = list(p)
            pp[0] *= 1.3
            pp[-1] *= 1.5
            extra.append(("new_err", run(self.set_ctrl(2), pp)))
        c2 = self.set_ctrl(2)
        if ff_cmp and any(c2["FF"]) and any(np.any(d != 0) for d in sig["dmeas"]):
            extra.append(("set2_noff", run(dict(c2, FF=[0.0] * len(c2["FF"]), FF_LL=[(0.0, 0.0, 0.0)] * len(c2["FF"])))))
        if spread:
            for q in self.unc_models()[:10]:
                r = run(c2, list(q))
                if scn.stable(r):
                    extra.append(("unc_variants", r))
        return dict(t=x["ts"], sp=sig["sp"], runs=runs, kpis=kp, T_end=x["T_end"], src=x["src"], rows=x["rows"],
                    extra=extra, sig=sig)
