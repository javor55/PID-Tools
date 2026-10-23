// Stav rozhraní (Zustand): jazyk, vzhled, záložka, pracovní prostor, běžící úlohy. Výsledky výpočtů drží
// TanStack Query (cache dotazů na API), sem patří jen to, co patří rozhraní.
import { create } from "zustand";
import type { JobInfo } from "./api/client";

export const TABS = [
  { id: "data", label: "tab1", milestone: "M13" },
  { id: "model", label: "tab2", milestone: "M14" },
  { id: "tuning", label: "tab3", milestone: "M16" },
  { id: "live", label: "tab4_live", milestone: "M18" },
  { id: "apc", label: "tab5", milestone: "M19" },
  { id: "diag", label: "dk_diag_tab", milestone: "M20" },
  { id: "loops", label: "tab7_audit", milestone: "M20" },
  { id: "project", label: "tab_project", milestone: "M21" },
] as const;
export type TabId = (typeof TABS)[number]["id"];
export type Theme = "system" | "light" | "dark";

function load<T>(k: string, d: T): T {
  try { const v = localStorage.getItem(k); return v === null ? d : (JSON.parse(v) as T); } catch { return d; }
}
function save(k: string, v: unknown) {
  try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* bez úložiště */ }
}

interface UiState {
  lang: "cs" | "en";
  theme: Theme;
  tab: TabId;
  wid: string | null;
  jobs: Record<string, JobInfo>;
  setLang: (l: "cs" | "en") => void;
  setTheme: (t: Theme) => void;
  setTab: (t: TabId) => void;
  setWid: (w: string | null) => void;
  putJob: (j: JobInfo) => void;
  dropJob: (id: string) => void;
}

export const useUi = create<UiState>((set) => ({
  lang: load("pid.lang", navigator.language?.startsWith("cs") ? "cs" : "en"),
  theme: load<Theme>("pid.theme", "system"),
  tab: load<TabId>("pid.tab", "data"),
  wid: null,
  jobs: {},
  setLang: (lang) => { save("pid.lang", lang); set({ lang }); },
  setTheme: (theme) => { save("pid.theme", theme); set({ theme }); },
  setTab: (tab) => { save("pid.tab", tab); set({ tab }); },
  setWid: (wid) => set({ wid }),
  putJob: (j) => set((s) => ({ jobs: { ...s.jobs, [j.id]: j } })),
  dropJob: (id) => set((s) => { const jobs = { ...s.jobs }; delete jobs[id]; return { jobs }; }),
}));
