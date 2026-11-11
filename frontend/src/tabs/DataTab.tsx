// Záložka Data podle návrhu. Hlavní plocha: prohlížeč záznamu, karta Kvalita dat, Náhled souboru (bez dat plocha pro
// přetažení CSV / XLSX). Panel (karty): Zdroj dat, Signály smyčky, Statistika, Jednotky a rozsahy, Pokračovat na Model.
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { ApiError } from "../api/client";
import type { components } from "../api/schema";
import { fmtDuration } from "../components/Header";
import { RecordViewer } from "../components/RecordViewer";
import { PrimaryAction, SideCard, Seg } from "../components/Ui";
import { type Columns, uploadFile, useSettings, useWs, useWsMutation, useWsQuery } from "../data";
import { useT, useTexts } from "../i18n";
import { useUi } from "../store";
import "../styles/data.css";
import { DataQualityCard } from "./DataQuality";
import { FullPreview, PreviewCard } from "./DataPreview";
import { ManualRead, ReadStatus, UnitsBody } from "./DataLayout";
import { OpcButton } from "./OpcDialog";

type StatRow = components["schemas"]["StatRow"];
const NONE = "—";
const ACCEPT = ".csv,.txt,.xlsx,.xls";

/** Nahrání souboru (výběr i přetažení); chyba čtení se ukáže tam, kde se nahrávalo. */
function useUpload() {
  const T = useT();
  const wid = useUi((s) => s.wid);
  const qc = useQueryClient();
  const [err, setErr] = useState<string | null>(null);
  const load = async (f: File | undefined) => {
    if (!f || !wid) return;
    setErr(null);
    try {
      await uploadFile(wid, f);
      await qc.invalidateQueries({ queryKey: ["ws", wid] });
    } catch (e) {
      setErr(e instanceof ApiError ? T(e.message) : String(e));
    }
  };
  return { load, err };
}

/** Soubor přetažený kamkoli na stránku (dokud je otevřená záložka Data) se načte. */
function usePageDrop(load: (f: File | undefined) => Promise<void>) {
  const [over, setOver] = useState(false);
  useEffect(() => {
    const has = (e: DragEvent) => Array.from(e.dataTransfer?.types ?? []).includes("Files");
    let depth = 0;
    const enter = (e: DragEvent) => { if (has(e)) { depth++; setOver(true); } };
    const leave = (e: DragEvent) => { if (has(e) && --depth <= 0) { depth = 0; setOver(false); } };
    const dragover = (e: DragEvent) => { if (has(e)) e.preventDefault(); };
    const drop = (e: DragEvent) => {
      if (!has(e)) return;
      e.preventDefault(); depth = 0; setOver(false);
      void load(e.dataTransfer?.files[0]);
    };
    window.addEventListener("dragenter", enter); window.addEventListener("dragleave", leave);
    window.addEventListener("dragover", dragover); window.addEventListener("drop", drop);
    return () => {
      window.removeEventListener("dragenter", enter); window.removeEventListener("dragleave", leave);
      window.removeEventListener("dragover", dragover); window.removeEventListener("drop", drop);
    };
  }, [load]);
  return over;
}

export function DataMain() {
  const T = useT();
  const texts = useTexts();
  const ws = useWs().data;
  const { load, err } = useUpload();
  const over = usePageDrop(load);
  const [full, setFull] = useState(false);
  const overlay = over && <div className="dt-pagedrop" aria-hidden="true">{T("ui_data_drop_active")}</div>;
  if (!ws?.has_data) {
    return (
      <div className="dt-main" data-testid="no-data">
        {overlay}
        <span className="dt-note small muted">{T("ui_data_drop_hint")}</span>
        <div className={"dt-drop" + (over ? " over" : "")} data-testid="drop-zone">
          <h2>{T("ui_data_drop_title")}</h2>
          <p>{T("empty")}</p>
          <label className="btn primary">
            {T("ui_data_drop_pick")}
            <input type="file" accept={ACCEPT} hidden data-testid="load-file-main" onChange={(e) => void load(e.target.files?.[0])} />
          </label>
          {err && <div className="err small" role="alert">{err}</div>}
        </div>
      </div>
    );
  }
  return (
    <div className="dt-main">
      {overlay}
      <div className="dt-top">
        <span className="dt-note">{T("ui_data_viewer_note")}</span>
        <button type="button" className="dt-linkbtn" onClick={() => setFull(true)} data-testid="full-open">{T("ui_data_full")}</button>
      </div>
      {texts && <RecordViewer texts={texts} />}
      <DataQualityCard />
      <PreviewCard onFull={() => setFull(true)} />
      {full && <FullPreview onClose={() => setFull(false)} />}
    </div>
  );
}

const fmtStat = (v: number | null | undefined, lang: string) => v === null || v === undefined ? "–"
  : (+v.toPrecision(4)).toLocaleString(lang, { minimumFractionDigits: 1, maximumFractionDigits: 6 });

type Src = "file" | "demo" | "opc";

/** Karta Zdroj dat: přepínač Soubor / Ukázka / OPC UA, načtený soubor, stav čtení a ruční nastavení. */
function SourceCard() {
  const T = useT();
  const lang = useUi((s) => s.lang);
  const ws = useWs().data;
  const demo = useWsMutation("POST", "/data/demo");
  const { load, err } = useUpload();
  const [pick, setPick] = useState<{ v: Src; f: string } | null>(null);
  const fname = ws?.fname ?? "";
  const src: Src = pick && (pick.v === "opc" || pick.f === fname) ? pick.v : fname === "demo" && ws?.has_data ? "demo" : "file";
  const sum = ws?.has_data ? T("ui_data_samples", { n: (ws.n ?? 0).toLocaleString(lang), ts: +(ws.Ts ?? 0).toPrecision(3),
    d: fmtDuration(ws.duration, lang) }) : "";
  return (
    <SideCard title={T("dk_sec_src")} help={T("h_source")} testid="card-src">
      <Seg<Src> value={src} options={["file", "demo", "opc"]} label={T("source")} stretch testid="src-seg"
        fmt={(v) => T(`src_${v}`)} onChange={(v) => {
          setPick({ v, f: fname });
          if (v === "demo") demo.mutate(undefined);
        }} />
      {src === "file" && !(ws?.has_data && fname !== "demo") && (
        <div className="dt-filebox">
          <span>{T("upload")}</span>
          <label className="btn" htmlFor="dt-file">{T("ui_data_drop_pick")}</label>
        </div>)}
      {src === "demo" && <p className="dt-p">{T("demo_desc")}</p>}
      {src === "opc" && (<><p className="dt-p">{T("opc_intro")}</p><OpcButton /></>)}
      {ws?.has_data && (src !== "file" || fname !== "demo") && (
        <div className="dt-filebox" data-testid="data-info">
          <b>{fname}</b><span>{sum}</span>
          {src === "file" && <label className="btn" htmlFor="dt-file">{T("ui_data_other_file")}</label>}
        </div>)}
      <input id="dt-file" type="file" accept={ACCEPT} hidden data-testid="load-file"
        onChange={(e) => { void load(e.target.files?.[0]).then(() => setPick(null)); e.target.value = ""; }} />
      {err && <div className="dt-read err" role="alert">{err}</div>}
      <ReadStatus />
      <ManualRead />
    </SideCard>
  );
}

/** Karta Signály smyčky: PV, MV, SP, měřené poruchy (DV jako odebíratelné štítky) a poloha aktuátoru. */
function SignalsCard() {
  const T = useT();
  const ws = useWs().data;
  const cols = useWsMutation<Columns>("PUT", "/columns");
  const [posOn, setPosOn] = useState(false);
  if (!ws?.has_data || !ws.pv || !ws.mv) return null;
  const set = (patch: Partial<Columns>) => {
    const cur: Columns = { pv: ws.pv!, mv: ws.mv!, sp: ws.sp ?? null, dists: ws.dists ?? [], pos: ws.pos ?? null };
    const next = { ...cur, ...patch };
    cols.mutate({ ...next, sp: next.sp === NONE ? null : next.sp, pos: next.pos === NONE ? null : next.pos });
  };
  const options = ws.columns;
  const dists = ws.dists ?? [];
  const free = options.filter((c) => c !== ws.pv && c !== ws.mv && c !== ws.sp && c !== ws.pos && !dists.includes(c));
  const sel = (id: string, value: string | null | undefined, opts: string[], onChange: (v: string) => void, optional?: string) => (
    <select id={id} data-testid={id} value={value ?? NONE} onChange={(e) => onChange(e.target.value)}>
      {optional && <option value={NONE}>{optional}</option>}
      {opts.map((c) => <option key={c} value={c}>{c}</option>)}
    </select>);
  const showPos = !!ws.pos || posOn;
  return (
    <SideCard title={T("dk_sec_signals")} help={T("ui_data_signals_h")} testid="card-signals">
      <div className="dt-sig">
        <label htmlFor="col-pv" className="role-PV" title={T("h_pv")}>PV</label>
        {sel("col-pv", ws.pv, options, (v) => set({ pv: v }))}
        <label htmlFor="col-mv" className="role-MV" title={T("h_mv")}>MV</label>
        {sel("col-mv", ws.mv, options, (v) => set({ mv: v }))}
        <label htmlFor="col-sp" className="role-SP" title={T("h_sp")}>SP</label>
        {sel("col-sp", ws.sp, options.filter((c) => c !== ws.pv && c !== ws.mv), (v) => set({ sp: v }), T("tn_sp_none"))}
        <span className="lab role-DV" title={T("col_dist_help")}>DV</span>
        <div className="dt-chips" data-testid="col-d">
          {dists.map((d) => (
            <span key={d} className="dt-chip" data-testid="dv-chip">{d}
              <button type="button" aria-label={`${T("ui_data_rm_dv")}: ${d}`} title={T("ui_data_rm_dv")}
                onClick={() => set({ dists: dists.filter((x) => x !== d) })}>×</button></span>))}
          {free.length > 0 && (
            <select className="dt-pill" aria-label={T("col_dist")} value="" data-testid="col-d-add"
              onChange={(e) => { if (e.target.value) set({ dists: [...dists, e.target.value] }); }}>
              <option value="">{T("ui_data_add_dv")}</option>
              {free.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>)}
        </div>
        {showPos ? (<>
          <label htmlFor="col-pos" className="role-POS" title={T("h_pos")}>{T("pos_short")}</label>
          {sel("col-pos", ws.pos, options.filter((c) => c !== ws.pv && c !== ws.mv && c !== ws.sp && !dists.includes(c)),
            (v) => set({ pos: v }), NONE)}
        </>) : (<>
          <span />
          <span className="dt-chips"><button type="button" className="dt-pill" title={T("h_pos")} data-testid="pos-add"
            onClick={() => setPosOn(true)}>{T("ui_data_add_pos")}</button></span>
        </>)}
      </div>
      <p className="dt-p">{T("guess_note")}</p>
    </SideCard>
  );
}

/** Karta Statistika: min / max / průměr / σ veličin smyčky a upozornění na rozsah měření. */
function StatsCard() {
  const T = useT();
  const lang = useUi((s) => s.lang);
  const ws = useWs().data;
  const st = useSettings().data ?? {};
  const rows = useWsQuery<StatRow[]>("datastats", "/datastats").data;
  if (!ws?.has_data || !rows) return null;
  const pv = rows.find((r) => r.role === "PV");
  const lo = Number(st.pv_lo), hi = Number(st.pv_hi);
  const f = (v: number) => fmtStat(v, lang);
  const warn = pv?.min != null && pv.min < lo ? T("ui_data_range_below", { lo: f(lo), v: f(pv.min) })
    : pv?.max != null && pv.max > hi ? T("ui_data_range_above", { hi: f(hi), v: f(pv.max) }) : null;
  return (
    <SideCard title={T("dk_sec_stats")} testid="card-stats">
      <table className="dt-stat" data-testid="stats">
        <thead><tr><th scope="col" /><th scope="col">Min</th><th scope="col">Max</th><th scope="col">{T("stat_mean")}</th><th scope="col">σ</th></tr></thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={`${r.name}${i}`}>
              <th scope="row" className={`role-${r.role}`} title={r.name}>{r.role}</th>
              <td>{fmtStat(r.min, lang)}</td><td>{fmtStat(r.max, lang)}</td><td>{fmtStat(r.mean, lang)}</td><td>{fmtStat(r.std, lang)}</td>
            </tr>))}
        </tbody>
      </table>
      <p className={"dt-rng" + (warn ? "" : " ok")} data-testid="stats-note">{warn ?? T("ui_data_range_ok")}</p>
    </SideCard>
  );
}

export function DataSide() {
  const T = useT();
  const setTab = useUi((s) => s.setTab);
  const has = !!useWs().data?.has_data;
  return (
    <>
      <SourceCard />
      {has && <SignalsCard />}
      {has && <StatsCard />}
      {has && (
        <SideCard title={T("tn_units")} help={T("ui_data_units_h")} testid="card-units"><UnitsBody /></SideCard>)}
      {has && <PrimaryAction onClick={() => setTab("model")} testid="to-model">{T("tn_to_model")}</PrimaryAction>}
    </>
  );
}

