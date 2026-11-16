// Barvy rolí a řad prohlížeče záznamu z proměnných CSS (styles/tokens.css) – jeden zdroj pro světlý i tmavý vzhled.
import { useEffect, useState } from "react";

export interface Palette { pv: string; sp: string; mv: string; pos: string; series: string[]; dist: string[] }

/** Náhradní (světlé) hodnoty, když proměnná CSS chybí (např. test bez stylů). Jediné místo s literály barev v TS. */
export const FALLBACK: Palette = {
  pv: "#1f5fa8", sp: "#7b8794", mv: "#c2410c", pos: "#7c3aed",
  series: ["#2563eb", "#dc2626", "#059669", "#d97706", "#7c3aed", "#db2777", "#0891b2", "#65a30d", "#9333ea",
    "#ea580c", "#0f766e", "#b91c1c", "#4f46e5", "#a16207"],
  dist: ["#0d9488", "#8b5cf6", "#b07a05", "#64748b"],
};

/** Přečte paletu z `<html>`; chybějící proměnná = výchozí hodnota z FALLBACK. */
export function readPalette(): Palette {
  const cs = getComputedStyle(document.documentElement);
  const v = (name: string, dflt: string) => cs.getPropertyValue(name).trim() || dflt;
  return {
    pv: v("--pid-pv", FALLBACK.pv), sp: v("--pid-sp", FALLBACK.sp), mv: v("--pid-mv", FALLBACK.mv),
    pos: v("--pid-pos", FALLBACK.pos),
    series: FALLBACK.series.map((d, i) => v(`--pid-series-${i + 1}`, d)),
    dist: FALLBACK.dist.map((d, i) => v(`--pid-dist-${i + 1}`, d)),
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
