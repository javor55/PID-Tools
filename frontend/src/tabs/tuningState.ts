// Stav záložky Ladění sdílený mezi hlavní plochou a pravým panelem: zvolená metoda, návrh, pohled, časová osa,
// kurzory měření, přepínače simulace, porovnání metod. Patří k pracovnímu prostoru (při jeho změně se vynuluje).
import { useEffect } from "react";
import { create } from "zustand";
import { request } from "../api/client";
import type { components } from "../api/schema";
import { useSettings } from "../data";
import { useUi } from "../store";

export type Suggestion = components["schemas"]["Suggestion"] & { sig?: string; t?: string; fromRow?: boolean };
export type CmpRow = { method: string; crit: string | null; ctype: string; Kc: number; Ti: number; Td: number;
  Ms: number | null; iae_load: number | null; iae_sp: number | null; ovs: number | null; noise: number | null };
export type View = "time" | "freq" | "all";
export type Unit = "auto" | "s" | "min" | "h";

interface TunState {
  wid: string | null;
  method: string | null;
  sug: Suggestion | null;
  err: string | null;
  busy: boolean;
  view: View;
  unit: Unit;
  measure: boolean;
  cur: number[];                     // kurzory t1, t2 [s] (nejvýše dva)
  spread: boolean;
  robust: boolean;
  ffcmp: boolean;
  tend: number | null;               // vlastní délka simulace [s]; null = automaticky
  lenUnit: Unit;
  cmp: CmpRow[] | null;
  cmpBusy: boolean;
  set: (p: Partial<TunState>) => void;
}

const fresh = (wid: string | null) => ({ wid, method: null, sug: null, err: null, busy: false, cur: [], tend: null,
  cmp: null, cmpBusy: false });

export const useTun = create<TunState>((set) => ({
  ...fresh(null), view: "time", unit: "auto", measure: false, spread: false, robust: false, ffcmp: false, lenUnit: "auto",
  set: (p) => set(p),
}));

/** Při změně pracovního prostoru zahodí návrh a výsledky (volá hlavní plocha i panel). */
export function useTunSync() {
  const wid = useUi((s) => s.wid);
  const cur = useTun((s) => s.wid);
  useEffect(() => { if (wid !== cur) useTun.setState(fresh(wid)); }, [wid, cur]);
}

/** Otisk nastavení, které ovlivňuje návrh (změna = návrh je neaktuální); sady a scénář do něj nepatří. */
export function settingsSig(st: Record<string, unknown>): string {
  return JSON.stringify(Object.keys(st).filter((k) => !/^(set\d|tune_hist|scen|sim_|tend|dsel|ed\||method\|)/.test(k)).sort()
    .map((k) => [k, st[k]]));
}

/** Výpočet návrhu zvolenou metodou (tlačítko Vypočítat, automaticky u rychlých metod, převzetí řádku porovnání). */
export function useCalc() {
  const wid = useUi((s) => s.wid);
  const st = useSettings().data ?? {};
  const sig = settingsSig(st);
  return async (method: string) => {
    useTun.setState({ err: null, busy: true });
    try {
      const sug = await request<Suggestion>("POST", `/workspaces/${wid}/tuning/suggest`, { method });
      useTun.setState({ sug: { ...sug, sig: `${method}|${sig}`, t: new Date().toLocaleTimeString() }, busy: false });
    } catch (e) { useTun.setState({ err: String((e as Error).message), busy: false }); }
  };
}
