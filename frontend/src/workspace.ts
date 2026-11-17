// Životní cyklus pracovního prostoru: založení při startu a obnova po ztrátě (smazání na serveru, restart sidecaru).
import { useEffect } from "react";
import { api, ApiError } from "./api/client";
import { toastError, useToasts } from "./components/Toasts";
import { queryClient, setWorkspaceLostHandler } from "./queryClient";
import { useUi } from "./store";

/** Text, kterým server hlásí neexistující prostor (404 z `project()` v API). */
export const WORKSPACE_NOT_FOUND = "workspace not found";

/** Při startu: uložené ID z minula se ověří (404 → nový prostor), bez ID se založí nový. */
export function useWorkspace() {
  const { wid, setWid } = useUi();
  useEffect(() => {
    if (wid) {          // uložené ID z minula – po restartu serveru už neplatí → nový prostor
      api.workspace(wid).catch((e) => { if (e instanceof ApiError && e.status === 404) setWid(null); });
      return;
    }
    api.createWorkspace().then((w) => setWid(w.id)).catch(() => setWid(null));
  }, [wid, setWid]);
}

/** Text mimo komponentu: z mezipaměti textů aktuálního jazyka (načtou se při startu aplikace). */
const text = (key: string) =>
  queryClient.getQueryData<Record<string, string>>(["i18n", useUi.getState().lang])?.[key] ?? key;

let recovering: Promise<void> | null = null;

async function recover(): Promise<void> {
  const old = useUi.getState().wid;
  if (old) {            // souběh / pozdní chyba mutace: pokud aktuální prostor existuje, není co obnovovat
    try { await api.workspace(old); return; } catch (e) { if (!(e instanceof ApiError && e.status === 404)) throw e; }
  }
  const w = await api.createWorkspace();
  const ui = useUi.getState();
  ui.setWid(w.id);
  if (old) queryClient.removeQueries({ queryKey: ["ws", old] });
  ui.setDataSub("sources");              // nový prostor nemá data → úvodní obrazovka s nabídkou obnovy
  await Promise.all([queryClient.invalidateQueries({ queryKey: ["recovery"] }),
                     queryClient.invalidateQueries({ queryKey: ["recent"] })]);
  // Druh „err“: zůstane do zavření (ne 4 s), uživatel musí vědět, že rozdělaná práce je jen v záchranné kopii.
  useToasts.getState().push({ kind: "err", text: text("ws_lost") });
}

/**
 * Pracovní prostor na serveru zmizel: založí nový, zahodí dotazy starého a ukáže úvodní obrazovku s nabídkou obnovy.
 * Souběžná volání (více dotazů vrátí 404 najednou) sdílejí jeden Promise, prostor se tedy založí jen jednou.
 */
export function onWorkspaceLost(): Promise<void> {
  if (!recovering) {
    recovering = recover().catch((e) => { toastError(e); useUi.getState().setWid(null); })
      .finally(() => { recovering = null; });
  }
  return recovering;
}

setWorkspaceLostHandler(() => { void onWorkspaceLost(); });
