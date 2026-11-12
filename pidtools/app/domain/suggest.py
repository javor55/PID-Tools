"""
Automatický návrh smyček podle názvů tagů a import mapování z CSV (čisté funkce nad názvy, bez dat).

Rozpoznané zápisy (tag smyčky + role signálu):
  TIC101.PV / .SP / .OUT | .MV | .OP     – tag s příponou role
  TIC101/PV_Out, /SP_Out, /MV, /LMN      – PCS 7 (parametry bloku APL / PID)
  TIC101/PID1/PV.CV, /SP.CV, /OUT.CV     – DeltaV (modul / blok / parametr.pole; blok PID se vynechá z tagu)
Co se takto nepozná, rozdělí podle slov v názvu `app.guess` (LIC101.PV_Out → ostatní heuristiky stejně jako u jedné
smyčky). Návrh nic nemění; vrací seznam smyček a nepoužité signály.
"""
import csv
import io
import re
from dataclasses import dataclass, field

from ...i18n import T
from .. import guess
from ..dataio import decode_text
from .model import LoopSpec, Roles, SourceRef

# parametry bloku (DeltaV, PCS 7) → role; porovnává se malými písmeny bez pole `.CV` / `.ST`
PARAM_ROLE = [
    (re.compile(r"^pv(_?(out|in|filt|filtered))?$"), "pv"),
    (re.compile(r"^sp(_?(out|int|ext|internal))?$"), "sp"),
    (re.compile(r"^(mv|lmn|out|op|out_d|mv_out|cv_out)$"), "mv"),
    (re.compile(r"^(pos|posfb|bkcal_in|bkcal_out|fb|rbk|zpos|lmn_pos)$"), "pos"),
    (re.compile(r"^(mode|auto|man|mode_act|actmode|ctrl_mode)$"), "mode"),
]
FIELD = re.compile(r"\.(cv|st|cst|value)$", re.I)                      # pole parametru DeltaV
BLOCK = re.compile(r"^(pid\w*|ai\w*|ao\w*|aio\w*|apl\w*|pidcon\w*|pidpro\w*)$", re.I)   # blok, ne tag smyčky


@dataclass
class Suggestion:
    """Navržená smyčka: tag, role → odkaz na sloupec zdroje, důvod (`pcs7` / `deltav` / `dot` / `guess`)."""
    tag: str
    roles: Roles = field(default_factory=Roles)
    via: str = "dot"
    description: str = ""

    @property
    def complete(self):
        """Smyčka se dá použít: má PV a MV."""
        return self.roles.pv is not None and self.roles.mv is not None

    def to_spec(self):
        return LoopSpec(tag=self.tag, description=self.description, roles=self.roles)


def _role_of(param):
    p = param.strip().lower()
    for rx, role in PARAM_ROLE:
        if rx.match(p):
            return role
    return None


def parse_name(name):
    """Název signálu → (tag smyčky, role, způsob rozpoznání), nebo None, když se z názvu nepozná."""
    s = str(name).strip()
    m = FIELD.search(s)
    body = s[:m.start()] if m else s                                    # …/PV.CV → …/PV
    if "/" in body or "\\" in body:                                     # cesta: …/<tag>[/<blok>]/<parametr>
        parts = [x for x in re.split(r"[/\\]", body) if x]
        if len(parts) >= 2:
            role = _role_of(parts[-1])
            if role:
                path = parts[:-1]
                if len(path) > 1 and BLOCK.match(path[-1]):             # DeltaV: modul/PID1/PV.CV → modul
                    path = path[:-1]
                return path[-1], role, "deltav" if m else "pcs7"
    if "." in body:                                                     # TIC101.PV, TIC101.OUT, area.TIC101.SP
        tag, _, suf = body.rpartition(".")
        role = _role_of(suf)
        if role and tag:
            return tag, role, "dot"
    return None


def _group_key(tag):
    return str(tag).strip().lower()


def suggest(columns):
    """
    Návrh smyček z dvojic `(source_id, sloupec)`. Vrací (návrhy, nepoužité odkazy). Smyčky jsou v pořadí prvního
    výskytu tagu; role se vezme z prvního sloupce, další sloupce stejné role téže smyčky zůstanou nepoužité.
    """
    refs = [c if isinstance(c, SourceRef) else SourceRef(*c) for c in columns]
    groups, order, unused = {}, [], []
    for r in refs:
        p = parse_name(r.column)
        if p is None:
            unused.append(r)
            continue
        tag, role, via = p
        key = _group_key(tag)
        if key not in groups:
            groups[key] = Suggestion(tag=tag, via=via)
            order.append(key)
        sg = groups[key]
        if getattr(sg.roles, role) is None:
            setattr(sg.roles, role, r)
        else:
            unused.append(r)
    out = [groups[k] for k in order]
    if not out:                                                          # nic nepoznáno → heuristiky app.guess
        out = _guess_only(refs)
        unused = [r for r in refs if r not in {x for sg in out for x in sg.roles.refs()}]
    return out, unused


def _guess_only(refs):
    """Jedna smyčka podle `app.guess.guess_roles` (název + tvar průběhu se tu nezná, jen název)."""
    if not refs:
        return []
    by = {r.column: r for r in refs}
    g = guess.guess_roles(list(by))
    pv, mv = g.get("pv"), g.get("mv")
    if not pv or not mv or pv == mv:
        return []
    roles = Roles(pv=by[pv], mv=by[mv], sp=by.get(g.get("sp")), pos=by.get(g.get("pos")))
    return [Suggestion(tag=guess.loop_tag(pv).upper() or pv, roles=roles, via="guess")]


# ---- import mapování z CSV (sloupce: loop, role, source, column [, description])
ALIASES = {"loop": ("loop", "smyčka", "smycka", "tag"), "role": ("role",), "source": ("source", "zdroj"),
           "column": ("column", "sloupec", "signal", "signál"), "description": ("description", "popis")}
ROLE_ALIASES = {"pv": "pv", "sp": "sp", "setpoint": "sp", "mv": "mv", "op": "mv", "out": "mv", "pos": "pos",
                "position": "pos", "poloha": "pos", "dv": "dv", "disturbance": "dv", "porucha": "dv", "mode": "mode",
                "režim": "mode", "rezim": "mode"}


def _header(row):
    low = [str(c).strip().lower().lstrip("﻿") for c in row]
    idx = {}
    for key, names in ALIASES.items():
        for n in names:
            if n in low:
                idx[key] = low.index(n)
                break
    return idx


def parse_mapping_csv(raw, sources):
    """
    CSV s mapováním (hlavička: loop, role, source, column; volitelně description) → (smyčky, varování).
    `sources` = [(id, název, [sloupce])]; ve sloupci `source` smí být id i název, může chybět, když je zdroj jediný. Role:
    PV, SP, MV, pos, mode, DV (opakovatelná). Neznámý zdroj, sloupec nebo role se přeskočí s varováním.
    """
    text = decode_text(raw) if isinstance(raw, (bytes, bytearray)) else str(raw)
    text = text.lstrip("﻿")
    try:
        dia = csv.Sniffer().sniff("\n".join(text.splitlines()[:10]), delimiters=";,\t|")
    except csv.Error:
        dia = csv.excel
    rows = [r for r in csv.reader(io.StringIO(text), dia) if any(c.strip() for c in r)]
    if not rows:
        raise ValueError(T("err_mapping_csv"))
    h = _header(rows[0])
    if not {"loop", "role", "column"} <= set(h):
        raise ValueError(T("err_mapping_csv"))
    cols_of = {sid: set(cols) for sid, _name, cols in sources}
    by_name = {**{sid: sid for sid, _n, _c in sources}, **{name: sid for sid, name, _c in sources}}
    loops, warns, order = {}, [], []
    for n, row in enumerate(rows[1:], start=2):
        def cell(k, row=row):
            i = h.get(k)
            return row[i].strip() if i is not None and i < len(row) else ""
        tag, role, col, sid = cell("loop"), cell("role").lower(), cell("column"), cell("source")
        role = ROLE_ALIASES.get(role)
        if not tag or not col or role is None:
            warns.append(T("warn_mapping_row", n=n))
            continue
        if not sid and len(cols_of) == 1:
            sid = next(iter(cols_of))
        sid = by_name.get(sid)
        if sid is None:
            warns.append(T("warn_mapping_source", n=n, source=cell("source")))
            continue
        if col not in cols_of[sid]:
            warns.append(T("warn_mapping_column", n=n, column=col))
            continue
        if tag not in loops:
            loops[tag] = Suggestion(tag=tag, via="csv")
            order.append(tag)
        roles, ref = loops[tag].roles, SourceRef(sid, col)
        if role == "dv":
            roles.dv.append(ref)
        elif getattr(roles, role) is None:
            setattr(roles, role, ref)
        else:
            warns.append(T("warn_mapping_dup", n=n, role=role.upper()))
        if cell("description"):
            loops[tag].description = cell("description")
    return [loops[t] for t in order], warns
