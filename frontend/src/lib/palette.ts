// Barvy rolí a řad prohlížeče záznamu z proměnných CSS (styles/tokens.css) – jeden zdroj pro světlý i tmavý vzhled.
import { useEffect, useState } from "react";

export interface Palette { pv: string; sp: string; mv: string; pos: string; model: string; series: string[]; dist: string[]; card: string }

/** Náhradní (světlé) hodnoty, když proměnná CSS chybí (např. test bez stylů). Jediné místo s literály barev v TS. */
export const FALLBACK: Palette = {
  pv: "#1f5fa8", sp: "#7b8794", mv: "#c2410c", pos: "#7c3aed", model: "#5b3fa8",
  series: ["#2563eb", "#dc2626", "#059669", "#d97706", "#7c3aed", "#db2777", "#0891b2", "#65a30d", "#9333ea",
    "#ea580c", "#0f766e", "#b91c1c", "#4f46e5", "#a16207"],
  dist: ["#0d9488", "#8b5cf6", "#b07a05", "#64748b"],
  card: "#ffffff",                                       // pozadí karet a grafů
};

/** Přečte paletu z `<html>`; chybějící proměnná = výchozí hodnota z FALLBACK. */
export function readPalette(): Palette {
  const cs = getComputedStyle(document.documentElement);
  const v = (name: string, dflt: string) => cs.getPropertyValue(name).trim() || dflt;
  return {
    pv: v("--pid-pv", FALLBACK.pv), sp: v("--pid-sp", FALLBACK.sp), mv: v("--pid-mv", FALLBACK.mv),
    pos: v("--pid-pos", FALLBACK.pos), model: v("--pid-model", FALLBACK.model),
    series: FALLBACK.series.map((d, i) => v(`--pid-series-${i + 1}`, d)),
    dist: FALLBACK.dist.map((d, i) => v(`--pid-dist-${i + 1}`, d)),
    card: v("--pid-card", FALLBACK.card),
  };
}

/** Paleta, která se přepočítá při změně `data-theme` na `<html>`; beze změny hodnot vrací tentýž objekt. */
export function usePalette(): Palette {
  const [pal, setPal] = useState<Palette>(readPalette);
  useEffect(() => {
    const upd = () => setPal((old) => {
      const now = readPalette();
      return JSON.stringify(now) === JSON.stringify(old) ? old : now;
    });
    upd();                                                   // vzhled se mohl změnit mezi vykreslením a připojením
    const mo = new MutationObserver(upd);
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => mo.disconnect();
  }, []);
  return pal;
}

// ---- čitelnost barvy proti pozadí (barvy řad ze serveru jsou navržené pro světlý vzhled)
const hex = (c: string): [number, number, number] | null => {
  const m = /^#?([0-9a-f]{6})$/i.exec(c.trim());
  if (!m) return null;
  const n = parseInt(m[1], 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
};
const lum = ([r, g, b]: [number, number, number]) => {
  const f = (v: number) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; };
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
};
const ratio = (a: [number, number, number], b: [number, number, number]) => {
  const x = lum(a), y = lum(b);
  return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05);
};

/**
 * Barva s kontrastem aspoň `min` proti pozadí `bg`: když ho nemá, smíchá se postupně s bílou (tmavé pozadí) nebo
 * s černou (světlé pozadí) – odstín zůstane. Barvy, které nejsou ve tvaru #rrggbb, vrací beze změny.
 */
export function readable(color: string, bg: string, min = 3): string {
  const c = hex(color), b = hex(bg);
  if (!c || !b || ratio(c, b) >= min) return color;
  const to = lum(b) < 0.5 ? 255 : 0;
  for (let t = 0.1; t <= 1.0001; t += 0.1) {
    const m = c.map((v) => Math.round(v + (to - v) * t)) as [number, number, number];
    if (ratio(m, b) >= min) return "#" + m.map((v) => v.toString(16).padStart(2, "0")).join("");
  }
  return to ? "#ffffff" : "#000000";
}
