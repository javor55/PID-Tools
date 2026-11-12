// Stav obrazovky Nastavení (celostránkový pohled z hlavičky) a knihovny regulátorů; jen v prohlížeči.
import { create } from "zustand";
import { useUi } from "../store";

export type Section = "general" | "controllers";
export type CtlView = "library" | "editor" | "test";

function load<T>(k: string, d: T): T {
  try { const v = localStorage.getItem(k); return v === null ? d : (JSON.parse(v) as T); } catch { return d; }
}
function save(k: string, v: unknown) {
  try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* bez úložiště */ }
}

/** Poslední výsledek testu použitelnosti profilu (API ho neukládá; platí na tomto počítači). */
export interface TestMemo { verdict: string; text: string; ok: number; warn: number; fail: number; at: string }

interface SettingsState {
  open: boolean;
  section: Section;
  view: CtlView;
  id: string | null;
  /** Výchozí regulátor pro nové smyčky (zatím jen lokálně; API pro volbu výchozího nemá). */
  defaultCtl: string;
  tests: Record<string, TestMemo>;
  openSettings: (section?: Section) => void;
  close: () => void;
  setSection: (s: Section) => void;
  go: (view: CtlView, id?: string | null) => void;
  setDefault: (id: string) => void;
  putTest: (id: string, t: TestMemo) => void;
}

export const useSettingsUi = create<SettingsState>((set) => ({
  open: false, section: "controllers", view: "library", id: null,
  defaultCtl: load("pid.defctl", "pcs7_pidconl"),
  tests: load<Record<string, TestMemo>>("pid.ctltests", {}),
  openSettings: (section) => set((s) => ({ open: true, section: section ?? s.section })),
  close: () => set({ open: false }),
  setSection: (section) => set({ section, view: "library" }),
  go: (view, id) => set((s) => ({ view, id: id === undefined ? s.id : id })),
  setDefault: (defaultCtl) => { save("pid.defctl", defaultCtl); set({ defaultCtl }); },
  putTest: (id, t) => set((s) => { const tests = { ...s.tests, [id]: t }; save("pid.ctltests", tests); return { tests }; }),
}));

// Přepnutí záložky / podzáložky (i z jiného místa, např. průvodce) zavře Nastavení.
useUi.subscribe((s, p) => { if (s.tab !== p.tab || s.dataSub !== p.dataSub) useSettingsUi.getState().close(); });
