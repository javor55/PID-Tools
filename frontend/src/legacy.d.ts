// Moduly čistého JS v src/legacy (připojují je React obaly z components/ a tabs/).
declare module "*/viewer.js" {
  /** Signál balíku z /signals doplněný o roli, barvu a jednotku (frontend/src/components/RecordViewer.tsx). */
  export interface ViewerSig {
    name: string; ti: number; off: number; n: number;     // popis z binárního balíku (api/signals.ts)
    role: string; color: string; unit: string;
    axis: string | null;                                  // společná osa panelu: "pv" / "mv" / veličina, jinak vlastní
    dash?: string | null;                                 // čárkování čáry, např. "6 4" (průběh modelu)
  }
  /** Vrstva úseků identifikace (viewer_spans.js): jen graf záložky Model. */
  export interface ViewerSpanInput {
    id: string; sig: string;                              // vstup (MV, D1…) a název jeho signálu v grafu
    wins: number[][]; fits: (number | null)[];
    wcol: string; wbg: string; wbd: string; wtx: string;
    badge: string | null; note: string | null;
  }
  export interface ViewerSpans {
    mode: "common" | "inputs"; common: number[]; step: number; unit: { u: string; f: number };
    ccol: string; cbd: string; ctx: string; cbg: string;  // barvy společného úseku (pás, mez, text, pozadí štítku)
    inputs: ViewerSpanInput[]; excl: number[][];
    txt: Record<string, string>;
  }
  /** Přepínače průběhu modelu (viewer_model.js): názvy signálů v grafu. */
  export interface ViewerModel {
    pv: string; all: string; win: string | null; mv: string | null; dv: string | null; resid: string | null;
    txt: Record<string, string>;
  }
  /** Data prohlížeče záznamu: výhradně pole, která viewer.js čte (D.x). */
  export interface ViewerData {
    key: string;                          // klíč v registru window.__pidView
    view_key: string;                     // klíč uloženého zobrazení (zoom, panely) v paměti stránky
    sig: string;                          // otisk dat: stejný otisk = jen aktualizace stávající instance
    sigs: ViewerSig[];
    times: { off: number; n: number }[];  // společné časové osy balíku
    T: number; decim: number; hash: string;
    clock: number | null;                 // ms epochy pro t = 0, nebo null
    tunit: string;                        // "auto" | "s" | "min" | "h"
    dec: string;                          // desetinný oddělovač
    dark: boolean;
    txt: Record<string, string>;          // texty vw_* bez prefixu
    fname: string;
    layout: string | null;                // JSON uloženého rozložení
    b64?: string | null; url?: string | null;   // data jinak než z mezipaměti window.__pidViewData
    groups?: { label: string; names: string[] }[];   // seznam signálů ve skupinách (např. podle smyček)
    buf?: ArrayBuffer | null;             // blob balíku v paměti (graf Modelu): místo url / b64 / mezipaměti
    defaults?: { panels: { sigs: string[]; h?: number }[] };   // výchozí rozložení panelů (jinak podle rolí)
    spans?: ViewerSpans; model?: ViewerModel;
  }
  export interface ViewerComponent {
    data: ViewerData;
    parentElement: HTMLElement;
    /** Stav ven (viewer.js posílá „layout“ po 1,5 s klidu); název funkce je historický. */
    setStateValue: (key: string, value: unknown) => void;
    setTriggerValue?: (key: string, value: unknown) => void;
    listHost?: HTMLElement;              // seznam signálů mimo graf (např. pravý panel stránky)
  }
  /** Vrací funkci pro odpojení (ResizeObserver, překreslení, prvek, záznam v registru). */
  const mount: (component: ViewerComponent) => () => void;
  export default mount;
}
declare module "*/viewer_an.js" {
  const an: unknown;
  export default an;
}
declare module "*/trend.js" {
  type Num = number | null;
  /** Karta grafu (řádek): průběh y na společné časové ose t, rozsah osy, případně úseky a průběh modelu. */
  export interface TrendRow {
    id: string; kind: "pv" | "in" | "sig"; title: string; badge?: string | null; note?: string | null;
    color: string; y: Num[] | null; lo: number; hi: number; h: number;
    lines?: [Num[] | null, string, string, number, string][];    // [y, barva, čárkování, tloušťka, název]
    wins?: number[][]; fits?: Num[];                              // úseky vstupu a jejich shoda s modelem
    wcol?: string; wbg?: string; wbd?: string; wtx?: string;
    model?: { all: Num[] | null; mv: Num[] | null; dv: Num[] | null; full_all?: Num[] | null; full?: Num[] | null };
    resid?: Num[] | null;
  }
  /** Data grafu průběhů s úseky: pole, která předávají Model a Diagnostika přes components/Trend.tsx. */
  export interface TrendData {
    key: string; view_key: string;
    mode: "view" | "common" | "inputs" | "ab";
    T: number; step?: number | null; unit: { u: string; f: number };
    clock: number | null; dec: string; dark: boolean;
    txt: Record<string, string>;
    t: Num[] | null;
    rows: TrendRow[]; excl: number[][];
    common?: number[];
    ab?: { a: number[]; b: number[] | null; ca: string; cb: string; la: string; lb: string };
    bar: { mode_switch?: boolean; zoom?: boolean; title?: string; note?: string; legend?: [string, string, string][] };
  }
  export interface TrendComponent {
    data: TrendData & { sig: string };    // sig = otisk dat (stejný otisk = nic se nepřekresluje)
    parentElement: HTMLElement;
    setStateValue: (key: string, value: unknown) => void;
    setTriggerValue: (key: string, value: unknown) => void;
  }
  /** Vrací funkci pro odpojení (ResizeObserver, prvek, záznam v registru). */
  const mount: (component: TrendComponent) => () => void;
  export default mount;
}
declare module "*/live_engine.js" {
  const engine: unknown;
  export default engine;
}
declare module "*/ctrl_engine.js" {
  const engine: unknown;
  export default engine;
}
declare module "*/live_ui.js" {
  export interface LiveComponent {
    data: Record<string, unknown>;
    parentElement: HTMLElement;
    setTriggerValue: (name: string, value: unknown) => void;
  }
  /** Vrací funkci pro odpojení (zastaví animaci a odpojí posluchače). */
  const mount: (component: LiveComponent) => () => void;
  export default mount;
}
