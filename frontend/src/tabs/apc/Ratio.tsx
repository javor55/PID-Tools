// APC › Poměr + křížové omezení: vstupy (zdroj a model vzduchu, R, skok požadavku) jsou v prohlížeči a jdou v těle
// požadavku; v hlavní ploše implementace, kontroly a simulace skoku výkonu bez křížového omezení / s ním.
import type { components } from "../../api/schema";
import { LineChart, type Series } from "../../components/LineChart";
import { SideCard } from "../../components/Ui";
import { useWs } from "../../data";
import { useT } from "../../i18n";
import { Bold, type CurveDef, curveSeries, useApc } from "./common";
import { ACard, VariantTable } from "./parts";
import { Checks, g, mergeBody, ModelEditor, NumField, useDesign, useEdits, useSim, ValueTable } from "./moreCommon";

type RatioIn = components["schemas"]["RatioIn"];
type RatioInfo = components["schemas"]["RatioInfo"];
type RatioDesign = components["schemas"]["RatioDesign"];
type RatioSim = components["schemas"]["RatioSim"];

function useRatio() {
  const { ov, put, clear } = useEdits<RatioIn>("ratio");
  const loop = ov.air_loop ?? null;
  const q = useApc<RatioInfo>(`ratio-${loop}`, `/apc/ratio${loop === null ? "" : `?air_loop=${loop}`}`);
  const body = mergeBody(q.data?.defaults, ov);
  return { q, ov, put, clear, body, design: useDesign<RatioDesign>("ratio", body, q.data?.design) };
}

export function RatioSide() {
  const T = useT();
  const { q, ov, put, clear, body, design } = useRatio();
  if (!q.data || !body || !design) return null;
  const manual = body.air_loop == null;
  return (
    <>
      <SideCard title={T("ra_air")} testid="ratio-side">
        <label className="field" title={T("h_ra_src")}><span>{T("ra_src")}</span>
          <select value={body.air_loop ?? ""} data-testid="ratio-src"
            onChange={(e) => put({ air_loop: e.target.value === "" ? undefined : +e.target.value, air: undefined })}>
            <option value="">{T("ra_manual")}</option>
            {design.sources.map((s) => <option key={s.index} value={s.index}>{s.name}</option>)}</select></label>
        <ModelEditor model={design.air} values={body.air ?? design.air.values} edited={ov.air !== undefined} testid="ratio-air"
          disabled={!manual} onChange={(p) => put({ air: p })} onReset={() => clear(["air"])} />
      </SideCard>
      <SideCard title={T("ra_setup")}>
        <NumField label={T("ra_R")} value={body.R} lo={0.01} hi={100} testid="ratio-R" title={T("h_ra_R")} onCommit={(x) => put({ R: x })} />
        <NumField label={T("ra_step")} value={body.step} lo={-50} hi={50} testid="ratio-step" title={T("h_ra_step")}
          onCommit={(x) => put({ step: x })} />
        <button className="btn" title={T("h_apc_reset")} data-testid="ratio-reset"
          disabled={ov.R === undefined && ov.step === undefined} onClick={() => clear(["R", "step"])}>{T("apc_reset")}</button>
      </SideCard>
    </>
  );
}

export function RatioMain() {
  const T = useT();
  const ws = useWs().data;
  const { q, body, design: d } = useRatio();
  const { sim, curves } = useSim<RatioSim>("ratio", body);
  if (!ws?.has_data) return <div className="card muted">{T("ui_no_data")}</div>;
  if (!q.data || !body || !d) return <div className="card muted">{q.isError ? T("need_model") : "…"}</div>;
  const flows: Series[] = curveSeries(curves, [{ name: T("ra_demand"), key: "demand", color: "#9aa5b1", dash: "5 4" },
    { name: T("ra_fuel"), key: "fuel", color: "#1f5fa8" }, { name: T("ra_air_r"), key: "air_r", color: "#0891b2" },
    { name: `${T("ra_air_r")} – ${T("ra_plain")}`, key: "air_r_plain", color: "#9aa5b1", dash: "5 4" }]);
  const lam: CurveDef[] = [{ name: T("ra_cross"), key: "lam", color: "#15803d" },
    { name: T("ra_plain"), key: "lam_plain", color: "#64748b", dash: "5 4" }];
  const lamS: Series[] = curveSeries(curves, lam);
  if (lamS.length) lamS.push({ name: "λ = 1", x: lamS[0].x, y: Array.from(lamS[0].x, () => 1), color: "#dc2626", dash: "5 4" });
  const V = ["plain", "cross"] as const;
  return (
    <div className="stack">
      <ACard title={T("ui_apc_verify")} testid="ratio-sim">
        <LineChart series={flows} height={220} yLabel={T("ra_flows")} xLabel={T("time_s")} testid="ratio-flows" />
        <LineChart series={lamS} height={140} yLabel="λ" xLabel={T("time_s")} testid="ratio-lam" />
      </ACard>
      <ACard title={T("ui_apc_result")} testid="ratio-res">
        {sim && <div className="small" data-testid="ratio-result"><Bold text={T("ra_result", {
          a: sim.lam_min.plain.toFixed(3), b: sim.lam_min.cross.toFixed(3) })} /></div>}
        {sim && (
          <VariantTable testid="ratio-kpis" cols={V.map((k) => ({ key: k, label: T("ra_" + k) }))} rows={[
            { key: "lam_min", label: T("ra_lam_min"), best: "max", values: V.map((k) => sim.kpis[k]?.lam_min) },
            { key: "t_rich", label: T("ra_t_rich"), best: "min", values: V.map((k) => sim.kpis[k]?.t_rich) },
            { key: "iae", label: T("ra_iae"), best: "min", values: V.map((k) => sim.kpis[k]?.iae) }]} />
        )}
      </ACard>
      <ACard title={T("ff_tab_title")} help={T("ui_apc_pcs_h")} testid="ratio-template">
        <ValueTable testid="ratio-val" rows={[{ key: "R", name: "R", value: body.R, unit: "%/%" }]} />
        <div className="small"><Bold text={d.impl_text} /></div>
        <div className="small muted">{T("model_" + d.air.code)}: {d.air.params.map((n, i) => `${n} = ${g(d.air.values[i], 4)}`).join(", ")}</div>
      </ACard>
      <Checks items={d.checks} testid="ratio-checks" />
    </div>
  );
}
