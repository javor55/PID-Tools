// Příprava průběhů pro graf (stejně jako pidtools/ui/trend.py): společné zředění dlouhých záznamů (min / max
// prvního průběhu po skupinách), zaokrouhlení, rozsah osy s okrajem.
export const MAX_PTS = 6000;

type Arr = ArrayLike<number>;

export function decimate(n: number, ref: Arr): number[] {
  if (n <= MAX_PTS) return Array.from({ length: n }, (_, i) => i);
  const g = Math.ceil(n / (MAX_PTS / 2));
  const out = new Set<number>();
  for (let b = 0; b < n; b += g) {
    let imin = b, imax = b, vmin = Infinity, vmax = -Infinity;
    for (let i = b; i < Math.min(b + g, n); i++) {
      const v = ref[i];
      if (!Number.isFinite(v)) continue;
      if (v < vmin) { vmin = v; imin = i; }
      if (v > vmax) { vmax = v; imax = i; }
    }
    out.add(imin); out.add(imax);
  }
  return [...out].sort((a, b) => a - b);
}

export function pick(a: Arr | undefined | null, idx: number[]): (number | null)[] | null {
  if (!a) return null;
  let big = 0;
  for (const i of idx) { const v = a[i]; if (Number.isFinite(v) && Math.abs(v) > big) big = Math.abs(v); }
  const dec = Math.min(12, Math.max(0, 5 - Math.floor(Math.log10(Math.max(big, 1e-12)))));
  const f = 10 ** dec;
  return idx.map((i) => (Number.isFinite(a[i]) ? Math.round(a[i] * f) / f : null));
}

export function range(...arrs: (Arr | null | undefined)[]): [number, number] {
  let lo = Infinity, hi = -Infinity;
  for (const a of arrs) if (a) for (let i = 0; i < a.length; i++) { const v = a[i]; if (Number.isFinite(v)) { if (v < lo) lo = v; if (v > hi) hi = v; } }
  if (!Number.isFinite(lo)) return [0, 1];
  if (hi - lo < 1e-9) { lo -= 1; hi += 1; }
  const m = 0.06 * (hi - lo);
  return [lo - m, hi + m];
}

export function runs(mask: Arr, t: Arr): [number, number][] {
  const out: [number, number][] = [];
  let a = -1;
  for (let i = 0; i <= mask.length; i++) {
    const on = i < mask.length && !!mask[i];
    if (on && a < 0) a = i;
    if (!on && a >= 0) { out.push([t[a], t[Math.min(i, t.length - 1)]]); a = -1; if (out.length >= 300) break; }
  }
  return out;
}

export function timeUnit(span: number): { u: string; f: number } {
  const u = span <= 1200 ? "s" : span <= 72000 ? "min" : "h";
  return { u, f: u === "s" ? 1 : u === "min" ? 60 : 3600 };
}
