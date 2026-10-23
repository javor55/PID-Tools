"""
Binární balík signálů (časy Float64, hodnoty Float32) – formát prohlížeče záznamu a API (/signals).

pack() vrací dict(blob, sigs = [{name, ti, off, n}], times = [{off, n}], tmin, T, decim, hash): blob = [časy
Float64 …][hodnoty Float32 …] (little-endian), signál bez platných vzorků se vynechá, stejné časy se sdílejí; nad
`cap` hodnot celkem se data zhustí na min / max po skupinách (decim = velikost skupiny).
frame() / unframe(): jeden binární celek pro přenos – [4 B délka popisu (uint32 LE)][popis JSON, UTF-8, doplněný
mezerami na násobek 8 B][blob].
"""
import hashlib
import json
import struct

import numpy as np

CAP = 6_000_000          # výchozí nejvyšší počet hodnot všech signálů (víc → min / max po skupinách)


def pack(names, t_all, get, cap=CAP):
    """
    Binární data prohlížeče: [časy Float64…][hodnoty Float32…] + popis signálů {name, ti, off, n}, časů {off, n}.
    Signál bez platných vzorků se vynechá; stejné časy (široký formát) se sdílejí.
    """
    t = np.asarray(t_all, float)
    ok_t = np.isfinite(t)
    order = np.argsort(np.where(ok_t, t, np.inf), kind="stable")
    t = t[order]
    tmin = float(t[np.isfinite(t)][0]) if np.isfinite(t).any() else 0.0
    vals = []
    for nm in names:
        try:
            v = np.asarray(get(nm), float)[order]
        except Exception:
            continue
        m = np.isfinite(v) & np.isfinite(t)
        if m.sum() >= 2:
            vals.append((nm, v, m))
    total = sum(int(m.sum()) for _, _, m in vals)
    g = int(np.ceil(total / cap)) if cap and total > cap else 1
    times, tkeys, sigs, vparts = [], {}, [], []
    for nm, v, m in vals:
        tt, vv = t[m] - tmin, v[m]
        if g > 1:                                  # min / max po skupinách g vzorků (tvar a špičky zůstanou)
            idx = minmax_idx(vv, 2 * g)
            tt, vv = tt[idx], vv[idx]
            key_t = None
        else:
            key_t = hashlib.md5(np.packbits(m).tobytes()).hexdigest()
        if key_t is not None and key_t in tkeys:
            ti = tkeys[key_t]
        else:
            ti = len(times)
            times.append(tt.astype(np.float64))
            if key_t is not None:
                tkeys[key_t] = ti
        sigs.append(dict(name=str(nm), ti=ti, n=int(len(vv))))
        vparts.append(vv.astype(np.float32))
    off, tdesc = 0, []
    for a in times:
        tdesc.append(dict(off=off, n=int(len(a))))
        off += a.nbytes
    for s_, a in zip(sigs, vparts):
        s_["off"] = off
        off += a.nbytes
    blob = b"".join([a.tobytes() for a in times] + [a.tobytes() for a in vparts])
    T_end = max((float(a[-1]) for a in times if len(a)), default=1.0)
    return dict(blob=blob, sigs=sigs, times=tdesc, tmin=tmin, T=max(T_end, 1e-9), decim=g,
                hash=hashlib.md5(blob).hexdigest()[:16])


def minmax_idx(v, g):
    """Indexy min a max v každé skupině g vzorků (seřazené)."""
    n = len(v)
    if n <= g:
        return np.arange(n)
    m = int(np.ceil(n / g)) * g
    a = np.full(m, np.nan)
    a[:n] = v
    a = a.reshape(-1, g)
    base = np.arange(a.shape[0]) * g
    imin = base + np.nanargmin(np.where(np.isfinite(a), a, np.inf), axis=1)
    imax = base + np.nanargmax(np.where(np.isfinite(a), a, -np.inf), axis=1)
    idx = np.unique(np.concatenate([imin, imax]))
    return idx[idx < n]


def frame(p):
    """Balík → bajty pro přenos (popis JSON + blob)."""
    meta = {k: v for k, v in p.items() if k != "blob"}
    head = json.dumps(meta, separators=(",", ":")).encode("utf-8")
    head += b" " * ((-(4 + len(head))) % 8)                  # blob začíná na násobku 8 B (Float64Array)
    return struct.pack("<I", len(head)) + head + p["blob"]


def unframe(data):
    """Bajty → (popis, {název: (časy, hodnoty)})."""
    n = struct.unpack_from("<I", data, 0)[0]
    meta = json.loads(data[4:4 + n].decode("utf-8"))
    blob = memoryview(data)[4 + n:]
    times = [np.frombuffer(blob, np.float64, d["n"], d["off"]) for d in meta["times"]]
    out = {s["name"]: (times[s["ti"]], np.frombuffer(blob, np.float32, s["n"], s["off"])) for s in meta["sigs"]}
    return meta, out
