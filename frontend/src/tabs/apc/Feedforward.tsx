// APC › Dopředná vazba (podle návrhu): v pravém panelu Model poruchy, Nastavení FF po měřených poruchách (PUT /apc/ff,
// částečné změny) a Scénář ověření; v ploše ověření skokem poruchy (bez FF / statická / dynamická), tabulka výsledků
// s nejlepší hodnotou a hodnoty do PCS 7 (PIDConL).
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import { create } from "zustand";
import { binary, request } from "../../api/client";
import type { components } from "../../api/schema";
import { unframe } from "../../api/signals";
import { LineChart } from "../../components/LineChart";
import { Seg, SideCard } from "../../components/Ui";
import { useWs } from "../../data";
import { useT } from "../../i18n";
import { useUi } from "../../store";
import { type CurveDef, curveSeries, NumInput, num, useApc } from "./common";
import { Checks } from "./moreCommon";
import { ACard, Impl, VariantTable } from "./parts";

type FFInfo = components["schemas"]["FFInfo"];
type FFDist = components["schemas"]["FFDist"];
type FFDesignIn = Partial<FFDist["design"]>;
type FFSim = components["schemas"]["FFSim"];

const VARIANTS: { k: "none" | "static" | "dynamic"; color: string; dash?: string }[] = [{ k: "none", color: "#9aa5b1", dash: "5 4" },
  { k: "static", color: "#1f5fa8", dash: "5 4" }, { k: "dynamic", color: "#15803d" }];
const TYPES = ["static", "dyn"] as const;

/** Scénář ověření (výběr poruchy a skok) sdílí postranní panel s plochou. */
const useScenario = create<{ sel: number; steps: Record<number, number>; set: (p: { sel?: number; step?: [number, number] }) => void }>((set) => ({
  sel: 0, steps: {},
  set: (p) => set((s) => ({ sel: p.sel ?? s.sel, steps: p.step ? { ...s.steps, [p.step[0]]: p.step[1] } : s.steps })),
}));

function useFf() {
  const wid = useUi((s) => s.wid);
  const qc = useQueryClient();
  const q = useApc<FFInfo>("ff", "/apc/ff");
  const key = ["ws", wid, "apc", "ff"];
  const done = () => qc.invalidateQueries({ queryKey: ["ws", wid] });
  const info = q.data;
  // změna hned v rozhraní (optimisticky), pak PUT (částečná změna jedné poruchy) a znovu načíst
  const put = async (j: number, patch: FFDesignIn) => {
    if (!info) return;
    qc.setQueryData<FFInfo>(key, (old) => old && { ...old, dists: old.dists.map((d) =>
      (d.index === j ? { ...d, design: { ...d.design, ...patch } } : d)) });
    await request("PUT", `/workspaces/${wid}/apc/ff`, info.dists.map((d) => (d.index === j ? patch : null)));
    await done();
  };
  const reset = async (index?: number) => {
    await request("POST", `/workspaces/${wid}/apc/ff/reset`, index === undefined ? {} : { index });
    await done();
  };
  return { q, info, put, reset };
}

function ModelCard({ info }: { info: FFInfo }) {
  const T = useT();
  const setTab = useUi((s) => s.setTab);
  const g = (x: number) => +x.toPrecision(4);
  return (
    <SideCard title={T("dist_model")} testid="ff-model">
      {info.dists.map((d) => {
        const [k, t, th] = d.model_params ?? [];
        return (
          <div key={d.index} className="small" data-testid={`ff-model-${d.index}`}>
            {info.dists.length > 1 && <b>{d.name}: </b>}
            {k === undefined ? "–" : T("ff_model", { k: g(k), t: g(t), th: g(th), tp: g(info.theta) })}
          </div>);
      })}
      {info.dists.map((d) => {
        const th = d.model_params?.[2];
        return d.design.use && th !== undefined && th < info.theta
          ? <div key={d.index} className="small apc-note">{T("ff_faster", { d: d.name, td: g(th), t: g(info.theta) })}</div> : null;
      })}
      <button type="button" className="link apc-link" onClick={() => setTab("model")}>{T("g_btn_model")}</button>
    </SideCard>
  );
}

function DistCard({ d, info, put, reset, several }: { d: FFDist; info: FFInfo; put: (j: number, p: FFDesignIn) => void;
  reset: (j?: number) => void; several: boolean }) {
  const T = useT();
  const g = (x: number) => +x.toPrecision(4);
  const nm = d.name;
  const field = (key: "gain" | "lead" | "lag" | "delay", label: string, min?: number) => (
    <label className="field" key={key}><span>{label}</span>
      <NumInput value={d.design[key]} min={min} testid={`ff-${key}-${d.index}`} onCommit={(x) => put(d.index, { [key]: x })} />
    </label>);
  return (
    <SideCard title={T("ff_dist_title", { d: nm })} testid={`ff-dist-${d.index}`} help={T("h_ff_gain")}
      aside={d.edited ? <span className="warn small" data-testid={`ff-edited-${d.index}`}>{T("ui_edited")}</span> : undefined}>
      <label className="apc-check"><input type="checkbox" checked={d.design.use} data-testid={`ff-use-${d.index}`}
        onChange={(e) => put(d.index, { use: e.target.checked })} /> {T("ff_use", { d: nm })}</label>
      <div className="field"><span>{T("ui_apc_type")}</span>
        <Seg value={d.design.dyn ? "dyn" : "static"} options={TYPES} label={T("ui_apc_type")} testid={`ff-dyn-${d.index}`} small
          fmt={(v) => T(v === "dyn" ? "ff_dynamic" : "ff_static")} titles={(v) => (v === "dyn" ? T("h_ff_dyn") : undefined)}
          onChange={(v) => put(d.index, { dyn: v === "dyn" })} /></div>
      {field("gain", T("ff_gain", { d: nm }))}
      {d.design.dyn && field("lead", T("ff_lead"), 0)}
      {d.design.dyn && field("lag", T("ff_lag"), 0)}
      {d.design.dyn && field("delay", T("ff_delay"), 0)}
      <div className="small" data-testid={`ff-eng-${d.index}`}>{T("ff_gain_eng", { u: info.mv_unit, d: nm })}: <b className="mono">
        {num(d.eng_gain)}</b></div>
      <div className="small muted">{T("ff_proposal", { g: g(d.defaults.gain), tl: g(d.defaults.lead), tg: g(d.defaults.lag),
        dl: g(d.defaults.delay) })}</div>
      <div className="row">
        <button className="btn" disabled={!d.edited} title={T("h_ff_reset")} data-testid={`ff-reset-${d.index}`}
          onClick={() => reset(d.index)}>{T("apc_reset")}</button>
        {several && <button className="btn" disabled={!info.dists.some((x) => x.edited)} title={T("h_ff_reset")}
          data-testid="ff-reset-all" onClick={() => reset()}>{T("ff_reset")}</button>}
      </div>
    </SideCard>
  );
}

export function FeedforwardSide() {
  const T = useT();
  const { info, put, reset } = useFf();
  const { sel, steps, set } = useScenario();
  if (!info?.dists.length) return null;
  const j = Math.min(sel, info.dists.length - 1);
  const dd = info.dists[j];
  return (
    <>
      <ModelCard info={info} />
      {info.dists.map((d) => <DistCard key={d.index} d={d} info={info} put={(i, p) => void put(i, p)}
        reset={(i) => void reset(i)} several={info.dists.length > 1} />)}
      <SideCard title={T("ui_apc_scenario")} testid="ff-scenario">
        <label className="field"><span>{T("ff_sim_dist")}</span>
          <select value={j} data-testid="ff-sim-dist" onChange={(e) => set({ sel: +e.target.value })}>
            {info.dists.map((d) => <option key={d.index} value={d.index}>{d.name}</option>)}</select></label>
        <label className="field"><span>{T("ff_step", { d: dd.name })}</span>
          <NumInput value={steps[j] ?? dd.step} testid="ff-sim-step" onCommit={(x) => set({ step: [j, x] })} /></label>
      </SideCard>
    </>
  );
}

function SimCards({ info }: { info: FFInfo }) {
  const T = useT();
  const wid = useUi((s) => s.wid);
  const { sel, steps } = useScenario();
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
  const kp = sim.data?.kpis;
  return (
    <>
      <ACard title={T("ff_sim_title")} testid="ff-sim">
        <LineChart series={curveSeries(cv.data, defs("pv"))} height={220} yLabel="PV" xLabel={T("time_s")} testid="ff-pv" />
        <LineChart series={curveSeries(cv.data, defs("mv"))} height={140} yLabel={`MV ${info.mv_unit}`} xLabel={T("time_s")} testid="ff-mv" />
        <p className="small muted">{T("ff_sim_help")}</p>
      </ACard>
      {kp && (
        <ACard title={T("ui_apc_result")} testid="ff-result">
          <VariantTable testid="ff-kpis" cols={VARIANTS.map((v) => ({ key: v.k, label: T("ff_" + v.k) }))} rows={[
            { key: "iae", label: T("iae_load"), best: "min", values: VARIANTS.map((v) => kp[v.k]?.iae) },
            { key: "maxdev", label: T("ff_maxdev"), best: "min", values: VARIANTS.map((v) => kp[v.k]?.maxdev) }]} />
        </ACard>
      )}
    </>
  );
}

function PcsCard({ info }: { info: FFInfo }) {
  const T = useT();
  const used = info.dists.filter((d) => d.design.use && d.values.length > 0);
  return (
    <ACard title={T("ff_tab_title")} help={T("ui_apc_pcs_h")} testid="ff-pcs">
      {!info.dists.some((d) => d.design.use) && <div className="muted small" data-testid="ff-all-off">{T("ff_none_on")}</div>}
      {used.map((d) => (
        <div key={d.index} className="apc-tblwrap">
          {info.dists.length > 1 && <div className="apc-sub">{d.name}</div>}
          <table className="apc-vt" data-testid={`ff-values-${d.index}`}>
            <thead><tr><th>{T("sm_apl_block")}</th><th className="r">{T("sm_apl_value")}</th><th>{T("sm_apl_unit")}</th></tr></thead>
            <tbody>{d.values.map((r) => <tr key={r.param}><th scope="row">{r.param}</th><td className="mono r">{num(r.value)}</td><td>{r.unit}</td></tr>)}</tbody>
          </table>
        </div>))}
      <p className="small muted">{T("ff_help")}</p>
    </ACard>
  );
}

export function FeedforwardMain() {
  const T = useT();
  const ws = useWs().data;
  const { q, info } = useFf();
  if (!ws?.has_data) return <div className="card muted">{T("ui_no_data")}</div>;
  if (!info) return <div className="card muted">{q.isError ? T("need_model") : "…"}</div>;
  if (!info.dists.length) {
    return (
      <div className="stack">
        <div className="card muted" data-testid="ff-none">{T("ff_need_dist")}</div>
        <Checks items={info.checks} testid="ff-checks" />
      </div>
    );
  }
  return (
    <div className="stack">
      <SimCards info={info} />
      <PcsCard info={info} />
      <Impl text={info.impl_text} testid="ff-impl" />
      <Checks items={info.checks} testid="ff-checks" />
    </div>
  );
}
