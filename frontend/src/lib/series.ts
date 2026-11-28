// Pomocné funkce pro grafy záznamu: úseky, kde je maska zapnutá (vyloučené části), a jednotka časové osy.
type Arr = ArrayLike<number>;

/** Úseky [od, do] [s], kde je `mask` nenulová (nejvýš 300). */
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
