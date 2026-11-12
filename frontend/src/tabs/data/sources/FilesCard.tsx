// Data › Zdroje a smyčky: karta „Soubory“ – tabulka zdrojů (formát, sloupce, perioda, rozsah, časové pásmo a posun, odebrání),
// přidání souboru (výběr i přetažení), úprava čtení, a pod ní časové pokrytí souborů se společnou mřížkou.
import { useRef, useState } from "react";
import { Card } from "../../../components/Card";
import { LabelHelp, Seg } from "../../../components/Ui";
import { useT } from "../../../i18n";
import { useUi } from "../../../store";
import { OpcButton } from "../../OpcDialog";
import { Commit, parse } from "./Commit";
import { errText, type Sources, type SourcePatch, useAct, useAddSource } from "./api";
import { fmtClock, fmtDur, fmtPeriod, fmtRange, hoursToSec, secToHours, type SourceInfo, stripExt, ticks, timeline, type GridMode } from "./geometry";

const ACCEPT = ".csv,.txt,.xlsx,.xls";
const LAYOUTS = ["wide", "pairs", "long"] as const;
const TIME_FMTS = ["auto", "num", "iso", "cz", "us", "eu", "mon", "clock"];
const UNITS = ["s", "ms", "min", "h"];

const zones = (): string[] => {
  try { return (Intl as unknown as { supportedValuesOf?: (k: string) => string[] }).supportedValuesOf?.("timeZone") ?? []; } catch { return []; }
};

function ReadOptions({ s, patch }: { s: SourceInfo; patch: (b: SourcePatch) => void }) {
  const T = useT();
  const layout = (s.layout ?? "wide") as (typeof LAYOUTS)[number];
  const num = (k: "row_dt" | "sampling_s") => (v: string) => { const n = parse(v); if (n !== undefined && (n === null || n > 0)) patch({ [k]: n }); };
  return (
    <div className="src-read" data-testid={`src-read-${s.id}`}>
      <label className="src-f"><span className="lbl">{T("src_ui_name")}</span>
        <Commit value={s.name} label={T("src_ui_name")} title={T("src_ui_name_h")} onCommit={(v) => v.trim() && patch({ name: v.trim() })} /></label>
      <div className="src-f"><span className="lbl">{T("layout")}<LabelHelp text="h_layout" /></span>
        <Seg value={layout} options={LAYOUTS} label={T("layout")} small testid={`src-layout-${s.id}`} fmt={(v) => T(`ui_data_lay_${v}`)}
          titles={(v) => v === "wide" ? T("ui_data_lay_wide_h") : v === "long" ? T("ui_data_lay_long_h") : T("layout_pairs")}
          onChange={(v) => patch({ layout: v })} /></div>
      <label className="src-f"><span className="lbl">{T("time_fmt")}<LabelHelp text="h_time_fmt" /></span>
        <select aria-label={T("time_fmt")} title={T("h_time_fmt")} value={s.time_fmt ?? "auto"} onChange={(e) => patch({ time_fmt: e.target.value })}>
          {TIME_FMTS.map((f) => <option key={f} value={f}>{T("tf_" + f)}</option>)}</select></label>
      <label className="src-f"><span className="lbl">{T("time_unit")}<LabelHelp text="time_unit_help" /></span>
        <select aria-label={T("time_unit")} title={T("time_unit_help")} value={s.unit ?? "s"} onChange={(e) => patch({ unit: e.target.value })}>
          {UNITS.map((f) => <option key={f} value={f}>{f}</option>)}</select></label>
      <label className="src-f"><span className="lbl">{T("row_dt")}<LabelHelp text="h_row_dt" /></span>
        <Commit type="number" min={0} value={s.row_dt != null ? String(+s.row_dt.toPrecision(6)) : ""} label={T("row_dt")} title={T("h_row_dt")}
          placeholder="auto" onCommit={num("row_dt")} /></label>
      <label className="src-f"><span className="lbl">{T("src_ui_sampling")}<LabelHelp text="src_ui_sampling_h" /></span>
        <Commit type="number" min={0} value={s.sampling_s != null ? String(+s.sampling_s.toPrecision(6)) : ""} label={T("src_ui_sampling")}
          title={T("src_ui_sampling_h")} placeholder={s.period ? String(+s.period.toPrecision(4)) : "auto"} onCommit={num("sampling_s")} /></label>
    </div>
  );
}

function FileRow({ s, i, origin, patch, remove, open, toggle }: {
  s: SourceInfo; i: number; origin: string | null; patch: (id: string, b: SourcePatch) => void; remove: (id: string) => void;
  open: boolean; toggle: () => void;
}) {
  const T = useT();
  const used = s.used_by.length;
  return (
    <>
      <tr data-testid={`src-row-${s.id}`}>
        <td><span className="src-name"><i className={`src-dot c${i % 6}`} aria-hidden="true" />
          <span title={s.name}>{s.name}</span></span>{!s.loaded && <span className="ltag warn">{T("src_ui_unloaded")}</span>}</td>
        <td>{s.kind.toUpperCase()}</td>
        <td>{s.columns.length}</td>
        <td title={s.sampling_s ? T("src_ui_own_sampling") : T("src_ui_data_period")}>{fmtPeriod(s.sampling_s ?? s.period)}{s.sampling_s ? " *" : ""}</td>
        <td data-testid={`src-range-${s.id}`}>{fmtRange(s.start, s.end, origin)}</td>
        <td>
          <span className="src-tz">
            <Commit value={s.timezone ?? ""} label={T("src_ui_tz")} title={T("src_ui_tz_h")} list="src-tz-list" placeholder="UTC"
              testid={`src-tz-${s.id}`} onCommit={(v) => patch(s.id, { timezone: v.trim() || null })} />
            <Commit type="number" value={String(secToHours(s.offset_s))} label={T("src_ui_offset")} title={T("src_ui_offset_h")}
              className="src-off" testid={`src-off-${s.id}`}
              onCommit={(v) => { const n = parse(v); if (n !== undefined) patch(s.id, { offset_s: hoursToSec(n ?? 0) }); }} />
            <span className="small muted">h</span>
          </span>
        </td>
        <td className="src-acts">
          <button type="button" className="btn small" aria-expanded={open} onClick={toggle} title={T("src_ui_read_h")}
            data-testid={`src-edit-${s.id}`}>{T("src_ui_read")}</button>
          <button type="button" className="btn small" onClick={() => remove(s.id)} data-testid={`src-del-${s.id}`}
            title={used ? T("src_ui_remove_used", { n: s.used_by.map((x) => x + 1).join(", ") }) : T("src_ui_remove_h")}>{T("src_ui_remove")}</button>
        </td>
      </tr>
      {open && <tr className="src-read-row"><td colSpan={7}><ReadOptions s={s} patch={(b) => patch(s.id, b)} /></td></tr>}
    </>
  );
}

/** Pruhy zdrojů proti společnému úseku + nastavení společné mřížky (překryv / sjednocení, perioda auto / ručně). */
function Coverage({ data }: { data: Sources }) {
  const T = useT();
  const act = useAct();
  const [err, setErr] = useState<string | null>(null);
  const [per, setPer] = useState<string | null>(null);
  const { sources, common, time_grid: g, origin } = data;
  const mode = (g.mode === "union" ? "union" : "overlap") as GridMode;
  const tl = timeline(sources, mode, common ?? null);
  const put = async (b: Partial<typeof g>) => {
    setErr(null);
    try { await act("PUT", "/time-grid", { ...g, ...b }); } catch (e) { setErr(errText(e)); }
  };
  const manual = g.period != null;
  const dates = !!tl && tl.hi - tl.lo > 86400;
  const note = !tl ? T("src_ui_no_span")
    : mode === "union" ? T("src_ui_span_union", { a: fmtClock(tl.lo, origin ?? null, dates), b: fmtClock(tl.hi, origin ?? null, dates) })
    : common ? T("src_ui_span_common", { a: fmtClock(common.start, origin ?? null, dates), b: fmtClock(common.end, origin ?? null, dates), d: fmtDur(common.duration) })
    : T("src_ui_span_none");
  const commitPer = () => {
    const n = parse(per ?? "");
    setPer(null);
    if (n && n > 0 && n !== g.period) void put({ period: n });
  };
  return (
    <div className="src-cov" data-testid="src-coverage">
      <div className="src-cov-h">
        <span className="lbl src-cov-t">{T("src_ui_coverage")}<LabelHelp text="src_ui_coverage_h" /></span>
        <span className="small muted" data-testid="src-span-note">{note}</span>
        <span className="src-grid">
          <Seg<GridMode> value={mode} options={["overlap", "union"]} label={T("src_ui_grid_mode")} small testid="src-grid-mode"
            help="src_ui_grid_mode_h" fmt={(v) => T(`src_ui_grid_${v}`)} onChange={(v) => void put({ mode: v })} />
          <Seg<"auto" | "manual"> value={manual ? "manual" : "auto"} options={["auto", "manual"]} label={T("src_ui_period")} small
            testid="src-grid-period" help="src_ui_period_h" fmt={(v) => T(`src_ui_period_${v}`)}
            onChange={(v) => void put({ period: v === "auto" ? null : (sources.find((s) => s.period)?.period ?? 1) })} />
          {manual && (
            <span className="src-per"><input type="number" min={0} step="any" aria-label={T("src_ui_period_val")} title={T("src_ui_period_val")}
              data-testid="src-grid-period-val" value={per ?? String(+(g.period ?? 1).toPrecision(6))} onChange={(e) => setPer(e.target.value)}
              onBlur={commitPer} onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }} /> s</span>)}
        </span>
      </div>
      {err && <div className="err small" role="alert" data-testid="src-grid-err">{err}</div>}
      {tl && (
        <div className="src-tl" data-testid="src-timeline">
          <div className="src-tl-rows">
            {tl.common && <div className="src-tl-common" style={{ left: `calc(158px + (100% - 158px) * ${tl.common.left / 100})`, width: `calc((100% - 158px) * ${tl.common.width / 100})` }}
              data-testid="src-tl-common" title={note} />}
            {sources.map((s, i) => {
              const b = tl.bars[i];
              return (
                <div className="src-tl-row" key={s.id} title={`${s.name} · ${fmtRange(s.start, s.end, origin ?? null)}`}>
                  <span className="src-tl-name">{stripExt(s.name)}</span>
                  <span className="src-tl-lane">{b && <i className={`src-bar c${i % 6}`} data-testid={`src-bar-${s.id}`}
                    style={{ left: `${b.left}%`, width: `${b.width}%` }} />}</span>
                </div>);
            })}
          </div>
          <div className="src-tl-axis" aria-hidden="true">
            {ticks(tl.lo, tl.hi, origin ?? null).map((t) => (
              <span key={t} style={{ left: `${((t - tl.lo) / (tl.hi - tl.lo)) * 100}%` }}>{fmtClock(t, origin ?? null, dates)}</span>))}
          </div>
        </div>)}
    </div>
  );
}

export function FilesCard({ data }: { data: Sources | undefined }) {
  const T = useT();
  const wid = useUi((s) => s.wid);
  const add = useAddSource();
  const act = useAct();
  const pick = useRef<HTMLInputElement>(null);
  const [err, setErr] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [over, setOver] = useState(false);
  const sources = data?.sources ?? [];
  const cols = sources.reduce((n, s) => n + s.columns.length, 0);

  const upload = async (files: FileList | File[] | null | undefined) => {
    setErr(null);
    for (const f of Array.from(files ?? [])) {
      try { await add.mutateAsync(f); } catch (e) { setErr(`${f.name}: ${errText(e)}`); }
    }
  };
  const patch = async (id: string, b: SourcePatch) => {
    setErr(null);
    try { await act("PATCH", `/sources/${id}`, b); } catch (e) { setErr(errText(e)); }
  };
  const remove = async (id: string) => {
    setErr(null);
    try { await act("DELETE", `/sources/${id}`); } catch (e) { setErr(errText(e)); }
  };
  const demo = async () => { setErr(null); try { await act("POST", "/data/demo"); } catch (e) { setErr(errText(e)); } };
  const isFiles = (e: React.DragEvent) => Array.from(e.dataTransfer.types).includes("Files");

  return (
    <Card title={T("src_ui_files")} help="src_ui_files_h" testid="src-files" className={over ? "src-over" : ""}
      right={<>
        <span data-testid="src-count">{T("src_ui_files_count", { n: sources.length, c: cols })}</span>
        <span className="src-btns">
          <label className="btn primary small" title={T("src_ui_add_h")}>
            {T("src_ui_add")}
            <input ref={pick} type="file" accept={ACCEPT} multiple hidden data-testid="src-add-file" aria-label={T("src_ui_add")}
              onChange={(e) => { void upload(e.target.files); e.target.value = ""; }} />
          </label>
          <OpcButton />
        </span>
      </>}>
      <div className="src-drop-wrap" onDragOver={(e) => { if (isFiles(e)) { e.preventDefault(); setOver(true); } }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => { if (isFiles(e)) { e.preventDefault(); setOver(false); void upload(e.dataTransfer.files); } }}>
        {sources.length > 0 && (
          <div className="lscroll">
            <table className="ltbl src-tbl" data-testid="src-table">
              <thead><tr>
                <th>{T("src_ui_h_file")}</th><th>{T("src_ui_h_format")}</th><th>{T("src_ui_h_cols")}</th>
                <th title={T("src_ui_h_period_h")}>{T("src_ui_h_period")}</th><th>{T("src_ui_h_range")}</th>
                <th><span className="lbl">{T("src_ui_h_tz")}<LabelHelp text="src_ui_tz_h" /></span></th><th><span className="sr-only">{T("src_ui_h_actions")}</span></th>
              </tr></thead>
              <tbody>
                {sources.map((s, i) => <FileRow key={s.id} s={s} i={i} origin={data?.origin ?? null} patch={(id, b) => void patch(id, b)}
                  remove={(id) => void remove(id)} open={open === s.id} toggle={() => setOpen(open === s.id ? null : s.id)} />)}
              </tbody>
            </table>
            <datalist id="src-tz-list">{zones().map((z) => <option key={z} value={z} />)}</datalist>
          </div>)}
        {!sources.length && (
          <div className="src-empty" data-testid="src-empty">
            <p>{T("src_ui_empty")}</p>
            <button type="button" className="btn small" onClick={() => void demo()} disabled={!wid} title={T("src_ui_demo_h")} data-testid="src-demo">
              {T("src_ui_demo")}</button>
          </div>)}
        {err && <div className="err small" role="alert" data-testid="src-err">{err}</div>}
        <div className="src-dropnote small muted">{T("src_ui_drop")}</div>
      </div>
      {data && sources.length > 0 && <Coverage data={data} />}
    </Card>
  );
}
