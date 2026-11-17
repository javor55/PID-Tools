// Společný základ grafů nad prohlížečem záznamu (viewer.js) s daty v paměti – Model › Identifikace (ModelChart) a Diagnostika
// (DiagChart): prostředí (texty, jazyk, vzhled, paleta), sloučení signálů smyčky s ostatními signály záznamu, hodiny a připojení
// modulu k prvku stránky. Obaly si jen složí data (signály, výchozí rozložení, úseky) a předají je sem.
import { useQuery } from "@tanstack/react-query";
import { type RefObject, useCallback, useEffect, useMemo, useRef } from "react";
import { binary } from "../api/client";
import type { components } from "../api/schema";
import { mergePacks, type PackMeta, unframe } from "../api/signals";
import mountViewer, { type ViewerData } from "../legacy/viewer.js";
import PIDViewAn from "../legacy/viewer_an.js";
import "../legacy/viewer.css";
import { useWs } from "../data";
import { decOf, useT, useTexts } from "../i18n";
import { readable, usePalette } from "../lib/palette";
import { useUi } from "../store";

(window as unknown as { PIDViewAn?: unknown }).PIDViewAn ??= PIDViewAn;

export type Pack = { meta: PackMeta; blob: ArrayBuffer };
type Ws = components["schemas"]["WorkspaceInfo"];

/** Mřížka smyčky (PV, MV, SP, poruchy) jako balík signálů; stejný dotaz sdílejí všechny grafy (mezipaměť dotazů). */
export function useGridPack() {
  const wid = useUi((s) => s.wid);
  const ws = useWs().data;
  return useQuery({
    queryKey: ["ws", wid, "grid", ws?.pv, ws?.mv, ws?.sp, ws?.dists, ws?.n], enabled: !!wid && !!ws?.has_data, staleTime: Infinity,
    queryFn: async () => unframe(await binary(`/workspaces/${wid}/signals?source=grid`)),
  });
}

/** Všechny signály záznamu: stejný dotaz jako prohlížeč v Datech (sdílená mezipaměť); ostatní signály lze přidat do grafu. */
export function useRawPack() {
  const wid = useUi((s) => s.wid);
  const ws = useWs().data;
  return useQuery({
    queryKey: ["ws", wid, "rawsignals", ws?.fname, ws?.n, ws?.layout], enabled: !!wid && !!ws?.has_data, staleTime: Infinity,
    queryFn: async () => unframe(await binary(`/workspaces/${wid}/signals`)),
  });
}

/** Texty, jazyk, vzhled a paleta; `col` upraví barvu řady podle čitelnosti na tmavém pozadí. */
export function useViewerEnv() {
  const T = useT();
  const texts = useTexts();
  const lang = useUi((s) => s.lang);
  const dark = useUi((s) => s.theme) === "dark" || document.documentElement.dataset.theme === "dark";
  const pal = usePalette();
  const card = pal.card;
  const col = useCallback((c: string) => (dark ? readable(c, card) : c), [dark, card]);
  return { T, texts, lang, dark, pal, col, dec: decOf(lang) };
}

/** Texty vw_* bez prefixu (tvar, který čte viewer.js). */
export const viewerTxt = (texts: Record<string, string>): Record<string, string> =>
  Object.fromEntries(Object.entries(texts).filter(([k]) => k.startsWith("vw_")).map(([k, v]) => [k.slice(3), v]));

/** Čas t = 0 balíku jako ms epochy (čas ze souboru je „jak na hodinách“, proto UTC), nebo null bez počátku záznamu. */
export function clockOf(ws: Ws, tmin: number): number | null {
  const c = ws.origin ? Date.parse(ws.origin.replace(" ", "T") + "Z") + tmin * 1000 : NaN;
  return Number.isFinite(c) ? c : null;
}

/**
 * K základnímu balíku (mřížka smyčky, případně průběhy modelu) přidá ostatní signály záznamu: ty, které nepatří smyčce a
 * jejich název nekoliduje s `reserved` ani s názvy poruch d0, d1… Časy se posunou o rozdíl počátků balíků.
 */
export function withRecordSignals(base: Pack, raw: Pack | undefined, ws: Ws, reserved: Set<string>): { merged: Pack; extra: string[] } {
  const loopNames = new Set([ws.pv, ws.mv, ws.sp, ...(ws.dists ?? [])].filter((x): x is string => !!x));
  const extra = (raw?.meta.sigs ?? []).map((s) => s.name).filter((n) => !loopNames.has(n) && !reserved.has(n) && !/^d\d+$/.test(n));
  if (!raw || !extra.length) return { merged: base, extra: [] };
  return { merged: mergePacks(base, raw, extra, raw.meta.tmin - base.meta.tmin), extra };
}

/** Jedinečné zobrazené názvy signálů (shoda názvů, např. SP = PV, se rozliší tečkou). */
export function uniqueNames() {
  const used = new Set<string>();
  return (n: string) => { let k = n || "?"; while (used.has(k)) k += "·"; used.add(k); return k; };
}

export interface ViewerHandlers {
  onLayout: (layout: string) => void;
  onWins?: (w: unknown) => void;
  onMode?: (mode: string) => void;
}

/**
 * Připojí viewer.js k prvku `box` s daty `data` (null = zatím není co kreslit). Stejný otisk dat = jen aktualizace stávající
 * instance (zoom zůstane); úseky a rozložení se aktualizují v modulu. Odpojení až s komponentou, ne při každé změně dat.
 */
export function useViewerMount(box: RefObject<HTMLElement | null>, data: Omit<ViewerData, "sig"> | null, handlers: ViewerHandlers) {
  const destroy = useRef<(() => void) | null>(null);
  const h = useRef(handlers);
  useEffect(() => { h.current = handlers; });
  const sig = useMemo(() => (data
    ? `${data.hash}|${data.dec}|${data.dark}|${JSON.stringify(data.sigs.map((s) => [s.name, s.role, s.color, s.unit]))}` : ""), [data]);
  useEffect(() => {
    if (!box.current || !data) return;
    destroy.current = mountViewer({
      data: { ...data, sig }, parentElement: box.current,
      setStateValue: (key, value) => {
        if (key === "layout" && typeof value === "string" && value.length <= 65536) h.current.onLayout(value);
        else if (key === "wins") h.current.onWins?.(value);
      },
      setTriggerValue: (key, value) => { if (key === "mode") h.current.onMode?.(String(value)); },
    });
  }, [box, data, sig]);
  useEffect(() => () => { destroy.current?.(); destroy.current = null; }, []);
}
