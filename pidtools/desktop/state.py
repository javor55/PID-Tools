"""
Stav desktopové aplikace pro jednu smyčku: data, výběr sloupců, rozsahy, úsek identifikace, modely, blok PIDConL,
sady parametrů a scénář. Bez Qt – okna jen čtou a mění tento stav a volají jeho metody.

Nastavení se drží ve slovníku `settings` se stejnými klíči jako webová aplikace (app.project.STATE_KEYS), takže
projekt uložený v desktopu otevře web a naopak.
"""
import numpy as np
import pandas as pd

from ..app import dataset as ds
from ..app import feedforward as ffm
from ..app import model as mdl
from ..app import project as prj
from ..app import scenario as scn
from ..app import segments as sg
from ..app import tuning as tun
from ..app.dataio import read_table
from ..app.guess import guess_roles
from ..app.loop import Scaling, block_ctrl, set_ctrl
from ..core import MODELS, pidconl_sim_full

DEFAULTS = dict(
    lang="en", loop_tag="", u_pv="", u_mv="%", pv_lo=0.0, pv_hi=100.0, mv_lo=0.0, mv_hi=100.0,
    samp=1.0, diffgain=5.0, propfac=1.0, dfb=True, db=0.0, db_mode="cont", mvl_lo=None, mvl_hi=None, pvfilt=0.0,
    mvrate=0.0, sprate=0.0, set1_gain=1.0, set1_ti=100.0, set1_td=0.0, set2_gain=1.0, set2_ti=100.0, set2_td=0.0,
    thmax=None, chosen=list(MODELS), mcode=None, dist_level="none", dist_strength=4, gain_sign="auto", id_stic=False,
    ctype="PI", opt_crit="MIGO", opt_target="scen", scen_kind=None, opt_ms=1.6, opt_robust=False, opt_ovs=2, sim_len_u="s",
)


class LoopState(Scaling):
    """Jedna smyčka. Rozsahy (pv_lo …) čte Scaling z nastavení."""

    def __init__(self):
        self.settings = dict(DEFAULTS)
        self.df = None
        self.fname = ""
        self.layout, self.time_fmt, self.unit = "wide", "auto", "s"
        self.c_time = self.c_tag = self.c_val = None    # sloupec času (wide) / tag, čas, hodnota (long); None = odhad
        self.ts_user = None                             # ruční perioda převzorkování [s]; None = automaticky
        self.sig = None
        self.grid = None
        self.c_pv = self.c_mv = None
        self.c_sp, self.c_d, self.c_pos = "—", [], "—"
        self.rng = (0.0, 0.0)
        self.fit = None              # {"res": {kód: výsledek}, "dnames": [...], "key": ...}
        self.ff_state = []
        self.sim_sp = None           # (SP z, SP na) v jednotkách PV, None = výchozí
        self.val_status = None       # výsledek validace pro průvodce: 0 dobrá, 1 stejný úsek, 2 špatná
        self.unc = None              # nejistota modelu: {"code", "key", "ps": [parametry variant]}

    # ---- nastavení a rozsahy
    def get(self, k, default=None):
        v = self.settings.get(k)
        return default if v is None else v

    def set(self, **kw):
        self.settings.update(kw)

    pv_lo = property(lambda s: float(s.get("pv_lo", 0.0)))
    pv_hi = property(lambda s: float(s.get("pv_hi", 100.0)))
    mv_lo = property(lambda s: float(s.get("mv_lo", 0.0)))
    mv_hi = property(lambda s: float(s.get("mv_hi", 100.0)))

    @property
    def norm(self):
        return self.pv_lo, self.pv_hi, self.mv_lo, self.mv_hi

    # ---- data
    def load_frame(self, df, name, layout=None):
        """Nová tabulka: rozložení, signály, odhad sloupců, celý záznam jako úsek identifikace."""
        self.df, self.fname = df, name
        self.layout = layout or ds.default_layout(df)
        self.c_time = self.c_tag = self.c_val = None
        self.sig = self._signals()
        g = guess_roles(self.sig.sigs, self.sig.get)
        self.c_pv, self.c_mv = g["pv"], g["mv"]
        self.c_sp = g["sp"] or "—"
        self.c_d, self.c_pos = [], g["pos"] or "—"
        self.fit = None
        self.update_grid(reset_range=True)

    def load_file(self, path):
        with open(path, "rb") as f:
            raw = f.read()
        self.load_frame(read_table(str(path), raw), str(path).replace("\\", "/").rsplit("/", 1)[-1])

    def load_demo(self):
        self.load_frame(ds.demo_frame(), "demo")
        self.c_d = ["FI100.Pritok"]
        if (self.get("set1_gain"), self.get("set1_ti")) == (1.0, 100.0):
            g, ti, td = ds.DEMO_SET1
            self.set(set1_gain=g, set1_ti=ti, set1_td=td)
        self.update_grid()

    def _signals(self):
        return ds.signals(self.df, self.layout, self.time_fmt, self.unit, self.c_time, self.c_tag, self.c_val)

    def set_layout(self, layout, time_fmt=None, unit=None, c_time=None, c_tag=None, c_val=None):
        if layout != self.layout:
            c_time = c_tag = c_val = None
        self.layout, self.time_fmt, self.unit = layout, time_fmt or self.time_fmt, unit or self.unit
        self.c_time, self.c_tag, self.c_val = c_time, c_tag, c_val
        self.sig = self._signals()
        for c in ("c_pv", "c_mv"):
            if getattr(self, c) not in self.sig.sigs:
                g = guess_roles(self.sig.sigs, self.sig.get)
                self.c_pv, self.c_mv, self.c_sp = g["pv"], g["mv"], g["sp"] or "—"
                self.c_d = []
                break
        self.update_grid(reset_range=True)

    def set_columns(self, c_pv, c_mv, c_sp="—", c_d=(), c_pos="—"):
        self.c_pv, self.c_mv, self.c_sp, self.c_d, self.c_pos = c_pv, c_mv, c_sp or "—", list(c_d), c_pos or "—"
        self.update_grid()

    def update_grid(self, reset_range=False):
        self.grid = ds.to_grid(self.sig, self.c_pv, self.c_mv, self.c_sp, self.c_d, self.ts_user)
        if reset_range or not (0 <= self.rng[0] < self.rng[1] <= self.grid.t[-1]):
            self.rng = (0.0, float(self.grid.t[-1]))
        if self.get("thmax") is None:
            self.settings["thmax"] = round(0.4 * (self.rng[1] - self.rng[0]), 1)

    @property
    def has_data(self):
        return self.grid is not None

    @property
    def t(self):
        return self.grid.t

    @property
    def pv(self):
        return self.P(self.grid.pv_e)

    @property
    def mv(self):
        return self.M(self.grid.mv_e)

    @property
    def sp(self):
        return self.P(self.grid.sp_e)

    # ---- úsek identifikace
    @property
    def sel_mask(self):
        return (self.t >= self.rng[0]) & (self.t <= self.rng[1])

    def segment(self):
        """(ts, pv, mv, poruchy) úseku identifikace v %; čas od začátku úseku."""
        m = self.sel_mask
        ts = self.t[m] - self.t[m][0]
        return ts, self.pv[m], self.mv[m], [d[m] for d in self.grid.dists]

    def quality(self, a=None, b=None):
        """Kvalita dat úseku (výchozí: úsek identifikace) včetně stopy komprese historianu."""
        a, b = (self.rng if a is None else (a, b))
        try:
            return sg.quality(self.t, self.pv, self.mv, self.sp, self.grid.Ts, self.grid.has_sp,
                              float(self.M(self.get("mvl_lo", self.mv_lo))), float(self.M(self.get("mvl_hi", self.mv_hi))),
                              a, b, sg.rep_frac(self.sig.t_all, self.sig.get(self.c_pv), self.grid.T0, a, b),
                              self.model[:2] if self.model else None)
        except Exception:
            return None

    def auto_segments(self, gap=None):
        """Automaticky nalezené úseky se skoky, každý s hodnocením kvality."""
        segs = sg.auto(self.t, self.mv, self.sp, self.grid.Ts, self.grid.has_sp, self.model[:2] if self.model else None,
                       gap)
        return [dict(q, quality=self.quality(q["start"], q["end"])) for q in segs]

    def compression(self):
        """Upozornění na kompresi historianu a nepravidelné vzorkování PV."""
        from ..app.dataio import compression_warnings
        return compression_warnings(self.sig.t_all, self.sig.get(self.c_pv), "PV")

    def preview(self):
        """Náhled: (převzorkovaná tabulka, statistika, typy sloupců původního souboru)."""
        from ..app.dataio import TIME_FORMATS, detect_time_format, time_columns, to_num
        g = self.grid
        out = {"t [s]": g.t}
        if self.sig.origin is not None:
            out["datetime"] = self.sig.origin + pd.to_timedelta(g.t + g.T0, unit="s")
        out[f"PV · {self.c_pv}"] = g.pv_e
        out[f"MV · {self.c_mv}"] = g.mv_e
        if g.has_sp:
            out[f"SP · {self.c_sp}"] = g.sp_e
        for nm, d in zip(self.c_d, g.dists):
            out[str(nm)] = d
        res = pd.DataFrame(out)
        num_ = res.drop(columns=["datetime"], errors="ignore")
        stats = pd.DataFrame({"min": num_.min(), "max": num_.max(), "mean": num_.mean(), "NaN": num_.isna().sum()})
        tcols = time_columns(self.df)
        kinds = {}
        for c in self.df.columns:
            if c in tcols:
                k = detect_time_format(self.df[c])[0]
                kinds[c] = ("time", k if k in TIME_FORMATS else str(k))
            else:
                kinds[c] = ("num" if np.isfinite(to_num(self.df[c])).mean() > 0.5 else "text", "")
        return res, stats, kinds

    # ---- identifikace
    def id_settings(self):
        return mdl.IdSettings(tuple(self.get("chosen")), float(self.get("thmax")), self.get("dist_level"),
                              float(self.get("dist_strength")), self.get("gain_sign"), bool(self.get("id_stic")))

    def fit_key(self):
        return mdl.fit_key(self.fname, tuple(self.rng), self.id_settings(), self.norm, self.grid.Ts, self.c_pv,
                           self.c_mv, self.c_d, self.layout == "long")

    def identify(self, progress=None):
        """Identifikace zvolených modelů na úseku. Vrací chyby [(kód, text)]."""
        ts, pv, mv, d = self.segment()
        res, errs = mdl.identify_all(ts, pv, mv, self.grid.Ts, d, self.id_settings(), progress=progress)
        if res:
            self.fit = dict(res=res, dnames=list(self.c_d), key=self.fit_key())
            self.settings["mcode"] = mdl.best(res)
            for c in res:
                self.reset_edits(c)
        return errs

    def refit(self, code, fixed, stic_fixed=None):
        """Dofitování modelu se zafixovanými parametry ({"p<i>": v, "d<j>_<i>": v}); ruční úpravy se srovnají."""
        ts, pv, mv, d = self.segment()
        self.fit["res"][code] = mdl.identify(code, ts, pv, mv, self.grid.Ts, d, self.id_settings(), fixed, stic_fixed)
        self.reset_edits(code)

    def fixed_from_settings(self, code):
        """Zafixované parametry podle zaškrtnutí (klíče fx|… jako ve webu) a aktuálních hodnot."""
        m = self.model
        p, pdl = m[1], m[2]
        n_d = len(pdl)
        return mdl.fixed_params(p, [bool(self.get(f"fx|{code}|{i}")) for i in range(len(p))], pdl,
                                [[bool(self.get(f"fx|{code}|d{j}|{i}")) for i in range(3)] for j in range(n_d)])

    def reset_edits(self, code):
        r = self.fit["res"][code]
        for i, v in enumerate(r["p"]):
            self.settings[f"ed|{code}|{i}"] = float(v)
        for j, pd_ in enumerate(r["pdl"]):
            for i, v in enumerate(pd_):
                self.settings[f"ed|{code}|d{j}|{i}"] = float(v)

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
    def model(self):
        """Model pro ladění (kód, parametry, parametry poruch) – nafitovaný s ručními úpravami, nebo None."""
        if not self.fit or self.fit.get("dnames") != list(self.c_d):
            return None
        code = self.get("mcode")
        if code not in self.fit["res"]:
            return None
        r = self.fit["res"][code]
        p = [self.get(f"ed|{code}|{i}", v) for i, v in enumerate(r["p"])]
        pdl = [[self.get(f"ed|{code}|d{j}|{i}", v) for i, v in enumerate(d)] for j, d in enumerate(r["pdl"])]
        p, pdl = mdl.clamp(p, pdl)
        return code, p, pdl

    def bootstrap(self, n=15, progress=None):
        """Nejistota modelu: bootstrap reziduí (n refitů na decimovaných datech)."""
        from ..core import bootstrap_models
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

    def compare_methods(self):
        """Srovnání všech metod a kritérií pro PI i PID (app.tuning.compare)."""
        code, p, pdl = self.model
        avg = (10.0, 10.0) if "AVG" in tun.methods(code, p) else None
        req = tun.Request(ms=float(self.get("opt_ms")), target=self.get("opt_target"),
                          ovs=float(self.get("opt_ovs")) / 100)
        return tun.compare(code, p, pdl, self.base_ctrl(), req, avg, self.sigma_pv(),
                           tun.robust_models(p, self.unc_models(), bool(self.get("opt_robust"))))

    def evaluate(self):
        code, p, pdl = self.model
        r = self.fit["res"][code]
        ts, pv, mv, d = self.segment()
        return mdl.evaluate(code, p, pdl, r.get("stic", 0.0) or 0.0, r.get("level", "none"), r.get("Th"),
                            ts, pv, mv, d, self.grid.Ts)

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

    def set_ctrl(self, n):
        ff, ffll = self.ff() if self.model else ([], [])
        return set_ctrl(self.base_ctrl(), float(self.get(f"set{n}_gain")), float(self.get(f"set{n}_ti")),
                        float(self.get(f"set{n}_td")), ff, ffll)

    def methods(self):
        code, p, _ = self.model
        return tun.methods(code, p)

    def request(self, method=None, tc=None):
        m = method or self.get(f"method|{self.get('mcode')}", "SIMC")
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
        from ..core import d_advice
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
        k = self.get("scen_kind")
        if k in scn.PRESETS and (k not in ("meas", "replay") or self.c_d):
            return k
        if k is None and self.get("scen2") == "replay" and self.c_d:
            return "replay"
        return "custom" if self.settings.get(self.scen_key) else "sp"

    def set_scen_kind(self, kind):
        self.set(scen_kind=kind, scen2="replay" if kind == "replay" else "custom")

    def scen_amps(self):
        """Amplitudy poruch předvoleb: (vstup [MV], výstup [PV], [měřené poruchy])."""
        d_in = float(self.get("scen_d_in") or round(0.05 * self.MR, 4))
        d_pv = float(self.get("scen_d_pv") or round(0.05 * self.PR, 4))
        meas = []
        if self.c_d and self.has_data:
            _, _, _, d = self.segment()
            for x in d:
                x = np.asarray(x, float)
                r = np.nanmax(x) - np.nanmin(x) if np.isfinite(x).any() else 0.0
                meas.append(float(f"{0.5 * r:.3g}") if r > 0 else 1.0)
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

    # ---- projekt
    def to_project(self, include_data=False):
        state = {k: prj.jsonable(v) for k, v in self.settings.items() if prj.is_state_key(k) and v is not None}
        rec = dict(tag=self.get("loop_tag", ""), state=state,
                   map=dict(c_pv=self.c_pv, c_mv=self.c_mv, c_sp=self.c_sp, c_d=list(self.c_d), c_pos=self.c_pos),
                   ranges={"id": list(self.rng), "val": list(self.rng)}, ff=list(self.ff_state))
        fit = prj.fit_record(self.fit)
        if fit:
            rec["fit"] = fit
        proj = dict(version=prj.PROJECT_VERSION, fname=self.fname, **rec)
        if include_data and self.has_data:
            g = self.grid
            cols = {"t_s": g.t, str(self.c_pv): g.pv_e, str(self.c_mv): g.mv_e}
            if g.has_sp:
                cols[str(self.c_sp)] = g.sp_e
            for nm, d in zip(self.c_d, g.dists):
                cols[str(nm)] = d
            proj["data"] = {"cols": cols}
        return proj

    def save_project(self, path, include_data=True):
        with open(path, "w", encoding="utf-8") as f:
            f.write(prj.serialize_project(self.to_project(include_data)))

    def apply_project(self, proj):
        """Obnova z projektu (aktivní smyčka). Data z projektu, jsou-li uložená; jinak zůstanou načtená data."""
        recs, act = prj.loop_records(proj)
        rec = recs[act]
        if proj.get("data"):
            cols = proj["data"]["cols"]
            self.load_frame(pd.DataFrame({k: np.asarray(v, float) for k, v in cols.items()}),
                            f"project|{proj.get('tag', '')}", layout="wide")
        self.settings = dict(DEFAULTS, **prj.migrate_state(rec.get("state", {})))
        mp = rec.get("map", {})
        if self.has_data and mp.get("c_pv") in self.sig.sigs and mp.get("c_mv") in self.sig.sigs:
            self.set_columns(mp["c_pv"], mp["c_mv"], mp.get("c_sp", "—"),
                             [c for c in mp.get("c_d", []) if c in self.sig.sigs], mp.get("c_pos", "—"))
        rg = (rec.get("ranges") or {}).get("id")
        if rg and self.has_data:
            self.rng = (float(rg[0]), float(rg[1]))
        self.ff_state = rec.get("ff") or []
        if rec.get("fit"):
            self.fit = dict(res=rec["fit"]["res"], dnames=list(rec["fit"]["dnames"]), key="__restore__")
            if self.has_data:
                self.fit["key"] = self.fit_key()

    def load_project(self, path):
        with open(path, encoding="utf-8") as f:
            self.apply_project(prj.load_project(f.read()))

    # ---- protokol
    def report_record(self):
        """Záznam smyčky pro app.report."""
        return dict(id=1, name=self.get("loop_tag") or str(self.c_pv), active=True, model=self.model,
                    ctrl=self.set_ctrl(2), ctrl1=self.set_ctrl(1), rng=tuple(self.rng),
                    fit=self.fit["res"][self.model[0]]["fit"] if self.model else None,
                    c_pv=self.c_pv, c_mv=self.c_mv, c_sp=self.c_sp, c_d=list(self.c_d), pv_rng=(self.pv_lo, self.pv_hi),
                    mv_rng=(self.mv_lo, self.mv_hi), u_pv=self.get("u_pv", ""), u_mv=self.get("u_mv", ""))

    def report_html(self, meta, sections, chart_mode="inline"):
        from ..app import report
        from ..app.apc import recommend as reco
        g = self.grid
        rec = self.report_record()
        apc = dict(items=reco.recommend(rec, [], None, any(d.get("use") for d in self.ff_state)))
        return report.build_report([rec], meta, sections, chart_mode,
                                   lambda r: (g.t, g.pv_e, g.mv_e, list(g.dists), g.Ts), apc)
