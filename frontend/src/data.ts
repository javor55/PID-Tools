// Dotazy a změny pracovního prostoru (TanStack Query). Po změně dat / sloupců se zneplatní vše o prostoru.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { affected, type Group, invalidateGroups } from "./queryKeys";
import { rawRequest, request, type WorkspaceInfo } from "./api/client";
import type { components } from "./api/schema";
import { toastError } from "./components/Toasts";
import { useUi } from "./store";

export type Quality = components["schemas"]["Quality"];
export type LoopMode = components["schemas"]["LoopMode"];
export type Columns = components["schemas"]["Columns"];

export function useWs() {
  const wid = useUi((s) => s.wid);
  return useQuery({
    queryKey: ["ws", wid], enabled: !!wid,
    queryFn: () => request<WorkspaceInfo>("GET", `/workspaces/${wid}`),
  });
}

export function useWsQuery<T>(part: string, path: string, enabled = true) {
  const wid = useUi((s) => s.wid);
  const ws = useWs();
  return useQuery({
    queryKey: ["ws", wid, part, ws.data?.pv, ws.data?.mv, ws.data?.n, ws.data?.rng],
    enabled: !!wid && !!ws.data?.has_data && enabled,
    queryFn: () => request<T>("GET", `/workspaces/${wid}${path}`),
  });
}

export function useSettings() {
  const wid = useUi((s) => s.wid);
  return useQuery({
    queryKey: ["ws", wid, "settings"], enabled: !!wid,
    queryFn: () => request<Record<string, unknown>>("GET", `/workspaces/${wid}/settings`),
  });
}

/** Změna prostoru (POST / PUT / PATCH) – po úspěchu znovu načíst dotazy uvedených skupin (bez `groups` vše o prostoru). */
export function useWsMutation<B = unknown>(method: string, path: string, groups?: Group[]) {
  const wid = useUi((s) => s.wid);
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body?: B) => request<WorkspaceInfo>(method, `/workspaces/${wid}${path}`, body),
    onSuccess: () => groups ? invalidateGroups(qc, wid, groups) : qc.invalidateQueries({ queryKey: ["ws", wid] }),
  });
}

export async function uploadFile(wid: string, file: File): Promise<WorkspaceInfo> {
  return rawRequest<WorkspaceInfo>("POST", `/workspaces/${wid}/data/file?name=${encodeURIComponent(file.name)}`,
    await file.arrayBuffer());
}

/**
 * Změna nastavení smyčky: hned v rozhraní (optimisticky), pak PATCH /settings a znovu načíst dotazy dotčené změnou.
 * Při chybě se vrátí předchozí hodnoty měněných klíčů, ukáže se toast a chyba se znovu vyhodí.
 */
export function usePatchSettings() {
  const wid = useUi((s) => s.wid);
  const qc = useQueryClient();
  return async (patch: Record<string, unknown>) => {
    const key = ["ws", wid, "settings"];
    const prev = qc.getQueryData<Record<string, unknown>>(key);
    qc.setQueryData<Record<string, unknown>>(key, (old) => ({ ...(old ?? {}), ...patch }));
    try {
      await request("PATCH", `/workspaces/${wid}/settings`, patch);
    } catch (e) {
      // Vrátit jen měněné klíče (souběžná změna jiného klíče zůstane).
      qc.setQueryData<Record<string, unknown>>(key, (cur) => {
        const out = { ...(cur ?? {}) };
        for (const k of Object.keys(patch)) {
          if (prev && k in prev) out[k] = prev[k]; else delete out[k];
        }
        return out;
      });
      toastError(e);
      throw e;
    }
    // jen dotazy, kterých se změna týká (tabulka v queryKeys.ts)
    await invalidateGroups(qc, wid, affected(Object.keys(patch)));
  };
}
