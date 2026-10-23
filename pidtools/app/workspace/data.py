"""
Data smyčky: načtení souboru, výběr sloupců, převzorkování, úsek identifikace (společný i podle vstupů),
vyřazení dat podle mezí, kvalita dat a náhled (M4a).
"""
import numpy as np
import pandas as pd

from .. import dataset as ds
from .. import model as mdl
from .. import segments as sg
from .. import windows as wn
from ..dataio import read_table
from ..guess import guess_roles
from ..loop import range_for


class DataMixin:
    """Část pracovního prostoru – metody pracují se stavem Workspace (self)."""

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
        self.wins, self.excl = {}, {}
        self.update_grid(reset_range=True)

    def load_file(self, path):
        with open(path, "rb") as f:
            raw = f.read()
        self.load_frame(read_table(str(path), raw), str(path).replace("\\", "/").rsplit("/", 1)[-1])

    def load_demo(self):
        self.load_frame(ds.demo_frame(), "demo")
        self.c_d = list(ds.DEMO_DISTS)
        if (self.get("set1_gain"), self.get("set1_ti")) == (1.0, 100.0):
            g, ti, td = ds.DEMO_SET1
            self.set(set1_gain=g, set1_ti=ti, set1_td=td)
        self.update_grid()

    def _signals(self):
        return ds.signals(self.df, self.layout, self.time_fmt, self.unit, self.c_time, self.c_tag, self.c_val,
                          self.row_dt)

    def set_layout(self, layout, time_fmt=None, unit=None, c_time=None, c_tag=None, c_val=None, row_dt=None):
        if layout != self.layout:
            c_time = c_tag = c_val = None
        if row_dt:
            self.row_dt = float(row_dt)
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
        for k, x in (("pv", self.grid.pv_e), ("mv", self.grid.mv_e)):      # rozsah PIDConL podle dat, dokud není zadán
            lo, hi = range_for((self.get(f"{k}_lo", 0.0), self.get(f"{k}_hi", 100.0)), x, bool(self.get(f"{k}_rng_user")))
            self.settings[f"{k}_lo"], self.settings[f"{k}_hi"] = lo, hi
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

    # ---- úsek identifikace (společný úsek, nebo úseky podle vstupů – pak rozpětí všech úseků)
    @property
    def win_mode(self):
        return self.get("win_mode") if self.get("win_mode") in ("common", "inputs") else "common"

    @property
    def inputs_mode(self):
        return self.win_mode == "inputs"

    @property
    def wins_s(self):
        """Úseky {vstup: [[od, do]]} pro MV a všechny poruchy (MV výchozí = společný úsek)."""
        return wn.with_defaults(self.wins, self.c_d, self.rng)

    def set_wins(self, inp, wins):
        W = self.wins_s
        W[str(inp)] = [[float(min(a, b)), float(max(a, b))] for a, b in wins if abs(b - a) > 0]
        self.wins = W

    @property
    def win_idx(self):
        return wn.indices(self.t, self.wins_s, self.c_d, float(max(self.grid.Ts, self.t[-1] / 1000)))[0]

    @property
    def id_rng(self):
        """Rozpětí dat identifikace: společný úsek, nebo od začátku prvního do konce posledního úseku podle vstupů."""
        if self.inputs_mode:
            span = wn.indices(self.t, self.wins_s, self.c_d, float(max(self.grid.Ts, self.t[-1] / 1000)))[1]
            if span:
                return span
        return self.rng

    @property
    def sel_mask(self):
        a, b = self.id_rng
        return (self.t >= a) & (self.t <= b)

    def excl_rows(self):
        """Vyřazení dat: [(signál, zap, min, max, rozsah)] – PV a MV podle rozsahů (zapnuto), poruchy podle dat."""
        g = self.grid
        rows = [("PV", g.pv_e, (self.pv_lo, self.pv_hi), True),
                ("MV", g.mv_e, (float(self.get("mvl_lo", self.mv_lo)), float(self.get("mvl_hi", self.mv_hi))), True)]
        for nm, d in zip(self.c_d, g.dists):
            rows.append((str(nm), d, (float(np.nanmin(d)), float(np.nanmax(d))), False))
        out = []
        for nm, _x, (lo, hi), on in rows:
            e = self.excl.get(nm) or [on, lo, hi]
            out.append((nm, bool(e[0]), float(e[1]) if e[1] is not None else lo, float(e[2]) if e[2] is not None else hi,
                        (hi - lo) if hi > lo else 1.0))
        return out

    def _excl_signals(self):
        g = self.grid
        return [g.pv_e, g.mv_e] + list(g.dists)

    @property
    def valid(self):
        """Vzorky, které se počítají do fitu (úseky podle vstupů; mimo meze vyřazeno); None = všechny."""
        if not self.inputs_mode:
            return None
        rows = self.excl_rows()
        return mdl.valid_mask(len(self.t), [(x, r[4]) for x, r in zip(self._excl_signals(), rows)],
                              [(r[1], r[2], r[3]) for r in rows], float(self.excl_tol))

    @property
    def excl_key(self):
        return (tuple((r[1], r[2], r[3]) for r in self.excl_rows()), float(self.excl_tol))

    def dkinds(self):
        """Typ přenosu každé poruchy pro identifikaci (jako MV / auto / struktura P0D … I1D)."""
        out = []
        for dn in self.c_d:
            k = wn.flat_kinds(self.get(f"dkind|{dn}", "pv"))
            out.append(k if k in mdl.DIST_CHOICES else "pv")
        return out

    def dsigns(self):
        return [mdl.SIGN.get(self.get(f"dsign|{dn}", "auto"), 0) for dn in self.c_d]

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

    def compression(self):
        """Upozornění na kompresi historianu a nepravidelné vzorkování PV."""
        from ..dataio import compression_warnings
        return compression_warnings(self.sig.t_all, self.sig.get(self.c_pv), "PV")

    def preview(self):
        """Náhled: (převzorkovaná tabulka, statistika, typy sloupců původního souboru)."""
        from ..dataio import TIME_FORMATS, detect_time_format, time_columns, to_num
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
