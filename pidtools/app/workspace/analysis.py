"""
Diagnostika smyčky nad daty pracovního prostoru: KPI úseku, ventil (oscilace, stikce), hystereze podle polohy
a nelinearita z místních zesílení (M4d). Výpočty jsou v app.diagnostics; tady se jen skládají vstupy ze stavu.
"""
from .. import diagnostics as dg


class AnalysisMixin:
    """Část pracovního prostoru – metody pracují se stavem Workspace (self)."""

    def range_mask(self, a, b):
        return (self.t >= a) & (self.t <= b)

    def diag_theta(self):
        """Dopravní zpoždění pro Harrisův index: z modelu (výchozí 5 s) + polovina SampleTime."""
        return (self.model[1][-1] if self.model else 5.0) + float(self.get("samp")) / 2

    def diag_kpis(self, a, b):
        """KPI úseku (od, do) [s] – rozptyl odchylky, IAE, pohyb MV, obraty, na mezi, Harris, oscilace."""
        g, m = self.grid, self.range_mask(a, b)
        lo, hi = float(self.M(self.get("mvl_lo", self.mv_lo))), float(self.M(self.get("mvl_hi", self.mv_hi)))
        return dg.kpis(self, self.t[m], self.sp[m], self.pv[m], self.mv[m], g.Ts, lo, hi, self.diag_theta(),
                       g.has_sp)

    def valve(self, a, b, integ=False):
        """Oscilace a stikce ventilu v úseku (od, do) [s]; integ = integrační proces (PV jako derivace)."""
        g, m = self.grid, self.range_mask(a, b)
        return dg.valve(self.sp[m], self.pv[m], self.mv[m], g.Ts, g.has_sp, integ)

    def position(self):
        """Signál polohy ventilu na mřížce dat, nebo None (bez sloupce polohy)."""
        if self.c_pos in (None, "", "—"):
            return None
        from ..dataset import on_grid
        return on_grid(self.sig, self.grid, self.c_pos)

    def hysteresis(self, a, b):
        pos = self.position()
        if pos is None:
            return None
        m = self.range_mask(a, b)
        return dg.hysteresis(self.grid.mv_e[m], pos[m])

    def nonlinearity(self):
        """Místní zesílení po skocích MV v úseku identifikace a jejich rozptyl; (seznam, rozptyl) nebo None."""
        if self.model is None:
            return None
        ts, pv, mv, d = self.segment()
        return dg.nonlinearity(self.model, ts, pv, mv, d, self.grid.Ts)
