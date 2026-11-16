// Otevření projektu (uložený soubor / poklep v okně desktopu). Vyčleněno ze záložky Projekt, aby ho App.tsx mohla
// importovat bez načtení celé líné záložky (TICKET-019).
import { useQueryClient, type QueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { create } from "zustand";
import { ApiError, bytes, rawRequest } from "../../api/client";
import { useT } from "../../i18n";
import { useUi } from "../../store";
import { useReport } from "./state";

const PENDING_EVENT = "pidtools:pending-open";      // okno desktopu ho vyvolá po uložení souboru k otevření

interface ProjMsg { err: boolean; text: string }
export const useProjMsg = create<{ msg: ProjMsg | null; set: (m: ProjMsg | null) => void }>((set) => ({ msg: null, set: (msg) => set({ msg }) }));

/** Nahraje projekt (bajty souboru) do prostoru a zneplatní jeho dotazy. */
export async function openProject(wid: string, raw: ArrayBuffer, qc: QueryClient, T: (k: string) => string) {
  useProjMsg.getState().set(null);
  try {
    await rawRequest("PUT", `/workspaces/${wid}/project`, raw);
    await qc.invalidateQueries({ queryKey: ["ws", wid] });
    useReport.getState().set({ html: null, err: null });
    useProjMsg.getState().set({ err: false, text: T("ui_proj_opened") });
  } catch (e) {
    useProjMsg.getState().set({ err: true, text: e instanceof ApiError ? T(e.message) : String(e) });
  }
}

/** Projekt otevřený poklepem na soubor v okně desktopu: při startu a po události od okna se vyzvedne z `/pending-open`. */
export function usePendingOpen() {
  const T = useT();
  const wid = useUi((s) => s.wid);
  const qc = useQueryClient();
  useEffect(() => {
    if (!wid) return;
    let busy = false;
    const check = async () => {
      if (busy) return;
      busy = true;
      try {
        const raw = await bytes("GET", "/pending-open");
        if (raw.byteLength > 0) { useUi.getState().setTab("project"); await openProject(wid, raw, qc, T); }
      } catch { /* bez čekajícího souboru / nedostupné (týmový režim) */ } finally { busy = false; }
    };
    void check();
    window.addEventListener(PENDING_EVENT, check);
    return () => window.removeEventListener(PENDING_EVENT, check);
  }, [wid, qc, T]);
}
