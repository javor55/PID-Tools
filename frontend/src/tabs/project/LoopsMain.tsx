// Karta „Loops in the project“ (FEATURE-007): souhrn smyček projektu, výběr a hromadné akce (identifikace, ladění jen
// jako návrh, převzetí návrhů do Setu 2, export sad) s průběhem ve stavovém řádku a souhrnem výsledku.
import { useEffect, useRef, useState } from "react";
import { bytes } from "../../api/client";
import type { components } from "../../api/schema";
import { Card } from "../../components/Card";
import { QueryState } from "../../components/QueryState";
import { toastError } from "../../components/Toasts";
import { Seg } from "../../components/Ui";
import { useSettings, useWsMutation } from "../../data";
import { useDec, useT } from "../../i18n";
import { rowPick } from "../../lib/a11y";
import { saveAs } from "../../start/project";
import { useUi } from "../../store";
import { useLoopsOverview } from "../LoopsTab";
import { fnum } from "../TuningMore";
import { type BatchParams, type BatchRow, useBatchOut, useBatchRun, useBatchUi } from "./batch";

type Row = components["schemas"]["LoopRow"];
type Reason = components["schemas"]["BatchReason"];

const METHODS = ["SIMC", "iSIMC", "Lambda", "AMIGO", "OPT", "AVG"] as const;     // metody Ladění (tun.methods); platnost pro model hlídá server
const CRITERIA = ["MIGO", "IAE", "ISE", "ITAE", "OVS"] as const;
const TARGETS = ["scen", "dist", "sp", "both"] as const;
// formáty hromadného exportu = formáty exportu jedné sady (app.tuning_export.FORMATS) a přípony souboru ze serveru
const EXPORT_EXT: Record<string, string> = { csv: "csv", pcs7: "txt", tia: "scl", deltav: "tsv" };
const STAGE_CLASS: Record<Row["stage"], string> = { no_data: "err", data: "warn", model: "", proposal: "warn", set2: "ok" };

/** Text důvodu přeskočení / chyby: klíč i18n z kontrol kvality dat nebo `batch_*` + argumenty. */
function useReasonText() {
  const T = useT();
  return (r: Reason | null | undefined) => (r ? T(r.key, r.args) : "");
}

/** Dialog s volbami ladění (stejné volby jako v Ladění: metoda, typ regulátoru, kritérium a cíl optimalizace). */
function TuneDialog({ onClose, onRun }: { onClose: () => void; onRun: (p: BatchParams) => void }) {
  const T = useT();
  const st = useSettings().data ?? {};
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => { ref.current?.showModal(); }, []);
  const [method, setMethod] = useState("");                                        // "" = metoda uložená u modelu každé smyčky
  const [ctype, setCtype] = useState<"PI" | "PID">(st.ctype === "PID" ? "PID" : "PI");
  const [crit, setCrit] = useState<(typeof CRITERIA)[number]>((CRITERIA as readonly string[]).includes(String(st.opt_crit)) ? String(st.opt_crit) as (typeof CRITERIA)[number] : "OVS");
  const [target, setTarget] = useState<(typeof TARGETS)[number]>((TARGETS as readonly string[]).includes(String(st.opt_target)) ? String(st.opt_target) as (typeof TARGETS)[number] : "both");
  const opt = method === "OPT";
  const run = () => {
    onRun({ ...(method ? { method } : {}), ctype, ...(opt ? { crit, ...(crit !== "MIGO" ? { target } : {}) } : {}) });
    ref.current?.close();
  };
  return (
    <dialog ref={ref} className="batch" onClose={onClose} data-testid="batch-tune-dialog" aria-labelledby="batch-tune-title">
      <div className="stack">
        <h3 id="batch-tune-title">{T("bt_tune_title")}</h3>
        <div className="muted small">{T("bt_tune_help")}</div>
        <label className="trow"><span>{T("method")}</span>
          <select value={method} onChange={(e) => setMethod(e.target.value)} data-testid="batch-method" aria-label={T("method")}>
            <option value="">{T("bt_tune_default")}</option>
            {METHODS.map((x) => <option key={x} value={x}>{T("m_" + x)}</option>)}</select></label>
        <div className="trow"><span>{T("ctrl_type")}</span>
          <Seg<"PI" | "PID"> value={ctype} options={["PI", "PID"]} onChange={setCtype} label={T("ctrl_type")} small testid="batch-ctype" /></div>
        {opt && <label className="trow"><span>{T("opt_crit")}</span>
          <select value={crit} onChange={(e) => setCrit(e.target.value as typeof crit)} data-testid="batch-crit" aria-label={T("opt_crit")}>
            {CRITERIA.map((x) => <option key={x} value={x}>{T("crit_" + x)}</option>)}</select></label>}
        {opt && crit !== "MIGO" && <label className="trow"><span>{T("opt_target")}</span>
          <select value={target} onChange={(e) => setTarget(e.target.value as typeof target)} data-testid="batch-target" aria-label={T("opt_target")}>
            {TARGETS.map((x) => <option key={x} value={x}>{T("tgt_" + x)}</option>)}</select></label>}
        <div className="row">
          <button type="button" className="btn primary" onClick={run} data-testid="batch-tune-run">{T("bt_tune_run")}</button>
          <button type="button" className="btn" onClick={() => ref.current?.close()} data-testid="batch-tune-close">{T("ui_close")}</button>
        </div>
      </div>
    </dialog>
  );
}

/** Dialog exportu: formát a sada; vyexportují se vybrané smyčky s modelem, ostatní se jen vyjmenují. */
function ExportDialog({ rows, onClose }: { rows: Row[]; onClose: () => void }) {
  const T = useT();
  const wid = useUi((s) => s.wid);
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => { ref.current?.showModal(); }, []);
  const [fmt, setFmt] = useState<keyof typeof EXPORT_EXT>("csv");
  const [n, setN] = useState(2);
  const withModel = rows.filter((r) => r.model);
  const without = rows.filter((r) => !r.model);
  const go = async () => {
    try {
      const buf = await bytes("GET", `/workspaces/${wid}/batch/export?fmt=${fmt}&n=${n}&loops=${withModel.map((r) => r.index).join(",")}`);
      saveAs(`tuning_set${n}_${fmt}_loops.${EXPORT_EXT[fmt]}`, new Blob(["﻿", buf]), "text/plain;charset=utf-8");
      ref.current?.close();
    } catch (e) { toastError(e); }
  };
  return (
    <dialog ref={ref} className="batch" onClose={onClose} data-testid="batch-export-dialog" aria-labelledby="batch-exp-title">
      <div className="stack">
        <h3 id="batch-exp-title">{T("bt_exp_title")}</h3>
        <div className="muted small">{T("tun_ui_exp_help")}</div>
        <label className="trow"><span>{T("tun_ui_exp_fmt")}</span>
          <select value={fmt} onChange={(e) => setFmt(e.target.value)} data-testid="batch-export-fmt" aria-label={T("tun_ui_exp_fmt")}>
            {Object.keys(EXPORT_EXT).map((x) => <option key={x} value={x}>{T("tun_ui_exp_" + x)}</option>)}</select></label>
        <label className="trow"><span>{T("tun_ui_exp_set")}</span>
          <select value={n} onChange={(e) => setN(+e.target.value)} data-testid="batch-export-set" aria-label={T("tun_ui_exp_set")}>
            {[1, 2].map((x) => <option key={x} value={x}>{T("set_" + x)}</option>)}</select></label>
        {without.length > 0 && withModel.length > 0 && (
          <div className="small" data-testid="batch-export-note">{T("bt_exp_note", { names: without.map((r) => r.name).join(", ") })}</div>)}
        {withModel.length === 0 && <div className="err small" role="alert" data-testid="batch-export-none">{T("bt_exp_none")}</div>}
        <div className="row">
          <button type="button" className="btn primary" disabled={withModel.length === 0} onClick={() => void go()}
            data-testid="batch-export-go">{T("tun_ui_exp_go")}</button>
          <button type="button" className="btn" onClick={() => ref.current?.close()} data-testid="batch-export-close">{T("ui_close")}</button>
        </div>
      </div>
    </dialog>
  );
}

/** Souhrn poslední úlohy: počty ok / přeskočeno / chyba a důvody u smyček, které neprošly. */
function Summary() {
  const T = useT();
  const last = useBatchUi((s) => s.last);
  const out = useBatchOut(last?.jid ?? null);
  const reason = useReasonText();
  if (!last) return null;
  return (
    <div className="bt-sum" data-testid="proj-batch-summary">
      <QueryState q={out}>{(d) => {
        const n = (s: BatchRow["status"]) => d.rows.filter((r) => r.status === s).length;
        const bad = d.rows.filter((r) => r.status !== "ok");
        return (
          <>
            <div className="bt-sum-head"><b>{T("bt_res_title")}</b>{" · "}{T("bt_job_" + d.action)}{" · "}
              <span data-testid="batch-counts" data-ok={n("ok")} data-skipped={n("skipped")} data-error={n("error")}>
                {T("bt_res_counts", { ok: n("ok"), skipped: n("skipped"), error: n("error") })}</span></div>
            {d.job.state === "cancelled" && <div className="small" role="status" data-testid="batch-cancelled">{T("bt_res_cancelled")}</div>}
            {(d.job.state === "error" || d.job.state === "timeout") && <div className="err small" role="alert">{T("bt_res_failed", { text: d.job.error ?? d.job.state })}</div>}
            {bad.length > 0 && (
              <ul className="bt-reasons" data-testid="batch-reasons">{bad.map((r) => (
                <li key={r.loop} data-testid={`batch-reason-${r.loop}`} data-status={r.status}>
                  <span className={"ltag " + (r.status === "error" ? "err" : "warn")}>{T("bt_res_" + r.status)}</span>{" "}
                  <b>{r.name}</b>: {reason(r.reason)}</li>))}</ul>)}
          </>);
      }}</QueryState>
    </div>
  );
}

export function LoopsMain() {
  const T = useT();
  const dec = useDec();
  const ov = useLoopsOverview();
  const { sel, setSel, onlyProblems, setOnlyProblems, running, last } = useBatchUi();
  const run = useBatchRun();
  const lastOut = useBatchOut(last?.jid ?? null);
  const activate = useWsMutation<{ index: number }>("PUT", "/loops/active");
  const [dlg, setDlg] = useState<"tune" | "export" | null>(null);
  const rows = ov.data?.loops ?? [];
  const picked = sel.filter((i) => i < rows.length);
  const isPicked = (i: number) => picked.includes(i);
  const toggle = (i: number) => setSel(isPicked(i) ? picked.filter((x) => x !== i) : [...picked, i].sort((a, b) => a - b));
  const status = new Map<number, BatchRow["status"]>((lastOut.data?.rows ?? []).map((r) => [r.loop, r.status]));
  const problem = (r: Row) => status.get(r.index) === "skipped" || status.get(r.index) === "error" || !r.health.ok || r.health.score > 0;
  const shown = onlyProblems ? rows.filter(problem) : rows;
  const none = picked.length === 0 || running;
  const chosen = rows.filter((r) => isPicked(r.index));
  const g3 = (x: number | null | undefined) => fnum(x, dec, 3);
  const pick = async (i: number) => {
    try { await activate.mutateAsync({ index: i }); } catch (e) { toastError(e); }
  };
  return (
    <Card title={T("bt_title")} help={T("bt_help")} testid="proj-loops" busy={running || ov.isFetching}>
      <div className="row bt-actions" role="toolbar" aria-label={T("bt_title")}>
        <button type="button" className="btn" disabled={none} title={picked.length ? T("bt_identify_h") : T("bt_need_sel")}
          onClick={() => void run("identify", picked)} data-testid="batch-identify">{T("bt_identify")}</button>
        <button type="button" className="btn" disabled={none} title={picked.length ? T("bt_tune_h") : T("bt_need_sel")}
          onClick={() => setDlg("tune")} data-testid="batch-tune">{T("bt_tune")}</button>
        <button type="button" className="btn" disabled={none} title={picked.length ? T("bt_accept_h") : T("bt_need_sel")}
          onClick={() => void run("accept", picked)} data-testid="batch-accept">{T("bt_accept")}</button>
        <button type="button" className="btn" disabled={none} title={picked.length ? T("bt_export_h") : T("bt_need_sel")}
          onClick={() => setDlg("export")} data-testid="batch-export">{T("bt_export")}</button>
        <span className="muted small" data-testid="batch-selected">{T("bt_selected", { n: picked.length })}</span>
        <label className="small bt-filter" title={T("bt_only_problems_h")}>
          <input type="checkbox" checked={onlyProblems} onChange={(e) => setOnlyProblems(e.target.checked)} data-testid="batch-only-problems" />{" "}
          {T("bt_only_problems")}</label>
      </div>
      <QueryState q={ov} empty={(d) => d.loops.length === 0} emptyText={T("bt_empty")}>{() => (
        <div className="lscroll">
          <table className="ltbl bt-table" data-testid="proj-loops-table">
            <thead><tr>
              <th><input type="checkbox" aria-label={T("bt_pick_all")} data-testid="batch-pick-all"
                checked={rows.length > 0 && picked.length === rows.length}
                onChange={(e) => setSel(e.target.checked ? rows.map((r) => r.index) : [])} /></th>
              <th>{T("bt_col_loop")}</th><th>{T("bt_col_io")}</th><th>{T("bt_col_model")}</th><th>{T("bt_col_sets")}</th>
              <th className="r">{T("bt_col_change")}</th><th className="r">{T("bt_col_ms")}</th><th>{T("bt_col_stage")}</th></tr></thead>
            <tbody>{shown.map((r) => {
              const st = status.get(r.index);
              return (
                <tr key={r.index} className={"pick" + (r.active ? " sel" : "")} data-testid={`proj-loop-${r.index}`} data-active={r.active}
                  data-stage={r.stage} data-batch={st} {...rowPick(() => toggle(r.index), isPicked(r.index))}>
                  <td><input type="checkbox" checked={isPicked(r.index)} aria-label={T("bt_pick_one", { name: r.name })}
                    data-testid={`batch-pick-${r.index}`} onClick={(e) => e.stopPropagation()} onChange={() => toggle(r.index)} /></td>
                  <td><button type="button" className="link bt-name" title={T("bt_activate", { name: r.name })}
                    data-testid={`proj-loop-name-${r.index}`} onClick={(e) => { e.stopPropagation(); void pick(r.index); }}>
                    {r.name}</button>{r.active && <b title={T("ui_lp_active")}> ●</b>}</td>
                  <td className="mono small">{r.pv ?? "—"} / {r.mv ?? "—"}</td>
                  <td data-testid={`proj-loop-model-${r.index}`}>{r.model
                    ? <><span title={T("model_" + r.model)}>{r.model}</span> <span className="mono small">{g3(r.fit)} %</span></>
                    : <span className="muted">{T("ui_lp_no_model")}</span>}</td>
                  <td className="mono small" data-testid={`proj-loop-sets-${r.index}`}>
                    {r.set1_defined ? `${g3(r.set1.gain)} / ${g3(r.set1.ti)}` : "—"} → {r.set2_defined ? `${g3(r.set2.gain)} / ${g3(r.set2.ti)}` : "—"}</td>
                  <td className="r mono small" data-testid={`proj-loop-change-${r.index}`}>
                    {r.change_pct === null || r.change_pct === undefined ? "—" : `${r.change_pct > 0 ? "+" : ""}${fnum(r.change_pct, dec, 3)} %`}</td>
                  <td className="r mono small" data-testid={`proj-loop-ms-${r.index}`}>{g3(r.ms)}</td>
                  <td><span className={"ltag " + STAGE_CLASS[r.stage]} data-testid={`proj-loop-stage-${r.index}`}>{T("bt_stage_" + r.stage)}</span></td>
                </tr>);
            })}</tbody>
          </table>
          {shown.length === 0 && <div className="muted small" data-testid="batch-no-rows">{T("bt_no_rows")}</div>}
        </div>)}
      </QueryState>
      <Summary />
      {dlg === "tune" && <TuneDialog onClose={() => setDlg(null)} onRun={(p) => void run("tune", picked, p)} />}
      {dlg === "export" && <ExportDialog rows={chosen} onClose={() => setDlg(null)} />}
    </Card>
  );
}
