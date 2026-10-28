// Záložka Přehled smyček (M20): smyčky projektu (aktivní, přidání, odebrání, sloupce, model, sady, stav) a přehled smyček
// souboru (audit: pořadí podle problémů, společné oscilace, detail); panel: smyčky přehledu, okno a spuštění analýzy.
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { request } from "../api/client";
import type { components } from "../api/schema";
import { LineChart } from "../components/LineChart";
import { useWs, useWsQuery } from "../data";
import { useT } from "../i18n";
import { Bold } from "./apc/common";
import { useUi } from "../store";

type Overview = components["schemas"]["LoopsOverview"];
type Row = components["schemas"]["LoopRow"];
type AuditLoop = components["schemas"]["AuditLoop"];
type AuditLoops = components["schemas"]["AuditLoops"];
type AuditResult = components["schemas"]["AuditResult"];
type Problem = components["schemas"]["AuditProblem"];

const NONE = "—";
const g = (x: unknown, n: number) => (typeof x === "number" && Number.isFinite(x) ? String(+x.toPrecision(n)) : "—");

/** Stav smyčky textem: problémy přehledu, jinak „bez nalezeného problému“; neúspěch výpočtu s hlášením. */
function useProblems() {
  const T = useT();
  return (ok: boolean, err: string | null | undefined, probs: Problem[]) =>
    !ok ? T(err || "err_fit_failed") : probs.length ? probs.map((p) => T("au_p_" + p.key)).join(", ") : `✓ ${T("au_ok")}`;
}
const scoreClass = (ok: boolean, s: number) => (!ok ? "" : s >= 6 ? "err" : s >= 3 ? "warn" : s === 0 ? "ok" : "");

export function useLoopsOverview() {
  return useWsQuery<Overview>("loopsov", "/loops/overview");
}

function ProjectLoops() {
  const T = useT();
  const wid = useUi((s) => s.wid);
  const qc = useQueryClient();
  const ws = useWs().data;
  const ov = useLoopsOverview();
  const problems = useProblems();
  const cols = ws?.columns ?? [];
  const used = new Set([ws?.sp, ws?.mv, ...(ov.data?.loops.map((l) => l.pv) ?? [])]);
  const defPv = cols.find((c) => !used.has(c)) ?? cols[0] ?? "";       // první sloupec, který není PV jiné smyčky ani SP / MV
  const defMv = ws?.mv ?? cols[Math.min(1, cols.length - 1)] ?? "";
  const [name, setName] = useState("");
  const [pv, setPv] = useState<string | null>(null);
  const [mv, setMv] = useState<string | null>(null);
  const [sp, setSp] = useState(NONE);
  const [pos, setPos] = useState(NONE);
  const refresh = () => qc.invalidateQueries({ queryKey: ["ws", wid] });
  const act = async (method: string, path: string, body?: unknown) => {
    await request(method, `/workspaces/${wid}${path}`, body);
    await refresh();
  };
  const add = async (auto: boolean) => {
    const body: Record<string, unknown> = name.trim() ? { name: name.trim() } : {};
    if (!auto) Object.assign(body, { pv: pv ?? defPv, mv: mv ?? defMv,
      sp: sp === NONE ? null : sp, pos: pos === NONE ? null : pos });
    await act("POST", "/loops", body);
    setName("");
  };
  const many = (ov.data?.loops.length ?? 0) > 1;
  return (
    <div className="card stack" data-testid="loops-card">
      <h3>{T("ui_lp_title")}</h3>
      <div className="muted small">{T("ui_lp_help")}</div>
      {ov.data && (
        <table className="tbl" data-testid="loops-table">
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
              <td className={`small ${scoreClass(r.health.ok, r.health.score)}`} data-testid={`loop-health-${r.index}`}>
                {r.health.ok && r.health.score > 0 ? <b>{r.health.score} · </b> : null}
                {problems(r.health.ok, r.health.err, r.health.problems)}</td>
              <td><div className="row">
                <button className="btn" disabled={r.active} data-testid={`loop-activate-${r.index}`}
                  onClick={() => void act("PUT", "/loops/active", { index: r.index })}>{T("ui_lp_activate")}</button>
                <button className="btn" disabled={!many} data-testid={`loop-delete-${r.index}`}
                  title={T("loop_del", { n: r.index + 1 })} onClick={() => void act("DELETE", `/loops/${r.index}`)}>{T("ui_lp_delete")}</button>
              </div></td>
            </tr>))}</tbody>
        </table>)}
      <h3>{T("ui_lp_new")}</h3>
      <div className="row" style={{ alignItems: "center" }}>
        <label className="field" style={{ gridTemplateColumns: "auto 1fr" }}><span>{T("au_c_name")}</span>
          <input type="text" value={name} onChange={(e) => setName(e.target.value)} data-testid="loop-new-name" /></label>
        <label className="field" style={{ gridTemplateColumns: "auto 1fr" }}><span>PV</span>
          <select value={pv ?? defPv} onChange={(e) => setPv(e.target.value)} data-testid="loop-new-pv">
            {cols.map((c) => <option key={c} value={c}>{c}</option>)}</select></label>
        <label className="field" style={{ gridTemplateColumns: "auto 1fr" }}><span>MV</span>
          <select value={mv ?? defMv} onChange={(e) => setMv(e.target.value)} data-testid="loop-new-mv">
            {cols.map((c) => <option key={c} value={c}>{c}</option>)}</select></label>
        <label className="field" style={{ gridTemplateColumns: "auto 1fr" }}><span>SP</span>
          <select value={sp} onChange={(e) => setSp(e.target.value)} data-testid="loop-new-sp">
            {[NONE, ...cols].map((c) => <option key={c} value={c}>{c}</option>)}</select></label>
        <label className="field" style={{ gridTemplateColumns: "auto 1fr" }}><span>{T("pos_short")}</span>
          <select value={pos} onChange={(e) => setPos(e.target.value)} data-testid="loop-new-pos">
            {[NONE, ...cols].map((c) => <option key={c} value={c}>{c}</option>)}</select></label>
        <button className="btn primary" onClick={() => void add(false)} data-testid="loop-add">{T("ui_lp_add_cols")}</button>
        <button className="btn" onClick={() => void add(true)} data-testid="loop-add-auto">{T("ui_lp_add_auto")}</button>
      </div>
    </div>
  );
}

function AuditResults() {
  const T = useT();
  const wid = useUi((s) => s.wid);
  const audit = useUi((s) => s.audit);
  const qc = useQueryClient();
  const setTab = useUi((s) => s.setTab);
  const defs = useWsQuery<AuditLoops>("auditloops", "/audit/loops");
  const problems = useProblems();
  const [sel, setSel] = useState(0);
  const res = audit?.wid === wid ? audit.res : null;
  if (!res) return <div className="card muted small" data-testid="audit-hint">{T("au_hint")}</div>;
  const nbad = res.results.filter((r) => r.score > 0).length;
  const cur: AuditResult | undefined = res.results[Math.min(sel, res.results.length - 1)];
  const rec = cur && defs.data?.loops.find((x) => (x.name || x.pv) === cur.name);
  const open = async () => {
    if (!rec) return;
    await request("POST", `/workspaces/${wid}/loops`, { name: rec.name, pv: rec.pv, mv: rec.mv, sp: rec.sp, pos: rec.pos });
    await qc.invalidateQueries({ queryKey: ["ws", wid] });
    setTab("model");
  };
  return (
    <>
      <div className="card stack" data-testid="audit-rank">
        <h3>{T("au_rank_title")} <span className={nbad ? "warn small" : "ok small"} data-testid="audit-nbad">
          {T("au_n_bad", { b: nbad, n: res.results.length })}</span></h3>
        <div className="muted small">{T("au_rank_help")}</div>
        <table className="tbl" data-testid="audit-table">
          <thead><tr><th>#</th><th>{T("au_c_name")}</th><th>{T("au_score")}</th><th>{T("au_problems")}</th><th>{T("au_std")}</th><th>{T("au_iae")}</th>
            <th>{T("au_travel")}</th><th>{T("au_rev")}</th><th>{T("au_lim")}</th><th>{T("au_frozen")}</th><th>{T("au_period")}</th>
            <th>{T("au_stic")}</th><th>{T("kpi_harris")}</th></tr></thead>
          <tbody>{res.results.map((r, i) => {
            const k = (r.kpis ?? {}) as Record<string, number | string | null>;
            return (
              <tr key={i} className={`pick ${i === sel ? "sel" : ""}`} data-testid={`audit-row-${i}`} onClick={() => setSel(i)}>
                <td>{i + 1}</td><td>{r.name}</td>
                <td className={`mono ${scoreClass(r.ok, r.score)}`} data-testid={`audit-score-${i}`}>{r.ok ? r.score : "—"}</td>
                <td className="small">{problems(r.ok, r.err, r.problems)}</td>
                <td className="mono">{r.ok ? g(k.std_e, 4) : ""}</td><td className="mono">{r.ok ? g(k.iae_h, 4) : ""}</td>
                <td className="mono">{r.ok ? g(k.travel_h, 4) : ""}</td><td className="mono">{r.ok ? g(k.rev_h, 3) : ""}</td>
                <td className="mono">{r.ok ? Number(k.at_lim).toFixed(1) : ""}</td><td className="mono">{r.ok ? Number(k.frozen).toFixed(1) : ""}</td>
                <td className="mono">{r.ok && k.period ? Number(k.period).toFixed(0) : r.ok ? "—" : ""}</td>
                <td>{r.ok && k.stic ? T("stic_short_" + String(k.stic)) : r.ok ? "—" : ""}</td>
                <td className="mono">{r.ok ? (k.harris === null ? "—" : Number(k.harris).toFixed(2)) : ""}</td>
              </tr>);
          })}</tbody>
        </table>
        <div className="small muted">{T("au_done", { n: res.results.length, b: nbad })}</div>
      </div>
      <div className="card stack" data-testid="audit-common">
        <h3>{T("au_common_title")}</h3>
        <div className="muted small">{T("au_common_help")}</div>
        {res.common.length
          ? res.common.map((c, i) => (
            <div key={i} className="small warn" data-testid={`audit-common-${i}`}>🔁 {T("au_common", { p: Math.round(c.period), l: c.loops.join(", "), s: c.source })}
              {c.by_stiction ? ` ${T("au_common_stic")}` : ""}</div>))
          : <div className="small muted" data-testid="audit-common-none">{T("au_common_none")}</div>}
      </div>
      {cur?.ok && (
        <div className="card stack" data-testid="audit-detail">
          <div className="row" style={{ justifyContent: "space-between" }}>
            <h3>{T("au_detail")} · {cur.name}</h3>
            {rec && <button className="btn" title={T("au_open_help")} onClick={() => void open()} data-testid="audit-open">{T("au_open_loop")}</button>}
          </div>
          <LineChart height={220} yLabel="PV" xLabel="t [s]" testid="audit-pv"
            series={[...(cur.sp ? [{ name: "SP", x: cur.t, y: cur.sp.map((v) => v ?? NaN), color: "#9aa5b1", dash: "5 4" }] : []),
              { name: "PV", x: cur.t, y: cur.pv.map((v) => v ?? NaN), color: "#1f5fa8" }]} />
          <LineChart height={140} yLabel="MV" xLabel="t [s]" testid="audit-mv"
            series={[{ name: "MV", x: cur.t, y: cur.mv.map((v) => v ?? NaN), color: "#c2410c" }]} />
        </div>)}
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
  const q = useWsQuery<AuditLoops>("auditloops", "/audit/loops");
  const [dr, setDr] = useState<{ k: string; recs: AuditLoop[] } | null>(null);       // rozpracované smyčky aktivní smyčky projektu
  const [sel, setSel] = useState(0);
  const [whole, setWhole] = useState(true);
  const [a, setA] = useState("0");
  const [b, setB] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  if (!ws?.has_data) return null;
  const k = `${ws.pv}|${ws.mv}`;
  const recs = dr?.k === k ? dr.recs : q.data?.loops ?? [];
  const cols = ws.columns ?? [];
  const cur = recs[Math.min(sel, recs.length - 1)];
  const idx = Math.min(sel, recs.length - 1);
  const save = async (next: AuditLoop[]) => {          // uložit do projektu (klíč audit_loops, jako desktop)
    setDr({ k, recs: next });
    await request("PATCH", `/workspaces/${wid}/settings`, { audit_loops: next });
    await qc.invalidateQueries({ queryKey: ["ws", wid, "auditloops"] });
  };
  const edit = (patch: Partial<AuditLoop>) => void save(recs.map((r, i) => (i === idx ? { ...r, ...patch } : r)));
  const propose = async () => {
    const p = await request<AuditLoops>("GET", `/workspaces/${wid}/audit/loops?propose=true`);
    setSel(0);
    await save(p.loops);
  };
  const add = () => {
    const n = recs.length;
    setSel(n);
    void save([...recs, { name: `${T("au_c_name")} ${n + 1}`, pv: cols[0], mv: cols[Math.min(1, cols.length - 1)], sp: null, pos: null,
      theta: null, integ: false }]);
  };
  const del = () => { setSel(Math.max(0, idx - 1)); void save(recs.filter((_, i) => i !== idx)); };
  const dur = ws.duration ?? 0;
  const run = async () => {
    setErr(null);
    setBusy(true);
    try {
      const body: Record<string, unknown> = { loops: recs };
      if (!whole) Object.assign(body, { a: +a, b: +(b ?? dur) });
      const res = await request<components["schemas"]["Audit"]>("POST", `/workspaces/${wid}/audit/analyse`, body);
      setAudit({ wid: wid!, res });
      await qc.invalidateQueries({ queryKey: ["ws", wid] });
    } catch (e) { setErr(String((e as Error).message)); }
    setBusy(false);
  };
  const sel_ = (v: string | null | undefined, optional: boolean, on: (x: string | null) => void, testid: string) => (
    <select value={v ?? NONE} data-testid={testid} onChange={(e) => on(e.target.value === NONE ? null : e.target.value)}>
      {(optional ? [NONE, ...cols] : cols).map((c) => <option key={c} value={c}>{c}</option>)}</select>);
  return (
    <div className="stack">
      <section>
        <h3>{T("au_sec_loops")}</h3>
        <div className="muted small">{T("au_loops_help")}</div>
        {!recs.length && <div className="muted small" data-testid="audit-none">{T("au_none")}</div>}
        <ul className="reco" data-testid="audit-defs">{recs.map((r, i) => (
          <li key={i}><button className={i === idx ? "btn primary" : "btn"} data-testid={`audit-def-${i}`}
            onClick={() => setSel(i)}>{r.name || r.pv}</button></li>))}</ul>
        <div className="row">
          <button className="btn" onClick={add} data-testid="audit-add">{T("au_add")}</button>
          <button className="btn" onClick={del} disabled={!recs.length} data-testid="audit-del">{T("au_del")}</button>
          <button className="btn" onClick={() => void propose()} data-testid="audit-propose">{T("au_propose")}</button>
        </div>
        {cur && (
          <>
            <label className="field"><span>{T("au_c_name")}</span>
              <input type="text" key={idx} defaultValue={cur.name} data-testid="audit-f-name"
                onBlur={(e) => { if (e.target.value !== cur.name) edit({ name: e.target.value.trim() }); }} /></label>
            <label className="field"><span>PV</span>{sel_(cur.pv, false, (x) => edit({ pv: x ?? cur.pv }), "audit-f-pv")}</label>
            <label className="field"><span>MV</span>{sel_(cur.mv, false, (x) => edit({ mv: x ?? cur.mv }), "audit-f-mv")}</label>
            <label className="field"><span>SP</span>{sel_(cur.sp, true, (x) => edit({ sp: x }), "audit-f-sp")}</label>
            <label className="field"><span>{T("pos_short")}</span>{sel_(cur.pos, true, (x) => edit({ pos: x }), "audit-f-pos")}</label>
            <label className="field" title={T("au_theta_help")}><span>θ [s]</span>
              <input key={`t${idx}`} type="number" min={0} step="any" defaultValue={cur.theta ?? 0} data-testid="audit-f-theta"
                onBlur={(e) => { const v = +e.target.value; edit({ theta: v > 0 ? v : null }); }} /></label>
            <label className="small"><input type="checkbox" checked={cur.integ} data-testid="audit-f-integ"
              onChange={(e) => edit({ integ: e.target.checked })} /> {T("au_c_integ")}</label>
          </>)}
      </section>
      <section>
        <h3>{T("au_sec_window")}</h3>
        <label className="small"><input type="checkbox" checked={whole} data-testid="audit-whole"
          onChange={(e) => setWhole(e.target.checked)} /> {T("au_whole")}</label>
        <label className="field"><span>{T("dk_from")}</span>
          <input type="number" value={a} disabled={whole} data-testid="audit-a" onChange={(e) => setA(e.target.value)} /></label>
        <label className="field"><span>{T("dk_to")}</span>
          <input type="number" value={b ?? String(dur)} disabled={whole} data-testid="audit-b" onChange={(e) => setB(e.target.value)} /></label>
      </section>
      <section>
        <button className="btn primary" disabled={busy || !recs.length} onClick={() => void run()} data-testid="audit-run">▶ {T("au_run")}</button>
        {err && <div className="err small" role="alert">{err}</div>}
      </section>
      <details className="small"><summary>{T("au_sec_help")}</summary><Bold text={T("au_help")} /></details>
    </div>
  );
}
