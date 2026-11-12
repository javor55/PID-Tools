// Stav rozhraní (Zustand): jazyk, vzhled, záložka, pracovní prostor, běžící úlohy. Výsledky výpočtů drží
// TanStack Query (cache dotazů na API), sem patří jen to, co patří rozhraní.
import { create } from "zustand";
import type { JobInfo } from "./api/client";
import type { components } from "./api/schema";

export const TABS = [
  { id: "data", label: "tab1", milestone: "M13" },
  { id: "model", label: "tab2", milestone: "M14" },
  { id: "tuning", label: "ui_tab_tuning", milestone: "M16" },
  { id: "apc", label: "ui_tab_apc", milestone: "M19" },
  { id: "live", label: "ui_tab_live", milestone: "M18" },
  { id: "project", label: "tab_project", milestone: "M21" },
  // Dřívější samostatné záložky: v návrhu v2 jsou podzáložky Data › Diagnostika (setTab je přesměruje).
  { id: "diag", label: "ui_dsub_diag_detail", milestone: "M20" },
  { id: "loops", label: "ui_dsub_diag_all", milestone: "M20" },
] as const;
/** Záložky v řádku pod hlavičkou; Projekt a report se otevírá tlačítkem v hlavičce (jako v návrhu). */
export const NAV_TABS = TABS.filter((t) => t.id !== "project" && t.id !== "diag" && t.id !== "loops");
export type TabId = (typeof TABS)[number]["id"];
/** Podzáložky Data (návrh v2): Zdroje a smyčky, Trendy, Kvalita dat, Diagnostika (Všechny smyčky / Detail smyčky). */
export const DATA_SUBS = ["sources", "trends", "quality", "diag-all", "diag-detail"] as const;
export type DataSub = (typeof DATA_SUBS)[number];
export const isDiagSub = (s: DataSub): s is "diag-all" | "diag-detail" => s === "diag-all" || s === "diag-detail";
export type Theme = "system" | "light" | "dark";

function load<T>(k: string, d: T): T {
  try { const v = localStorage.getItem(k); return v === null ? d : (JSON.parse(v) as T); } catch { return d; }
}
function save(k: string, v: unknown) {
  try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* bez úložiště */ }
}

/** Úseky provozních dat v Diagnostice (A, B, porovnání) – podle záznamu (`key`), jen v prohlížeči jako v desktopu. */
export interface DiagWin { key: string; a: [number, number]; b: [number, number]; cmp: boolean }

/** Výsledek přehledu smyček (`POST /audit/analyse`) pro pracovní prostor – zůstane při přepnutí záložky. */
export interface AuditState { wid: string; res: components["schemas"]["Audit"] }

interface UiState {
  lang: "cs" | "en";
  theme: Theme;
  tab: TabId;
  dataSub: DataSub;
  apcTech: string;
  wid: string | null;
  /** Výška grafů z nastavení aplikace (výchozí výška LineChart). */
  chartH: number;
  jobs: Record<string, JobInfo>;
  diag: DiagWin | null;
  setDiag: (d: DiagWin) => void;
  audit: AuditState | null;
  setAudit: (a: AuditState | null) => void;
  setLang: (l: "cs" | "en") => void;
  setTheme: (t: Theme) => void;
  setTab: (t: TabId) => void;
  setDataSub: (s: DataSub) => void;
  setApcTech: (t: string) => void;
  setWid: (w: string | null) => void;
  putJob: (j: JobInfo) => void;
  /** Příkaz kartám panelu „Rozbalit vše / Sbalit vše“ (n roste s každým kliknutím). */
  sideCmd: { n: number; open: boolean };
  sideAll: (open: boolean) => void;
  dropJob: (id: string) => void;
}

export const useUi = create<UiState>((set) => ({
  lang: load("pid.lang", navigator.language?.startsWith("cs") ? "cs" : "en"),
  theme: load<Theme>("pid.theme", "system"),
  tab: ((t) => (t === "diag" || t === "loops" ? "data" : t))(load<TabId>("pid.tab", "data")),
  dataSub: load<DataSub>("pid.dsub", "sources"),
  apcTech: load("pid.apc", "ff"),
  wid: (() => { try { return sessionStorage.getItem("pid.wid"); } catch { return null; } })(),
  chartH: 220,
  jobs: {},
  diag: null,
  setDiag: (diag) => set({ diag }),
  audit: null,
  setAudit: (audit) => set({ audit }),
  setLang: (lang) => { save("pid.lang", lang); set({ lang }); },
  setTheme: (theme) => { save("pid.theme", theme); set({ theme }); },
  // „diag“ a „loops“ (staré odkazy, akce průvodce) otevřou podzáložky Data › Diagnostika.
  setTab: (tab) => {
    if (tab === "diag" || tab === "loops") { const dataSub = tab === "diag" ? "diag-detail" : "diag-all"; save("pid.tab", "data"); save("pid.dsub", dataSub); set({ tab: "data", dataSub }); return; }
    save("pid.tab", tab); set({ tab });
  },
  setDataSub: (dataSub) => { save("pid.dsub", dataSub); save("pid.tab", "data"); set({ dataSub, tab: "data" }); },
  setApcTech: (apcTech) => { save("pid.apc", apcTech); set({ apcTech }); },
  setWid: (wid) => { try { if (wid) sessionStorage.setItem("pid.wid", wid); else sessionStorage.removeItem("pid.wid"); } catch { /* */ } set({ wid }); },
  putJob: (j) => set((s) => ({ jobs: { ...s.jobs, [j.id]: j } })),
  sideCmd: { n: 0, open: true },
  sideAll: (open) => set((s) => ({ sideCmd: { n: s.sideCmd.n + 1, open } })),
  dropJob: (id) => set((s) => { const jobs = { ...s.jobs }; delete jobs[id]; return { jobs }; }),
}));
