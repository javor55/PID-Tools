"""
Regulátor z vlastních rovnic (R4, docs/cs/regulatory.md § 5): strom výrazů z `controllers.program` se převede na zdrojový
text jedné funkce Pythonu a ta se vykoná v prázdném prostředí (bez builtins) – rychlé (jedno volání funkce na krok, ~1–2 µs)
a bezpečné: kód vzniká jen z ověřeného stromu (názvy `v_<identifikátor>`, čísla jako `repr(float)`, pevná sada pomocných
funkcí). Rozhraní stejné jako `core.controller.Controller`: `init`, `step`, `track`, `set_tuning`, `set_limits`.

Stav programu: `S` (stavy `state`), `H` (skryté stavy stavových funkcí lag / ddt / rate / lead_lag / prev; `None` = ještě
nevyhodnoceno, první volání se inicializuje na vstup). `track` (ruční režim) provede výpočet a poté nastaví stavy podle
jejich výrazů `init` s `MV0` = ruční hodnota (bezrázové převzetí).
"""
import functools
import math
import re

from ..controllers import parse_profile
from ..controllers.program import (FUNCS, compile_program, eval_tree, f_div, f_pow, f_table, program_to_canonical,
                                   tuning_roles)

__all__ = ["ProgramController", "ProgramProfile", "ideal_ctrl_program", "is_program"]

_INF = math.inf


# ================================================================ stavové funkce (JS: ctrl_engine.js, stejné výrazy)
def _lag(H, i, x, T, dt):
    if T <= 0:
        H[i] = x
        return x
    a = math.exp(-dt / T)
    s = H[i]
    if s is None:
        s = x
    s = a * s + (1.0 - a) * x
    H[i] = s
    return s


def _ddt(H, i, x, dt):
    p = H[i]
    H[i] = x
    return 0.0 if p is None else (x - p) / dt


def _rate(H, i, x, up, dn, dt):
    s = H[i]
    if s is None:
        s = x
    else:
        s = s + min(max(x - s, -dn * dt), up * dt)
    H[i] = s
    return s


def _lead_lag(H, i, x, tld, tlg, dt):
    if tlg <= 0:
        H[i] = x
        return x
    a = math.exp(-dt / tlg)
    s = H[i]
    if s is None:
        s = x
    s = a * s + (1.0 - a) * x
    H[i] = s
    return s + (tld / tlg) * (x - s)


def _prev(H, i, x):
    p = H[i]
    H[i] = x
    return x if p is None else p


_NS = {"__builtins__": {}, "min": min, "max": max, "abs": abs, "_sign": FUNCS["sign"], "_sqrt": FUNCS["sqrt"],
       "_exp": FUNCS["exp"], "_log": FUNCS["log"], "_clamp": FUNCS["clamp"], "_deadband": FUNCS["deadband"],
       "_gap": FUNCS["gap"], "_table": f_table, "_div": f_div, "_pow": f_pow, "_s_lag": _lag, "_s_ddt": _ddt,
       "_s_rate": _rate, "_s_lead_lag": _lead_lag, "_s_prev": _prev}
_CMP = ("<", "<=", ">", ">=", "==", "!=")
_LOGIC = ("and", "or")
_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")


def _ident(name):
    """Pojistka před `exec`: do kódu smí jen identifikátor (strom normálně vzniká jen z překladače)."""
    if not isinstance(name, str) or not _IDENT.match(name):
        raise ValueError(f"neplatný název v programu: {name!r}")
    return name


def _emit(n):
    """Strom výrazu → text výrazu Pythonu (jen uzly a operace ze stromu, viz `controllers.program`)."""
    k = n[0]
    if k == "num":
        return repr(float(n[1]))
    if k == "var":
        return "v_" + _ident(n[1])
    if k == "neg":
        return f"(-{_emit(n[1])})"
    if k == "not":
        return f"(1.0 if {_emit(n[1])} == 0.0 else 0.0)"
    if k == "cond":
        return f"({_emit(n[2])} if {_emit(n[1])} != 0.0 else {_emit(n[3])})"
    if k == "table":
        return f"_table({_emit(n[1])}, {[float(v) for v in n[2]]!r}, {[float(v) for v in n[3]]!r})"
    if k == "call":
        name, args = _ident(n[1]), ", ".join(_emit(a) for a in n[2])
        if (f"_s_{name}" if n[3] is not None else name if name in ("min", "max", "abs") else f"_{name}") not in _NS:
            raise ValueError(f"neznámá funkce v programu: {name!r}")
        if n[3] is not None:
            return f"_s_{name}(H, {int(n[3])}, {args}{'' if name == 'prev' else ', v_dt'})"
        return f"{name}({args})" if name in ("min", "max", "abs") else f"_{name}({args})"
    op, a, b = n[1], _emit(n[2]), _emit(n[3])
    if op in ("+", "-", "*"):
        return f"({a} {op} {b})"
    if op == "/":
        return f"_div({a}, {b})"
    if op == "^":
        return f"_pow({a}, {b})"
    if op in _CMP:
        return f"(1.0 if {a} {op} {b} else 0.0)"
    if op not in _LOGIC:
        raise ValueError(f"neznámá operace v programu: {op!r}")
    return f"(1.0 if ({a} != 0.0 {op} {b} != 0.0) else 0.0)"


def _codegen(program):
    L = ["def run(v_SP, v_PV, v_FF, v_MV_LO, v_MV_HI, v_dt, v_t, S, H, p):"]
    L += [f"    v_{_ident(p['name'])} = p[{i}]" for i, p in enumerate(program["params"])]
    L += [f"    v_{_ident(s['name'])} = S[{i}]" for i, s in enumerate(program["states"])]
    for _, name, e in program["body"]:
        L.append(f"    v_{_ident(name)} = {_emit(e)}")
    L += [f"    S[{i}] = v_{s['name']}" for i, s in enumerate(program["states"])]
    L.append(f"    return v_MV, {'v_MV2' if 'MV2' in program['outputs'] else 'None'}")
    ns = dict(_NS)
    exec(compile("\n".join(L), "<program>", "exec"), ns)       # noqa: S102 – kód vzniká jen z ověřeného stromu
    return ns["run"]


@functools.lru_cache(maxsize=64)
def _build(source):
    prog = compile_program(source)["program"]
    return prog, _codegen(prog)


def is_program(profile):
    return isinstance(profile, ProgramProfile) or (isinstance(profile, dict) and profile.get("kind") == "program")


class ProgramProfile:
    """Přeložený profil typu `program`: `data` (s odvozenými `params` a `program`), `tuning_roles` = cíle příkazů `map`."""

    is_program = True

    def __init__(self, data):
        self.data = data = parse_profile(data)
        self.id = data["id"]
        self.program, self.run = _build(data["source"])
        self.tuning_roles = tuning_roles(self.program)
        self.params = [(p["name"], p["name"], p["default"], False, False, None, None) for p in self.program["params"]]


class ProgramController:
    """Regulátor z vlastních rovnic; rozhraní jako `Controller` (init / step / track / set_tuning / set_limits)."""

    def __init__(self, profile, ctrl, h):
        prof = profile if isinstance(profile, ProgramProfile) else ProgramProfile(profile)
        self.profile, self.h = prof, h
        prog = prof.program
        self._names = [p["name"] for p in prog["params"]]
        self._rng = [(p["min"], p["max"]) for p in prog["params"]]
        self._vals = [self._clamp(i, ctrl.get(p["name"]) if ctrl.get(p["name"]) is not None else p["default"])
                      for i, p in enumerate(prog["params"])]
        self._p = tuple(self._vals)
        ts = self._vals[self._names.index("Ts")] if "Ts" in self._names else h
        self.m = max(1, int(round(ts / h)))
        self.Tc = self.m * h
        lo, hi = ctrl.get("MV_Lo", ctrl.get("MV_LO")), ctrl.get("MV_Hi", ctrl.get("MV_HI"))
        self.lo, self.hi = (-_INF if lo is None else lo), (_INF if hi is None else hi)
        self._run, self._states, self._init = prof.run, prog["states"], [s["init_expr"] for s in prog["states"]]
        self.outputs = {}
        self.k, self.dem, self.u = 0, 0.0, 0.0
        self.spr = self.yf = 0.0
        self.ext_reset = None
        self.S = [s["init"] for s in self._states]
        self.H = [None] * len(prog["hidden"])

    def _clamp(self, i, v):
        lo, hi = self._rng[i]
        v = float(v)
        return min(max(v, lo if lo is not None else -_INF), hi if hi is not None else _INF)

    def _env(self, sp, y, ff, u0):
        env = dict(zip(self._names, self._p))
        env.update(SP=sp, PV=y, FF=ff, MV0=u0)
        return env

    def _apply_init(self, sp, y, ff, u0):
        env = self._env(sp, y, ff, u0)
        for i, e in enumerate(self._init):
            if e is not None:
                self.S[i] = eval_tree(e, env)

    def set_tuning(self, *tuning):
        """Změna parametrů za běhu: hodnoty pro cíle příkazů `map` v pořadí zdroje (`profile.tuning_roles`)."""
        for name, v in zip(self.profile.tuning_roles, tuning):
            i = self._names.index(name)
            self._vals[i] = self._clamp(i, v)
        self._p = tuple(self._vals)

    def set_limits(self, lo, hi):
        """Vstupy MV_LO / MV_HI programu (dynamické meze)."""
        self.lo, self.hi = lo, hi

    def init(self, sp, y_meas, u0, ff=0.0):
        """Bezrázový start: stavy podle výrazů `init` (MV0 = u0), skryté stavy se inicializují prvním voláním."""
        self.spr, self.yf, self.k = sp, y_meas, 0
        self.S = [s["init"] for s in self._states]
        self.H = [None] * len(self.H)
        self._apply_init(sp, y_meas, ff, u0)
        self.u = u0

    def _eval(self, sp, y, ff):
        mv, mv2 = self._run(sp, y, ff, self.lo, self.hi, self.Tc, self.k * self.h, self.S, self.H, self._p)
        if mv2 is not None:
            self.outputs["MV2"] = mv2
        return mv

    def track(self, sp, y_meas, u_man, ff=0.0):
        """Ruční režim: výstup = u_man, stavy se nastaví podle `init` výrazů (bezrázový přechod do automatu)."""
        k = self.k
        self.k = k + 1
        self.spr, self.yf = sp, y_meas
        if not k % self.m:
            self._eval(sp, y_meas, ff)
        self._apply_init(sp, y_meas, ff, u_man)
        self.u = u_man
        return u_man

    def step(self, sp, y_meas, ff=0.0):
        """Jeden krok simulace; vrací MV. Mezi výpočty (Ts > h) drží poslední hodnotu."""
        k = self.k
        self.spr, self.yf = sp, y_meas
        if k % self.m:
            self.k = k + 1
            return self.u
        self.u = u = self._eval(sp, y_meas, ff)
        self.k = k + 1
        return u


def ideal_ctrl_program(prof, ctrl):
    """Ekvivalentní ideální PID `dict(Gain, TI, TD, DiffGain, SampleTime, PVFilt)` z hodnot parametrů programu (přes `unmap`)."""
    vals = {n: ctrl.get(n) for n in (p["name"] for p in prof.program["params"])}
    eff = program_to_canonical(prof.program, vals)
    ts = ctrl.get("Ts")
    return dict(Gain=eff["Kc"], TI=eff["Ti"], TD=eff["Td"], DiffGain=eff["N"], SampleTime=ts if ts else 1.0, PVFilt=0.0)

