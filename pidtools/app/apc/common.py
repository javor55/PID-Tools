"""APC – společné výpočty: charakteristický čas, mřížka simulace, převody a vzájemné vazby smyček."""
import numpy as np


def tchar(model):
    """Charakteristický čas procesu: dopravní zpoždění + součet časových konstant."""
    code, p = model[0], model[1]
    return p[-1] + (p[1] if code in ("P1D", "P2D", "I1D") else 0.0) + (p[2] if code == "P2D" else 0.0)


MAX_STEPS = 12000


def grid(t_end, samp):
    """
    Mřížka simulace struktury: krok ≤ SampleTime (nejvýš ~6000 kroků, jemněji než SampleTime nemá smysl).
    U velmi pomalých procesů (horizont ≫ SampleTime) se krok prodlouží, aby simulace měla nejvýš MAX_STEPS kroků –
    jinak by výpočet trval desítky sekund (regulátor pak počítá s krokem simulace, dynamika je proti němu pomalá).
    """
    h = float(min(samp, max(t_end / 6000, samp / 10)))
    if t_end / h > MAX_STEPS:
        h = float(t_end / MAX_STEPS)
    n = int(t_end / h) + 1
    return h, n, np.arange(n) * h


def eng(rng):
    """Převod % rozsahu → inženýrské jednotky pro rozsah (lo, hi)."""
    lo, hi = rng
    return lambda x: lo + np.asarray(x, float) * (hi - lo) / 100


def clean(ctrl):
    """Sada parametrů bez dopředné vazby (FF, FF_LL)."""
    return {k: v for k, v in ctrl.items() if k not in ("FF", "FF_LL")}


def cross_model(x, y):
    """Model vlivu MV smyčky y na PV smyčky x [%PV_x / %MV_y] – z modelu měřené poruchy (sloupec MV_y)."""
    if y["c_mv"] in x["c_d"]:
        j = x["c_d"].index(y["c_mv"])
        if j < len(x["model"][2]):
            pd_ = list(x["model"][2][j])
            pd_[0] *= (y["mv_rng"][1] - y["mv_rng"][0]) / 100   # Kd je v %PV na jednotku MV_y
            return pd_
    return None
