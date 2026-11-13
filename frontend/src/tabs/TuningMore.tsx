// Ladění 2: sdílené dotazy (simulace, scénář, frekvence), karta Scénář simulace v panelu, události scénáře, srovnání
// všech metod (úloha) a frekvenční analýza (Bode, citlivost S / T, Nyquist) pro sadu 1, 2 a návrh.
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { binary, request } from "../api/client";
import type { components } from "../api/schema";
import { unframe } from "../api/signals";
import { LineChart, type Series } from "../components/LineChart";
import { useSettings, useWs, useWsQuery, usePatchSettings } from "../data";
import { useDec, useT } from "../i18n";
import { useJobRunner } from "../jobs";
import { useUi } from "../store";
import { Md } from "../components/Ui";
import { type CmpRow, type Suggestion, type Unit, useCalc, useTun } from "./tuningState";

type Scenario = components["schemas"]["Scenario"];
type FreqSet = components["schemas"]["FreqSet"];
type SimInfo = components["schemas"]["SimInfo"];
type TuningInfo = components["schemas"]["TuningInfo"];
type Row = [boolean, string, string, number, number | null, number | null, number | null, number | null];
export type Pid = { Kc: number; Ti: number; Td: number };

const TYPES = ["step", "ramp", "sine", "pulse", "rpulse", "noise"] as const;
const SET_COLORS: Record<string, string> = { set1: "#64748b", set2: "#15803d", sug: "#7c3aed" };
export const UNITS = { s: 1, min: 60, h: 3600 } as const;
export const autoUnit = (span: number): "s" | "min" | "h" => (span <= 1200 ? "s" : span <= 72000 ? "min" : "h");
export const unitOf = (u: Unit, span: number) => (u === "auto" ? autoUnit(span) : u);

/** Číslo v textu podle jazyka (desetinná čárka) a s danou přesností. */
export const fnum = (x: number | null | undefined, dec: string, p = 3) =>
  x === null || x === undefined || !Number.isFinite(x) ? "–" : String(+x.toPrecision(p)).replace(".", dec);

// ---- sdílené dotazy: návrh (preview), simulace s ukazateli a průběhy, scénář, frekvence
export function usePreview(): Pid | null {
  const sug = useTun((s) => s.sug);
  return sug ? { Kc: sug.Kc, Ti: sug.Ti, Td: sug.Td } : null;
}

export function useSim() {
  const wid = useUi((s) => s.wid);
  const st = useSettings().data ?? {};
  const info = useWsQuery<TuningInfo>("tuning", "/tuning");
  const model = useWsQuery<components["schemas"]["ModelState"]>("model", "/model");
  const { spread, robust, ffcmp, tend } = useTun();
  const preview = usePreview();
  const sp = spread && !!model.data?.uncertainty;
  const body = { preview, spread: sp, robust, ff_cmp: ffcmp, T_end: tend };
  const key = ["ws", wid, "sim", info.data?.sets, preview, st, sp, robust, ffcmp, tend];
  // při přepočtu zůstane vidět předchozí výsledek – žádné blikání
  const sim = useQuery({ queryKey: [...key, "kpi"], enabled: !!info.data, placeholderData: keepPreviousData,
    queryFn: () => request<SimInfo>("POST", `/workspaces/${wid}/simulate`, body) });
  const curves = useQuery({ queryKey: [...key, "curves"], enabled: !!info.data, placeholderData: keepPreviousData,
    queryFn: async () => unframe(await binary(`/workspaces/${wid}/simulate/curves`, body)) });
  return { sim, curves, preview, spread: sp, hasUnc: !!model.data?.uncertainty };
}

export function useScenario() {
  const wid = useUi((s) => s.wid);
  const st = useSettings().data ?? {};
  return useQuery({ queryKey: ["ws", wid, "scenario", st], placeholderData: keepPreviousData,
    queryFn: () => request<Scenario>("GET", `/workspaces/${wid}/scenario`) });
}

export function useFreq(preview: Pid | null) {
  const wid = useUi((s) => s.wid);
  const st = useSettings().data ?? {};
  return useQuery({ queryKey: ["ws", wid, "freq", preview, st], placeholderData: keepPreviousData,
    queryFn: () => request<FreqSet[]>("POST", `/workspaces/${wid}/frequency`, preview ?? undefined) });
}

function NumCell({ v, onCommit, testid, label, className, title }: { v: number | null; onCommit: (x: number | null) => void;
  testid?: string; label?: string; className?: string; title?: string }) {
  const [d, setD] = useState<string | null>(null);
  return (
    <input type="number" step="any" className={className ?? "num"} value={d ?? (v === null ? "" : +v.toPrecision(6))}
      data-testid={testid} aria-label={label} title={title} onChange={(e) => setD(e.target.value)}
      onBlur={() => { if (d !== null) onCommit(d === "" ? null : Number.isFinite(+d) ? +d : v); setD(null); }}
      onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }} />
  );
}

/** Nápověda sloupců tabulky událostí (index sloupce řádku scénáře). */
const HELP_COL: Record<number, string> = { 3: "h_sc_amp", 4: "h_sc_start", 5: "h_sc_end", 6: "h_sc_period", 7: "h_sc_tau" };

function usePutScenario() {
  const wid = useUi((s) => s.wid);
  const qc = useQueryClient();
  return async (body: Record<string, unknown>) => {
    await request("PUT", `/workspaces/${wid}/scenario`, body);
    await qc.invalidateQueries({ queryKey: ["ws", wid] });
  };
}

// ---- karta panelu Scénář simulace: druh, SP z → na a čas, porucha (DV), délka s jednotkou
export function ScenarioSide() {
  const T = useT();
  const st = useSettings().data ?? {};
  const patch = usePatchSettings();
  const put = usePutScenario();
  const sc = useScenario();
  const { sim } = useSim();
  const { tend, lenUnit, set } = useTun();
  if (!sc.data) return null;
  const s = sc.data;
  const rows = s.rows as Row[];
  const uPv = String(st.u_pv ?? ""), uMv = String(st.u_mv ?? "");
  const replay = s.kind === "replay";
  const T_end = tend ?? sim.data?.T_end ?? s.T_end;
  const lu = unitOf(lenUnit, T_end), mult = UNITS[lu];
  const iSp = rows.findIndex((r) => r[1] === "SP"), iDv = rows.findIndex((r) => r[1] !== "SP");
  const [sp0, sp1] = s.sp_from_to;
  const setRow = (i: number, j: number, v: unknown) =>
    void put({ rows: rows.map((r, k) => (k === i ? r.map((x, m) => (m === j ? v : x)) : r)), T_end: s.T_end });
  const tm = (v: number | null) => (v === null ? null : +(v / mult).toPrecision(5));
  const dvAmp = s.kind === "in" || s.kind === "sp_in" ? Number(st.scen_d_in ?? rows[iDv]?.[3] ?? 0)
    : s.kind === "pv" ? Number(st.scen_d_pv ?? rows[iDv]?.[3] ?? 0) : Number(rows[iDv]?.[3] ?? 0);
  const setDv = (x: number) => {
    if (s.kind === "in" || s.kind === "sp_in") void patch({ scen_d_in: x });
    else if (s.kind === "pv") void patch({ scen_d_pv: x });
    else setRow(iDv, 3, x);
  };
  const dvLabel = iDv >= 0 ? (rows[iDv][1] === "IN" ? uMv : rows[iDv][1] === "PV" ? uPv : "") : "";
  return (
    <div className="tn-scen" data-testid="scenario">
      <label className="trow"><span>{T("dk_sc_kind")}</span>
        <select value={s.kind} data-testid="scen-kind" title={T("dk_sc_kind_help")} onChange={(e) => void put({ kind: e.target.value })}>
          {s.kinds.map((k) => <option key={k} value={k}>{T("dk_sc_" + k)}</option>)}
        </select>
      </label>
      <div className="tn-note">{T("dk_sc_note_" + s.kind)}</div>
      {!replay && (
        <div className="tn-grid3">
          <span /><span className="tn-sub">{T("ui_tuning_from_to")}</span><span className="tn-sub">{T("ui_tuning_at")}</span>
          <span className="tn-lab">SP</span>
          <span className="tn-pair">
            <NumCell v={sp0} onCommit={(x) => x !== null && void put({ sp_from_to: [x, sp1] })} testid="scen-sp0"
              label={T("sim_sp_from", { u: uPv })} title={T("h_sim_sp_from")} className="tn-in" />
            <i>→</i>
            <NumCell v={sp1} onCommit={(x) => x !== null && void put({ sp_from_to: [sp0, x] })} testid="scen-sp1"
              label={T("sim_sp_to", { u: uPv })} title={T("h_sim_sp_to")} className="tn-in" />
          </span>
          {iSp >= 0 ? <NumCell v={tm(rows[iSp][4])} onCommit={(x) => x !== null && setRow(iSp, 4, x * mult)} className="tn-in"
            testid="scen-sp-t" label={T("ui_tuning_at")} title={T("h_sc_start")} /> : <span className="tn-sub">–</span>}
          {iDv >= 0 && <>
            <span className="tn-lab dv" title={T("tg_" + rows[iDv][1].replace(/^M\d+$/, "M"))}>DV</span>
            <NumCell v={dvAmp} onCommit={(x) => x !== null && setDv(x)} className="tn-in" testid="scen-dv"
              label={`DV ${dvLabel}`} title={T("h_sc_amp")} />
            <NumCell v={tm(rows[iDv][4])} onCommit={(x) => x !== null && setRow(iDv, 4, x * mult)} className="tn-in"
              testid="scen-dv-t" label={T("ui_tuning_at")} title={T("h_sc_start")} />
          </>}
          <span className="tn-lab">{T("ui_tuning_len")}</span>
          <NumCell v={tm(T_end)} onCommit={(x) => { if (x !== null && x > 0) set({ tend: x * mult, lenUnit: lu }); }}
            className="tn-in" testid="scen-len" label={T("sim_len")} title={T("h_sim_len")} />
          <select value={lu} aria-label={T("time_unit")} title={T("h_sim_len")} data-testid="scen-len-unit"
            onChange={(e) => set({ lenUnit: e.target.value as Unit })}>
            {(["s", "min", "h"] as const).map((u) => <option key={u} value={u}>{u}</option>)}
          </select>
        </div>
      )}
      {!replay && (
        <label className="tn-check" title={T("h_sim_len_auto")}>
          <input type="checkbox" checked={tend === null} data-testid="scen-len-auto"
            onChange={(e) => set({ tend: e.target.checked ? null : T_end })} /> {T("sim_len_auto")}
          {tend === null && sim.data?.src && <span className="tn-sub">{T("sim_len_src_" + sim.data.src)}</span>}
        </label>
      )}
    </div>
  );
}

// ---- události scénáře (tabulka pod grafem – potřebuje šířku)
export function ScenarioEvents() {
  const T = useT();
  const ws = useWs().data;
  const put = usePutScenario();
  const sc = useScenario();
  if (!sc.data || sc.data.kind === "replay") return null;
  const s = sc.data;
  const rows = s.rows as Row[];
  const targets = ["SP", "IN", "PV", ...(ws?.dists ?? []).map((_, j) => `M${j}`)];
  const tgLabel = (t: string) => (t.startsWith("M") ? `${T("tg_M")}: ${ws?.dists[+t.slice(1)] ?? t}` : T("tg_" + t));
  const setRow = (i: number, j: number, v: unknown) =>
    void put({ rows: rows.map((r, k) => (k === i ? r.map((x, m) => (m === j ? v : x)) : r)), T_end: s.T_end });
  return (
    <section className="tn-card" data-testid="scenario-events">
      <div className="tn-head"><h2>{T("scen_title")}</h2></div>
      <div className="tn-scroll">
        <table className="tn-tbl" data-testid="scen-rows"><thead><tr>
          <th title={T("h_sc_on")}>{T("sc_on")}</th><th title={T("h_sc_target")}>{T("sc_target")}</th>
          <th title={T("h_sc_type")}>{T("sc_type")}</th><th title={T("h_sc_amp")}>{T("sc_amp")}</th>
          <th title={T("h_sc_start")}>{T("sc_start")}</th><th title={T("h_sc_end")}>{T("sc_end")}</th>
          <th title={T("h_sc_period")}>{T("sc_period")}</th><th title={T("h_sc_tau")}>{T("sc_tau")}</th><th /></tr></thead>
          <tbody>{rows.map((r, i) => (
            <tr key={`${s.kind}-${i}-${r.join("|")}`} data-testid="scen-row">
              <td><input type="checkbox" checked={!!r[0]} title={T("h_sc_on")} onChange={(e) => setRow(i, 0, e.target.checked)} /></td>
              <td><select value={r[1]} title={T("h_sc_target")} onChange={(e) => setRow(i, 1, e.target.value)}>
                {targets.map((t) => <option key={t} value={t}>{tgLabel(t)}</option>)}</select></td>
              <td><select value={r[2]} title={T("h_sc_type")} onChange={(e) => setRow(i, 2, e.target.value)}>
                {TYPES.map((t) => <option key={t} value={t}>{T("ty_" + t)}</option>)}</select></td>
              {[3, 4, 5, 6, 7].map((j) => (
                <td key={j}><NumCell v={r[j] as number | null} testid={`scen-${i}-${j}`} title={T(HELP_COL[j])}
                  onCommit={(x) => setRow(i, j, j === 3 || j === 4 ? (x ?? 0) : x)} /></td>))}
              <td><button className="btn" title="×" onClick={() => void put({ rows: rows.filter((_, k) => k !== i), T_end: s.T_end })}>×</button></td>
            </tr>))}
          </tbody></table>
      </div>
      <div className="row">
        <button className="btn" data-testid="scen-add"
          onClick={() => void put({ rows: [...rows, [true, "IN", "step", 1, Math.round(s.T_end / 2), null, null, null]], T_end: s.T_end })}>
          + {T("ui_sc_add")}</button>
      </div>
      <div className="tn-note">{T("scen_help")}</div>
      <Md text={T("sc_where_help")} />
    </section>
  );
}

// ---- Všechny metody pro tento model (klepnutím na řádek se metoda převezme do Návrhu)
export function CompareCard({ withRun = true }: { withRun?: boolean }) {
  const T = useT();
  const run = useJobRunner();
  const st = useSettings().data ?? {};
  const patch = usePatchSettings();
  const calc = useCalc();
  const dec = useDec();
  const info = useWsQuery<TuningInfo>("tuning", "/tuning");
  const { cmp: rows, cmpBusy: busy, method, view, set } = useTun();
  const m = method ?? info.data?.default_method;
  const mr = (Number(st.mv_hi ?? 100) - Number(st.mv_lo ?? 0)) / 100;    // šum MV v % rozsahu → jednotky MV
  const go = async () => {
    set({ cmpBusy: true });
    try {
      const j = await run("/tuning/compare", undefined, T("cmp_title"));
      if (j.state === "done") set({ cmp: await request<CmpRow[]>("GET", `/jobs/${j.id}/result`) });
    } finally { set({ cmpBusy: false }); }
  };
  useEffect(() => { if (view === "all" && !rows && !busy && info.data) void go(); }, [view, info.data]);   // eslint-disable-line react-hooks/exhaustive-deps
  const pick = async (q: Pick<CmpRow, "method" | "crit" | "ctype"> & Partial<CmpRow>) => {
    set({ method: q.method });
    if (q.Kc !== undefined && q.Ti !== undefined && q.Td !== undefined)
      set({ sug: { method: q.method, Kc: q.Kc, Ti: q.Ti, Td: q.Td, notes: [], checks: [], values: {}, warnings: [], approximate: false, fromRow: true } as Suggestion });
    await patch({ ctype: q.ctype, ...(q.crit ? { opt_crit: q.crit } : {}) });
    if (q.Kc === undefined) await calc(q.method);
  };
  const cur = (q: CmpRow) => q.method === m && q.ctype === (st.ctype ?? "PI") && (m !== "OPT" || q.crit === (st.opt_crit ?? "OVS"));
  const use = (q: { method: string; crit: string | null }) => {
    const k = "use_" + (q.crit ?? q.method);
    const v = T(k);
    return v === k ? "" : v;
  };
  const f = (x: number | null, p = 4) => fnum(x, dec, p);
  const csv = () => {                                  // srovnání metod jako CSV (středník, desetinná čárka podle jazyka)
    const n = (x: number | null) => (x === null ? "" : String(x).replace(".", dec));
    const lines = ["method;crit;type;Kc;Ti;Td;Ms;iae_load;iae_sp;overshoot;noise", ...(rows ?? []).map((q) =>
      [q.method, q.crit ?? "", q.ctype, q.Kc, q.Ti, q.Td, q.Ms, q.iae_load, q.iae_sp, q.ovs, q.noise]
        .map((x) => (typeof x === "string" ? x : n(x))).join(";"))];
    const el = document.createElement("a");
    el.href = URL.createObjectURL(new Blob(["\ufeff" + lines.join("\n") + "\n"], { type: "text/csv;charset=utf-8" }));
    el.download = "tuning_comparison.csv";
    el.click();
    URL.revokeObjectURL(el.href);
  };
  return (
    <section className="tn-card" data-testid="compare">
      <div className="tn-head"><h2>{T("tn_methods")}</h2><span className="tn-sub">{T("tn_methods_note")}</span>
        {rows && <button type="button" className="btn tn-right" data-testid="cmp-csv" title={T("tun_ui_cmp_csv_help")} onClick={csv}>
          {T("tun_ui_cmp_csv")}</button>}
        {withRun && <button className={"btn" + (rows ? "" : " tn-right")} disabled={busy} onClick={() => void go()} data-testid="cmp-run">
          {busy ? "…" : T("tn_methods_run")}</button>}
      </div>
      <div className="tn-scroll">
        <table className="tn-tbl" data-testid="cmp-table"><thead><tr><th>{T("col_method")}</th>
          <th className="r">Gain</th><th className="r">TI [s]</th><th className="r">TD [s]</th><th className="r">Ms</th>
          <th className="r">{T("iae_load")}</th><th className="r">{T("iae_sp")}</th><th className="r">{T("ovs_col")}</th>
          <th className="r">{T("noise_col", { u: String(st.u_mv || "MV") })}</th><th>{T("use_col")}</th></tr></thead>
          <tbody>{rows ? rows.map((q, i) => (
            <tr key={i} className={"pick" + (cur(q) ? " sel" : "")} data-testid="cmp-row" onClick={() => void pick(q)}>
              <td>{T("m_" + q.method) + (q.crit ? ` · ${T("crit_" + q.crit)}` : "")} <span className="tn-sub">{q.ctype}</span>
                {cur(q) && <b className="tn-ok"> ✓</b>}</td>
              <td className="r mono">{f(q.Kc)}</td><td className="r mono">{f(q.Ti)}</td><td className="r mono">{f(q.Td)}</td>
              <td className="r mono">{f(q.Ms, 3)}</td><td className="r mono">{f(q.iae_load)}</td><td className="r mono">{f(q.iae_sp)}</td>
              <td className="r mono">{q.ovs === null ? "–" : q.ovs.toFixed(1)}</td>
              <td className="r mono">{q.noise === null ? "–" : f(q.noise * mr, 3)}</td><td className="tn-sub">{use(q)}</td>
            </tr>)) : (info.data?.methods ?? []).map((x) => (
              <tr key={x} className={"pick" + (x === m ? " sel" : "")} data-testid="cmp-pending"
                onClick={() => void pick({ method: x, crit: x === "OPT" ? String(st.opt_crit ?? "OVS") : null, ctype: String(st.ctype ?? "PI") })}>
                <td>{T("m_" + x)}{x === m && <b className="tn-ok"> ✓</b>}</td>
                <td colSpan={8} className="tn-faint">{x === "OPT" ? T("ui_tuning_pending_opt") : T("ui_tuning_pending")}</td>
                <td className="tn-sub">{use({ method: x, crit: x === "OPT" ? String(st.opt_crit ?? "OVS") : null })}</td></tr>))}
          </tbody></table>
      </div>
      {rows && <div className="tn-note">{T("cmp_help")}</div>}
    </section>
  );
}

// ---- frekvenční analýza
export function FreqCard({ data }: { data: FreqSet[] }) {
  const T = useT();
  const name = (n: string) => (n === "sug" ? T("dk_suggest") : n === "set1" ? "Set 1" : "Set 2");
  const line = (key: "mag_db" | "phase_deg" | "S_db" | "T_db", dash?: string): Series[] =>
    data.map((r) => ({ name: `${name(r.name)}${key === "T_db" ? " |T|" : ""}`,
      x: r.w, y: r[key], color: SET_COLORS[r.name] ?? "#888", dash }));
  const n = (x: number | null | undefined, d: number) => (x === null || x === undefined ? "–" : x.toFixed(d));
  return (
    <section className="tn-card" data-testid="freq">
      <div className="tn-head"><h2>{T("fq_title")}</h2></div>
      <div className="tn-scroll">
        <table className="tn-tbl" data-testid="freq-table"><thead><tr><th /><th>{T("fq_stable")}</th><th className="r">Ms</th><th className="r">GM</th>
          <th className="r">PM [°]</th><th className="r">ωc [rad/s]</th><th className="r">{T("fq_bw")}</th></tr></thead>
          <tbody>{data.map((r) => (
            <tr key={r.name}><td>{name(r.name)}</td><td>{r.stable ? "✓" : "✗"}</td><td className="r mono">{n(r.Ms, 2)}</td>
              <td className="r mono">{n(r.GM, 2)}</td><td className="r mono">{n(r.PM, 0)}</td>
              <td className="r mono">{r.wc ? r.wc.toPrecision(3) : "–"}</td><td className="r mono">{r.bw ? r.bw.toPrecision(3) : "–"}</td></tr>))}
          </tbody></table>
      </div>
      <div className="tn-note">{T("fq_bode")}</div>
      <LineChart series={line("mag_db")} height={180} logX yLabel={T("fq_mag")} testid="freq-mag" />
      <LineChart series={line("phase_deg")} height={160} logX yLabel={T("fq_phase")} xLabel={T("fq_w")} testid="freq-phase" />
      <div className="tn-note">{T("fq_sens")}</div>
      <LineChart series={[...line("S_db"), ...line("T_db", "5 4")]} height={180} logX yLabel="dB" xLabel={T("fq_w")}
        testid="freq-sens" />
      <div className="tn-note">{T("fq_nyquist")}</div>
      <LineChart series={nyq(data, name)} height={696} xDomain={[-NYQ_LIM, 1.5]} yDomain={[-NYQ_LIM, 1.5]} xLabel="Re L"
        yLabel="Im L" testid="freq-nyq" />
      <div className="tn-note">{T("fq_help")}</div>
    </section>
  );
}

// Nyquist: pohled a kružnice Ms (střed −1, poloměr 1/Ms), kritický bod −1 (kříž; NaN přeruší čáru)
const NYQ_LIM = 3, MS_T = 1.6;
const inView = (x: number, y: number) => x >= -NYQ_LIM && x <= 1.5 && y >= -NYQ_LIM && y <= 1.5;
const MS_CIRCLE = { x: Array.from({ length: 200 }, (_, i) => -1 + Math.cos((2 * Math.PI * i) / 199) / MS_T),
  y: Array.from({ length: 200 }, (_, i) => Math.sin((2 * Math.PI * i) / 199) / MS_T) };
const CRIT = { x: [-1.06, -0.94, NaN, -1, -1], y: [0, 0, NaN, -0.06, 0.06] };

// Nyquistův diagram L: body mimo pohled se vynechají (NaN); výška 696 = stejné měřítko os, kružnice je kruh
function nyq(data: FreqSet[], name: (n: string) => string): Series[] {
  return [{ name: `Ms = ${MS_T}`, x: MS_CIRCLE.x, y: MS_CIRCLE.y, color: "#9aa5b1", dash: "4 3" },
    ...data.map((r) => ({ name: name(r.name),
      x: r.re.map((x, i) => (inView(x, r.im[i]) ? x : NaN)), y: r.im.map((y, i) => (inView(r.re[i], y) ? y : NaN)),
      color: SET_COLORS[r.name] ?? "#888" })),
    { name: "−1", x: CRIT.x, y: CRIT.y, color: "#b91c1c" }];
}
