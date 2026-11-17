#!/usr/bin/env python3
"""
Kontrola textů i18n (TICKET-016): `python3 tools/i18n_check.py`.

Vypíše
  * klíče chybějící v některém jazyce (en × cs a další soubory v pidtools/i18n),
  * nesoulad zástupných `{x}` mezi jazyky u téhož klíče,
  * nepoužité klíče.

Klíč je POUŽITÝ, když
  (a) se jeho přesný text v uvozovkách objeví ve zdrojích (Python, TS / TSX / JS, nástroje, předvolby; testy se
      nepočítají),
  (b) začíná prefixem skládaného klíče (`"model_" + code`, `` `dk_sc_${kind}` ``, `"q_%s"`, `f"q_{n}"` …); prefixy
      se hledají ve zdrojích regexem, nerozpoznané jsou ručně v `MANUAL_PREFIXES`,
  (c) má prefix legacy modulu (`LEGACY`): text čte modul jako `X.zbytek` / `X["zbytek"]`, proto se hledá zbytek
      klíče v souboru modulu,
  (d) je v `KEEP` (výjimka s odůvodněním).
Metadata (`_lang_name`, `_decimal`, vše na `_`) se nikdy nevyhodnocují jako nepoužitá.

Návratový kód 1 = chybějící klíče nebo nesoulad zástupných; nepoužité klíče samy kód neovlivní (hlídá je
tests/test_i18n_keys.py). Jen stdlib.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
I18N = ROOT / "pidtools" / "i18n"

# ------------------------------------------------------------------ zdroje (testy se nepočítají)
SOURCE_GLOBS = [
    ("pidtools", "*.py"), ("pidtools", "*.json"),
    ("frontend/src", "*.ts"), ("frontend/src", "*.tsx"), ("frontend/src", "*.js"),
    ("tools", "*.py"), ("desktop/src", "*.rs"),
]
SKIP_PARTS = {"node_modules", "__pycache__", "ui", "i18n"}        # pidtools/api/ui = sestavené UI; i18n = texty samy
SKIP_NAMES = {"openapi.json", "schema.d.ts", "i18n_check.py"}      # generované soubory; nástroj sám (jeho seznamy)

# ------------------------------------------------------------------ legacy moduly: prefix klíče → soubory, které z něj čtou X.zbytek
# Rozhraní předá modulu texty s prefixem a modul ho odřízne (RecordViewer.tsx / TrendsView.tsx: `vw_*` → `X.*`;
# DiagTab.tsx / ModelTab.tsx: seznam TXT → `T("mw_" + k)` → `X.*` v trend.js).
LEGACY = {
    "vw_": ["frontend/src/legacy/viewer.js", "frontend/src/legacy/viewer_an.js", "frontend/src/legacy/chart_tools.js",
            "frontend/src/legacy/table.js"],
    "mw_": ["frontend/src/legacy/trend.js", "frontend/src/legacy/chart_tools.js"],
}

# ------------------------------------------------------------------ ruční prefixy skládaných klíčů (co regex nepozná)
MANUAL_PREFIXES: dict[str, str] = {
    # pidtools/api/controllers.py: `_issue(e, "ctl_e")` → `T(f"{prefix}_{e.code}")`; kódy chyb a varování překladače
    # jsou v pidtools/controllers/*.py (všechny kódy ověřeny ručně)
    "ctl_e_": "chyby překladu programu regulátoru (kód z controllers/program.py)",
    "ctl_wn_": "varování překladu programu regulátoru",
}

# ------------------------------------------------------------------ výjimky: klíče použité způsobem, který nástroj nevidí
KEEP: dict[str, str] = {
    # frontend/src/components/Header.tsx: T(`${kind}_title`) / T(`${kind}_empty`), kind = "undo" | "redo" (složení bez prefixu)
    "undo_title": "tlačítko Zpět – složený klíč `${kind}_title`",
    "undo_empty": "tlačítko Zpět – složený klíč `${kind}_empty`",
    "redo_title": "tlačítko Znovu – složený klíč `${kind}_title`",
    "redo_empty": "tlačítko Znovu – složený klíč `${kind}_empty`",
}

# ------------------------------------------------------------------ regexy pro skládání klíčů
# Každý vzor dává (prefix, přípona); přípona může chybět. Skládaný klíč = prefix + cokoli + přípona.
_W = r"[A-Za-z0-9_]*"
COMPOSE = [
    re.compile(rf"""["'`]({_W})["'`]\s*\+(?!\s*["'`])"""),                         # "prefix_" + x   (+ "přípona" níže)
    re.compile(rf"""["'`]({_W})["'`]\s*\+[^+"'`\n]+\+\s*["'`]({_W})["'`]"""),     # "prefix_" + x + "_přípona"
    re.compile(rf"""["']({_W})%[sd]({_W})["']"""),                                  # "prefix_%s_přípona"
    re.compile(rf"""["']({_W})\{{[^}}"']*\}}({_W})["']\.format"""),                # "prefix_{{}}".format(x)
    re.compile(rf"""["']({_W})["']\s*%\s*[\w(]"""),                                # "prefix_" % x
]
# šablona / f-řetězec: `prefix_${x}_přípona` (přípona jen když za ní řetězec končí), jinak jen prefix
TEMPLATE = re.compile(rf"""`({_W})\$\{{[^}}]*\}}({_W})(.?)""")
FSTRING = re.compile(rf"""\bf(["'])({_W})\{{[^}}]*\}}({_W})(.?)""")
# složení uvnitř legacy modulu: X["ev_" + k] / X[`ev_${k}`] / L["set" + n]
LEGACY_COMPOSE = re.compile(rf"""\b(?:X|L)\[\s*(?:["']({_W})["']\s*\+|`({_W})\$\{{)""")
LITERAL = re.compile(r"""(["'`])([A-Za-z_][A-Za-z0-9_]*)\1""")
PLACEHOLDER = re.compile(r"\{(\w*)(?:[:!][^}]*)?\}")


def _files():
    out = []
    for base, pat in SOURCE_GLOBS:
        for p in sorted((ROOT / base).rglob(pat)):
            rel = p.relative_to(ROOT)
            if SKIP_PARTS & set(rel.parts[:-1]) or p.name in SKIP_NAMES or p.name.endswith(".d.ts"):
                continue
            out.append(p)
    return out


def load_langs():
    """{kód: {klíč: text}} ze všech souborů pidtools/i18n/*.json."""
    return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted(I18N.glob("*.json"))}


def missing_keys(langs):
    """{kód: [klíče, které jazyk nemá, ale některý jiný ano]} (jen neprázdné)."""
    allk = set().union(*[set(d) for d in langs.values()])
    return {c: sorted(allk - set(d)) for c, d in langs.items() if allk - set(d)}


def placeholder_mismatch(langs):
    """[(klíč, {kód: množina jmen v {…}})] pro klíče, kde se množiny mezi jazyky liší."""
    out = []
    for k in sorted(set().union(*[set(d) for d in langs.values()])):
        sets = {c: set(PLACEHOLDER.findall(d[k])) for c, d in langs.items() if k in d}
        if len({frozenset(s) for s in sets.values()}) > 1:
            out.append((k, sets))
    return out


LOOSE = set()                                                         # přípony složených klíčů bez prefixu


def _add(patterns, pre, suf):
    """Přidá vzor (prefix, přípona), jen pokud vypadá jako klíč: s příponou neprázdný prefix, bez přípony prefix
    končící „_“ nebo s „_“ uvnitř (jinak jsou to třídy CSS, názvy souborů apod.)."""
    if suf and not pre:
        LOOSE.add(suf)                                              # složení bez prefixu: jen informativní výpis
    if suf and pre and len(pre) + len(suf) >= 3 or (not suf and (pre.endswith("_") and len(pre) >= 2 or "_" in pre and len(pre) >= 3)):
        patterns.add((pre, suf))


def scan_sources():
    """(množina přesných literálů, množina složených vzorů (prefix, přípona))."""
    literals, patterns = set(), set()
    for p in _files():
        txt = p.read_text(encoding="utf-8", errors="replace")
        literals.update(m.group(2) for m in LITERAL.finditer(txt))
        for rx in COMPOSE:
            for m in rx.finditer(txt):
                g = m.groups()
                _add(patterns, g[0], g[1] if len(g) > 1 else "")
        for m in TEMPLATE.finditer(txt):
            _add(patterns, m.group(1), m.group(2) if m.group(3) == "`" else "")
        for m in FSTRING.finditer(txt):
            _add(patterns, m.group(2), m.group(3) if m.group(4) == m.group(1) else "")
    return literals, patterns


_cache = {}


def _read(rel):
    if rel not in _cache:
        _cache[rel] = (ROOT / rel).read_text(encoding="utf-8")
    return _cache[rel]


def _legacy_used(key):
    """None = klíč nemá prefix legacy modulu; jinak True / False podle výskytu zbytku v modulech."""
    for pre, files in LEGACY.items():
        if not key.startswith(pre):
            continue
        rest = key[len(pre):]
        rx = re.compile(rf"""\b(?:X|L|W\.txt|txt)\s*(?:\.\s*{re.escape(rest)}\b|\[\s*["']{re.escape(rest)}["']\s*\])""")
        for f in files:
            src = _read(f)
            if rx.search(src):
                return True
            for m in LEGACY_COMPOSE.finditer(src):                    # složený klíč uvnitř modulu
                if rest.startswith(m.group(1) or m.group(2) or "\0"):
                    return True
        return False
    return None


def _composed(key, patterns):
    return any(key.startswith(pre) and key.endswith(suf) and len(key) > len(pre) + len(suf)
               for pre, suf in patterns)


def unused_keys(langs=None):
    """Seřazený seznam klíčů, které nejsou použité (viz hlavička)."""
    langs = langs or load_langs()
    literals, patterns = scan_sources()
    patterns |= {(p, "") for p in MANUAL_PREFIXES}
    keys = set().union(*[set(d) for d in langs.values()])
    out = []
    for k in sorted(keys):
        if k.startswith("_") or k in KEEP or k in literals:
            continue
        leg = _legacy_used(k)
        if leg is None:
            leg = _composed(k, patterns)
        if not leg:
            out.append(k)
    return out


def main():
    langs = load_langs()
    miss = missing_keys(langs)
    mism = placeholder_mismatch(langs)
    unused = unused_keys(langs)
    total = {c: len(d) for c, d in langs.items()}
    print("Klíčů:", ", ".join(f"{c} {n}" for c, n in total.items()))
    print(f"Chybějící klíče: {sum(len(v) for v in miss.values())}")
    for c, ks in miss.items():
        print(f"  {c}: " + ", ".join(ks))
    print(f"Nesoulad zástupných: {len(mism)}")
    for k, s in mism:
        print(f"  {k}: " + "; ".join(f"{c}={sorted(v)}" for c, v in s.items()))
    print(f"Nepoužité klíče: {len(unused)}")
    for k in unused:
        print("  " + k)
    if LOOSE:
        print("Složení bez prefixu (nevyhodnocuje se, ověř ručně; klíče s takovou příponou řeší KEEP): "
              + ", ".join(sorted(LOOSE)))
    print(f"KEEP: {len(KEEP)} klíčů, ruční prefixy: {len(MANUAL_PREFIXES)}")
    return 1 if (miss or mism) else 0


if __name__ == "__main__":
    sys.exit(main())
