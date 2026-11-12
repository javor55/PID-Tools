// Záložka Model (M14): graf s úseky pro identifikaci (sdílený trend.js), tabulka modelů a výběr modelu;
// panel: data pro identifikaci (MAN / AUTO), režim úseků MV, modely a nastavení identifikace, Identifikovat.
import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { binary, request } from "../api/client";
import type { components } from "../api/schema";
import { unframe, series } from "../api/signals";
import { Trend } from "../components/Trend";
import { Help } from "../components/Ui";
import { DistCompare, ModelDetails } from "./ModelDetails";
import { DIST_STYLE, MV_STYLE, windowFits } from "./modelConst";
import { ModelViews, ValidationCard } from "./ModelValidation";
import "../styles/model.css";
import { usePatchSettings, useSettings, useWs, useWsQuery } from "../data";
import { useT } from "../i18n";
import { dur } from "../lib/format";
import { decimate, pick, range, runs, timeUnit } from "../lib/series";
import { useUi } from "../store";
import { useQueryClient } from "@tanstack/react-query";

type ModelState = components["schemas"]["ModelState"];
type WindowsInfo = components["schemas"]["WindowsInfo"];

const TXT = ["mode", "h_mode", "common", "inputs", "zoom", "zoom_all", "zoom_win", "zoom_note", "excluded", "m_all",
  "m_mv", "m_dv", "resid", "r_win", "r_full", "model", "win", "drag_win", "start", "end", "zoom_one", "del", "add", "time"];
function useModelData() {
  const wid = useUi((s) => s.wid);
  const ws = useWs().data;
  const settings = useSettings().data ?? {};
  const grid = useQuery({
    queryKey: ["ws", wid, "grid", ws?.pv, ws?.mv, ws?.sp, ws?.dists, ws?.n],
    enabled: !!wid && !!ws?.has_data, staleTime: Infinity,
    queryFn: async () => unframe(await binary(`/workspaces/${wid}/signals?source=grid`)),
  });
  const windows = useWsQuery<WindowsInfo>("windows", "/windows");
  const model = useWsQuery<ModelState>("model", "/model");
  const hasModel = !!model.data?.current && !model.data?.stale;
  const curves = useQuery({
    queryKey: ["ws", wid, "curves", model.data?.current, model.data?.selected],
    enabled: !!wid && hasModel,
    queryFn: async () => unframe(await binary(`/workspaces/${wid}/model/curves`)),
  });
  return { ws, settings, grid: grid.data, windows: windows.data, model: model.data, curves: curves.data };
}

export function ModelMain() {
  const T = useT();
  const wid = useUi((s) => s.wid);
  const lang = useUi((s) => s.lang);
  const qc = useQueryClient();
  const patch = usePatchSettings();
  const { ws, settings, grid, windows, model, curves } = useModelData();
  const winMode = settings.win_mode === "inputs" ? "inputs" : "common";

  const data = useMemo(() => {
    if (!ws?.has_data || !grid) return null;
    const { meta, blob } = grid;
    const get = (n: string) => series(meta, blob, n);
    const pv = get("pv"), mv = get("mv");
    if (!pv || !mv) return null;
    const t = pv.t, n = t.length;
    const idx = decimate(n, pv.v);
    const [lo, hi] = range(pv.v);
    const pvRow: Record<string, unknown> = { id: "PV", kind: "pv", title: `PV · ${ws.pv}`, color: "#1f5fa8",
      y: pick(pv.v, idx), lo, hi, h: 220 };
    if (curves) {
      const c = (k: string) => series(curves.meta, curves.blob, k)?.v;
      pvRow.model = { all: pick(c("model"), idx), mv: pick(c("model_mv"), idx), dv: pick(c("model_dv"), idx),
        full_all: pick(c("full"), idx) };
      pvRow.resid = pick(c("residual"), idx);
    }
    const rows = [pvRow];
    const sel = model?.results.find((x) => x.code === model.selected);
    const wf = winMode === "inputs" && sel?.method === "win" && windows && curves
      ? windowFits(windows.wins, sel.window_fits, ws.Ts ?? 1) : {};
    const legend: unknown[] = [];
    const inputs: [string, ArrayLike<number>, string, string[]][] = [["MV", mv.v, ws.mv ?? "MV", MV_STYLE]];
    (ws.dists ?? []).forEach((d, j) => { const s = get(`d${j}`); if (s) inputs.push([d, s.v, d, DIST_STYLE[j % 4]]); });
    inputs.forEach(([rid, y, name, sty], k) => {
      const w = windows?.wins?.[rid] ?? [];
      const [l, h] = range(y);
      rows.push({ id: rid, kind: "in", title: `${rid === "MV" ? "MV" : T("mw_dist")} · ${name}`,
        color: rid === "MV" ? "#c2410c" : sty[0], y: pick(y, idx), lo: l, hi: h, h: 110, wins: w, fits: wf[rid] ?? [],
        wcol: sty[0], wtx: sty[1], wbg: sty[2], wbd: sty[3],
        badge: winMode === "inputs" ? T("mw_badge", { k: k + 1, n: w.length }) : null,
        note: winMode === "inputs" ? T("mw_note_in") : null });
      legend.push([sty[1], rid, sty[2]]);
    });
    const valid = get("valid");
    const excl = winMode === "inputs" && valid ? runs(Array.from(valid.v, (x) => (x > 0.5 ? 0 : 1)), t) : [];
    const T_end = t[n - 1];
    const clock = ws.origin ? Date.parse(ws.origin.replace(" ", "T") + "Z") + meta.tmin * 1000 : null;
    return {
      key: "model_wins", view_key: `model|${ws.fname}|${n}`, T: T_end, unit: timeUnit(T_end),
      clock: Number.isFinite(clock) ? clock : null, dec: lang === "cs" ? "," : ".",
      dark: document.documentElement.dataset.theme === "dark",
      txt: Object.fromEntries(TXT.map((k) => [k, T("mw_" + k)])), mode: winMode, t: pick(t, idx), step: ws.Ts,
      rows, excl, common: ws.rng ?? [0, T_end],
      bar: { mode_switch: true, zoom: true, legend: winMode === "inputs" ? legend : [] },
    };
  }, [ws, grid, windows, curves, model, winMode, T, lang]);

  const onWins = async (w: { mode: string; wins: Record<string, [number, number][]>; common: [number, number] }) => {
    if (w.mode === "inputs") await request("PUT", `/workspaces/${wid}/windows`, { wins: w.wins });
    else if (w.common) await request("PUT", `/workspaces/${wid}/range`, { a: w.common[0], b: w.common[1] });
    await qc.invalidateQueries({ queryKey: ["ws", wid] });
  };

  if (!ws?.has_data) return <div className="card muted">{T("ui_no_data")}</div>;
  return (
    <div className="stack">
      {data && <Trend data={data} onWins={(w) => void onWins(w)} onMode={(m) => void patch({ win_mode: m })}
        testid="model-trend" />}
      <ModelTable model={model} />
      {model?.has_fit && <ValidationCard model={model} />}
      {model?.has_fit && <ModelViews model={model} />}
      {model?.has_fit && <ModelDetails model={model} />}
    </div>
  );
}

function ModelTable({ model }: { model?: ModelState }) {
  const T = useT();
  const dec = useUi((s) => s.lang) === "cs" ? "," : ".";
  const wid = useUi((s) => s.wid);
  const qc = useQueryClient();
  const sel = model?.results.find((r) => r.code === model.selected);
  const anyCl = !!model?.results.some((r) => r.method === "cl" || r.mixed);
  if (!model?.has_fit) return <div className="card muted" data-testid="no-model">{T("info_fit")}</div>;
  const select = async (code: string) => {
    qc.setQueriesData<ModelState>({ queryKey: ["ws", wid, "model"] }, (old) => (old ? { ...old, selected: code } : old));
    await request("PUT", `/workspaces/${wid}/model/select`, { code });
    await qc.invalidateQueries({ queryKey: ["ws", wid] });
  };
  return (
    <div className="card mcmp" data-testid="model-cmp">
      <h3>{T("ms_cmp")} <Help text={T("h_ms_cmp")} /></h3>
      {model.stale && <div className="warn small" data-testid="stale">{T("warn_stale")}</div>}
      <div className="mcmp-head" style={{ "--mc": MV_STYLE[0] } as React.CSSProperties}>
        {T("ms_cmp_tab", { k: 1, n: "MV" })}</div>
      <table className="tbl" data-testid="models">
        <thead><tr><th /><th>{T("col_model")}</th><th>FIT [%]</th><th>NRMSE [%]</th><th>{T("col_status")}</th>
          {anyCl && <th title={T("idm_table_note")}>{T("idm_fit_cl")}</th>}<th>{T("dk_params")}</th></tr></thead>
        <tbody>
          {model.results.map((r) => (
            <tr key={r.code} className={r.code === model.selected ? "sel" : ""}>
              <td><input type="radio" name="mcode" checked={r.code === model.selected} onChange={() => void select(r.code)}
                aria-label={r.code} title={T("ms_cmp_pick")} /></td>
              <td>{T("model_" + r.code)}{r.mixed ? " · AUTO" : ""}</td>
              <td className="mono">{r.fit_live?.toFixed(1) ?? "–"}</td>
              <td className="mono">{r.nrmse?.toFixed(2) ?? "–"}</td>
              <td>{r.status !== null && r.status !== undefined ? T("st_" + r.status) : "–"}</td>
              {anyCl && <td className="mono" data-testid={`fit-cl-${r.code}`}>{r.fit_cl_pv == null ? "—" :
                `PV ${r.fit_cl_pv.toFixed(1)} / MV ${(r.fit_cl_mv ?? NaN).toFixed(1)}`}</td>}
              <td className="mono small">{r.p.map((x) => x.toPrecision(4)).join(", ")}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="small muted">{T("ms_cmp_pick")}</div>
      {sel && sel.dists.some((d) => d.cmp.length > 0) && (
        <div data-testid="dist-cmp">
          {sel.dists.map((d, j) => d.cmp.length > 0 && (
            <div key={j} className="mcmp-sec">
              <div className="mcmp-head" style={{ "--mc": DIST_STYLE[j % 4][0] } as React.CSSProperties}>
                {T("ms_cmp_tab", { k: j + 2, n: d.name })}</div>
              <DistCompare code={sel.code} j={j} d={d} />
            </div>))}
          <div className="muted small">{T("ms_cmp_dv_note")}</div>
        </div>
      )}
      {anyCl && <div className="muted small">{T("idm_table_note")}</div>}
      {model.results.filter((r) => r.p_open && r.method === "cl").map((r) => (
        <div key={r.code} className="small" data-testid={`open-model-${r.code}`}>
          {T("idm_open_model", { p: `${T("model_" + r.code)}: ${r.p_open!.map((x) => x.toPrecision(4)).join(", ")}` })}</div>))}
      {model.results.filter((r) => r.mixed && r.fit_cl_pv != null && r.fit_cl_pv < 50).map((r) => (
        <div key={r.code} className="warn small" data-testid="mix-set1-bad">{T("mix_set1_bad", { m: T("model_" + r.code),
          f: (r.fit_cl_pv ?? 0).toFixed(0) })}</div>))}
      {model.results.flatMap((r) => r.checks.map((c) => (
        <div key={r.code + c.key} className="warn small" data-testid="model-check">⚠ {T(c.key, {
          ...c.args, m: T("model_" + r.code), th: dur(Number(c.args.th), dec), T: dur(Number(c.args.T), dec) })}</div>)))}
    </div>
  );
}

export { ModelSide } from "./ModelSide";
