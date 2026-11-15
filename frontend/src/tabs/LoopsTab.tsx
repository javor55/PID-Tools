// Záložka Přehled smyček (M20): smyčky projektu (aktivní, přidání, odebrání, sloupce, model, sady, stav) a přehled smyček
// souboru (audit: pořadí podle problémů, společné oscilace, detail); panel: smyčky přehledu, okno a spuštění analýzy.
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { request } from "../api/client";
import type { components } from "../api/schema";
import { Card } from "../components/Card";
import { LineChart } from "../components/LineChart";
import { Md, PrimaryAction, SideCard, Seg } from "../components/Ui";
import { useWs, useWsQuery } from "../data";
import { useT } from "../i18n";
import { Bold } from "./apc/common";
import { useUi } from "../store";
import "../styles/loops.css";

type Overview = components["schemas"]["LoopsOverview"];
type Row = components["schemas"]["LoopRow"];
type AuditLoop = components["schemas"]["AuditLoop"];
type AuditLoops = components["schemas"]["AuditLoops"];
type AuditResult = components["schemas"]["AuditResult"];
type Problem = components["schemas"]["AuditProblem"];

const NONE = "—";
const g = (x: unknown, n: number) => (typeof x === "number" && Number.isFinite(x) ? String(+x.toPrecision(n)) : "—");

/** Stav smyčky jako štítky: problémy přehledu (závažné ×, ostatní !), jinak „bez nalezeného problému“; neúspěch výpočtu. */
function useProblems() {
  const T = useT();
  return (ok: boolean, err: string | null | undefined, probs: Problem[]) =>
    !ok ? <span className="ltag err">{T(err || "err_fit_failed")}</span> : probs.length
      ? <>{probs.map((p) => <span key={p.key} className={`ltag ${p.severity >= 3 ? "err" : "warn"}`}>{p.severity >= 3 ? "×" : "!"} {T("au_p_" + p.key)}</span>)}</>
      : <span className="ltag ok">✓ {T("au_ok")}</span>;
}
const scoreClass = (ok: boolean, s: number) => (!ok ? "" : s >= 6 ? "err" : s >= 3 ? "warn" : s === 0 ? "ok" : "");
function ScoreBar({ ok, score, testid }: { ok: boolean; score: number; testid?: string }) {
  const c = scoreClass(ok, score);
  return (
    <span className="lscore">
      <span className="lbar"><i className={c} style={{ width: `${ok ? Math.min(100, score * 11) : 0}%` }} /></span>
      <span className={`mono ${c}`} data-testid={testid}>{ok ? score : "—"}</span>
    </span>
  );
}

export function useLoopsOverview() {
  return useWsQuery<Overview>("loopsov", "/loops/overview");
}

/** Smyčky projektu jen pro čtení (úpravy jsou ve Zdrojích a smyčkách); přepnutí aktivní smyčky. */
function ProjectLoops() {
  const T = useT();
  const wid = useUi((s) => s.wid);
  const qc = useQueryClient();
  const setDataSub = useUi((s) => s.setDataSub);
  const ov = useLoopsOverview();
  const problems = useProblems();
  const activate = async (i: number) => {
    await request("PUT", `/workspaces/${wid}/loops/active`, { index: i });
    await qc.invalidateQueries({ queryKey: ["ws", wid] });
  };
  return (
    <Card title={T("ui_lp_title")} help={T("ui_lp_help")} testid="loops-card"
      right={<button type="button" className="dt-linkbtn" title={T("dq_loop_edit_h")} data-testid="loops-edit"
        onClick={() => setDataSub("sources")}>{T("ui_lp_edit")}</button>}>
      {ov.data && (
        <div className="lscroll"><table className="ltbl" data-testid="loops-table">
          <thead><tr><th>#</th><th>{T("au_c_name")}</th><th>PV</th><th>MV</th><th>SP</th><th>{T("pos_short")}</th><th>{T("col_model")}</th>
            <th>{T("ui_lp_sets")}</th><th>{T("col_status")}</th><th /></tr></thead>
          <tbody>{ov.data.loops.map((r: Row) => (
            <tr key={r.index} className={r.active ? "sel" : ""} data-testid={`loop-row-${r.index}`} data-active={r.active}>
              <td>{r.index + 1}{r.active && <b title={T("ui_lp_active")}> ●</b>}</td>
              <td data-testid={`loop-name-${r.index}`}>{r.name}</td>
              <td className="mono">{r.pv}</td><td className="mono">{r.mv}</td>
              <td className="mono">{r.sp ?? NONE}</td><td className="mono">{r.pos ?? NONE}</td>
              <td>{r.model ? <span title={T("model_" + r.model)}>{r.model} <span className="mono">K={g(r.params[0], 4)}</span></span>
                : <span className="muted">{T("ui_lp_no_model")}</span>}</td>
              <td className="mono small">{[r.set1, r.set2].map((s, i) => `${i + 1}: ${g(s.gain, 4)} / ${g(s.ti, 4)} / ${g(s.td, 4)}`).join(" · ")}</td>
              <td className="ltags" data-testid={`loop-health-${r.index}`}>
                {r.health.ok && r.health.score > 0 ? <b className={scoreClass(true, r.health.score)}>{r.health.score} </b> : null}
                {problems(r.health.ok, r.health.err, r.health.problems)}</td>
              <td><button className="btn" disabled={r.active} data-testid={`loop-activate-${r.index}`} title={T("ui_lp_activate_h")}
                onClick={() => void activate(r.index)}>{T("ui_lp_activate")}</button></td>
            </tr>))}</tbody>
        </table></div>)}
    </Card>
  );
}

type SortKey = "name" | "score" | "std" | "iae" | "travel" | "rev" | "lim" | "frozen" | "period" | "harris";

function AuditResults() {
  const T = useT();
  const wid = useUi((s) => s.wid);
  const audit = useUi((s) => s.audit);
  const qc = useQueryClient();
  const setTab = useUi((s) => s.setTab);
  const defs = useWsQuery<AuditLoops>("auditloops", "/audit/loops");
  const problems = useProblems();
  const [sel, setSel] = useState(0);
  const [sort, setSort] = useState<{ k: SortKey; dir: 1 | -1 } | null>(null);
  const res = audit?.wid === wid ? audit.res : null;
  if (!res) return <div className="card muted small" data-testid="audit-hint">{T("au_hint")}</div>;
  const nbad = res.results.filter((r) => r.score > 0).length;
  const cur: AuditResult | undefined = res.results[Math.min(sel, res.results.length - 1)];
  const recOf = (r: AuditResult | undefined) => r && defs.data?.loops.find((x) => (x.name || x.pv) === r.name);
  const rec = recOf(cur);
  const open = async (x: AuditLoop | undefined) => {
    if (!x) return;
    await request("POST", `/workspaces/${wid}/loops`, { name: x.name, pv: x.pv, mv: x.mv, sp: x.sp, pos: x.pos });
    await qc.invalidateQueries({ queryKey: ["ws", wid] });
    setTab("model");
  };
  const kv = (r: AuditResult, k: SortKey): number | string => {
    const kp = (r.kpis ?? {}) as Record<string, number | string | null>;
    const m: Record<SortKey, number | string | null> = { name: r.name, score: r.ok ? r.score : null, std: kp.std_e, iae: kp.iae_h,
      travel: kp.travel_h, rev: kp.rev_h, lim: kp.at_lim, frozen: kp.frozen, period: kp.period, harris: kp.harris };
    const x = r.ok || k === "name" ? m[k] : null;
    return x === null || x === undefined ? -Infinity : x;
  };
  const order = res.results.map((r, i) => ({ r, i }));
  if (sort) order.sort((p, q) => {
    const x = kv(p.r, sort.k), y = kv(q.r, sort.k);
    return (x < y ? -1 : x > y ? 1 : 0) * sort.dir;
  });
  const th = (k: SortKey, label: string) => (
    <th scope="col" key={k} className={k === "name" ? "" : "r"} aria-sort={sort?.k === k ? (sort.dir === 1 ? "ascending" : "descending") : "none"}>
      <button type="button" className="lsort" onClick={() => setSort(sort?.k === k ? (sort.dir === 1 ? { k, dir: -1 } : null) : { k, dir: 1 })}>
        {label} <span aria-hidden="true">{sort?.k === k ? (sort.dir === 1 ? "↑" : "↓") : "↕"}</span></button></th>);
  return (
    <>
      <Card title={T("au_rank_title")} help={T("au_rank_help")} testid="audit-rank"
        right={<span className={`ltag ${nbad ? "err" : "ok"}`} data-testid="audit-nbad">{nbad ? "× " : "✓ "}{T("au_n_bad", { b: nbad, n: res.results.length })}</span>}>
        <div className="lscroll">
          <table className="ltbl" data-testid="audit-table">
            <thead><tr>{th("name", T("au_c_name"))}{th("score", T("au_score"))}<th scope="col">{T("au_problems")}</th>
              {th("std", T("au_std"))}{th("iae", T("au_iae"))}{th("travel", T("au_travel"))}{th("rev", T("au_rev"))}{th("lim", T("au_lim"))}
              {th("frozen", T("au_frozen"))}{th("period", T("au_period"))}<th scope="col">{T("au_stic")}</th>{th("harris", T("kpi_harris"))}</tr></thead>
            <tbody>{order.map(({ r, i }, row) => {
              const k = (r.kpis ?? {}) as Record<string, number | string | null>;
              return (
                <tr key={i} className={`pick ${i === sel ? "sel" : ""}`} data-testid={`audit-row-${row}`} onClick={() => setSel(i)}
                  onDoubleClick={() => void open(recOf(r))} title={T("au_open_help")}>
                  <td><b>{r.name}</b></td>
                  <td><ScoreBar ok={r.ok} score={r.score} testid={`audit-score-${row}`} /></td>
                  <td className="ltags">{problems(r.ok, r.err, r.problems)}</td>
                  <td className="r mono">{r.ok ? g(k.std_e, 4) : ""}</td><td className="r mono">{r.ok ? g(k.iae_h, 4) : ""}</td>
                  <td className="r mono">{r.ok ? g(k.travel_h, 4) : ""}</td><td className="r mono">{r.ok ? g(k.rev_h, 3) : ""}</td>
                  <td className="r mono">{r.ok ? Number(k.at_lim).toFixed(1) : ""}</td><td className="r mono">{r.ok ? Number(k.frozen).toFixed(1) : ""}</td>
                  <td className="r mono">{r.ok && k.period ? Number(k.period).toFixed(0) : r.ok ? "—" : ""}</td>
                  <td>{r.ok && k.stic ? T("stic_short_" + String(k.stic)) : r.ok ? "—" : ""}</td>
                  <td className="r mono">{r.ok ? (k.harris === null ? "—" : Number(k.harris).toFixed(2)) : ""}</td>
                </tr>);
            })}</tbody>
          </table>
        </div>
        <p className="dnote">{T("au_done", { n: res.results.length, b: nbad })}</p>
      </Card>
      <Card title={T("au_common_title")} help={T("au_common_help")} testid="audit-common">
        {res.common.length
          ? res.common.map((c, i) => (
            <div key={i} className="lrow" data-testid={`audit-common-${i}`}><span className="ltag warn">! {T("au_common_chip")}</span>
              <span><Bold text={T("au_common", { p: Math.round(c.period), l: c.loops.join(", "), s: c.source })} />
                {c.by_stiction ? ` ${T("au_common_stic")}` : ""}</span></div>))
          : <div className="small muted" data-testid="audit-common-none">{T("au_common_none")}</div>}
      </Card>
      {cur?.ok && (
        <Card title={`${T("au_detail")} · ${cur.name}`} testid="audit-detail"
          right={rec && <button className="btn" title={T("au_open_help")} onClick={() => void open(rec)} data-testid="audit-open">{T("au_open_loop")}</button>}>
          <LineChart height={220} yLabel="PV" xLabel="t [s]" testid="audit-pv"
            series={[...(cur.sp ? [{ name: "SP", x: cur.t, y: cur.sp.map((v) => v ?? NaN), color: "#9aa5b1", dash: "5 4" }] : []),
              { name: "PV", x: cur.t, y: cur.pv.map((v) => v ?? NaN), color: "#1f5fa8" }]} />
          <LineChart height={140} yLabel="MV" xLabel="t [s]" testid="audit-mv"
            series={[{ name: "MV", x: cur.t, y: cur.mv.map((v) => v ?? NaN), color: "#c2410c" }]} />
        </Card>)}
    </>
  );
}

export function LoopsMain() {
  const T = useT();
  const ws = useWs().data;
  if (!ws?.has_data) return <div className="card muted" data-testid="no-data">{T("ui_no_data")}</div>;
  return (
    <div className="stack">
      <ProjectLoops />
      <AuditResults />
    </div>
  );
}

export function LoopsSide() {
  const T = useT();
  const wid = useUi((s) => s.wid);
  const ws = useWs().data;
  const qc = useQueryClient();
  const setAudit = useUi((s) => s.setAudit);
  const [whole, setWhole] = useState(true);
  const [a, setA] = useState("0");
  const [b, setB] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  if (!ws?.has_data) return null;
  const dur = ws.duration ?? 0;
  const run = async () => {
    setErr(null);
    setBusy(true);
    try {
      const body: Record<string, unknown> = { project: true };
      if (!whole) Object.assign(body, { a: +a, b: +(b ?? dur) });
      const res = await request<components["schemas"]["Audit"]>("POST", `/workspaces/${wid}/audit/analyse`, body);
      setAudit({ wid: wid!, res });
      await qc.invalidateQueries({ queryKey: ["ws", wid] });
    } catch (e) { setErr(String((e as Error).message)); }
    setBusy(false);
  };
  return (
    <>
      <SideCard title={T("au_sec_window")} help={T("au_project_h")} testid="audit-side-window">
        <Seg value={whole ? "whole" : "range"} options={["whole", "range"] as const} label={T("au_sec_window")} testid="audit-whole" stretch help="h_au_window"
          fmt={(v) => (v === "whole" ? T("au_whole") : `${T("dk_from")} – ${T("dk_to")}`)} onChange={(v) => setWhole(v === "whole")} />
        <label className="field" title={T("h_au_window")}><span>{T("dk_from")}</span>
          <input type="number" value={a} disabled={whole} data-testid="audit-a" onChange={(e) => setA(e.target.value)} /></label>
        <label className="field" title={T("h_au_window")}><span>{T("dk_to")}</span>
          <input type="number" value={b ?? String(dur)} disabled={whole} data-testid="audit-b" onChange={(e) => setB(e.target.value)} /></label>
      </SideCard>
      <PrimaryAction disabled={busy} onClick={() => void run()} testid="audit-run" title={T("au_project_h")}>{T("au_run")}</PrimaryAction>
      {err && <div className="err small" role="alert">{err}</div>}
      <SideCard title={T("au_sec_help")} defaultOpen={false} testid="audit-side-help"><Md text={T("au_help")} /></SideCard>
    </>
  );
}
