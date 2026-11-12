// Trendy – dotazy na API: zdroje a smyčky (strom signálů), zředěné průběhy z `/signals/trend` a stav po pracovním prostoru.
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { request } from "../../../api/client";
import type { components } from "../../../api/schema";
import { useUi } from "../../../store";
import { describeSignals, type LoopLite, type SigInfo } from "./model";

export type SourcesInfo = components["schemas"]["Sources"];
export type TrendOut = components["schemas"]["Trend"];
export type LoopMapping = components["schemas"]["LoopMapping"];

export function useTrendSources() {
  const wid = useUi((s) => s.wid);
  return useQuery({
    queryKey: ["ws", wid, "trends", "sources"], enabled: !!wid,
    queryFn: () => request<SourcesInfo>("GET", `/workspaces/${wid}/sources`),
  });
}

export function useTrendLoops() {
  const wid = useUi((s) => s.wid);
  return useQuery({
    queryKey: ["ws", wid, "trends", "loops"], enabled: !!wid,
    queryFn: () => request<LoopMapping[]>("GET", `/workspaces/${wid}/loops/mappings`),
  });
}

export interface TrendCatalog {
  sigs: SigInfo[];
  info: Map<string, SigInfo>;
  origin: string | null;
  full: [number, number] | null;          // společný úsek zdrojů (jinak sjednocení)
  isCommon: boolean;
  ready: boolean;
}

/** Katalog signálů: všechny sloupce všech zdrojů se smyčkou, rolí, barvou a veličinou; rozsah společné osy. */
export function useTrendCatalog(): TrendCatalog {
  const src = useTrendSources().data;
  const lp = useTrendLoops().data;
  return useMemo(() => {
    const sources = (src?.sources ?? []).filter((s) => s.loaded !== false).map((s) => ({ id: s.id, name: s.name, columns: s.columns ?? [] }));
    const loops: LoopLite[] = (lp ?? []).map((m, i) => ({
      index: m.index ?? i, tag: m.tag || `#${i + 1}`,
      roles: { pv: m.roles?.pv, sp: m.roles?.sp, mv: m.roles?.mv, pos: m.roles?.pos, mode: m.roles?.mode, dv: m.roles?.dv ?? [] },
    }));
    const sigs = describeSignals(sources, loops);
    const spans = (src?.sources ?? []).filter((s) => s.start != null && s.end != null);
    let full: [number, number] | null = null, isCommon = false;
    if (src?.common) { full = [src.common.start, src.common.end]; isCommon = true; }
    else if (spans.length) full = [Math.min(...spans.map((s) => s.start!)), Math.max(...spans.map((s) => s.end!))];
    return { sigs, info: new Map(sigs.map((s) => [s.ref, s])), origin: src?.origin ?? null, full, isCommon, ready: !!src && !!lp };
  }, [src, lp]);
}

/** Index aktivní smyčky projektu (pro volbu „jen aktivní smyčka“). */
export function useActiveLoop() {
  const wid = useUi((s) => s.wid);
  return useQuery({
    queryKey: ["ws", wid, "trends", "active"], enabled: !!wid,
    queryFn: () => request<components["schemas"]["Loops"]>("GET", `/workspaces/${wid}/loops`),
  }).data?.active ?? null;
}

/** Zředěné průběhy v úseku [a, b] (zředění min / max na serveru), volitelně se statistikou a hodnotami v časech `at`. */
export function useTrendSeries(refs: string[], a: number | null, b: number | null, n: number, at: number[] = [], enabled = true) {
  const wid = useUi((s) => s.wid);
  const key = [...refs].sort().join("|");
  return useQuery({
    queryKey: ["ws", wid, "trends", "series", key, a, b, n, at.join(",")],
    enabled: !!wid && enabled && refs.length > 0 && a !== null && b !== null && b > a,
    placeholderData: keepPreviousData, staleTime: 30_000, retry: false,
    queryFn: () => {
      const q = new URLSearchParams();
      refs.forEach((r) => q.append("names", r));
      q.set("a", String(a)); q.set("b", String(b)); q.set("n", String(n));
      at.forEach((x) => q.append("at", String(x)));
      return request<TrendOut>("GET", `/workspaces/${wid}/signals/trend?${q.toString()}`);
    },
  });
}
