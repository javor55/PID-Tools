"""
Identifikace: nastavení, režim MAN / AUTO a kombinovaná identifikace, identifikace a dofitování, ruční úpravy
parametrů, aktuálnost modelu, křížové ověření, nejistota a shoda modelu s daty (M4b).
"""
import numpy as np

from ...core import pd_z
from .. import model as mdl
from .. import tuning as tun
from .. import windows as wn


class IdentMixin:
    """Část pracovního prostoru – metody pracují se stavem Workspace (self)."""

    # ---- identifikace
    def id_settings(self):
        return mdl.IdSettings(tuple(self.get("chosen")), float(self.get("thmax")), self.get("dist_level"),
                              float(self.get("dist_strength")), self.get("gain_sign"), bool(self.get("id_stic")))

    def fit_key(self):
        key = mdl.fit_key(self.fname, tuple(self.id_rng), self.id_settings(), self.norm, self.grid.Ts, self.c_pv,
                          self.c_mv, self.c_d, self.layout == "long") + (tuple(self.dkinds()),)
        if self.inputs_mode:
            key = key + ("win", tuple(self.win_idx), self.excl_key, tuple(self.dsigns()))
            mix = self.mixed()
            if mix:
                key = key + ("mix", tuple(self.mv_modes()), tuple(sorted((k, str(v)) for k, v in mix["ctrl"].items())))
        return key

    @property
    def id_closed(self):
        """Identifikace z dat v AUTO (nepřímá metoda se Set 1) – jen se sloupcem SP; „auto“ podle záznamu."""
        return self.grid is not None and self.grid.has_sp and self.id_mode_eff == "cl"

    # ---- ruční (MAN) / automatická (AUTO) smyčka v záznamu
    @property
    def id_mode(self):
        m = self.get("id_mode")
        return m if m in ("auto", "open", "cl") else "auto"

    def loop_det(self):
        """Úseky MAN / AUTO celého záznamu (spočtené jednou pro soubor a signály)."""
        from .. import loopmode as lm
        key = (self.fname, len(self.t), str(self.c_mv), str(self.c_pv), str(self.c_sp))
        if getattr(self, "_lm_det", (None,))[0] != key:
            self._lm_det = (key, lm.detect(self.t, self.mv, self.pv, self.sp if self.grid.has_sp else None))
        return self._lm_det[1]

    def auto_frac(self):
        """Podíl AUTO v úseku identifikace (společný úsek, nebo úseky MV)."""
        from .. import loopmode as lm
        det = self.loop_det()
        if self.inputs_mode:
            m = np.zeros(len(self.t), bool)
            for a, b in self.wins_s.get("MV", []):
                m |= (self.t >= a) & (self.t <= b)
            return float(det["auto"][m].mean()) if m.any() else 0.0
        return lm.frac_in(det, self.t, *self.rng)

    @property
    def id_mode_eff(self):
        """Použitý režim identifikace („open“ / „cl“) – u „auto“ podle podílu AUTO v úseku a buzení SP."""
        from .. import closedloop as cl
        from .. import loopmode as lm
        if self.grid is None or self.inputs_mode:      # úseky podle vstupů: režim má každý úsek MV (mv_modes)
            return "open"
        has_sp = self.grid.has_sp
        ex = cl.excitation(self.sp[self.sel_mask], self.pv[self.sel_mask], self.mv[self.sel_mask])["ok"] if has_sp else False
        return lm.resolve_mode(self.id_mode, self.auto_frac(), has_sp, ex, self.set1_ok)

    @property
    def set1_ok(self):
        """Set 1 je skutečný regulátor ze záznamu (ne výchozí zástupné hodnoty) – podmínka identifikace v AUTO."""
        return not tun.is_placeholder(float(self.get("set1_gain")), float(self.get("set1_ti")),
                                      float(self.get("set1_td")))

    # ---- režim úseků MV (kombinovaná identifikace: ruční úseky + úseky v AUTO)
    def wmode_over(self):
        return {str(k): str(v) for k, v in (self.get(f"wmode|{self.fname}") or [])}

    def mv_modes(self):
        """Režim každého úseku MV („man“ / „auto“) – volba, jinak rozpoznání v záznamu; bez SP vše ručně."""
        if not self.inputs_mode or self.grid is None:
            return []
        choice = self.id_mode if self.grid.has_sp else "open"
        return wn.mv_modes(self.t, self.wins_s.get("MV", []), self.loop_det(), self.wmode_over(), choice, self.set1_ok)

    def set_mv_mode(self, k, mode):
        wmv = self.wins_s.get("MV", [])
        if k < len(wmv):
            ov = self.wmode_over()
            ov[wn.mode_key(wmv[k])] = mode
            self.set(**{f"wmode|{self.fname}": [[a, b] for a, b in ov.items()]})

    def mixed(self):
        """Kombinovaná identifikace: dict(sp, ctrl, open, closed, open_mv), nebo None (žádný úsek MV v AUTO)."""
        modes = self.mv_modes()
        if "auto" not in modes or not self.grid.has_sp:
            return None
        op, cl_, nmv = wn.mode_indices(self.t, self.wins_s, self.c_d, float(max(self.grid.Ts, self.t[-1] / 1000)), modes)
        return dict(sp=self.sp, ctrl=self.set_ctrl_plain(1), open=op, closed=cl_, open_mv=nmv)

    def manual_span(self):
        from .. import loopmode as lm
        return lm.manual_span(self.loop_det(), self.t, self.mv, *self.rng)

    def narrow_to_manual(self):
        """Úsek identifikace (u úseků podle vstupů úsek MV) na nejdelší ruční část se skokem MV."""
        span = self.manual_span()
        if not span:
            return False
        if self.inputs_mode:
            self.set_wins("MV", [span])
        else:
            self.rng = (float(span[0]), float(span[1]))
        return True

    def identify(self, progress=None):
        """
        Identifikace zvolených modelů: na společném úseku (v AUTO i doladění v uzavřené smyčce), nebo z úseků podle
        vstupů (s kontrolními odhady po úsecích). Vrací chyby [(kód, text)].
        """
        if self.inputs_mode:
            return self._identify_windows(progress)
        ts, pv, mv, d = self.segment()
        res, errs = mdl.identify_all(ts, pv, mv, self.grid.Ts, d, self.id_settings(), progress=progress,
                                     d_full=list(self.grid.dists), dkinds=self.dkinds())
        if res and self.id_closed:
            n = len(res)
            ctrl = {k: v for k, v in self.set_ctrl_plain(1).items()}
            res, e2 = mdl.identify_cl_all(res, ts, self.sp[self.sel_mask], pv, mv, self.grid.Ts, d, ctrl,
                                          self.id_settings(),
                                          progress=(lambda i, c: progress(n + i, c)) if progress else None)
            errs = errs + e2
        if res:
            self.fit = dict(res=res, dnames=list(self.c_d), key=self.fit_key())
            self.settings["mcode"] = mdl.best(res)
            for c in res:
                self.reset_edits(c)
        return errs

    def _identify_windows(self, progress=None):
        if not self.win_idx:
            return [("—", "err_no_windows")]
        g = self.grid
        res, errs = mdl.identify_windows_all(self.t, self.pv, self.mv, g.Ts, list(g.dists), self.win_idx, self.valid,
                                             self.id_settings(), self.dkinds(), self.dsigns(), progress=progress,
                                             mixed=self.mixed())
        for c in res:
            res[c]["dv_chk"] = self.window_checks(c, res[c])
        if res:
            self.fit = dict(res=res, dnames=list(self.c_d), key=self.fit_key())
            self.settings["mcode"] = mdl.best(res)
            for c in res:
                self.reset_edits(c)
        return errs

    def window_checks(self, code, r):
        """Zesílení MV a poruch zvlášť v každém jejich úseku (kontrola, zda úseky souhlasí)."""
        g = self.grid
        return wn.window_checks(code, r, self.t, self.pv, self.mv, g.Ts, list(g.dists), self.wins_s, self.valid,
                                self.dsigns(), self.c_d)

    def refit(self, code, fixed, stic_fixed=None):
        """Dofitování modelu se zafixovanými parametry ({"p<i>": v, "d<j>_<i>": v}) a zvolenými strukturami poruch."""
        r0 = self.fit["res"][code]
        dk = [wn.dsel(self.get, code, r0, j) for j in range(len(r0["pdl"]))]
        g = self.grid
        mix = self.mixed()
        if r0.get("method") == "win" and self.inputs_mode and mix and mix["closed"]:
            r = mdl.identify_mixed(code, self.t, self.pv, self.mv, g.Ts, list(g.dists), self.win_idx, self.valid,
                                   self.id_settings(), dk, self.dsigns(), mix, fixed)
            r["dv_chk"] = self.window_checks(code, r)
        elif r0.get("method") == "win" and self.inputs_mode:
            r = mdl.identify_windows(code, self.t, self.pv, self.mv, g.Ts, list(g.dists), self.win_idx, self.valid,
                                     self.id_settings(), dk, self.dsigns(), fixed)
            r["dv_chk"] = self.window_checks(code, r)
        else:
            ts, pv, mv, d = self.segment()
            r = mdl.identify(code, ts, pv, mv, g.Ts, d, self.id_settings(), fixed, stic_fixed, d_full=list(g.dists),
                             dkinds=dk)
        self.fit["res"][code] = r
        self.reset_edits(code)

    def cross_validate(self, progress=None):
        """Křížové ověření (úseky podle vstupů): fit bez každého úseku a shoda na něm. {kód: [FIT]}."""
        from ...core import cross_validate
        g = self.grid
        out = {}
        sets = self.id_settings()
        items = [(c, r) for c, r in self.fit["res"].items() if r.get("method") == "win"]
        for i, (c, r) in enumerate(items):
            if progress:
                progress(i, c)
            out[c] = cross_validate(c, self.t, self.pv, self.mv, g.Ts, list(g.dists), self.win_idx, self.valid,
                                    theta_max=sets.th_max, sign=mdl.SIGN[sets.gain_sign], dsign=tuple(self.dsigns()),
                                    dstruct=wn.structs(c, r))
        self.cv = dict(key=self.fit_key(), res=out)
        return out

    def fixed_from_settings(self, code):
        """Zafixované parametry podle zaškrtnutí (klíče fx|… jako ve webu) a aktuálních hodnot."""
        m = self.model
        p, pdl = m[1], m[2]
        n_d = len(pdl)
        z = [list(pd_z(d)) for d in pdl]
        return mdl.fixed_params(p, [bool(self.get(f"fx|{code}|{i}")) for i in range(len(p))], z,
                                [[bool(self.get(f"fx|{code}|d{j}|{i}")) for i in range(4)] for j in range(n_d)])

    def reset_edits(self, code):
        r = self.fit["res"][code]
        for i, v in enumerate(r["p"]):
            self.settings[f"ed|{code}|{i}"] = float(v)
        for j, pd_ in enumerate(r["pdl"]):
            self.settings.pop(f"dsel|{code}|{j}", None)          # struktura poruchy zpět na identifikovanou
            self.set_dist_ed(code, j, pd_)

    def set_dist_ed(self, code, j, pd_):
        """Pole parametrů poruchy j (Kd, Tp, θd, Tp2) z parametrů [Kd, Tp, θd, typ, Tp2]."""
        for i, v in enumerate(pd_z(pd_)):
            self.settings[f"ed|{code}|d{j}|{i}"] = float(v)

    def choose_dist(self, code, j, struct):
        """Jiná struktura přenosu poruchy j (z porovnání při identifikaci) → její parametry do polí."""
        self.settings[f"dsel|{code}|{j}"] = struct
        r = self.fit["res"][code]
        self.set_dist_ed(code, j, wn.dsel_pd(self.get, code, r, j))

    def rescale_if_needed(self):
        """Změnily se jen rozsahy regulátoru → přepočet modelů (jako ve webu). Vrací True při přepočtu."""
        if not self.fit:
            return False
        new = self.fit_key()
        old = self.fit.get("key")
        if old is None or old == "__restore__":
            self.fit["key"] = new
            return False
        if mdl.only_norm_changed(old, new):
            self.fit["res"], (fK, fKd, _) = mdl.rescale_results(self.fit["res"], old[mdl.NORM], new[mdl.NORM])
            for k in list(self.settings):
                if k.startswith("ed|") and k.endswith("|0"):
                    self.settings[k] = float(self.settings[k]) * (fKd if "|d" in k else fK)
            self.fit["key"] = new
            return True
        return False

    @property
    def stale(self):
        return bool(self.fit) and self.fit.get("key") != self.fit_key()

    @property
    def signals_changed(self):
        """Patří identifikace k jiným signálům (jiná PV nebo MV)? Pak se model nepoužije."""
        return bool(self.fit) and not wn.fit_signals_ok(self.fit.get("key"), self.fname, self.c_pv, self.c_mv)

    @property
    def model(self):
        """Model pro ladění (kód, parametry, parametry poruch) – nafitovaný s ručními úpravami, nebo None."""
        if not self.fit or self.fit.get("dnames") != list(self.c_d) or self.signals_changed:
            return None
        code = self.get("mcode")
        if code not in self.fit["res"]:
            return None
        r = self.fit["res"][code]
        p = [self.get(f"ed|{code}|{i}", v) for i, v in enumerate(r["p"])]
        pdl = [wn.dist_from_ed(self.get, code, r, j) for j in range(len(r["pdl"]))]
        p, pdl = mdl.clamp(p, pdl)
        return code, p, pdl

    def bootstrap(self, n=15, progress=None):
        """Nejistota modelu: bootstrap reziduí (n refitů na decimovaných datech)."""
        from ...core import bootstrap_models
        code, p, pdl = self.model
        ts, pv, mv, d = self.segment()
        k = int(np.ceil(len(ts) / 1500))
        bs = bootstrap_models(code, ts[::k], pv[::k], mv[::k], self.grid.Ts * k, [x[::k] for x in d],
                              float(self.get("thmax")), {"p": p, "pdl": pdl}, n=n, progress=progress)
        self.unc = dict(code=code, key=self.fit_key(), ps=[b["p"] for b in bs])
        return self.unc

    def unc_models(self):
        """Varianty modelu z nejistoty (jen pro aktuální model a data)."""
        m = self.model
        if m is None or not self.unc or self.unc["code"] != m[0] or self.unc.get("key") != self.fit_key():
            return []
        return self.unc["ps"]

    def evaluate(self):
        code, p, pdl = self.model
        r = self.fit["res"][code]
        ts, pv, mv, d = self.segment()
        ev = mdl.evaluate(code, p, pdl, r.get("stic", 0.0) or 0.0, r.get("level", "none"), r.get("Th"),
                          ts, pv, mv, d, self.grid.Ts)
        if r.get("method") == "win" and self.inputs_mode:   # shoda a průběh modelu jen v úsecích (vlastní posun)
            from ...core import dyn_scale, model_metrics, predict_windows
            g = self.grid
            ye, fits, f = predict_windows(code, p, pdl, self.t, self.pv, self.mv, g.Ts, list(g.dists), self.win_idx,
                                          self.valid)
            ev = dict(ev, fit=f, fits=fits, y_plot=ye[self.sel_mask], y_full=ye)
            mw = np.isfinite(ye) & (self.valid if self.valid is not None else True)
            if mw.sum() > 20:
                ev["metrics"] = model_metrics(self.pv[mw], ye[mw], self.mv[mw], g.Ts, dyn_scale(code, p))
                ev["sigma_pv"] = float(np.std(np.diff(self.pv[mw] - ye[mw])) / np.sqrt(2))
        return ev

    def model_curves(self):
        """Průběhy modelu na celém záznamu: v úsecích a přes celý záznam (viz app.windows.model_curves)."""
        code, p, pdl = self.model
        r = self.fit["res"][code]
        g = self.grid
        win = r.get("method") == "win" and self.inputs_mode
        seg = None
        if not win:
            m = self.sel_mask
            ts, pv, mv, d = self.segment()
            seg = (m, ts, pv, mv, d, self.evaluate()["y_plot"])
        return wn.model_curves(code, p, pdl, r.get("stic", 0.0) or 0.0, self.t, self.pv, self.mv, list(g.dists), g.Ts,
                               self.valid, self.win_idx if win else None, seg)

    def window_fits(self, code):
        """Shody nafitovaného modelu v jednotlivých (sloučených) úsecích podle vstupů [%]."""
        from ...core import predict_windows
        r, g = self.fit["res"][code], self.grid
        return predict_windows(code, r["p"], r["pdl"], self.t, self.pv, self.mv, g.Ts, list(g.dists), self.win_idx,
                               self.valid)[1]

    def live_fits(self):
        """{kód: FIT na aktuálních úsecích} (úseky podle vstupů; jinak FIT z identifikace)."""
        from ...core import predict_windows
        g = self.grid
        out = {}
        for c, r in self.fit["res"].items():
            if r.get("method") == "win" and self.inputs_mode:
                out[c] = predict_windows(c, r["p"], r["pdl"], self.t, self.pv, self.mv, g.Ts, list(g.dists),
                                         self.win_idx, self.valid)[2]
            else:
                out[c] = r["fit"]
        return out
