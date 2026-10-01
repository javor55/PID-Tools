"""Změna normovacích rozsahů: model v reálných jednotkách zůstává, mění se jen jeho vyjádření v %."""
import numpy as np
import pytest

from pidtools.core import fit_model, norm_factors, predict, rescale_fit


def _data():
    h, n = 1.0, 1500
    t = np.arange(n) * h
    mv = np.where((t > 100) & (t < 700), 40.0, 30.0) + np.where(t > 1000, 8.0, 0.0)      # MV [%]
    q = np.where(t > 400, 5.0, 0.0)                                                      # měřená porucha [m3/h]
    y = np.zeros(n)
    for k in range(1, n):                         # PV [°C] = 45 + 0,3 °C/% · MV(t−8) + 0,5 °C/(m3/h) · q, T = 40 s
        u = mv[max(k - 9, 0)] - 30.0
        y[k] = y[k - 1] + h / 40.0 * (0.3 * u + 0.5 * q[k - 1] - y[k - 1])
    return t, h, 45.0 + y, mv, q


def _pct(x, lo, hi):
    return (x - lo) / (hi - lo) * 100


def test_rescaled_model_is_the_same_in_real_units():
    t, h, pv, mv, q = _data()
    A, B = (0.0, 100.0, 0.0, 100.0), (0.0, 300.0, 0.0, 100.0)
    rA = fit_model("P1D", t, _pct(pv, *A[:2]), _pct(mv, *A[2:]), h, [q])
    rB = rescale_fit(rA, A, B)
    assert rB["p"][0] == pytest.approx(rA["p"][0] / 3) and rB["p"][1:] == pytest.approx(rA["p"][1:])
    assert rB["pdl"][0][0] == pytest.approx(rA["pdl"][0][0] / 3)
    yA, _ = predict("P1D", rA["p"], rA["pdl"], t, _pct(pv, *A[:2]), _pct(mv, *A[2:]), [q], h)
    yB, _ = predict("P1D", rB["p"], rB["pdl"], t, _pct(pv, *B[:2]), _pct(mv, *B[2:]), [q], h)
    eA = A[0] + yA * (A[1] - A[0]) / 100
    eB = B[0] + yB * (B[1] - B[0]) / 100
    assert np.max(np.abs(eA - eB)) < 1e-6                       # stejná predikce v °C
    # a odpovídá fitu provedenému rovnou při novém rozsahu
    rB2 = fit_model("P1D", t, _pct(pv, *B[:2]), _pct(mv, *B[2:]), h, [q])
    assert rB2["p"][0] == pytest.approx(rB["p"][0], rel=1e-3) and rB2["p"][-1] == pytest.approx(rB["p"][-1], abs=0.5)


def test_factors():
    fK, fKd, fS = norm_factors((0, 100, 0, 100), (20, 70, 0, 50))   # PV rozsah 100 → 50, MV 100 → 50
    assert fK == pytest.approx(1.0) and fKd == pytest.approx(2.0) and fS == pytest.approx(2.0)
