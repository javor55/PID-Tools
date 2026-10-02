"""Pomocné numerické funkce sdílené jádrem."""
import numpy as np
from scipy.signal import lfilter

__all__ = ["lag", "acf", "padd", "propfac"]


def propfac(ctrl):
    """PropFacSP z konfigurace regulátoru: váha SP v P složce 0–1 (1 = P z odchylky, 0 = P jen z PV).
    Starší klíč PropFbk (P ve zpětné vazbě ano/ne) odpovídá PropFacSP 0 / 1."""
    b = ctrl.get("PropFacSP")
    if b is None:
        return 0.0 if ctrl.get("PropFbk") else 1.0
    return float(min(max(b, 0.0), 1.0))


def lag(x, T, h):
    a = np.exp(-h / max(T, 1e-9))
    return lfilter([1 - a], [1, -a], x)


def acf(x):
    x = np.asarray(x, float) - np.mean(x)
    n = len(x)
    f = np.fft.rfft(x, 2 * n)
    a = np.fft.irfft(f * np.conj(f))[:n]
    return a / a[0] if a[0] > 0 else a


def padd(a, b):
    n = max(len(a), len(b))
    return np.pad(np.asarray(a, float), (0, n - len(a))) + np.pad(np.asarray(b, float), (0, n - len(b)))
