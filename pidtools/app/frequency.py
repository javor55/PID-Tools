"""
Frekvenční analýza smyčky (web i desktop): Bodeho diagram otevřené smyčky L = C·G, Nyquistův diagram s kružnicí
Ms, citlivostní funkce S = 1/(1+L), T = L/(1+L) a přenos z šumu PV do MV (C·S). Vše z core.loop_tf, tedy včetně
filtru D (DiffGain), filtru PV a zpoždění poloviny periody vzorkování.
"""
import numpy as np

from ..core import robustness
from ..core.robustness import loop_tf

MS_TARGET = 1.6        # kružnice v Nyquistově diagramu (doporučené Ms 1,4–1,8)


def grid(code, p, samp, n=500):
    """Kmitočty [rad/s] od 0,01 / charakteristický čas po Nyquistův kmitočet regulátoru."""
    tchar = p[-1] + (p[1] if code in ("P1D", "P2D", "I1D") else 0) + (p[2] if code == "P2D" else 0) + samp + 1e-6
    return np.logspace(np.log10(0.01 / tchar), np.log10(np.pi / max(samp, 1e-6)), n)


def _plain(ctrl):
    return {k: v for k, v in ctrl.items() if k not in ("FF", "FF_LL")}


def response(code, p, ctrl, w=None):
    """
    Frekvenční charakteristiky jedné sady: dict(w, L, S, T, CS, mag_db, phase_deg, Ms, GM, PM, wc, w180, stable).
    wc = kmitočet řezu |L| = 1 (fázová bezpečnost), w180 = kmitočet fáze −180° (amplitudová bezpečnost).
    """
    c = _plain(ctrl)
    w = grid(code, p, c["SampleTime"]) if w is None else w
    L = loop_tf(code, list(p), c, w)
    S = 1 / (1 + L)
    T = L / (1 + L)
    G1 = loop_tf(code, list(p), dict(c, Gain=1.0, TI=np.inf, TD=0.0), w)    # proces (s PV filtrem a zpožděním)
    C = np.divide(L, G1, out=np.zeros_like(L), where=np.abs(G1) > 0)
    th = p[-1] + c["SampleTime"] / 2           # zpoždění odečíst analyticky (unwrap na řídké mřížce by selhal)
    ph = np.unwrap(np.angle(L * np.exp(1j * w * th)))
    if ph[0] > 0.5 * np.pi:
        ph -= 2 * np.pi
    ph = ph - w * th
    mag = np.abs(L)
    i = np.where((mag[:-1] >= 1) & (mag[1:] < 1))[0]
    j = np.where((ph[:-1] > -np.pi) & (ph[1:] <= -np.pi))[0]
    rb = robustness(code, list(p), c)
    return dict(w=w, L=L, S=S, T=T, CS=C * S, mag_db=20 * np.log10(np.maximum(mag, 1e-12)),
                phase_deg=np.degrees(ph), Ms=rb["Ms"], GM=rb["GM"], PM=rb["PM"], stable=rb["stable"],
                wc=float(w[i[-1]]) if len(i) else None, w180=float(w[j[0]]) if len(j) else None)


def compare(code, p, ctrls):
    """Charakteristiky více sad na společné mřížce: {název: response}."""
    samp = min(_plain(c)["SampleTime"] for c in ctrls.values())
    w = grid(code, p, samp)
    return {k: response(code, p, c, w) for k, c in ctrls.items()}


def ms_circle(ms=MS_TARGET, n=200):
    """Kružnice v Nyquistově diagramu: střed −1, poloměr 1/Ms (křivka L mimo ni ⇔ Ms menší)."""
    a = np.linspace(0, 2 * np.pi, n)
    return -1 + np.cos(a) / ms, np.sin(a) / ms


def phase_floor(res, lo=-720.0):
    """Spodní mez osy fáze: do −720° (dál už jen zpoždění), ať je vidět oblast kolem −180°."""
    m = min(float(np.min(r["phase_deg"])) for r in res.values())
    return max(m, lo) - 20


def db(x):
    return 20 * np.log10(np.maximum(np.abs(x), 1e-12))


def bandwidth(r):
    """Šířka pásma uzavřené smyčky [rad/s]: kde |T| poprvé klesne pod −3 dB (None, když ne)."""
    t = db(r["T"])
    k = np.where(t < -3)[0]
    return float(r["w"][k[0]]) if len(k) else None
