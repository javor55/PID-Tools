// Stav uložení projektu, automatické ukládání (záchranná kopie na serveru) a akce „Nový“ projekt.
import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { api, request } from "../api/client";
import type { components } from "../api/schema";
import { queryClient } from "../queryClient";
import { useSettingsUi } from "../settings/settingsStore";
import { useAppSettings } from "../settings/appSettings";
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
  const st = useSaveState().data;
  const minutes = useAppSettings().data?.general.autosave_min ?? 1;
  const ref = useRef({ st, minutes, rev: -1, since: 0, busy: false });
  useEffect(() => { ref.current.st = st; ref.current.minutes = minutes; });
  useEffect(() => {
    if (!wid) return;
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
  }, [wid]);
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
