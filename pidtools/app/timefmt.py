"""Čas pro lidi: doby v s / min / h podle velikosti a jednotka časové osy grafů podle délky záznamu."""
import numpy as np

UNITS = {"s": 1.0, "min": 60.0, "h": 3600.0}


def dur(sec):
    """Doba čitelně: 45 s, 12,5 min, 2 h 05 min; nekonečno / NaN → „–“."""
    if sec is None or not np.isfinite(sec):
        return "–"
    sec = float(sec)
    a = abs(sec)
    if a < 120:
        return f"{sec:.3g} s"
    if a < 2 * 3600:
        return f"{sec / 60:.3g} min"
    h, m = divmod(int(round(a / 60)), 60)
    return f"{'-' if sec < 0 else ''}{h} h {m:02d} min"


def auto_unit(span):
    """Jednotka časové osy podle délky [s]: do 20 min s, do 20 h min, jinak h."""
    span = float(span or 0.0)
    return "s" if span <= 1200 else ("min" if span <= 72000 else "h")


def unit_for(choice, span):
    """Zvolená jednotka (s / min / h) nebo automaticky podle délky (choice „auto“ nebo None)."""
    return choice if choice in UNITS else auto_unit(span)
