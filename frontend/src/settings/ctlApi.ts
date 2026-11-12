// API knihovny regulátorů (/controllers…): typy ze schématu a dotazy TanStack Query.
import { useQuery } from "@tanstack/react-query";
import { bytes, request } from "../api/client";
import type { components } from "../api/schema";

type S = components["schemas"];
export type Summary = S["ControllerSummary"];
export type Profile = S["ControllerProfile"];
export type Param = S["ControllerParam"];
export type Part = S["PartInfo"];
export type Protocol = S["CheckProtocol"];
export type CompileResult = S["CompileResult"];
export type MapResult = S["MapResult"];

export const ctlApi = {
  list: () => request<Summary[]>("GET", "/controllers"),
  get: (id: string) => request<Profile>("GET", `/controllers/${id}`),
  parts: () => request<Part[]>("GET", "/controllers/parts"),
  create: (from_id: string, name?: string) => request<Profile>("POST", "/controllers", { from_id, name }),
  update: (id: string, p: Profile) => request<Profile>("PUT", `/controllers/${id}`, p),
  remove: (id: string) => request<void>("DELETE", `/controllers/${id}`),
  import: (p: Profile) => request<Profile>("POST", "/controllers/import", p),
  exportFile: (id: string) => bytes("GET", `/controllers/${id}/export`),
  test: (id: string) => request<Protocol>("POST", `/controllers/${id}/test`),
  compile: (source: string) => request<CompileResult>("POST", "/controllers/compile", { source, quick: true }),
  map: (id: string, canonical: { Kc: number; Ti: number | null; Td: number; b: number; c: number; N: number | null }) =>
    request<MapResult>("POST", `/controllers/${id}/map`, { canonical }),
};

export const useControllers = () => useQuery({ queryKey: ["ctl"], queryFn: ctlApi.list });
export const useProfile = (id: string | null) =>
  useQuery({ queryKey: ["ctl", id], enabled: !!id, queryFn: () => ctlApi.get(id as string) });
export const useParts = () => useQuery({ queryKey: ["ctl-parts"], queryFn: ctlApi.parts, staleTime: Infinity });

/** Uloží soubor v prohlížeči (export `.pidctrl`, protokol). */
export function saveBlob(data: BlobPart, name: string, type = "application/json") {
  const url = URL.createObjectURL(new Blob([data], { type }));
  const a = document.createElement("a");
  a.href = url; a.download = name;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
