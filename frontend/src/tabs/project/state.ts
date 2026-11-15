// Společný stav záložky Projekt: náhled reportu, podzáložka (Report / Deník ladění) a výběr ve deníku.
import { create } from "zustand";
import type { components } from "../../api/schema";

export type Snapshot = components["schemas"]["SnapshotSummary"];
export type SnapshotDetail = components["schemas"]["SnapshotDetail"];
export type JournalList = components["schemas"]["JournalList"];
export type Compare = components["schemas"]["Compare"];
export type SectionInfo = components["schemas"]["SectionInfo"];

export const STATUSES = ["draft", "deployed", "verified", "rejected"] as const;
export type Status = (typeof STATUSES)[number];

interface ReportState { html: string | null; busy: boolean; err: string | null; set: (p: Partial<ReportState>) => void }
export const useReport = create<ReportState>((set) => ({ html: null, busy: false, err: null, set: (p) => set(p) }));

interface ProjSub {
  sub: "report" | "journal"; setSub: (s: "report" | "journal") => void;
  sel: string | null; select: (id: string | null) => void;       // vybraná verze v deníku
  cmp: string | null; setCmp: (id: string | null) => void;       // verze, se kterou se porovnává
  loop: string; setLoop: (l: string) => void;                    // filtr smyčky ("" = všechny)
  status: string; setStatus: (s: string) => void;                // filtr stavu ("" = všechny)
  lang: string | null; setLang: (l: string) => void;   // jazyk reportu (null = jako rozhraní)
}
export const useProjSub = create<ProjSub>((set) => ({
  sub: "report", setSub: (sub) => set({ sub }),
  sel: null, select: (sel) => set({ sel, cmp: null }),
  cmp: null, setCmp: (cmp) => set({ cmp }),
  loop: "", setLoop: (loop) => set({ loop }),
  status: "", setStatus: (status) => set({ status }),
  lang: null, setLang: (lang) => set({ lang }),
}));
