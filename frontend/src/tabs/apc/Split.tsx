// APC › Split range: vstupy (režim, bod rozdělení, mezera, model ventilu A) jsou v prohlížeči a jdou v těle požadavku;
// v hlavní ploše vyvážený bod, zesílení a Ms obou polovin, hodnoty pro šablonu, kontroly a simulace skoku SP přes b.
import type { components } from "../../api/schema";
import { LineChart } from "../../components/LineChart";
import { useSettings, useWs } from "../../data";
import { useT } from "../../i18n";
import { Bold, type CurveDef, curveSeries, num, useApc } from "./common";
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
    <div className="stack" data-testid="split-side">
      <section>
        <h3>{T("sr_setup")}</h3>
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
      </section>
      <section>
        <h3>{T("sr_valve_a")}</h3>
        <ModelEditor model={design.valve_a} values={body.valve_a ?? design.valve_a.values} edited={aEdited} testid="split-va"
          onChange={(p) => put({ valve_a: p })} onReset={() => clear(["valve_a"])} />
      </section>
    </div>
  );
}

function Halves({ d }: { d: SplitDesign }) {
  const T = useT();
  const cell = (h: SplitDesign["now"]["lower"]) => `K ${g(h.k)} · Ms ${h.ms == null ? "–" : h.ms.toFixed(2)}${h.stable ? "" : " ⚠"}`;
  return (
    <table className="tbl" data-testid="split-halves">
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
      <div className="card stack" data-testid="split-result">
        <div className="small"><Bold text={T("sr_result", { b: d.bstar.toFixed(1), lo: g(d.now.lower.k), up: g(d.now.upper.k),
          k: g(d.new.upper.k), f: g(d.corr) })} /></div>
        <Halves d={d} />
      </div>
      <div className="card stack" data-testid="split-template">
        <h3>{T("sm_apl_title")}</h3>
        <ValueTable testid="split-val" rows={[
          { key: "b", name: "b*", value: d.bstar, unit: "%" },
          { key: "gap", name: T("sr_gap"), value: d.gap, unit: "%" },
          { key: "corr", name: "Gain ×", value: d.corr, unit: "–" }]} />
        <div className="small"><Bold text={d.impl_text} /></div>
      </div>
      <div className="card stack"><Checks items={d.checks} testid="split-checks" /></div>
      <div className="card stack" data-testid="split-sim">
        <LineChart series={curveSeries(curves, pv)} height={220} yLabel={`PV ${upv}`} xLabel={T("time_s")} testid="split-pv" />
        <LineChart series={curveSeries(curves, u)} height={140} yLabel={T("sr_u")} xLabel={T("time_s")} testid="split-u" />
        <LineChart series={curveSeries(curves, v)} height={140} yLabel={T("sr_valves")} xLabel={T("time_s")} testid="split-valves" />
        {sim && (
          <table className="tbl" data-testid="split-kpis">
            <thead><tr><th>{T("setting")}</th><th>{`IAE [${upv}·s]`}</th><th>{T("kpi_maxdev", { u: upv })}</th><th>{T("kpi_rev")}</th></tr></thead>
            <tbody>{(["now", "new"] as const).map((k) => (
              <tr key={k} data-testid={`split-kpi-${k}`}><td>{T("sr_" + k)}</td><td className="mono">{num(sim.kpis[k]?.iae)}</td>
                <td className="mono">{num(sim.kpis[k]?.maxdev)}</td><td className="mono">{sim.kpis[k]?.rev}</td></tr>))}</tbody>
          </table>
        )}
      </div>
    </div>
  );
}
