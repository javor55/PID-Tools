// APC › Gain scheduling podle PV: úseky dat pracovních bodů (gs_r*), identifikace bodů jako úloha, ladění v bodech
// (klíče gs_*), hodnoty pro blok GainSched a ověření jedna sada vs. scheduling na nelineárním procesu.
import { useState } from "react";
import type { components } from "../../api/schema";
import { NumSetting, SelectSetting } from "../../components/Fields";
import { LineChart } from "../../components/LineChart";
import { usePatchSettings, useSettings, useWs } from "../../data";
import { useT } from "../../i18n";
import { useJobRunner } from "../../jobs";
import { type CurveDef, curveSeries, NumInput, num, useApc } from "./common";
import { Checks, Impl, PointTable, usePost, useSim } from "./parts";

type GsInfo = components["schemas"]["GsInfo"];
type GsSim = components["schemas"]["GsSim"];

const CTYPES = ["PI", "PID"] as const;
const NS = [2, 3] as const;

const useGs = () => useApc<GsInfo>("gainsched", "/apc/gainsched");

function Ranges({ inp }: { inp: GsInfo["inputs"] }) {
  const T = useT();
  const patch = usePatchSettings();
  // zapisují se všechny úseky najednou (API bere úseky z nastavení jen, když jsou platné všechny)
  const put = (i: number, j: 0 | 1, x: number) => void patch(Object.fromEntries(inp.ranges.map((r, k) =>
    [`gs_r${k + 1}`, k === i ? (j ? [r[0], x] : [x, r[1]]) : r])));
  return (
    <table className="tbl" data-testid="gs-ranges">
      <thead><tr><th>{T("gs_pt")}</th><th>{T("dk_from")}</th><th>{T("dk_to")}</th></tr></thead>
      <tbody>{inp.ranges.map((r, i) => (
        <tr key={i}><td>{i + 1}</td>
          <td><NumInput value={r[0]} testid={`gs-r${i + 1}-from`} onCommit={(x) => put(i, 0, x)} /></td>
          <td><NumInput value={r[1]} testid={`gs-r${i + 1}-to`} onCommit={(x) => put(i, 1, x)} /></td></tr>))}</tbody>
    </table>
  );
}

export function GainSchedSide() {
  const T = useT();
  const post = usePost();
  const run = useJobRunner();
  const q = useGs();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  if (!q.data) return null;
  const { inputs: inp, integ } = q.data;
  if (integ) return <div className="warn small" data-testid="gs-side-integ">⚠ {T("gs_integ")}</div>;
  const fit = async () => {
    setBusy(true); setErr(null);
    try {
      const j = await run("/apc/gainsched/fit", undefined, T("gs_fitting"));
      if (j.state !== "done") setErr(j.error ?? j.state);
    } catch (e) { setErr(String((e as Error).message)); }
    setBusy(false);
  };
  return (
    <div className="stack" data-testid="gs-side">
      <section>
        <h3>{T("dk_gs_points")}</h3>
        <SelectSetting k="gs_n" label={T("dk_gs_n")} options={NS} def={inp.n} />
        <Ranges inp={inp} />
        <div className="small muted">{T("gs_s1_help")}</div>
        <div className="row">
          <button className="btn" data-testid="gs-auto" onClick={() => void post("/apc/gainsched/auto")}>{T("gs_auto")}</button>
          <button className="btn primary" disabled={busy} data-testid="gs-fit" onClick={() => void fit()}>{T("dk_gs_fit")}</button>
        </div>
        {err && <div className="err small" data-testid="gs-fit-err">{err}</div>}
      </section>
      <section>
        <h3>{T("method")}</h3>
        <SelectSetting k="gs_m" label={T("method")} options={inp.methods} def={inp.method} fmt={(m) => T("m_" + m)} />
        <SelectSetting k="gs_ct" label={T("ctrl_type")} options={CTYPES} def={inp.ctype} />
        {inp.method === "SIMC" && <NumSetting k="gs_tcf" label={T("dk_gs_tcf")} def={inp.tcf_default} min={0.001} />}
        {inp.method === "OPT" && <NumSetting k="gs_ms" label={T("gs_ms")} def={inp.ms_default} min={1.05} />}
        <button className="btn" data-testid="gs-reset" title={T("h_apc_reset")}
          onClick={() => void post("/apc/gainsched/reset")}>{T("apc_reset")}</button>
      </section>
    </div>
  );
}

const SERIES = (T: (k: string) => string, p: string): CurveDef[] => [
  { name: T("gs_fixed"), key: `${p}_fixed`, color: "#9aa5b1", dash: "5 4" }, { name: T("gs_sched"), key: `${p}_sched`, color: "#15803d" }];

function SimCard({ d }: { d: GsInfo }) {
  const T = useT();
  const st = useSettings().data ?? {};
  const { sim, cv } = useSim<GsSim>(["gs-sim", d.inputs, d.points], "/apc/gainsched/simulate", "", {}, d.fitted);
  if (!d.fitted) return null;
  const pv = [{ name: "SP", key: "sp", color: "#64748b", dash: "2 3" }, ...SERIES(T, "pv")];
  return (
    <div className="card stack" data-testid="gs-sim">
      <h3>{T("gs_sim_title")}</h3>
      <div className="small muted">{T("gs_sim_help")}</div>
      <LineChart series={curveSeries(cv.data, pv)} height={220} yLabel={`PV ${String(st.u_pv ?? "")}`} xLabel={T("time_s")} testid="gs-pv" />
      <LineChart series={curveSeries(cv.data, SERIES(T, "mv"))} height={140} yLabel={`MV ${String(st.u_mv ?? "")}`} xLabel={T("time_s")} testid="gs-mv" />
      <LineChart series={curveSeries(cv.data, SERIES(T, "gain"))} height={120} yLabel="Gain" xLabel={T("time_s")} testid="gs-gain" />
      {sim.data && (
        <table className="tbl" data-testid="gs-kpis">
          <thead><tr><th>{T("gs_step")}</th><th>{T("gs_iae_fixed")}</th><th>{T("gs_iae_sched")}</th></tr></thead>
          <tbody>{sim.data.kpis.map((k, i) => (
            <tr key={i} data-testid={`gs-kpi-${i}`}><td>{num(k.from_x)} → {num(k.to_x)}</td>
              <td className="mono">{num(k.iae_fixed)}</td><td className="mono">{num(k.iae_sched)}</td></tr>))}</tbody>
        </table>
      )}
    </div>
  );
}

function PointsCard({ d }: { d: GsInfo }) {
  const T = useT();
  return (
    <div className="card stack" data-testid="gs-points">
      <h3>{T("gs_s2")}</h3>
      <table className="tbl">
        <thead><tr><th>{T("gs_pt")}</th><th>PV</th><th>MV</th><th>{T("ui_gs_fit_pct")}</th><th>Gain</th><th>TI [s]</th><th>TD [s]</th></tr></thead>
        <tbody>{d.points.map((p) => (
          <tr key={p.index} data-testid={`gs-point-${p.index}`}><td>{p.index + 1}</td><td className="mono">{num(p.x)}</td>
            <td className="mono">{num(p.u)}</td><td className="mono">{num(p.fit)}</td>
            <td className="mono" data-testid={`gs-gain-${p.index}`}>{num(p.gain)}</td>
            <td className="mono">{p.ti === null ? "–" : num(p.ti)}</td><td className="mono">{num(p.td)}</td></tr>))}</tbody>
      </table>
      <div className="small" data-testid="gs-fits">{T("dk_gs_fits", { f: d.points.map((p) => `${p.fit.toFixed(0)} %`).join(", ") })}
        {d.filled && <> · {T("dk_gs_filled")}</>}</div>
      <div className="small muted">{T("gs_pts_help")}</div>
    </div>
  );
}

export function GainSchedMain() {
  const T = useT();
  const ws = useWs().data;
  const q = useGs();
  if (!ws?.has_data) return <div className="card muted">{T("ui_no_data")}</div>;
  if (!q.data) return <div className="card muted">{q.isError ? T("need_model") : "…"}</div>;
  const d = q.data;
  if (d.integ) {
    return <div className="stack"><div className="card warn" data-testid="gs-integ">⚠ {T("gs_integ")}</div><Checks items={d.checks} /></div>;
  }
  return (
    <div className="stack">
      {d.stale && <div className="card warn small" data-testid="gs-stale">⚠ {T("gs_stale")}</div>}
      {d.spread != null && <div className="card small" data-testid="gs-spread">{T("gs_spread", { s: num(d.spread) })}</div>}
      {d.issues.map((k) => <div key={k} className="card warn small" data-testid="gs-issue">⚠ {T(k)}</div>)}
      {!d.fitted && <div className="card muted" data-testid="gs-need-fit">{T("dk_gs_need")}</div>}
      {d.fitted && <PointsCard d={d} />}
      {d.fitted && (
        <div className="card stack" data-testid="gs-table-card">
          <h3>{T("gs_tab_title")}</h3>
          <PointTable rows={d.table} testid="gs-table" />
        </div>
      )}
      <Impl text={d.impl_text} testid="gs-impl" />
      <Checks items={d.checks} />
      <SimCard d={d} />
    </div>
  );
}
