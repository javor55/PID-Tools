// Dotazy a změny pracovního prostoru (TanStack Query). Po změně dat / sloupců se zneplatní vše o prostoru.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { rawRequest, request, type WorkspaceInfo } from "./api/client";
import type { components } from "./api/schema";
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

/** Změna prostoru (POST / PUT / PATCH) – po úspěchu znovu načíst vše o prostoru. */
export function useWsMutation<B = unknown>(method: string, path: string) {
  const wid = useUi((s) => s.wid);
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body?: B) => request<WorkspaceInfo>(method, `/workspaces/${wid}${path}`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["ws", wid] }),
  });
}

export async function uploadFile(wid: string, file: File): Promise<WorkspaceInfo> {
  return rawRequest<WorkspaceInfo>("POST", `/workspaces/${wid}/data/file?name=${encodeURIComponent(file.name)}`,
    await file.arrayBuffer());
}
