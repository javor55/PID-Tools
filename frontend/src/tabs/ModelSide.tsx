// Panel záložky Model podle návrhu: hlavní tlačítko Identifikovat model, data pro identifikaci, Struktura modelu,
// karta každého přenosu (typ, parametry s „Identif.“, směr účinku, původní hodnoty, FIT), další nastavení
// (modely, neměřené poruchy, stikce), vyřazení dat a ověření modelu. Každý blok je SideCard.
import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { binary, request } from "../api/client";
import type { components } from "../api/schema";
import { series, unframe } from "../api/signals";
import { paramLabel, SetInput } from "../components/SetInput";
import { Help, PrimaryAction, SideCard, Seg } from "../components/Ui";
import { type LoopMode, usePatchSettings, useSettings, useWs, useWsQuery } from "../data";
import { useDec, useT } from "../i18n";
import { dur } from "../lib/format";
import { useJobRunner } from "../jobs";
import { useQueryClient } from "@tanstack/react-query";
import { useUi } from "../store";
import "../styles/model.css";
import { DIST_CHOICES, DIST_STYLE, FAMILY, MODELS, MV_STYLE, mean, windowFits } from "./modelConst";

type ModelState = components["schemas"]["ModelState"];
type ModelRes = components["schemas"]["ModelRes"];
type WindowsInfo = components["schemas"]["WindowsInfo"];
type LoopInfo = components["schemas"]["LoopInfo"];
type Set1Check = components["schemas"]["Set1Check"];
type Set1Estimate = components["schemas"]["Set1Estimate"];
type RecordSet = components["schemas"]["RecordSet"];

/** Číselné pole (potvrzení Enterem / opuštěním pole) s popiskem vlevo. */
function Num({ label, value, onCommit, step, testid, help }: { label: string; value: number | undefined;
  onCommit: (v: number) => void; step?: number; testid?: string; help?: string }) {
  const [v, setV] = useState<string | null>(null);
  return (
    <label className="field">
      <span>{label}{help && <> <Help text={help} /></>}</span>
      <input type="number" step={step ?? "any"} value={v ?? (value ?? "")} data-testid={testid}
        onChange={(e) => setV(e.target.value)}
        onBlur={() => { if (v !== null && v !== "" && Number.isFinite(+v)) onCommit(+v); setV(null); }}
        onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }} />
    </label>
  );
}

/** Řádek parametru karty přenosu: název | hodnota | jednotka | Identif. (zaškrtnuto = odhaduje se z dat). */
function ParamRow({ label, edKey, fxKey, value, unit, help, signed }: { label: string; edKey: string; fxKey: string;
  value: number; unit: string; help: string; signed: boolean }) {
  const T = useT();
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
    <>
      <label className="mp-name" title={help}>{label}</label>
      <input className="num" type="number" step="any" min={signed ? undefined : 0} value={v ?? +cur.toPrecision(6)}
        data-testid={`ed-${edKey}`} aria-label={label} title={help}
        onChange={(e) => setV(e.target.value)}
        onBlur={() => { if (v !== null && v !== "" && Number.isFinite(+v)) void patch({ [edKey]: +v }); setV(null); }}
        onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }} />
      <span className="mp-unit">{unit}</span>
      <input type="checkbox" checked={!st[fxKey]} aria-label={`Identif. ${label}`} title={T("h_ms_identif")} data-testid={`fx-${fxKey}`}
        onChange={(e) => void patch({ [fxKey]: !e.target.checked })} />
    </>
  );
}

const unitOf = (T: (k: string) => string, n: string) => n === "K" ? "%/%" : n === "Ki" ? "%/(%·s)" : n === "Kd" ? T("ms_unit_kd") : "s";

interface CardProps {
  k: number;                     // pořadí přenosu (1 = MV)
  name: string;                  // MV / název poruchy
  col: string;                   // sloupec v datech
  j: number;                     // index poruchy (−1 = MV)
  model?: ModelState;
  r?: ModelRes;
  win: boolean;
  fit: number | null;
  src: string;
  color: string;
  modelFits: Record<string, number>;
}

function TransferCard({ k, name, col, j, model, r, win, fit, src, color, modelFits }: CardProps) {
  const T = useT();
  const wid = useUi((s) => s.wid);
  const qc = useQueryClient();
  const run = useJobRunner();
  const patch = usePatchSettings();
  const st = useSettings().data ?? {};
  const isMv = j < 0;
  const title = col !== name ? T("ms_card", { k, n: name, c: col }) : T("ms_card1", { k, n: name });
  const cur = model?.current as { code: string; p: number[]; pdl: number[][] } | null | undefined;
  const has = !!(model?.has_fit && r && cur);
  const procType = (st.proc_type as string) ?? "auto";
  const best = model?.results.reduce<string | null>((b, x) => (b === null || (modelFits[x.code] ?? -1e9) > (modelFits[b] ?? -1e9) ? x.code : b), null) ?? null;
  const famBest = model?.results.filter((x) => (FAMILY[procType] ?? MODELS).includes(x.code))
    .reduce<string | null>((b, x) => (b === null || (modelFits[x.code] ?? -1e9) > (modelFits[b] ?? -1e9) ? x.code : b), null) ?? best;
  const mn = (c: string | null) => (c ? T("model_" + c) : "");

  const select = async (code: string, mtype: string) => {
    await patch({ mtype });
    if (code && code !== model?.selected) await request("PUT", `/workspaces/${wid}/model/select`, { code });
    await qc.invalidateQueries({ queryKey: ["ws", wid] });
  };
  const setDist = async (struct: string) => {
    await request("PUT", `/workspaces/${wid}/model/dist`, { code: r!.code, index: j, struct });
    await qc.invalidateQueries({ queryKey: ["ws", wid] });
  };
  const reset = async () => {
    await request("POST", `/workspaces/${wid}/model/reset`, { code: r!.code });
    await qc.invalidateQueries({ queryKey: ["ws", wid] });
  };

  // ---- typ přenosu
  let typeSel: React.ReactNode;
  if (isMv && has && model) {
    const opts = ["pv", "auto", ...model.results.map((x) => x.code)];
    const resolve = (o: string) => (o === "pv" ? famBest : o === "auto" ? best : o);
    const stored = String(st.mtype ?? "");
    const val = opts.includes(stored) && resolve(stored) === model.selected ? stored : (model.selected ?? "pv");
    typeSel = (
      <select value={val} data-testid="mtype" aria-label={T("ms_type")}
        onChange={(e) => void select(resolve(e.target.value) ?? "", e.target.value)}>
        {opts.map((o) => <option key={o} value={o}>
          {o === "pv" ? T("ms_type_pv", { m: mn(famBest) }) : o === "auto" ? T("ms_type_auto", { m: mn(best) })
            : `${mn(o)} · FIT ${(modelFits[o] ?? NaN).toFixed(1)} %`}</option>)}
      </select>);
  } else if (isMv) {
    const kinds = ["pv", "auto", "self", "integ"];
    const v = kinds.includes(String(st.mtype0)) ? String(st.mtype0) : "pv";
    typeSel = (
      <select value={v} data-testid="mtype0" aria-label={T("ms_type")}
        onChange={(e) => { const x = e.target.value;
          void patch({ mtype0: x, chosen: [...(FAMILY[x === "pv" ? procType : x === "auto" ? "auto" : x] ?? MODELS)] }); }}>
        {kinds.map((o) => <option key={o} value={o}>
          {o === "pv" ? T("ms_type_pv", { m: T("ms_proc_" + procType) }) : T("dkind_" + o)}</option>)}
      </select>);
  } else if (has && r) {
    const d = r.dists[j];
    const fitOf = new Map(d?.cmp.filter((c) => c.fit != null).map((c) => [c.struct, c.fit as number]));
    const ids = [...fitOf.keys()];
    if (d && !ids.includes(d.struct)) ids.unshift(d.struct);
    typeSel = d && (
      <select value={d.struct} data-testid={`dsel-${j}`} aria-label={T("ms_type")} onChange={(e) => void setDist(e.target.value)}>
        {ids.map((c) => <option key={c} value={c}>{mn(c)}{fitOf.has(c) ? ` · FIT ${fitOf.get(c)!.toFixed(1)} %` : ""}
          {c === d.ident ? ` · ${T("ms_dist_ident")}` : ""}</option>)}
      </select>);
  } else {
    const key = `dkind|${col}`;
    const v = DIST_CHOICES.includes(String(st[key]) as never) ? String(st[key]) : "pv";
    typeSel = (
      <select value={v} data-testid={`dkind-${j}`} aria-label={T("ms_type")} onChange={(e) => void patch({ [key]: e.target.value })}>
        {DIST_CHOICES.map((o) => <option key={o} value={o}>{o === "pv" || o === "auto" ? T("dkind_" + o) : mn(o)}</option>)}
      </select>);
  }

  // ---- směr účinku (MV: gain_sign; porucha: dsign|název, jen v režimu Podle vstupů)
  const signKey = isMv ? "gain_sign" : `dsign|${col}`;
  const sign = (st[signKey] as string) ?? "auto";
  const signLab = { neg: "−", auto: "auto", pos: "+" } as const;

  // ---- parametry
  const params: { label: string; edKey: string; fxKey: string; value: number; help: string; signed: boolean; unit?: string }[] = [];
  if (has && r && cur) {
    if (isMv) {
      r.names.forEach((nm, i) => params.push({ label: nm, edKey: `ed|${r.code}|${i}`, fxKey: `fx|${r.code}|${i}`,
        value: cur.p[i], signed: i === 0,
        help: T("help_" + (i === 0 ? "gain" : i === r.names.length - 1 ? "theta" : "T")) }));
      if (st.id_stic || r.stic) params.push({ label: T("stic_param", { u: "" }), edKey: `ed|${r.code}|stic`,
        fxKey: `fx|${r.code}|stic`, value: r.stic, signed: false, unit: "% MV", help: T("h_stic_param") });
    } else r.dists[j]?.fields.forEach(([fname, idx]) => params.push({ label: String(fname), edKey: `ed|${r.code}|d${j}|${idx}`,
      fxKey: `fx|${r.code}|d${j}|${idx}`, value: Number(st[`ed|${r.code}|d${j}|${idx}`] ?? 0), signed: Number(idx) === 0,
      help: T("h_dist_" + String(Number(idx) === 3 ? 1 : idx)) }));
  }
  const first = isMv;
  const suffix = first ? "" : `-d${j}`;
  return (
    <div className={"mcard " + (isMv ? "mcard-mv" : "mcard-dv")} style={{ "--mc": color } as React.CSSProperties}>
      <SideCard testid={isMv ? "params" : `params-d${j}`} title={title}
        aside={fit !== null ? <span className="mfit mono" data-testid={`fit-${j}`}>FIT {fit.toFixed(0)} %</span> : null}>
        <div className="msrc">{src}</div>
        {r?.dists[j]?.flat && <div className="warn small">{T("ms_dv_flat")}</div>}
        <div className="mrow">
          <label>{T("ms_type")}</label><Help text={T(isMv ? (has ? "h_ms_type" : "h_ms_type0") : "h_dkind")} />
          {typeSel}
        </div>
        {params.length > 0 && (
          <div className="mparams" data-testid={`mparams${suffix}`}>
            <span /><span /><span />
            <span className="mp-head">{T("ms_identif")} <Help text={T("h_ms_identif")} /></span>
            {params.map((p) => <ParamRow key={p.edKey} {...p} unit={p.unit ?? unitOf(T, p.label)} />)}
          </div>
        )}
        <div className="mrow">
          <label>{T("ms_sign")}</label><Help text={T(isMv ? "h_ms_sign" : "h_dsign")} />
          <div className={isMv || win ? "" : "dis"} title={isMv || win ? undefined : T("ms_dist_common")}>
            <Seg value={sign} options={["neg", "auto", "pos"] as const} small label={T("ms_sign")}
              fmt={(v) => signLab[v as keyof typeof signLab]} testid={`sign-${j}`}
              onChange={(v) => { if (isMv || win) void patch({ [signKey]: v }); }} />
          </div>
        </div>
        {has && r && (
          <div className="mbtns">
            <button className="btn" data-testid={first ? "refit" : `refit${suffix}`} title={T("h_refit")}
              onClick={() => void run("/model/refit", { code: r.code }, T("refit"))}>{T("refit")}</button>
            <button className="btn" data-testid={first ? "reset" : `reset${suffix}`} title={T("h_ms_reset")}
              onClick={() => void reset()}>{T("ms_reset")}</button>
          </div>
        )}
      </SideCard>
    </div>
  );
}

/** Vyřazení dat: meze PV / MV / poruch a tolerance (PUT /windows – úseky se posílají beze změny). */
function Exclusion({ info }: { info: WindowsInfo }) {
  const T = useT();
  const wid = useUi((s) => s.wid);
  const qc = useQueryClient();
  const rows = info.excl as [string, boolean, number, number, number][];
  const save = async (next: Record<string, [boolean, number, number]>, tol?: number) => {
    await request("PUT", `/workspaces/${wid}/windows`, { wins: info.wins, excl: next, tol: tol ?? info.tol });
    await qc.invalidateQueries({ queryKey: ["ws", wid] });
  };
  const all = () => Object.fromEntries(rows.map(([n, on, lo, hi]) => [n, [on, lo, hi] as [boolean, number, number]]));
  const set = (n: string, i: 0 | 1 | 2, v: boolean | number) => {
    const a = all(); const e = [...a[n]] as [boolean, number, number]; (e as (boolean | number)[])[i] = v; a[n] = e; void save(a);
  };
  return (
    <SideCard title={T("excl_title")} testid="side-excl" defaultOpen={false}>
      <div className="small muted">{T("excl_intro")}</div>
      <div className="mexcl">
        <span /><span className="mp-head">Min</span><span className="mp-head">Max</span><span className="mp-head">{T("excl_on")}</span>
        {rows.map(([n, on, lo, hi]) => (
          <ExclRow key={n + lo + hi} n={n} on={on} lo={lo} hi={hi} set={set} />
        ))}
      </div>
      <Num label={T("excl_tol")} help={T("h_excl_tol")} value={info.tol} step={0.1} testid="excl-tol"
        onCommit={(v) => void save(all(), v)} />
    </SideCard>
  );
}

function ExclRow({ n, on, lo, hi, set }: { n: string; on: boolean; lo: number; hi: number;
  set: (n: string, i: 0 | 1 | 2, v: boolean | number) => void }) {
  const T = useT();
  const [a, setA] = useState<string | null>(null);
  const [b, setB] = useState<string | null>(null);
  const commit = (v: string | null, i: 1 | 2) => { if (v !== null && v !== "" && Number.isFinite(+v)) set(n, i, +v); };
  return (
    <>
      <b className="mp-name">{n}</b>
      <input className="num" type="number" step="any" value={a ?? +lo.toPrecision(5)} aria-label={`${n} min`} title={T("excl_intro")}
        onChange={(e) => setA(e.target.value)} onBlur={() => { commit(a, 1); setA(null); }}
        onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }} />
      <input className="num" type="number" step="any" value={b ?? +hi.toPrecision(5)} aria-label={`${n} max`} title={T("excl_intro")}
        onChange={(e) => setB(e.target.value)} onBlur={() => { commit(b, 2); setB(null); }}
        onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }} />
      <input type="checkbox" checked={on} aria-label={`${n} ${on ? "on" : "off"}`} title={T("excl_intro")} onChange={(e) => set(n, 0, e.target.checked)} />
    </>
  );
}

/** Regulátor v záznamu = Sada 1 (sdílená s Laděním) v jednotkách bloku profilu smyčky; jde zadat i bez modelu,
 *  protože identifikace v uzavřené smyčce ho potřebuje dřív, než je model (a tím i záložka Ladění). */
function RecordSetBox({ onChange }: { onChange: () => Promise<void> }) {
  const T = useT();
  const wid = useUi((s) => s.wid);
  const rs = useWsQuery<RecordSet>("record-set", "/tuning/record-set");
  const [err, setErr] = useState<string | null>(null);
  const r = rs.data;
  if (!r) return null;
  const write = async (key: string, x: number) => {
    setErr(null);
    try {
      await request("PUT", `/workspaces/${wid}/tuning/record-set`, { values: { ...r.set.values, [key]: x } });
    } catch (e) { setErr(String((e as Error).message)); }
    await onChange();
  };
  return (
    <div className="rec-set" data-testid="record-set">
      <div className="rec-set-h"><b>{T("idm_rec_title")}</b><Help text={T("idm_rec_h")} /></div>
      <div className="small muted" data-testid="record-set-ctl">{r.controller.vendor ? `${r.controller.vendor} · ` : ""}{r.controller.name}</div>
      <div className="rec-set-grid">
        {r.tuning_params.map((q) => (
          <label key={q.key} className="field"><span>{paramLabel(q)}</span>
            <SetInput value={(r.set.values[q.key] as number | null) ?? 0} placeholder={r.set.placeholder}
              label={`${T("set_1")} ${q.name}`} testid={`rec-${q.key}`} onCommit={(x) => void write(q.key, x)} /></label>))}
      </div>
      {r.set.warnings.map((w) => <div key={w.key} className="warn small">⚠ {w.text}</div>)}
      {err && <div className="err small" role="alert">{err}</div>}
    </div>
  );
}

/** Smyčka v AUTO (M2): varování, zúžení na ruční úsek, Set 1 (zápis do nastavení, kontrola) a hlášení o buzení. */
function ClosedLoop({ lp, idMode, win, model }: { lp: LoopInfo; idMode: string; win: boolean; model?: ModelState }) {
  const T = useT();
  const wid = useUi((s) => s.wid);
  const qc = useQueryClient();
  const patch = usePatchSettings();
  const dec = useDec();
  const [msg, setMsg] = useState<{ warn: boolean; text: string } | null>(null);
  const eff = win ? "open" : lp.effective;
  const closed = eff === "cl" && lp.has_sp;
  const chk = useWsQuery<Set1Check>(`set1check|${model?.selected}|${JSON.stringify(lp.set1)}`, "/model/set1/check",
    closed && !!model?.has_fit);
  const refresh = () => qc.invalidateQueries({ queryKey: ["ws", wid] });
  const narrow = async () => { await request("POST", `/workspaces/${wid}/windows/narrow`); await refresh(); };
  const estimate = async () => {
    const e = await request<Set1Estimate>("POST", `/workspaces/${wid}/model/set1/estimate`);
    setMsg(e.ok ? { warn: false, text: T("idm_est_done", { g: (e.gain ?? 0).toPrecision(4), ti: e.ti == null ? "∞" : e.ti.toPrecision(4),
      r: e.r2.toFixed(2) }) } : { warn: true, text: T("idm_est_fail") });
    await refresh();
  };
  const c = chk.data;
  return (
    <div data-testid="closed-loop">
      {!win && eff === "open" && lp.auto_frac >= 0.15 && (
        <>
          <div className="warn small" data-testid="lm-warn">{T("lm_warn", { a: Math.round(100 * lp.auto_frac) })}</div>
          <div className="row">
            {lp.manual_span && <button type="button" className="btn" data-testid="lm-narrow" title={T("h_lm_narrow")}
              onClick={() => void narrow()}>{T("lm_narrow", { a: dur(lp.manual_span[0], dec), b: dur(lp.manual_span[1], dec) })}</button>}
            {lp.has_sp && <button type="button" className="btn" data-testid="lm-to-cl" title={T("idm")}
              onClick={() => void patch({ id_mode: "cl" })}>{T("lm_to_cl")}</button>}
          </div>
        </>
      )}
      {idMode === "cl" && !lp.has_sp && <div className="warn small">{T("idm_need_sp")}</div>}
      {closed && (
        <>
          <div className="small muted" data-testid="cl-note">{T("idm_cl_note2")}</div>
          {lp.low_excitation && <div className="warn small" data-testid="low-exc">{T("idm_low_exc")}</div>}
          {c?.available && (c.ok
            ? <div className="small" data-testid="set1-ok">✓ {T("idm_set1_ok", { f: (c.fit_pv ?? 0).toFixed(0) })}</div>
            : <div className="warn small" data-testid="set1-bad">{c.stable ? T("idm_set1_bad", { f: (c.fit_pv ?? 0).toFixed(0) }) : T("idm_set1_unstable")}</div>)}
        </>
      )}
      {lp.has_sp && (closed || lp.auto_frac >= 0.15) && <RecordSetBox onChange={refresh} />}
      {lp.has_sp && (closed || lp.auto_frac >= 0.15) && (
        <div className="row">
          <button type="button" className="btn" data-testid="set1-estimate" title={T("h_idm_est")}
            onClick={() => void estimate()}>{T("idm_est_btn")}</button><Help text={T("h_idm_est")} />
        </div>)}
      {msg && <div className={"small " + (msg.warn ? "warn" : "muted")} data-testid="set1-msg">{msg.text}</div>}
    </div>
  );
}

/** FIT [%] simulace s daným průběhem modelu vůči PV (jen vzorky, kde model existuje). */
function fitOf(pv: ArrayLike<number>, m: ArrayLike<number> | undefined): number | null {
  if (!m) return null;
  let n = 0, s = 0;
  for (let i = 0; i < pv.length; i++) if (Number.isFinite(m[i]) && Number.isFinite(pv[i])) { n++; s += pv[i]; }
  if (n < 3) return null;
  const mu = s / n;
  let num = 0, den = 0;
  for (let i = 0; i < pv.length; i++) if (Number.isFinite(m[i]) && Number.isFinite(pv[i])) {
    num += (pv[i] - m[i]) ** 2; den += (pv[i] - mu) ** 2;
  }
  return den > 0 ? 100 * (1 - Math.sqrt(num / den)) : null;
}

function Validation({ model }: { model?: ModelState }) {
  const T = useT();
  const wid = useUi((s) => s.wid);
  const setTab = useUi((s) => s.setTab);
  const ok = !!model?.current && !model.stale;
  const curves = useQuery({
    queryKey: ["ws", wid, "curves", model?.current, model?.selected], enabled: !!wid && ok,
    queryFn: async () => unframe(await binary(`/workspaces/${wid}/model/curves`)),
  });
  const f = useMemo(() => {
    const c = curves.data;
    const g = (k: string) => (c ? series(c.meta, c.blob, k)?.v : undefined);
    const pv = g("pv");
    if (!pv) return null;
    return [[T("ms_val_all"), fitOf(pv, g("model"))], [T("ms_val_mv"), fitOf(pv, g("model_mv"))],
      [T("ms_val_dv"), fitOf(pv, g("model_dv"))]] as [string, number | null][];
  }, [curves.data, T]);
  return (
    <SideCard title={T("ms_val")} help={T("ms_val_intro")} testid="side-validation">
      <div className="mval">
        {(f ?? [[T("ms_val_all"), null], [T("ms_val_mv"), null], [T("ms_val_dv"), null]] as [string, number | null][]).map(([l, v]) => (
          <div key={l} className="mval-row"><span>{l}</span><span className="mono">FIT {v === null ? "–" : v.toFixed(1) + " %"}</span></div>))}
      </div>
      <button type="button" className="btn" disabled={!ok} data-testid="use-model" onClick={() => setTab("tuning")}>{T("ms_use")}</button>
    </SideCard>
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
  const lp = useWsQuery<LoopInfo>("modelloop", "/model/loop");
  const windows = useWsQuery<WindowsInfo>("windows", "/windows");
  const model = useWsQuery<ModelState>("model", "/model").data;
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  if (!ws?.has_data) return null;
  const chosen = (st.chosen as string[] | undefined) ?? [...MODELS];
  const idMode = (st.id_mode as string) ?? "auto";
  const level = (st.dist_level as string) ?? "none";
  const win = st.win_mode === "inputs";
  const mvWins = windows.data?.wins?.MV ?? [];
  const dists = ws.dists ?? [];
  const procType = (st.proc_type as string) ?? "auto";

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

  // shoda přenosů: z úseků (Podle vstupů), jinak FIT modelu u MV
  const sel = model?.results.find((x) => x.code === model.selected);
  const modelFits: Record<string, number> = {};
  model?.results.forEach((x) => { const v = x.fit_live ?? x.fit; if (v != null) modelFits[x.code] = v; });
  const perInput = win && sel?.method === "win" && windows.data
    ? windowFits(windows.data.wins, sel.window_fits, ws.Ts ?? 1) : null;
  const fitOfInput = (name: string): number | null => (perInput ? mean(perInput[name] ?? []) : name === "MV" ? (sel ? (sel.fit_live ?? sel.fit ?? null) : null) : null);
  const srcOf = (name: string) => {
    const w = windows.data?.wins?.[name] ?? [];
    const s = (x: number) => `${Math.round(x)} s`;
    if (!win) return T("ms_src_common", { a: s((ws.rng ?? [0, 0])[0]), b: s((ws.rng ?? [0, 0])[1]) });
    if (w.length === 0) return T("ms_src_none");
    if (w.length === 1) return T("ms_src_one", { a: s(w[0][0]), b: s(w[0][1]) });
    return T("ms_src_many", { n: w.length });
  };
  const transfers = [{ name: "MV", col: ws.mv ?? "MV", j: -1 }, ...dists.map((d, j) => ({ name: d, col: d, j }))];

  return (
    <>
      <div className="side-primary">
        <PrimaryAction onClick={() => void identify()} disabled={busy || chosen.length === 0} testid="identify">
          {T("ui_model_run")}</PrimaryAction>
        <div className="small muted">{T("ms_fit_note")}</div>
        {err && <div className="err small" role="alert">{err}</div>}
      </div>

      <SideCard title={T("idm")} help={T("h_idm")} testid="side-idm">
        <select value={idMode} onChange={(e) => void patch({ id_mode: e.target.value })} data-testid="id-mode" aria-label={T("idm")} title={T("h_idm")}>
          {["auto", "open", "cl"].map((m) => <option key={m} value={m}>{T("idm_" + m)}</option>)}
        </select>
        {lm.data && <div className="small muted" data-testid="lm-status">
          {T("lm_status", { a: Math.round(100 * lm.data.auto_frac), m: 100 - Math.round(100 * lm.data.auto_frac) })}
          {idMode === "auto" && !win ? " " + T("lm_resolved", { m: T("idm_" + lm.data.effective) }) : ""}
        </div>}
        {lm.data && !lm.data.set1_ok && lm.data.auto_frac >= 0.15 && idMode !== "open" &&
          <div className="warn small">{T("lm_need_set1")}</div>}
        {lp.data && <ClosedLoop lp={lp.data} idMode={idMode} win={win} model={model} />}
        {win && ws.sp && mvWins.length > 0 && (
          <div data-testid="mv-modes">
            <div className="small muted">{T("mix_title")}</div>
            {mvWins.map((w, i) => (
              <label className="field" key={i}><span>MV {i + 1}</span>
                <select value={windows.data?.mv_modes?.[i] ?? "man"} disabled={idMode !== "auto"} title={T("h_mix")}
                  onChange={(e) => void setMode(i, e.target.value)} data-testid={`mv-mode-${i}`}>
                  <option value="man">{T("mix_man")}</option><option value="auto">{T("mix_auto")}</option>
                </select>
                <span className="small mono">{Math.round(w[0])}–{Math.round(w[1])} s</span>
              </label>
            ))}
          </div>
        )}
      </SideCard>

      <SideCard title={T("ms_struct")} testid="side-struct">
        <p className="mformula">PV = G₁(s)·MV{dists.map((d, j) => ` + G${"₂₃₄₅₆₇₈₉"[j]}(s)·${d}`).join("")}</p>
        <div className="mlabel"><span>{T("ms_proc")}</span><Help text={T("h_ms_proc")} /></div>
        <Seg value={procType} options={["auto", "self", "integ"] as const} label={T("ms_proc")} stretch testid="proc-type"
          fmt={(v) => T("ms_proc_" + v)}
          onChange={(v) => void patch({ proc_type: v, chosen: [...FAMILY[v]], mtype: "pv", mtype0: "pv" })} />
        <div className="small muted">{T("ms_proc_note")}</div>
      </SideCard>

      {transfers.map((x, i) => (
        <TransferCard key={x.name} k={i + 1} name={x.name} col={x.col} j={x.j} model={model}
          r={sel} win={win} fit={fitOfInput(x.name)} src={srcOf(x.name)} modelFits={modelFits}
          color={x.j < 0 ? MV_STYLE[0] : DIST_STYLE[x.j % 4][0]} />
      ))}

      <SideCard title={T("models")} help={T("h_models")} testid="side-models">
        <div className="checks-grid">
          {MODELS.map((c) => (
            <label key={c} className="small" title={T("h_models")}>
              <input type="checkbox" checked={chosen.includes(c)} data-testid={`chk-${c}`}
                onChange={(e) => void patch({ chosen: e.target.checked ? [...chosen, c] : chosen.filter((y) => y !== c) })} />
              {" "}{T("model_" + c)}
            </label>
          ))}
        </div>
        <Num label={T("thmax")} help={T("thmax_help")} value={st.thmax as number | undefined}
          onCommit={(v) => void patch({ thmax: v })} testid="thmax" />
      </SideCard>

      <SideCard title={T("dist_level")} help={T("h_dist_level")} testid="side-unmeasured" defaultOpen={false}>
        <select value={level} onChange={(e) => void patch({ dist_level: e.target.value })} aria-label={T("dist_level")} title={T("h_dist_level")}>
          {["none", "medium", "high"].map((x) => <option key={x} value={x}>{T("dl_" + x)}</option>)}
        </select>
        <div className="small muted">{T("dl_desc_" + level).replace(/\*\*/g, "")}</div>
        <label className="field"><span className="lbl">{T("dist_strength")}<Help text={T("h_dist_strength")} /></span>
          <input type="range" min={1} max={10} disabled={level === "none"} value={Number(st.dist_strength ?? 4)}
            onChange={(e) => void patch({ dist_strength: +e.target.value })} />
        </label>
      </SideCard>

      <SideCard title={T("id_stic")} help={T("h_id_stic")} testid="side-stic" defaultOpen={false}>
        <label className="small" title={T("h_id_stic")}><input type="checkbox" checked={!!st.id_stic}
          onChange={(e) => void patch({ id_stic: e.target.checked })} /> {T("id_stic")}</label>
      </SideCard>

      {windows.data && windows.data.excl.length > 0 && <Exclusion info={windows.data} />}

      <Validation model={model} />
    </>
  );
}
