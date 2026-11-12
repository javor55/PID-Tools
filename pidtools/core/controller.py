"""
Obecný regulátor (E1, docs/cs/regulatory.md § 3–4): kanonický řetězec částí řízený profilem.

Profil (`pidtools.controllers`, JSON `.pidctrl`) vybere z registrů jednotlivé části – formu (ideální / paralelní /
sériová), zdroj a filtr D, režim mrtvého pásma, anti-windup, algoritmus – a přiřadí názvy parametrů bloku
(`Gain`, `TI` …) rolím regulátoru (`Kc`, `Ti` …). Rozhraní je stejné jako u dřívějšího `PIDConL`:
`init(sp, y_meas, u0, ff)`, `step(sp, y_meas, ff)`, `track(sp, y_meas, u_man, ff)`, `set_tuning(...)`.

Pořadí výpočtu jednoho kroku (kanonické, každá část vypnutelná):
  PV filtr → SP rampa → odchylka s mrtvým pásmem → P (váha b) → D (zdroj, filtr) → regulační zóna →
  součet P + I + D + FF → omezení a rychlost výstupu → anti-windup → integrace.

Krok je psaný pro rychlost: koeficienty se přepočítají při změně ladění, ve `step` jsou jen obyčejná čísla.
Veličiny jsou v % normovacích rozsahů (normování na jednotky obstarává vrstva `app`).
Speciální funkce (R3): gap, nelineární zesílení (kvadrát odchylky, tabulka), rychlostní algoritmus, externí reset
(BKCAL), dynamické meze (`set_limits`) a výstupní stupně (split range, 3-step, PWM) jsou položky registrů níže; vlastní
rovnice (R4) vykonává `core.program`. Rychlá cesta `step` pro základní PID se tím nemění: gap a nelineární zesílení se
skládají do funkce odchylky, externí reset je anti-windup s přístupem k regulátoru a výstupní stupeň obalí `step`.
"""
import math

import numpy as np

from ..controllers import load_preset, parse_profile
from ..controllers.mapping import apply_reprs, role_reprs
from .program import ProgramController, ProgramProfile, ideal_ctrl_program, is_program

__all__ = ["Controller", "Profile", "REGISTRIES", "controller_from_preset", "ideal_ctrl", "make_profile", "nonlinear_parts",
           "preset_profile"]

_INF = math.inf


class Registry:
    """Registr částí regulátoru: id → implementace (plán v2, kap. 7: rozšíření = přidat položku, ne větvit kód)."""

    def __init__(self, name):
        self.name = name
        self.items = {}

    def register(self, key, planned=False):
        def deco(obj):
            self.items[key] = (obj, planned)
            return obj
        return deco

    def get(self, key):
        if key not in self.items:
            raise ValueError(f"{self.name}: neznámá položka '{key}' (známé: {', '.join(sorted(self.items))})")
        obj, planned = self.items[key]
        if planned:
            raise NotImplementedError(f"{self.name}: '{key}' je v návrhu a bude doplněno (fáze R3 / R4)")
        return obj


FORMS = Registry("forma")
DEADBANDS = Registry("mrtvé pásmo")
D_SOURCES = Registry("zdroj D")
D_FILTERS = Registry("filtr D")
ANTIWINDUPS = Registry("anti-windup")
ALGORITHMS = Registry("algoritmus")
NORMALISATIONS = Registry("normování")
PV_FILTERS = Registry("filtr PV")
NL_GAINS = Registry("nelineární zesílení")
OUTPUT_STAGES = Registry("výstupní stupeň")
REGISTRIES = dict(forms=FORMS, deadbands=DEADBANDS, d_sources=D_SOURCES, d_filters=D_FILTERS,
                  antiwindups=ANTIWINDUPS, algorithms=ALGORITHMS, normalisations=NORMALISATIONS,
                  pv_filters=PV_FILTERS, nl_gains=NL_GAINS, output_stages=OUTPUT_STAGES)


# ================================================================ registry: formy
# Forma převede trojici ladicích hodnot (role níže) na ideální Kc, Ti, Td; Ti = None / ∞ / ≤ 0 = bez I složky.
@FORMS.register("ideal")
def _form_ideal(a, b, c):
    return a, b, c


_form_ideal.roles = ("Kc", "Ti", "Td")


@FORMS.register("parallel")
def _form_parallel(kp, ki, kd):
    """Paralelní: u = Kp·e + Ki·∫e + Kd·de/dt → Kc = Kp, Ti = Kp / Ki, Td = Kd / Kp."""
    if kp == 0:
        raise ValueError("paralelní forma: Kp = 0 nelze převést na ideální tvar")
    return kp, (kp / ki if ki and ki > 0 else None), kd / kp


_form_parallel.roles = ("Kp", "Ki", "Kd")


@FORMS.register("series")
def _form_series(kc, ti, td):
    """Sériová (interaktivní): Kc' = Kc (1 + Td / Ti), Ti' = Ti + Td, Td' = Ti Td / (Ti + Td). Filtr D se nepřepočítává."""
    if ti is None or not (ti > 0) or not math.isfinite(ti):
        return kc, ti, td
    return kc * (1.0 + td / ti), ti + td, ti * td / (ti + td)


_form_series.roles = ("Kc", "Ti", "Td")


# ================================================================ registry: mrtvé pásmo
@DEADBANDS.register("continuous")
def _db_continuous(db, P=None):
    """Spojité: uvnitř pásma 0, mimo odchylka zmenšená o šířku pásma."""
    def f(e):
        if abs(e) >= db:
            return e - (1.0 if e > 0 else -1.0) * db
        return 0.0
    return f


@DEADBANDS.register("step")
def _db_step(db, P=None):
    """Skokové: uvnitř pásma 0, mimo odchylka beze změny."""
    def f(e):
        return e if abs(e) >= db else 0.0
    return f


@DEADBANDS.register("gap")
def _db_gap(db, P=None):
    """Gap: uvnitř pásma se zesílení sníží na k (role `gap_gain`), mimo pásmo odchylka spojitě navazuje (k = 0 = spojité)."""
    k = (P or {}).get("gap_gain", 0.0)

    def f(e):
        if abs(e) < db:
            return k * e
        return e - (1.0 if e > 0 else -1.0) * db * (1.0 - k)
    return f


# ================================================================ registry: zdroj a filtr D
D_SOURCES.register("error")(lambda params: 0)          # 0 = D z (zpracované) odchylky
D_SOURCES.register("pv")(lambda params: 1)             # 1 = D z −PV
D_SOURCES.register("error_or_pv")(lambda params: 1 if params.get("d_on_pv") else 0)


@D_FILTERS.register("td_over_n")
def _df_td_over_n(params, Td):
    """Časová konstanta filtru Tf = Td / N (DiffGain, PCS 7)."""
    N = max(params.get("N", 5.0), 1e-6)
    return Td / N if Td > 0 else 0.0


@D_FILTERS.register("none")
def _df_none(params, Td):
    return 0.0


@D_FILTERS.register("fixed")
def _df_fixed(params, Td):
    """Pevná časová konstanta Tf (role `Tf`)."""
    return float(params.get("Tf", 0.0)) if Td > 0 else 0.0


# ================================================================ registry: anti-windup
# Funkce (i_old, inc, u_un, u, k_aw) → nové I; u_un = neomezený součet, u = výstup po omezení.
@ANTIWINDUPS.register("clamp_conditional")
def _aw_clamp(i_old, inc, u_un, u, k_aw):
    """Podmíněná integrace: při omezení se integruje jen směrem, který omezení uvolňuje."""
    if u == u_un or (u_un > u and inc < 0) or (u_un < u and inc > 0):
        return i_old + inc
    return i_old


@ANTIWINDUPS.register("back_calculation")
def _aw_backcalc(i_old, inc, u_un, u, k_aw):
    """Zpětný výpočet: I += inc + (u − u_un) · Ts / Tt (k_aw = Ts / Tt, role `Tt`)."""
    return i_old + inc + (u - u_un) * k_aw


@ANTIWINDUPS.register("none")
def _aw_none(i_old, inc, u_un, u, k_aw):
    return i_old + inc


def _aw_external(ctl, P):
    """Externí reset (BKCAL, „reset feedback“): zpětná vazba z vnějšku (`ctl.ext_reset`, skutečná poloha za regulátorem)
    s časovou konstantou Tt (role `Tt`, jinak Ti); bez signálu se chová jako zpětný výpočet z vlastního výstupu."""
    tt = P.get("Tt")

    def f(i_old, inc, u_un, u, k_aw):
        ub = ctl.ext_reset if ctl.ext_reset is not None else u
        k = ctl.Tc / tt if tt else (ctl.Tc / ctl.Ti if ctl.use_i else 0.0)
        return i_old + inc + (ub - u_un) * k
    return f


_aw_external.factory = True
ANTIWINDUPS.register("external_reset")(_aw_external)


def _alg_velocity(i_old, inc, u_un, u, k_aw):
    """Rychlostní (přírůstkový) algoritmus: u = u_prev + ΔP + ΔI + ΔD + ΔFF. Je shodný s polohovým, jehož I složka se každý
    krok přepíše na u − P − D − FF (zpětný výpočet s Tt = Ts): omezení výstupu tak nemá windup a meze lze měnit."""
    return i_old + inc + (u - u_un)


# ================================================================ registry: nelineární zesílení
# Tvarovač odchylky `g(e)` (po mrtvém pásmu): továrna (regulátor, parametry, popis v profilu) → funkce nebo None.
def _interp(xs, ys, x):
    """Lineární interpolace tabulky; mimo rozsah drží krajní hodnotu."""
    if x <= xs[0]:
        return ys[0]
    for i in range(1, len(xs)):
        if x < xs[i]:
            return ys[i - 1] + (ys[i] - ys[i - 1]) * (x - xs[i - 1]) / (xs[i] - xs[i - 1])
    return ys[-1]


NL_GAINS.register("none")(lambda ctl, P, spec: None)


@NL_GAINS.register("squared")
def _nl_squared(ctl, P, spec):
    """Kvadrát odchylky: e' = e·|e| / E0 pro |e| < E0 (zesílení K·|e| / E0, role `nl_e0`), mimo beze změny."""
    e0 = P.get("nl_e0", 0.0)
    if not e0 or e0 <= 0:
        return None

    def f(e):
        return e * abs(e) / e0 if abs(e) < e0 else e
    return f


@NL_GAINS.register("table")
def _nl_table(ctl, P, spec):
    """Zesílení podle tabulky (gain scheduling): e' = e · g(x), x = PV / SP / MV / odchylka (`input`), g lineárně z tabulky."""
    xs, ys, src = [float(v) for v in spec["x"]], [float(v) for v in spec["y"]], spec.get("input", "pv")
    if len(xs) < 2 or len(xs) != len(ys) or any(b <= a for a, b in zip(xs, xs[1:])):
        raise ValueError("tabulka zesílení: x musí být rostoucí a mít stejný počet bodů jako y (min. 2)")
    if src == "pv":
        return lambda e: e * _interp(xs, ys, ctl.yf)
    if src == "sp":
        return lambda e: e * _interp(xs, ys, ctl.spr)
    if src == "mv":
        return lambda e: e * _interp(xs, ys, ctl.u_prev)
    if src == "error":
        return lambda e: e * _interp(xs, ys, e)
    raise ValueError(f"tabulka zesílení: neznámý vstup '{src}' (pv, sp, mv, error)")


# ================================================================ registry: výstupní stupně
# Továrna (regulátor, parametry) → objekt `stage(u) → ekvivalentní poloha`; volá se každý krok simulace h, `stage.outputs`
# jsou signály z § 4.1 (MV, MV2, PULSE_UP, PULSE_DN, PWM). Model procesu dostane vždy ekvivalentní polohu akčního členu.
OUTPUT_STAGES.register("none")(None)


class _SplitRange:
    """Split range / ohřev–chlazení: požadavek 0–100 % se rozdělí v bodě `split_point` na MV (ohřev, nad bodem) a MV2
    (chlazení, pod bodem), mezera `split_gap` kolem bodu, zesílení stran `k_heat`, `k_cool`. Ekvivalent = čistý účinek."""

    def __init__(self, ctl, P):
        self.s, self.g, self.kh, self.kc = P["split_point"], P["split_gap"], P["k_heat"], P["k_cool"]
        self.outputs = dict(MV=0.0, MV2=0.0)

    def __call__(self, u):
        s, g = self.s, self.g
        a, b = s - g / 2, s + g / 2
        heat = min(100.0, (u - b) / max(100.0 - b, 1e-9) * 100.0 * self.kh) if u > b else 0.0
        cool = min(100.0, (a - u) / max(a, 1e-9) * 100.0 * self.kc) if u < a else 0.0
        self.outputs["MV"], self.outputs["MV2"] = heat, cool
        return s + heat / 100.0 * (100.0 - s) - cool / 100.0 * s


class _ThreeStep:
    """3-step (motorový pohon bez zpětného hlášení): poloha se integruje z pulzů, doba přestavení `motor_time` na 100 %,
    práh `tri_threshold` [%], minimální puls `min_pulse` a pauza `min_pause` [s]. Ekvivalent = odhad polohy pohonu."""

    def __init__(self, ctl, P):
        self.h, self.tm, self.thr = ctl.h, max(P["motor_time"], 1e-9), P["tri_threshold"]
        self.tmin, self.tpause = P["min_pulse"], P["min_pause"]
        self.pos, self.left, self.dir, self.pause = None, 0.0, 0, 0.0
        self.outputs = dict(PULSE_UP=0.0, PULSE_DN=0.0)

    def __call__(self, u):
        if self.pos is None:
            self.pos = u
        h = self.h
        if self.left <= 0 and self.pause > 0:
            self.pause -= h
        elif self.left <= 0:
            d = u - self.pos
            need = abs(d) / 100.0 * self.tm
            if abs(d) >= self.thr and need > 0 and need >= self.tmin:
                self.left, self.dir = need, (1 if d > 0 else -1)
        on = 0.0
        if self.left > 0:
            dt = min(h, self.left)
            self.pos = min(max(self.pos + self.dir * dt / self.tm * 100.0, 0.0), 100.0)
            self.left -= dt
            on = dt / h
            if self.left <= 1e-12:
                self.left, self.pause = 0.0, self.tpause
        self.outputs["PULSE_UP"], self.outputs["PULSE_DN"] = (on if self.dir > 0 else 0.0), (on if self.dir < 0 else 0.0)
        return self.pos


class _Pwm:
    """PWM: perioda `pwm_period` [s], střída = požadavek / 100, minimální puls `min_pulse` (kratší puls nebo pauza se
    zaokrouhlí). Ekvivalent = střední hodnota přes periodu (střída · 100); `outputs["PWM"]` je okamžitý stav 0 / 1."""

    def __init__(self, ctl, P):
        self.h, self.tp, self.tmin = ctl.h, max(P["pwm_period"], ctl.h), P["min_pulse"]
        self.t, self.duty = None, 0.0
        self.outputs = dict(PWM=0.0)

    def __call__(self, u):
        if self.t is None or self.t >= self.tp - 1e-9:
            self.t = 0.0
            duty = min(max(u, 0.0), 100.0) / 100.0
            on, tp, tm = duty * self.tp, self.tp, self.tmin
            if tm > 0:
                if on < tm / 2:
                    duty = 0.0
                elif on < tm:
                    duty = tm / tp
                elif tp - on < tm / 2:
                    duty = 1.0
                elif tp - on < tm:
                    duty = 1.0 - tm / tp
            self.duty = duty
        self.outputs["PWM"] = 1.0 if self.t < self.duty * self.tp - 1e-12 else 0.0
        self.t += self.h
        return self.duty * 100.0


OUTPUT_STAGES.register("split_range")(_SplitRange)
OUTPUT_STAGES.register("three_step")(_ThreeStep)
OUTPUT_STAGES.register("pwm")(_Pwm)


# ================================================================ registry: ostatní části
ALGORITHMS.register("position")(True)
ALGORITHMS.register("velocity")(_alg_velocity)          # přepíše anti-windup (viz funkce)
NORMALISATIONS.register("percent")(True)                # PV i MV v % rozsahů (rozsahy obstarává vrstva app)
NORMALISATIONS.register("engineering", planned=True)(None)
PV_FILTERS.register("lag1")(True)
PV_FILTERS.register("none")(False)


# ================================================================ profil
class Profile:
    """Přeložený profil: volby částí ze `structure` a tabulka parametrů (klíč bloku → role)."""

    def __init__(self, data):
        data = parse_profile(data)
        if data.get("kind") == "program":
            raise ValueError("profil typu program vykonává ProgramProfile (použijte make_profile)")
        self.data, self.id = data, data["id"]
        st = data["structure"]
        self.form = st.get("form", "ideal")
        self.form_fn = FORMS.get(self.form)
        self.tuning_roles = self.form_fn.roles
        self.d_source = D_SOURCES.get(st.get("d", {}).get("source", "error"))
        self.d_filter = D_FILTERS.get(st.get("d", {}).get("filter", "td_over_n"))
        self.antiwindup = ANTIWINDUPS.get(st.get("antiwindup", "clamp_conditional"))
        alg = ALGORITHMS.get(st.get("algorithm", "position"))
        if alg is not True:
            self.antiwindup = alg
        NORMALISATIONS.get(st.get("normalisation", {}).get("kind", "percent"))
        self.pv_lag = bool(PV_FILTERS.get(st.get("pv", {}).get("filter", "lag1")))
        db = st.get("error", {}).get("deadband")
        self.db_modes = (db or {}).get("modes", {})
        self.db_other = (db or {}).get("other", "step")
        for m in list(self.db_modes.values()) + [self.db_other]:
            DEADBANDS.get(m)
        out = st.get("output", {})
        self.stage = OUTPUT_STAGES.get(out.get("stage", "none"))
        nl = st.get("error", {}).get("nonlinear") or {}
        self.nl = (NL_GAINS.get(nl.get("kind", "none")), nl)
        self.use_rate, self.use_zone = bool(out.get("rate_limit")), bool(out.get("control_zone"))
        self.use_sp_rate = bool(st.get("sp", {}).get("rate_limit"))
        self.reprs = role_reprs(data)   # {role: varianta jednotky} (jen jiné než kanonické; `controllers.units`)
        self.params = []                # (klíč, role, výchozí, povinný, může být None, rozsah, alias)
        for p in data["params"]:
            self.params.append((p["key"], p["role"], _num(p.get("default")), bool(p.get("required")),
                                bool(p.get("nullable")), p.get("range"), p.get("alias")))

    def resolve(self, ctrl):
        """Slovník bloku (klíče jako Gain, TI) → hodnoty podle rolí (Kc, Ti …); chybějící = výchozí, povinné = KeyError."""
        out = {}
        for key, role, default, required, nullable, rng, alias in self.params:
            v = ctrl.get(key)
            if v is None and alias is not None and ctrl.get(alias["key"]) is not None:
                v = alias["true"] if ctrl.get(alias["key"]) else alias["false"]
            if v is None:
                if nullable and key in ctrl:        # např. TI = None: bez I složky
                    out[role] = None
                    continue
                if required:
                    raise KeyError(key)
                v = default
            out[role] = float(min(max(v, rng[0]), rng[1])) if rng is not None else v
        for role, v in _ROLE_DEFAULTS.items():      # role, které profil nemá (např. bez váhy b), mají neutrální hodnotu
            out.setdefault(role, v)
        if self.reprs:                  # jednotky profilu (PB, min, opakování/min, Tf …) → kanonické (K, s, N)
            out = apply_reprs(out, self.reprs, ctrl.get("_ranges"), "to_canon")
        return out


_ROLE_DEFAULTS = dict(b=1.0, d_on_pv=False, deadband=0.0, deadband_mode="", mv_lo=-_INF, mv_hi=_INF, pv_filter=0.0,
                      mv_rate=0.0, sp_rate=0.0, con_zone=0.0, N=5.0, Tf=0.0, gap_gain=0.0, nl_e0=0.0, split_point=50.0,
                      split_gap=0.0, k_heat=1.0, k_cool=1.0, motor_time=60.0, tri_threshold=1.0, min_pulse=0.0,
                      min_pause=0.0, pwm_period=10.0)


def _num(v):
    """Číslo z JSON; "inf" / "-inf" jako řetězce pro nekonečno."""
    if isinstance(v, str) and v.lstrip("+-") == "inf":
        return -_INF if v.startswith("-") else _INF
    return v


# ================================================================ regulátor
class Controller:
    """
    Regulátor krok po kroku podle profilu. `ctrl` je slovník parametrů v názvech bloku (jako `block_ctrl` /
    `set_ctrl` z app.loop), `h` krok simulace [s]; regulátor počítá každých round(SampleTime / h) kroků.
    Stav: yf (PV po filtru), spr (SP po rampě), I, D, u, dem (největší požadovaná změna výstupu za výpočet).
    """

    def __new__(cls, profile=None, *args, **kwargs):
        if cls is Controller and is_program(profile):         # profil typu program (R4) → regulátor z rovnic
            return ProgramController(profile, *args, **kwargs)
        return super().__new__(cls)

    def __init__(self, profile, ctrl, h):
        prof = profile if isinstance(profile, Profile) else Profile(profile)
        self.profile = prof
        P = prof.resolve(ctrl)
        self._params = P
        self.h = h
        self.m = max(1, int(round(P["Ts"] / h)))
        self.Tc = Tc = self.m * h
        self.lo, self.hi = P["mv_lo"], P["mv_hi"]
        db = P["deadband"]
        self._db = None
        if db > 0:
            name = prof.db_modes.get(P["deadband_mode"], prof.db_other)
            self._db = DEADBANDS.get(name)(db, P)
        self.yf = self.spr = self.u = self.u_prev = 0.0
        self.ext_reset = None                       # externí reset (BKCAL) pro anti-windup `external_reset`
        shaper = prof.nl[0](self, P, prof.nl[1])
        if shaper is not None:
            base = self._db
            self._db = shaper if base is None else (lambda e: shaper(base(e)))
        self.b = P["b"]
        self._omb = 1.0 - self.b
        self._dsrc = prof.d_source(P)
        Tpv = (P["pv_filter"] or 0.0) if prof.pv_lag else 0.0
        self._lag = Tpv > 0
        self._apv = float(np.exp(-h / Tpv)) if Tpv > 0 else 0.0
        self._bpv = 1 - self._apv
        self._rate = (P["mv_rate"] or 0.0) if prof.use_rate else 0.0
        self._sprate = (P["sp_rate"] or 0.0) if prof.use_sp_rate else 0.0
        self._rlim, self._slim = self._rate * Tc, self._sprate * Tc
        cz = (P["con_zone"] or 0.0) if prof.use_zone else 0.0
        self._cz = cz if (cz > 0 and math.isfinite(self.lo) and math.isfinite(self.hi)) else 0.0
        self._aw = prof.antiwindup(self, P) if getattr(prof.antiwindup, "factory", False) else prof.antiwindup
        self._k_aw = Tc / P["Tt"] if P.get("Tt") else 0.0
        self.k = 0
        self.dem = 0.0
        self.set_tuning(*(P[r] for r in prof.tuning_roles), _bumpless=False)
        self.outputs = {}
        if prof.stage is not None:                  # výstupní stupeň obalí step / track (rychlá cesta zůstává beze změny)
            stage = prof.stage(self, P)
            self.stage, self.outputs = stage, stage.outputs
            base_step, base_track = Controller.step, Controller.track
            self.step = lambda sp, y_meas, ff=0.0: stage(base_step(self, sp, y_meas, ff))
            self.track = lambda sp, y_meas, u_man, ff=0.0: stage(base_track(self, sp, y_meas, u_man, ff))

    def set_limits(self, lo, hi):
        """Dynamické meze výstupu (MV_LO / MV_HI z override, kaskády) za běhu; regulační zóna je jen s konečnými mezemi."""
        self.lo, self.hi = lo, hi
        cz = (self._params["con_zone"] or 0.0) if self.profile.use_zone else 0.0
        self._cz = cz if (cz > 0 and math.isfinite(lo) and math.isfinite(hi)) else 0.0

    # ---- ladění
    def _set_gains(self, a, b, c):
        Kc, Ti, Td = self.profile.form_fn(a, b, c)
        Tc = self.Tc
        self.Kc, self.Ti, self.Td = Kc, Ti, Td
        self.use_i = Ti is not None and math.isfinite(Ti) and Ti > 0
        self.Tf = Tf = self.profile.d_filter(self._params, Td)
        self._ki = Kc * Tc / Ti if self.use_i else 0.0
        self._use_d = Td > 0
        self._ad = Tf / (Tf + Tc) if self._use_d else 0.0
        self._kd = Kc * Td / (Tf + Tc) if self._use_d else 0.0
        self._ksign = 1.0 if Kc >= 0 else -1.0

    def set_tuning(self, *tuning, _bumpless=True):
        """Změna parametrů za běhu (v rolích formy: ideální Gain, TI, TD) bez rázu výstupu (přepočet I složky)."""
        if _bumpless:
            e = self._err()
            P_old = self._p_term(e)
        self._set_gains(*tuning)
        if _bumpless:
            self.I += P_old - self._p_term(e)

    # ---- části
    def _err(self):
        e = self.spr - self.yf
        return self._db(e) if self._db is not None else e

    def _p_term(self, e):
        # váha b: P = Kc · (b · e − (1 − b) · PV); zbytek P působí jen z PV (b = 1 čistá odchylka, b = 0 jen PV)
        return self.Kc * (self.b * e - self._omb * self.yf)

    def _xd(self, e):
        return -self.yf if self._dsrc else e

    # ---- rozhraní
    def init(self, sp, y_meas, u0, ff=0.0):
        """Bezrázový start: I složka se nastaví tak, aby výstup byl u0."""
        self.u_prev = u0
        self.yf = y_meas
        self.spr = sp
        e = self._err()
        self.I = u0 - self._p_term(e) - ff
        self.D = 0.0
        self.xd_prev = self._xd(e)
        self.u = self.u_prev = u0

    def track(self, sp, y_meas, u_man, ff=0.0):
        """Ruční režim: výstup = u_man, regulátor sleduje (bezrázový přechod do automatu)."""
        self.yf = self._apv * self.yf + self._bpv * y_meas if self._lag else y_meas
        self.spr = sp
        e = self._err()
        self.xd_prev = self._xd(e)
        self.D = 0.0
        self.I = u_man - self._p_term(e) - ff
        self.u = self.u_prev = u_man
        self.k += 1
        return u_man

    def step(self, sp, y_meas, ff=0.0):
        """Jeden krok simulace; vrací výstup (MV). Mezi výpočty (SampleTime > h) drží poslední hodnotu."""
        yf = self.yf = self._apv * self.yf + self._bpv * y_meas if self._lag else y_meas
        k = self.k
        self.k = k + 1
        if k % self.m:
            return self.u
        spr = self.spr
        if self._sprate > 0:
            lim = self._slim
            spr = spr + float(min(max(sp - spr, -lim), lim))
        else:
            spr = sp
        self.spr = spr
        e = spr - yf
        if self._db is not None:
            e = self._db(e)
        Kc = self.Kc
        P = Kc * (self.b * e - self._omb * yf)
        xd = -yf if self._dsrc else e
        if self._use_d:
            self.D = D = self._ad * self.D + self._kd * (xd - self.xd_prev)
        else:
            D = self.D
        self.xd_prev = xd
        u_prev = self.u_prev
        cz = self._cz
        if cz > 0 and abs(e) > cz:
            # regulační zóna: mimo pásmo MV na limit, I sleduje (bezrázový návrat do regulace)
            u = self.hi if e * self._ksign > 0 else self.lo
            if self._rate > 0:
                rl = self._rlim
                u = float(min(max(u, u_prev - rl), u_prev + rl))
            self.I = u - P - D - ff
            self.u = self.u_prev = u
            return u
        inc = self._ki * e if self.use_i else 0.0
        u_un = P + self.I + inc + D + ff
        dem = abs(u_un - u_prev)
        if dem > self.dem:
            self.dem = dem
        u = min(max(u_un, self.lo), self.hi)
        if self._rate > 0:
            rl = self._rlim
            u = float(min(max(u, u_prev - rl), u_prev + rl))
        self.I = self._aw(self.I, inc, u_un, u, self._k_aw)
        self.u = self.u_prev = u
        return u


def ideal_ctrl(profile, ctrl):
    """
    Ekvivalentní ideální regulátor `dict(Gain, TI, TD, DiffGain)` k hodnotám profilu `ctrl` (forma, jednotky a filtr D
    profilu už započtené; Tf = Td / DiffGain). Z něj počítá robustnost, šum a pravidla (`core.robustness`).
    """
    if is_program(profile):
        return ideal_ctrl_program(profile if isinstance(profile, ProgramProfile) else ProgramProfile(profile), ctrl)
    prof = profile if isinstance(profile, Profile) else Profile(profile)
    P = prof.resolve(ctrl)
    Kc, Ti, Td = prof.form_fn(*(P[r] for r in prof.tuning_roles))
    Tf = prof.d_filter(P, Td)
    if prof.d_filter is D_FILTERS.items["td_over_n"][0]:
        dg = P.get("N", 5.0)                          # N přímo (bez zaokrouhlení Td / (Td / N))
    else:
        dg = Td / Tf if (Td > 0 and Tf > 0) else 1e12
    return dict(Gain=Kc, TI=Ti if (Ti is not None and Ti > 0) else _INF, TD=Td, DiffGain=dg, SampleTime=P["Ts"], PVFilt=P.get("pv_filter") or 0.0)


def nonlinear_parts(profile):
    """Nelineární části profilu (ovlivňují linearitu, mapování a robustnost): ['gap', 'nonlinear_gain', 'split_range',
    'three_step', 'pwm']; prázdný seznam = lineární regulátor (mimo omezení výstupu)."""
    if is_program(profile):             # nelinearitu programu nelze určit ze struktury (měří ji kontrola linearity)
        return []
    prof = profile if isinstance(profile, Profile) else Profile(profile)
    st = prof.data["structure"]
    out = []
    modes = list(prof.db_modes.values()) + [prof.db_other]
    if "gap" in modes and any(p["role"] == "deadband" for p in prof.data["params"]):
        out.append("gap")
    if st.get("error", {}).get("nonlinear", {}).get("kind", "none") != "none":
        out.append("nonlinear_gain")
    stage = st.get("output", {}).get("stage", "none")
    if stage in ("split_range", "three_step", "pwm"):
        out.append(stage)
    return out


def make_profile(data):
    """Přeložený profil podle druhu: `Profile` (skládaný) nebo `ProgramProfile` (vlastní rovnice, `kind = program`)."""
    if isinstance(data, (Profile, ProgramProfile)):
        return data
    return ProgramProfile(data) if is_program(data) else Profile(data)


_profiles = {}


def preset_profile(preset_id):
    """Přeložený profil dodané předvolby (např. 'pcs7_pidconl'), vytvořený jednou a sdílený."""
    if preset_id not in _profiles:
        _profiles[preset_id] = Profile(load_preset(preset_id))
    return _profiles[preset_id]


def controller_from_preset(preset_id, ctrl, h):
    """Regulátor z dodané předvolby."""
    return Controller(preset_profile(preset_id), ctrl, h)
