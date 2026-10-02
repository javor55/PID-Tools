"""
Smyčka: převody jednotek (rozsah regulátoru NormPV / NormMV) a konfigurace bloku PIDConL a sad parametrů.

Výpočty v jádře pracují v % rozsahů regulátoru (Gain je bezrozměrný jako v PIDConL); data a parametry, které
zadává uživatel, jsou v inženýrských jednotkách.
"""
import numpy as np


class Scaling:
    """Převody mezi inženýrskými jednotkami a % rozsahu regulátoru. Třída potřebuje atributy pv_lo, pv_hi,
    mv_lo, mv_hi (dědí ji kontext webové aplikace i desktopový stav smyčky)."""

    @property
    def PR(self):
        return self.pv_hi - self.pv_lo

    @property
    def MR(self):
        return self.mv_hi - self.mv_lo

    def P(self, x):
        """PV [jednotky] → %."""
        return (np.asarray(x, float) - self.pv_lo) / self.PR * 100

    def M(self, x):
        """MV [jednotky] → %."""
        return (np.asarray(x, float) - self.mv_lo) / self.MR * 100

    def EP(self, x):
        """PV % → jednotky."""
        return self.pv_lo + np.asarray(x, float) * self.PR / 100

    def EM(self, x):
        """MV % → jednotky."""
        return self.mv_lo + np.asarray(x, float) * self.MR / 100


def block_ctrl(sc, samp, diffgain, propfac, dfb, deadband, db_mode, mv_lolim, mv_hilim, pvfilt, mvrate, sprate):
    """
    Konfigurace bloku PIDConL (společná pro obě sady) jako slovník pro simulaci a analýzu.
    sc: Scaling; deadband [PV], MV_LoLim / MV_HiLim [MV], mvrate [MV/s], sprate [PV/s], db_mode "cont" / "step".
    """
    return dict(SampleTime=samp, DiffGain=diffgain, PropFacSP=propfac, DiffFbk=dfb,
                DeadBand=deadband / sc.PR * 100, DbMode="spojité" if db_mode == "cont" else "skokové",
                MV_Lo=float(sc.M(mv_lolim)), MV_Hi=float(sc.M(mv_hilim)), PVFilt=pvfilt,
                MVRate=mvrate / sc.MR * 100, SPRate=sprate / sc.PR * 100)


def set_ctrl(base, gain, ti, td, ff=(), ffll=()):
    """Sada parametrů (Gain, TI [s], TD [s]; TI ≤ 0 = bez I složky) nad konfigurací bloku, s dopřednou vazbou."""
    return dict(base, Gain=gain, TI=ti if ti and ti > 0 else np.inf, TD=td, FF=list(ff), FF_LL=list(ffll))


def rule_ctrl(base, r):
    """Návrh pravidla ladění (dict Kc, Ti, Td z core.tune) jako sada parametrů."""
    return dict(base, Gain=r["Kc"], TI=r["Ti"] if r["Ti"] > 0 else np.inf, TD=r["Td"])
