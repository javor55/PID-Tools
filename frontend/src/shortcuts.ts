// Globální klávesové zkratky (FEATURE-001): jeden posluchač `keydown` na `window`, rozpoznání klávesy je čistá funkce.
// Ctrl+S uložit projekt, F5 Calculate (jen Ladění), Ctrl+1…6 záložky, Alt+↑/↓ smyčka, Ctrl+P záložka Projekt, F1 průvodce
// (ten řeší components/Guide.tsx), Ctrl+Z / Ctrl+Y (Ctrl+Shift+Z) zpět / znovu změny nastavení (FEATURE-006).
// Zkratky s Ctrl / Alt / F-klávesou fungují i při psaní do pole; Ctrl+Z / Ctrl+Y ne (v poli vrací text prohlížeč).
import { useEffect } from "react";
import type { components } from "./api/schema";
import { toastError } from "./components/Toasts";
import { request } from "./api/client";
import { ALL_GROUPS, invalidateGroups } from "./queryKeys";
import { queryClient } from "./queryClient";
import { useSettingsUi } from "./settings/settingsStore";
import { pickLoop, saveProjectToast } from "./start/project";
import { NAV_TABS, useUi } from "./store";
import { useTun } from "./tabs/tuningState";

export type Action =
  | { kind: "save" }
  | { kind: "calc" }
  | { kind: "tab"; index: number }          // pořadí v NAV_TABS (od 0)
  | { kind: "project" }
  | { kind: "undo" }
  | { kind: "redo" }
  | { kind: "loop"; dir: -1 | 1 };

export interface KeyLike { key: string; ctrlKey: boolean; metaKey: boolean; altKey: boolean; shiftKey: boolean }

/**
 * Která zkratka odpovídá stisku klávesy (null = žádná, událost se nechá prohlížeči).
 * Se Shiftem se nic nespouští (Ctrl+Shift+S, Shift+F5 patří prohlížeči) kromě Ctrl+Shift+Z (znovu); Ctrl+R a Ctrl+F5
 * také zůstávají prohlížeči.
 * Ctrl+Alt (AltGr na některých klávesnicích) se bere jako znak, ne jako zkratka.
 */
export function matchShortcut(e: KeyLike): Action | null {
  const mod = e.ctrlKey || e.metaKey;
  const k = e.key.length === 1 ? e.key.toLowerCase() : e.key;
  if (e.shiftKey) return mod && !e.altKey && k === "z" ? { kind: "redo" } : null;
  if (mod && !e.altKey) {
    if (k === "s") return { kind: "save" };
    if (k === "p") return { kind: "project" };
    if (k === "z") return { kind: "undo" };
    if (k === "y") return { kind: "redo" };
    if (e.ctrlKey && !e.metaKey && /^[1-9]$/.test(k) && +k <= NAV_TABS.length) return { kind: "tab", index: +k - 1 };
    return null;
  }
  if (e.altKey && !mod) {
    if (k === "ArrowUp") return { kind: "loop", dir: -1 };
    if (k === "ArrowDown") return { kind: "loop", dir: 1 };
    return null;
  }
  if (!mod && !e.altKey && k === "F5") return { kind: "calc" };
  return null;
}

/** Přepne na předchozí / další smyčku; na okraji seznamu nic. Pořadí = index smyčky v projektu. */
async function stepLoop(dir: -1 | 1): Promise<void> {
  const wid = useUi.getState().wid;
  if (!wid) return;
  const hit = queryClient.getQueriesData<components["schemas"]["Loops"]>({ queryKey: ["ws", wid, "loops"] })
    .map(([, d]) => d).find((d) => !!d);
  if (!hit) return;
  const idx = hit.loops.map((l) => l.index).sort((a, b) => a - b);
  const at = idx.indexOf(hit.active) + dir;
  if (at < 0 || at >= idx.length) return;
  await pickLoop(idx[at]!);
}

let undoBusy = false;

/**
 * Zpět / znovu poslední změny nastavení (POST /undo, /redo): po úspěchu se zneplatní dotazy všech skupin, protože krok
 * může měnit nastavení, sady, úsek i scénář. Chyba serveru (409 – není co vracet / krok už neplatí) jde do toastu.
 * Souběžné volání se zahodí (další se spustí až po dokončení předchozího).
 */
export async function stepUndo(kind: "undo" | "redo"): Promise<void> {
  const wid = useUi.getState().wid;
  if (!wid || undoBusy) return;
  undoBusy = true;
  try {
    await request("POST", `/workspaces/${wid}/${kind}`);
  } catch (e) {
    toastError(e);
  } finally {
    undoBusy = false;
    await invalidateGroups(queryClient, wid, ALL_GROUPS);       // i po chybě: krok mohl být přeskočen
  }
}

/** Provede akci zkratky; při otevřeném nastavení aplikace jen uložení. */
export function runAction(a: Action): void {
  if (useSettingsUi.getState().open && a.kind !== "save") return;
  const ui = useUi.getState();
  switch (a.kind) {
    case "save": void saveProjectToast(); break;
    case "calc": {
      const tun = useTun.getState();
      if (ui.tab === "tuning" && !tun.busy) tun.calc?.();
      break;
    }
    case "tab": { const t = NAV_TABS[a.index]; if (t) ui.setTab(t.id); break; }
    case "project": ui.setTab("project"); break;
    case "loop": stepLoop(a.dir).catch(toastError); break;
    case "undo": case "redo": stepUndo(a.kind).catch(toastError); break;
  }
}

/** Cíl události je pole pro psaní nebo výběr (input, textarea, select, contenteditable). */
function inTextField(t: EventTarget | null): boolean {
  if (!(t instanceof HTMLElement)) return false;
  return t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT" || t.isContentEditable;
}

/** Jeden posluchač na window (volá se jednou v App.tsx). */
export function useShortcuts() {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const a = matchShortcut(e);
      if (!a) return;
      // šipky se Alt ve výběru (select) nechávají prvku
      if ((a.kind === "undo" || a.kind === "redo") && inTextField(e.target)) return;      // v poli vrací text prohlížeč
      if (a.kind === "loop" && (e.target as HTMLElement | null)?.tagName === "SELECT") return;
      e.preventDefault();                       // F5 nesmí načíst stránku znovu, Ctrl+S / Ctrl+P neotevírají dialogy prohlížeče
      if (e.repeat) return;
      runAction(a);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
}
