// Data › Zdroje a smyčky: karta „Smyčky“ – karta na smyčku ve dvou řádcích (tag, popis, role PV / SP / MV / poloha / DV / režim jako
// „soubor › sloupec“, rozsahy, kaskáda, stav mapování), přidání a odebrání smyčky, výběr aktivní smyčky, návrh podle
// názvů tagů a import mapování z CSV (návrh se nejdřív ukáže ke kontrole). Role jde zadat výběrem i přetažením sloupce.
import { useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { Card } from "../../../components/Card";
import { LabelHelp } from "../../../components/Ui";
import { useT } from "../../../i18n";
import { useUi } from "../../../store";
import { errText, importCsv, type Sources, type Suggestions, useActiveLoop, useAct, useMappings } from "./api";
import { Commit, parse } from "./Commit";
import {
  COL_MIME, type LoopMapping, loopName, mappingBody, mappingStatus, parseKey, type Ref, refKey, refLabel, type Role,
  withoutDv, withRole,
} from "./geometry";

type Src = Sources["sources"];

/** Výběr sloupce všech zdrojů ve tvaru „soubor › sloupec“ (seskupeno podle zdroje); prázdná hodnota = nepřiřazeno. */
function ColSelect({ value, sources, onPick, label, title, empty, testid }: {
  value: Ref | null | undefined; sources: Src; onPick: (r: Ref | null) => void; label: string; title: string; empty: string; testid?: string;
}) {
  const key = value ? refKey(value) : "";
  const known = !value || sources.some((s) => s.id === value.source && s.columns.includes(value.column));
  // v uzavřeném výběru je kvůli šířce jen název sloupce (celé „soubor › sloupec“ je v title a ve skupinách seznamu);
  // stejný název ve více souborech se rozliší předponou
  const count = new Map<string, number>();
  sources.forEach((s) => s.columns.forEach((c) => count.set(c, (count.get(c) ?? 0) + 1)));
  const txt = (r: Ref) => (count.get(r.column)! > 1 ? refLabel(r, sources) : r.column);
  return (
    <select aria-label={label} title={value ? `${title}\n${refLabel(value, sources)}` : title} value={key} data-testid={testid} className={value ? "" : "src-unset"}
      onChange={(e) => onPick(e.target.value ? parseKey(e.target.value) : null)}>
      <option value="">{empty}</option>
      {!known && value && <option value={key}>{refLabel(value, sources)}</option>}
      {sources.map((s) => (
        <optgroup key={s.id} label={s.name}>
          {s.columns.map((c) => <option key={c} value={refKey({ source: s.id, column: c })}>{txt({ source: s.id, column: c })}</option>)}
        </optgroup>))}
    </select>
  );
}

/** Pole role (popisek nad výběrem), na které lze pustit sloupec přetažený z panelu vpravo. */
function DropCell({ onDropRef, children, className, label, help }: {
  onDropRef: (r: Ref) => void; children: React.ReactNode; className?: string; label: string; help?: string;
}) {
  const [over, setOver] = useState(false);
  const has = (e: React.DragEvent) => Array.from(e.dataTransfer.types).includes(COL_MIME);
  return (
    <div className={"src-lf " + (className ?? "") + (over ? " src-dropover" : "")}
      onDragOver={(e) => { if (has(e)) { e.preventDefault(); e.dataTransfer.dropEffect = "copy"; setOver(true); } }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        setOver(false);
        if (!has(e)) return;
        e.preventDefault();
        try { const r = JSON.parse(e.dataTransfer.getData(COL_MIME)) as Ref; if (r?.source && r?.column) onDropRef(r); } catch { /* cizí data */ }
      }}><span className="lbl">{label}{help && <LabelHelp text={help} />}</span>{children}</div>
  );
}

/** Rozsah [od, do] v jednotkách signálu: uloží se, až jsou vyplněné obě meze (obě prázdné = odhad z dat). */
function Range({ norm, label, onChange }: { norm: number[] | null | undefined; label: string; onChange: (v: number[] | null) => void }) {
  const [v, setV] = useState<[string, string] | null>(null);
  const cur: [string, string] = v ?? (norm ? [String(+norm[0].toPrecision(6)), String(+norm[1].toPrecision(6))] : ["", ""]);
  const done = () => {
    if (!v) return;
    const [a, b] = v;
    if (a.trim() === "" && b.trim() === "") { if (norm) onChange(null); setV(null); return; }
    const x = parse(a), y = parse(b);
    if (x != null && y != null && y > x) { if (!norm || norm[0] !== x || norm[1] !== y) onChange([x, y]); setV(null); }
  };
  const inp = (k: 0 | 1, suffix: string) => (
    <input type="number" step="any" aria-label={`${label} ${suffix}`} title={`${label} ${suffix}`} value={cur[k]} placeholder="auto"
      onChange={(e) => setV(k ? [cur[0], e.target.value] : [e.target.value, cur[1]])} onBlur={done}
      onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }} />);
  return <span className="src-range">{inp(0, "↓")}–{inp(1, "↑")}</span>;
}

function Proposal({ p, sources, apply, close, busy }: {
  p: { kind: "suggest" | "import"; res: Suggestions }; sources: Src; apply: () => void; close: () => void; busy: boolean;
}) {
  const T = useT();
  const done = p.res.loops.filter((l) => l.complete);
  const roles = (l: Suggestions["loops"][number]) => (["pv", "sp", "mv", "pos", "mode"] as const)
    .filter((r) => l.roles[r]).map((r) => `${r.toUpperCase()}: ${l.roles[r]!.column}`).join(" · ");
  return (
    <div className="src-prop" role="region" aria-label={T("src_ui_prop_title")} data-testid="src-proposal">
      <div className="src-prop-h">
        <b>{T(p.kind === "suggest" ? "src_ui_prop_suggest" : "src_ui_prop_import")}</b>
        <span className="small muted">{T("src_ui_prop_summary", { n: p.res.loops.length, c: done.length, u: p.res.unused.length })}</span>
        <span className="src-prop-btns">
          <button type="button" className="btn primary small" disabled={!done.length || busy} onClick={apply} data-testid="src-prop-apply"
            title={T("src_ui_prop_apply_h")}>{T("src_ui_prop_apply", { n: done.length })}</button>
          <button type="button" className="btn small" onClick={close} data-testid="src-prop-close" title={T("src_ui_prop_close_h")}>{T("src_ui_prop_close")}</button>
        </span>
      </div>
      {!p.res.loops.length && <p className="small muted">{T("src_ui_prop_none")}</p>}
      {p.res.loops.length > 0 && (
        <div className="lscroll">
          <table className="ltbl compact" data-testid="src-prop-table">
            <thead><tr><th>Tag</th><th>{T("src_ui_h_roles")}</th><th title={T("src_ui_prop_via_h")}>{T("src_ui_prop_via")}</th><th>{T("src_ui_h_status")}</th></tr></thead>
            <tbody>
              {p.res.loops.map((l, i) => (
                <tr key={i}>
                  <td><b>{l.tag || "–"}</b>{l.description && <div className="small muted">{l.description}</div>}</td>
                  <td className="small">{roles(l)}{l.roles.dv.length > 0 && ` · DV: ${l.roles.dv.map((d) => refLabel(d, sources)).join(", ")}`}</td>
                  <td className="small">{l.via}</td>
                  <td><span className={"ltag " + (l.complete ? "ok" : "err")}>{T(l.complete ? "src_ui_st_complete" : "src_ui_st_incomplete")}</span></td>
                </tr>))}
            </tbody>
          </table>
        </div>)}
      {p.res.warnings.map((w, i) => <div key={i} className="small warn">{w}</div>)}
    </div>
  );
}

export function LoopsCard({ data }: { data: Sources | undefined }) {
  const T = useT();
  const wid = useUi((s) => s.wid);
  const act = useAct();
  const qc = useQueryClient();
  const maps = useMappings().data ?? [];
  const active = useActiveLoop();
  const sources = data?.sources ?? [];
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [prop, setProp] = useState<{ kind: "suggest" | "import"; res: Suggestions; csv?: string } | null>(null);
  const csvIn = useRef<HTMLInputElement>(null);
  const hasData = sources.some((s) => s.loaded && s.columns.length > 0);

  const run = async (f: () => Promise<unknown>) => {
    setErr(null); setBusy(true);
    try { await f(); } catch (e) { setErr(errText(e)); } finally { setBusy(false); }
  };
  const save = (i: number, m: LoopMapping) => run(() => act("PUT", `/loops/${i}/mapping`, mappingBody(m)));
  const setRole = (i: number, role: Role, r: Ref | null) => void save(i, withRole(maps[i], role, r));

  const suggest = () => run(async () => {
    const res = await act<Suggestions>("POST", "/loops/suggest", { apply: false });
    setProp({ kind: "suggest", res });
  });
  const readCsv = (f: File | undefined) => run(async () => {
    if (!f || !wid) return;
    const csv = await f.text();
    setProp({ kind: "import", res: await importCsv(wid, csv, false), csv });
  });
  const apply = () => run(async () => {
    if (!prop || !wid) return;
    if (prop.kind === "suggest") await act("POST", "/loops/suggest", { apply: true });
    else { await importCsv(wid, prop.csv ?? "", true); await qc.invalidateQueries({ queryKey: ["ws", wid] }); }
    setProp(null);
  });

  const casted = new Map<number, number>();                     // podřazená smyčka → nadřazená
  maps.forEach((m, i) => { if (m.cascade_to != null) casted.set(m.cascade_to, i); });
  const names = maps.map((m, i) => loopName(m, i, T("src_ui_loop")));

  return (
    <Card title={T("src_ui_loops")} help="src_ui_loops_h" testid="src-loops"
      right={<>
        <span data-testid="src-loops-count">{T("src_ui_loops_count", { n: maps.length })}</span>
        <span className="src-btns">
          <button type="button" className="btn small" onClick={() => void suggest()} disabled={!hasData || busy} data-testid="src-suggest"
            title={T("src_ui_suggest_h")}>{T("src_ui_suggest")}</button>
          <button type="button" className="btn small" onClick={() => void run(() => act("POST", "/loops", {}))} disabled={!hasData || busy}
            data-testid="src-add-loop" title={T("src_ui_add_loop_h")}>{T("src_ui_add_loop")}</button>
          <button type="button" className="btn small" onClick={() => csvIn.current?.click()} disabled={!hasData || busy} data-testid="src-import"
            title={T("src_ui_import_h")}>{T("src_ui_import")}</button>
          <input ref={csvIn} type="file" accept=".csv,.txt,text/csv" hidden data-testid="src-import-file" aria-label={T("src_ui_import")}
            onChange={(e) => { void readCsv(e.target.files?.[0]); e.target.value = ""; }} />
        </span>
      </>}>
      {prop && <Proposal p={prop} sources={sources} apply={() => void apply()} close={() => setProp(null)} busy={busy} />}
      {err && <div className="err small" role="alert" data-testid="src-loops-err">{err}</div>}
      {maps.length > 0 && (
        <div className="src-lcards" data-testid="src-loops-table">
          {maps.map((m, i) => {
            const st = mappingStatus(m);
            const up = casted.get(i);
            return (
              <div key={i} className={"src-lcard" + (i === active ? " sel" : "")} data-testid={`src-loop-${i}`}>
                <div className="src-lrow1">
                  <div className="src-lf src-tagcell">
                    <span className="lbl">{T("src_ui_h_tagdesc")}<LabelHelp text="h_loop_tag" /></span>
                    <span className="src-tagline">
                      <button type="button" className={"src-act" + (i === active ? " on" : "")} aria-pressed={i === active}
                        aria-label={T("src_ui_activate", { n: names[i] })} title={T("src_ui_activate_h")} data-testid={`src-activate-${i}`}
                        onClick={() => void run(() => act("PUT", "/loops/active", { index: i }))}>{i === active ? "●" : "○"}</button>
                      <Commit value={m.tag} label={T("src_ui_tag")} title={T("h_loop_tag")} className="src-tag" testid={`src-tag-${i}`}
                        onCommit={(v) => void save(i, { ...m, tag: v.trim() })} />
                    </span>
                    <Commit value={m.description} label={T("src_ui_desc")} title={T("src_ui_desc_h")} className="src-desc"
                      onCommit={(v) => void save(i, { ...m, description: v })} />
                  </div>
                  {(["pv", "sp", "mv", "pos"] as const).map((role) => (
                    <DropCell key={role} onDropRef={(r) => setRole(i, role, r)} label={role === "pos" ? T("src_ui_h_pos") : role.toUpperCase()}
                      help={role === "pos" ? "src_ui_pos_h" : undefined}>
                      <ColSelect value={m.roles[role]} sources={sources} label={`${role.toUpperCase()} – ${names[i]}`} title={T(`src_ui_role_${role}_h`)}
                        empty={T("src_ui_unassigned")} testid={`src-${role}-${i}`} onPick={(r) => setRole(i, role, r)} />
                    </DropCell>))}
                  <DropCell onDropRef={(r) => setRole(i, "mode", r)} label={T("src_ui_h_mode")} help="src_ui_mode_h">
                    <ColSelect value={m.roles.mode} sources={sources} label={`${T("src_ui_h_mode")} – ${names[i]}`} title={T("src_ui_mode_h")}
                      empty={T("src_ui_unassigned")} testid={`src-mode-${i}`} onPick={(r) => setRole(i, "mode", r)} />
                  </DropCell>
                </div>
                <div className="src-lrow2">
                  <div className="src-lf src-stat">
                    <span className={"ltag " + st.level} data-testid={`src-status-${i}`} title={T(`src_ui_st_${st.kind}_h`)}>{T(`src_ui_st_${st.kind}`)}</span>
                    {i === active && <span className="small muted">{T("src_ui_active")}</span>}
                  </div>
                  <DropCell onDropRef={(r) => setRole(i, "dv", r)} className="src-dvcell" label={T("src_ui_h_dv")} help="src_ui_dv_h">
                    <span className="src-dvs">
                      {(m.roles.dv ?? []).map((d, j) => (
                        <span className="src-chip" key={refKey(d)} title={refLabel(d, sources)}>{d.column}
                          <button type="button" aria-label={T("src_ui_dv_remove", { n: d.column })} title={T("src_ui_dv_remove", { n: d.column })}
                            onClick={() => void save(i, withoutDv(m, j))}>×</button></span>))}
                      <ColSelect value={null} sources={sources} label={`+ DV – ${names[i]}`} title={T("src_ui_dv_add_h")} empty="+ DV"
                        testid={`src-dv-${i}`} onPick={(r) => setRole(i, "dv", r)} />
                    </span>
                  </DropCell>
                  <div className="src-lf src-ranges">
                    <span className="lbl">{T("src_ui_h_ranges")}<LabelHelp text="src_ui_range_h" /></span>
                    <span className="src-rngs">
                      <Range norm={m.norm_pv} label="PV" onChange={(v) => void save(i, { ...m, norm_pv: v })} /><span className="small muted">PV</span>
                      <Range norm={m.norm_mv} label="MV" onChange={(v) => void save(i, { ...m, norm_mv: v })} /><span className="small muted">MV</span>
                    </span>
                  </div>
                  <div className="src-lf">
                    <span className="lbl">{T("src_ui_cascade")}<LabelHelp text="src_ui_cascade_h" /></span>
                    <select aria-label={T("src_ui_cascade")} title={T("src_ui_cascade_h")} className="src-casc" value={m.cascade_to ?? ""}
                      data-testid={`src-casc-${i}`} onChange={(e) => void save(i, { ...m, cascade_to: e.target.value === "" ? null : +e.target.value })}>
                      <option value="">{T("src_ui_no_cascade")}</option>
                      {maps.map((_, j) => j !== i && <option key={j} value={j}>{T("src_ui_cascade_to", { n: names[j] })}</option>)}
                    </select>
                    {up !== undefined && <span className="ltag ok" title={T("src_ui_cascade_h")}>{T("src_ui_cascade_from", { n: names[up] })}</span>}
                  </div>
                  <button type="button" className="btn small src-x" aria-label={T("src_ui_remove_loop", { n: names[i] })}
                    title={maps.length < 2 ? T("src_ui_remove_last") : T("src_ui_remove_loop_h")} disabled={maps.length < 2 || busy}
                    data-testid={`src-rm-${i}`} onClick={() => void run(() => act("DELETE", `/loops/${i}`))}>×</button>
                </div>
              </div>);
          })}
        </div>)}
      {!maps.length && <p className="small muted" data-testid="src-loops-empty">{T("src_ui_loops_empty")}</p>}
      <p className="small muted src-tip">{T("src_ui_loops_tip")}</p>
    </Card>
  );
}
