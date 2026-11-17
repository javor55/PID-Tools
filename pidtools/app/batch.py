"""
Hromadné akce nad smyčkami projektu (FEATURE-007): identifikace, návrh ladění a převzetí návrhů do Setu 2, plus
hromadný export sad pro řídicí systém.

Model běhu (viz app.jobs): úloha běží v jiném procesu nad odlehčenými kopiemi smyček (`Workspace.lean`). Z procesu
úlohy se nic nezapisuje do prostoru; po každé zpracované smyčce proces pošle částečný výsledek (`partial`) a hlavní
proces ho zapíše do smyčky (`on_partial` v API). Zrušení úlohy tak zachová už hotové smyčky.

Návrhy ladění se drží v nastavení smyčky pod klíčem `batch_sug|<kód modelu>` = [Kc, Ti, Td, metoda] (prefix je v
app.project.STATE_PREFIX, typ a meze hlídá `project.sug_ok`). Klíč nese kód modelu, takže návrh pro jiný model, než
je zrovna vybraný, se nepoužije; uloží se do projektu a přežije jeho uložení. Set 2 se mění jen akcí „accept“.
"""
from . import project as prj
from . import segments as sg
from . import tuning as tun
from . import tuning_export as tex

ACTIONS = ("identify", "tune", "accept")
STAGES = ("no_data", "data", "model", "proposal", "set2")


# ---- návrhy a stav smyčky
def sug_keys(ls):
    """Klíče nastavení smyčky s návrhem hromadného ladění (pro libovolný model)."""
    return [k for k in ls.settings if str(k).startswith(prj.SUG_PREFIX)]


def proposal(ls):
    """Návrh [Kc, Ti, Td, metoda] pro právě vybraný model smyčky, jinak None (bez návrhu, nebo pro jiný model)."""
    code = ls.get("mcode")
    v = ls.settings.get(prj.SUG_PREFIX + code) if code and ls.model is not None else None
    return v if prj.sug_ok(v) else None


def stage(ls):
    """Stav smyčky v přehledu: no_data | data | model | proposal (čeká na převzetí) | set2 (Set 2 zadán)."""
    if not ls.has_data or not ls.c_pv or not ls.c_mv:
        return "no_data"
    if proposal(ls) is not None:
        return "proposal"
    if ls.get("set2_defined"):
        return "set2"
    return "model" if ls.model is not None else "data"


# ---- plán: které smyčky se zpracují a které se přeskočí (kontroly běží v hlavním procesu, mají k datům přístup)
def _precheck(ls, action, params):
    """Důvod přeskočení (klíč i18n, argumenty), nebo None = smyčku lze zpracovat."""
    if action == "accept":
        return None if proposal(ls) is not None else ("batch_skip_no_proposal", {})
    if not ls.has_data:
        return "batch_skip_no_data", {}
    if not ls.c_mv:
        return "batch_skip_no_mv", {}
    if action == "identify":
        q = ls.quality()                      # úsek identifikace; ≥ 2 = z úseku nejde model určit
        bad = [c for c in (q or {}).get("checks", []) if c[1] >= 2]
        if q and q["level"] >= 2 and bad:
            return bad[0][0], sg.format_args(bad[0][2])
        return None
    if ls.model is None:                      # tune
        return "batch_skip_no_model", {}
    method = params.get("method") or ls.get(f"method|{ls.get('mcode')}", tun.DEFAULT_METHOD)
    if method not in ls.methods():
        return "batch_skip_method", dict(method=method, model=ls.get("mcode"))
    return None


def plan(proj, loops, action, params):
    """Položky úlohy: [{loop, name, skip: (klíč, args) | None, ws: odlehčená kopie smyčky | None}] v daném pořadí."""
    names = proj.names()
    out = []
    for i in loops:
        ls = proj.loops[i]
        skip = _precheck(ls, action, params)
        out.append(dict(loop=i, name=str(names[i]), skip=skip, ws=None if skip else ls.lean()))
    return out


# ---- zpracování jedné smyčky (v procesu úlohy; vrací (stav, důvod, změna k zapsání do smyčky))
def _identify(ws, runner, prog):
    steps = len(ws.get("chosen")) * (2 if ws.id_closed and not ws.inputs_mode else 1)
    before = ws.fit
    out = runner(ws, "identify", steps=steps, progress=prog)
    if ws.fit is before:                      # nový výsledek nevznikl: žádný model se nepodařilo identifikovat
        errs = out["result"] or [("—", "no model")]
        return "error", ("batch_error", dict(text="; ".join(f"{c}: {t}" for c, t in errs))), None
    return "ok", None, dict(out=out)


def _tune(ws, params):
    ov = {k: params[p] for k, p in (("ctype", "ctype"), ("opt_crit", "crit"), ("opt_target", "target")) if params.get(p)}
    ws.set(**ov)                              # jen v kopii: nastavení smyčky se tím nemění
    method = params.get("method") or ws.get(f"method|{ws.get('mcode')}", tun.DEFAULT_METHOD)
    s = ws.suggest(method, params.get("tc"))
    val = [float(s["Kc"]), float(s["Ti"]), float(s["Td"]), method]
    if not prj.sug_ok(val):
        return "error", ("batch_bad_proposal", dict(method=method, kc=val[0], ti=val[1])), None
    return "ok", None, dict(drop=sug_keys(ws), set={prj.SUG_PREFIX + ws.get("mcode"): val})


def _accept(ws):
    v = proposal(ws)
    ws.write_set(2, dict(Kc=v[0], Ti=v[1], Td=v[2]), dict(method=v[3]))
    keys = ("set2_gain", "set2_ti", "set2_td", "set2_defined", "tune_hist")
    return "ok", None, dict(drop=sug_keys(ws), set={k: ws.settings[k] for k in keys})


def run(items, action, params, runner, progress=None, partial=None):
    """
    Úloha (app.jobs): smyčky postupně. `runner` = api.tasks.run (metoda prostoru + stav k přenosu). Po každé smyčce
    `partial({loop, name, status, reason, delta})`; návratová hodnota = seznam řádků výsledku bez `delta`.
    Chyba jedné smyčky (ValueError, RuntimeError …) ji označí jako error s textem a úloha pokračuje dalšími.
    """
    n = len(items)
    rows = []
    for i, it in enumerate(items):
        label = f"{i + 1} / {n} · {it['name']}"
        if progress:
            progress(i / n, label)
        delta = None
        if it["skip"] is not None:
            status, reason = "skipped", it["skip"]
        else:
            ws = it["ws"]
            try:
                if action == "identify":
                    status, reason, delta = _identify(ws, runner, lambda f, t="", i=i, label=label:
                                                      progress((i + f) / n, label) if progress else None)
                elif action == "tune":
                    status, reason, delta = _tune(ws, params)
                else:
                    status, reason, delta = _accept(ws)
            except Exception as ex:           # noqa: BLE001 – chyba jedné smyčky se hlásí v řádku výsledku
                status, reason, delta = "error", ("batch_error", dict(text=f"{type(ex).__name__}: {ex}")), None
        row = dict(loop=it["loop"], name=it["name"], status=status,
                   reason=None if reason is None else dict(key=reason[0], args=reason[1]))
        if partial:
            partial(dict(row, delta=delta))
        rows.append(row)
    if progress and items:
        progress(1.0, f"{n} / {n} · {items[-1]['name']}")
    return rows


def apply_delta(ls, delta):
    """Změna nastavení smyčky z úlohy (návrh ladění, převzetí do Setu 2) → smyčka; volá hlavní proces."""
    for k in delta.get("drop", []):
        ls.settings.pop(k, None)
    ls.set(**delta.get("set", {}))


# ---- hromadný export
def export(proj, loops, fmt, n, dec="."):
    """
    Jeden soubor se sadou `n` všech vybraných smyček s modelem; formát řádků je tentýž jako export jedné sady
    (`tuning_export.FORMATS`). Vrací (text, přeskočené smyčky). Spojení podle formátu:
      csv     jedna hlavička a řádky všech smyček s prvním sloupcem `loop`;
      deltav  řádky `loop<TAB>NAME<TAB>VALUE<TAB>UNIT`;
      pcs7 / tia  bloky smyček za sebou, každý za komentářem `// ===== loop <název> =====` a s vlastní hlavičkou.
    """
    names = proj.names()
    parts, skipped = [], []
    for i in loops:
        ls = proj.loops[i]
        if not ls.has_data or ls.model is None:
            skipped.append(i)
            continue
        ctx = ls.export_ctx(n)
        ctx["dec"] = dec
        ctx["loop"] = str(names[i])
        parts.append((str(names[i]), tex.export(fmt, ctx)))
    if fmt == "csv":
        lines = []
        for k, (nm, txt) in enumerate(parts):
            rows = txt.splitlines()
            if k == 0:
                lines.append("loop;" + rows[0])
            lines += [f"{nm};{r}" for r in rows[1:]]
        text = "\n".join(lines) + "\n" if lines else ""
    elif fmt == "deltav":
        text = "".join(f"{nm}\t{r}\n" for nm, txt in parts for r in txt.splitlines())
    else:
        text = "".join(f"// ===== loop {nm} =====\n{txt}" + ("" if txt.endswith("\n") else "\n") + "\n" for nm, txt in parts)
    return text, skipped
