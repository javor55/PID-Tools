"""
Úseky dat pro identifikaci: kvalita úseku (core.data_quality s podílem opakovaných hodnot z historianu),
automaticky nalezené úseky se skoky MV / SP a jejich hodnocení. Vše v % rozsahů, časy v s od začátku záznamu.
"""
import numpy as np

from ..core import data_quality, find_segments


def rep_frac(t_all, pv_raw, T0, a, b):
    """Podíl opakovaných (nezměněných) hodnot PV v surových datech úseku – stopa komprese historianu."""
    m = (t_all >= a + T0) & (t_all <= b + T0) & np.isfinite(pv_raw)
    v = pv_raw[m]
    return float(np.mean(np.diff(v) == 0)) if len(v) > 20 else None


def quality(t, pv, mv, sp, Ts, has_sp, mv_lo, mv_hi, a, b, rep=None, model=None):
    """Kvalita úseku (a, b) pro identifikaci; model = (kód, parametry) zpřesní požadavek na ustálení."""
    m = (t >= a) & (t <= b)
    if m.sum() < 20:
        return dict(level=2, checks=[("q_short", 2, {})], snr=0.0, sigma=0.0, n_steps=0)
    return data_quality(t[m], pv[m], mv[m], sp[m] if has_sp else np.zeros(m.sum()), Ts, has_sp, mv_lo, mv_hi, rep,
                        model)


def settle_time(model):
    """Doba ustálení podle modelu (zpoždění + 4× časové konstanty), None bez modelu."""
    if not model:
        return None
    code, p = model[0], model[1]
    return p[-1] + 4 * ((p[1] if code in ("P1D", "P2D", "I1D") else 0) + (p[2] if code == "P2D" else 0))


def auto(t, mv, sp, Ts, has_sp, model=None, gap=None, pv=None):
    """Automaticky nalezené úseky (shluky skoků MV / SP): [{start, end, n_mv, n_sp, up, down}]; pv = délka úseku
    bez modelu podle odezvy PV."""
    return find_segments(t, mv, sp if has_sp else np.zeros_like(mv), Ts, has_sp, max_gap=gap or None,
                         settle=settle_time(model), pv=pv)


def format_args(ar):
    """Čísla v hláškách kvality: celá nad 100, jinak 3 platné číslice."""
    return {k: ((f"{v:.0f}" if abs(v) >= 100 else f"{v:.3g}") if isinstance(v, float) else v) for k, v in ar.items()}
