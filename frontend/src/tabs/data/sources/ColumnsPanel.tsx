// Data › Zdroje a smyčky, pravý panel: všechny sloupce všech souborů s minigrafem a štítkem „smyčka · role“. Sloupec lze
// přetáhnout do buňky role v tabulce smyček; pro klávesnici je u každého sloupce výběr „Použít jako…“ (aktivní smyčka).
import { useState } from "react";
import { SideCard } from "../../../components/Ui";
import { useT } from "../../../i18n";
import { errText, type Sources, useAct, useActiveLoop, useMappings, useSparks } from "./api";
import { COL_MIME, loopName, mappingBody, refKey, type Role, sparkPath, usageOf, withRole } from "./geometry";

const PICK_ROLES: Role[] = ["pv", "sp", "mv", "pos", "mode", "dv"];

export function ColumnsPanel({ data }: { data: Sources | undefined }) {
  const T = useT();
  const act = useAct();
  const maps = useMappings().data ?? [];
  const active = useActiveLoop();
  const sources = data?.sources ?? [];
  const sparks = useSparks(sources);
  const [q, setQ] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const usage = usageOf(maps);
  const needle = q.trim().toLowerCase();
  const assign = async (source: string, column: string, role: Role) => {
    const m = maps[active];
    if (!m) return;
    setErr(null);
    try { await act("PUT", `/loops/${active}/mapping`, mappingBody(withRole(m, role, { source, column }))); } catch (e) { setErr(errText(e)); }
  };
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
                return (
                  <div className="src-col" key={c} draggable data-testid={`src-col-${s.id}-${c}`}
                    onDragStart={(e) => { e.dataTransfer.setData(COL_MIME, JSON.stringify({ source: s.id, column: c })); e.dataTransfer.effectAllowed = "copy"; }}>
                    <span className="src-col-n" title={c}>{c}</span>
                    <svg viewBox="0 0 60 18" width="60" height="18" aria-hidden="true" className="src-spark">
                      {sp && <path d={sparkPath(sp.t, sp.v)} fill="none" stroke="currentColor" strokeWidth="1.2" vectorEffect="non-scaling-stroke" />}
                    </svg>
                    <span className="src-col-use">
                      {uses.map((u, i) => <span key={i} className="src-use" title={T("src_ui_used_in", { n: loopName(maps[u.loop], u.loop, T("src_ui_loop")), r: u.role.toUpperCase() })}>
                        {loopName(maps[u.loop], u.loop, T("src_ui_loop"))} · {u.role.toUpperCase()}</span>)}
                    </span>
                    <select className="src-col-pick" aria-label={T("src_ui_use_as_for", { c: c })} title={T("src_ui_use_as_h")} value=""
                      onChange={(e) => { if (e.target.value) void assign(s.id, c, e.target.value as Role); }}>
                      <option value="">{T("src_ui_use_as")}</option>
                      {PICK_ROLES.map((r) => <option key={r} value={r}>{r.toUpperCase()}</option>)}
                    </select>
                  </div>);
              })}
            </details>);
        })}
        {!total && <p className="small muted">{T("src_ui_cols_empty")}</p>}
      </div>
      {err && <div className="err small" role="alert">{err}</div>}
      <p className="small muted">{T("src_ui_cols_tip")}</p>
    </SideCard>
  );
}
