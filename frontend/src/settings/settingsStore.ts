// Stav obrazovky Nastavení (celostránkový pohled z hlavičky) a knihovny regulátorů; jen v prohlížeči.
import { create } from "zustand";
import { useUi } from "../store";
import { patchSettings } from "./appSettings";

export const SECTIONS = ["general", "appearance", "charts", "diagnostics", "defaults", "journal", "report", "connections", "io", "controllers"] as const;
export type Section = (typeof SECTIONS)[number];
export type CtlView = "library" | "editor" | "test";

/** Poslední výsledek testu použitelnosti profilu (ukládá se v nastavení aplikace na serveru). */
export interface TestMemo { verdict: string; text: string; ok: number; warn: number; fail: number; at: string }

interface SettingsState {
  open: boolean;
  section: Section;
  view: CtlView;
  id: string | null;
  /** Výchozí regulátor pro nové smyčky a poslední testy: zrcadlo nastavení aplikace ze serveru (appSettings.ts). */
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
  defaultCtl: "pcs7_pidconl",
  tests: {},
  openSettings: (section) => set((s) => ({ open: true, section: section ?? s.section })),
  close: () => set({ open: false }),
  setSection: (section) => set({ section, view: "library" }),
  go: (view, id) => set((s) => ({ view, id: id === undefined ? s.id : id })),
  setDefault: (defaultCtl) => { set({ defaultCtl }); void patchSettings((n) => { n.defaults.controller = defaultCtl; }).catch(() => undefined); },
  putTest: (id, t) => {
    set((s) => ({ tests: { ...s.tests, [id]: t } }));
    void patchSettings((n) => { n.controller_tests[id] = t; }).catch(() => undefined);
  },
}));

// Přepnutí záložky / podzáložky (i z jiného místa, např. průvodce) zavře Nastavení.
useUi.subscribe((s, p) => { if (s.tab !== p.tab || s.dataSub !== p.dataSub) useSettingsUi.getState().close(); });

// „Otevřít v knihovně“ z karty Regulátor smyčky (Ladění): CustomEvent("pid:open-settings", {detail: {section, id}}).
if (typeof window !== "undefined") {
  window.addEventListener("pid:open-settings", (e) => {
    const d = (e as CustomEvent<{ section?: Section; id?: string | null }>).detail ?? {};
    const st = useSettingsUi.getState();
    st.openSettings(d.section ?? "controllers");
    if (d.id) st.go("library", d.id);
  });
}
