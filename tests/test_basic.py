import numpy as np

# Importing functions to test from the parent directory
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from pidtools.core import n_free, simulate, stiction_valve

def test_n_free():
    assert n_free("P0D") == 1  # K, θ -> 2 params - 1 = 1
    assert n_free("P1D") == 2  # K, T1, θ -> 3 params - 1 = 2
    assert n_free("I0D") == 1  # Ki, θ -> 2 params - 1 = 1

def test_stiction_valve_no_stiction():
    u = np.array([0, 10, 20, 10, 0])
    v = stiction_valve(u, S=0)
    np.testing.assert_array_equal(v, u)

def test_stiction_valve_with_stiction():
    u = np.array([0, 5, 10, 15, 12, 10, 5, 0])
    # S=2, J=2 (default)
    # u=0 -> x=0, v=0
    # u=5 -> d=5 > 2 -> x=5 - sign(5)*(2-2)=5, v=5
    # For simplicity, testing a basic known behavior where it sticks until delta > S
    v = stiction_valve(u, S=2.0)
    assert v[0] == 0
    # The simple stick-slip model:
    # If |u - x| > S, x = u - sign(u - x) * (S - J). With J=S, x = u
    # Wait, the code says:
    # J = S if J is None else min(max(J, 0.0), S)
    # x = u - np.sign(d) * (S - J) => if J=S, x = u
    assert v[1] == 5
    assert v[2] == 10
    
    # testing small movement
    u2 = np.array([10, 11, 11.5, 12.1])
    v2 = stiction_valve(u2, S=2.0)
    assert v2[0] == 10
    assert v2[1] == 10 # 11 - 10 = 1 < 2, sticks
    assert v2[2] == 10 # 11.5 - 10 = 1.5 < 2, sticks
    assert v2[3] == 12.1 # 12.1 - 10 = 2.1 > 2, moves to 12.1 (since J=S)

def test_simulate_P0D():
    h = 1.0
    t = np.arange(10) * h
    du = np.ones(10)
    # P0D: params = [K, θ]
    p = [2.0, 0.0] 
    y = simulate("P0D", p, t, du, h)
    np.testing.assert_array_almost_equal(y, 2.0 * du)

def test_simulate_I0D():
    h = 1.0
    t = np.arange(10) * h
    du = np.ones(10)
    # I0D: params = [Ki, θ]
    p = [0.5, 0.0]
    y = simulate("I0D", p, t, du, h)
    # Integral of 1 over time with Ki=0.5 -> y = 0.5 * t (since np.cumsum(ones) * h)
    # wait, cumsum([1, 1, ...]) = [1, 2, 3, ...]
    # So y[0] = 0.5, y[1] = 1.0 ...
    expected = 0.5 * np.cumsum(du) * h
    np.testing.assert_array_almost_equal(y, expected)
