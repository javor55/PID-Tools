// Záložka Model, část 2 (M15): parametry vybraného modelu (procesu i poruch) s ruční úpravou a zafixováním,
// dofitování a návrat k nafitovaným hodnotám; ověření modelu (shoda, rezidua), křížové ověření, nejistota.
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { request } from "../api/client";
import type { components } from "../api/schema";
import { useSettings, useWsQuery } from "../data";
import { useT } from "../i18n";
import { useJobRunner } from "../jobs";
import { useUi } from "../store";
import { ModelResiduals } from "./ModelResiduals";

type ModelState = components["schemas"]["ModelState"];
type ModelRes = components["schemas"]["ModelRes"];
type Validation = components["schemas"]["Validation"];

function ParamRow({ label, edKey, fxKey, value }: { label: string; edKey: string; fxKey: string; value: number }) {
  const wid = useUi((s) => s.wid);
  const qc = useQueryClient();
  const st = useSettings().data ?? {};
  const [v, setV] = useState<string | null>(null);
  const patch = async (p: Record<string, unknown>) => {
    qc.setQueryData<Record<string, unknown>>(["ws", wid, "settings"], (old) => ({ ...(old ?? {}), ...p }));
    await request("PATCH", `/workspaces/${wid}/settings`, p);
    await qc.invalidateQueries({ queryKey: ["ws", wid] });
  };
  const cur = Number(st[edKey] ?? value);
  return (
    <tr>
      <td>{label}</td>
      <td><input className="num" type="number" step="any" value={v ?? +cur.toPrecision(6)} data-testid={`ed-${edKey}`}
        onChange={(e) => setV(e.target.value)}
        onBlur={() => { if (v !== null && v !== "" && Number.isFinite(+v)) void patch({ [edKey]: +v }); setV(null); }}
        onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }} /></td>
      <td><input type="checkbox" checked={!!st[fxKey]} aria-label={`fix ${label}`} data-testid={`fx-${fxKey}`}
        onChange={(e) => void patch({ [fxKey]: e.target.checked })} /></td>
    </tr>
  );
}

// Porovnání struktur přenosu měřené poruchy (FIT jen jejích parametrů) a výběr jiné struktury
function DistCompare({ code, j, d }: { code: string; j: number; d: ModelRes["dists"][number] }) {
  const T = useT();
  const wid = useUi((s) => s.wid);
  const qc = useQueryClient();
  const use = async (struct: string) => {
    await request("PUT", `/workspaces/${wid}/model/dist`, { code, index: j, struct });
    await qc.invalidateQueries({ queryKey: ["ws", wid] });
  };
  return (
    <div data-testid={`dist-cmp-${j}`}>
      <div className="small">{T("dkind")} · {d.name}</div>
      {d.flat && <div className="muted small">{T("ms_dv_flat")}</div>}
      <table className="tbl"><thead><tr><th>{T("ms_cmp_type")}</th><th>FIT [%]</th><th /><th /></tr></thead><tbody>
        {d.cmp.map((c) => (
          <tr key={c.struct} data-struct={c.struct} data-current={c.struct === d.struct ? 1 : 0}>
            <td>{T("model_" + c.struct)}{c.struct === d.ident ? ` · ${T("ms_dist_ident")}` : ""}</td>
            <td className="mono" data-testid={`dist-fit-${j}-${c.struct}`}>{c.fit == null ? "–" : c.fit.toFixed(1)}</td>
            <td>{c.struct === d.struct ? `✓ ${T("ms_cmp_use")}` : ""}</td>
            <td>{c.fit != null && c.struct !== d.struct && (
              <button className="btn" data-testid={`dist-use-${j}-${c.struct}`} onClick={() => void use(c.struct)}>{T("ui_dist_use")}</button>)}</td>
          </tr>))}
      </tbody></table>
    </div>
  );
}

export function ModelDetails({ model }: { model: ModelState }) {
  const T = useT();
  const wid = useUi((s) => s.wid);
  const qc = useQueryClient();
  const run = useJobRunner();
  const st = useSettings().data ?? {};
  const val = useWsQuery<Validation>("validation", "/model/validation", !!model.current && !model.stale);
  const [n, setN] = useState(15);
  const r: ModelRes | undefined = model.results.find((x) => x.code === model.selected);
  if (!r || !model.current) return null;
  const cur = model.current as { code: string; p: number[]; pdl: number[][] };
  const code = r.code;
  const reset = async () => {
    await request("POST", `/workspaces/${wid}/model/reset`, { code });
    await qc.invalidateQueries({ queryKey: ["ws", wid] });
  };
  const m = val.data?.metrics as Record<string, number> | undefined;
  const unc = model.uncertainty as { code: string; ps: number[][] } | null | undefined;
  const q = (a: number[], f: number) => { const s = [...a].sort((x, y) => x - y); return s[Math.min(s.length - 1, Math.floor(f * (s.length - 1) + 0.5))]; };

  return (
    <div className="grid2">
      <div className="card" data-testid="params">
        <h3>{T("dk_params")} · {T("model_" + code)}</h3>
        <table className="tbl"><thead><tr><th /><th /><th>{T("fix")}</th></tr></thead><tbody>
          {r.names.map((nm, i) => <ParamRow key={nm} label={nm} edKey={`ed|${code}|${i}`} fxKey={`fx|${code}|${i}`}
            value={cur.p[i]} />)}
          {r.dists.map((d, j) => d.fields.map(([fname, idx]) => (
            <ParamRow key={`${j}-${idx}`} label={`${fname} (${d.name})`} edKey={`ed|${code}|d${j}|${idx}`}
              fxKey={`fx|${code}|d${j}|${idx}`} value={Number(st[`ed|${code}|d${j}|${idx}`] ?? 0)} />)))}
        </tbody></table>
        <div className="row">
          <button className="btn" data-testid="refit" onClick={() => void run("/model/refit", { code }, T("refit"))}>{T("refit")}</button>
          <button className="btn" data-testid="reset" onClick={() => void reset()}>{T("dk_reset")}</button>
        </div>
      </div>
      {r.dists.some((d) => d.cmp.length > 0) && (
        <div className="card" data-testid="dist-cmp">
          <h3>{T("ms_cmp")} · {T("dkind")}</h3>
          {r.dists.map((d, j) => d.cmp.length > 0 && <DistCompare key={j} code={code} j={j} d={d} />)}
          <div className="muted small">{T("ms_cmp_dv_note")}</div>
        </div>
      )}
      <div className="card" data-testid="validation">
        <h3>{T("val_title")}</h3>
        {m ? (
          <table className="tbl"><tbody>
            <tr><td>FIT</td><td className="mono">{m.FIT?.toFixed(1)} %</td></tr>
            <tr><td>NRMSE</td><td className="mono">{m.NRMSE?.toFixed(2)} %</td></tr>
            <tr><td>R²</td><td className="mono">{m.R2?.toFixed(4)}</td></tr>
            <tr><td>{T("resid")} · ACF</td><td className="mono">{(100 * (m.frac_acf ?? 0)).toFixed(0)} %</td></tr>
            <tr><td>{T("resid")} · CCF (MV)</td><td className="mono">{(100 * (m.frac_ccf ?? 0)).toFixed(0)} %</td></tr>
            <tr><td>{T("col_status")}</td><td>{T("st_" + m.status)}</td></tr>
          </tbody></table>
        ) : <div className="muted small">…</div>}
        {model.crossval && (
          <div className="small" data-testid="crossval">{T("ms_cmp_cv")}: {Object.entries(model.crossval).map(([c, v]) =>
            `${c} ${v.map((x) => (x === null ? "–" : x.toFixed(0))).join(" / ")}`).join(" · ")}</div>
        )}
        <div className="row">
          {st.win_mode === "inputs" && <button className="btn" data-testid="crossval-run"
            onClick={() => void run("/model/crossval", undefined, T("cv_run"))}>{T("cv_run")}</button>}
        </div>
      </div>
      <div className="card" data-testid="uncertainty">
        <h3>{T("unc_title")}</h3>
        <div className="row">
          <label className="small">{T("unc_n")} <input className="num" type="number" min={3} max={100} value={n}
            onChange={(e) => setN(Math.max(3, Math.min(100, +e.target.value || 15)))} /></label>
          <button className="btn" data-testid="unc-run"
            onClick={() => void run("/model/uncertainty", { n }, T("unc_running"))}>{T("unc_run")}</button>
        </div>
        {unc && unc.code === code && unc.ps.length > 0 && (
          <table className="tbl" data-testid="unc-table"><thead><tr><th /><th>{T("unc_nominal")}</th><th>{T("unc_p05")}</th>
            <th>{T("unc_p95")}</th></tr></thead><tbody>
            {r.names.map((nm, i) => {
              const col = unc.ps.map((p) => p[i]);
              return <tr key={nm}><td>{nm}</td><td className="mono">{cur.p[i].toPrecision(4)}</td>
                <td className="mono">{q(col, 0.05).toPrecision(4)}</td><td className="mono">{q(col, 0.95).toPrecision(4)}</td></tr>;
            })}
          </tbody></table>
        )}
      </div>
      <ModelResiduals model={model} />
      {model.warnings.length > 0 && (
        <div className="card">{model.warnings.map(([k, c]) => <div key={k + c} className="warn small">⚠ {T(k, { m: T("model_" + c) })}</div>)}</div>
      )}
    </div>
  );
}
