// Záložka Model, část 3 (E6): ověření modelu na jiném úseku (predikce z MV / simulace smyčky se Sadou 1 nebo 2,
// tabulka hodnocení na úseku identifikace a ověřovacím, verdikt) a pohledy na model (odezva na skok, porovnání modelů).
import { useState } from "react";
import type { components } from "../api/schema";
import { LineChart, type Series } from "../components/LineChart";
import { Help, Seg } from "../components/Ui";
import { useSettings, usePatchSettings, useWs, useWsQuery } from "../data";
import { useT } from "../i18n";
import { MV_STYLE } from "./modelConst";

type ModelState = components["schemas"]["ModelState"];
type ValidateOut = components["schemas"]["ValidateOut"];
type ValRow = components["schemas"]["ValRow"];
type StepOut = components["schemas"]["StepOut"];
type CompareOut = components["schemas"]["CompareOut"];

const nan = (a: (number | null)[]) => a.map((v) => (v === null ? NaN : v));
const COLORS: Record<string, string> = { P0D: "#0e7490", P1D: "#1f5fa8", P2D: "#7c3aed", I0D: "#b45309", I1D: "#be185d" };

/** Pole „od / do“ ověřovacího úseku [s] – potvrzení Enterem nebo opuštěním pole. */
function RangeInput({ label, value, onCommit, testid, help }: { label: string; value: number; onCommit: (v: number) => void;
  testid: string; help: string }) {
  const [v, setV] = useState<string | null>(null);
  return (
    <label className="small" title={help}>{label}{" "}
      <input className="num" type="number" step="any" value={v ?? Math.round(value * 10) / 10} data-testid={testid} title={help}
        onChange={(e) => setV(e.target.value)}
        onBlur={() => { if (v !== null && v !== "" && Number.isFinite(+v)) onCommit(+v); setV(null); }}
        onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }} />
    </label>
  );
}

function RatingTable({ v, unit }: { v: ValidateOut; unit: string }) {
  const T = useT();
  const rows: [string, ValRow][] = [[T("eval_id"), v.id], [T("eval_val"), v.val]];
  return (
    <table className="tbl" data-testid="val-rating">
      <thead><tr><th /><th>FIT [%]</th><th>NRMSE [%]</th><th>{T("eval_iae", { u: unit || "PV" })}</th><th>R²</th>
        <th>{T("eval_white")}</th><th>{T("eval_ccf")}</th><th>{T("col_status")}</th></tr></thead>
      <tbody>
        {rows.map(([name, m], i) => (
          <tr key={i} data-row={i === 0 ? "id" : "val"}>
            <td>{name}</td><td className="mono" data-testid={i === 0 ? "val-fit-id" : "val-fit-val"}>{m.FIT.toFixed(1)}</td>
            <td className="mono">{m.NRMSE.toFixed(2)}</td><td className="mono">{(m.IAE * v.pv_range / 100).toPrecision(3)}</td>
            <td className="mono">{m.R2.toFixed(3)}</td><td className="mono">{(100 * m.frac_acf).toFixed(0)} %</td>
            <td className="mono">{(100 * m.frac_ccf).toFixed(0)} %</td><td>{T("st_" + m.status)}</td>
          </tr>))}
      </tbody>
    </table>
  );
}

export function ValidationCard({ model }: { model: ModelState }) {
  const T = useT();
  const ws = useWs().data;
  const patch = usePatchSettings();
  const st = useSettings().data ?? {};
  const [mode, setMode] = useState<"pred" | "cl">("pred");
  const [which, setWhich] = useState<1 | 2>(1);
  const ok = !!model.current && !model.stale;
  const vr = st.val_rng as number[] | undefined;
  const hasSp = !!ws?.sp;
  const eff = mode === "cl" && hasSp ? "cl" : "pred";
  const q = `a=${vr?.[0] ?? ""}&b=${vr?.[1] ?? ""}`;
  const val = useWsQuery<ValidateOut>(`validate|${q}|${eff}|${which}|${model.selected}|${JSON.stringify(model.current)}`,
    `/model/validate?${vr ? q + "&" : ""}mode=${eff}&which=${which}`, ok);
  if (!ok) return null;
  const v = val.data;
  const setRange = (a: number, b: number) => { if (b > a) void patch({ val_rng: [a, b] }); };
  const end = ws?.rng ? Math.max(ws.rng[1], v?.rng[1] ?? 0) : (v?.rng[1] ?? 0);
  const unitPv = (st.u_pv as string) || "PV";
  const t = v ? nan(v.t) : [];
  const ser: Series[] = [];
  const serMv: Series[] = [];
  if (v) {
    if (v.sp) ser.push({ name: "SP", x: t, y: nan(v.sp), color: "#64748b", dash: "5 4", width: 1.4 });
    ser.push({ name: T("measured"), x: t, y: nan(v.pv), color: "#1f5fa8", width: 1.3 });
    if (v.sim_pv.length) ser.push({ name: `${T("simulated")} / ${T("prediction")}`, x: nan(v.sim_t), y: nan(v.sim_pv),
      color: which === 2 && eff === "cl" ? "#7c3aed" : MV_STYLE[0], width: 2.2 });
    serMv.push({ name: `MV ${T("measured")}`, x: t, y: nan(v.mv), color: "#c2410c", width: 1.3 });
    if (v.sim_mv) serMv.push({ name: `MV ${T("simulated")}`, x: nan(v.sim_t), y: nan(v.sim_mv),
      color: which === 2 ? "#7c3aed" : MV_STYLE[0], width: 2.2 });
  }
  return (
    <div className="card span-all" data-testid="val-seg">
      <h3>{T("val_title")} <Help text={T("val_intro")} /></h3>
      <div className="row">
        <RangeInput label={T("seg_val") + " · " + T("mw_start")} value={v?.rng[0] ?? 0} onCommit={(a) => setRange(a, v?.rng[1] ?? end)}
          testid="val-a" help={T("h_seg_val")} />
        <RangeInput label={T("mw_end")} value={v?.rng[1] ?? end} onCommit={(b) => setRange(v?.rng[0] ?? 0, b)}
          testid="val-b" help={T("h_seg_val")} />
        <button type="button" className="btn" data-testid="val-reset" title={T("mdl_ui_h_val_reset")}
          onClick={() => void patch({ val_rng: null })}>{T("mdl_ui_val_reset")}</button>
        <Seg value={mode} options={["pred", "cl"] as const} label={T("val_mode")} help="val_mode_help" testid="val-mode"
          fmt={(x) => T("val_" + x)} onChange={setMode} />
        {mode === "cl" && hasSp && (
          <Seg value={which} options={[1, 2] as const} label={T("val_params")} help="h_val_which" testid="val-which"
            fmt={(x) => T(x === 1 ? "val_cur" : "val_new")} onChange={setWhich} />)}
      </div>
      {mode === "cl" && !hasSp && <div className="warn small">{T("need_sp")}</div>}
      {val.isError && <div className="warn small" role="alert" data-testid="val-err">{T("err_short")}</div>}
      {v && (
        <>
          <div className="row small" data-testid="val-fits">
            <span>{eff === "pred" ? T("fit_pred") : T("fit_pv")}: <b className="mono" data-testid="val-fit-pv">
              {v.fit_pv == null ? "–" : v.fit_pv.toFixed(1) + " %"}</b></span>
            {eff === "cl" && <span>{T("fit_mv")}: <b className="mono">{v.fit_mv == null ? "–" : v.fit_mv.toFixed(1) + " %"}</b></span>}
          </div>
          {!v.stable && <div className="err small" role="alert">{T("err_sim_unstable", { n: T(which === 1 ? "val_cur" : "val_new") })}</div>}
          <div className={"small " + (v.verdict === "ok" ? "" : "warn")} data-testid="val-verdict" data-verdict={v.verdict}>
            {T("mdl_ui_verdict_" + v.verdict)}</div>
          <RatingTable v={v} unit={unitPv} />
          <div data-testid="val-chart" data-n={v.t.length}><LineChart series={ser} height={220} xLabel="t [s]" yLabel={unitPv} /></div>
          {eff === "cl" && <LineChart series={serMv} height={140} xLabel="t [s]" yLabel="MV" />}
          {eff === "cl" && <div className="muted small">{T("val_cl_help")}</div>}
        </>
      )}
    </div>
  );
}

/** Pohledy na model: odezva na skok MV o 10 % (nafitovaný / upravený / z otevřené smyčky / varianty z nejistoty) a porovnání všech modelů. */
export function ModelViews({ model }: { model: ModelState }) {
  const T = useT();
  const [view, setView] = useState<"step" | "all">("step");
  const ok = !!model.current && !model.stale;
  const step = useWsQuery<StepOut>(`step|${model.selected}|${JSON.stringify(model.current)}|${model.uncertainty ? 1 : 0}`,
    `/model/step?code=${model.selected}`, ok && view === "step");
  const cmp = useWsQuery<CompareOut>(`compare|${model.results.map((r) => r.code + r.fit).join()}`, "/model/compare",
    ok && view === "all");
  if (!ok) return null;
  const ser: Series[] = [];
  const s = step.data;
  if (view === "step" && s) {
    const x = nan(s.t);
    s.variants.forEach((y, i) => ser.push({ name: T("unc_variants"), x, y: nan(y), color: "#94a3b8", width: 1, legend: i === 0 }));
    if (s.open) ser.push({ name: T("idm_open_curve"), x, y: nan(s.open), color: "#94a3b8", dash: "2 3", width: 1.6 });
    ser.push({ name: T("fit"), x, y: nan(s.fit), color: COLORS[s.code] ?? MV_STYLE[0], width: 2.2 });
    if (s.edited) ser.push({ name: T("edited"), x, y: nan(s.edited), color: "#dc2626", dash: "5 4", width: 2 });
  }
  const c = cmp.data;
  if (view === "all" && c) {
    const x = nan(c.t);
    ser.push({ name: T("measured"), x, y: nan(c.pv), color: "#1f5fa8", width: 1.3 });
    c.models.forEach((m) => ser.push({ name: `${m.code} (${m.fit.toFixed(1)} %)`, x, y: nan(m.y), color: COLORS[m.code] ?? "#444", width: 1.8 }));
  }
  return (
    <div className="card span-all" data-testid="model-views">
      <h3>{T("compare_title")} <Help text={T("mdl_ui_h_views")} /></h3>
      <Seg value={view} options={["step", "all"] as const} label={T("compare_title")} testid="views-seg"
        fmt={(x) => (x === "step" ? T("step_title") : T("compare_all"))} onChange={setView} />
      <div data-testid={view === "step" ? "step-chart" : "compare-chart"} data-n={ser.length}>
        <LineChart series={ser} height={260} xLabel="t [s]" />
      </div>
    </div>
  );
}
