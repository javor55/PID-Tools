// Moduly čistého JS v src/legacy (připojují je React obaly z components/ a tabs/).
declare module "*/viewer.js" {
  /** Signál balíku z /signals doplněný o roli, barvu a jednotku (frontend/src/components/RecordViewer.tsx). */
  export interface ViewerSig {
    name: string; ti: number; off: number; n: number;     // popis z binárního balíku (api/signals.ts)
    role: string; color: string; unit: string;
    axis: string | null;                                  // společná osa panelu: "pv" / "mv" / veličina, jinak vlastní
    dash?: string | null;                                 // čárkování čáry, např. "6 4" (průběh modelu)
  }
  /** Vrstva úseků (viewer_spans.js): graf záložky Model (common / inputs) a Diagnostiky (ab). */
  export interface ViewerSpanInput {
    id: string; sig: string;                              // vstup (MV, D1…) a název jeho signálu v grafu
    wins: number[][]; fits: (number | null)[];
    wcol: string; wbg: string; wbd: string; wtx: string;
    badge: string | null; note: string | null;
  }
  /** Úsek A a volitelně B (Diagnostika): barvy pásu / meze (ca, cb), textu štítku (ta, tb), pozadí štítku (bg) a názvy. */
  export interface ViewerSpanAB {
    a: number[]; b: number[] | null; ca: string; cb: string; ta: string; tb: string; bg: string; la: string; lb: string;
  }
  export interface ViewerSpans {
    mode: "common" | "inputs" | "ab"; step: number; unit: { u: string; f: number };
    common?: number[];
    ccol?: string; cbd?: string; ctx?: string; cbg?: string;  // barvy společného úseku (pás, mez, text, pozadí štítku)
    inputs: ViewerSpanInput[]; excl: number[][];
    ab?: ViewerSpanAB;
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
    buf?: ArrayBuffer | null;             // blob balíku v paměti (grafy Modelu a Diagnostiky): místo url / b64 / mezipaměti
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
