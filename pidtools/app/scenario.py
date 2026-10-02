"""
Scénář simulace v záložce Ladění: tabulka událostí → průběhy SP a poruch, délka simulace, výpočetní mřížka,
proces a ventil v simulaci, ukazatele odezvy.

Řádek události: [zapnuto, cíl, typ, amplituda, začátek, konec, perioda, τ]
  cíl:  "SP" (žádaná hodnota, jednotky PV), "IN" (porucha na vstupu procesu, jednotky MV),
        "PV" (porucha na výstupu, jednotky PV), "M<j>" (j-tá měřená porucha, její jednotky)
  typ:  step, ramp, sine, pulse, rpulse (náhodné pulzy), noise
Časy v sekundách, None = nevyplněno.
"""
import numpy as np

from .. import core
from ..core.util import lag

TARGETS_BASE = ("SP", "IN", "PV")
TYPES = ("step", "ramp", "sine", "pulse", "rpulse", "noise")


def targets(n_dist):
    """Kódy cílů událostí pro n měřených poruch."""
    return list(TARGETS_BASE) + [f"M{j}" for j in range(n_dist)]


def row(target, typ, amp, start, end=None, period=None, tau=None, on=True):
    return [bool(on), target, typ, amp, start, end, period, tau]


def default_rows(sp_amp, mv_range, n_dist, T_end):
    """Výchozí scénář: skok SP (5 %), skok poruchy na vstupu (40 %) a skoky měřených poruch (70 %, 75 % …)."""
    rows = [row("SP", "step", round(sp_amp, 6), round(0.05 * T_end)),
            row("IN", "step", round(0.05 * mv_range, 4), round(0.4 * T_end))]
    rows += [row(f"M{j}", "step", 1.0, round((0.7 + 0.05 * j) * T_end)) for j in range(n_dist)]
    return rows


def quick_rows(kind, sp_amp, mv_range, T_end, pv_noise=0.0):
    """Rychlé scénáře: "sp" skok SP, "sp_dist" skok SP + porucha na vstupu, "noise" skok SP + šum PV."""
    rows = [row("SP", "step", round(sp_amp, 6), round(0.05 * T_end))]
    if kind == "sp_dist":
        rows.append(row("IN", "step", round(0.05 * mv_range, 4), round(0.4 * T_end)))
    elif kind == "noise":
        rows.append(row("PV", "noise", round(pv_noise, 4), 0.0))
    return rows


def rescale_times(rows, f):
    """Časy událostí (začátek, konec) × f – při změně délky simulace zůstanou události na stejném místě."""
    out = [list(r) for r in rows]
    for r in out:
        for i in (4, 5):
            if r[i] is not None:
                r[i] = round(float(r[i]) * f, 6)
    return out


def set_sp_step(rows, amp):
    """Amplituda prvního skoku SP = amp. Vrací (řádky, zda byl skok nalezen)."""
    out = [list(r) for r in rows]
    for r in out:
        if r[1] == "SP" and r[2] == "step":
            r[3] = round(amp, 6)
            return out, True
    return out, False


def nice(x):
    """Zaokrouhlení nahoru na „hezké“ číslo (1, 1,5, 2, 3, 5, 7,5 × 10^n)."""
    if not np.isfinite(x) or x <= 0:
        return x
    e = 10 ** np.floor(np.log10(x))
    return float(next(m * e for m in (1, 1.5, 2, 3, 5, 7.5, 10) if m * e >= x * 0.999))


def t_char(code, p, tc=0.0, samp=0.0):
    """Charakteristický čas smyčky: dopravní zpoždění + časová konstanta + τc + perioda vzorkování."""
    return p[-1] + (p[1] if code in ("P1D", "P2D", "I1D") else 0) + (tc or 0) + samp


def auto_length(code, p, ctrls, T_char, samp, ts_id, settling=core.settling_time):
    """
    Délka simulace podle dynamiky: 4× nejdelší doba ustálení uzavřené smyčky (zadané sady; skok SP i porucha),
    aby se mezi událostmi (5 %, 40 %, 70 % délky) smyčka vždy ustálila. Když se žádná sada neustálí (nestabilní),
    podle modelu procesu (20× charakteristický čas), nejméně délka úseku identifikace. Vrací (délka [s], zdroj).
    Sady nesmí záviset na scénáři (optimalizace na scénáři), jinak by se délka a výsledek navzájem posouvaly.
    """
    st_ = [settling(code, tuple(p), {k: v for k, v in c.items() if k not in ("FF", "FF_LL")})
           for c in ctrls if c is not None]
    st_ = [x for x in st_ if x]
    if st_:
        return nice(max(4 * max(st_), 50 * samp)), "cl"
    t_data = float(ts_id[-1]) if ts_id is not None and len(ts_id) else 0.0
    t_mod = max(20 * T_char, 50 * samp)
    if t_data > 0:      # nevěrohodně pomalý model (časová konstanta ≫ záznam) nesmí dát simulaci na dny
        t_mod = min(t_mod, 20 * t_data)
    return nice(max(t_mod, t_data)), ("data" if t_data >= t_mod else "model")


def grid(samp, T_end):
    """Výpočetní mřížka: krok h (dělení SampleTime, nejvýš ~20 000 kroků regulátoru) a časy."""
    m_sub = max(1, min(10, int(20000 * samp / T_end)))
    h = samp / m_sub
    n = int(T_end / h) + 1
    return h, np.arange(n) * h


def signals(rows, ts, h, T_end, pv_range, mv_range, pv0, n_dist):
    """
    Průběhy scénáře z událostí. SP a poruchy PV/IN v % rozsahů, měřené poruchy v jejich jednotkách
    (odchylky od počátku). Vrací dict(sp, dmv, dpv, dmeas, sp_amp, d_amp) – amplitudy v % (0 = žádná událost).
    """
    n = len(ts)
    sp = np.full(n, pv0)
    dmv, dpv = np.zeros(n), np.zeros(n)
    dmeas = [np.zeros(n) for _ in range(n_dist)]
    sp_amp = d_amp = 0.0
    for ri, r in enumerate(rows):
        on, tgc, tyc, amp, t0_, t1_, per, tau = (list(r) + [None] * 8)[:8]
        if not on or amp is None or tgc is None or tyc is None:
            continue
        if tgc[0] == "M" and int(tgc[1:]) >= n_dist:
            continue
        amp = float(amp)
        t0_ = float(t0_) if t0_ is not None else 0.0
        t1_ = float(t1_) if t1_ is not None and float(t1_) > t0_ else np.inf
        per = float(per) if per is not None and float(per) > 0 else max((min(t1_, T_end) - t0_) / 4, 10 * h)
        tau = float(tau) if tau is not None else 0.0
        act = (ts >= t0_) & (ts < t1_)
        sig = np.zeros(n)
        if tyc == "step":
            sig[act] = amp
        elif tyc == "ramp":
            dur = (t1_ - t0_) if np.isfinite(t1_) else per
            sig = amp * np.clip((ts - t0_) / max(dur, h), 0, 1)
        elif tyc == "sine":
            sig[act] = amp * np.sin(2 * np.pi * (ts[act] - t0_) / per)
        elif tyc == "pulse":
            sig[act] = amp * (((ts[act] - t0_) % per) < per / 2)
        elif tyc == "rpulse":
            rg = np.random.default_rng(100 + ri)
            tp = t0_
            while tp < min(t1_, T_end):
                tp += rg.exponential(per)
                w_ = (ts >= tp) & (ts < tp + per / 2) & act
                sig[w_] = amp * rg.choice([-1.0, 1.0])
                tp += per / 2
        elif tyc == "noise":
            sig[act] = np.random.default_rng(200 + ri).normal(0, abs(amp), act.sum())
        if tau > 0:
            sig = lag(sig, tau, h)
        if tgc == "SP":
            sp = sp + sig / pv_range * 100
            sp_amp = max(sp_amp, abs(amp) / pv_range * 100)
        elif tgc == "IN":
            dmv = dmv + sig / mv_range * 100
            d_amp = max(d_amp, abs(amp) / mv_range * 100)
        elif tgc == "PV":
            dpv = dpv + sig / pv_range * 100
        else:
            dmeas[int(tgc[1:])] = dmeas[int(tgc[1:])] + sig
    return dict(sp=sp, dmv=dmv, dpv=dpv, dmeas=dmeas, sp_amp=sp_amp, d_amp=d_amp)


def replay_dists(ts, ts_id, d_id):
    """Přehrání měřených poruch z úseku identifikace (odchylky od počátku) na mřížku simulace."""
    return [np.interp(ts, ts_id, d - d[0]) for d in d_id]


def plant(stic_e, slip_pct, noise_e, valve_gains, pv_range, mv_range, seed=7):
    """Proces a ventil v simulaci: stikce [jednotky MV], skluz [%], šum PV [jednotky PV], charakteristika ventilu."""
    S = stic_e / mv_range * 100
    return dict(Stic=S, SticJ=S * slip_pct / 100, Noise=noise_e / pv_range * 100, ValveChar=list(valve_gains),
                Seed=seed)


def valve_curve(gains, x=None):
    """Charakteristika ventilu po pásmech 10 %: poloha [%] → efektivní MV [%] (pro graf)."""
    x = np.linspace(0, 100, 101) if x is None else np.asarray(x, float)
    g = np.asarray(gains, float)
    cum = np.r_[0.0, np.cumsum(g * 10.0)]
    i = np.minimum((x // 10).astype(int), 9)
    return x, cum[i] + g[i] * (x - 10 * i)


def stable(r):
    """Výsledek simulace je konečný a neutekl (nestabilní smyčka)."""
    return bool(np.all(np.isfinite(r["PV"])) and np.abs(r["PV"]).max() < 1e5)


def kpis(r, pv_range, mv_range):
    """Ukazatele odezvy: IAE [%·s], max. odchylka [PV], rozsah a dráha MV [MV], počet obratů ventilu."""
    Pv, Mv, S_, V = r["PV"], r["MV"], r["SPr"], r["V"]
    dv = np.diff(V)
    return dict(iae=float(core.iae(r["t"], S_, Pv)), maxdev=float(np.abs(Pv - S_).max() * pv_range / 100),
                mv_range=float((Mv.max() - Mv.min()) * mv_range / 100),
                mv_travel=float(np.abs(np.diff(Mv)).sum() * mv_range / 100),
                reversals=int(np.sum(np.diff(np.sign(dv[np.abs(dv) > 1e-9])) != 0)))
