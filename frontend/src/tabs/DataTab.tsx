// Záložka Data: prohlížeč záznamu (hlavní plocha) a panel – zdroj dat, sloupce smyčky, kvalita dat, MAN / AUTO.
import { useState } from "react";
import { ApiError } from "../api/client";
import { RecordViewer } from "../components/RecordViewer";
import { type Columns, type LoopMode, type Quality, uploadFile, useWs, useWsMutation, useWsQuery } from "../data";
import { useT, useTexts } from "../i18n";
import { useUi } from "../store";
import { useQueryClient } from "@tanstack/react-query";

export function DataMain() {
  const T = useT();
  const texts = useTexts();
  const ws = useWs().data;
  if (!ws?.has_data) return <div className="card muted" data-testid="no-data">{T("ui_no_data")}</div>;
  return texts ? <RecordViewer texts={texts} /> : null;
}

const NONE = "—";

function ColumnSelect({ label, value, options, onChange, optional, testid }: {
  label: string; value: string | null | undefined; options: string[]; onChange: (v: string) => void;
  optional?: boolean; testid: string;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      <select value={value ?? NONE} onChange={(e) => onChange(e.target.value)} data-testid={testid}>
        {optional && <option value={NONE}>{NONE}</option>}
        {options.map((c) => <option key={c} value={c}>{c}</option>)}
      </select>
    </label>
  );
}

export function DataSide() {
  const T = useT();
  const wid = useUi((s) => s.wid);
  const qc = useQueryClient();
  const ws = useWs().data;
  const demo = useWsMutation("POST", "/data/demo");
  const cols = useWsMutation<Columns>("PUT", "/columns");
  const quality = useWsQuery<Quality>("quality", "/quality");
  const lm = useWsQuery<LoopMode>("loopmode", "/loopmode");
  const [err, setErr] = useState<string | null>(null);

  async function onFile(f: File | undefined) {
    if (!f || !wid) return;
    setErr(null);
    try {
      await uploadFile(wid, f);
      await qc.invalidateQueries({ queryKey: ["ws", wid] });
    } catch (e) {
      setErr(e instanceof ApiError ? T(e.message) : String(e));
    }
  }
  const set = (patch: Partial<Columns>) => {
    if (!ws?.pv || !ws?.mv) return;
    const cur: Columns = { pv: ws.pv, mv: ws.mv, sp: ws.sp ?? null, dists: ws.dists ?? [], pos: ws.pos ?? null };
    const next = { ...cur, ...patch };
    cols.mutate({ ...next, sp: next.sp === NONE ? null : next.sp, pos: next.pos === NONE ? null : next.pos });
  };
  const options = ws?.columns ?? [];

  return (
    <div className="stack">
      <section>
        <div className="row">
          <button className="btn" onClick={() => demo.mutate(undefined)} data-testid="load-demo">{T("src_demo")}</button>
          <label className="btn">
            {T("src_file")}
            <input type="file" accept=".csv,.txt,.xlsx,.xls" hidden data-testid="load-file"
              onChange={(e) => void onFile(e.target.files?.[0])} />
          </label>
        </div>
        <div className="muted small">{T("upload")}</div>
        {err && <div className="err small" role="alert">{err}</div>}
        {ws?.has_data && <div className="small mono" data-testid="data-info">{ws.fname} · {ws.n} · Ts {ws.Ts?.toPrecision(4)} s</div>}
      </section>
      {ws?.has_data && (
        <section>
          <ColumnSelect label="PV" value={ws.pv} options={options} onChange={(v) => set({ pv: v })} testid="col-pv" />
          <ColumnSelect label="MV" value={ws.mv} options={options} onChange={(v) => set({ mv: v })} testid="col-mv" />
          <ColumnSelect label={T("col_sp")} value={ws.sp} options={options} optional onChange={(v) => set({ sp: v })}
            testid="col-sp" />
          <label className="field">
            <span>{T("col_dist")}</span>
            <select multiple value={ws.dists ?? []} data-testid="col-d"
              onChange={(e) => set({ dists: Array.from(e.target.selectedOptions, (o) => o.value) })}>
              {options.filter((c) => c !== ws.pv && c !== ws.mv && c !== ws.sp).map((c) => <option key={c}>{c}</option>)}
            </select>
          </label>
          <ColumnSelect label={T("col_pos")} value={ws.pos} options={options} optional onChange={(v) => set({ pos: v })}
            testid="col-pos" />
        </section>
      )}
      {quality.data && (
        <section data-testid="quality">
          <h3>{T("q_title")}</h3>
          <ul className="checks">
            {quality.data.checks.map((c) => (
              <li key={c.key} className={c.level >= 2 ? "err" : c.level === 1 ? "warn" : "ok"}>{T(c.key, c.args)}</li>
            ))}
          </ul>
        </section>
      )}
      {lm.data && (
        <section className="small muted" data-testid="loopmode">
          {T("lm_status", { a: Math.round(100 * lm.data.auto_frac), m: 100 - Math.round(100 * lm.data.auto_frac) })}
        </section>
      )}
    </div>
  );
}
