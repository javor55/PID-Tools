// Společné prvky technik s vlastními vstupy (split range, VPC, poměr): upravené vstupy drží prohlížeč (po prostorech),
// API je dostane v těle požadavku; „původní hodnoty“ = zahodit úpravy a vrátit výchozí z GET. Dále editor modelu
// druhého členu, kontrolní seznam, tabulka hodnot pro PCS 7 a dotazy na návrh a simulaci.
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { create } from "zustand";
import { binary, request } from "../../api/client";
import type { components } from "../../api/schema";
import { unframe } from "../../api/signals";
import { useT } from "../../i18n";
import { useUi } from "../../store";
import { NumInput, num } from "./common";

export type ModelInfo = components["schemas"]["ModelInfo"];
export type Check = components["schemas"]["pidtools__api__apc_more__Check"];

type Edits = Record<string, unknown>;
interface MoreState {
  edits: Record<string, Edits>;                       // klíč "wid:technika" → upravené vstupy (jen změněné položky)
  put: (k: string, patch: Edits) => void;             // undefined v patchi položku zahodí
  clear: (k: string, fields?: string[]) => void;
}
const useMoreStore = create<MoreState>((set) => ({
  edits: {},
  put: (k, patch) => set((s) => {
    const cur = { ...s.edits[k], ...patch };
    for (const f of Object.keys(cur)) if (cur[f] === undefined) delete cur[f];
    return { edits: { ...s.edits, [k]: cur } };
  }),
  clear: (k, fields) => set((s) => {
    const cur = { ...s.edits[k] };
    for (const f of fields ?? Object.keys(cur)) delete cur[f];
    return { edits: { ...s.edits, [k]: cur } };
  }),
}));
const NONE: Edits = {};

/** Upravené vstupy techniky v tomto prostoru + změna a návrat k původním hodnotám. */
export function useEdits<In extends object>(tech: string) {
  const wid = useUi((s) => s.wid);
  const k = `${wid}:${tech}`;
  const ov = (useMoreStore((s) => s.edits[k]) ?? NONE) as Partial<In>;
  const put = useMoreStore((s) => s.put);
  const clear = useMoreStore((s) => s.clear);
  return { ov, put: (p: Partial<Record<keyof In, unknown>>) => put(k, p as Edits),
    clear: (f?: (keyof In & string)[]) => clear(k, f) };
}

/** Tělo požadavku: výchozí z GET přepsané úpravami. */
export const mergeBody = <In extends object>(defaults: In | undefined, ov: Partial<In>) =>
  (defaults ? ({ ...defaults, ...ov } as In) : undefined);

/** Výsledky pro tělo (POST …/design); do přepočtu zůstává předchozí, na začátku výsledek z GET. */
export function useDesign<D>(tech: string, body: object | undefined, first: D | undefined) {
  const wid = useUi((s) => s.wid);
  const q = useQuery({ queryKey: ["ws", wid, "apc", `${tech}-design`, body], enabled: !!wid && !!body,
    placeholderData: keepPreviousData, retry: false,
    queryFn: () => request<D>("POST", `/workspaces/${wid}/apc/${tech}/design`, body) });
  return q.data ?? first;
}

/** Ukazatele a křivky simulace pro tělo (POST …/simulate a …/simulate/curves). */
export function useSim<S>(tech: string, body: object | undefined) {
  const wid = useUi((s) => s.wid);
  const key = ["ws", wid, "apc", `${tech}-sim`, body];
  const kpi = useQuery({ queryKey: [...key, "kpi"], enabled: !!wid && !!body, placeholderData: keepPreviousData, retry: false,
    queryFn: () => request<S>("POST", `/workspaces/${wid}/apc/${tech}/simulate`, body) });
  const cv = useQuery({ queryKey: [...key, "curves"], enabled: !!wid && !!body, placeholderData: keepPreviousData, retry: false,
    queryFn: async () => unframe(await binary(`/workspaces/${wid}/apc/${tech}/simulate/curves`, body)) });
  return { sim: kpi.data, curves: cv.data };
}

/** Číselné pole s mezemi (API jiné hodnoty odmítne): hodnota se po potvrzení ořízne. */
export function NumField({ label, value, onCommit, testid, lo, hi, title }: { label: string; value: number;
  onCommit: (x: number) => void; testid: string; lo?: number; hi?: number; title?: string }) {
  const cl = (x: number) => Math.min(hi ?? Infinity, Math.max(lo ?? -Infinity, x));
  return (
    <label className="field" title={title}><span>{label}</span>
      <NumInput value={value} min={lo} testid={testid} onCommit={(x) => onCommit(cl(x))} /></label>
  );
}

/** Parametry modelu druhého členu (typ jako u smyčky; parametry kromě zesílení nezáporné). */
export function ModelEditor({ model, values, edited, onChange, onReset, testid, disabled }: { model: ModelInfo; values: number[];
  edited: boolean; onChange: (p: number[]) => void; onReset: () => void; testid: string; disabled?: boolean }) {
  const T = useT();
  return (
    <div className="stack" data-testid={testid}>
      <div className="small muted">{T("model_" + model.code)}</div>
      {model.params.map((n, i) => (
        <label className="field" key={n}><span>{n}</span>
          <NumInput value={values[i] ?? 0} min={i ? 0 : undefined} disabled={disabled} testid={`${testid}-${i}`}
            onCommit={(x) => onChange(values.map((v, k) => (k === i ? (i ? Math.max(x, 0) : x) : v)))} /></label>))}
      {!disabled && <button className="btn" disabled={!edited} title={T("h_apc_reset")} data-testid={`${testid}-reset`}
        onClick={onReset}>{T("apc_reset")}</button>}
    </div>
  );
}

/** Kontrolní seznam struktury: ✅ splněno, ⬜ chybí, ℹ️ připomínka (jako app.guides.icon). */
export function Checks({ items, testid }: { items: Check[]; testid: string }) {
  return (
    <ul className="checks" data-testid={testid}>
      {items.map((c, i) => <li key={i} className={c.state === false ? "warn" : undefined}>
        {c.state ? "✅" : c.state === false ? "⬜" : "ℹ️"} {c.text}</li>)}
    </ul>
  );
}

/** Tabulka hodnot pro PCS 7: parametr, hodnota, jednotka; buňka hodnoty má `testid-<klíč>`. */
export function ValueTable({ rows, testid }: { rows: { key: string; name: string; value: number; unit: string }[]; testid: string }) {
  const T = useT();
  return (
    <table className="tbl" data-testid={testid}>
      <thead><tr><th>{T("sm_gen_par")}</th><th>{T("sm_apl_value")}</th><th>{T("sm_apl_unit")}</th></tr></thead>
      <tbody>{rows.map((r) => (
        <tr key={r.key}><td>{r.name}</td><td className="mono" data-testid={`${testid}-${r.key}`}>{num(r.value)}</td><td>{r.unit}</td></tr>))}</tbody>
    </table>
  );
}

/** Číslo na n platných číslic (jako `:.3g` v Pythonu) pro texty výsledků. */
export const g = (x: number, n = 3) => String(+x.toPrecision(n));
