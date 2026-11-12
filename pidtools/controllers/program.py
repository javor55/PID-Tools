"""
Jazyk vlastních rovnic regulátoru (R4, docs/cs/regulatory.md § 5): bezpečný malý jazyk bez cyklů a I/O. Zdroj (text) se
přeloží (`compile_program`) do stromu výrazů (JSON), který vykonávají oba interprety: `core.program` (Python, generovaná
rychlá funkce) a `ctrl_engine.js`. Strom je jediná pravda o chování; sem patří i pomocné funkce se stejnou sémantikou jako
v JS (dělení nulou = 0, bezpečné sqrt / log / exp / mocnina).

Zdroj – jeden příkaz na řádek, `#` komentář:

    param Kp = 1.0 "Zesílení" [-] min 0 max 100     # parametr: výchozí hodnota, popis, jednotka, meze
    state I = 0 [%] init MV0 - Kp * (SP - PV)       # stav mezi kroky; `init` = bezrázový start (SP, PV, FF, MV0, param)
    e = SP - PV                                       # přiřazení (lokální proměnná, stav nebo výstup MV, MV2)
    MV = clamp(Kp * e + I, MV_LO, MV_HI)
    map Kp = Kc                                       # mapování kanonického PID (Kc, Ti, Td, b, c, N) → parametr
    unmap Kc = Kp                                     # opačně: parametry → kanonický PID (u jednoduchých map samo)

Vstupy: SP, PV, FF, MV_LO, MV_HI, dt (perioda výpočtu), t (čas). Výrazy: `+ - * / ^`, porovnání, `and or not`, `c ? a : b`
(logika = 1 / 0). Funkce: min max abs sign sqrt exp log clamp deadband gap table(x, [x…], [y…]) a funkce se stavem
(každé volání má vlastní stav) lag(x, T) ddt(x) rate(x, nahoru, dolů) lead_lag(x, Tlead, Tlag) prev(x); stavové funkce
nesmí být ve větvi podmínky ani za `and` / `or`. Dělení nulou dává 0, sqrt záporného 0, log nepositivního log(1e-300),
exp(x > 700) exp(700), mocnina s neplatným nebo nekonečným výsledkem 0. Seznam `[…]` v `table` nelze v `init` stavu
(řádek `state` bere `[…]` jako jednotku).
Omezení: velikost zdroje, počet příkazů, parametrů, stavů a uzlů stromu (`LIMITS`), hloubka výrazu.
"""
import copy
import functools
import math
import re

__all__ = ["FORMAT", "FUNCS", "LIMITS", "ProgramError", "ProgramErrors", "STATEFUL", "canonical_to_program",
           "compile_program", "eval_tree", "has_mapping", "program_params", "program_to_canonical", "tuning_roles"]

FORMAT = "pidprog"
VERSION = 1
LIMITS = dict(source=20000, statements=200, params=40, states=40, nodes=3000, depth=60, hidden=60, table=64)
INPUTS = ("SP", "PV", "FF", "MV_LO", "MV_HI", "dt", "t")
OUTPUTS = ("MV", "MV2")
ROLES = ("Kc", "Ti", "Td", "b", "c", "N")                   # kanonický PID (mapování)
KEYWORDS = {"param", "state", "map", "unmap", "init", "and", "or", "not"}
STATEFUL = {"lag": 2, "ddt": 1, "rate": 3, "lead_lag": 3, "prev": 1}          # název → počet argumentů
PURE = {"min": (2, 8), "max": (2, 8), "abs": (1, 1), "sign": (1, 1), "sqrt": (1, 1), "exp": (1, 1), "log": (1, 1),
        "clamp": (3, 3), "deadband": (2, 2), "gap": (3, 3), "table": (3, 3)}
_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_NUM = re.compile(r"(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?")
_OPS = ("<=", ">=", "==", "!=", "+", "-", "*", "/", "^", "(", ")", "[", "]", ",", "?", ":", "=", "<", ">")


class ProgramError(ValueError):
    """Chyba nebo varování překladu: `code` (klíč textu `ctl_e_<code>` / `ctl_wn_<code>`), `args`, řádek a sloupec (od 1)."""

    def __init__(self, code, args=None, line=1, col=1):
        self.code, self.info, self.line, self.col = code, args or {}, line, col       # `info` (ne `args`: to je výjimky)
        super().__init__(f"{line}:{col} {code} {self.info}")

    def as_dict(self):
        return dict(code=self.code, args=self.info, line=self.line, col=self.col)


class ProgramErrors(ValueError):
    """Neúspěšný překlad: `errors` = [ProgramError]."""

    def __init__(self, errors):
        self.errors = errors
        super().__init__("; ".join(str(e) for e in errors[:3]))


# ================================================================ funkce (sémantika sdílená s ctrl_engine.js)
def f_sign(x):
    return 1.0 if x > 0 else (-1.0 if x < 0 else 0.0)


def f_sqrt(x):
    return math.sqrt(x) if x > 0 else 0.0


def f_exp(x):
    return math.exp(min(x, 700.0))


def f_log(x):
    return math.log(max(x, 1e-300))


def f_clamp(x, lo, hi):
    return min(max(x, lo), hi)


def f_deadband(x, w):
    return x - (1.0 if x > 0 else -1.0) * w if abs(x) >= w else 0.0


def f_gap(x, w, k):
    return k * x if abs(x) < w else x - (1.0 if x > 0 else -1.0) * w * (1.0 - k)


def f_div(a, b):
    return a / b if b != 0.0 else 0.0


def f_pow(a, b):
    try:
        r = math.pow(a, b)
    except (ValueError, OverflowError):
        return 0.0
    return r if math.isfinite(r) else 0.0


def f_table(x, xs, ys):
    if x <= xs[0]:
        return ys[0]
    for i in range(1, len(xs)):
        if x < xs[i]:
            return ys[i - 1] + (ys[i] - ys[i - 1]) * (x - xs[i - 1]) / (xs[i] - xs[i - 1])
    return ys[-1]


FUNCS = dict(min=min, max=max, abs=abs, sign=f_sign, sqrt=f_sqrt, exp=f_exp, log=f_log, clamp=f_clamp, deadband=f_deadband,
             gap=f_gap, table=f_table, div=f_div, pow=f_pow)


# ================================================================ lexer
def _tokens(text, no, decl):
    """Tokeny řádku: (druh, hodnota, sloupec). U řádků `param` / `state` je `[…]` jedna jednotka (druh 'unit')."""
    out, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if c in " \t\r":
            i += 1
        elif c == "#":
            break
        elif c == '"':
            j = text.find('"', i + 1)
            if j < 0:
                raise ProgramError("unterminated_string", {}, no, i + 1)
            out.append(("str", text[i + 1:j], i + 1))
            i = j + 1
        elif c == "[" and decl:
            j = text.find("]", i + 1)
            if j < 0:
                raise ProgramError("unterminated_unit", {}, no, i + 1)
            out.append(("unit", text[i + 1:j].strip(), i + 1))
            i = j + 1
        elif c.isdigit() or (c == "." and i + 1 < n and text[i + 1].isdigit()):
            m = _NUM.match(text, i)
            val = float(m.group())
            if not math.isfinite(val):
                raise ProgramError("bad_number", dict(text=m.group()), no, i + 1)
            out.append(("num", val, i + 1))
            i = m.end()
        elif c.isalpha() or c == "_":
            m = _IDENT.match(text, i)
            if m is None:
                raise ProgramError("bad_char", dict(ch=c), no, i + 1)
            out.append(("id", m.group(), i + 1))
            i = m.end()
        else:
            op = next((o for o in _OPS if text.startswith(o, i)), None)
            if op is None:
                raise ProgramError("bad_char", dict(ch=c), no, i + 1)
            out.append(("op", op, i + 1))
            i += len(op)
    return out


# ================================================================ parser (jeden příkaz na řádek)
class _Parser:
    def __init__(self, toks, no, text):
        self.t, self.i, self.no, self.end, self.paren = toks, 0, no, len(text) + 1, 0

    def peek(self):
        return self.t[self.i] if self.i < len(self.t) else ("eol", None, self.end)

    def err(self, code, tok=None, **args):
        tok = tok or self.peek()
        return ProgramError(code, args, self.no, tok[2])

    def take(self):
        tok = self.peek()
        self.i += 1
        return tok

    def accept(self, kind, val=None):
        k, v, _ = self.peek()
        if k == kind and (val is None or v == val):
            return self.take()
        return None

    def expect(self, kind, val=None, what=None):
        tok = self.accept(kind, val)
        if tok is None:
            raise self.err("expected", what=what or val or kind)
        return tok

    def done(self):
        if self.peek()[0] != "eol":
            raise self.err("unexpected", token=str(self.peek()[1]))

    def node(self, k, tok, **kw):
        kids = [kw[x] for x in ("a", "b", "c") if x in kw] + kw.get("args", [])
        d = 1 + max((x.get("d", 1) for x in kids), default=0)
        if d > LIMITS["depth"]:                         # hloubka stromu (i dlouhý řetěz `a + b + …`) je omezená
            raise ProgramError("too_deep", dict(max=LIMITS["depth"]), self.no, tok[2])
        return dict(k=k, line=self.no, col=tok[2], d=d, **kw)

    # ---- výrazy
    def expr(self, depth=0):
        c = self.or_()
        if (q := self.accept("op", "?")):
            a = self.expr()
            self.expect("op", ":", ":")
            b = self.expr()
            return self.node("cond", q, c=c, a=a, b=b)
        return c

    def or_(self):
        a = self.and_()
        while (tok := self.accept("id", "or")):
            a = self.node("bin", tok, op="or", a=a, b=self.and_())
        return a

    def and_(self):
        a = self.not_()
        while (tok := self.accept("id", "and")):
            a = self.node("bin", tok, op="and", a=a, b=self.not_())
        return a

    def not_(self):
        if (tok := self.accept("id", "not")):
            return self.node("not", tok, a=self.not_())
        return self.cmp()

    def cmp(self):
        a = self.add()
        k, v, _ = self.peek()
        if k == "op" and v in ("<", "<=", ">", ">=", "==", "!="):
            tok = self.take()
            return self.node("bin", tok, op=v, a=a, b=self.add())
        return a

    def add(self):
        a = self.mul()
        while self.peek()[0] == "op" and self.peek()[1] in ("+", "-"):
            tok = self.take()
            a = self.node("bin", tok, op=tok[1], a=a, b=self.mul())
        return a

    def mul(self):
        a = self.unary()
        while self.peek()[0] == "op" and self.peek()[1] in ("*", "/"):
            tok = self.take()
            a = self.node("bin", tok, op=tok[1], a=a, b=self.unary())
        return a

    def unary(self):
        if (tok := self.accept("op", "-")):
            return self.node("neg", tok, a=self.unary())
        return self.power()

    def power(self):
        a = self.atom()
        if (tok := self.accept("op", "^")):
            return self.node("bin", tok, op="^", a=a, b=self.unary())
        return a

    def number_list(self):
        tok = self.expect("op", "[", "[")
        vals = []
        while True:
            sign = -1.0 if self.accept("op", "-") else 1.0
            vals.append(sign * self.expect("num", None, "number")[1])
            if not self.accept("op", ","):
                break
        self.expect("op", "]", "]")
        return self.node("list", tok, v=vals)

    def atom(self):
        tok = self.take()
        k, v, _ = tok
        if k == "num":
            return self.node("num", tok, v=v)
        if k == "op" and v == "(":
            self.paren += 1
            if self.paren > LIMITS["depth"]:
                raise self.err("too_deep", tok, max=LIMITS["depth"])
            e = self.expr(1)
            self.expect("op", ")", ")")
            self.paren -= 1
            return e
        if k == "id":
            if v in KEYWORDS:
                raise self.err("reserved", tok, name=v)
            if self.accept("op", "("):
                args = []
                if not self.accept("op", ")"):
                    while True:
                        k2, v2, _ = self.peek()
                        if v == "table" and args and k2 == "op" and v2 == "[":
                            args.append(self.number_list())
                        else:
                            args.append(self.expr(1))
                        if self.accept("op", ")"):
                            break
                        self.expect("op", ",", ", )")
                return self.node("call", tok, name=v, args=args)
            return self.node("var", tok, name=v)
        self.i -= 1
        raise self.err("expected", tok, what="expression")

    def signed(self):
        sign = -1.0 if self.accept("op", "-") else 1.0
        if sign > 0:
            self.accept("op", "+")
        return sign * self.expect("num", None, "number")[1]


def _parse_line(text, no):
    """Příkaz řádku jako slovník (druh, název, …) nebo None pro prázdný řádek."""
    first = text.split("#", 1)[0].split(None, 1)
    decl = bool(first) and first[0] in ("param", "state")
    toks = _tokens(text, no, decl)
    if not toks:
        return None
    p = _Parser(toks, no, text)
    k, v, col = p.take()
    if k != "id":
        raise p.err("expected", toks[0], what="statement")
    base = dict(line=no, col=col)
    if v in ("param", "state"):
        name = p.expect("id", None, "name")
        p.expect("op", "=", "=")
        st = dict(base, kind=v, name=name[1], ncol=name[2], default=p.signed(), unit="", desc="", min=None, max=None, init=None)
        while p.peek()[0] != "eol":
            k2, v2, c2 = p.take()
            if k2 == "str" and v == "param":
                st["desc"] = v2
            elif k2 == "unit":
                st["unit"] = v2
            elif k2 == "id" and v == "param" and v2 in ("min", "max"):
                st[v2] = p.signed()
            elif k2 == "id" and v == "state" and v2 == "init":
                st["init"] = p.expr()
            else:
                raise ProgramError("unexpected", dict(token=str(v2)), no, c2)
        return st
    if v in ("map", "unmap"):
        name = p.expect("id", None, "name")
        p.expect("op", "=", "=")
        st = dict(base, kind=v, name=name[1], ncol=name[2], expr=p.expr())
        p.done()
        return st
    if v in KEYWORDS:
        raise p.err("reserved", toks[0], name=v)
    p.expect("op", "=", "=")
    st = dict(base, kind="set", name=v, expr=p.expr())
    p.done()
    return st


# ================================================================ kontrola a převod na strom
def _unit(u):
    return None if u in ("", "-") else u


class _Checker:
    """Kontrola názvů, arity, stavových funkcí a (lehká) jednotek; výsledkem je JSON strom výrazu."""

    def __init__(self, params, states):
        self.names = {n: ("input", "s" if n in ("dt", "t") else None) for n in INPUTS}
        self.names.update({p["name"]: ("param", _unit(p["unit"])) for p in params})
        self.names.update({s["name"]: ("state", _unit(s["unit"])) for s in states})
        self.defined = set(self.names)
        self.errors, self.warnings, self.hidden = [], [], []
        self.assigned_later = set()
        self.extra = set()          # názvy navíc (MV0 v init, kanonické role v map)

    def err(self, node, code, **args):
        self.errors.append(ProgramError(code, args, node["line"], node["col"]))

    def warn(self, node, code, **args):
        self.warnings.append(ProgramError(code, args, node["line"], node["col"]))

    def expr(self, n, cond=False, stateless=False):
        """Zkontroluje výraz a vrátí (JSON uzel, jednotka). Při chybě je uzel náhradní 0 (chyba je v `errors`)."""
        k = n["k"]
        if k == "num":
            return ["num", n["v"]], None
        if k == "var":
            name = n["name"]
            if name in self.extra:
                return ["var", name], None
            if name in self.defined:
                return ["var", name], self.names.get(name, ("", None))[1]
            self.err(n, "use_before_assign" if name in self.assigned_later else "unknown_name", name=name)
            return ["num", 0.0], None
        if k == "neg":
            a, u = self.expr(n["a"], cond, stateless)
            return ["neg", a], u
        if k == "not":
            return ["not", self.expr(n["a"], cond, stateless)[0]], None
        if k == "cond":
            c, _ = self.expr(n["c"], cond, stateless)
            a, ua = self.expr(n["a"], True, stateless)
            b, ub = self.expr(n["b"], True, stateless)
            self._same(n, ua, ub)
            return ["cond", c, a, b], ua or ub
        if k == "bin":
            op = n["op"]
            a, ua = self.expr(n["a"], cond, stateless)
            b, ub = self.expr(n["b"], cond or op in ("and", "or"), stateless)
            if op in ("+", "-"):
                self._same(n, ua, ub)
                return ["bin", op, a, b], ua or ub
            if op == "*":      # jednotka jen u násobení číslem; součiny veličin jsou „neznámé“ (bez falešných varování)
                return ["bin", op, a, b], (ub if n["a"]["k"] == "num" else (ua if n["b"]["k"] == "num" else None))
            if op == "/":
                return ["bin", op, a, b], (ua if n["b"]["k"] == "num" else None)
            return ["bin", op, a, b], None
        if k == "list":
            self.err(n, "list_not_allowed")
            return ["num", 0.0], None
        return self.call(n, cond, stateless)

    def _same(self, n, ua, ub):
        if ua is not None and ub is not None and ua != ub:
            self.warn(n, "unit_mismatch", a=ua, b=ub)

    def call(self, n, cond, stateless):
        name, args = n["name"], n["args"]
        if name in STATEFUL:
            if len(args) != STATEFUL[name]:
                self.err(n, "arity", name=name, n=STATEFUL[name])
                return ["num", 0.0], None
            if cond:
                self.err(n, "stateful_in_branch", name=name)
            if stateless:
                self.err(n, "stateful_not_allowed", name=name)
            sub = [self.expr(a, cond, stateless) for a in args]
            self.hidden.append(name)
            return ["call", name, [s[0] for s in sub], len(self.hidden) - 1], (None if name == "ddt" else sub[0][1])
        if name not in PURE:
            self.err(n, "unknown_function", name=name)
            return ["num", 0.0], None
        lo, hi = PURE[name]
        if not lo <= len(args) <= hi:
            self.err(n, "arity", name=name, n=lo if lo == hi else f"{lo}–{hi}")
            return ["num", 0.0], None
        if name == "table":
            x, _ = self.expr(args[0], cond, stateless)
            if args[1]["k"] != "list" or args[2]["k"] != "list":
                self.err(n, "table_lists")
                return ["num", 0.0], None
            xs, ys = args[1]["v"], args[2]["v"]
            if len(xs) < 2 or len(xs) != len(ys) or len(xs) > LIMITS["table"]:
                self.err(args[1], "table_size", max=LIMITS["table"])
            elif any(b <= a for a, b in zip(xs, xs[1:])):
                self.err(args[1], "table_order")
            return ["table", x, xs, ys], None
        sub = [self.expr(a, cond, stateless) for a in args]
        if name in ("min", "max", "clamp"):
            for s in sub[1:]:
                self._same(n, sub[0][1], s[1])
        keep = name in ("min", "max", "abs", "clamp", "deadband", "gap")
        return ["call", name, [s[0] for s in sub], None], (sub[0][1] if keep else None)


def _count(node):
    return 1 + sum(_count(c) for c in node if isinstance(c, list)) if isinstance(node, list) else 0


def _depth(node):
    return 1 + max((_depth(c) for c in node if isinstance(c, list)), default=0) if isinstance(node, list) else 0


@functools.lru_cache(maxsize=64)
def _compile_cached(source):
    return _compile(source)


def compile_program(source):
    """
    Zdroj → dict(program=strom, warnings=[ProgramError]). Chyby: `ProgramErrors` (seznam `ProgramError` s řádkem a
    sloupcem). Strom: {format, version, params, states, hidden, body, outputs, map, unmap}; viz modul.
    """
    if not isinstance(source, str):
        raise ProgramErrors([ProgramError("not_text")])
    res = _compile_cached(source)
    if isinstance(res, ProgramErrors):
        raise res
    return dict(program=copy.deepcopy(res["program"]), warnings=list(res["warnings"]))


def _check_decls(params, states):
    """Kontrola deklarací: rezervované a duplicitní názvy, meze a výchozí hodnoty parametrů."""
    errs = []
    seen = {}
    for s in params + states:
        n = s["name"]
        if n in INPUTS or n in OUTPUTS or n in KEYWORDS or n in PURE or n in STATEFUL or n == "MV0":
            errs.append(ProgramError("reserved", dict(name=n), s["line"], s["ncol"]))
        elif n in seen:
            errs.append(ProgramError("duplicate", dict(name=n, line=seen[n]), s["line"], s["ncol"]))
        seen[n] = s["line"]
        lo, hi = s["min"], s["max"]
        if s["kind"] == "param":
            if lo is not None and hi is not None and lo > hi:
                errs.append(ProgramError("range_order", {}, s["line"], s["col"]))
            elif (lo is not None and s["default"] < lo) or (hi is not None and s["default"] > hi):
                errs.append(ProgramError("default_out_of_range", dict(name=n), s["line"], s["col"]))
    return errs


def _compile(source):
    errs = []
    if len(source) > LIMITS["source"]:
        return ProgramErrors([ProgramError("too_big", dict(what="source", max=LIMITS["source"]))])
    stmts = []
    for no, text in enumerate(source.split("\n"), 1):
        try:
            st = _parse_line(text, no)
        except ProgramError as ex:
            errs.append(ex)
            continue
        except RecursionError:
            errs.append(ProgramError("too_deep", dict(max=LIMITS["depth"]), no, 1))
            continue
        if st:
            stmts.append(st)
    if len(stmts) > LIMITS["statements"]:
        errs.append(ProgramError("too_big", dict(what="statements", max=LIMITS["statements"])))
    params = [s for s in stmts if s["kind"] == "param"]
    states = [s for s in stmts if s["kind"] == "state"]
    if len(params) > LIMITS["params"] or len(states) > LIMITS["states"]:
        errs.append(ProgramError("too_big", dict(what="params / states", max=LIMITS["params"])))
    errs += _check_decls(params, states)

    def checker(with_states=True):
        return _Checker([dict(name=p["name"], unit=p["unit"]) for p in params],
                        [dict(name=s["name"], unit=s["unit"]) for s in states] if with_states else [])

    ck = checker()
    sets = [s for s in stmts if s["kind"] == "set"]
    ck.assigned_later = {s["name"] for s in sets}
    for s in sets:
        n = s["name"]
        if n in INPUTS or n == "MV0":
            errs.append(ProgramError("assign_input", dict(name=n), s["line"], s["col"]))
        elif n in ck.names and ck.names[n][0] == "param":
            errs.append(ProgramError("assign_param", dict(name=n), s["line"], s["col"]))
        elif n in PURE or n in STATEFUL:
            errs.append(ProgramError("reserved", dict(name=n), s["line"], s["col"]))
    states_out = []
    ck_init = checker(False)            # init výrazy stavů: parametry, vstupy a MV0, bez stavových funkcí
    ck_init.extra = {"MV0"}
    for s in states:
        init = ck_init.expr(s["init"], False, True)[0] if s["init"] is not None else None
        states_out.append(dict(name=s["name"], init=s["default"], unit=s["unit"], init_expr=init))
    errs += ck_init.errors
    body, outputs = [], []
    for s in sets:
        node, unit = ck.expr(s["expr"])
        n = s["name"]
        if n in OUTPUTS and n not in outputs:
            outputs.append(n)
        if n in ck.names and ck.names[n][0] == "state" and ck.names[n][1] and unit and ck.names[n][1] != unit:
            ck.warn(s, "unit_mismatch", a=ck.names[n][1], b=unit)
        ck.defined.add(n)
        body.append(["set", n, node])
    if "MV" not in outputs and not errs and not ck.errors:
        ck.errors.append(ProgramError("missing_mv", {}, 1, 1))
    if len(ck.hidden) > LIMITS["hidden"]:
        ck.errors.append(ProgramError("too_big", dict(what="stateful functions", max=LIMITS["hidden"])))
    pnames = {p["name"] for p in params}
    maps, unmaps = [], []
    for s in stmts:
        if s["kind"] == "map":
            if s["name"] not in pnames:
                errs.append(ProgramError("map_target", dict(name=s["name"]), s["line"], s["ncol"]))
            m = checker(False)
            m.extra = set(ROLES)
            m.defined -= set(pnames)
            maps.append([s["name"], m.expr(s["expr"], False, True)[0]])
            errs += m.errors
        elif s["kind"] == "unmap":
            if s["name"] not in ROLES:
                errs.append(ProgramError("unmap_target", dict(name=s["name"], roles=", ".join(ROLES)), s["line"], s["ncol"]))
            m = checker(False)
            unmaps.append([s["name"], m.expr(s["expr"], False, True)[0]])
            errs += m.errors
    errs += ck.errors
    program = dict(format=FORMAT, version=VERSION,
                   params=[dict(name=p["name"], default=p["default"], unit=p["unit"], desc=p["desc"], min=p["min"], max=p["max"])
                           for p in params],
                   states=states_out, hidden=ck.hidden, body=body, outputs=outputs, map=maps, unmap=unmaps)
    if sum(_count(b[2]) for b in body) > LIMITS["nodes"]:
        errs.append(ProgramError("too_big", dict(what="nodes", max=LIMITS["nodes"])))
    if any(_depth(b[2]) > LIMITS["depth"] for b in body):
        errs.append(ProgramError("too_deep", dict(max=LIMITS["depth"]), 1, 1))
    if errs:
        errs.sort(key=lambda e: (e.line, e.col))
        return ProgramErrors(errs)
    return dict(program=program, warnings=ck.warnings)


# ================================================================ vyhodnocení stromu (mapování, init výrazy)
def eval_tree(n, env):
    """Hodnota bezstavového výrazu (uzel stromu) při proměnných `env`; stejná sémantika jako generovaný kód a JS."""
    k = n[0]
    if k == "num":
        return n[1]
    if k == "var":
        return env[n[1]]
    if k == "neg":
        return -eval_tree(n[1], env)
    if k == "not":
        return 1.0 if eval_tree(n[1], env) == 0.0 else 0.0
    if k == "cond":
        return eval_tree(n[2], env) if eval_tree(n[1], env) != 0.0 else eval_tree(n[3], env)
    if k == "table":
        return f_table(eval_tree(n[1], env), n[2], n[3])
    if k == "call":
        return FUNCS[n[1]](*[eval_tree(a, env) for a in n[2]])
    op = n[1]
    a = eval_tree(n[2], env)
    if op == "and":
        return 1.0 if (a != 0.0 and eval_tree(n[3], env) != 0.0) else 0.0
    if op == "or":
        return 1.0 if (a != 0.0 or eval_tree(n[3], env) != 0.0) else 0.0
    b = eval_tree(n[3], env)
    if op == "+":
        return a + b
    if op == "-":
        return a - b
    if op == "*":
        return a * b
    if op == "/":
        return f_div(a, b)
    if op == "^":
        return f_pow(a, b)
    return 1.0 if {"<": a < b, "<=": a <= b, ">": a > b, ">=": a >= b, "==": a == b, "!=": a != b}[op] else 0.0


# ================================================================ parametry a mapování programu
def program_params(program):
    """Seznam parametrů profilu (`params`) odvozený z deklarací `param` programu: klíč = role = název."""
    out = []
    for p in program["params"]:
        d = dict(key=p["name"], role=p["name"], name=p["name"], unit=p["unit"] or "-", default=p["default"])
        if p["desc"]:
            d["description"] = p["desc"]
        if p["min"] is not None or p["max"] is not None:
            d["range"] = [p["min"] if p["min"] is not None else -1e300, p["max"] if p["max"] is not None else 1e300]
        out.append(d)
    return out


def tuning_roles(program):
    """Parametry, které pravidla ladění nastavují: cíle příkazů `map` v pořadí zdroje."""
    return [m[0] for m in program["map"]]


def _reverse(program):
    rev = {r: e for r, e in program["unmap"]}
    for name, e in program["map"]:
        if e[0] == "var" and e[1] in ROLES and e[1] not in rev:
            rev[e[1]] = ["var", name]
    return rev


def has_mapping(program):
    """Program lze ladit pravidly: má `map` a zpětné mapování Kc (`unmap Kc = …` nebo `map … = Kc`)."""
    return bool(program["map"]) and "Kc" in _reverse(program)


def _inf(x):
    return math.inf if (x is None or not x or x <= 0 or not math.isfinite(x)) else float(x)


def canonical_to_program(program, canon):
    """Kanonický PID → hodnoty parametrů programu {název: hodnota} podle příkazů `map`."""
    if not program["map"]:
        raise ValueError("program nemá mapování (příkazy `map`), pravidla ladění nelze použít")
    env = dict(Kc=float(canon["Kc"]), Ti=_inf(canon.get("Ti")), Td=float(canon.get("Td", 0.0) or 0.0),
               b=float(canon.get("b", 1.0)), c=float(canon.get("c", 1.0)), N=_inf(canon.get("N", 5.0)))
    return {name: eval_tree(e, env) for name, e in program["map"]}


def program_to_canonical(program, values):
    """Hodnoty parametrů programu → kanonický PID (příkazy `unmap`, u jednoduchých `map` samo)."""
    rev = _reverse(program)
    if "Kc" not in rev:
        raise ValueError("program nemá zpětné mapování Kc (příkaz `unmap Kc = …` nebo `map … = Kc`)")
    env = {p["name"]: float(p["default"] if values.get(p["name"]) is None else values[p["name"]]) for p in program["params"]}
    out = dict(Ti=math.inf, Td=0.0, b=1.0, c=1.0, N=5.0)
    for role, e in rev.items():
        out[role] = eval_tree(e, env)
    out["Ti"] = _inf(out["Ti"])
    return out
