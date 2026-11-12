// Dotazy a změny obrazovky Zdroje a smyčky (API zdrojů a mapování smyček z E3). Po každé změně se zneplatní vše o prostoru
// (["ws", wid, …]) – záložky Model, Ladění … pracují se smyčkami, které se změnou mohly přeskládat.
import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, rawRequest, request } from "../../../api/client";
import type { components } from "../../../api/schema";
import { useUi } from "../../../store";
import type { LoopMapping, SourceInfo } from "./geometry";

export type Sources = components["schemas"]["Sources"];
export type TimeGrid = components["schemas"]["TimeGridBody"];
export type SourcePatch = components["schemas"]["SourcePatch"];
export type Suggestions = components["schemas"]["Suggestions"];
export type TrendSeries = components["schemas"]["TrendSeries"];
type Trend = components["schemas"]["Trend"];
type Loops = components["schemas"]["Loops"];

export function useSources() {
  const wid = useUi((s) => s.wid);
  return useQuery({
    queryKey: ["ws", wid, "sources"], enabled: !!wid,
    queryFn: () => request<Sources>("GET", `/workspaces/${wid}/sources`),
  });
}

export function useMappings() {
  const wid = useUi((s) => s.wid);
  return useQuery({
    queryKey: ["ws", wid, "mappings"], enabled: !!wid,
    queryFn: () => request<LoopMapping[]>("GET", `/workspaces/${wid}/loops/mappings`),
  });
}

/** Aktivní smyčka (index od 0) projektu. */
export function useActiveLoop() {
  const wid = useUi((s) => s.wid);
  return useQuery({
    queryKey: ["ws", wid, "loops-active"], enabled: !!wid,
    queryFn: () => request<Loops>("GET", `/workspaces/${wid}/loops`),
  }).data?.active ?? 0;
}

/** Zředěný průběh sloupců po zdrojích (`n` skupin = minigrafy); klíč `zdroj:sloupec` → řada. */
export function useSparks(sources: readonly SourceInfo[], n = 24) {
  const wid = useUi((s) => s.wid);
  const qs = useQueries({
    queries: sources.map((s) => ({
      queryKey: ["ws", wid, "spark", s.id, s.columns.join("\u001f"), s.start, s.end, n],
      enabled: !!wid && s.loaded && s.columns.length > 0,
      staleTime: 60_000,
      retry: false,
      queryFn: async () => {
        const names = s.columns.map((c) => `names=${encodeURIComponent(`${s.id}:${c}`)}`).join("&");
        const r = await request<Trend>("GET", `/workspaces/${wid}/signals/trend?${names}&n=${n}`);
        return Object.fromEntries(r.series.map((x) => [x.column, x])) as Record<string, TrendSeries>;
      },
    })),
  });
  return Object.fromEntries(sources.map((s, i) => [s.id, qs[i]?.data])) as Record<string, Record<string, TrendSeries> | undefined>;
}

export const errText = (e: unknown) => (e instanceof ApiError ? e.message : String(e));

/** Změna prostoru (JSON): po úspěchu se zneplatní všechny dotazy prostoru. Vrací odpověď. */
export function useAct() {
  const wid = useUi((s) => s.wid);
  const qc = useQueryClient();
  return async <T = unknown>(method: string, path: string, body?: unknown): Promise<T> => {
    try {
      return await request<T>(method, `/workspaces/${wid}${path}`, body);
    } finally {
      await qc.invalidateQueries({ queryKey: ["ws", wid] });
    }
  };
}

/** Nahrání souboru jako nový zdroj (`POST /sources`, tělo = bajty souboru). */
export function useAddSource() {
  const wid = useUi((s) => s.wid);
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (f: File) => rawRequest<SourceInfo>("POST", `/workspaces/${wid}/sources?name=${encodeURIComponent(f.name)}`,
      await f.arrayBuffer()),
    onSettled: () => qc.invalidateQueries({ queryKey: ["ws", wid] }),
  });
}

/** CSV s mapováním smyček (`POST /loops/import`, tělo = text CSV); `apply` smyčky rovnou přidá. */
export async function importCsv(wid: string, text: string, apply: boolean): Promise<Suggestions> {
  const buf = new TextEncoder().encode(text);
  return rawRequest<Suggestions>("POST", `/workspaces/${wid}/loops/import?apply=${apply}`, buf.buffer as ArrayBuffer);
}
