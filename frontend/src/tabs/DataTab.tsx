// Záložka Data podle návrhu. Hlavní plocha: prohlížeč záznamu, karta Kvalita dat, Náhled souboru (bez dat plocha pro
// přetažení CSV / XLSX). Panel (karty): Zdroj dat, Signály smyčky, Statistika, Jednotky a rozsahy, Pokračovat na Model.
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { ApiError } from "../api/client";
import type { components } from "../api/schema";
import { RecordViewer } from "../components/RecordViewer";
import { PrimaryAction, SideCard } from "../components/Ui";
import { uploadFile, useSettings, useWs, useWsQuery } from "../data";
import { useT, useTexts } from "../i18n";
import { useUi } from "../store";
import "../styles/data.css";
import { DataQualityCard } from "./DataQuality";
import { FullPreview, PreviewCard } from "./DataPreview";
import { UnitsBody } from "./DataLayout";

type StatRow = components["schemas"]["StatRow"];
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

/** Smyčka jen pro čtení: role a sloupce aktivní smyčky; úpravy jsou jen ve Zdrojích a smyčkách. */
function LoopCard() {
  const T = useT();
  const ws = useWs().data;
  const setDataSub = useUi((s) => s.setDataSub);
  if (!ws?.has_data) return null;
  const rows: [string, string | null | undefined][] = [["PV", ws.pv], ["SP", ws.sp], ["MV", ws.mv], ["POS", ws.pos]];
  return (
    <SideCard title={T("dq_loop_title")} testid="card-loop">
      <div className="dt-ro" data-testid="loop-ro">
        {[...rows.filter(([, v]) => v), ...(ws.dists ?? []).map((d) => ["DV", d] as [string, string])].flatMap(([k, v], i) => [
          <b key={`k${i}`} className={`role-${k}`}>{k}</b>, <span key={`v${i}`} className="mono">{v}</span>])}
      </div>
      <button type="button" className="dt-linkbtn" title={T("dq_loop_edit_h")} data-testid="loop-edit" onClick={() => setDataSub("sources")}>
        {T("dq_loop_edit")}</button>
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
      {has && <LoopCard />}
      {has && <StatsCard />}
      {has && (
        <SideCard title={T("tn_units")} help={T("ui_data_units_h")} testid="card-units"><UnitsBody /></SideCard>)}
      {has && <PrimaryAction onClick={() => setTab("model")} testid="to-model">{T("tn_to_model")}</PrimaryAction>}
    </>
  );
}

