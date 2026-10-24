// Společné díly technik APC s více výsledky (kaskáda, gain scheduling, rozvazbení, override): kontrolní seznam struktury,
// postup pro PCS 7, tabulka bodů, výběr druhé smyčky projektu (předává se jako ?loop=) a tlačítko původních hodnot.
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import { create } from "zustand";
import { ApiError, binary, request } from "../../api/client";
import type { components } from "../../api/schema";
import { unframe } from "../../api/signals";
import { useT } from "../../i18n";
import { TABS, useUi } from "../../store";
import { Bold, num, useApc } from "./common";

export type LoopCheck = components["schemas"]["LoopCheck"];
export type PointRow = components["schemas"]["PointRow"];
type CascadeInfo = components["schemas"]["CascadeInfo"];

/** Zvolená druhá smyčka podle techniky (undefined = výchozí z API) – sdílí ji postranní panel s hlavní plochou. */
export const usePair = create<{ loops: Record<string, number | undefined>; setLoop: (k: string, i: number) => void }>((set) => ({
  loops: {}, setLoop: (k, i) => set((s) => ({ loops: { ...s.loops, [k]: i } })),
}));

/** Dotazový řetězec (vynechané hodnoty se nepřidají). */
export function qs(p: Record<string, string | number | undefined>): string {
  const e = Object.entries(p).filter(([, v]) => v !== undefined);
  return e.length ? "?" + e.map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`).join("&") : "";
}

/** Ostatní smyčky projektu (z /apc/cascade) – nabídka výběru druhé smyčky i text, když žádná není. */
export function useOthers() {
  const q = useApc<CascadeInfo>("cascade-list", "/apc/cascade");
  return { loops: q.data?.inputs.loops ?? [], pending: q.isPending && !q.isError };
}

/** POST bez návratové hodnoty (původní hodnoty) a znovu načíst vše o prostoru. */
export function usePost() {
  const wid = useUi((s) => s.wid);
  const qc = useQueryClient();
  return async (path: string, body: unknown = {}) => {
    await request("POST", `/workspaces/${wid}${path}`, body);
    await qc.invalidateQueries({ queryKey: ["ws", wid] });
  };
}

/** Simulace techniky: KPI (JSON) a křivky (binární balík) ze stejného těla; klíč zneplatní změna zadání. */
export function useSim<K>(key: unknown[], path: string, query: string, body: unknown, enabled = true) {
  const wid = useUi((s) => s.wid);
  const k = ["ws", wid, "apc", ...key];
  const base = { enabled, placeholderData: keepPreviousData, retry: false } as const;
  const sim = useQuery({ ...base, queryKey: [...k, "kpi"],
    queryFn: () => request<K>("POST", `/workspaces/${wid}${path}${query}`, body) });
  const cv = useQuery({ ...base, queryKey: [...k, "curves"],
    queryFn: async () => unframe(await binary(`/workspaces/${wid}${path}/curves${query}`, body)) });
  return { sim, cv };
}

export function LoopSelect({ kind, label, current }: { kind: string; label: string; current?: number }) {
  const T = useT();
  const { loops } = useOthers();
  const setLoop = usePair((s) => s.setLoop);
  if (!loops.length) return <div className="muted small" data-testid={`apc-nootherloop-${kind}`}>{T("apc_need_loop")}</div>;
  return (
    <label className="field"><span>{label}</span>
      <select value={current ?? loops[0].index} data-testid={`apc-loop-${kind}`} onChange={(e) => setLoop(kind, +e.target.value)}>
        {loops.map((l) => <option key={l.index} value={l.index}>{l.name}{l.has_model ? "" : " (–)"}</option>)}</select>
    </label>
  );
}

/** Chyba dotazu techniky se dvěma smyčkami: jediná smyčka v projektu, druhá bez modelu, jinak chybové hlášení. */
export function PairError({ err, loop }: { err: unknown; loop?: number }) {
  const T = useT();
  const { loops, pending } = useOthers();
  if (pending) return <div className="card muted">…</div>;
  if (!loops.length) return <div className="card muted" data-testid="apc-need-loop">{T("apc_need_loop")}</div>;
  const sel = loops.find((l) => l.index === (loop ?? loops[0].index));
  if (sel && !sel.has_model) {
    return <div className="card warn" data-testid="apc-loop-nomodel">⚠ {T("g_chk_model", { n: sel.name })}</div>;
  }
  if (err instanceof ApiError && err.status === 409) return <div className="card muted">{T("need_model")}</div>;
  return <div className="card err">{String((err as Error)?.message ?? err)}</div>;
}

/** Kontrolní seznam struktury: ok = splněno, jinak upozornění / připomínka; akce „tab:…“ otevře záložku. */
export function Checks({ items }: { items: LoopCheck[] }) {
  const T = useT();
  const setTab = useUi((s) => s.setTab);
  if (!items.length) return null;
  return (
    <div className="card stack" data-testid="apc-checks">
      <ul className="checks">
        {items.map((c, i) => {
          const tab = c.action?.startsWith("tab:") ? TABS.find((t) => t.id === c.action!.slice(4)) : undefined;
          return (
            <li key={i} className={c.ok === true ? "ok" : c.ok === false ? "warn" : "muted"}>
              {c.ok === true ? "✓" : c.ok === false ? "⚠" : "•"} <Bold text={c.text} />
              {tab && <> <button className="btn" onClick={() => setTab(tab.id)}>{T("g_open", { m: T(tab.label) })}</button></>}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

/** Postup pro PCS 7 (text API s **tučným** a řádky seznamu). */
export function Impl({ text, testid }: { text?: string | null; testid: string }) {
  const T = useT();
  if (!text) return null;
  return (
    <div className="card stack" data-testid={testid}>
      <h3>{T("g_impl")}</h3>
      <div className="small" style={{ whiteSpace: "pre-wrap" }}><Bold text={text} /></div>
    </div>
  );
}

/** Tabulka hodnot do bloku GainSched: vstup, hodnoty v bodech a jednotka. */
export function PointTable({ rows, testid }: { rows: PointRow[]; testid: string }) {
  const T = useT();
  const n = rows[0]?.values.length ?? 0;
  return (
    <table className="tbl" data-testid={testid}>
      <thead><tr><th>{T("gs_in")}</th>{Array.from({ length: n }, (_, i) => <th key={i}>{i + 1}</th>)}<th>{T("sm_apl_unit")}</th></tr></thead>
      <tbody>{rows.map((r) => (
        <tr key={r.input} data-testid={`${testid}-${r.input}`}><td>{r.input}</td>
          {r.values.map((v, i) => <td key={i} className="mono">{num(v)}</td>)}<td>{r.unit}</td></tr>))}</tbody>
    </table>
  );
}

/** Regulátor (Gain, TI, TD) – tabulka s `data-testid` hodnot `<prefix>-kc|ti|td`. */
export function PidRow({ c, prefix }: { c: { Kc: number; Ti: number; Td: number }; prefix: string }) {
  return (
    <table className="tbl"><thead><tr><th>Gain</th><th>TI [s]</th><th>TD [s]</th></tr></thead>
      <tbody><tr><td className="mono" data-testid={`${prefix}-kc`}>{num(c.Kc)}</td>
        <td className="mono" data-testid={`${prefix}-ti`}>{num(c.Ti)}</td>
        <td className="mono" data-testid={`${prefix}-td`}>{num(c.Td)}</td></tr></tbody></table>
  );
}
