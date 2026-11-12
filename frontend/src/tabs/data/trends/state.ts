// Trendy – stav rozhraní sdílený mezi hlavní plochou (grafy) a pravým panelem (strom signálů): Zustand.
import { create } from "zustand";
import type { Calc, LayoutMode } from "./model";

export interface TrendsState {
  checked: string[] | null;             // vybrané odkazy `zdroj:sloupec` (a `calc:id`); null = výchozí výběr
  layout: LayoutMode;
  groupBy: "loop" | "source";
  search: string;
  onlyActive: boolean;
  sharedY: boolean;
  view: [number, number] | null;        // zoom [s] na společné ose; null = celý rozsah
  a: number | null;
  b: number | null;
  calcs: Calc[];
  set: (p: Partial<Omit<TrendsState, "set" | "toggle" | "reset">>) => void;
  toggle: (ref: string, all: string[]) => void;
  reset: () => void;
}

const INIT = {
  checked: null, layout: "loop" as LayoutMode, groupBy: "loop" as const, search: "", onlyActive: false, sharedY: false,
  view: null, a: null, b: null, calcs: [] as Calc[],
};

export const useTrends = create<TrendsState>((set) => ({
  ...INIT,
  set: (p) => set(p),
  toggle: (ref, all) => set((s) => {
    const cur = s.checked ?? all;
    return { checked: cur.includes(ref) ? cur.filter((x) => x !== ref) : [...cur, ref] };
  }),
  reset: () => set({ ...INIT }),
}));
