"""
Odhad role sloupců (PV, MV, SP, poloha ventilu) podle názvů tagů z různých systémů.

Název se rozdělí na části (LIC101.PV → „lic101“, „pv“). Shoda s poslední částí (přípona tagu) váží nejvíc,
shoda s jinou částí méně. MV a SP dostanou bonus, pokud mají stejný tag smyčky jako vybraná PV
(FIC100.PV + FIC100.OP, ne LIC200.OP). Když název nic neřekne, rozhodnou průběhy: SP je schodovitá
(málo různých hodnot), MV je skoková a omezená, PV je spojitá.
"""
import re

import numpy as np

# klíčová slova rolí (malými písmeny, bez diakritiky i s ní); pořadí nehraje roli
ROLE_WORDS = {
    "pv": {"pv", "cv", "x", "xm", "xact", "meas", "measured", "measurement", "process", "procval", "actual", "act",
           "ist", "istwert", "value", "merena", "měřená", "mereni", "měření", "skut", "skutecna", "skutečná", "in"},
    "mv": {"mv", "op", "out", "output", "y", "lmn", "man", "co", "cmd", "command", "u", "ctrl", "control",
           "manip", "manipulated", "valve", "ventil", "akcni", "akční", "stellgr", "stellgroesse", "yout"},
    "sp": {"sp", "sv", "w", "wsp", "spt", "setpoint", "set", "setp", "target", "soll", "sollwert", "zadana",
           "žádaná", "pozad", "požad", "pozadovana", "požadovaná", "ref", "reference"},
    "pos": {"pos", "zpos", "position", "fb", "fbk", "feedback", "rbk", "readback", "poloha", "zpetne", "zpětné",
            "posfb", "valvepos", "ypos", "stroke"},
}


def tokens(name):
    """Části názvu: „LIC101.PV_Out“ → ["lic101", "pv", "out"]; také rozdělí „LIC101PV“ za číslicí."""
    s = re.sub(r"(?<=\d)(?=[a-zA-Z])", " ", str(name))
    return [t for t in re.split(r"[^0-9a-zA-Zá-žÁ-Ž]+", s.lower()) if t]


def loop_tag(name):
    """Tag smyčky = název bez poslední části (LIC101.PV → lic101); u jednoslovných názvů prázdný."""
    t = tokens(name)
    return " ".join(t[:-1]) if len(t) > 1 else ""


def name_score(name, role):
    """Skóre shody názvu s rolí: přípona 3, jiná část 2, část začínající klíčovým slovem (≥ 4 znaky) 1."""
    words = ROLE_WORDS[role]
    t = tokens(name)
    if not t:
        return 0.0
    if t[-1] in words:
        return 3.0
    if any(x in words for x in t):
        return 2.0
    if any(x.startswith(w) for x in t for w in words if len(w) >= 4):
        return 1.0
    return 0.0


def _shape(v):
    """Charakter průběhu: (podíl různých hodnot, podíl kroků beze změny)."""
    v = np.asarray(v, float)
    v = v[np.isfinite(v)]
    if len(v) < 10:
        return 1.0, 0.0
    return len(np.unique(v)) / len(v), float(np.mean(np.diff(v) == 0))


def guess_roles(sigs, get=None):
    """
    Doporučené sloupce → {"pv": …, "mv": …, "sp": … nebo None, "pos": … nebo None}.
    get(sloupec) → hodnoty; volitelné, slouží jen k rozhodnutí, když názvy nic neřeknou.
    """
    sigs = list(sigs)
    if not sigs:
        return {"pv": None, "mv": None, "sp": None, "pos": None}
    shapes = {}

    def shape(c):
        if get is None:
            return 1.0, 0.0
        if c not in shapes:
            try:
                shapes[c] = _shape(get(c))
            except Exception:
                shapes[c] = (1.0, 0.0)
        return shapes[c]

    def pick(role, taken, tag=None, data_score=None):
        best, best_s = None, 0.0
        for c in sigs:
            if c in taken:
                continue
            s = name_score(c, role)
            if s and tag and loop_tag(c) == tag:
                s += 1.5
            if s > best_s:
                best, best_s = c, s
        if best is None and data_score is not None:  # názvy nepomohly → podle průběhu
            cands = [c for c in sigs if c not in taken]
            if cands:
                best = max(cands, key=data_score)
        return best

    pv = pick("pv", set())
    tag = loop_tag(pv) if pv else None
    mv = pick("mv", {pv}, tag)
    sp = pick("sp", {pv, mv}, tag)
    pos = pick("pos", {pv, mv, sp}, tag)
    # bez nápovědy v názvech: PV = nejspojitější, MV = nejvíc „schodovitá“ ze zbylých
    if pv is None:
        pv = max([c for c in sigs if c not in (mv, sp)] or sigs, key=lambda c: shape(c)[0])
    if mv is None:
        rest = [c for c in sigs if c not in (pv, sp)]
        mv = max(rest, key=lambda c: shape(c)[1]) if rest else pv
    if sp is None and get is not None:  # SP jen s jasně schodovitým průběhem (málo různých hodnot)
        rest = [c for c in sigs if c not in (pv, mv, pos)]
        cand = min(rest, key=lambda c: shape(c)[0]) if rest else None
        if cand is not None and shape(cand)[0] < 0.01 and shape(cand)[1] > 0.95:
            sp = cand
    return {"pv": pv, "mv": mv, "sp": sp, "pos": pos}
