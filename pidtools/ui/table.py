"""
Tabulka aplikace – jeden vzhled pro všechny záložky (podle návrhu): záhlaví tučně, řádky oddělené jemnou čarou,
čísla vpravo písmem s pevnou šířkou v zápisu jazyka (cs: desetinná čárka, mezera mezi tisíci, znaménko −),
zvýrazněné buňky (Styler pandas, např. nejlepší hodnota) a volitelný výběr řádku klepnutím.

Náhrada st.dataframe: `table(df, key, select=True)` vrací objekt s `.selection.rows` jako st.dataframe
s on_select="rerun", takže místa volání zůstávají stejná. Vykreslené tabulky běhu jsou v session_state["_tables"]
(seznam (klíč, DataFrame)) – pro testy (AppTest vlastní komponenty nečte).
"""
import math
import re
from numbers import Number
from types import SimpleNamespace

import numpy as np
import pandas as pd
import streamlit as st

from .widgets import static_asset, v2_component

ss = st.session_state

_CSS = """
.pidt-wrap {overflow: auto; width: 100%; --tx: #1f2933; --mut: #52606d; --ln: #d7dde5; --soft: #e5e9ef;
    --sel: #eef4fb; --hov: #f6f8fa; font: inherit;}
.pidt-wrap.dark {--tx: #e2e8f0; --mut: #94a3b8; --ln: #334155; --soft: #1e293b; --sel: rgba(96,165,250,0.14);
    --hov: rgba(148,163,184,0.08);}
.pidt {width: 100%; border-collapse: collapse; font-size: 13px; color: var(--tx); font-family: inherit;}
.pidt th {font-weight: 600; text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--ln); white-space: nowrap;
    position: sticky; top: 0; background: inherit;}
.pidt td {padding: 5px 8px; border-bottom: 1px solid var(--soft); vertical-align: top;}
.pidt tr:last-child td {border-bottom: 0;}
.pidt .n {text-align: right; font-family: 'IBM Plex Mono', ui-monospace, monospace; font-size: 12px; white-space: nowrap;}
.pidt th.n {font-family: inherit; font-size: 13px;}
.pidt tr.click td {cursor: pointer;}
.pidt tr.click:hover td {background: var(--hov);}
.pidt tr.sel td {background: var(--sel);}
.pidt td.best {background: rgba(34,197,94,0.14);}
.pidt td.muted {color: var(--mut);}
"""

_NUMLIKE = re.compile(r"^[−\-+]?\d")


def reset():
    """Na začátku běhu: seznam vykreslených tabulek (pro testy)."""
    ss["_tables"] = []


def num_text(v, lang=None):
    """Číslo do tabulky v zápisu jazyka; None / NaN jako „—“."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "—"
    if isinstance(v, (bool, np.bool_)):
        return "✓" if v else ""
    if not isinstance(v, Number):
        return str(v)
    x = float(v)
    if not math.isfinite(x):
        return "∞" if x > 0 else "−∞"
    if abs(x) >= 1e6 and abs(x) < 1e15:
        x = round(x)                                    # velká čísla celá s mezerami, ne 1,64e+06
    if float(x).is_integer() and abs(x) < 1e15:
        s = f"{int(x):,}"
    else:
        s = f"{x:.6g}"
        if "e" not in s and abs(x) >= 1000:
            i, _, f = s.partition(".")
            s = f"{int(i):,}" + ("." + f if f else "")
    return _loc(s, lang)


def _loc(s, lang=None):
    """Desetinná tečka / oddělovač tisíců / minus podle jazyka (cs: „1 234,5“, „−2“)."""
    lang = lang or ss.get("lang", "cs")
    if lang == "cs":
        s = s.replace(",", " ").replace(".", ",")
    s = re.sub(r"(^|[\s(])-(?=\d)", r"\1−", s)
    return s


def _is_num_col(s):
    vals = [v for v in s if v is not None and not (isinstance(v, float) and math.isnan(v)) and v != ""]
    if not vals:
        return False
    return all((isinstance(v, Number) and not isinstance(v, (bool, np.bool_))) or
               (isinstance(v, str) and (_NUMLIKE.match(v) or v in ("—", "–", "∞"))) for v in vals)


def table(data, key=None, *, where=None, select=False, hide_index=None, height=None, row_class=None,
          cell_class=None, helps=None, **_ignored):
    """
    Vykreslí tabulku. data: DataFrame nebo Styler (styly buněk se převezmou). select=True → klepnutím se vybere
    řádek (zůstane vybraný jako u st.dataframe). hide_index: None = index jen když nese popisky (ne 0, 1, 2 …).
    row_class / cell_class: CSS třídy řádků / buněk („best“, „muted“ …); where: kontejner (jinak aktuální).
    Vrací objekt s .selection.rows.
    """
    if where is not None:
        with where:
            return table(data, key, select=select, hide_index=hide_index, height=height, row_class=row_class,
                         cell_class=cell_class, helps=helps)
    sty = None
    if hasattr(data, "data") and hasattr(data, "_compute"):          # pandas Styler
        styler, df = data, data.data
        try:
            styler._compute()
            sty = [["; ".join(f"{p}: {v}" for p, v in styler.ctx.get((i, j), [])) for j in range(df.shape[1])]
                   for i in range(df.shape[0])]
        except Exception:
            sty = None
    else:
        df = data if isinstance(data, pd.DataFrame) else pd.DataFrame(data)
    ss.setdefault("_tables", []).append((key, df))
    from .charts import visible
    if not visible():                       # neaktivní záložka / skrytý pohled – nic neposílat
        return SimpleNamespace(selection=SimpleNamespace(rows=[]))
    show_idx = (not isinstance(df.index, pd.RangeIndex)) if hide_index is None else not hide_index
    lang = ss.get("lang", "cs")
    cols, rows = [], [[] for _ in range(len(df))]
    if show_idx:
        cols.append(dict(name=str(df.index.name or ""), num=False))
        for i, v in enumerate(df.index):
            rows[i].append(str(v))
        if sty:
            sty = [[""] + r for r in sty]
    for c in df.columns:
        s = df[c]
        is_num = _is_num_col(list(s))
        cols.append(dict(name=str(c), num=is_num, help=(helps or {}).get(c)))
        for i, v in enumerate(s):
            if isinstance(v, str) and is_num:
                try:
                    v = float(v)                  # „1.64e+06“, „290.8“ → číslo v zápisu jazyka
                except ValueError:
                    pass
            txt = num_text(v, lang) if not isinstance(v, str) else (_loc(v, lang) if is_num else v)
            rows[i].append(txt)
    ccls = None
    if cell_class is not None:
        ccls = [([""] if show_idx else []) + list(r) for r in cell_class]
    out = dict(cols=cols, rows=rows, sty=sty, ccls=ccls, rcls=row_class, select=bool(select), height=height,
               dark=_dark())
    sel = None
    if select:
        prev = ss.get(key)
        sel = getattr(prev, "sel", None) if prev is not None else None
        if not isinstance(sel, int) or not 0 <= sel < len(df):
            sel = None
        out["sel"] = sel
    comp = v2_component("pidtools_table", css=_CSS, js=static_asset("table.js"))
    res = comp(key=key, data=out, on_sel_change=(lambda: None) if select else None)
    if select:
        v = getattr(res, "sel", None)
        sel = v if isinstance(v, int) and 0 <= v < len(df) else sel
    return SimpleNamespace(selection=SimpleNamespace(rows=[sel] if sel is not None else []))


def _dark():
    try:
        return (st.context.theme.type or "light") == "dark"
    except Exception:
        return False
