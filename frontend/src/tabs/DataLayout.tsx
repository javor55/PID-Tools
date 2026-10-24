// Panel záložky Data: čtení tabulky (rozložení, sloupce času / tagu / hodnoty, formát a jednotka času, perioda řádku)
// a jednotky + rozsahy PV / MV (klíče nastavení jako v desktopu a Streamlitu).
import { useState } from "react";
import { ApiError } from "../api/client";
import type { components } from "../api/schema";
import { NumSetting, TextSetting } from "../components/Fields";
import { useSettings, useWs, useWsMutation, useWsQuery } from "../data";
import { useT } from "../i18n";

type LayoutInfo = components["schemas"]["LayoutInfo"];
type Layout = components["schemas"]["Layout"];

function Pick({ label, value, options, onChange, testid }: {
  label: string; value: string; options: { v: string; text: string }[]; onChange: (v: string) => void; testid: string;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      <select value={value} onChange={(e) => onChange(e.target.value)} data-testid={testid}>
        {!options.some((o) => o.v === value) && <option value={value}>{value}</option>}
        {options.map((o) => <option key={o.v} value={o.v}>{o.text}</option>)}
      </select>
    </label>
  );
}

function RowDt({ value, onCommit }: { value: number; onCommit: (v: number) => void }) {
  const T = useT();
  const [v, setV] = useState<string | null>(null);
  const done = () => { if (v !== null && v !== "" && +v > 0 && +v !== value) onCommit(+v); setV(null); };
  return (
    <label className="field" title={T("h_row_dt")}>
      <span>{T("row_dt")}</span>
      <input type="number" min={1e-6} step="any" value={v ?? +value.toPrecision(6)} data-testid="lay-rowdt"
        onChange={(e) => setV(e.target.value)} onBlur={done}
        onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }} />
    </label>
  );
}

/** Rozložení tabulky; otevřené, když soubor nešel přečíst automaticky (jiné než společný čas, čas nerozpoznán). */
export function LayoutSection() {
  const T = useT();
  const ws = useWs().data;
  const q = useWsQuery<LayoutInfo>("layout", "/layout");
  const put = useWsMutation<Layout>("PUT", "/layout");
  const [err, setErr] = useState<string | null>(null);
  const [ov, setOv] = useState<{ f: string; v: boolean } | null>(null);      // ruční rozbalení / sbalení (pro daný soubor)
  const L = q.data;
  if (!L || !ws?.has_data) return null;
  const rows = L.c_time === L.rows_mark;
  const cols = L.table_columns.map((c) => ({ v: c, text: c }));
  const apply = async (patch: Partial<Layout>, keepCols = true) => {
    setErr(null);
    const base: Layout = { layout: L.layout, time_fmt: L.time_fmt, unit: L.unit, row_dt: L.row_dt,
      c_time: keepCols ? L.c_time : null, c_tag: keepCols ? L.c_tag : null, c_val: keepCols ? L.c_val : null };
    try { await put.mutateAsync({ ...base, ...patch }); } catch (e) { setErr(e instanceof ApiError ? T(e.message) : String(e)); }
  };
  const open = L.layout !== "wide" || L.time_note === "rows_auto" || L.time_fmt !== "auto" || L.unit !== "s";
  return (
    <details className="sec" open={ov?.f === ws.fname ? ov.v : open} data-testid="layout-sec"
      onToggle={(e) => setOv({ f: ws.fname, v: e.currentTarget.open })}>
      <summary>{T("dk_sec_file")}</summary>
      <div className="stack">
        <Pick label={T("layout")} value={L.layout ?? "wide"} testid="lay-layout"
          options={(["wide", "pairs", "long"] as const).map((v) => ({ v, text: T("layout_" + v) }))}
          onChange={(v) => void apply({ layout: v as Layout["layout"] }, false)} />
        {L.layout === "wide" && (
          <Pick label={T("col_time")} value={L.c_time ?? L.rows_mark} testid="lay-time"
            options={[{ v: L.rows_mark, text: T("time_rows") }, ...cols]} onChange={(v) => void apply({ c_time: v })} />)}
        {L.layout === "long" && (<>
          <Pick label={T("col_time")} value={L.c_time ?? ""} options={cols} testid="lay-time" onChange={(v) => void apply({ c_time: v })} />
          <Pick label={T("col_tag")} value={L.c_tag ?? ""} options={cols} testid="lay-tag" onChange={(v) => void apply({ c_tag: v })} />
          <Pick label={T("col_value")} value={L.c_val ?? ""} options={cols} testid="lay-val" onChange={(v) => void apply({ c_val: v })} />
        </>)}
        {L.layout === "wide" && rows && <RowDt value={L.row_dt} onCommit={(v) => void apply({ row_dt: v })} />}
        {!(L.layout === "wide" && rows) && (
          <Pick label={T("time_fmt")} value={L.time_fmt ?? "auto"} testid="lay-fmt"
            options={L.time_formats.map((v) => ({ v, text: T("tf_" + v) }))} onChange={(v) => void apply({ time_fmt: v })} />)}
        <Pick label={T("time_unit")} value={L.unit ?? "s"} testid="lay-unit"
          options={L.units.map((v) => ({ v, text: v }))} onChange={(v) => void apply({ unit: v })} />
        {L.layout === "wide" && rows && (
          <div className="muted small" data-testid="lay-note">
            {T(L.time_note === "rows_auto" ? "time_rows_auto" : "time_rows_note", { dt: +L.row_dt.toPrecision(6), u: L.unit })}
          </div>)}
        {err && <div className="err small" role="alert" data-testid="lay-err">{T("err_data", { ex: err })}</div>}
      </div>
    </details>
  );
}

/** Jednotky, tag smyčky a rozsahy PV / MV (rozsah zadaný ručně už odhad z dat nepřepíše). */
export function UnitsSection() {
  const T = useT();
  const st = useSettings().data ?? {};
  if (!useWs().data?.has_data) return null;
  const bad = (k: string) => Number(st[`${k}_hi`]) <= Number(st[`${k}_lo`]);
  return (
    <section data-testid="units">
      <h3>{T("sb_units")}</h3>
      <TextSetting k="u_pv" label={T("unit_pv")} placeholder="m, °C, bar…" title={T("h_unit")} />
      <TextSetting k="u_mv" label={T("unit_mv")} title={T("h_unit")} />
      <TextSetting k="loop_tag" label="Tag" />
      {(["pv", "mv"] as const).map((k) => (
        <div key={k} className="grid2 small" style={{ gridTemplateColumns: "1fr 1fr" }}>
          <NumSetting k={`${k}_lo`} label={T("ui_range_lo", { v: k.toUpperCase() })} extra={{ [`${k}_rng_user`]: true }} />
          <NumSetting k={`${k}_hi`} label={T("ui_range_hi", { v: k.toUpperCase() })} extra={{ [`${k}_rng_user`]: true }} />
          {bad(k) && <div className="err small" role="alert">{T("err_range_blk")}</div>}
        </div>))}
    </section>
  );
}
