// Záložka Ladění (M16, M17): sady parametrů v PLC s robustností, návrh metodou s upozorněními a kontrolami, zápis do
// sady, porovnání metod, scénář, odezva (Set 1, Set 2, návrh) a ukazatele, frekvenční charakteristiky; panel: blok
// PIDConL a nastavení metod.
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { binary, request } from "../api/client";
import type { components } from "../api/schema";
import { series, unframe } from "../api/signals";
import { CheckSetting, NumSetting, SelectSetting } from "../components/Fields";
import { LineChart, type Series } from "../components/LineChart";
import { useSettings, useWs, useWsQuery } from "../data";
import { useT } from "../i18n";
import { dur } from "../lib/format";
import { useUi } from "../store";
import { CompareCard, FreqCard, ScenarioCard } from "./TuningMore";

type TuningInfo = components["schemas"]["TuningInfo"];
type Suggestion = components["schemas"]["Suggestion"];
type SimInfo = components["schemas"]["SimInfo"];
type ModelState = components["schemas"]["ModelState"];
type Pid = { Kc: number; Ti: number; Td: number };

export function TuningMain() {
  const T = useT();
  const wid = useUi((s) => s.wid);
  const dec = useUi((s) => s.lang) === "cs" ? "," : ".";
  const qc = useQueryClient();
  const ws = useWs().data;
  const st = useSettings().data ?? {};
  const info = useWsQuery<TuningInfo>("tuning", "/tuning");
  const [method, setMethod] = useState<string | null>(null);
  const [sug, setSug] = useState<Suggestion | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [spread, setSpread] = useState(false);
  const model = useWsQuery<ModelState>("model", "/model");
  const hasUnc = !!model.data?.uncertainty;                 // varianty z nejistoty (záložka Model)
  const sp = spread && hasUnc;
  const preview: Pid | null = sug ? { Kc: sug.Kc, Ti: sug.Ti, Td: sug.Td } : null;
  const simKey = ["ws", wid, "sim", info.data?.sets, preview, st, sp];
  // při přepočtu (jiná sada, nastavení, návrh) zůstane vidět předchozí výsledek – žádné blikání
  const sim = useQuery({ queryKey: [...simKey, "kpi"], enabled: !!info.data, placeholderData: keepPreviousData,
    queryFn: () => request<SimInfo>("POST", `/workspaces/${wid}/simulate`, { preview, spread: sp }) });
  const curves = useQuery({ queryKey: [...simKey, "curves"], enabled: !!info.data, placeholderData: keepPreviousData,
    queryFn: async () => unframe(await binary(`/workspaces/${wid}/simulate/curves`, { preview, spread: sp })) });

  if (!ws?.has_data) return <div className="card muted">{T("ui_no_data")}</div>;
  if (info.isError || (info.data === undefined && !info.isLoading)) return <div className="card muted">{T("need_model")}</div>;
  if (!info.data) return <div className="card muted">…</div>;
  const m = method ?? info.data.default_method;

  const calc = async () => {
    setErr(null);
    try { setSug(await request<Suggestion>("POST", `/workspaces/${wid}/tuning/suggest`, { method: m })); }
    catch (e) { setErr(String((e as Error).message)); }
  };
  const write = async (n: number) => {
    if (!sug) return;
    await request("PUT", `/workspaces/${wid}/tuning/sets/${n}`, { Kc: sug.Kc, Ti: sug.Ti, Td: sug.Td, log: { method: sug.method } });
    await qc.invalidateQueries({ queryKey: ["ws", wid] });
  };
  const chk = (key: string, args: Record<string, unknown>) =>
    T(key, { ...args, m: T("model_" + info.data!.model), th: dur(Number(args.th), dec), T: dur(Number(args.T), dec),
      kk: Number(args.kk ?? 0).toPrecision(3), r: Number(args.r ?? 0).toPrecision(3), g: Number(args.g ?? 0).toPrecision(4) });

  const sigs: { name: string; key: string; color: string; dash?: string }[] = [
    { name: "SP", key: "sp", color: "#9aa5b1", dash: "5 4" }, { name: "Set 1", key: "pv_1", color: "#64748b" },
    { name: "Set 2", key: "pv_2", color: "#15803d" }, ...(preview ? [{ name: T("dk_suggest"), key: "pv_sug", color: "#1f5fa8" }] : [])];
  const mvs = [{ name: "Set 1", key: "mv_1", color: "#64748b" }, { name: "Set 2", key: "mv_2", color: "#15803d" },
    ...(preview ? [{ name: T("dk_suggest"), key: "mv_sug", color: "#c2410c" }] : [])];
  const mk = (list: typeof sigs) => (curves.data ? list.flatMap((s) => {
    const x = series(curves.data!.meta, curves.data!.blob, s.key);
    return x ? [{ name: s.name, x: x.t, y: x.v, color: s.color, dash: s.dash }] : [];
  }) : []);
  // varianty z nejistoty (pv_x…) jako tenké šedé čáry pod hlavními průběhy; legenda jen jedna položka
  const cv = curves.data;
  const varPv: Series[] = sp && cv ? cv.meta.sigs.map((x) => x.name).filter((n) => n.startsWith("pv_x")).flatMap((n, i) => {
    const x = series(cv.meta, cv.blob, n);
    return x ? [{ name: T("unc_variants"), x: x.t, y: x.v, color: "#cbd2d9", width: 1, legend: i === 0 }] : [];
  }) : [];
  const k = (sim.data?.kpis ?? {}) as Record<string, Record<string, unknown> | null>;
  const kv = (n: string, f: (r: Record<string, unknown>) => unknown) => (k[n] ? f(k[n]!) : null);
  const step = (r: Record<string, unknown>) => (r.step ?? {}) as Record<string, number | null>;

  return (
    <div className="stack">
      <div className="card" data-testid="sets">
        <h3>{T("sets_title")}</h3>
        <table className="tbl"><thead><tr><th /><th>Gain</th><th>TI [s]</th><th>TD [s]</th><th>Ms</th><th>GM</th><th>PM [°]</th></tr></thead>
          <tbody>{info.data.sets.map((s) => {
            const mt = (s.metrics ?? {}) as Record<string, number | boolean | null>;
            return <tr key={s.n} data-testid={`set-row-${s.n}`}><td>Set {s.n}</td><td className="mono">{+s.gain.toPrecision(5)}</td>
              <td className="mono">{+s.ti.toPrecision(5)}</td><td className="mono">{+s.td.toPrecision(5)}</td>
              <td className="mono">{mt.stable === false ? "∞" : Number(mt.Ms ?? NaN).toFixed(2)}</td>
              <td className="mono">{Number(mt.GM ?? NaN).toFixed(1)}</td><td className="mono">{Number(mt.PM ?? NaN).toFixed(0)}</td></tr>;
          })}</tbody></table>
      </div>
      <div className="card" data-testid="suggest">
        <h3>{T("calc_title")}</h3>
        <div className="row">
          <select value={m} onChange={(e) => setMethod(e.target.value)} data-testid="method">
            {info.data.methods.map((x) => <option key={x} value={x}>{T("m_" + x)}</option>)}
          </select>
          <button className="btn primary" onClick={() => void calc()} data-testid="calc">{T("dk_calc")}</button>
        </div>
        {err && <div className="err small">{err}</div>}
        {sug && (
          <>
            <table className="tbl" data-testid="sug-values"><tbody>
              <tr><td>Gain</td><td className="mono">{+sug.Kc.toPrecision(4)}</td><td>TI</td><td className="mono">{+sug.Ti.toPrecision(4)} s</td>
                <td>TD</td><td className="mono">{+sug.Td.toPrecision(4)} s</td></tr></tbody></table>
            {sug.notes.map((n) => <div key={n.key} className="small muted">{T(n.key, n.args)}</div>)}
            {sug.checks.map((c) => <div key={c.key} className="warn small" data-testid="sug-check">⚠ {chk(c.key, c.args)}</div>)}
            <div className="row">
              <button className="btn" onClick={() => void write(2)} data-testid="to-set2">{T("tn_write_s2")}</button>
              <button className="btn" onClick={() => void write(1)}>{T("tn_write_s1")}</button>
            </div>
          </>
        )}
      </div>
      <CompareCard onPick={(q) => setSug({ method: q.method, Kc: q.Kc, Ti: q.Ti, Td: q.Td, notes: [], checks: [] })} />
      <ScenarioCard />
      <div className="card" data-testid="response">
        <label className="small" title={T("h_spread_on")}>
          <input type="checkbox" checked={sp} disabled={!hasUnc} data-testid="sim-spread"
            onChange={(e) => setSpread(e.target.checked)} /> {T("spread_on")}
        </label>
        <LineChart series={[...varPv, ...mk(sigs)]} height={220} yLabel={`PV ${String(st.u_pv ?? "")}`} xLabel="t [s]" testid="resp-pv" />
        <LineChart series={mk(mvs)} height={140} yLabel={`MV ${String(st.u_mv ?? "")}`} xLabel="t [s]" testid="resp-mv" />
        {sim.data && (
          <table className="tbl" data-testid="kpis"><thead><tr><th /><th>IAE</th><th>{T("kpi_over")}</th><th>{T("kpi_t90")}</th>
            <th>{T("kpi_settle")}</th></tr></thead><tbody>
            {[["1", "Set 1"], ["2", "Set 2"], ["sug", T("dk_suggest")]].filter(([n]) => n in k).map(([n, lab]) => (
              <tr key={n}><td>{lab}</td>
                <td className="mono">{k[n] ? Number(kv(n, (r) => r.iae)).toPrecision(4) : "∞"}</td>
                <td className="mono">{k[n] ? Number(kv(n, (r) => step(r).over) ?? 0).toFixed(1) : "–"}</td>
                <td className="mono">{k[n] ? dur(kv(n, (r) => step(r).t90) as number, dec) : "–"}</td>
                <td className="mono">{k[n] ? dur(kv(n, (r) => step(r).settle) as number, dec) : "–"}</td></tr>))}
          </tbody></table>
        )}
      </div>
      <FreqCard preview={preview} />
    </div>
  );
}

export function TuningSide() {
  const T = useT();
  const st = useSettings().data ?? {};
  const ws = useWs().data;
  if (!ws?.has_data) return null;
  const uPv = String(st.u_pv || "PV"), uMv = String(st.u_mv || "MV");
  return (
    <div className="stack">
      <section>
        <h3>{T("blk_title")}</h3>
        <NumSetting k="samp" label={T("sampletime")} min={0.001} />
        <NumSetting k="diffgain" label="DiffGain" min={0.1} />
        <NumSetting k="pv_lo" label="NormPV Low" title={T("h_normpv")} />
        <NumSetting k="pv_hi" label="NormPV High" title={T("h_normpv")} />
        <NumSetting k="mv_lo" label="NormMV Low" />
        <NumSetting k="mv_hi" label="NormMV High" />
        <NumSetting k="mvl_lo" label="MV_LoLim" />
        <NumSetting k="mvl_hi" label="MV_HiLim" />
        <NumSetting k="propfac" label="PropFacSP" min={0} step={0.1} />
        <CheckSetting k="dfb" label={T("dfb")} def />
      </section>
      <section>
        <h3>{T("blk_elems")}</h3>
        <NumSetting k="db" label={T("deadband")} min={0} />
        <SelectSetting k="db_mode" label={T("db_mode")} options={["cont", "step"] as const} def="cont" fmt={(x) => T("db_" + x)} />
        <NumSetting k="pvfilt" label={T("pvfilt")} min={0} />
        <NumSetting k="mvrate" label={T("mvrate", { u: uMv })} min={0} />
        <NumSetting k="sprate" label={T("sprate", { u: uPv })} min={0} />
      </section>
      <section>
        <h3>{T("method")}</h3>
        <SelectSetting k="ctype" label={T("ctrl_type")} options={["PI", "PID"] as const} def="PI" />
        <SelectSetting k="opt_crit" label={T("opt_crit")} options={["MIGO", "IAE", "ISE", "ITAE", "OVS"] as const} def="OVS"
          fmt={(x) => T("crit_" + x)} />
        <SelectSetting k="opt_target" label={T("opt_target")} options={["scen", "dist", "sp", "both"] as const} def="both"
          fmt={(x) => T("tgt_" + x)} />
        <SelectSetting k="opt_ovs" label={T("opt_ovs")} options={[0, 2, 5, 10] as const} def={2} fmt={(x) => `${x} %`} />
        <SelectSetting k="opt_ms" label={T("opt_ms")} options={[1.4, 1.6, 1.8, 2.0] as const} def={1.6} />
        <CheckSetting k="opt_robust" label={T("opt_robust")} />
      </section>
    </div>
  );
}
