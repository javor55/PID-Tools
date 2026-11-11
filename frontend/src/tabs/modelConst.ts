// Záložka Model: společné konstanty (modely, barvy vstupů podle návrhu) a pomocné výpočty.
export const MODELS = ["P0D", "P1D", "P2D", "I0D", "I1D"] as const;
/** Modely podle výchozího typu přenosů (Struktura modelu): integrační / samoregulační / auto. */
export const FAMILY: Record<string, readonly string[]> = {
  integ: ["I0D", "I1D"], self: ["P0D", "P1D", "P2D"], auto: MODELS };
export const DIST_CHOICES = ["pv", "auto", ...MODELS] as const;
/** Barvy úseků a karet: [čára, text, pozadí, ohraničení] – MV jantarová, poruchy podle pořadí (jako v grafech). */
export const DIST_STYLE = [["#0d9488", "#0b7a70", "#e3f5f2", "#8fd3ca"], ["#7c3aed", "#5b21b6", "#f3effc", "#c9b8f0"],
  ["#db2777", "#9d174d", "#fdf0f6", "#f5b8d3"], ["#0891b2", "#0e7490", "#e6f6fa", "#9fdcec"]];
export const MV_STYLE = ["#f59e0b", "#c77d00", "#fff4dc", "#f2c46d"];

/**
 * Shoda modelu v každém úseku vstupu: `fits` z API jsou po sloučených úsecích (úseky všech vstupů se překrývají →
 * jeden sloučený), zde se přiřadí zpět každému úseku vstupu (jako `owner_fits` ve webu).
 */
export function windowFits(wins: Record<string, number[][]>, fits: (number | null)[], Ts: number): Record<string, (number | null)[]> {
  const all = Object.values(wins).flat().map(([a, b]) => [a, b] as [number, number])
    .filter(([a, b]) => b - a >= 3 * Ts).sort((x, y) => x[0] - y[0]);
  const merged: [number, number][] = [];
  for (const [a, b] of all) {
    const last = merged[merged.length - 1];
    if (last && a <= last[1]) last[1] = Math.max(last[1], b); else merged.push([a, b]);
  }
  const out: Record<string, (number | null)[]> = {};
  for (const [k, w] of Object.entries(wins)) {
    out[k] = w.map(([a]) => {
      const i = merged.findIndex(([ma, mb]) => a >= ma - Ts && a < mb);
      return i >= 0 && i < fits.length ? fits[i] : null;
    });
  }
  return out;
}

export const mean = (a: (number | null)[]): number | null => {
  const v = a.filter((x): x is number => x !== null && Number.isFinite(x));
  return v.length ? v.reduce((s, x) => s + x, 0) / v.length : null;
};
