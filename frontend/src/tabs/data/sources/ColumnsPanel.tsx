// Data › Zdroje a smyčky, pravý panel: všechny sloupce všech souborů s minigrafem a štítky „smyčka · role“. Sloupec lze
// přetáhnout do buňky role v tabulce smyček, nebo na něj kliknout: nabídka „Přiřadit do smyčky … [PV] [SP] [MV] [DV]
// [Poloha] [Režim]“ (výchozí aktivní smyčka) a „+ Nová smyčka“, která smyčku založí pojmenovanou podle tagu sloupce.
import { useState } from "react";
import { request } from "../../../api/client";
import { useUi } from "../../../store";
import { SideCard } from "../../../components/Ui";
import { useT } from "../../../i18n";
import { errText, type Sources, useAct, useActiveLoop, useMappings, useSparks } from "./api";
import {
  COL_MIME, type LoopMapping, loopName, mappingBody, type Ref, refKey, type Role, sameRef, sparkPath, usageOf, withRole,
} from "./geometry";

export const PICK_ROLES: Role[] = ["pv", "sp", "mv", "dv", "pos", "mode"];

/** Tag smyčky odvozený z názvu sloupce: „LIC101.PV“ → „LIC101“, „FI100_Pritok“ → „FI100“. */
export function tagOf(column: string): string {
  const t = column.split(/[.:/\s]/)[0];
  const m = /^([A-Za-z]{1,6}[-_]?\d{1,6}[A-Za-z]?)/.exec(t);
  return (m ? m[1] : t).slice(0, 40);
}

/** Role, kterou má sloupec ve smyčce (u DV „dv“), nebo null. */
export function roleIn(m: LoopMapping | undefined, r: Ref): Role | null {
  if (!m) return null;
  for (const k of ["pv", "sp", "mv", "pos", "mode"] as const) if (sameRef(m.roles[k], r)) return k;
  return (m.roles.dv ?? []).some((d) => sameRef(d, r)) ? "dv" : null;
}

function Assign({ col, maps, active, onClose }: { col: Ref; maps: LoopMapping[]; active: number; onClose: () => void }) {
  const T = useT();
  const act = useAct();
  const wid = useUi((s) => s.wid);
  const [loop, setLoop] = useState(active);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const m = maps[loop];
  const cur = roleIn(m, col);
  const name = (i: number) => loopName(maps[i], i, T("src_ui_loop"));
  const run = async (f: () => Promise<unknown>) => {
    setErr(null); setBusy(true);
    try { await f(); onClose(); } catch (e) { setErr(errText(e)); } finally { setBusy(false); }
  };
  const assign = (role: Role) => run(async () => {
    if (!m || role === cur) return;
    // jiná role: sloupec se z dosavadní role přesune (DV se jen přidá k ostatním)
    let next = m;
    if (cur && cur !== "dv") next = withRole(next, cur, null);
    if (cur === "dv" && role !== "dv") next = { ...next, roles: { ...next.roles, dv: (next.roles.dv ?? []).filter((d) => !sameRef(d, col)) } };
    await act("PUT", `/loops/${loop}/mapping`, mappingBody(withRole(next, role, col)));
  });
  const create = (role: Role) => run(async () => {
    // nová smyčka: server ji založí s odhadnutými rolemi (smyčka potřebuje PV i MV); zvolená role se přepíše tímto
    // sloupcem a tag se odvodí z jeho názvu – zbylé role se pak doplní v kartě smyčky
    await act("POST", "/loops", {});
    const all = await request<LoopMapping[]>("GET", `/workspaces/${wid}/loops/mappings`);
    const n = all.length - 1;
    const base = { ...all[n], tag: tagOf(col.column), description: "" };
    await act("PUT", `/loops/${n}/mapping`, mappingBody(withRole(base, role, col)));
    await act("PUT", "/loops/active", { index: n });
  });
  const isNew = loop === -1;
  return (
    <div className="src-assign" role="dialog" aria-label={T("src_ui_assign_title", { c: col.column })} data-testid="src-assign"
      onKeyDown={(e) => { if (e.key === "Escape") onClose(); }}>
      <div className="src-assign-h">
        <span>{T("src_ui_assign_to")}</span>
        <select aria-label={T("src_ui_assign_loop")} value={loop} data-testid="src-assign-loop" onChange={(e) => setLoop(+e.target.value)}>
          {maps.map((_, i) => <option key={i} value={i}>{name(i)}</option>)}
          <option value={-1}>{T("src_ui_assign_new")}</option>
        </select>
        <button type="button" className="src-assign-x" aria-label={T("ui_close")} onClick={onClose}>×</button>
      </div>
      <div className="src-assign-roles">
        {PICK_ROLES.map((r) => (
          <button key={r} type="button" disabled={busy} aria-pressed={!isNew && cur === r} data-testid={`src-assign-${r}`}
            title={T(`src_ui_role_${r}_h`)} onClick={() => void (isNew ? create(r) : assign(r))}>{T(`src_ui_role_${r}`)}</button>))}
      </div>
      <div className="small muted">
        {isNew ? T("src_ui_assign_new_h", { t: tagOf(col.column) })
          : cur ? T("src_ui_assign_cur", { r: T(`src_ui_role_${cur}`), n: name(loop) }) : T("src_ui_assign_free", { n: name(loop) })}
      </div>
      {err && <div className="err small" role="alert">{err}</div>}
    </div>
  );
}

export function ColumnsPanel({ data }: { data: Sources | undefined }) {
  const T = useT();
  const maps = useMappings().data ?? [];
  const active = useActiveLoop();
  const sources = data?.sources ?? [];
  const sparks = useSparks(sources);
  const [q, setQ] = useState("");
  const [open, setOpen] = useState<string | null>(null);
  const usage = usageOf(maps);
  const needle = q.trim().toLowerCase();
  const total = sources.reduce((n, s) => n + s.columns.length, 0);
  return (
    <SideCard title={T("src_ui_cols")} help="src_ui_cols_h" testid="src-columns">
      <input type="search" aria-label={T("src_ui_search")} title={T("src_ui_search_h")} placeholder={T("src_ui_search")} value={q}
        onChange={(e) => setQ(e.target.value)} data-testid="src-search" />
      <div className="src-cols" data-testid="src-cols-list">
        {sources.map((s) => {
          const cols = s.columns.filter((c) => !needle || c.toLowerCase().includes(needle));
          if (!cols.length) return null;
          return (
            <details key={s.id} open className="src-colgrp">
              <summary title={s.name}><b>{s.name}</b> <span className="small muted">{T("src_ui_cols_n", { n: cols.length })}</span></summary>
              {cols.map((c) => {
                const k = refKey({ source: s.id, column: c });
                const sp = sparks[s.id]?.[c];
                const uses = usage.get(k) ?? [];
                const isOpen = open === k;
                return (
                  <div key={c}>
                    <button type="button" className={"src-col" + (isOpen ? " open" : "")} draggable data-testid={`src-col-${s.id}-${c}`}
                      aria-expanded={isOpen} title={T("src_ui_col_h")} disabled={!maps.length}
                      onClick={() => setOpen(isOpen ? null : k)}
                      onDragStart={(e) => { e.dataTransfer.setData(COL_MIME, JSON.stringify({ source: s.id, column: c })); e.dataTransfer.effectAllowed = "copy"; }}>
                      <span className="src-col-n" title={c}>{c}</span>
                      <svg viewBox="0 0 60 18" width="60" height="18" aria-hidden="true" className="src-spark">
                        {sp && <path d={sparkPath(sp.t, sp.v)} fill="none" stroke="currentColor" strokeWidth="1.2" vectorEffect="non-scaling-stroke" />}
                      </svg>
                      <span className="src-col-use">
                        {uses.map((u, i) => <span key={i} className="src-use" title={T("src_ui_used_in", { n: loopName(maps[u.loop], u.loop, T("src_ui_loop")), r: u.role.toUpperCase() })}>
                          {loopName(maps[u.loop], u.loop, T("src_ui_loop"))} · {u.role.toUpperCase()}</span>)}
                        {!uses.length && <span className="small muted">{T("src_ui_col_unused")}</span>}
                      </span>
                    </button>
                    {isOpen && <Assign col={{ source: s.id, column: c }} maps={maps} active={active} onClose={() => setOpen(null)} />}
                  </div>);
              })}
            </details>);
        })}
        {!total && <p className="small muted">{T("src_ui_cols_empty")}</p>}
      </div>
      <p className="small muted">{T("src_ui_cols_tip")}</p>
    </SideCard>
  );
}
