// Ladění 2 (M17): scénář simulace (předvolba, SP z → na, amplitudy, vlastní události), porovnání všech metod (úloha)
// a frekvenční charakteristiky (Bode, citlivost S / T) pro sadu 1, 2 a návrh.
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { request } from "../api/client";
import type { components } from "../api/schema";
import { NumSetting } from "../components/Fields";
import { LineChart, type Series } from "../components/LineChart";
import { useSettings, useWs } from "../data";
import { useT } from "../i18n";
import { useJobRunner } from "../jobs";
import { useUi } from "../store";

type Scenario = components["schemas"]["Scenario"];
type FreqSet = components["schemas"]["FreqSet"];
type Pid = { Kc: number; Ti: number; Td: number };
export type CmpRow = { method: string; crit: string | null; ctype: string; Kc: number; Ti: number; Td: number;
  Ms: number | null; iae_load: number | null; iae_sp: number | null; ovs: number | null; noise: number | null };
type Row = [boolean, string, string, number, number | null, number | null, number | null, number | null];

const TYPES = ["step", "ramp", "sine", "pulse", "rpulse", "noise"] as const;
const SET_COLORS: Record<string, string> = { set1: "#64748b", set2: "#15803d", sug: "#1f5fa8" };
// Nyquist: pohled a kružnice Ms (střed −1, poloměr 1/Ms), kritický bod −1 (kříž; NaN přeruší čáru)
const NYQ_LIM = 3, MS_T = 1.6;
const inView = (x: number, y: number) => x >= -NYQ_LIM && x <= 1.5 && y >= -NYQ_LIM && y <= 1.5;
const MS_CIRCLE = { x: Array.from({ length: 200 }, (_, i) => -1 + Math.cos((2 * Math.PI * i) / 199) / MS_T),
  y: Array.from({ length: 200 }, (_, i) => Math.sin((2 * Math.PI * i) / 199) / MS_T) };
const CRIT = { x: [-1.06, -0.94, NaN, -1, -1], y: [0, 0, NaN, -0.06, 0.06] };

function NumCell({ v, onCommit, testid }: { v: number | null; onCommit: (x: number | null) => void; testid?: string }) {
  const [d, setD] = useState<string | null>(null);
  return (
    <input type="number" step="any" className="num" value={d ?? (v === null ? "" : +v.toPrecision(6))} data-testid={testid}
      onChange={(e) => setD(e.target.value)}
      onBlur={() => { if (d !== null) onCommit(d === "" ? null : Number.isFinite(+d) ? +d : v); setD(null); }}
      onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }} />
  );
}

export function ScenarioCard() {
  const T = useT();
  const wid = useUi((s) => s.wid);
  const qc = useQueryClient();
  const ws = useWs().data;
  const st = useSettings().data ?? {};
  const sc = useQuery({ queryKey: ["ws", wid, "scenario", st], placeholderData: keepPreviousData,
    queryFn: () => request<Scenario>("GET", `/workspaces/${wid}/scenario`) });
  if (!sc.data) return null;
  const s = sc.data;
  const rows = s.rows as Row[];
  const uPv = String(st.u_pv || "PV"), uMv = String(st.u_mv || "MV");          // bez jednotky aspoň název
  const targets = ["SP", "IN", "PV", ...(ws?.dists ?? []).map((_, j) => `M${j}`)];
  const tgLabel = (t: string) => (t.startsWith("M") ? `${T("tg_M")}: ${ws?.dists[+t.slice(1)] ?? t}` : T("tg_" + t));
  const put = async (body: Record<string, unknown>) => {
    await request("PUT", `/workspaces/${wid}/scenario`, body);
    await qc.invalidateQueries({ queryKey: ["ws", wid] });
  };
  const setRow = (i: number, j: number, v: unknown) =>
    void put({ rows: rows.map((r, k) => (k === i ? r.map((x, m) => (m === j ? v : x)) : r)), T_end: s.T_end });
  const [sp0, sp1] = s.sp_from_to;

  return (
    <div className="card" data-testid="scenario">
      <h3>{T("scen_title")}</h3>
      <div className="row">
        <label className="field"><span>{T("dk_sc_kind")}</span>
          <select value={s.kind} data-testid="scen-kind" title={T("dk_sc_kind_help")}
            onChange={(e) => void put({ kind: e.target.value })}>
            {s.kinds.map((k) => <option key={k} value={k}>{T("dk_sc_" + k)}</option>)}
          </select>
        </label>
        <label className="field"><span>{T("sim_sp_from", { u: uPv })}</span>
          <NumCell v={sp0} onCommit={(x) => x !== null && void put({ sp_from_to: [x, sp1] })} testid="scen-sp0" /></label>
        <label className="field"><span>{T("sim_sp_to", { u: uPv })}</span>
          <NumCell v={sp1} onCommit={(x) => x !== null && void put({ sp_from_to: [sp0, x] })} testid="scen-sp1" /></label>
        {["in", "sp_in"].includes(s.kind) && <NumSetting k="scen_d_in" label={T("dk_sc_d_in", { u: uMv })} />}
        {s.kind === "pv" && <NumSetting k="scen_d_pv" label={T("dk_sc_d_pv", { u: uPv })} />}
      </div>
      <div className="small muted">{T("dk_sc_note_" + s.kind)}</div>
      {s.kind !== "replay" && (
        <>
          <table className="tbl" data-testid="scen-rows"><thead><tr>
            <th>{T("sc_on")}</th><th>{T("sc_target")}</th><th>{T("sc_type")}</th><th>{T("sc_amp")}</th><th>{T("sc_start")}</th>
            <th>{T("sc_end")}</th><th>{T("sc_period")}</th><th>{T("sc_tau")}</th><th /></tr></thead>
            <tbody>{rows.map((r, i) => (
              <tr key={`${s.kind}-${i}-${r.join("|")}`} data-testid="scen-row">
                <td><input type="checkbox" checked={!!r[0]} onChange={(e) => setRow(i, 0, e.target.checked)} /></td>
                <td><select value={r[1]} onChange={(e) => setRow(i, 1, e.target.value)}>
                  {targets.map((t) => <option key={t} value={t}>{tgLabel(t)}</option>)}</select></td>
                <td><select value={r[2]} onChange={(e) => setRow(i, 2, e.target.value)}>
                  {TYPES.map((t) => <option key={t} value={t}>{T("ty_" + t)}</option>)}</select></td>
                {[3, 4, 5, 6, 7].map((j) => (
                  <td key={j}><NumCell v={r[j] as number | null} testid={`scen-${i}-${j}`}
                    onCommit={(x) => setRow(i, j, j === 3 || j === 4 ? (x ?? 0) : x)} /></td>))}
                <td><button className="btn" title="×" onClick={() => void put({ rows: rows.filter((_, k) => k !== i), T_end: s.T_end })}>×</button></td>
              </tr>))}
            </tbody></table>
          <div className="row">
            <button className="btn" data-testid="scen-add"
              onClick={() => void put({ rows: [...rows, [true, "IN", "step", 1, Math.round(s.T_end / 2), null, null, null]], T_end: s.T_end })}>
              + {T("ui_sc_add")}</button>
          </div>
          <div className="small muted">{T("scen_help")}</div>
        </>
      )}
    </div>
  );
}

export function CompareCard({ onPick }: { onPick: (r: CmpRow) => void }) {
  const T = useT();
  const run = useJobRunner();
  const st = useSettings().data ?? {};
  const [rows, setRows] = useState<CmpRow[] | null>(null);
  const [sel, setSel] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const mr = (Number(st.mv_hi ?? 100) - Number(st.mv_lo ?? 0)) / 100;    // šum MV v % rozsahu → jednotky MV
  const go = async () => {
    setBusy(true);
    try {
      const j = await run("/tuning/compare", undefined, T("cmp_title"));
      if (j.state === "done") { setRows(await request<CmpRow[]>("GET", `/jobs/${j.id}/result`)); setSel(null); }
    } finally { setBusy(false); }
  };
  const f = (x: number | null, p = 4) => (x === null || x === undefined ? "–" : String(+x.toPrecision(p)));
  return (
    <div className="card" data-testid="compare">
      <div className="row"><h3>{T("cmp_title")}</h3>
        <button className="btn" disabled={busy} onClick={() => void go()} data-testid="cmp-run">{busy ? "…" : T("cmp_title")}</button></div>
      {rows && (
        <>
          <table className="tbl" data-testid="cmp-table"><thead><tr><th>{T("col_method")}</th><th>{T("ctrl_type")}</th>
            <th>Gain</th><th>TI [s]</th><th>TD [s]</th><th>Ms</th><th>{T("iae_load")}</th><th>{T("iae_sp")}</th>
            <th>{T("ovs_col")}</th><th>{T("noise_col", { u: String(st.u_mv || "MV") })}</th></tr></thead>
            <tbody>{rows.map((q, i) => (
              <tr key={i} className={i === sel ? "sel" : "pick"} data-testid="cmp-row" onClick={() => { setSel(i); onPick(q); }}>
                <td>{T("m_" + q.method) + (q.crit ? ` · ${T("crit_" + q.crit)}` : "")}</td><td>{q.ctype}</td>
                <td className="mono">{f(q.Kc)}</td><td className="mono">{f(q.Ti)}</td><td className="mono">{f(q.Td)}</td>
                <td className="mono">{f(q.Ms, 3)}</td><td className="mono">{f(q.iae_load)}</td><td className="mono">{f(q.iae_sp)}</td>
                <td className="mono">{q.ovs === null ? "–" : q.ovs.toFixed(1)}</td><td className="mono">{q.noise === null ? "–" : f(q.noise * mr, 3)}</td>
              </tr>))}</tbody></table>
          <div className="small muted">{T("cmp_help")}</div>
        </>
      )}
    </div>
  );
}

export function FreqCard({ preview }: { preview: Pid | null }) {
  const T = useT();
  const wid = useUi((s) => s.wid);
  const st = useSettings().data ?? {};
  const fr = useQuery({ queryKey: ["ws", wid, "freq", preview, st], placeholderData: keepPreviousData,
    queryFn: () => request<FreqSet[]>("POST", `/workspaces/${wid}/frequency`, preview ?? undefined) });
  if (!fr.data) return null;
  const name = (n: string) => (n === "sug" ? T("dk_suggest") : n === "set1" ? "Set 1" : "Set 2");
  const line = (key: "mag_db" | "phase_deg" | "S_db" | "T_db", dash?: string): Series[] =>
    fr.data!.map((r) => ({ name: `${name(r.name)}${key === "T_db" ? " |T|" : ""}`,
      x: r.w, y: r[key], color: SET_COLORS[r.name] ?? "#888", dash }));
  const n = (x: number | null | undefined, d: number) => (x === null || x === undefined ? "–" : x.toFixed(d));
  return (
    <div className="card" data-testid="freq">
      <h3>{T("fq_title")}</h3>
      <table className="tbl" data-testid="freq-table"><thead><tr><th /><th>{T("fq_stable")}</th><th>Ms</th><th>GM</th>
        <th>PM [°]</th><th>ωc [rad/s]</th><th>{T("fq_bw")}</th></tr></thead>
        <tbody>{fr.data.map((r) => (
          <tr key={r.name}><td>{name(r.name)}</td><td>{r.stable ? "✓" : "✗"}</td><td className="mono">{n(r.Ms, 2)}</td>
            <td className="mono">{n(r.GM, 2)}</td><td className="mono">{n(r.PM, 0)}</td>
            <td className="mono">{r.wc ? r.wc.toPrecision(3) : "–"}</td><td className="mono">{r.bw ? r.bw.toPrecision(3) : "–"}</td></tr>))}
        </tbody></table>
      <div className="small muted">{T("fq_bode")}</div>
      <LineChart series={line("mag_db")} height={180} logX yLabel={T("fq_mag")} testid="freq-mag" />
      <LineChart series={line("phase_deg")} height={160} logX yLabel={T("fq_phase")} xLabel={T("fq_w")} testid="freq-phase" />
      <div className="small muted">{T("fq_sens")}</div>
      <LineChart series={[...line("S_db"), ...line("T_db", "5 4")]} height={180} logX yLabel="dB" xLabel={T("fq_w")}
        testid="freq-sens" />
      <div className="small muted">{T("fq_nyquist")}</div>
      <LineChart series={nyq(fr.data, name)} height={696} xDomain={[-NYQ_LIM, 1.5]} yDomain={[-NYQ_LIM, 1.5]} xLabel="Re L"
        yLabel="Im L" testid="freq-nyq" />
      <div className="small muted">{T("fq_help")}</div>
    </div>
  );
}

// Nyquistův diagram L: body mimo pohled se vynechají (NaN); výška 696 = stejné měřítko os, kružnice je kruh
function nyq(data: FreqSet[], name: (n: string) => string): Series[] {
  return [{ name: `Ms = ${MS_T}`, x: MS_CIRCLE.x, y: MS_CIRCLE.y, color: "#9aa5b1", dash: "4 3" },
    ...data.map((r) => ({ name: name(r.name),
      x: r.re.map((x, i) => (inView(x, r.im[i]) ? x : NaN)), y: r.im.map((y, i) => (inView(r.re[i], y) ? y : NaN)),
      color: SET_COLORS[r.name] ?? "#888" })),
    { name: "−1", x: CRIT.x, y: CRIT.y, color: "#b91c1c" }];
}
