// APC › Regulace polohy ventilu (VPC): vstupy (model MV2, SP polohy, násobek τc, porucha) jsou v prohlížeči a jdou
// v těle požadavku; v hlavní ploše PI regulátor VPC, hodnoty pro šablonu, kontroly a simulace poruchy bez VPC / s ním.
import type { components } from "../../api/schema";
import { LineChart, type Series } from "../../components/LineChart";
import { useSettings, useWs } from "../../data";
import { useT } from "../../i18n";
import { Bold, type CurveDef, curveSeries, num, useApc } from "./common";
import { Checks, g, mergeBody, ModelEditor, NumField, useDesign, useEdits, useSim, ValueTable } from "./moreCommon";

type VpcIn = components["schemas"]["VpcIn"];
type VpcInfo = components["schemas"]["VpcInfo"];
type VpcDesign = components["schemas"]["VpcDesign"];
type VpcSim = components["schemas"]["VpcSim"];

function useVpc() {
  const { ov, put, clear } = useEdits<VpcIn>("vpc");
  const q = useApc<VpcInfo>("vpc", "/apc/vpc");
  const body = mergeBody(q.data?.defaults, ov);
  return { q, ov, put, clear, body, design: useDesign<VpcDesign>("vpc", body, q.data?.design) };
}

export function VpcSide() {
  const T = useT();
  const { q, ov, put, clear, body, design } = useVpc();
  if (!q.data || !body || !design) return null;
  return (
    <div className="stack" data-testid="vpc-side">
      <section>
        <h3>{T("vpc_mv2")}</h3>
        <ModelEditor model={design.mv2} values={body.mv2 ?? design.mv2.values} edited={ov.mv2 !== undefined} testid="vpc-mv2"
          onChange={(p) => put({ mv2: p })} onReset={() => clear(["mv2"])} />
      </section>
      <section>
        <h3>{T("vpc_setup")}</h3>
        <NumField label={T("vpc_sp")} value={body.sp} lo={5} hi={95} testid="vpc-sp" title={T("h_vpc_sp")} onCommit={(x) => put({ sp: x })} />
        <NumField label={T("vpc_factor")} value={body.factor} lo={1} hi={30} testid="vpc-factor" title={T("h_vpc_factor")}
          onCommit={(x) => put({ factor: x })} />
        <NumField label={T("vpc_d")} value={body.d} lo={-100} hi={100} testid="vpc-d" title={T("h_vpc_d")} onCommit={(x) => put({ d: x })} />
        <button className="btn" title={T("h_apc_reset")} data-testid="vpc-reset"
          disabled={ov.sp === undefined && ov.factor === undefined && ov.d === undefined}
          onClick={() => clear(["sp", "factor", "d"])}>{T("apc_reset")}</button>
      </section>
    </div>
  );
}

export function VpcMain() {
  const T = useT();
  const ws = useWs().data;
  const st = useSettings().data ?? {};
  const { q, body, design: d } = useVpc();
  const { sim, curves } = useSim<VpcSim>("vpc", body);
  if (!ws?.has_data) return <div className="card muted">{T("ui_no_data")}</div>;
  if (!q.data || !body || !d) return <div className="card muted">{q.isError ? T("need_model") : "…"}</div>;
  const upv = String(st.u_pv ?? "PV");
  const [k, t, th] = d.surrogate.values;
  const pv: CurveDef[] = [{ name: "SP", key: "sp", color: "#9aa5b1", dash: "5 4" },
    { name: T("vpc_off"), key: "pv_off", color: "#64748b", dash: "5 4" }, { name: T("vpc_on"), key: "pv_on", color: "#15803d" }];
  const mv1: Series[] = curveSeries(curves, [{ name: T("vpc_off"), key: "mv1_off", color: "#64748b", dash: "5 4" },
    { name: T("vpc_on"), key: "mv1_on", color: "#1f5fa8" }]);
  if (mv1.length) mv1.push({ name: T("vpc_sp_short"), x: mv1[0].x, y: Array.from(mv1[0].x, () => body.sp), color: "#9aa5b1", dash: "5 4" });
  const mv2: CurveDef[] = [{ name: T("vpc_on"), key: "mv2_on", color: "#7c3aed" }];
  return (
    <div className="stack">
      <div className="card stack" data-testid="vpc-result">
        <div className="small"><Bold text={T("vpc_result", { g: g(d.controller.Kc, 4), ti: g(d.controller.Ti, 4), k: g(k), t: g(t, 4),
          th: g(th, 4), tc: g(d.tc, 4) })} /></div>
      </div>
      <div className="card stack" data-testid="vpc-template">
        <h3>{T("sm_apl_title")}</h3>
        <ValueTable testid="vpc-val" rows={[
          { key: "sp", name: T("vpc_sp"), value: body.sp, unit: "%" },
          { key: "kc", name: "Gain", value: d.controller.Kc, unit: "–" },
          { key: "ti", name: "TI", value: d.controller.Ti, unit: "s" },
          { key: "tc", name: "τc", value: d.tc, unit: "s" }]} />
        <div className="small"><Bold text={d.impl_text} /></div>
      </div>
      <div className="card stack"><Checks items={d.checks} testid="vpc-checks" /></div>
      <div className="card stack" data-testid="vpc-sim">
        <LineChart series={curveSeries(curves, pv)} height={220} yLabel={`PV ${upv}`} xLabel={T("time_s")} testid="vpc-pv" />
        <LineChart series={mv1} height={140} yLabel="MV1 [%]" xLabel={T("time_s")} testid="vpc-mv1" />
        <LineChart series={curveSeries(curves, mv2)} height={140} yLabel="MV2 [%]" xLabel={T("time_s")} testid="vpc-mv2-chart" />
        {sim && (
          <table className="tbl" data-testid="vpc-kpis">
            <thead><tr><th>{T("setting")}</th><th>{`IAE [${upv}·s]`}</th><th>{T("vpc_at_lim")}</th><th>{T("vpc_reserve")}</th></tr></thead>
            <tbody>{(["off", "on"] as const).map((v) => (
              <tr key={v} data-testid={`vpc-kpi-${v}`}><td>{T("vpc_" + v)}</td><td className="mono">{num(sim.kpis[v]?.iae)}</td>
                <td className="mono">{num(sim.kpis[v]?.at_lim)}</td><td className="mono">{num(sim.kpis[v]?.reserve)}</td></tr>))}</tbody>
          </table>
        )}
      </div>
    </div>
  );
}
