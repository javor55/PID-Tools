"""
Export ladění: tabulka srovnání sad (CSV) a parametry v názvech a jednotkách bloku regulátoru pro řídicí systém
(PCS 7, TIA Portal, DeltaV). Registr `FORMATS`: id → popis (štítek `tun_ui_exp_<id>` v i18n, přípona, typ obsahu,
funkce). Funkce dostane `ctx` = {loop, model, profile {name, vendor, block, verified}, sets [1, 2], sel (číslo sady),
rows [{key, name, unit, values [Set 1, Set 2], sel}] (parametry bloku), metrics [{name, values}]} a vrátí text.
"""
import math

__all__ = ["FORMATS", "export"]


def _num(x, dec="."):
    if isinstance(x, bool):
        return "1" if x else "0"
    if isinstance(x, float):
        if not math.isfinite(x):
            return "inf" if x > 0 else "-inf"
        return f"{x:.6g}".replace(".", dec)
    return "" if x is None else str(x)


def _head(ctx, mark):
    p = ctx["profile"]
    s = f"{mark} {p['vendor']} {p['block']} ({p['name']}), model {ctx['model']}, set {ctx['sel']}"
    return s + ("" if p["verified"] else f"\n{mark} UNVERIFIED profile - check against the block manual")


def _csv(ctx):
    """Srovnání sad: parametr; jednotka; Set 1; Set 2 (+ robustnost) – středník a desetinná čárka (Excel)."""
    dec = ctx.get("dec", ",")
    out = ["parameter;unit;" + ";".join(f"set_{n}" for n in ctx["sets"])]
    out += [";".join([r["name"], r["unit"] or ""] + [_num(v, dec) for v in r["values"]]) for r in ctx["rows"]]
    out += [";".join([m["name"], ""] + [_num(v, dec) for v in m["values"]]) for m in ctx["metrics"]]
    return "\n".join(out) + "\n"


def _pcs7(ctx):
    """PCS 7: `NAME := hodnota;` s jednotkou v komentáři, parametry podle bloku profilu."""
    return _head(ctx, "//") + "\n" + "".join(f"{r['name']} := {_num(r['sel'])}; // {r['unit'] or '-'}\n" for r in ctx["rows"])


def _tia(ctx):
    """TIA Portal (SCL): přiřazení do instance bloku `#PID.<parametr> := hodnota;`."""
    return _head(ctx, "//") + "\n" + "".join(f"#PID.{r['name']} := {_num(r['sel'])}; // {r['unit'] or '-'}\n"
                                              for r in ctx["rows"])


def _deltav(ctx):
    """DeltaV: tabulka NAME<TAB>VALUE<TAB>UNIT pro ruční zadání / hromadný import."""
    return "\n".join(f"{r['name']}\t{_num(r['sel'])}\t{r['unit'] or ''}" for r in ctx["rows"]) + "\n"


FORMATS = {
    "csv": dict(ext="csv", mime="text/csv", fn=_csv),
    "pcs7": dict(ext="txt", mime="text/plain", fn=_pcs7),
    "tia": dict(ext="scl", mime="text/plain", fn=_tia),
    "deltav": dict(ext="tsv", mime="text/tab-separated-values", fn=_deltav),
}


def export(fmt, ctx):
    """Text exportu ve formátu `fmt` (KeyError = neznámý formát)."""
    return FORMATS[fmt]["fn"](ctx)
