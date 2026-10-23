"""
Pracovní prostor jedné regulační smyčky bez UI: data, výběr sloupců, rozsahy, úsek identifikace, modely, blok
PIDConL, sady parametrů, scénář a projekt. Používá ho desktop (okna jen čtou a mění tento stav a volají jeho metody),
zlaté případy (tools/golden.py) a později API (docs/cs/milniky.md, M4 / M6).

Nastavení se drží ve slovníku `settings` se stejnými klíči jako webová aplikace (app.project.STATE_KEYS), takže
projekt uložený v jednom rozhraní otevře druhé. Metody jsou rozdělené podle oblastí do modulů data, ident, tuning
a project; Workspace je skládá dohromady.
"""
from ...core import MODELS
from .. import tuning as tun
from ..loop import Scaling

DEFAULTS = dict(
    lang="en", loop_tag="", u_pv="", u_mv="%", pv_lo=0.0, pv_hi=100.0, mv_lo=0.0, mv_hi=100.0,
    samp=1.0, diffgain=5.0, propfac=1.0, dfb=True, db=0.0, db_mode="cont", mvl_lo=None, mvl_hi=None, pvfilt=0.0,
    mvrate=0.0, sprate=0.0, set1_gain=1.0, set1_ti=100.0, set1_td=0.0, set2_gain=1.0, set2_ti=100.0, set2_td=0.0,
    thmax=None, chosen=list(MODELS), mcode=None, dist_level="none", dist_strength=4, gain_sign="auto", id_stic=False,
    ctype="PI", opt_crit=tun.DEFAULT_CRIT, opt_target=tun.DEFAULT_TARGET, scen_kind=None, opt_ms=1.6, opt_robust=False,
    opt_ovs=2, sim_len_u="s",
)


from .analysis import AnalysisMixin  # noqa: E402
from .data import DataMixin  # noqa: E402
from .ident import IdentMixin  # noqa: E402
from .project import ProjectMixin  # noqa: E402
from .tuning import TuningMixin  # noqa: E402


class Workspace(DataMixin, IdentMixin, TuningMixin, AnalysisMixin, ProjectMixin, Scaling):
    """Jedna smyčka. Rozsahy (pv_lo …) čte Scaling z nastavení."""

    def __init__(self):
        self.settings = dict(DEFAULTS)
        self.df = None
        self.fname = ""
        self.layout, self.time_fmt, self.unit = "wide", "auto", "s"
        self.c_time = self.c_tag = self.c_val = None    # sloupec času (wide) / tag, čas, hodnota (long); None = odhad
        self.ts_user = None                             # ruční perioda převzorkování [s]; None = automaticky
        self.row_dt = 1.0                               # bez času (co řádek, to vzorek): perioda v jednotkách unit
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
        self.wins = {}               # úseky podle vstupů {vstup: [[od, do] s]} (MV a měřené poruchy)
        self.excl = {}               # vyřazení dat podle mezí {signál: [zap, min, max]} (inženýrské jednotky)
        self.excl_tol = 0.5          # tolerance vyřazení [% rozsahu]
        self.cv = None               # křížové ověření {"key", "res": {kód: [FIT]}}

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

    def lean(self):
        """
        Kopie pro výpočet v jiném procesu (app.jobs): bez původní tabulky a signálů ze souboru (nejdou přenést
        a výpočty nad převzorkovanými daty je nepotřebují); nastavení, úseky a výsledky jako samostatné kopie.
        """
        import copy
        c = copy.copy(self)
        c.df = c.sig = None
        c.settings = dict(self.settings)
        c.wins = {k: [list(w) for w in v] for k, v in self.wins.items()}
        c.excl = {k: list(v) for k, v in self.excl.items()}
        return c
