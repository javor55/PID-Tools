// Náhled souboru (první a poslední řádky po převzorkování) a „Celý náhled“: okno s grafy záznamu a celou tabulkou
// (přechod na čas, filtr řádků, upozornění z Kvality dat, export CSV). Data z /preview po částech.
import { keepPreviousData, useQueries, useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { bytes, request } from "../api/client";
import type { components } from "../api/schema";
import { RecordViewer } from "../components/RecordViewer";
import { Seg } from "../components/Ui";
import { useWs } from "../data";
import { useT, useTexts } from "../i18n";
import { useUi } from "../store";
import "../styles/data.css";

type PreviewT = components["schemas"]["Preview"];
type Row = PreviewT["rows"][number];
type Filter = "all" | "warn" | "mv";

const ROW_H = 24;
const CHUNK = 200;

function useFmt() {
  const lang = useUi((s) => s.lang);
  return (v: number | null | undefined) => v === null || v === undefined ? "" :
    v.toLocaleString(lang, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function previewQuery(wid: string | null, ws: { fname?: string; n?: number; pv?: string | null; mv?: string | null; sp?: string | null;
  dists?: string[]; pos?: string | null } | undefined, q: Record<string, string | number>) {
  return {
    queryKey: ["ws", wid, "preview", ws?.fname, ws?.n, ws?.pv, ws?.mv, ws?.sp, ws?.dists, ws?.pos, q],
    queryFn: () => request<PreviewT>("GET", `/workspaces/${wid}/preview?` + new URLSearchParams(
      Object.entries(q).map(([k, v]) => [k, String(v)])).toString()),
    enabled: !!wid && !!ws?.n,
  };
}

/** Karta „Náhled souboru“: tři první řádky, tři tečky a poslední řádek. */
export function PreviewCard({ onFull }: { onFull: () => void }) {
  const T = useT();
  const wid = useUi((s) => s.wid);
  const ws = useWs().data;
  const fmt = useFmt();
  const head = useQuery(previewQuery(wid, ws, { offset: 0, limit: 3 }));
  const total = head.data?.total ?? 0;
  const tail = useQuery({ ...previewQuery(wid, ws, { offset: Math.max(total - 1, 0), limit: 1 }), enabled: total > 4 });
  if (!head.data) return null;
  const cols = head.data.columns;
  const rows: (Row | null)[] = total > 4 ? [...head.data.rows, null, ...(tail.data?.rows ?? [])] : head.data.rows;
  const time = (r: Row) => r.dt ? r.dt.slice(0, head.data!.Ts >= 1 ? 19 : 23) : fmt(r.t);
  return (
    <section className="dt-card" aria-label={T("tn_prev")} data-testid="data-preview">
      <div className="dt-head">
        <h2>{T("tn_prev")}</h2>
        <button type="button" className="link" onClick={onFull} data-testid="full-open">{T("ui_data_all_table")}</button>
        <span className="dt-sub">{T("tn_prev_note")}</span>
      </div>
      <div className="dt-scroll">
        <table className="dt-prev">
          <thead>
            <tr>
              <th scope="col">{T("col_time")}<small>{T("prev_k_time")}{head.data.rows[0]?.dt ? ` · ${T("prev_datetime")}` : ""}</small></th>
              {cols.map((c) => (
                <th key={c.label} scope="col" className={`role-${c.role}`}>{c.role === "POS" ? T("pos_short") : c.role}
                  <small>{T("prev_k_num")} · {c.label.replace(/^(PV|MV|SP) · /, "")}</small></th>))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => r === null
              ? <tr key={i}><td>…</td>{cols.map((c) => <td key={c.label} />)}</tr>
              : <tr key={i}><td>{time(r)}</td>{r.v.map((v, j) => <td key={j}>{fmt(v)}</td>)}</tr>)}
          </tbody>
        </table>
      </div>
    </section>
  );
}

/** Tabulka po převzorkování po částech: pevná výška řádku, vykreslují se jen viditelné řádky. */
function Table({ filter, goto, onTotals, onRange }: { filter: Filter; goto: { t: number; n: number } | null;
  onTotals: (p: PreviewT) => void; onRange: (r: [number, number]) => void }) {
  const T = useT();
  const wid = useUi((s) => s.wid);
  const ws = useWs().data;
  const fmt = useFmt();
  const box = useRef<HTMLDivElement>(null);
  const [top, setTop] = useState(0);
  const [h, setH] = useState(400);
  const first = useQuery({ ...previewQuery(wid, ws, { filter, offset: 0, limit: CHUNK }), placeholderData: keepPreviousData });
  const total = first.data?.total ?? 0;
  const vis = Math.ceil(h / ROW_H) + 2;
  const need: number[] = [];
  for (let c = Math.floor(top / CHUNK); c <= Math.floor((top + vis) / CHUNK) && c * CHUNK < total; c++) need.push(c);
  const chunks = useQueries({ queries: need.map((c) => ({
    ...previewQuery(wid, ws, { filter, offset: c * CHUNK, limit: CHUNK }), placeholderData: keepPreviousData })) });
  useEffect(() => { if (first.data) onTotals(first.data); }, [first.data, onTotals]);
  const last = Math.min(top + Math.max(Math.floor((h - 28) / ROW_H), 1), total);
  useEffect(() => { onRange([total ? top + 1 : 0, last]); }, [top, last, total, onRange]);
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setH(el.clientHeight));
    ro.observe(el);
    setH(el.clientHeight);
    return () => ro.disconnect();
  }, []);
  // přechod na čas: server vrátí řádek (po filtru), na který se posune
  const gt = useQuery({ ...previewQuery(wid, ws, { filter, t: goto?.t ?? 0, limit: 1 }), enabled: !!wid && !!goto });
  const [cur, setCur] = useState<number | null>(null);
  useEffect(() => {
    if (!goto || !gt.data || !box.current) return;
    setCur(gt.data.offset);
    box.current.scrollTop = Math.max(gt.data.offset - 3, 0) * ROW_H;
  }, [goto, gt.data]);

  const rowAt = (i: number): Row | undefined => {
    const c = Math.floor(i / CHUNK);
    const k = need.indexOf(c);
    return k >= 0 ? chunks[k].data?.rows[i - c * CHUNK] : undefined;
  };
  const cols = first.data?.columns ?? [];
  const grid = `54px minmax(140px, 1.4fr) ${cols.map(() => "minmax(52px, 1fr)").join(" ")} minmax(70px, 1fr)`;
  const from = Math.max(top - 2, 0), to = Math.min(top + vis, total);
  const items = [];
  for (let i = from; i < to; i++) {
    const r = rowAt(i);
    if (!r) continue;
    const notes = r.notes.map((n) => T(`dq_${n}_name`, { name: "" }).trim()).join(" · ");
    items.push(
      <div key={i} className={"dtf-row" + (r.notes.length ? " warn" : "") + (cur === i ? " cur" : "")} style={{ top: i * ROW_H, gridTemplateColumns: grid }}>
        <span className="i">{r.i}</span>
        <span className="tm">{r.dt ? r.dt.slice(0, (first.data?.Ts ?? 1) >= 1 ? 19 : 23) : fmt(r.t)}</span>
        {r.v.map((v, j) => <span key={j} className="num">{fmt(v)}</span>)}
        <span className="nt">{notes}</span>
      </div>);
  }
  return (
    <div ref={box} className="dtf-scroll" data-testid="full-table" onScroll={(e) => setTop(Math.floor(e.currentTarget.scrollTop / ROW_H))}>
      <div className="dtf-thead" style={{ gridTemplateColumns: grid }}>
        <span className="i num">#</span><span>{first.data?.rows[0]?.dt ? T("col_time") : T("time_s")}</span>
        {cols.map((c) => <span key={c.label} className={`num role-${c.role}`} title={c.label}>{c.role === "POS" ? T("pos_short") : c.role}</span>)}
        <span>{T("prev_note")}</span>
      </div>
      <div style={{ height: total * ROW_H, position: "relative" }}>{items}</div>
    </div>
  );
}

/** Okno „Celý náhled · soubor“: grafy záznamu + tabulka, jen grafy, jen tabulka. */
export function FullPreview({ onClose }: { onClose: () => void }) {
  const T = useT();
  const texts = useTexts();
  const wid = useUi((s) => s.wid);
  const lang = useUi((s) => s.lang);
  const ws = useWs().data;
  const dlg = useRef<HTMLDialogElement>(null);
  const [lay, setLay] = useState<"both" | "charts" | "table">("both");
  const [filter, setFilter] = useState<Filter>("all");
  const [goto, setGoto] = useState<{ t: number; n: number } | null>(null);
  const [gv, setGv] = useState("");
  const [tot, setTot] = useState<PreviewT | null>(null);
  const [counts, setCounts] = useState({ warn: 0, mv: 0 });
  useEffect(() => { dlg.current?.showModal(); }, []);
  const [range, setRange] = useState<[number, number]>([0, 0]);
  const onTotals = useCallback((p: PreviewT) => { setTot(p); if (p.n_all === p.total) setCounts({ warn: p.n_warn, mv: p.n_mv }); }, []);
  const exportCsv = async () => {
    const data = await bytes("GET", `/workspaces/${wid}/preview/csv`);
    const url = URL.createObjectURL(new Blob([data], { type: "text/csv" }));
    const a = document.createElement("a");
    a.href = url; a.download = "data_resampled.csv"; a.click();
    URL.revokeObjectURL(url);
  };
  const go = () => { const v = Number(gv.replace(",", ".")); if (gv.trim() !== "" && Number.isFinite(v)) setGoto((g) => ({ t: v, n: (g?.n ?? 0) + 1 })); };
  const nCols = (tot?.columns.length ?? 0) + 2;
  return (
    <dialog ref={dlg} className="dt-full" data-testid="full-preview" aria-label={T("prev_full_title", { f: ws?.fname ?? "" })}
      onClose={onClose} onClick={(e) => { if (e.target === dlg.current) dlg.current?.close(); }}>
      <div className="dtf-head">
        <h2>{T("prev_full_title", { f: (ws?.fname ?? "").split("|")[0] })}</h2>
        <span className="dt-sub">{T("ui_data_rows_cols", { n: (tot?.n_all ?? ws?.n ?? 0).toLocaleString(lang), c: nCols })}</span>
        <div className="dt-end">
          <Seg value={lay} options={["both", "charts", "table"] as const} onChange={setLay} label={T("ui_data_lay_both")}
            fmt={(v) => T(`ui_data_lay_${v}`)} small testid="full-lay" />
          <button type="button" className="dtf-x" aria-label={T("ui_data_close")} onClick={() => dlg.current?.close()}>×</button>
        </div>
      </div>
      <div className={`dtf-body ${lay === "both" ? "" : lay}`}>
        <div className="dtf-charts">{texts && <RecordViewer texts={texts} />}</div>
        <div className="dtf-tab">
          <div className="dtf-ctl">
            <label htmlFor="dtf-goto" title={T("h_prev_goto")}>{T("prev_goto")}</label>
            <input id="dtf-goto" value={gv} placeholder={T("prev_goto_ph")} data-testid="full-goto" onChange={(e) => setGv(e.target.value)}
              onBlur={go} onKeyDown={(e) => { if (e.key === "Enter") go(); }} />
            <select aria-label={T("prev_filter")} value={filter} data-testid="full-filter" onChange={(e) => setFilter(e.target.value as Filter)}>
              <option value="all">{T("prev_f_all")}</option>
              <option value="warn">{T("ui_data_f_warn", { n: counts.warn })}</option>
              <option value="mv">{T("ui_data_f_mv", { n: counts.mv })}</option>
            </select>
            <button type="button" className="btn" onClick={() => void exportCsv()} data-testid="full-export">{T("ui_data_export")}</button>
          </div>
          <Table filter={filter} goto={goto} onTotals={onTotals} onRange={setRange} />
          <div className="dtf-foot">
            <span>{T("ui_data_rows_range", { a: range[0].toLocaleString(lang), b: range[1].toLocaleString(lang), n: (tot?.total ?? 0).toLocaleString(lang) })} · {T("ui_data_scroll_note")}</span>
            <span className="dtf-leg">{T("ui_data_warn_legend")}</span>
          </div>
        </div>
      </div>
    </dialog>
  );
}
