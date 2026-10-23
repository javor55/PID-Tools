// Klient API (pidtools.api). Token: desktop ho předá v adrese (#token=…) nebo jako window.__PID__.token;
// uloží se do sessionStorage. Jazyk odpovědí podle zvoleného jazyka (Accept-Language).
import type { components } from "./schema";

export type JobInfo = components["schemas"]["JobInfo"];
export type WorkspaceInfo = components["schemas"]["WorkspaceInfo"];
export type Health = components["schemas"]["Health"];

declare global {
  interface Window { __PID__?: { token?: string; api?: string } }
}

const KEY = "pidtools.token";

function readToken(): string | null {
  const m = /(?:^|[#&])token=([^&]+)/.exec(window.location.hash);
  if (m) {
    try { sessionStorage.setItem(KEY, decodeURIComponent(m[1])); } catch { /* bez úložiště */ }
    history.replaceState(null, "", window.location.pathname + window.location.search);
    return decodeURIComponent(m[1]);
  }
  if (window.__PID__?.token) return window.__PID__.token;
  try { return sessionStorage.getItem(KEY); } catch { return null; }
}

let token: string | null = typeof window !== "undefined" ? readToken() : null;
let lang = "en";
const base = (typeof window !== "undefined" && window.__PID__?.api) || "";

export function setLang(l: string) { lang = l; }
export function setToken(t: string | null) { token = t; }

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

function headers(extra: Record<string, string> = {}): Record<string, string> {
  const h: Record<string, string> = { "Accept-Language": lang, ...extra };
  if (token) h.Authorization = `Bearer ${token}`;
  return h;
}

export async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const init: RequestInit = { method, headers: headers(body !== undefined ? { "Content-Type": "application/json" } : {}) };
  if (body !== undefined) init.body = JSON.stringify(body);
  const r = await fetch(base + path, init);
  if (!r.ok) {
    let msg = r.statusText;
    try { const j = await r.json(); msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail); } catch { /* text */ }
    throw new ApiError(r.status, msg);
  }
  if (r.status === 204) return undefined as T;
  const ct = r.headers.get("content-type") ?? "";
  return (ct.includes("json") ? r.json() : r.arrayBuffer()) as Promise<T>;
}

/** Požadavek s binárním tělem (soubor) – odpověď JSON. */
export async function rawRequest<T>(method: string, path: string, body: ArrayBuffer): Promise<T> {
  const r = await fetch(base + path, { method, headers: headers({ "Content-Type": "application/octet-stream" }), body });
  if (!r.ok) {
    let msg = r.statusText;
    try { const j = await r.json(); msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail); } catch { /* text */ }
    throw new ApiError(r.status, msg);
  }
  return r.json() as Promise<T>;
}

/** Binární odpověď (signály, průběhy); s tělem jako POST JSON. */
export async function binary(path: string, body?: unknown): Promise<ArrayBuffer> {
  const r = await fetch(base + path, body === undefined ? { headers: headers() }
    : { method: "POST", headers: headers({ "Content-Type": "application/json" }), body: JSON.stringify(body) });
  if (!r.ok) throw new ApiError(r.status, r.statusText);
  return r.arrayBuffer();
}

export const api = {
  health: () => request<Health>("GET", "/health"),
  texts: (l: string) => request<Record<string, string>>("GET", `/i18n/${l}`),
  createWorkspace: () => request<WorkspaceInfo>("POST", "/workspaces"),
  workspace: (wid: string) => request<WorkspaceInfo>("GET", `/workspaces/${wid}`),
  job: (jid: string) => request<JobInfo>("GET", `/jobs/${jid}`),
  cancelJob: (jid: string) => request<JobInfo>("POST", `/jobs/${jid}/cancel`),
};

/** Průběh úlohy jako server-sent events (fetch, aby šel poslat token v hlavičce). Vrací funkci pro ukončení. */
export function watchJob(jid: string, onInfo: (j: JobInfo) => void): () => void {
  const ctl = new AbortController();
  (async () => {
    const r = await fetch(`${base}/jobs/${jid}/events`, { headers: headers(), signal: ctl.signal });
    if (!r.ok || !r.body) return;
    const reader = r.body.pipeThrough(new TextDecoderStream()).getReader();
    let buf = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += value;
      let i: number;
      while ((i = buf.indexOf("\n\n")) >= 0) {
        const ev = buf.slice(0, i);
        buf = buf.slice(i + 2);
        const line = ev.split("\n").find((l) => l.startsWith("data: "));
        if (line) onInfo(JSON.parse(line.slice(6)) as JobInfo);
      }
    }
  })().catch(() => { /* zrušeno nebo spojení přerušeno */ });
  return () => ctl.abort();
}
