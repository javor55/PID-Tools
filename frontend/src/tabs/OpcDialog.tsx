// Dialog OPC UA (jen čtení): server, procházení a hledání uzlů, výběr PV / MV / SP / poruch, časový rozsah a načtení
// historie jako úloha (/opc/history). Po úspěchu jsou v prostoru nová data; vybrané role se nastaví jako sloupce.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Fragment, useEffect, useRef, useState } from "react";
import { ApiError, request } from "../api/client";
import type { components } from "../api/schema";
import { useJobRunner } from "../jobs";
import { useT } from "../i18n";
import { useUi } from "../store";

type OpcNode = components["schemas"]["Node"];
type Pick = { path: string; role: string };

const ROLES = ["", "PV", "MV", "SP", "DV"];
const KEY_URL = "pid.opc.url";

function stored(k: string, d: string): string {
  try { return localStorage.getItem(k) ?? d; } catch { return d; }
}

function localInput(d: Date): string {
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
}

export function useOpcAvailable() {
  return useQuery({ queryKey: ["opc-available"], queryFn: () => request<boolean>("GET", "/opc/available"), staleTime: Infinity });
}

/** Tlačítko v panelu zdroje dat; bez balíčku asyncua je vypnuté. */
export function OpcButton() {
  const T = useT();
  const avail = useOpcAvailable();
  const [open, setOpen] = useState(false);
  return (
    <>
      <button className="btn" disabled={avail.data !== true} title={avail.data === false ? T("opc_missing") : undefined}
        onClick={() => setOpen(true)} data-testid="opc-open">{T("opc_menu")}</button>
      {open && <OpcDialog onClose={() => setOpen(false)} />}
    </>
  );
}

function NodeList({ nodes, depth, kids, openIds, onToggle, onPick }: {
  nodes: OpcNode[]; depth: number; kids: Record<string, OpcNode[]>; openIds: Set<string>;
  onToggle: (n: OpcNode) => void; onPick: (n: OpcNode) => void;
}) {
  return (
    <>
      {nodes.map((n) => (
        <Fragment key={n.node_id}>
          <li style={{ paddingLeft: depth * 14 }} data-testid={n.is_var ? "opc-var" : "opc-folder"}>
            {n.is_var
              ? <button className="link" onDoubleClick={() => onPick(n)} onClick={() => onPick(n)}>📈 {n.name}</button>
              : <button className="link" onClick={() => onToggle(n)}>{openIds.has(n.node_id) ? "📂" : "📁"} {n.name}</button>}
          </li>
          {openIds.has(n.node_id) && kids[n.node_id] && (
            <NodeList nodes={kids[n.node_id]} depth={depth + 1} kids={kids} openIds={openIds} onToggle={onToggle} onPick={onPick} />)}
        </Fragment>))}
    </>
  );
}

export function OpcDialog({ onClose }: { onClose: () => void }) {
  const T = useT();
  const wid = useUi((s) => s.wid);
  const qc = useQueryClient();
  const run = useJobRunner();
  const ref = useRef<HTMLDialogElement>(null);
  const [url, setUrl] = useState(stored(KEY_URL, "opc.tcp://localhost:4840"));
  const [user, setUser] = useState("");
  const [pw, setPw] = useState("");
  const [text, setText] = useState("");
  const [kids, setKids] = useState<Record<string, OpcNode[]>>({});
  const [openIds, setOpenIds] = useState<Set<string>>(new Set());
  const [found, setFound] = useState<OpcNode[] | null>(null);
  const [connected, setConnected] = useState(false);
  const [sel, setSel] = useState<Record<string, Pick>>({});
  const [from, setFrom] = useState(() => localInput(new Date(Date.now() - 8 * 3600e3)));
  const [to, setTo] = useState(() => localInput(new Date()));
  const [msg, setMsg] = useState<{ err: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => { ref.current?.showModal(); }, []);

  const server = { url: url.trim(), user: user.trim() || null, password: pw || null };
  const fail = (e: unknown) => setMsg({ err: true, text: T("opc_failed", { e: e instanceof ApiError ? e.message : String(e) }) });

  async function connect() {
    setMsg(null);
    try {
      const top = await request<OpcNode[]>("POST", "/opc/browse", server);
      try { localStorage.setItem(KEY_URL, server.url); } catch { /* bez úložiště */ }
      setKids({ "": top }); setOpenIds(new Set()); setFound(null); setConnected(true);
      setMsg({ err: false, text: T("opc_connected") });
    } catch (e) { setConnected(false); fail(e); }
  }
  async function toggle(n: OpcNode) {
    const o = new Set(openIds);
    if (o.has(n.node_id)) o.delete(n.node_id);
    else {
      o.add(n.node_id);
      if (!kids[n.node_id]) {
        try {
          const ch = await request<OpcNode[]>("POST", "/opc/browse", { ...server, node_id: n.node_id, parent_path: n.path });
          setKids((k) => ({ ...k, [n.node_id]: ch }));
        } catch (e) { fail(e); return; }
      }
    }
    setOpenIds(o);
  }
  async function find() {
    if (!text.trim()) { setFound(null); return; }
    try {
      const r = await request<OpcNode[]>("POST", "/opc/find", { ...server, text: text.trim() });
      setFound(r.filter((n) => n.is_var));
    } catch (e) { fail(e); }
  }
  const pick = (n: OpcNode) => { if (n.is_var) setSel((s) => (n.node_id in s ? s : { ...s, [n.node_id]: { path: n.path, role: "" } })); };

  async function load() {
    const ids = Object.keys(sel);
    if (!ids.length || !wid) return;
    setBusy(true); setMsg(null);
    try {
      const nodes = Object.fromEntries(ids.map((i) => [i, sel[i].path]));
      const j = await run("/opc/history", { ...server, nodes, start: new Date(from).toISOString(), end: new Date(to).toISOString() },
        T("opc_history"));
      if (j.state !== "done") { setMsg({ err: true, text: T(j.error ?? j.state) }); return; }
      const tag = (role: string) => ids.map((i) => sel[i]).filter((p) => p.role === role).map((p) => p.path);
      const [pv, mv] = [tag("PV")[0], tag("MV")[0]];
      if (pv && mv) {
        await request("PUT", `/workspaces/${wid}/columns`, { pv, mv, sp: tag("SP")[0] ?? null, dists: tag("DV"), pos: null });
        await qc.invalidateQueries({ queryKey: ["ws", wid] });
      }
      onClose();
    } catch (e) { fail(e); } finally { setBusy(false); }
  }

  return (
    <dialog ref={ref} className="opc" onClose={onClose} data-testid="opc-dialog">
      <div className="stack">
        <h3>{T("opc_title")}</h3>
        <div className="muted small">{T("opc_intro")}</div>
        <div className="opc-cols">
          <label className="field wide"><span>{T("opc_url")}</span>
            <input type="text" value={url} onChange={(e) => setUrl(e.target.value)} data-testid="opc-url" /></label>
          <div className="row">
            <label className="field wide" style={{ flex: 1 }}><span>{T("opc_user")}</span>
              <input type="text" value={user} onChange={(e) => setUser(e.target.value)} data-testid="opc-user" /></label>
            <label className="field wide" style={{ flex: 1 }}><span>{T("opc_pw")}</span>
              <input type="password" value={pw} onChange={(e) => setPw(e.target.value)} data-testid="opc-pw" /></label>
          </div>
        </div>
        <div className="row">
          <button className="btn primary" onClick={() => void connect()} data-testid="opc-connect">{T("opc_connect")}</button>
          {msg && <span className={msg.err ? "err small" : "ok small"} role={msg.err ? "alert" : "status"} data-testid="opc-msg">{msg.text}</span>}
        </div>
        <div className="opc-cols">
          <div className="stack">
            <div className="row">
              <input type="text" value={text} placeholder={T("opc_search_ph")} data-testid="opc-search"
                onChange={(e) => setText(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") void find(); }} />
              <button className="btn" disabled={!connected} onClick={() => void find()} data-testid="opc-find">{T("opc_find")}</button>
            </div>
            <ul className="opc-list" data-testid="opc-tree">
              {found
                ? (found.length ? found.map((n) => (
                  <li key={n.node_id} data-testid="opc-var"><button className="link" onClick={() => pick(n)}>📈 {n.path}</button></li>))
                  : <li className="muted">{T("ui_opc_none")}</li>)
                : <NodeList nodes={kids[""] ?? []} depth={0} kids={kids} openIds={openIds} onToggle={(n) => void toggle(n)} onPick={pick} />}
            </ul>
          </div>
          <div className="stack">
            <div className="small">{T("opc_selected")} · {T("ui_opc_n_sel", { n: Object.keys(sel).length })}</div>
            <ul className="opc-list" data-testid="opc-selected">
              {Object.entries(sel).map(([id, p], i) => (
                <li key={id}>
                  <select value={p.role} aria-label={T("ui_opc_role")} data-testid={`opc-role-${i}`}
                    onChange={(e) => setSel((s) => ({ ...s, [id]: { ...p, role: e.target.value } }))}>
                    {ROLES.map((r) => <option key={r} value={r}>{r === "" ? "—" : r === "SP" ? T("col_sp") : r}</option>)}
                  </select>
                  <span style={{ flex: 1 }} title={id}>{p.path}</span>
                  <button className="btn" onClick={() => setSel((s) => Object.fromEntries(Object.entries(s).filter(([k]) => k !== id)))}
                    data-testid={`opc-remove-${i}`}>{T("opc_remove")}</button>
                </li>))}
            </ul>
          </div>
        </div>
        <div className="opc-cols">
          <label className="field wide"><span>{T("ui_opc_from")}</span>
            <input type="datetime-local" value={from} onChange={(e) => setFrom(e.target.value)} data-testid="opc-from" /></label>
          <label className="field wide"><span>{T("ui_opc_to")}</span>
            <input type="datetime-local" value={to} onChange={(e) => setTo(e.target.value)} data-testid="opc-to" /></label>
        </div>
        <div className="row">
          <button className="btn primary" disabled={!connected || busy || !Object.keys(sel).length} onClick={() => void load()}
            data-testid="opc-history">{T("opc_history")}</button>
          <button className="btn" onClick={() => ref.current?.close()} data-testid="opc-close">{T("ui_close")}</button>
        </div>
      </div>
    </dialog>
  );
}
