// Záložka Model (M14): graf s úseky pro identifikaci (sdílený trend.js), tabulka modelů a výběr modelu;
// panel: data pro identifikaci (MAN / AUTO), režim úseků MV, modely a nastavení identifikace, Identifikovat.
import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { binary, request } from "../api/client";
import type { components } from "../api/schema";
import { unframe, series } from "../api/signals";
import { Trend } from "../components/Trend";
import { type LoopMode, useSettings, useWs, useWsQuery } from "../data";
import { useT } from "../i18n";
import { useJobRunner } from "../jobs";
import { dur } from "../lib/format";
import { decimate, pick, range, runs, timeUnit } from "../lib/series";
import { useUi } from "../store";
import { useQueryClient } from "@tanstack/react-query";

type ModelState = components["schemas"]["ModelState"];
type WindowsInfo = components["schemas"]["WindowsInfo"];

export const MODELS = ["P0D", "P1D", "P2D", "I0D", "I1D"] as const;
const TXT = ["mode", "h_mode", "common", "inputs", "zoom", "zoom_all", "zoom_win", "zoom_note", "excluded", "m_all",
  "m_mv", "m_dv", "resid", "r_win", "r_full", "model", "win", "drag_win", "start", "end", "zoom_one", "del", "add", "time"];
const DIST_STYLE = [["#0d9488", "#0b7a70", "#e3f5f2", "#8fd3ca"], ["#7c3aed", "#5b21b6", "#f3effc", "#c9b8f0"],
  ["#db2777", "#9d174d", "#fdf0f6", "#f5b8d3"], ["#0891b2", "#0e7490", "#e6f6fa", "#9fdcec"]];
const MV_STYLE = ["#f59e0b", "#c77d00", "#fff4dc", "#f2c46d"];

function usePatchSettings() {
  const wid = useUi((s) => s.wid);
  const qc = useQueryClient();
  return async (patch: Record<string, unknown>) => {
    // hned v rozhraní (zaškrtávátka, výběry), pak s API
    qc.setQueryData<Record<string, unknown>>(["ws", wid, "settings"], (old) => ({ ...(old ?? {}), ...patch }));
    await request("PATCH", `/workspaces/${wid}/settings`, patch);
    await qc.invalidateQueries({ queryKey: ["ws", wid] });
  };
}

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
    const legend: unknown[] = [];
    const inputs: [string, ArrayLike<number>, string, string[]][] = [["MV", mv.v, ws.mv ?? "MV", MV_STYLE]];
    (ws.dists ?? []).forEach((d, j) => { const s = get(`d${j}`); if (s) inputs.push([d, s.v, d, DIST_STYLE[j % 4]]); });
    inputs.forEach(([rid, y, name, sty], k) => {
      const w = windows?.wins?.[rid] ?? [];
      const [l, h] = range(y);
      rows.push({ id: rid, kind: "in", title: `${rid === "MV" ? "MV" : T("mw_dist")} · ${name}`,
        color: rid === "MV" ? "#c2410c" : sty[0], y: pick(y, idx), lo: l, hi: h, h: 110, wins: w, fits: [],
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
  }, [ws, grid, windows, curves, winMode, T, lang]);

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
    </div>
  );
}

function ModelTable({ model }: { model?: ModelState }) {
  const T = useT();
  const dec = useUi((s) => s.lang) === "cs" ? "," : ".";
  const wid = useUi((s) => s.wid);
  const qc = useQueryClient();
  if (!model?.has_fit) return <div className="card muted" data-testid="no-model">{T("info_fit")}</div>;
  const select = async (code: string) => {
    qc.setQueriesData<ModelState>({ queryKey: ["ws", wid, "model"] }, (old) => (old ? { ...old, selected: code } : old));
    await request("PUT", `/workspaces/${wid}/model/select`, { code });
    await qc.invalidateQueries({ queryKey: ["ws", wid] });
  };
  return (
    <div className="card">
      {model.stale && <div className="warn small" data-testid="stale">{T("warn_stale")}</div>}
      <table className="tbl" data-testid="models">
        <thead><tr><th /><th>{T("col_model")}</th><th>FIT [%]</th><th>NRMSE [%]</th><th>{T("col_status")}</th>
          <th>{T("dk_params")}</th></tr></thead>
        <tbody>
          {model.results.map((r) => (
            <tr key={r.code} className={r.code === model.selected ? "sel" : ""}>
              <td><input type="radio" name="mcode" checked={r.code === model.selected} onChange={() => void select(r.code)}
                aria-label={r.code} /></td>
              <td>{T("model_" + r.code)}{r.mixed ? " · AUTO" : ""}</td>
              <td className="mono">{r.fit_live?.toFixed(1) ?? "–"}</td>
              <td className="mono">{r.nrmse?.toFixed(2) ?? "–"}</td>
              <td>{r.status !== null && r.status !== undefined ? T("st_" + r.status) : "–"}</td>
              <td className="mono small">{r.p.map((x) => x.toPrecision(4)).join(", ")}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {model.results.flatMap((r) => r.checks.map((c) => (
        <div key={r.code + c.key} className="warn small" data-testid="model-check">⚠ {T(c.key, {
          ...c.args, m: T("model_" + r.code), th: dur(Number(c.args.th), dec), T: dur(Number(c.args.T), dec) })}</div>)))}
    </div>
  );
}

function Num({ label, value, onCommit, step, testid }: { label: string; value: number | undefined;
  onCommit: (v: number) => void; step?: number; testid?: string }) {
  const [v, setV] = useState<string | null>(null);
  return (
    <label className="field">
      <span>{label}</span>
      <input type="number" step={step ?? "any"} value={v ?? (value ?? "")} data-testid={testid}
        onChange={(e) => setV(e.target.value)}
        onBlur={() => { if (v !== null && v !== "" && Number.isFinite(+v)) onCommit(+v); setV(null); }}
        onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }} />
    </label>
  );
}

export function ModelSide() {
  const T = useT();
  const wid = useUi((s) => s.wid);
  const qc = useQueryClient();
  const patch = usePatchSettings();
  const run = useJobRunner();
  const ws = useWs().data;
  const st = useSettings().data ?? {};
  const lm = useWsQuery<LoopMode>("loopmode", "/loopmode");
  const windows = useWsQuery<WindowsInfo>("windows", "/windows");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  if (!ws?.has_data) return null;
  const chosen = (st.chosen as string[] | undefined) ?? [...MODELS];
  const idMode = (st.id_mode as string) ?? "auto";
  const level = (st.dist_level as string) ?? "none";
  const mvWins = windows.data?.wins?.MV ?? [];

  const identify = async () => {
    setBusy(true); setErr(null);
    const j = await run("/identify", undefined, T("ms_identif"));
    if (j.state !== "done") setErr(j.error ?? j.state);
    setBusy(false);
  };
  const setMode = async (index: number, mode: string) => {
    await request("PUT", `/workspaces/${wid}/windows/mode`, { index, mode });
    await qc.invalidateQueries({ queryKey: ["ws", wid] });
  };
  return (
    <div className="stack">
      <section>
        <label className="field"><span>{T("idm")}</span>
          <select value={idMode} onChange={(e) => void patch({ id_mode: e.target.value })} data-testid="id-mode">
            {["auto", "open", "cl"].map((m) => <option key={m} value={m}>{T("idm_" + m)}</option>)}
          </select>
        </label>
        {lm.data && <div className="small muted" data-testid="lm-status">
          {T("lm_status", { a: Math.round(100 * lm.data.auto_frac), m: 100 - Math.round(100 * lm.data.auto_frac) })}
          {idMode === "auto" && st.win_mode !== "inputs" ? " " + T("lm_resolved", { m: T("idm_" + lm.data.effective) }) : ""}
        </div>}
        {lm.data && !lm.data.set1_ok && lm.data.auto_frac >= 0.15 && idMode !== "open" &&
          <div className="warn small">{T("lm_need_set1")}</div>}
        {st.win_mode === "inputs" && ws.sp && mvWins.length > 0 && (
          <div data-testid="mv-modes">
            <div className="small muted">{T("mix_title")}</div>
            {mvWins.map((w, i) => (
              <label className="field" key={i}><span>MV {i + 1}</span>
                <select value={windows.data?.mv_modes?.[i] ?? "man"} disabled={idMode !== "auto"}
                  onChange={(e) => void setMode(i, e.target.value)} data-testid={`mv-mode-${i}`}>
                  <option value="man">{T("mix_man")}</option><option value="auto">{T("mix_auto")}</option>
                </select>
                <span className="small mono">{Math.round(w[0])}–{Math.round(w[1])} s</span>
              </label>
            ))}
          </div>
        )}
      </section>
      <section>
        <h3>{T("models")}</h3>
        <div className="checks-grid">
          {MODELS.map((c) => (
            <label key={c} className="small">
              <input type="checkbox" checked={chosen.includes(c)} data-testid={`chk-${c}`}
                onChange={(e) => void patch({ chosen: e.target.checked ? [...chosen, c] : chosen.filter((x) => x !== c) })} />
              {" "}{T("model_" + c)}
            </label>
          ))}
        </div>
        <Num label={T("thmax")} value={st.thmax as number | undefined} onCommit={(v) => void patch({ thmax: v })}
          testid="thmax" />
        <label className="field"><span>{T("dist_level")}</span>
          <select value={level} onChange={(e) => void patch({ dist_level: e.target.value })}>
            {["none", "medium", "high"].map((x) => <option key={x} value={x}>{T("dl_" + x)}</option>)}
          </select>
        </label>
        <label className="field"><span>{T("dist_strength")}</span>
          <input type="range" min={1} max={10} disabled={level === "none"} value={Number(st.dist_strength ?? 4)}
            onChange={(e) => void patch({ dist_strength: +e.target.value })} />
        </label>
        <label className="field"><span>{T("gain_sign")}</span>
          <select value={(st.gain_sign as string) ?? "auto"} onChange={(e) => void patch({ gain_sign: e.target.value })}>
            {["auto", "pos", "neg"].map((x) => <option key={x} value={x}>{T("gsg_" + x)}</option>)}
          </select>
        </label>
        <label className="small"><input type="checkbox" checked={!!st.id_stic}
          onChange={(e) => void patch({ id_stic: e.target.checked })} /> {T("id_stic")}</label>
      </section>
      <button className="btn primary" disabled={busy || chosen.length === 0} onClick={() => void identify()}
        data-testid="identify">{T("run_fit")}</button>
      {err && <div className="err small" role="alert">{err}</div>}
    </div>
  );
}
