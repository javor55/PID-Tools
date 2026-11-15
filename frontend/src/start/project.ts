// Stav uložení projektu, automatické ukládání (záchranná kopie na serveru) a akce „Nový“ projekt.
import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { create } from "zustand";
import { api, bytes, request } from "../api/client";
import type { components } from "../api/schema";
import { toastError } from "../components/Toasts";
import { queryClient } from "../queryClient";
import { useSettingsUi } from "../settings/settingsStore";
import { useAppSettings } from "../settings/appSettings";
import { usePublic } from "../deploy";
import { useUi } from "../store";

export type SaveState = components["schemas"]["SaveState"];
export type RecoveryInfo = components["schemas"]["RecoveryInfo"];
export type RecentItem = components["schemas"]["RecentItem"];

/** Prostor je „v klidu“, když se po tuto dobu nezměnil počet změn (rev); teprve pak se zapíše záchranná kopie. */
export const IDLE_MS = 8000;

export function useSaveState() {
  const wid = useUi((s) => s.wid);
  return useQuery({
    queryKey: ["ws", wid, "save-state"], enabled: !!wid, refetchInterval: 5000,
    queryFn: () => request<SaveState>("GET", `/workspaces/${wid}/save-state`),
  });
}

/** Čas posledního uložení (ruční nebo záchranná kopie), epocha v sekundách; null = ještě nikdy. */
export const lastSaved = (st: SaveState | undefined) => (st ? Math.max(st.saved_at ?? 0, st.autosaved_at ?? 0) || null : null);

/** Záchranná kopie: po změnách a v klidu (nejvýš jednou za zvolený počet minut; 0 = vypnuto) zapíše projekt na server. */
export function useAutosave() {
  const wid = useUi((s) => s.wid);
  const pub = usePublic();                    // veřejný režim: server nic neukládá, projekt se ukládá do souboru
  const st = useSaveState().data;
  const minutes = useAppSettings().data?.general.autosave_min ?? 1;
  const ref = useRef({ st, minutes, rev: -1, since: 0, busy: false });
  useEffect(() => { ref.current.st = st; ref.current.minutes = minutes; });
  useEffect(() => {
    if (!wid || pub) return;
    const tick = async () => {
      const r = ref.current;
      const s = r.st;
      if (!s) return;
      if (s.rev !== r.rev) { r.rev = s.rev; r.since = Date.now(); }
      if (!r.minutes || !s.has_data || !s.autosave_pending || r.busy) return;
      if (Date.now() - r.since < IDLE_MS || Date.now() - (s.autosaved_at ?? 0) * 1000 < r.minutes * 60_000) return;
      r.busy = true;
      try {
        const n = await request<SaveState>("POST", `/workspaces/${wid}/autosave`);
        queryClient.setQueryData(["ws", wid, "save-state"], n);
      } catch { /* příště */ } finally { r.busy = false; }
    };
    const t = window.setInterval(() => void tick(), 2000);
    return () => window.clearInterval(t);
  }, [wid, pub]);
}

export const useRecovery = () =>
  useQuery({ queryKey: ["recovery"], queryFn: () => request<RecoveryInfo>("GET", "/autosave/latest"), staleTime: Infinity });

export const useRecent = () => useQuery({ queryKey: ["recent"], queryFn: () => request<RecentItem[]>("GET", "/recent") });

/** Nový prázdný projekt: nový pracovní prostor (výchozí hodnoty z nastavení), starý se zahodí, záchranná kopie smaže. */
export async function newProject(): Promise<void> {
  const ui = useUi.getState();
  const old = ui.wid;
  await request("DELETE", "/autosave").catch(() => undefined);
  const w = await api.createWorkspace();
  ui.setWid(w.id);
  if (old) {
    queryClient.removeQueries({ queryKey: ["ws", old] });
    await request("DELETE", `/workspaces/${old}`).catch(() => undefined);
  }
  ui.setDataSub("sources");
  useSettingsUi.getState().close();
  void queryClient.invalidateQueries({ queryKey: ["recovery"] });
  void queryClient.invalidateQueries({ queryKey: ["recent"] });
}

/** Přípona souborů projektu: výchozí `.pidproj`, otevřít jde i starší `.json` (obsah je stejný JSON). */
export const PROJECT_EXT = ".pidproj";

/** Stažení souboru v prohlížeči (skrytý odkaz na Blob). */
export function saveAs(name: string, data: BlobPart, type: string) {
  const a = document.createElement("a");
  const url = URL.createObjectURL(new Blob([data], { type }));
  a.href = url; a.download = name;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10000);
}

/** Volba „uložit i s daty“ (záložka Projekt); sdílí ji tlačítko v záložce i zkratka Ctrl+S. */
export const useSaveOpts = create<{ withData: boolean; setWithData: (v: boolean) => void }>((set) => ({
  withData: true, setWithData: (withData) => set({ withData }),
}));

/** Základ názvu souboru: značka smyčky (nebo „pidtools“) + dnešní datum. */
export function projectBaseName(tag: unknown): string {
  const base = (String(tag ?? "") || "pidtools").replace(/[^\w.-]+/gu, "_").replace(/^_+|_+$/g, "").slice(0, 60) || "pidtools";
  return `${base}_${new Date().toISOString().slice(0, 10)}`;
}

/**
 * Uloží projekt do souboru `<základ>_projekt.pidproj` (stažení v prohlížeči; GET /project označí prostor jako uložený).
 * Nepředané volby se vezmou ze stavu: prostor z `useUi`, „s daty“ z `useSaveOpts`, základ názvu z nastavení smyčky.
 * Chybu předává volajícímu (záložka Projekt ji píše do svého hlášení, zkratka a hlavička toastem).
 */
export async function saveProject(opts: { wid?: string | null; withData?: boolean; base?: string } = {}): Promise<boolean> {
  const wid = opts.wid ?? useUi.getState().wid;
  if (!wid) return false;
  const withData = opts.withData ?? useSaveOpts.getState().withData;
  const base = opts.base ?? projectBaseName(queryClient.getQueryData<Record<string, unknown>>(["ws", wid, "settings"])?.loop_tag);
  saveAs(`${base}_projekt${PROJECT_EXT}`, await bytes("GET", `/workspaces/${wid}/project?data=${withData}`), "application/json");
  await queryClient.invalidateQueries({ queryKey: ["ws", wid, "save-state"] });
  return true;
}

/** Uložení z hlavičky a ze zkratky: chyba jde do toastu. */
export async function saveProjectToast(): Promise<void> {
  try { await saveProject(); } catch (e) { toastError(e); }
}

/** Přepnutí aktivní smyčky (výběr v hlavičce i zkratky Alt+↑ / Alt+↓): zapíše na server a zneplatní dotazy prostoru. */
export async function pickLoop(index: number): Promise<void> {
  const wid = useUi.getState().wid;
  if (!wid) return;
  await request("PUT", `/workspaces/${wid}/loops/active`, { index });
  await queryClient.invalidateQueries({ queryKey: ["ws", wid] });
}
