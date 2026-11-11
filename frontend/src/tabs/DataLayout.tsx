// Panel záložky Data: stav čtení souboru, ruční nastavení čtení (rozložení, sloupce času / tagu / hodnoty, formát a jednotka
// času, perioda řádku) a obsah karty „Jednotky a rozsahy“ (klíče nastavení jako v desktopu a Streamlitu).
import { useRef, useState } from "react";
import { ApiError } from "../api/client";
import type { components } from "../api/schema";
import { Seg } from "../components/Ui";
import { usePatchSettings, useSettings, useWs, useWsMutation, useWsQuery } from "../data";
import { useT } from "../i18n";
import "../styles/data.css";

type LayoutInfo = components["schemas"]["LayoutInfo"];
type Layout = components["schemas"]["Layout"];

function Pick({ label, value, options, onChange, testid, title }: {
  label: string; value: string; options: { v: string; text: string }[]; onChange: (v: string) => void; testid: string; title?: string;
}) {
  return (
    <>
      <label htmlFor={testid} title={title}>{label}</label>
      <select id={testid} value={value} onChange={(e) => onChange(e.target.value)} data-testid={testid}>
        {!options.some((o) => o.v === value) && <option value={value}>{value}</option>}
        {options.map((o) => <option key={o.v} value={o.v}>{o.text}</option>)}
      </select>
    </>
  );
}

function RowDt({ value, onCommit }: { value: number; onCommit: (v: number) => void }) {
  const T = useT();
  const [v, setV] = useState<string | null>(null);
  const done = () => { if (v !== null && v !== "" && +v > 0 && +v !== value) onCommit(+v); setV(null); };
  return (
    <>
      <label htmlFor="lay-rowdt" title={T("h_row_dt")}>{T("row_dt")}</label>
      <input id="lay-rowdt" type="number" min={1e-6} step="any" value={v ?? +value.toPrecision(6)} data-testid="lay-rowdt"
        onChange={(e) => setV(e.target.value)} onBlur={done}
        onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }} />
    </>
  );
}

const LAYOUTS = ["wide", "pairs", "long"] as const;

/** „✓ Přečteno automaticky (široké, čas „Čas“, datum a čas). Další soubor lze i přetáhnout kamkoli na stránku.“ */
export function ReadStatus() {
  const T = useT();
  const ws = useWs().data;
  const L = useWsQuery<LayoutInfo>("layout", "/layout").data;
  if (!L || !ws?.has_data) return null;
  const lay = T(`ui_data_lay_${L.layout ?? "wide"}`).toLowerCase();
  const rows = L.layout === "wide" && L.c_time === L.rows_mark;
  const fmt = L.time_fmt && L.time_fmt !== "auto" ? T("tf_" + L.time_fmt) : ws.origin ? T("prev_datetime") : T("prev_k_num");
  const txt = rows
    ? T(L.time_note === "rows_auto" ? "time_rows_auto" : "time_rows_note", { dt: +L.row_dt.toPrecision(6), u: L.unit })
    : T("read_auto_ok", { lay, c: L.c_time ?? L.c_tag ?? "", f: fmt });
  return <p className="dt-read" data-testid="read-status">{txt} {T("ui_data_read_more")}</p>;
}

/** Ruční nastavení čtení; otevřené, když soubor nešel přečíst automaticky (jiné než společný čas, čas nerozpoznán). */
export function ManualRead() {
  const T = useT();
  const ws = useWs().data;
  const q = useWsQuery<LayoutInfo>("layout", "/layout");
  const put = useWsMutation<Layout>("PUT", "/layout");
  const [err, setErr] = useState<string | null>(null);
  const [ov, setOv] = useState<{ f: string; v: boolean } | null>(null);      // ruční rozbalení / sbalení (pro daný soubor)
  const sent = useRef<{ f: string; body: Layout } | null>(null);
  const L = q.data;
  if (!L || !ws?.has_data) return null;
  const rows = L.c_time === L.rows_mark;
  const cols = L.table_columns.map((c) => ({ v: c, text: c }));
  const apply = async (patch: Partial<Layout>, keepCols = true) => {
    setErr(null);
    // poslední odeslané čtení má přednost před načteným (to se po změně načítá znovu): dvě rychlé změny po sobě
    // (perioda, pak jednotka) jinak pošlou podruhé starou hodnotu té první
    const cur = { layout: L.layout, time_fmt: L.time_fmt, unit: L.unit, row_dt: L.row_dt, c_time: L.c_time, c_tag: L.c_tag,
      c_val: L.c_val, ...(sent.current?.f === ws.fname ? sent.current.body : {}) };
    const body: Layout = { ...cur, ...(keepCols ? {} : { c_time: null, c_tag: null, c_val: null }), ...patch };
    sent.current = { f: ws.fname, body };
    try { await put.mutateAsync(body); } catch (e) {
      sent.current = null;                                   // server nechal předchozí čtení
      setErr(e instanceof ApiError ? T(e.message) : String(e));
    }
  };
  const open = L.layout !== "wide" || L.time_note === "rows_auto" || L.time_fmt !== "auto" || L.unit !== "s";
  const titles = (v: string) => v === "wide" ? T("ui_data_lay_wide_h") : v === "long" ? T("ui_data_lay_long_h") : T("layout_pairs");
  return (
    <details className="dt-manual" open={ov?.f === ws.fname ? ov.v : open} data-testid="layout-sec"
      onToggle={(e) => setOv({ f: ws.fname, v: e.currentTarget.open })}>
      <summary title={T("h_read_manual")}>{T("ui_data_manual")}</summary>
      <div className="dt-grid">
        <span>{T("layout")}</span>
        <Seg value={L.layout ?? "wide"} options={LAYOUTS} label={T("layout")} stretch small testid="lay-layout" help="h_layout"
          fmt={(v) => T(`ui_data_lay_${v}`)} titles={titles} onChange={(v) => void apply({ layout: v }, false)} />
        {L.layout === "wide" && (
          <Pick label={T("col_time")} value={L.c_time ?? L.rows_mark} testid="lay-time" title={T("h_lay_time")}
            options={[{ v: L.rows_mark, text: T("time_rows") }, ...cols]} onChange={(v) => void apply({ c_time: v })} />)}
        {L.layout === "long" && (<>
          <Pick label={T("col_time")} value={L.c_time ?? ""} options={cols} testid="lay-time" title={T("h_lay_time")} onChange={(v) => void apply({ c_time: v })} />
          <Pick label={T("col_tag")} value={L.c_tag ?? ""} options={cols} testid="lay-tag" title={T("h_lay_tag")} onChange={(v) => void apply({ c_tag: v })} />
          <Pick label={T("col_value")} value={L.c_val ?? ""} options={cols} testid="lay-val" title={T("h_lay_val")} onChange={(v) => void apply({ c_val: v })} />
        </>)}
        {L.layout === "wide" && rows && <RowDt value={L.row_dt} onCommit={(v) => void apply({ row_dt: v })} />}
        {!(L.layout === "wide" && rows) && (
          <Pick label={T("time_fmt")} value={L.time_fmt ?? "auto"} testid="lay-fmt" title={T("h_time_fmt")}
            options={L.time_formats.map((v) => ({ v, text: T("tf_" + v) }))} onChange={(v) => void apply({ time_fmt: v })} />)}
        <Pick label={T("time_unit")} value={L.unit ?? "s"} testid="lay-unit" title={T("time_unit_help")}
          options={L.units.map((v) => ({ v, text: v }))} onChange={(v) => void apply({ unit: v })} />
        {L.layout === "wide" && rows && (
          <div className="dt-p full" data-testid="lay-note">
            {T(L.time_note === "rows_auto" ? "time_rows_auto" : "time_rows_note", { dt: +L.row_dt.toPrecision(6), u: L.unit })}
          </div>)}
        {err && <div className="dt-read err full" role="alert" data-testid="lay-err">{T("err_data", { ex: err })}</div>}
        <p className="dt-p full">{T("ui_data_manual_note")}</p>
      </div>
    </details>
  );
}

function BareText({ k, label, placeholder, title }: { k: string; label: string; placeholder?: string; title?: string }) {
  const st = useSettings().data ?? {};
  const patch = usePatchSettings();
  const [v, setV] = useState<string | null>(null);
  const cur = String(st[k] ?? "");
  const done = () => { if (v !== null && v !== cur) void patch({ [k]: v }); setV(null); };
  return (
    <input type="text" aria-label={label} title={title} value={v ?? cur} placeholder={placeholder} data-testid={`set-${k}`}
      onChange={(e) => setV(e.target.value)} onBlur={done}
      onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }} />
  );
}

function BareNum({ k, label, extra, title }: { k: string; label: string; extra: Record<string, unknown>; title?: string }) {
  const st = useSettings().data ?? {};
  const patch = usePatchSettings();
  const [v, setV] = useState<string | null>(null);
  const cur = st[k] ?? "";
  return (
    <input type="number" step="any" aria-label={label} title={title} data-testid={`set-${k}`}
      value={v ?? (typeof cur === "number" ? +cur.toPrecision(6) : String(cur))} onChange={(e) => setV(e.target.value)}
      onBlur={() => { if (v !== null && v !== "" && Number.isFinite(+v)) void patch({ [k]: +v, ...extra }); setV(null); }}
      onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }} />
  );
}

/** Jednotky, rozsahy PV / MV a tag smyčky (rozsah zadaný ručně už odhad z dat nepřepíše). */
export function UnitsBody() {
  const T = useT();
  const st = useSettings().data ?? {};
  const bad = (k: string) => Number(st[`${k}_hi`]) <= Number(st[`${k}_lo`]);
  return (
    <div data-testid="units">
      <div className="dt-units">
        <span /><span className="h">{T("tn_unit")}</span><span className="h">{T("tn_range")}</span>
        {(["pv", "mv"] as const).map((k) => (
          <div key={k} style={{ display: "contents" }}>
            <span className={`lab role-${k.toUpperCase()}`}>{k.toUpperCase()}</span>
            <BareText k={`u_${k}`} label={T(`unit_${k}`)} placeholder={k === "pv" ? "m, °C, bar…" : undefined} title={T("h_unit")} />
            <span className="rng">
              <BareNum k={`${k}_lo`} label={T("ui_range_lo", { v: k.toUpperCase() })} extra={{ [`${k}_rng_user`]: true }} title={T("h_norm")} />–
              <BareNum k={`${k}_hi`} label={T("ui_range_hi", { v: k.toUpperCase() })} extra={{ [`${k}_rng_user`]: true }} title={T("h_norm")} />
            </span>
          </div>))}
        <span className="lab">Tag</span>
        <span style={{ gridColumn: "2 / -1" }}><BareText k="loop_tag" label="Tag" title={T("h_loop_tag")} /></span>
      </div>
      {(["pv", "mv"] as const).filter(bad).map((k) => <div key={k} className="dt-read err" role="alert">{T("err_range_blk")}</div>)}
      <p className="dt-p" style={{ marginTop: 8 }}>{T("norm_where", {
        pv: `${st.pv_lo ?? 0}–${st.pv_hi ?? 100}`, mv: `${st.mv_lo ?? 0}–${st.mv_hi ?? 100}` })}</p>
    </div>
  );
}
