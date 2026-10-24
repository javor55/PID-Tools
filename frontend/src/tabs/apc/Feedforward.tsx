// APC › Dopředná vazba: nastavení po měřených poruchách (PUT /apc/ff, částečné změny), hodnoty pro PIDConL a ověření
// skokem poruchy bez FF / se statickou / s dynamickou (KPI a křivky PV, MV).
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { binary, request } from "../../api/client";
import type { components } from "../../api/schema";
import { unframe } from "../../api/signals";
import { LineChart } from "../../components/LineChart";
import { useWs } from "../../data";
import { useT } from "../../i18n";
import { useUi } from "../../store";
import { type CurveDef, curveSeries, NumInput, num, useApc } from "./common";

type FFInfo = components["schemas"]["FFInfo"];
type FFDist = components["schemas"]["FFDist"];
type FFDesignIn = Partial<FFDist["design"]>;
type FFSim = components["schemas"]["FFSim"];

const VARIANTS: { k: "none" | "static" | "dynamic"; color: string; dash?: string }[] = [{ k: "none", color: "#9aa5b1", dash: "5 4" }, { k: "static", color: "#1f5fa8", dash: "5 4" },
  { k: "dynamic", color: "#15803d" }];

function DistCard({ d, info, put, reset }: { d: FFDist; info: FFInfo; put: (j: number, p: FFDesignIn) => void;
  reset: (j: number) => void }) {
  const T = useT();
  const g = (x: number) => +x.toPrecision(4);
  const nm = d.name;
  const field = (key: "gain" | "lead" | "lag" | "delay", label: string, min?: number) => (
    <label className="field" key={key}><span>{label}</span>
      <NumInput value={d.design[key]} min={min} testid={`ff-${key}-${d.index}`} onCommit={(x) => put(d.index, { [key]: x })} />
    </label>);
  return (
    <div className="card stack" data-testid={`ff-dist-${d.index}`}>
      <h3>{T("ff_dist_title", { d: nm })}
        {d.edited && <span className="warn small" data-testid={`ff-edited-${d.index}`}> · {T("ui_edited")}</span>}</h3>
      <div className="row">
        <label className="small"><input type="checkbox" checked={d.design.use} data-testid={`ff-use-${d.index}`}
          onChange={(e) => put(d.index, { use: e.target.checked })} /> {T("ff_use", { d: nm })}</label>
        <label className="small"><input type="checkbox" checked={d.design.dyn} data-testid={`ff-dyn-${d.index}`}
          onChange={(e) => put(d.index, { dyn: e.target.checked })} /> {T("ff_dyn")}</label>
      </div>
      <div className="apc-grid">
        {field("gain", T("ff_gain", { d: nm }))}
        {field("lead", T("ff_lead"), 0)}
        {field("lag", T("ff_lag"), 0)}
        {field("delay", T("ff_delay"), 0)}
      </div>
      <div className="small" data-testid={`ff-eng-${d.index}`}>{T("ff_gain_eng", { u: info.mv_unit, d: nm })}: <b className="mono">
        {num(d.eng_gain)}</b></div>
      <div className="small muted">{T("ff_proposal", { g: g(d.defaults.gain), tl: g(d.defaults.lead), tg: g(d.defaults.lag),
        dl: g(d.defaults.delay) })}</div>
      <div className="row">
        <button className="btn" disabled={!d.edited} title={T("h_ff_reset")} data-testid={`ff-reset-${d.index}`}
          onClick={() => reset(d.index)}>{T("apc_reset")}</button>
      </div>
      {d.values.length > 0 && (
        <table className="tbl" data-testid={`ff-values-${d.index}`}>
          <thead><tr><th>{T("sm_gen_par")}</th><th>{T("sm_apl_value")}</th><th>{T("sm_apl_unit")}</th></tr></thead>
          <tbody>{d.values.map((r) => <tr key={r.param}><td>{r.param}</td><td className="mono">{num(r.value)}</td><td>{r.unit}</td></tr>)}</tbody>
        </table>
      )}
    </div>
  );
}

function SimCard({ info }: { info: FFInfo }) {
  const T = useT();
  const wid = useUi((s) => s.wid);
  const [sel, setSel] = useState(0);
  const [steps, setSteps] = useState<Record<number, number>>({});
  const j = Math.min(sel, info.dists.length - 1);
  const dd = info.dists[j];
  const step = steps[j] ?? dd.step;
  const key = ["ws", wid, "apc", "ff-sim", j, step, info.dists.map((d) => d.design)];
  const body = { dist: j, step };
  const sim = useQuery({ queryKey: [...key, "kpi"], placeholderData: keepPreviousData,
    queryFn: () => request<FFSim>("POST", `/workspaces/${wid}/apc/ff/simulate`, body) });
  const cv = useQuery({ queryKey: [...key, "curves"], placeholderData: keepPreviousData,
    queryFn: async () => unframe(await binary(`/workspaces/${wid}/apc/ff/simulate/curves`, body)) });
  const defs = (p: string): CurveDef[] => VARIANTS.map((v) => ({ name: T("ff_" + v.k), key: `${p}_${v.k}`, color: v.color, dash: v.dash }));
  return (
    <div className="card stack" data-testid="ff-sim">
      <h3>{T("ff_sim_title")}</h3>
      <div className="apc-grid">
        <label className="field"><span>{T("ff_sim_dist")}</span>
          <select value={j} data-testid="ff-sim-dist" onChange={(e) => setSel(+e.target.value)}>
            {info.dists.map((d) => <option key={d.index} value={d.index}>{d.name}</option>)}</select></label>
        <label className="field"><span>{T("ff_step", { d: dd.name })}</span>
          <NumInput value={step} testid="ff-sim-step" onCommit={(x) => setSteps({ ...steps, [j]: x })} /></label>
      </div>
      <div className="small muted">{T("ff_sim_help")}</div>
      <LineChart series={curveSeries(cv.data, defs("pv"))} height={220} yLabel="PV" xLabel={T("time_s")} testid="ff-pv" />
      <LineChart series={curveSeries(cv.data, defs("mv"))} height={140} yLabel={`MV ${info.mv_unit}`} xLabel={T("time_s")} testid="ff-mv" />
      {sim.data && (
        <table className="tbl" data-testid="ff-kpis">
          <thead><tr><th>{T("setting")}</th><th>{T("iae_load")}</th><th>{T("ff_maxdev")}</th></tr></thead>
          <tbody>{VARIANTS.map((v) => (
            <tr key={v.k} data-testid={`ff-kpi-${v.k}`}><td>{T("ff_" + v.k)}</td>
              <td className="mono">{num(sim.data.kpis[v.k]?.iae)}</td><td className="mono">{num(sim.data.kpis[v.k]?.maxdev)}</td></tr>))}</tbody>
        </table>
      )}
    </div>
  );
}

export function FeedforwardMain() {
  const T = useT();
  const wid = useUi((s) => s.wid);
  const qc = useQueryClient();
  const ws = useWs().data;
  const q = useApc<FFInfo>("ff", "/apc/ff");
  const key = ["ws", wid, "apc", "ff"];
  if (!ws?.has_data) return <div className="card muted">{T("ui_no_data")}</div>;
  if (!q.data) return <div className="card muted">{q.isError ? T("need_model") : "…"}</div>;
  const info = q.data;
  if (!info.dists.length) return <div className="card muted" data-testid="ff-none">{T("ff_need_dist")}</div>;
  const done = () => qc.invalidateQueries({ queryKey: ["ws", wid] });
  // změna hned v rozhraní (optimisticky), pak PUT (částečná změna jedné poruchy) a znovu načíst
  const put = async (j: number, patch: FFDesignIn) => {
    qc.setQueryData<FFInfo>(key, (old) => old && { ...old, dists: old.dists.map((d) =>
      (d.index === j ? { ...d, design: { ...d.design, ...patch } } : d)) });
    await request("PUT", `/workspaces/${wid}/apc/ff`, info.dists.map((d) => (d.index === j ? patch : null)));
    await done();
  };
  const reset = async (index?: number) => {
    await request("POST", `/workspaces/${wid}/apc/ff/reset`, index === undefined ? {} : { index });
    await done();
  };
  return (
    <div className="stack">
      <div className="card row" style={{ alignItems: "center", justifyContent: "space-between" }}>
        <h3 style={{ margin: 0 }}>{T("dk_ff_setup")}</h3>
        <button className="btn" disabled={!info.dists.some((d) => d.edited)} title={T("h_ff_reset")} data-testid="ff-reset-all"
          onClick={() => void reset()}>{T("ff_reset")}</button>
      </div>
      {info.dists.map((d) => <DistCard key={d.index} d={d} info={info} put={(j, p) => void put(j, p)} reset={(j) => void reset(j)} />)}
      {!info.dists.some((d) => d.design.use) && <div className="card muted" data-testid="ff-all-off">{T("ff_none_on")}</div>}
      <SimCard info={info} />
    </div>
  );
}
