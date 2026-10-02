"""
APC – interakce více smyček (N×N): matice ustálených zesílení MV_j → PV_i z modelů projektu (diagonála = modely
smyček, mimo diagonálu = modely měřených poruch, kde je MV jiné smyčky zadané jako porucha), relativní zisková
matice RGA, Niederlinskiho index a doporučené párování.
"""
import numpy as np

from ...core.apc import best_pairing, niederlinski, rga
from .common import cross_model


def matrix(recs):
    """Matice K [%PV_i / %MV_j] a maska známých prvků (vazba je v modelech)."""
    n = len(recs)
    K = np.zeros((n, n))
    known = np.zeros((n, n), bool)
    for i, a in enumerate(recs):
        for j, b in enumerate(recs):
            if i == j:
                K[i, j], known[i, j] = a["model"][1][0], True
            else:
                x = cross_model(a, b)
                if x is not None:
                    K[i, j], known[i, j] = x[0], True
    return K, known


def analyse(recs):
    """dict(names, K, known, L (RGA), NI, pairing (MV pro PV_i), diag_ok, advice [klíče])."""
    K, known = matrix(recs)
    L = rga(K)
    NI = niederlinski(K) if len(recs) > 1 else float("nan")
    perm, _ = best_pairing(K) if len(recs) <= 7 else (None, None)
    advice = []
    if not known[~np.eye(len(recs), dtype=bool)].any():
        advice.append("rgan_no_cross")
    dl = np.diag(L) if np.all(np.isfinite(L)) else np.full(len(recs), np.nan)
    if np.any(dl < 0):
        advice.append("rgan_neg")
    elif np.any(np.abs(dl - 1) > 0.5):
        advice.append("rgan_strong")
    else:
        advice.append("rgan_weak")
    if np.isfinite(NI) and NI < 0:
        advice.append("rgan_ni_neg")
    if perm is not None and perm != list(range(len(recs))):
        advice.append("rgan_repair")
    return dict(names=[r["name"] for r in recs], mvs=[r["c_mv"] for r in recs], K=K, known=known, L=L, NI=NI,
                pairing=perm, advice=advice)
