// Data › Diagnostika › Všechny smyčky (E5): triáž smyček – dlaždice verdiktů jako filtry, „Kde začít“, tabulka smyček
// s metrikami, společná oscilace a detail s důkazy verdiktu. Výpočet běží na pozadí (POST /triage); prahy pravidel
// verdiktu jsou v panelu vpravo. Starší přehled smyček souboru (audit, správa smyček projektu) zůstává pod ním.
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { request } from "../api/client";
import type { components } from "../api/schema";
import { Card } from "../components/Card";
import { LabelHelp, PrimaryAction, SideCard } from "../components/Ui";
import { useWs, useWsQuery } from "../data";
import { useT } from "../i18n";
import { useJobRunner } from "../jobs";
import { useUi } from "../store";
import { LoopsMain, LoopsSide } from "./LoopsTab";
import "../styles/tri.css";

export type TriageResult = components["schemas"]["TriageResult"];
type Row = components["schemas"]["TriageLoop"];
type Thresholds = components["schemas"]["Thresholds"];

/** Verdikty v pořadí dlaždic (shodně s registrem pravidel na serveru). */
export const VERDICTS = ["valve", "cascade", "foreign", "nonlinear", "tune", "low_auto", "ok"] as const;
export type Verdict = (typeof VERDICTS)[number];

const num = (x: unknown, n = 2) => (typeof x === "number" && Number.isFinite(x) ? String(+x.toPrecision(n)) : "–");
const met = (r: Row, k: string) => (r.metrics as Record<string, unknown>)[k];

/** Poslední výsledek triáže (prázdný, dokud neběžela). */
export function useTriage() {
  return useWsQuery<TriageResult>("triage", "/triage");
}

/** Otevře smyčku (nastaví ji aktivní) a přepne na cílové místo. */
function useOpenLoop() {
  const wid = useUi((s) => s.wid);
  const qc = useQueryClient();
  const { setTab, setDataSub } = useUi();
  return async (index: number, to: "diag-detail" | "tuning" | "apc" | "sources") => {
    await request("PUT", `/workspaces/${wid}/loops/active`, { index });
    await qc.invalidateQueries({ queryKey: ["ws", wid] });
    if (to === "tuning" || to === "apc") setTab(to); else setDataSub(to);
  };
}

const goOf = (v: string): "diag-detail" | "tuning" | "apc" | "sources" =>
  v === "tune" || v === "cascade" ? "tuning" : v === "nonlinear" ? "apc" : v === "low_auto" ? "sources" : "diag-detail";
const goLabel = { "diag-detail": "tri_btn_detail", tuning: "tri_btn_tuning", apc: "tri_btn_apc", sources: "tri_btn_data" } as const;

function Pill({ v }: { v: string }) {
  const T = useT();
  return <span className={`vpill v-${v}`} title={T(`tri_vd_${v}`)} data-verdict={v}>{T(`tri_v_${v}`)}</span>;
}

function Tiles({ res, f, setF }: { res: TriageResult; f: string; setF: (v: string) => void }) {
  const T = useT();
  return (
    <Card title={T("tri_tiles", { n: res.loops.length })} help="tri_h_tiles" testid="tri-tiles"
      right={f !== "all" && <button type="button" className="link" onClick={() => setF("all")} data-testid="tri-clear">{T("tri_clear")}</button>}>
      <div className="vtiles">
        {VERDICTS.map((v) => (
          <button key={v} type="button" className={`vtile v-${v}`} aria-pressed={f === v} disabled={!res.counts[v]}
            title={T(`tri_vd_${v}`)} data-verdict={v} onClick={() => setF(f === v ? "all" : v)}>
            <b>{res.counts[v] ?? 0}</b><span>{T(`tri_v_${v}`)}</span>
          </button>))}
      </div>
    </Card>
  );
}

function Start({ res }: { res: TriageResult }) {
  const T = useT();
  const open = useOpenLoop();
  return (
    <Card title={T("tri_start")} help="tri_h_start" testid="tri-start">
      {res.start.length === 0 ? <p className="muted">{T("tri_start_none")}</p> : (
        <ol className="tri-start">
          {res.start.map((i) => {
            const r = res.loops[i];
            const go = goOf(r.verdict);
            return (
              <li key={i}>
                <span>{T(`tri_start_${r.verdict}`, { tag: r.tag })}</span>
                <button type="button" className="btn small" onClick={() => void open(i, go)} data-testid={`tri-start-${i}`}>{T(goLabel[go])}</button>
              </li>);
          })}
        </ol>)}
    </Card>
  );
}

function Common({ res }: { res: TriageResult }) {
  const T = useT();
  return (
    <Card title={T("tri_common")} help="tri_h_common" testid="tri-common">
      {res.common.length === 0 ? <p className="muted">{T("tri_common_none")}</p> : res.common.map((g, k) => (
        <p key={k} className="tri-common">
          <span className="ltag warn">!</span>{" "}
          {T("tri_common_text", {
            p: `${num(g.period, 3)} s`, loops: g.loops.map((i) => res.loops[i].tag).join(", "), src: res.loops[g.source].tag,
            why: T(g.by_stiction ? "tri_common_stic" : "tri_common_amp"),
          })}
        </p>))}
    </Card>
  );
}

function Detail({ r }: { r: Row | undefined }) {
  const T = useT();
  const open = useOpenLoop();
  return (
    <Card title={r ? T("tri_detail", { tag: r.tag }) : T("tri_title")} help="tri_h_detail" testid="tri-detail"
      right={r && <><Pill v={r.verdict} />{" "}<button type="button" className="btn small" onClick={() => void open(r.index, "diag-detail")}
        data-testid="tri-open-detail">{T("tri_detail_open")}</button></>}>
      {!r ? <p className="muted">{T("tri_detail_none")}</p> : (
        <ul className="tri-ev">
          {r.evidence.map((e, k) => (
            <li key={k}><span className={`ltag ${r.severity >= 2 ? "warn" : r.severity === 0 ? "ok" : "info"}`}>{e.metric}</span> {e.text}</li>))}
        </ul>)}
    </Card>
  );
}

function Table({ res, f, sel, setSel }: { res: TriageResult; f: string; sel: number | null; setSel: (i: number) => void }) {
  const T = useT();
  const open = useOpenLoop();
  const rank = (r: Row) => res.start.indexOf(r.index);
  const rows = res.loops.filter((r) => f === "all" || r.verdict === f)
    .sort((a, b) => (rank(a) < 0 ? 99 : rank(a)) - (rank(b) < 0 ? 99 : rank(b)) || a.index - b.index);
  return (
    <Card title={T("tri_loops")} help="tri_h_table" testid="tri-table" right={<span className="muted small">{T("tri_sorted")}</span>}>
      <div className="lscroll"><table className="ltbl">
        <thead><tr>{["loop", "auto", "perf", "osc", "valve", "nl", "dq", "verdict", "action"].map((c) => <th key={c}>{T(`tri_c_${c}`)}</th>)}</tr></thead>
        <tbody>{rows.map((r) => {
          const go = goOf(r.verdict);
          const stic = met(r, "stic_ratio"), hy = met(r, "hyst_pct");
          return (
            <tr key={r.index} className={"pick" + (sel === r.index ? " sel" : "")} onClick={() => setSel(r.index)} data-testid={`tri-row-${r.index}`}>
              <td><b>{r.tag}</b></td>
              <td className="mono">{num(met(r, "auto_pct"), 3)} %</td>
              <td className="mono">{met(r, "harris") == null ? "–" : `Harris ${num(met(r, "harris"))}`}</td>
              <td className="mono">{met(r, "osc") ? `${num(met(r, "period"), 3)} s` : "–"}</td>
              <td className="mono">{[met(r, "stic") === "likely" ? `stic ${num(stic)}` : null,
                hy == null ? null : `hyst ${num(hy)} %`].filter(Boolean).join(" · ") || "–"}</td>
              <td className="mono">{met(r, "nonlin") == null ? "–" : `${num(met(r, "nonlin"))}×`}</td>
              <td className="mono">{num(100 - Number(met(r, "nan_pct") ?? 0), 3)} %</td>
              <td><Pill v={r.verdict} /></td>
              <td><button type="button" className="btn small" onClick={(e) => { e.stopPropagation(); void open(r.index, go); }}>{T(goLabel[go])}</button></td>
            </tr>);
        })}</tbody>
      </table></div>
      <p className="muted small">{T("tri_foot", { n: rows.length, m: res.loops.length })}</p>
    </Card>
  );
}

export function TriageMain() {
  const T = useT();
  const ws = useWs().data;
  const res = useTriage().data;
  const [f, setF] = useState("all");
  const [sel, setSel] = useState<number | null>(null);
  if (!ws?.has_data) return <div className="card muted" data-testid="no-data">{T("ui_no_data")}</div>;
  return (
    <div className="stack">
      <p className="muted" data-testid="tri-intro">{T("tri_intro")}</p>
      {!res?.ready ? <div className="card muted" data-testid="tri-empty">{T("tri_none")}</div> : (
        <>
          <Tiles res={res} f={f} setF={setF} />
          <Start res={res} />
          <Table res={res} f={f} sel={sel} setSel={setSel} />
          <Common res={res} />
          <Detail r={sel == null ? undefined : res.loops[sel]} />
        </>)}
      <details className="tri-legacy" open>
        <summary>{T("ui_lp_title")}</summary>
        <LoopsMain />
      </details>
    </div>
  );
}

function ThresholdCard() {
  const T = useT();
  const wid = useUi((s) => s.wid);
  const qc = useQueryClient();
  const q = useWsQuery<Thresholds>("tri-thr", "/triage/thresholds");
  const [draft, setDraft] = useState<Record<string, string>>({});
  if (!q.data) return null;
  const save = async (rule: string, name: string, v: string) => {
    if (v.trim() === "" || !Number.isFinite(+v)) { setDraft((d) => { const n = { ...d }; delete n[`${rule}.${name}`]; return n; }); return; }
    await request("PUT", `/workspaces/${wid}/triage/thresholds`, { values: { [rule]: { [name]: +v } } });
    setDraft((d) => { const n = { ...d }; delete n[`${rule}.${name}`]; return n; });
    await qc.invalidateQueries({ queryKey: ["ws", wid, "tri-thr"] });
  };
  return (
    <SideCard title={T("tri_thr_title")} help={T("tri_h_thr")} testid="tri-thr">
      {q.data.items.map((it) => {
        const k = `${it.rule}.${it.name}`;
        return (
          <label key={k} className="field">
            <span className="lbl"><span>{T(it.name_label)}{it.unit ? ` [${it.unit}]` : ""}</span><LabelHelp text={T(`tri_vd_${it.rule}`)} /></span>
            <input type="number" step="any" min={it.lo} max={it.hi} aria-label={T(it.name_label)} value={draft[k] ?? String(+it.value.toPrecision(4))}
              data-testid={`tri-thr-${k}`} onChange={(e) => setDraft((d) => ({ ...d, [k]: e.target.value }))}
              onBlur={() => { if (k in draft) void save(it.rule, it.name, draft[k]); }}
              onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }} />
          </label>);
      })}
      <div className="muted small">{T("tri_thr_hint")}</div>
    </SideCard>
  );
}

export function TriageSide() {
  const T = useT();
  const ws = useWs().data;
  const run = useJobRunner();
  const res = useTriage().data;
  const [busy, setBusy] = useState(false);
  if (!ws?.has_data) return null;
  const go = async () => { setBusy(true); try { await run("/triage", undefined, T("tri_running")); } finally { setBusy(false); } };
  return (
    <>
      <PrimaryAction onClick={() => void go()} disabled={busy} testid="tri-run" title={T("tri_h_run")}>
        {busy ? T("tri_running") : T(res?.ready ? "tri_rerun" : "tri_run")}
      </PrimaryAction>
      <ThresholdCard />
      <LoopsSide />
    </>
  );
}
