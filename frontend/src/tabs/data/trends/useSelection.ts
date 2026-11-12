// Trendy – výběr signálů (včetně vypočtených) společný hlavní ploše a pravému panelu.
import { useMemo } from "react";
import { type TrendCatalog, useTrendCatalog } from "./hooks";
import { CALC_COLORS, defaultSelection, type SigInfo } from "./model";
import { useTrends } from "./state";

export interface Selection extends TrendCatalog {
  all: SigInfo[];                        // sloupce zdrojů + vypočtené signály
  allInfo: Map<string, SigInfo>;
  checked: string[];                     // vybrané (existující) odkazy v pořadí stromu
}

export function useSelection(): Selection {
  const cat = useTrendCatalog();
  const calcs = useTrends((s) => s.calcs);
  const chk = useTrends((s) => s.checked);
  return useMemo(() => {
    const ci: SigInfo[] = calcs.map((c, k) => ({
      ref: `calc:${c.id}`, source: "calc", sourceName: "ƒ", column: c.name, loop: null, loopIndex: null, role: "", label: c.name,
      color: CALC_COLORS[k % CALC_COLORS.length], dash: null, quantity: c.unit ? `u:${c.unit}` : "q:calc", unit: c.unit,
    }));
    const all = [...cat.sigs, ...ci];
    const allInfo = new Map(all.map((s) => [s.ref, s]));
    const want = chk ?? defaultSelection(cat.sigs);
    const set = new Set(want);
    return { ...cat, all, allInfo, checked: all.filter((s) => set.has(s.ref)).map((s) => s.ref) };
  }, [cat, calcs, chk]);
}
