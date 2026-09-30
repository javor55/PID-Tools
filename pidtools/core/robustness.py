"""Kmitočtová analýza smyčky: stabilita, robustnost (Ms, GM, PM) a šum MV."""
import numpy as np

from .models import MODELS

def loop_tf(code, p, ctrl, w):
    s = 1j * w
    if code == "P0D":
        G = p[0] * np.ones_like(s)
    elif code == "P1D":
        G = p[0] / (p[1] * s + 1)
    elif code == "P2D":
        G = p[0] / ((p[1] * s + 1) * (p[2] * s + 1))
    elif code == "I0D":
        G = p[0] / s
    else:
        G = p[0] / (s * (p[1] * s + 1))
    G = G * np.exp(-s * (p[-1] + ctrl["SampleTime"] / 2))
    if ctrl.get("PVFilt", 0) and ctrl["PVFilt"] > 0:
        G = G / (ctrl["PVFilt"] * s + 1)
    Kc, Ti, Td = ctrl["Gain"], ctrl["TI"], ctrl["TD"]
    C = np.ones_like(s)
    if Ti and np.isfinite(Ti) and Ti > 0:
        C = C + 1 / (Ti * s)
    if Td > 0:
        C = C + Td * s / (1 + Td * s / max(ctrl.get("DiffGain", 5.0), 1e-6))
    return Kc * C * G


def _n_integrators(code, ctrl):
    Ti = ctrl.get("TI")
    return (1 if MODELS[code]["integ"] else 0) + (1 if Ti and np.isfinite(Ti) and Ti > 0 else 0)


def _freq_grid(code, p, ctrl, n=4000):
    Tchar = p[-1] + (p[1] if code in ("P1D", "P2D", "I1D") else 0) + ctrl["SampleTime"] + 1e-6
    w_hi = np.pi / max(ctrl["SampleTime"], 1e-6)
    return np.logspace(np.log10(1e-5 / Tchar), np.log10(w_hi), n)


def is_stable(code, p, ctrl, w=None, L=None):
    """
    Nyquistovo kritérium pro otevřenou smyčku bez nestabilních pólů (integrátory v počátku jsou povoleny):
    stabilní ⇔ změna úhlu (1 + L(jω)) pro ω: 0+ → ∞ je n·π/2 (n = počet integrátorů) a |L| na konci < 1.
    """
    if L is None:
        w = _freq_grid(code, p, ctrl) if w is None else w
        L = loop_tf(code, p, ctrl, w)
    if not np.all(np.isfinite(L)) or np.abs(L[-1]) >= 1:
        return False
    d = np.unwrap(np.angle(1 + L))
    return bool(abs((d[-1] - d[0]) - _n_integrators(code, ctrl) * np.pi / 2) < np.pi / 2)


def robustness(code, p, ctrl):
    """Ms (max. citlivost), Mt, amplitudová bezpečnost GM, fázová bezpečnost PM [°], stabilita."""
    w = _freq_grid(code, p, ctrl)
    L = loop_tf(code, p, ctrl, w)
    mag, ph = np.abs(L), np.unwrap(np.angle(L))
    if ph[0] > 0.5 * np.pi:
        ph -= 2 * np.pi
    Ms = float(np.max(np.abs(1 / (1 + L))))
    Mt = float(np.max(np.abs(L / (1 + L))))
    PM = GM = float("nan")
    i = np.where((mag[:-1] >= 1) & (mag[1:] < 1))[0]
    if len(i):
        i = i[-1]
        f = (mag[i] - 1) / (mag[i] - mag[i + 1])
        PM = float(np.degrees(np.pi + ph[i] + f * (ph[i + 1] - ph[i])))
    j = np.where((ph[:-1] > -np.pi) & (ph[1:] <= -np.pi))[0]
    if len(j):
        j = j[0]
        f = (ph[j] + np.pi) / (ph[j] - ph[j + 1])
        GM = float(1 / (mag[j] + f * (mag[j + 1] - mag[j])))
    return dict(Ms=Ms, Mt=Mt, GM=GM, PM=PM, stable=is_stable(code, p, ctrl, L=L))


def hf_gain(Kc, Td, N, Ts):
    """Vysokofrekvenční zesílení diskrétního PID (P + D s filtrem TD/N, vzorkování Ts)."""
    return abs(Kc) * (1 + (Td / (Td / max(N, 1e-6) + Ts) if Td > 0 else 0.0))


def mv_noise(ctrl, sigma_pv):
    """Přibližná směrodatná odchylka šumu MV [%] z bílého šumu PV [%]."""
    return hf_gain(ctrl["Gain"], ctrl.get("TD", 0.0), ctrl.get("DiffGain", 5.0), ctrl.get("SampleTime", 1.0)) * sigma_pv
