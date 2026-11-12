// Nastavení aplikace ze serveru (`/app-settings`): dotaz, uložení změny, jednorázový převod starých hodnot z localStorage
// (výchozí regulátor, poslední testy) a promítnutí do rozhraní (jazyk, vzhled, velikost písma, výška grafů).
import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { bytes, rawRequest, request } from "../api/client";
import type { components } from "../api/schema";
import { queryClient } from "../queryClient";
import { useUi } from "../store";
import { useSettingsUi } from "./settingsStore";

export type AppSettings = components["schemas"]["AppSettings"];
export type ThresholdItem = components["schemas"]["ThresholdInfo"];

const KEY = ["app-settings"];

export const useAppSettings = () =>
  useQuery({ queryKey: KEY, queryFn: () => request<AppSettings>("GET", "/app-settings"), staleTime: Infinity });

export const useThresholdSchema = () =>
  useQuery({ queryKey: ["app-settings", "schema"], queryFn: () => request<ThresholdItem[]>("GET", "/app-settings/diagnostics-schema"), staleTime: Infinity });

function mirror(s: AppSettings) {
  useSettingsUi.setState({ defaultCtl: s.defaults.controller, tests: s.controller_tests });
}

export function setSettings(s: AppSettings) {
  queryClient.setQueryData(KEY, s);
  mirror(s);
}

async function current(): Promise<AppSettings> {
  return queryClient.getQueryData<AppSettings>(KEY) ?? (await queryClient.fetchQuery({ queryKey: KEY, queryFn: () => request<AppSettings>("GET", "/app-settings") }));
}

let chain: Promise<unknown> = Promise.resolve();
let pending = 0;

/**
 * Změní nastavení: hned v rozhraní (vždy nad posledním stavem), na server jde PUT po jednom v pořadí; odpověď se použije,
 * až když už nečeká další změna (jinak by starší odpověď přepsala novější hodnoty). Při chybě se stav načte znovu ze serveru.
 */
export function patchSettings(fn: (s: AppSettings) => void): Promise<AppSettings> {
  pending++;
  const run = async () => {
    const cur = await current();
    const next = structuredClone(cur);
    fn(next);
    setSettings(next);
    return next;
  };
  const staged = run();
  const done = chain.then(async () => {
    const next = await staged;
    try {
      const saved = await request<AppSettings>("PUT", "/app-settings", next);
      if (pending === 1) setSettings(saved);
      return saved;
    } catch (e) {
      await queryClient.invalidateQueries({ queryKey: KEY });
      throw e;
    } finally {
      pending--;
    }
  });
  chain = done.catch(() => undefined);
  return done;
}

export const resetSettings = async () => setSettings(await request<AppSettings>("DELETE", "/app-settings"));
export const importSettings = async (f: File) => setSettings(await rawRequest<AppSettings>("POST", "/app-settings/import", await f.arrayBuffer()));
export const exportSettings = () => bytes("GET", "/app-settings/export");
export const uploadLogo = async (f: File) =>
  setSettings(await rawRequest<AppSettings>("POST", `/app-settings/logo?name=${encodeURIComponent(f.name)}`, await f.arrayBuffer()));
export const removeLogo = async () => setSettings(await request<AppSettings>("DELETE", "/app-settings/logo"));

const lsGet = (k: string): unknown => { try { const v = localStorage.getItem(k); return v === null ? null : JSON.parse(v); } catch { return null; } };
const lsDrop = (k: string) => { try { localStorage.removeItem(k); } catch { /* bez úložiště */ } };

/**
 * Jednou za spuštění: nastavení ze serveru → rozhraní (jazyk, vzhled, písmo, výška grafů) a zpět změna jazyka / vzhledu
 * v rozhraní → server. Starý výchozí regulátor a poslední testy z localStorage se jednou přenesou na server.
 */
export function useAppSettingsSync() {
  const s = useAppSettings().data;
  const migrated = useRef(false);
  useEffect(() => {
    if (!s) return;
    mirror(s);
    const ui = useUi.getState();
    if (s.appearance.language && s.appearance.language !== ui.lang) ui.setLang(s.appearance.language);
    if (s.appearance.theme && s.appearance.theme !== ui.theme) ui.setTheme(s.appearance.theme);
    document.documentElement.dataset.font = s.appearance.font_size;
    if (ui.chartH !== s.charts.height) useUi.setState({ chartH: s.charts.height });
    if (migrated.current) return;
    migrated.current = true;
    const ctl = lsGet("pid.defctl") as string | null;
    const tests = lsGet("pid.ctltests") as AppSettings["controller_tests"] | null;
    if (ctl || tests) {
      void patchSettings((n) => {
        if (typeof ctl === "string" && n.defaults.controller === "pcs7_pidconl") n.defaults.controller = ctl;
        for (const [id, t] of Object.entries(tests ?? {})) if (!n.controller_tests[id]) n.controller_tests[id] = t;
      }).then(() => { lsDrop("pid.defctl"); lsDrop("pid.ctltests"); }).catch(() => undefined);
    }
    if (!s.appearance.language || !s.appearance.theme) {
      void patchSettings((n) => { n.appearance.language ||= ui.lang; n.appearance.theme ||= ui.theme; }).catch(() => undefined);
    }
  }, [s]);
  useEffect(() => useUi.subscribe((st, prev) => {
    if (st.lang === prev.lang && st.theme === prev.theme) return;
    const cur = queryClient.getQueryData<AppSettings>(KEY);
    if (!cur || (cur.appearance.language === st.lang && cur.appearance.theme === st.theme)) return;
    void patchSettings((n) => { n.appearance.language = st.lang; n.appearance.theme = st.theme; }).catch(() => undefined);
  }), []);
}
