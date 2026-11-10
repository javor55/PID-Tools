// APC › Split range: vstupy (režim, bod rozdělení, mezera, model ventilu A) jsou v prohlížeči a jdou v těle požadavku;
// v hlavní ploše vyvážený bod, zesílení a Ms obou polovin, hodnoty pro šablonu, kontroly a simulace skoku SP přes b.
import type { components } from "../../api/schema";
import { LineChart } from "../../components/LineChart";
import { SideCard } from "../../components/Ui";
import { useSettings, useWs } from "../../data";
import { useT } from "../../i18n";
import { Bold, type CurveDef, curveSeries, useApc } from "./common";
import { ACard, VariantTable } from "./parts";
import { Checks, g, mergeBody, ModelEditor, NumField, useDesign, useEdits, useSim, ValueTable } from "./moreCommon";

type SplitIn = components["schemas"]["SplitIn"];
type SplitInfo = components["schemas"]["SplitInfo"];
type SplitDesign = components["schemas"]["SplitDesign"];
type SplitSim = components["schemas"]["SplitSim"];

const MODES = ["opposite", "sequence"] as const;

/** Výchozí vstupy z GET (model ventilu A závisí na režimu a b₀) a upravené vstupy → tělo požadavků. */
function useSplit() {
  const { ov, put, clear } = useEdits<SplitIn>("split");
  const mode = ov.mode ?? "opposite", b0 = ov.b0 ?? 50, gap = ov.gap ?? 0;
  const q = useApc<SplitInfo>(`split-${mode}-${b0}-${gap}`, `/apc/split?mode=${mode}&b0=${b0}&gap=${gap}`);
  const body = mergeBody(q.data?.defaults, ov);
  return { q, ov, put, clear, body, design: useDesign<SplitDesign>("split", body, q.data?.design) };
}

export function SplitSide() {
  const T = useT();
  const { q, ov, put, clear, body, design } = useSplit();
  if (!q.data || !body || !design) return null;
  const aEdited = ov.valve_a !== undefined;
  return (
    <>
      <SideCard title={T("sr_setup")} testid="split-side">
        <label className="field"><span>{T("sr_mode")}</span>
          <select value={body.mode} data-testid="split-mode"
            onChange={(e) => put({ mode: e.target.value as SplitIn["mode"], valve_a: undefined })}>
            {MODES.map((m) => <option key={m} value={m}>{T("sr_" + m)}</option>)}</select></label>
        <NumField label={T("sr_b0")} value={body.b0} lo={1} hi={99} testid="split-b0" title={T("h_sr_b0")}
          onCommit={(x) => put({ b0: x })} />
        <NumField label={T("sr_gap")} value={body.gap} lo={-20} hi={20} testid="split-gap" title={T("h_sr_gap")}
          onCommit={(x) => put({ gap: x })} />
        <button className="btn" title={T("h_apc_reset")} data-testid="split-reset"
          disabled={ov.b0 === undefined && ov.gap === undefined} onClick={() => clear(["b0", "gap"])}>{T("apc_reset")}</button>
      </SideCard>
      <SideCard title={T("sr_valve_a")}>
        <ModelEditor model={design.valve_a} values={body.valve_a ?? design.valve_a.values} edited={aEdited} testid="split-va"
          onChange={(p) => put({ valve_a: p })} onReset={() => clear(["valve_a"])} />
      </SideCard>
    </>
  );
}

function Halves({ d }: { d: SplitDesign }) {
  const T = useT();
  const cell = (h: SplitDesign["now"]["lower"]) => `K ${g(h.k)} · Ms ${h.ms == null ? "–" : h.ms.toFixed(2)}${h.stable ? "" : " ⚠"}`;
  return (
    <table className="apc-vt" data-testid="split-halves">
      <thead><tr><th></th><th>{T("sr_lower")}</th><th>{T("sr_upper")}</th></tr></thead>
      <tbody>{(["now", "new"] as const).map((k) => (
        <tr key={k} data-testid={`split-half-${k}`}><td>{T("sr_" + k)} (b = {d[k].b.toFixed(0)} %)</td>
          <td className="mono" data-testid={`split-half-${k}-lower`}>{cell(d[k].lower)}</td>
          <td className="mono" data-testid={`split-half-${k}-upper`}>{cell(d[k].upper)}</td></tr>))}</tbody>
    </table>
  );
}

export function SplitMain() {
  const T = useT();
  const ws = useWs().data;
  const st = useSettings().data ?? {};
  const { q, body, design: d } = useSplit();
  const { sim, curves } = useSim<SplitSim>("split", body);
  if (!ws?.has_data) return <div className="card muted">{T("ui_no_data")}</div>;
  if (!q.data || !body || !d) return <div className="card muted">{q.isError ? T("need_model") : "…"}</div>;
  const upv = String(st.u_pv ?? "PV");
  const pv: CurveDef[] = [{ name: "SP", key: "sp", color: "#9aa5b1", dash: "5 4" },
    { name: T("sr_now"), key: "pv_now", color: "#64748b", dash: "5 4" }, { name: T("sr_new"), key: "pv_new", color: "#15803d" }];
  const u: CurveDef[] = [{ name: T("sr_now"), key: "u_now", color: "#64748b", dash: "5 4" },
    { name: T("sr_new"), key: "u_new", color: "#15803d" }];
  const v: CurveDef[] = [{ name: T("sr_va"), key: "va", color: "#0891b2" }, { name: T("sr_vb"), key: "vb", color: "#1f5fa8" }];
  return (
    <div className="stack">
      <ACard title={T("ui_apc_verify")} testid="split-sim">
        <LineChart series={curveSeries(curves, pv)} height={220} yLabel={`PV ${upv}`} xLabel={T("time_s")} testid="split-pv" />
        <LineChart series={curveSeries(curves, u)} height={140} yLabel={T("sr_u")} xLabel={T("time_s")} testid="split-u" />
        <LineChart series={curveSeries(curves, v)} height={140} yLabel={T("sr_valves")} xLabel={T("time_s")} testid="split-valves" />
      </ACard>
      <ACard title={T("ui_apc_result")} testid="split-result">
        <div className="small"><Bold text={T("sr_result", { b: d.bstar.toFixed(1), lo: g(d.now.lower.k), up: g(d.now.upper.k),
          k: g(d.new.upper.k), f: g(d.corr) })} /></div>
        <Halves d={d} />
        {sim && (
          <VariantTable testid="split-kpis" cols={(["now", "new"] as const).map((k) => ({ key: k, label: T("sr_" + k) }))} rows={[
            { key: "iae", label: `IAE [${upv}·s]`, best: "min", values: (["now", "new"] as const).map((k) => sim.kpis[k]?.iae) },
            { key: "maxdev", label: T("kpi_maxdev", { u: upv }), best: "min", values: (["now", "new"] as const).map((k) => sim.kpis[k]?.maxdev) },
            { key: "rev", label: T("kpi_rev"), best: "min", values: (["now", "new"] as const).map((k) => sim.kpis[k]?.rev), fmt: String }]} />
        )}
      </ACard>
      <ACard title={T("ff_tab_title")} help={T("ui_apc_pcs_h")} testid="split-template">
        <ValueTable testid="split-val" rows={[
          { key: "b", name: "b*", value: d.bstar, unit: "%" },
          { key: "gap", name: T("sr_gap"), value: d.gap, unit: "%" },
          { key: "corr", name: "Gain ×", value: d.corr, unit: "–" }]} />
        <div className="small"><Bold text={d.impl_text} /></div>
      </ACard>
      <Checks items={d.checks} testid="split-checks" />
    </div>
  );
}
