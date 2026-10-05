"""Diagnostika provozu: oscilace, stikce, výkon smyčky, kvalita dat, hledání úseků, nelinearita, plán testu."""
import numpy as np

from .models import MODELS, simulate, predict
from .util import acf as _acf

def oscillation(x, h):
    """
    Detekce oscilací přes autokorelaci (Thornhill): perioda a pravidelnost r.
    r > 1 ⇒ pravidelná oscilace. Vrací dict(osc, period, r, amp).
    """
    x = np.asarray(x, float)
    if len(x) < 50 or np.std(x) == 0:
        return dict(osc=False, period=np.nan, r=0.0, amp=0.0)
    tt = np.arange(len(x))
    x = x - np.polyval(np.polyfit(tt, x, 1), tt)
    a = _acf(x)[: len(x) // 2]
    zc = np.where(np.sign(a[:-1]) != np.sign(a[1:]))[0]
    amp = float((np.percentile(x, 95) - np.percentile(x, 5)) / 2)
    if len(zc) < 5:
        return dict(osc=False, period=np.nan, r=0.0, amp=amp)
    zc = zc[:12]
    per = 2 * np.diff(zc) * h
    Tp = float(np.mean(per))
    r = float(Tp / (3 * np.std(per))) if np.std(per) > 0 else 10.0
    # první maximum ACF po první nule musí být výrazné
    peak = float(np.max(a[zc[1]:zc[2] + 1]))  # první kladné maximum ACF (jedna perioda)
    return dict(osc=bool(r > 1 and peak > 0.2), period=Tp, r=r, amp=amp)


def stiction_ccf(mv, pv, h, integ, period=None):
    """
    Horchův test: korelace MV a PV (u integračních procesů MV a dPV/dt).
    Lichá korelace (ρ(0) ≈ 0) ukazuje na stikci ventilu, sudá (maximum u nuly) spíš na ladění / vnější poruchu.
    Vrací poměr |ρ(0)| / max|ρ| a průběh korelace.
    """
    x = np.asarray(mv, float)
    y = np.gradient(np.asarray(pv, float), h) if integ else np.asarray(pv, float)
    x, y = x - x.mean(), y - y.mean()
    n = len(x)
    L = int(min(n // 3, (period / h if period and np.isfinite(period) else n // 6)))
    L = max(L, 5)
    lags = np.arange(-L, L + 1)
    den = np.std(x) * np.std(y) * n
    if den == 0:
        return dict(ratio=np.nan, lags=lags * h, ccf=np.zeros_like(lags, float))
    nf = 1 << int(np.ceil(np.log2(2 * n)))
    full = np.fft.irfft(np.conj(np.fft.rfft(x, nf)) * np.fft.rfft(y, nf), nf)  # full[k] = Σ x[i]·y[i+k]
    ccf = np.r_[full[nf - L:], full[:L + 1]] / den
    ratio = float(abs(ccf[L]) / max(np.max(np.abs(ccf)), 1e-12))
    return dict(ratio=ratio, lags=lags * h, ccf=ccf)


def valve_hysteresis(mv, pos, nbins=20):
    """Odhad hystereze/vůle ventilu z MV a měřené polohy: rozdíl MV při otevírání a zavírání pro stejnou polohu."""
    mv, pos = np.asarray(mv, float), np.asarray(pos, float)
    d = np.sign(np.diff(mv))
    d = np.r_[d[0] if len(d) else 0, d]
    # směr pohybu držíme i během konstantní MV
    for i in range(1, len(d)):
        if d[i] == 0:
            d[i] = d[i - 1]
    edges = np.linspace(np.percentile(pos, 2), np.percentile(pos, 98), nbins + 1)
    diffs = []
    for a, b in zip(edges[:-1], edges[1:]):
        m = (pos >= a) & (pos < b)
        up, dn = mv[m & (d > 0)], mv[m & (d < 0)]
        if len(up) > 3 and len(dn) > 3:
            diffs.append(np.median(up) - np.median(dn))
    return float(np.median(diffs)) if diffs else float("nan")


def harris_index(e, d, p_ar=20):
    """
    Harrisův index (minimum variance, FCOR): η = σ²_MV / σ²_e ∈ (0, 1].
    d = dopravní zpoždění ve vzorcích (≥ 1). Blízko 1 = regulace na hranici možností, malé = prostor ke zlepšení.
    """
    e = np.asarray(e, float) - np.mean(e)
    n = len(e)
    p_ar = int(min(p_ar, n // 10))
    if n < 100 or p_ar < 2 or np.var(e) == 0:
        return float("nan")
    X = np.column_stack([e[p_ar - i - 1:n - i - 1] for i in range(p_ar)])
    yv = e[p_ar:]
    a = np.linalg.lstsq(X, yv, rcond=None)[0]
    s2 = np.var(yv - X @ a)
    d = max(1, int(d))
    psi = np.zeros(d)
    psi[0] = 1.0
    for i in range(1, d):
        psi[i] = sum(a[j] * psi[i - j - 1] for j in range(min(p_ar, i)))
    return float(min(1.0, s2 * np.sum(psi ** 2) / np.var(e)))


def loop_kpis(t, sp, pv, mv, h, mv_lo, mv_hi, theta, has_sp=True):
    """Ukazatele výkonu smyčky z provozních dat (veličiny v %)."""
    e = (sp - pv) if has_sp else (pv - np.mean(pv))
    hours = max((t[-1] - t[0]) / 3600, 1e-9)
    dmv = np.diff(mv)
    thr = max(1e-6, 0.05 * np.std(dmv)) if len(dmv) else 1e-6
    s = np.sign(dmv[np.abs(dmv) > thr])
    rev = int(np.sum(s[1:] != s[:-1])) if len(s) > 1 else 0
    osc = oscillation(e, h)
    return dict(std_e=float(np.std(e)), iae_h=float(np.sum(np.abs(e)) * h / hours),
                travel_h=float(np.sum(np.abs(dmv)) / hours), rev_h=float(rev / hours),
                at_lim=float(np.mean((mv <= mv_lo + 1e-6) | (mv >= mv_hi - 1e-6)) * 100),
                harris=harris_index(e, theta / h + 1), osc=osc)


def _robust_sigma(x):
    d = np.diff(np.asarray(x, float))
    d = d[np.isfinite(d)]
    if len(d) < 5:
        return 0.0
    return float(1.4826 * np.median(np.abs(d - np.median(d))) / np.sqrt(2))


def detect_steps(x, h, thr=None):
    """Skokové změny signálu (MV/SP v %). Vrací seznam dict(i, size)."""
    x = np.asarray(x, float)
    n = len(x)
    if n < 5 or not np.all(np.isfinite(x)):
        x = np.nan_to_num(x, nan=np.nanmedian(x) if np.any(np.isfinite(x)) else 0.0)
    d = np.diff(x)
    noise = 1.4826 * np.median(np.abs(d - np.median(d))) if len(d) else 0.0
    thr = thr if thr else max(0.5, 8 * noise)
    idx = np.where(np.abs(d) > thr)[0]
    # souvislé změny (rampy po několik vzorků) sloučit do jedné události
    ev = []
    for i in idx:
        if ev and i - ev[-1][1] <= 2:
            ev[-1][1] = i
        else:
            ev.append([i, i])
    out = []
    for a, b in ev:
        before = x[max(0, a - 2):a + 1].mean()
        after = x[b + 1:min(n, b + 4)].mean() if b + 1 < n else x[-1]
        if abs(after - before) > thr:
            out.append(dict(i=int(a + 1), size=float(after - before)))
    return out


def data_quality(t, pv, mv, sp, h, has_sp, mv_lo, mv_hi, rep_frac=None, model=None):
    """
    Hodnocení vhodnosti úseku pro identifikaci. Úrovně: 0 = vhodná, 1 = s výhradou, 2 = nevhodná.
    Vrací dict(level, checks=[(klíč textu, úroveň, argumenty)], snr, sigma, n_steps).
    """
    checks = []
    st_mv = detect_steps(mv, h)
    sp_moves = has_sp and np.nanmax(sp) - np.nanmin(sp) > 1e-6
    st_sp = detect_steps(sp, h) if sp_moves else []
    n_eff = len(st_mv) + len(st_sp)
    sizes = [s["size"] for s in st_mv + st_sp]
    if n_eff >= 2:
        checks.append(("q_steps_ok", 0, dict(n=n_eff)))
    elif n_eff == 1:
        checks.append(("q_steps_one", 1, {}))
    else:
        checks.append(("q_steps_none", 2, {}))
    if n_eff >= 2 and (all(s > 0 for s in sizes) or all(s < 0 for s in sizes)):
        checks.append(("q_one_dir", 1, {}))
    sigma = _robust_sigma(pv)
    k = max(3, len(pv) // 200)
    pv_s = np.convolve(pv, np.ones(k) / k, mode="valid") if len(pv) > k else np.asarray(pv)
    signal = float(np.percentile(pv_s, 98) - np.percentile(pv_s, 2))
    snr = signal / sigma if sigma > 0 else np.inf
    if snr >= 10:
        checks.append(("q_snr_ok", 0, dict(s=snr)))
    elif snr >= 4:
        checks.append(("q_snr_low", 1, dict(s=snr)))
    else:
        checks.append(("q_snr_bad", 2, dict(s=snr)))
    tol = 0.005 * max(mv_hi - mv_lo, 1e-9)
    out_lim = float(np.mean((mv < mv_lo - tol) | (mv > mv_hi + tol)) * 100)
    at_lim = float(np.mean(((mv <= mv_lo + 1e-6) & (mv >= mv_lo - tol)) | ((mv >= mv_hi - 1e-6) & (mv <= mv_hi + tol))) * 100)
    if out_lim >= 5:
        # MV za limity: nesouhlasí rozsah NormMV / limity MV s daty, ne kvalita dat
        checks.append(("q_lim_out", 1, dict(p=out_lim)))
    if at_lim >= 20:
        checks.append(("q_lim_bad", 2, dict(p=at_lim)))
    elif at_lim >= 5:
        checks.append(("q_lim_warn", 1, dict(p=at_lim)))
    if rep_frac is not None and rep_frac > 0.5:
        checks.append(("q_compressed", 1, dict(p=rep_frac * 100)))
    if sp_moves and not st_sp:
        checks.append(("q_sp_ramp", 1, {}))
    if model is not None:
        code, p = model
        th = p[-1]
        Tsum = (p[1] if code in ("P1D", "P2D", "I1D") else 0.0) + (p[2] if code == "P2D" else 0.0)
        if h > max(th / 2, (th + Tsum) / 10, 1e-9):
            checks.append(("q_sampling", 1, dict(h=h)))
        ti = sorted(t[s["i"]] for s in st_mv + st_sp)
        if len(ti) >= 2 and not MODELS[code]["integ"]:
            gap = float(np.min(np.diff(ti)))
            if gap < th + 3 * Tsum:
                checks.append(("q_fast_steps", 1, dict(g=gap, s=th + 3 * Tsum)))
        if len(ti) >= 1 and (t[-1] - ti[-1]) < th + 2 * Tsum:
            checks.append(("q_short_tail", 1, dict(s=th + 2 * Tsum)))
    level = max(c_[1] for c_ in checks) if checks else 2
    return dict(level=level, checks=checks, snr=float(snr), sigma=sigma, n_steps=n_eff)


def _response_time(t, pv, t0, t1):
    """
    Doba od skoku v t0 do zřetelné odezvy PV (čtvrtina největší odchylky v okně do t1, nad šumem); None bez odezvy.
    Zahrnuje zpoždění i začátek náběhu – bez modelu je to odhad, jak dlouho po skoku musí úsek pokračovat.
    """
    i0 = int(np.searchsorted(t, t0))
    i1 = int(np.searchsorted(t, t1))
    if i0 < 1 or i1 - i0 < 5:
        return None
    seg = pv[i0:i1]
    base = float(np.nanmean(pv[max(0, i0 - 3):i0 + 1]))
    dev = np.abs(seg - base)
    d = np.diff(pv[max(0, i0 - 200):i1])
    d = d[np.isfinite(d)]
    noise = 1.4826 * np.median(np.abs(d - np.median(d))) if len(d) else 0.0
    peak = float(np.nanmax(dev)) if np.any(np.isfinite(dev)) else 0.0
    thr = max(0.25 * peak, 5 * noise)
    if not peak > thr or not thr > 0:
        return None
    k = int(np.argmax(dev > thr))
    return float(t[i0 + k] - t0)


def find_segments(t, mv, sp, h, has_sp, max_gap=None, settle=None, pv=None):
    """
    Automatické nalezení úseků vhodných pro identifikaci: shluky skoků MV (ruční režim) nebo SP (automat).
    max_gap: skoky dál od sebe tvoří samostatné úseky. settle: doba ustálení procesu (θ + 4T), je-li známa.
    pv: bez známého settle se konec úseku odhadne z odezvy PV – úsek pokračuje aspoň 2,5× dobu do zřetelné odezvy
    (u velkého zpoždění by jinak skončil dřív, než PV vůbec zareaguje).
    """
    ev = [(t[s["i"]], "mv", s["size"]) for s in detect_steps(mv, h)]
    if has_sp and np.nanmax(sp) - np.nanmin(sp) > 1e-6:
        ev += [(t[s["i"]], "sp", s["size"]) for s in detect_steps(sp, h)]
    if not ev:
        return []
    ev.sort()
    times = np.array([e[0] for e in ev])
    if max_gap is None:
        gaps = np.diff(times)
        base = np.median(gaps) if len(gaps) else (t[-1] - t[0]) / 4
        max_gap = max(3 * base, 3 * (settle or 0), 60 * h)
    groups, cur = [], [ev[0]]
    for e in ev[1:]:
        if e[0] - cur[-1][0] > max_gap:
            groups.append(cur)
            cur = [e]
        else:
            cur.append(e)
    groups.append(cur)
    out = []
    for gi, g in enumerate(groups):
        first, last = g[0][0], g[-1][0]
        prev_end = groups[gi - 1][-1][0] if gi > 0 else t[0]
        next_start = groups[gi + 1][0][0] if gi + 1 < len(groups) else t[-1]
        tail = max(settle or 0, min(max_gap, 0.6 * (next_start - last)) if gi + 1 < len(groups) else max_gap)
        if settle is None and pv is not None:
            tr = _response_time(t, np.asarray(pv, float), last, next_start if gi + 1 < len(groups) else t[-1])
            if tr:
                tail = max(tail, 2.5 * tr)
        start = max(t[0], first - min(0.3 * max_gap, 0.5 * (first - prev_end)) if gi > 0 else first - min(0.3 * max_gap, first - t[0]))
        end = min(t[-1], last + min(tail, next_start - last - h) if gi + 1 < len(groups) else last + tail)
        out.append(dict(start=float(start), end=float(end), n_mv=sum(1 for e in g if e[1] == "mv"),
                        n_sp=sum(1 for e in g if e[1] == "sp"), up=sum(1 for e in g if e[2] > 0),
                        down=sum(1 for e in g if e[2] < 0)))
    return out


# ================================================================ nelinearita
def local_gains(code, p, pdl, t, pv, mv, dists, h, thr=None):
    """
    Lokální zesílení pro každý skok MV: odchylka dat od globálního modelu se v okně po skoku
    vysvětlí změnou zesílení (odezva na daný skok · f + posun). Vrací seznam dict.
    """
    yhat, _ = predict(code, p, pdl, t, pv, mv, dists, h)
    dm = np.diff(mv)
    if thr is None:
        thr = max(0.25 * np.max(np.abs(dm)), 1e-6) if len(dm) else 1e-6
    idx = np.where(np.abs(dm) > thr)[0] + 1
    # sloučit rychle po sobě jdoucí změny (rampy)
    merged = []
    for i in idx:
        if merged and i - merged[-1] < max(3, int(0.05 * p[-1] / h) + 2):
            continue
        merged.append(i)
    out = []
    min_len = int((p[-1] + (p[1] if code in ("P1D", "P2D", "I1D") else 0)) / h) + 10
    for k, i0 in enumerate(merged):
        i1 = merged[k + 1] if k + 1 < len(merged) else len(t)
        if i1 - i0 < min_len:
            continue
        step = np.zeros(len(t))
        dstep = mv[i0] - mv[i0 - 1]
        step[i0:] = dstep
        s = simulate(code, p, t, step, h)[i0:i1]
        r = (pv - yhat)[i0:i1]
        cols = [s, np.ones_like(s)]  # drift už je v globálním modelu (u integračních by byl kolineární s rampou)
        f = np.linalg.lstsq(np.column_stack(cols), r, rcond=None)[0][0]
        out.append(dict(t=float(t[i0]), mv_from=float(mv[i0 - 1]), mv_to=float(mv[i0]), dmv=float(dstep),
                        gain=float(p[0] * (1 + f)), ratio=float(1 + f)))
    return out


def step_plan(code, p, sigma, dpv_max, mv_room=(-np.inf, np.inf), snr=10.0):
    """
    Návrh skokového testu v ručním režimu (vše v %).
    Samoregulační: dublet +Δ / 0 / −Δ / 0, každý krok drží do ustálení (θ + 4ΣT).
    Integrační: pulzy +Δ/−Δ (hladina se vrací), délka pulzu z dynamiky, Δ z povolené odchylky.
    Vrací dict s časem, průběhem MV (odchylka), predikcí PV a parametry.
    """
    th = p[-1]
    Tsum = (p[1] if code in ("P1D", "P2D", "I1D") else 0.0) + (p[2] if code == "P2D" else 0.0)
    integ = MODELS[code]["integ"]
    room = min(abs(mv_room[0]), abs(mv_room[1]))
    if not integ:
        hold = th + 4 * Tsum + max(th, 1.0)
        dmv_max = dpv_max / abs(p[0])
        dmv_min = snr * sigma / abs(p[0])
        dmv = float(min(dmv_max, room, max(dmv_min, 0.5 * dmv_max)))
        seq = [(hold, dmv), (hold, 0.0), (hold, -dmv), (hold, 0.0)]
        dpv = abs(p[0]) * dmv
    else:
        hold = 2 * (th + 3 * Tsum) + 5 * max(th, 1.0)
        dmv_max = dpv_max / (abs(p[0]) * hold)
        dmv = float(min(dmv_max, room))
        seq = [(hold, dmv), (hold, -dmv), (hold / 2, 0.0), (hold, -dmv), (hold, dmv), (hold / 2, 0.0)]
        dpv = abs(p[0]) * dmv * hold
    total = sum(s[0] for s in seq)
    hs = max(total / 3000, 0.05)
    t = np.arange(0, total + hs, hs)
    u = np.zeros_like(t)
    t0 = 0.0
    for dur, val in seq:
        u[(t >= t0) & (t < t0 + dur)] = val
        t0 += dur
    y = simulate(code, p, t, u, hs)
    snr_ach = dpv / sigma if sigma > 0 else np.inf
    return dict(t=t, u=u, y=y, dmv=dmv, hold=hold, total=total, dpv=float(np.max(np.abs(y))), snr=float(snr_ach),
                feasible=bool(snr_ach >= 3), integ=integ)
