"""
Jednotky a názvy parametrů profilu (docs/cs/regulatory.md § 4.7): čisté funkce převodu mezi zobrazenou hodnotou
(tak, jak ji zadává faceplate bloku) a kanonickou veličinou ideálního PID (K [-], Ti [s], Td [s], N [-]).

Každá veličina (`kind`) má varianty (`REPRS`): `to_canon(kind, rep, x, ctx)` a `from_canon(kind, rep, v, ctx)` jsou
si inverzní. Bez I složky je Ti = ∞ (inf); „opakování za minutu“ a Ki mají pro ni hodnotu 0 (a 0 znamená bez I).
Bez filtru D je N = ∞ (Tf = 0). `ctx` nese závislé veličiny: `K` (kanonické zesílení, pro Ki a Kd), `Td` (pro Tf),
`pv_range`, `mv_range` (pro zesílení v inženýrských jednotkách; rozsahy jsou (lo, hi)).
"""
import math

__all__ = ["REPRS", "from_canon", "to_canon"]

INF = math.inf
# varianty zobrazení po veličinách: varianta → jednotka (pro popisek v rozhraní)
REPRS = {
    "gain": {"K": "-", "PB": "%", "K_eng": "MV/PV"},
    "integral": {"s": "s", "min": "min", "ms": "ms", "rep_min": "1/min", "s_rep": "s", "Ki": "1/s", "Ki_min": "1/min"},
    "derivative": {"s": "s", "min": "min", "ms": "ms", "Kd": "s"},
    "filter": {"N": "-", "inv_N": "-", "Tf": "s", "alpha": "-"},
}
_TIME = {"s": 1.0, "min": 60.0, "ms": 1e-3}


def _pos(x):
    return x is not None and math.isfinite(x) and x > 0


def _span(rng):
    return float(rng[1]) - float(rng[0])


def _need(ctx, key, kind, rep):
    v = (ctx or {}).get(key)
    if v is None:
        raise ValueError(f"conversion {kind}/{rep} needs '{key}'")
    return v


def _check(kind, rep):
    if rep not in REPRS.get(kind, {}):
        raise ValueError(f"unknown variant '{rep}' of quantity '{kind}' (known: {', '.join(REPRS.get(kind, {}))})")


def to_canon(kind, rep, x, ctx=None):
    """Zobrazená hodnota → kanonická (K, Ti [s], Td [s], N)."""
    _check(kind, rep)
    if kind == "gain":
        if rep == "K":
            return x
        if rep == "PB":
            return INF if x == 0 else 100.0 / x
        return x * _span(_need(ctx, "pv_range", kind, rep)) / _span(_need(ctx, "mv_range", kind, rep))
    if kind == "integral":
        if rep in _TIME or rep == "s_rep":
            return x if x is None else x * _TIME.get(rep, 1.0)
        if rep == "rep_min":
            return INF if not x else 60.0 / x
        K = _need(ctx, "K", kind, rep)
        if not x:
            return INF
        return K / x if rep == "Ki" else 60.0 * K / x
    if kind == "derivative":
        if rep in _TIME:
            return x * _TIME[rep]
        return x / _need(ctx, "K", kind, rep)
    if rep == "N":
        return x
    if rep in ("inv_N", "alpha"):
        return INF if x == 0 else 1.0 / x
    return INF if x == 0 else _need(ctx, "Td", kind, rep) / x          # Tf = Td / N


def from_canon(kind, rep, v, ctx=None):
    """Kanonická hodnota → zobrazená (inverzní k `to_canon`)."""
    _check(kind, rep)
    if kind == "gain":
        if rep == "K":
            return v
        if rep == "PB":
            return 0.0 if not math.isfinite(v) else (INF if v == 0 else 100.0 / v)
        return v * _span(_need(ctx, "mv_range", kind, rep)) / _span(_need(ctx, "pv_range", kind, rep))
    if kind == "integral":
        if rep in _TIME or rep == "s_rep":
            return v / _TIME.get(rep, 1.0)
        if rep == "rep_min":
            return 60.0 / v if _pos(v) else 0.0
        K = _need(ctx, "K", kind, rep)
        if not _pos(v):
            return 0.0
        return K / v if rep == "Ki" else 60.0 * K / v
    if kind == "derivative":
        if rep in _TIME:
            return v / _TIME[rep]
        return v * _need(ctx, "K", kind, rep)
    if rep == "N":
        return v
    if rep in ("inv_N", "alpha"):
        return 0.0 if not math.isfinite(v) else (INF if v == 0 else 1.0 / v)
    return 0.0 if not math.isfinite(v) else (INF if v == 0 else _need(ctx, "Td", kind, rep) / v)
