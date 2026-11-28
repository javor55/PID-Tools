// Hromadné akce nad smyčkami projektu (FEATURE-007): výběr smyček, spuštění úlohy `/batch` a čtení jejích výsledků.
// Data serveru jdou přes TanStack Query, ve Zustandu je jen stav rozhraní (výběr, filtr, poslední úloha).
import { useQuery } from "@tanstack/react-query";
import { useCallback } from "react";
import { create } from "zustand";
import { request } from "../../api/client";
import type { components } from "../../api/schema";
import { toastError } from "../../components/Toasts";
import { useT } from "../../i18n";
import { useJobRunner } from "../../jobs";
import { useUi } from "../../store";

export type BatchOut = components["schemas"]["BatchOut"];
export type BatchRow = components["schemas"]["BatchRow"];
export type BatchParams = components["schemas"]["BatchParams"];
export type BatchAction = components["schemas"]["BatchReq"]["action"];

interface BatchUi {
  sel: number[];                                   // vybrané smyčky (index v projektu)
  setSel: (s: number[]) => void;
  onlyProblems: boolean;
  setOnlyProblems: (v: boolean) => void;
  last: { jid: string; action: BatchAction } | null;   // poslední spuštěná úloha (její řádky se ukazují v souhrnu)
  running: boolean;
  set: (p: Partial<BatchUi>) => void;
}

export const useBatchUi = create<BatchUi>((set) => ({
  sel: [], setSel: (sel) => set({ sel }),
  onlyProblems: false, setOnlyProblems: (onlyProblems) => set({ onlyProblems }),
  last: null, running: false,
  set: (p) => set(p),
}));

/** Řádky výsledku úlohy (i rozpracované / zrušené): GET /batch/{jid}. */
export function useBatchOut(jid: string | null) {
  const wid = useUi((s) => s.wid);
  return useQuery({
    queryKey: ["ws", wid, "batch", jid], enabled: !!wid && !!jid,
    queryFn: () => request<BatchOut>("GET", `/workspaces/${wid}/batch/${jid}`),
  });
}

/** Spustí hromadnou akci jako úlohu (průběh a zrušení ve stavovém řádku); chyba se hlásí toastem. */
export function useBatchRun() {
  const T = useT();
  const run = useJobRunner();
  const set = useBatchUi((s) => s.set);
  return useCallback(async (action: BatchAction, loops: number[], params?: BatchParams) => {
    if (!loops.length) return;
    set({ running: true });
    try {
      const j = await run("/batch", { loops, action, ...(params ? { params } : {}) }, T("bt_job_" + action));
      set({ last: { jid: j.id, action } });
    } catch (e) {
      toastError(e);
    } finally {
      set({ running: false });
    }
  }, [run, set, T]);
}
