"""Návrh ladění: pravidla (SIMC, iSIMC, Lambda, AMIGO, průměrovací) a optimalizace (MIGO, IAE/ISE/ITAE/překmit, scénář)."""
import numpy as np
from scipy.signal import lfilter

from .models import MODELS
from .robustness import loop_tf, is_stable, _freq_grid, hf_gain
from .simulation import pidconl_sim_full
from .util import padd as _padd

def _series_to_ideal(Kc, Ti, Td):
    if Td <= 0:
        return Kc, Ti, 0.0
    f = 1 + Td / Ti
    return Kc * f, Ti * f, Td / f


def integ_gain(code, p):
    """Rychlost náběhu PV na jednotku MV (u samoregulačních aproximace K/T1)."""
    if MODELS[code]["integ"]:
        return p[0]
    if code in ("P1D", "P2D"):
        return p[0] / p[1]
    return None


def default_tc(code, p, Ts_ctrl=0.0, method="SIMC", ctype="PI", diffgain=None):
    """
    Výchozí τc (λ) z efektivního zpoždění, se kterým pravidla počítají:
    PI u 2. řádu – pravidlo poloviny (θ + T2/2); PI u integračního + 1. řádu – setrvačnost jako zpoždění (θ + T1);
    PID, kde D kompenzuje T2 / T1 – přidá se zpoždění filtru D v PIDConL (TD/DiffGain), je-li DiffGain zadán.
    Bez toho vycházelo u procesů s velkou setrvačností vůči θ příliš agresivní ladění (Ms 2–6).
    """
    theta = p[-1] + Ts_ctrl / 2
    if code == "P2D":
        theta += p[2] / 2 if ctype == "PI" else (p[2] / diffgain if diffgain else 0.0)
    elif code == "I1D":
        theta += p[1] if ctype == "PI" else (p[1] / diffgain if diffgain else 0.0)
    T = p[1] if code in ("P1D", "P2D", "I1D") else 0.0
    if method == "Lambda":  # běžná průmyslová volba λ ≈ 3θ (klidná, robustní smyčka)
        return float(max(3 * theta, 0.05 * T, Ts_ctrl, 1e-3))
    return float(max(theta, 0.02 * T, Ts_ctrl, 1e-3))  # SIMC: τc = θ („těsná“ regulace)


def _amigo(code, p, ctype):
    """AMIGO (Åström & Hägglund 2004) – robustní ladění s cílem Ms ≈ 1,4. p už obsahuje θ + Ts/2."""
    th = max(p[-1], 1e-6)
    notes = [("note_amigo", {})]
    if MODELS[code]["integ"]:
        Kv = p[0]
        L = th + (p[1] if code == "I1D" else 0.0)  # zpoždění 1. řádu přičteno k θ
        if ctype == "PID":
            Kc, Ti, Td = 0.45 / (Kv * L), 8 * L, 0.5 * L
        else:
            Kc, Ti, Td = 0.35 / (Kv * L), 13.4 * L, 0.0
        notes.append(("note_amigo_b0", {}))
        return dict(Kc=Kc, Ti=Ti, Td=Td, notes=notes)
    K = p[0]
    if code == "P0D":
        T, L = 0.0, th
    elif code == "P1D":
        T, L = p[1], th
    else:
        T, L = p[1] + p[2] / 2, th + p[2] / 2
    tau = L / (L + T)
    if ctype == "PID" and T > 0:
        Kc = (0.2 + 0.45 * T / L) / K
        Ti = L * (0.4 * L + 0.8 * T) / (L + 0.1 * T)
        Td = 0.5 * L * T / (0.3 * L + T)
    else:
        if ctype == "PID":
            notes.append(("note_nod", {}))
        Kc = 0.15 / K + (0.35 - L * T / (L + T) ** 2) * T / (K * L)
        Ti = 0.35 * L + 13 * L * T ** 2 / (T ** 2 + 12 * L * T + 7 * L ** 2)
        Td = 0.0
    notes.append(("note_amigo_b0" if tau <= 0.5 else "note_amigo_b1", dict(tau=tau)))
    return dict(Kc=Kc, Ti=Ti, Td=Td, notes=notes)


def tune(code, p, method="SIMC", tc=None, ctype="PI", Ts_ctrl=0.0, avg=None):
    """
    Návrh PI/PID v ideálním tvaru (Gain, TI, TD) – shodném s PIDConL.
    Dopravní zpoždění se zvětšuje o Ts_ctrl/2 (vliv vzorkování regulátoru).
    method: "SIMC", "Lambda", "AVG" (průměrovací) (avg = (dPV_max %, dMV_max %)).
    """
    p = list(p)
    if abs(p[0]) < 1e-9:
        p[0] = 1e-9 if p[0] >= 0 else -1e-9
    p[-1] = p[-1] + Ts_ctrl / 2
    theta = p[-1]
    tc = tc if (tc and tc > 0) else max(theta, 1e-3)
    notes = []  # seznam (klíč textu, argumenty) – texty jsou v i18n.py

    if method == "AVG":
        kp = integ_gain(code, p)
        if kp is None:
            raise ValueError("err_avg_integ")
        dpv, dmv = avg
        Kc = abs(dmv) / abs(dpv) * np.sign(kp)
        Ti = 4.0 / (abs(kp) * abs(Kc))
        tc_eq = 1.0 / (abs(kp) * abs(Kc)) - theta
        notes.append(("note_avg", dict(tc=tc_eq)))
        if tc_eq < theta:
            notes.append(("note_avg_aggr", {}))
        if not MODELS[code]["integ"]:
            notes.append(("note_avg_selfreg", {}))
        return dict(Kc=Kc, Ti=Ti, Td=0.0, notes=notes)

    if method == "AMIGO":
        return _amigo(code, p, ctype)
    if method == "iSIMC" and code not in ("P1D", "P2D"):
        method = "SIMC"  # zlepšené pravidlo se týká jen samoregulačních procesů

    if method == "iSIMC" and code in ("P1D", "P2D"):
        K, T1 = p[0], p[1]
        th = theta
        if code == "P2D":
            if ctype == "PID":
                Kc_s, Ti_s = T1 / (K * (tc + theta)), min(T1, 4 * (tc + theta))
                Kc, Ti, Td = _series_to_ideal(Kc_s, Ti_s, p[2])
                return dict(Kc=Kc, Ti=Ti, Td=Td, notes=[("note_isimc_p2d", {}),
                                                        ("note_series", dict(kc=Kc_s, ti=Ti_s, td=p[2]))])
            T1, th = T1 + p[2] / 2, theta + p[2] / 2
            notes.append(("note_half", {}))
        if ctype == "PID" and code == "P1D":
            Kc_s, Ti_s, Td_s = T1 / (K * (tc + th)), min(T1, 4 * (tc + th)), th / 3
            Kc, Ti, Td = _series_to_ideal(Kc_s, Ti_s, Td_s)
            notes.append(("note_series", dict(kc=Kc_s, ti=Ti_s, td=Td_s)))
            return dict(Kc=Kc, Ti=Ti, Td=Td, notes=notes)
        Kc = (T1 + th / 3) / (K * (tc + th))
        Ti = min(T1 + th / 3, 4 * (tc + th))
        notes.append(("note_isimc", {}))
        return dict(Kc=Kc, Ti=Ti, Td=0.0, notes=notes)

    if code == "P0D":
        K = p[0]
        Ki = 1.0 / (K * (tc + theta))
        Kc = 0.25 / K
        return dict(Kc=Kc, Ti=Kc / Ki, Td=0.0, notes=[("note_p0d", {})])

    if code == "P1D":
        K, T1 = p[0], p[1]
        Kc = T1 / (K * (tc + theta))
        Ti = min(T1, 4 * (tc + theta)) if method == "SIMC" else T1
        if ctype == "PID":
            notes.append(("note_nod", {}))
        return dict(Kc=Kc, Ti=Ti, Td=0.0, notes=notes)

    if code == "P2D":
        K, T1, T2 = p[0], p[1], p[2]
        if ctype == "PI":
            T1e, th_e = T1 + T2 / 2, theta + T2 / 2
            Kc = T1e / (K * (tc + th_e))
            Ti = min(T1e, 4 * (tc + th_e)) if method == "SIMC" else T1e
            return dict(Kc=Kc, Ti=Ti, Td=0.0, notes=[("note_half", {})])
        Kc_s = T1 / (K * (tc + theta))
        Ti_s = min(T1, 4 * (tc + theta)) if method == "SIMC" else T1
        Kc, Ti, Td = _series_to_ideal(Kc_s, Ti_s, T2)
        return dict(Kc=Kc, Ti=Ti, Td=Td, notes=[("note_series", dict(kc=Kc_s, ti=Ti_s, td=T2))])

    if code in ("I0D", "I1D"):
        kp = p[0]
        T1 = p[1] if code == "I1D" else 0.0
        use_d = code == "I1D" and ctype == "PID"
        th = theta if use_d or code == "I0D" else theta + T1
        if method == "SIMC":
            Kc_s, Ti_s = 1.0 / (kp * (tc + th)), 4 * (tc + th)
        else:
            Kc_s, Ti_s = (2 * tc + th) / (kp * (tc + th) ** 2), 2 * tc + th
        if code == "I0D" and ctype == "PID":
            notes.append(("note_nod", {}))
        if use_d:
            Kc, Ti, Td = _series_to_ideal(Kc_s, Ti_s, T1)
            notes.append(("note_series", dict(kc=Kc_s, ti=Ti_s, td=T1)))
        else:
            Kc, Ti, Td = Kc_s, Ti_s, 0.0
            if code == "I1D":
                notes.append(("note_lag_to_delay", {}))
        return dict(Kc=Kc, Ti=Ti, Td=Td, notes=notes)
    raise ValueError(code)


def ff_gain(code, p, pd):
    """Statická dopředná vazba: ΔMV[%] = FF · Δporucha[j.]."""
    return -pd[0] / p[0]


def d_advice(code, p):
    """Doporučení D složky podle poměru dopravního zpoždění a časových konstant."""
    th = p[-1]
    if code == "P0D":
        return dict(key="d_p0d", tau=1.0, rec="PI")
    if code == "I0D":
        return dict(key="d_i0d", tau=None, rec="PI")
    if code == "I1D":
        return dict(key="d_i1d_yes" if p[1] > th else "d_i1d_no", tau=None, rec="PID" if p[1] > th else "PI",
                    ratio=p[1] / max(th, 1e-9))
    if code == "P2D" and p[2] > th:
        tau = (th + p[2] / 2) / (th + p[1] + p[2])
        return dict(key="d_p2d_yes", tau=tau, rec="PID", ratio=p[2] / max(th, 1e-9))
    T = p[1] + (p[2] / 2 if code == "P2D" else 0)
    L = th + (p[2] / 2 if code == "P2D" else 0)
    tau = L / (L + T)
    if tau < 0.1:
        return dict(key="d_lag", tau=tau, rec="PI")
    if tau < 0.6:
        return dict(key="d_balanced", tau=tau, rec="PID")
    return dict(key="d_delay", tau=tau, rec="PI")


def optimize_migo(code, p, ctype, Ts_ctrl, diffgain=5.0, Ms_max=1.6, hf_max=None, starts=(), extra_ps=(), pvf=0.0):
    """
    MIGO (Åström–Hägglund): maximalizace integračního zesílení Ki = Gain/TI – tedy minimalizace
    integrované chyby při poruše na vstupu – za podmínky Ms ≤ Ms_max, Mt ≤ Ms_max, stability a u PID TD ≤ TI/4.
    Pro PID volitelně omezení vysokofrekvenčního zesílení (šum do MV): hf_gain ≤ hf_max.
    extra_ps: další varianty modelu (nejistota) – podmínky Ms/Mt a stabilita musí platit pro všechny.
    """
    from scipy.optimize import minimize
    sgn = 1.0 if p[0] >= 0 else -1.0
    base = dict(DiffGain=diffgain, SampleTime=Ts_ctrl, PVFilt=pvf)
    w = _freq_grid(code, p, dict(base, TI=1.0), n=1500)
    pid = ctype == "PID"

    def unpack(x):
        Kc = sgn * np.exp(x[0])
        Ti = np.exp(x[1])
        Td = np.exp(x[2]) if pid else 0.0
        return Kc, Ti, Td

    def cost(x):
        Kc, Ti, Td = unpack(x)
        ctrl = dict(base, Gain=Kc, TI=Ti, TD=Td)
        Ms = Mt = 0.0
        for pp in [p] + list(extra_ps):
            L = loop_tf(code, pp, ctrl, w)
            if not is_stable(code, pp, ctrl, L=L):
                return 1e6
            Ms = max(Ms, np.max(np.abs(1 / (1 + L))))
            Mt = max(Mt, np.max(np.abs(L / (1 + L))))
        pen = 200 * max(0.0, Ms / Ms_max - 1) ** 2 + 200 * max(0.0, Mt / Ms_max - 1) ** 2
        if pid:  # realizovatelné, „rozumné“ PID: TD ≤ TI/4 (reálné nuly regulátoru)
            pen += 200 * max(0.0, 4 * Td / Ti - 1) ** 2
        if pid and hf_max:
            pen += 200 * max(0.0, hf_gain(Kc, Td, diffgain, Ts_ctrl) / hf_max - 1) ** 2
        return -np.log(abs(Kc) / Ti) + pen

    best = None
    for Kc0, Ti0, Td0 in starts:
        if not (np.isfinite(Kc0) and np.isfinite(Ti0) and Kc0 != 0 and Ti0 > 0):
            continue
        for scale in (1.0, 0.5):
            x0 = [np.log(abs(Kc0) * scale), np.log(Ti0)] + ([np.log(max(Td0, 0.05 * Ti0))] if pid else [])
            if cost(x0) >= 1e6:
                continue
            r = minimize(cost, x0, method="Nelder-Mead",
                         options=dict(maxiter=1500, xatol=1e-4, fatol=1e-6))
            if best is None or r.fun < best.fun:
                best = r
    if best is None or best.fun >= 1e6:
        raise ValueError("err_opt_failed")
    Kc, Ti, Td = unpack(best.x)
    notes = [("note_opt", dict(ms=Ms_max))] + ([("note_opt_robust", dict(n=len(extra_ps)))] if extra_ps else [])
    return dict(Kc=float(Kc), Ti=float(Ti), Td=float(Td), notes=notes)


def _proc_poly(code, p, h):
    """Diskrétní model procesu B(z⁻¹)/A(z⁻¹) – stejná diskretizace jako pidconl_sim (krok h)."""
    d = max(1, int(round(p[-1] / h)))
    zd = np.zeros(d + 1)
    zd[d] = 1.0
    if code == "P0D":
        return p[0] * zd, np.array([1.0])
    if code == "P1D":
        a = np.exp(-h / p[1])
        return np.convolve(zd, [0.0, p[0] * (1 - a)]), np.array([1.0, -a])
    if code == "P2D":
        a1, a2 = np.exp(-h / p[1]), np.exp(-h / p[2])
        return p[0] * np.convolve(zd, np.convolve([0.0, 1 - a1], [0.0, 1 - a2])), np.convolve([1.0, -a1], [1.0, -a2])
    if code == "I0D":
        return np.convolve(zd, [0.0, p[0] * h]), np.array([1.0, -1.0])
    a1 = np.exp(-h / p[1])
    return p[0] * h * np.convolve(zd, [0.0, 1 - a1]), np.convolve([1.0, -a1], [1.0, -1.0])


def _ctrl_poly(ctrl, h):
    """PIDConL (ideální tvar, D s filtrem, P/D ve zpětné vazbě) jako polynomy: u = Nr/Dc·r − Ny/Dc·y."""
    Kc, Ti, Td = ctrl["Gain"], ctrl["TI"], ctrl["TD"]
    N = ctrl.get("DiffGain", 5.0)
    Tf = Td / N if Td > 0 else 0.0
    cf = Tf / (Tf + h) if Td > 0 else 0.0
    Ki = Kc * h / Ti if (Ti and np.isfinite(Ti) and Ti > 0) else 0.0
    Kd = Kc * Td / (Tf + h) if Td > 0 else 0.0
    beta = 0.0 if ctrl.get("PropFbk") else 1.0
    gam = 0.0 if ctrl.get("DiffFbk") else 1.0
    d1 = np.convolve([1.0, -1.0], [1.0, -cf])
    d2 = np.convolve([1.0, -1.0], [1.0, -1.0])
    oc = np.array([1.0, -cf])
    Ny = _padd(_padd(Kc * d1, Ki * oc), Kd * d2)
    Nr = _padd(_padd(Kc * beta * d1, Ki * oc), Kd * gam * d2)
    return Nr, Ny, d1


def _loop_polys(code, p, ctrl, h):
    B, A = _proc_poly(code, p, h)
    Nr, Ny, Dc = _ctrl_poly(ctrl, h)
    Tpv = ctrl.get("PVFilt", 0.0) or 0.0
    if Tpv > 0:  # filtr PV: yf = (1−a)/(1 − a z⁻¹) · y
        a_ = np.exp(-h / Tpv)
        Bf, Af = np.array([1 - a_]), np.array([1.0, -a_])
    else:
        Bf, Af = np.array([1.0]), np.array([1.0])
    den = _padd(np.convolve(np.convolve(A, Dc), Af), np.convolve(np.convolve(B, Ny), Bf))
    return B, A, Nr, Ny, Dc, Bf, Af, den


def closed_loop_steps(code, p, ctrl, h, n, with_u=False):
    """Lineární odezvy uzavřené smyčky na jednotkový skok SP a poruchy na vstupu procesu (rychle, přes lfilter)."""
    B, A, Nr, Ny, Dc, Bf, Af, den = _loop_polys(code, p, ctrl, h)
    one = np.ones(n)
    y_sp = lfilter(np.convolve(np.convolve(B, Nr), Af), den, one)
    y_d = lfilter(np.convolve(np.convolve(B, Dc), Af), den, one)
    if not with_u:
        return 1.0 - y_sp, -y_d  # regulační odchylky
    u_sp = lfilter(np.convolve(np.convolve(A, Nr), Af), den, one)
    u_d = lfilter(-np.convolve(np.convolve(B, Ny), Bf), den, one)
    return 1.0 - y_sp, -y_d, u_sp, u_d


def _crit(e, h, crit, ovs_lim):
    t = np.arange(len(e)) * h
    if crit == "ISE":
        return float(np.sum(e ** 2) * h)
    if crit == "ITAE":
        return float(np.sum(t * np.abs(e)) * h)
    J = float(np.sum(np.abs(e)) * h)
    if crit == "OVS":
        k = int(np.argmax(np.abs(e)))
        pk = e[k]
        opp = float(np.max(-np.sign(pk) * e[k:])) if pk != 0 else 0.0
        ratio = max(opp, 0.0) / max(abs(pk), 1e-12)
        J *= 1.0 + 200.0 * max(0.0, ratio - ovs_lim) + 2000.0 * max(0.0, ratio - ovs_lim) ** 2
    return J


def overshoot_ratio(e):
    k = int(np.argmax(np.abs(e)))
    pk = e[k]
    return float(max(np.max(-np.sign(pk) * e[k:]), 0.0) / max(abs(pk), 1e-12)) if pk != 0 else 0.0


def optimize_time(code, p, ctype, Ts_ctrl, diffgain=5.0, crit="IAE", target="both", Ms_max=1.6, hf_max=None,
                  starts=(), extra_ps=(), ovs_lim=0.02, pfb=False, dfb=True, pvf=0.0, rate=0.0, sp_amp=1.0, d_amp=1.0):
    """
    Optimalizace parametrů podle časového kritéria odezvy (IAE, ISE, ITAE nebo IAE s limitem překmitu „OVS“)
    na skok SP, skok poruchy na vstupu procesu nebo obojí. Vždy s podmínkou robustnosti Ms (a Mt) ≤ Ms_max,
    stability, u PID TD ≤ TI/4 a volitelně limitu šumu MV. Odezvy se počítají na diskrétním modelu s regulátorem
    PIDConL (SampleTime, DiffGain, P/D ve zpětné vazbě); limity MV a deadband se ověřují až v simulaci.
    """
    from scipy.optimize import minimize
    sgn = 1.0 if p[0] >= 0 else -1.0
    pid = ctype == "PID"
    th = p[-1]
    Tsum = (p[1] if code in ("P1D", "P2D", "I1D") else 0.0) + (p[2] if code == "P2D" else 0.0)
    Ti_s = max([s[1] for s in starts if np.isfinite(s[1])] + [1.0])
    Th = max(40 * (th + Tsum + Ts_ctrl), 8 * Ti_s, 200 * Ts_ctrl)
    h = max(Ts_ctrl, Th / 8000)
    n = int(Th / h) + 1
    base = dict(DiffGain=diffgain, SampleTime=Ts_ctrl, PropFbk=pfb, DiffFbk=dfb, PVFilt=pvf)
    w = _freq_grid(code, p, dict(base, TI=1.0), n=1200)
    rate_state = {"du": 0.0}

    def unpack(x):
        return sgn * np.exp(x[0]), np.exp(x[1]), (np.exp(x[2]) if pid else 0.0)

    def responses(Kc, Ti, Td):
        if rate > 0:
            e_sp, e_d, u_sp, u_d = closed_loop_steps(code, p, dict(base, Gain=Kc, TI=Ti, TD=Td), h, n, True)
            rate_state["du"] = max(np.max(np.abs(np.diff(np.r_[0.0, u_sp]))) * abs(sp_amp) if target != "dist" else 0,
                                   np.max(np.abs(np.diff(np.r_[0.0, u_d]))) * abs(d_amp) if target != "sp" else 0) / h
        else:
            e_sp, e_d = closed_loop_steps(code, p, dict(base, Gain=Kc, TI=Ti, TD=Td), h, n)
        if not (np.all(np.isfinite(e_sp)) and np.all(np.isfinite(e_d))):
            return None
        tail = slice(int(0.9 * n), n)
        if np.max(np.abs(e_sp[tail])) > 0.05 or np.max(np.abs(e_d[tail])) > 0.05 * max(np.max(np.abs(e_d)), 1e-9):
            return None  # neustálí se (nestabilní nebo extrémně pomalé)
        return e_sp, e_d

    def raw_J(Kc, Ti, Td):
        r = responses(Kc, Ti, Td)
        if r is None:
            return None
        e_sp, e_d = r
        return _crit(e_sp, h, crit, ovs_lim), _crit(e_d, h, crit, ovs_lim)

    # normalizace podle výchozího bodu (aby SP a porucha vážily v „obojím“ stejně)
    J0 = None
    for s in starts:
        if s[0] != 0 and np.isfinite(s[0]) and s[1] > 0:
            J0 = raw_J(*s)
            if J0 is not None:
                break
    if J0 is None:
        raise ValueError("err_opt_failed")
    J0 = (max(J0[0], 1e-12), max(J0[1], 1e-12))

    def cost(x):
        Kc, Ti, Td = unpack(x)
        ctrl = dict(base, Gain=Kc, TI=Ti, TD=Td)
        Ms = Mt = 0.0
        for pp in [p] + list(extra_ps):
            L = loop_tf(code, pp, ctrl, w)
            if not is_stable(code, pp, ctrl, L=L):
                return 1e6
            Ms = max(Ms, np.max(np.abs(1 / (1 + L))))
            Mt = max(Mt, np.max(np.abs(L / (1 + L))))
        pen = 200 * max(0.0, Ms / Ms_max - 1) ** 2 + 200 * max(0.0, Mt / Ms_max - 1) ** 2
        if pid:
            pen += 200 * max(0.0, 4 * Td / Ti - 1) ** 2
            if hf_max:
                pen += 200 * max(0.0, hf_gain(Kc, Td, diffgain, Ts_ctrl) / hf_max - 1) ** 2
        J = raw_J(Kc, Ti, Td)
        if J is None:
            return 1e6
        if rate > 0:
            pen += 200 * max(0.0, rate_state["du"] / rate - 1) ** 2
        Js, Jd = J[0] / J0[0], J[1] / J0[1]
        val = Js if target == "sp" else Jd if target == "dist" else 0.5 * (Js + Jd)
        return np.log(max(val, 1e-12)) + pen

    best = None
    for Kc0, Ti0, Td0 in starts:
        if not (np.isfinite(Kc0) and np.isfinite(Ti0) and Kc0 != 0 and Ti0 > 0):
            continue
        x0 = [np.log(abs(Kc0)), np.log(Ti0)] + ([np.log(max(Td0, 0.05 * Ti0))] if pid else [])
        if cost(x0) >= 1e6:
            x0[0] -= np.log(2)
            if cost(x0) >= 1e6:
                continue
        r = minimize(cost, x0, method="Nelder-Mead", options=dict(maxiter=600, xatol=1e-3, fatol=1e-4))
        if best is None or r.fun < best.fun:
            best = r
    if best is None or best.fun >= 1e6:
        raise ValueError("err_opt_failed")
    Kc, Ti, Td = unpack(best.x)
    notes = [("note_topt", dict(ms=Ms_max))] + ([("note_opt_robust", dict(n=len(extra_ps)))] if extra_ps else [])
    if crit == "OVS":
        e_sp, e_d = closed_loop_steps(code, p, dict(base, Gain=Kc, TI=Ti, TD=Td), h, n)
        ratio = overshoot_ratio(e_sp if target != "dist" else e_d)
        if ratio > ovs_lim + 0.005:
            notes.append(("note_ovs_fail", dict(r=100 * ratio, lim=100 * ovs_lim)))
    return dict(Kc=float(Kc), Ti=float(Ti), Td=float(Td), notes=notes)


def optimize_scenario(code, p, pdl, ctype, ctrl_base, crit, h, sp, pv0, mv0, dmeas=(), dist_mv=None, dist_pv=None,
                      Ms_max=1.6, hf_max=None, starts=(), extra_ps=(), ovs_lim=0.02):
    """
    Optimalizace na celém scénáři simulace (skoky/rampy/sinus/pulzy SP a poruch) včetně nelineárních prvků
    smyčky (limity a rychlost MV, deadband, rampa SP, filtr PV, stikce, charakteristika ventilu).
    Kritérium se počítá z odchylky SP − PV; podmínky Ms (lineární model), TD ≤ TI/4, šum MV a limit rychlosti MV.
    """
    from scipy.optimize import minimize
    sgn = 1.0 if p[0] >= 0 else -1.0
    pid = ctype == "PID"
    base = {k: v for k, v in ctrl_base.items() if k not in ("Gain", "TI", "TD")}
    base["Noise"] = 0.0
    rate = base.get("MVRate", 0.0) or 0.0
    w = _freq_grid(code, p, dict(base, TI=1.0), n=1000)

    def unpack(x):
        return sgn * np.exp(x[0]), np.exp(x[1]), (np.exp(x[2]) if pid else 0.0)

    def J_of(Kc, Ti, Td):
        r = pidconl_sim_full(code, p, pdl, h, sp, pv0, mv0, dict(base, Gain=Kc, TI=Ti, TD=Td), dmeas, dist_mv, dist_pv)
        e = r["SPr"] - r["PV"]
        if not np.all(np.isfinite(e)) or np.abs(e).max() > 1e4:
            return None, None
        return _crit(e, h, crit, ovs_lim), r["dem"]

    J0 = None
    for s in starts:
        if s[0] != 0 and np.isfinite(s[0]) and s[1] > 0:
            J0 = J_of(*s)[0]
            if J0:
                break
    if not J0:
        raise ValueError("err_opt_failed")

    def cost(x):
        Kc, Ti, Td = unpack(x)
        ctrl = dict(base, Gain=Kc, TI=Ti, TD=Td)
        Ms = Mt = 0.0
        for pp in [p] + list(extra_ps):
            L = loop_tf(code, pp, ctrl, w)
            if not is_stable(code, pp, ctrl, L=L):
                return 1e6
            Ms = max(Ms, np.max(np.abs(1 / (1 + L))))
            Mt = max(Mt, np.max(np.abs(L / (1 + L))))
        pen = 200 * max(0.0, Ms / Ms_max - 1) ** 2 + 200 * max(0.0, Mt / Ms_max - 1) ** 2
        if pid:
            pen += 200 * max(0.0, 4 * Td / Ti - 1) ** 2
            if hf_max:
                pen += 200 * max(0.0, hf_gain(Kc, Td, base.get("DiffGain", 5.0), base["SampleTime"]) / hf_max - 1) ** 2
        J, dem = J_of(Kc, Ti, Td)
        if J is None:
            return 1e6
        if rate > 0:
            pen += 200 * max(0.0, dem / rate - 1) ** 2
        return np.log(max(J / J0, 1e-12)) + pen

    best = None
    for Kc0, Ti0, Td0 in starts:
        if not (np.isfinite(Kc0) and np.isfinite(Ti0) and Kc0 != 0 and Ti0 > 0):
            continue
        x0 = [np.log(abs(Kc0)), np.log(Ti0)] + ([np.log(max(Td0, 0.05 * Ti0))] if pid else [])
        if cost(x0) >= 1e6:
            continue
        r = minimize(cost, x0, method="Nelder-Mead", options=dict(maxiter=250, xatol=2e-3, fatol=1e-3))
        if best is None or r.fun < best.fun:
            best = r
    if best is None or best.fun >= 1e6:
        raise ValueError("err_opt_failed")
    Kc, Ti, Td = unpack(best.x)
    return dict(Kc=float(Kc), Ti=float(Ti), Td=float(Td), notes=[("note_scen", dict(ms=Ms_max))])


def outer_with_inner(code, p, tc_i, th_i):
    """
    Vnější model včetně dynamiky uzavřené vnitřní smyčky ≈ e^(-θi s)/(τci s + 1):
    přidá zpoždění θi a setrvačnost τci (menší z konstant převedena pravidlem polovin na zpoždění).
    Vrací (code, p) rozšířeného modelu.
    """
    th = p[-1] + th_i
    if code == "P0D":
        return "P1D", [p[0], tc_i, th]
    if code == "P1D":
        T1, T2 = max(p[1], tc_i), min(p[1], tc_i)
        return "P2D", [p[0], T1, T2, th]
    if code == "P2D":
        Ts_ = sorted([p[1], p[2], tc_i], reverse=True)
        return "P2D", [p[0], Ts_[0], Ts_[1] + Ts_[2] / 2, th + Ts_[2] / 2]
    if code == "I0D":
        return "I1D", [p[0], tc_i, th]
    T1, T2 = max(p[1], tc_i), min(p[1], tc_i)
    return "I1D", [p[0], T1, th + T2]


def settling_time(code, p, ctrl, tol=0.02):
    """
    Doba ustálení uzavřené smyčky [s] – delší z odezvy na skok SP a na skok poruchy na vstupu procesu
    (odchylka trvale pod tol · maximum odchylky). Lineární odezva bez limitů MV. None = nestabilní nebo neustálená.
    """
    h = float(ctrl.get("SampleTime", 1.0) or 1.0)
    lags = sum(p[1:-1]) if code in ("P1D", "P2D", "I1D") else 0.0
    ti = ctrl.get("TI") or 0.0
    t_guess = 20 * (p[-1] + lags) + 10 * (ti if np.isfinite(ti) else 0.0) + 50 * h
    for _ in range(4):
        n = int(min(max(t_guess / h, 200), 200000))
        try:
            e_sp, e_d = closed_loop_steps(code, list(p), ctrl, h, n)
        except Exception:
            return None
        out = []
        for e in (e_sp, e_d):
            if not np.all(np.isfinite(e)):
                return None
            pk = np.max(np.abs(e))
            if pk <= 0:
                out.append(0.0)
                continue
            big = np.nonzero(np.abs(e) > tol * pk)[0]
            out.append(float((big[-1] + 1) * h) if len(big) else 0.0)
        if max(out) < 0.8 * n * h:
            return max(out)
        t_guess *= 4
    return None
