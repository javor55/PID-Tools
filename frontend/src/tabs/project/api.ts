// Dotazy deníku ladění (TanStack Query). Klíče začínají ["ws", wid], takže se zneplatní s celým prostorem.
import { useQuery } from "@tanstack/react-query";
import { bytes, request } from "../../api/client";
import { useUi } from "../../store";
import type { Compare, JournalList, SectionInfo, SnapshotDetail } from "./state";

export function useJournal() {
  const wid = useUi((s) => s.wid);
  return useQuery({ queryKey: ["ws", wid, "journal"], enabled: !!wid, queryFn: () => request<JournalList>("GET", `/workspaces/${wid}/journal`) });
}

export function useSnapshot(sid: string | null) {
  const wid = useUi((s) => s.wid);
  return useQuery({ queryKey: ["ws", wid, "journal", sid], enabled: !!wid && !!sid,
    queryFn: () => request<SnapshotDetail>("GET", `/workspaces/${wid}/journal/${sid}`) });
}

export function useCompare(a: string | null, b: string | null) {
  const wid = useUi((s) => s.wid);
  return useQuery({ queryKey: ["ws", wid, "journal", "cmp", a, b], enabled: !!wid && !!a && !!b,
    queryFn: () => request<Compare>("GET", `/workspaces/${wid}/journal/compare?a=${a}&b=${b}`) });
}

export function useSections(lang: string) {
  const wid = useUi((s) => s.wid);
  return useQuery({ queryKey: ["ws", wid, "report-sections", lang], enabled: !!wid,
    queryFn: () => request<SectionInfo[]>("GET", `/workspaces/${wid}/report/sections?lang=${lang}`) });
}

export async function reportFromSnapshot(wid: string, sid: string, body: unknown, lang: string): Promise<string> {
  return new TextDecoder().decode(await bytes("POST", `/workspaces/${wid}/journal/${sid}/report?lang=${lang}`, body));
}
