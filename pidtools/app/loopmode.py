"""
Režim smyčky v záznamu (ručně MAN / regulátor AUTO) a kontroly věrohodnosti modelu a návrhu ladění.

Identifikace „otevřené smyčky“ (fit MV → PV) předpokládá, že MV mění člověk (skoky) a ne regulátor. Když v úseku
MV plynule mění regulátor podle odchylky, MV a PV nejsou nezávislé a model vychází zkreslený – typicky kratší
dopravní zpoždění a jiné zesílení. `detect` proto rozdělí záznam na úseky MAN / AUTO: v AUTO se MV hýbe ve většině
vzorků a nejde o jednotlivé skoky; je-li k dispozici SP, musí změny MV aspoň zčásti vysvětlovat regulační odchylka.

Bez závislosti na UI (web i desktop).
"""
import numpy as np

AUTO_MIN = 0.15        # podíl AUTO v úseku, od kterého se otevřená smyčka hlásí jako zkreslená
CL_MIN = 0.5           # podíl AUTO, od kterého režim „auto“ volí identifikaci v uzavřené smyčce


def _window_auto(dmv, de, e, h, tiny):
    """Je okno v AUTO? (podíl vzorků s pohybem MV, skokovitost, vysvětlení odchylkou)."""
    moving = np.abs(dmv) > tiny
    frac = float(moving.mean()) if len(dmv) else 0.0
    if frac < 0.15:
        return False
    tot = float(np.abs(dmv).sum())
    if tot > 0 and float(np.abs(dmv).max()) > 0.6 * tot:      # jeden skok = ruční zásah
        return False
    if de is None:
        return frac >= 0.3
    X = np.c_[de, e * h]
    try:
        coef, *_ = np.linalg.lstsq(X, dmv, rcond=None)
    except np.linalg.LinAlgError:
        return frac >= 0.3
    res = dmv - X @ coef
    r2 = 1 - float(np.sum(res ** 2)) / max(float(np.sum((dmv - dmv.mean()) ** 2)), 1e-12)
    return frac >= 0.5 or r2 >= 0.05


def detect(t, mv, pv=None, sp=None, win_s=600.0):
    """
    Úseky MAN / AUTO v záznamu: dict(auto = maska vzorků v AUTO, runs = [(od, do, "man" | "auto")], frac = podíl AUTO).
    Okna délky win_s (aspoň 30 vzorků) s polovičním překryvem; vzorek patří do AUTO, když je AUTO většina oken,
    která ho obsahují.
    """
    t, mv = np.asarray(t, float), np.asarray(mv, float)
    n = len(t)
    if n < 10:
        return dict(auto=np.zeros(n, bool), runs=[(float(t[0]), float(t[-1]), "man")] if n else [], frac=0.0)
    h = float(np.median(np.diff(t)))
    w = int(max(30, round(win_s / max(h, 1e-9))))
    w = min(w, n)
    span = float(np.nanmax(mv) - np.nanmin(mv))
    tiny = max(1e-4 * max(span, 1.0), 1e-9)
    has_sp = sp is not None and pv is not None
    if has_sp:
        e = np.asarray(sp, float) - np.asarray(pv, float)
    votes, cnt = np.zeros(n), np.zeros(n)
    step = max(1, w // 2)
    starts = list(range(0, max(1, n - w + 1), step))
    if starts[-1] + w < n:                       # poslední okno až do konce záznamu
        starts.append(n - w)
    for a in starts:
        b = min(n, a + w)
        dmv = np.diff(mv[a:b])
        ok = np.isfinite(dmv)
        if has_sp:
            de, ek = np.diff(e[a:b]), e[a + 1:b]
            ok &= np.isfinite(de) & np.isfinite(ek)
            au = _window_auto(dmv[ok], de[ok], ek[ok], h, tiny)
        else:
            au = _window_auto(dmv[ok], None, None, h, tiny)
        votes[a:b] += au
        cnt[a:b] += 1
    auto = votes / np.maximum(cnt, 1) > 0.5
    auto = _merge_short(auto, w)
    runs = []
    d = np.diff(np.r_[0, auto.astype(int), 0])
    edges = np.sort(np.r_[0, np.where(d != 0)[0], n])
    edges = np.unique(np.clip(edges, 0, n))
    for i0, i1 in zip(edges[:-1], edges[1:]):
        if i1 > i0:
            runs.append((float(t[i0]), float(t[i1 - 1]), "auto" if auto[i0] else "man"))
    return dict(auto=auto, runs=runs, frac=float(auto.mean()))


def _merge_short(auto, w):
    """Krátké úseky (méně než jedno okno) přiřadit okolí – žádné drobné střídání MAN / AUTO."""
    auto = auto.copy()
    for _ in range(3):
        d = np.diff(np.r_[0, auto.astype(int), 0])
        edges = np.unique(np.r_[0, np.where(d != 0)[0], len(auto)])
        changed = False
        for i0, i1 in zip(edges[:-1], edges[1:]):
            if 0 < i1 - i0 < w and i0 > 0 and i1 < len(auto):
                auto[i0:i1] = not auto[i0]
                changed = True
        if not changed:
            break
    return auto


def frac_in(det, t, a, b):
    """Podíl AUTO v úseku (od, do) [s]."""
    t = np.asarray(t, float)
    m = (t >= a) & (t <= b)
    return float(det["auto"][m].mean()) if m.any() else 0.0


def manual_span(det, t, mv, a, b, min_len=None):
    """
    Nejvhodnější ruční (MAN) úsek uvnitř (od, do) pro identifikaci otevřené smyčky: nejdelší souvislý MAN úsek,
    ve kterém se MV aspoň jednou výrazně změní (skok). Vrací (od, do) nebo None.
    """
    t, mv = np.asarray(t, float), np.asarray(mv, float)
    span = float(np.nanmax(mv) - np.nanmin(mv)) or 1.0
    best, best_len = None, 0.0
    for r0, r1, kind in det["runs"]:
        if kind != "man":
            continue
        a2, b2 = max(a, r0), min(b, r1)
        if b2 <= a2:
            continue
        m = (t >= a2) & (t <= b2)
        if m.sum() < 10 or np.ptp(mv[m]) < 0.05 * span:
            continue
        if min_len and b2 - a2 < min_len:
            continue
        if b2 - a2 > best_len:
            best, best_len = (float(a2), float(b2)), b2 - a2
    return best


def resolve_mode(choice, auto_frac, has_sp, excitation_ok=True, set1_ok=True):
    """
    Režim identifikace: „open“ / „cl“ podle volby; „auto“ = uzavřená smyčka, když je většina úseku v AUTO, je SP
    a Set 1 je skutečný regulátor ze záznamu (ne výchozí zástupné hodnoty – simulace smyčky by pak model zkreslila).
    """
    if choice in ("open", "cl"):
        return choice
    return "cl" if (auto_frac >= CL_MIN and has_sp and excitation_ok and set1_ok) else "open"


# ---- kontroly věrohodnosti modelu a ladění
def dominant_T(code, p):
    """Rozhodující setrvačnost modelu [s] (0 u modelů bez setrvačnosti)."""
    return float(p[1]) if code in ("P1D", "P2D", "I1D") else 0.0


def model_checks(code, p, Ts):
    """
    Podezřelý model: [(klíč textu, argumenty)] – u pomalého procesu (T ≥ 100 · perioda dat) skoro nulové dopravní
    zpoždění (θ + T2 < 1 % T): takový model dovolí libovolně velké zesílení regulátoru.
    """
    out = []
    T = dominant_T(code, p)
    th_eff = float(p[-1]) + (float(p[2]) if code == "P2D" else 0.0)
    if T > 0 and T >= 100 * Ts and th_eff < max(0.01 * T, Ts):
        out.append(("chk_no_delay", dict(th=round(th_eff, 1), T=T)))
    return out


def tuning_checks(code, p, Kc, Ts, set1_gain=None):
    """
    Podezřelý návrh ladění: [(klíč, argumenty)] – zesílení smyčky K·Gain > 20 (samoregulační proces), návrh
    o víc než 20× jiný než současná sada 1, model bez dopravního zpoždění.
    """
    out = list(model_checks(code, p, Ts))
    if code in ("P0D", "P1D", "P2D") and abs(float(p[0]) * Kc) > 20:
        out.append(("chk_loop_gain", dict(kk=abs(float(p[0]) * Kc))))
    if set1_gain and abs(set1_gain) > 0 and Kc:
        r = abs(Kc / set1_gain)
        if r > 20 or r < 0.05:
            out.append(("chk_vs_set1", dict(r=r, g=set1_gain)))
    return out
