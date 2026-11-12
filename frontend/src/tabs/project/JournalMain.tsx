// Projekt › Deník ladění (E10, deska ProjectLog): historie verzí (snímků) smyček se stavy, detail verze, porovnání dvou verzí
// vedle sebe, „Otevřít tento stav“ a „Report z verze“. Snímek je neměnný; mění se jen stav, poznámky a přílohy.
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { ApiError, request } from "../../api/client";
import { Card } from "../../components/Card";
import { Seg } from "../../components/Ui";
import { useT } from "../../i18n";
import { useUi } from "../../store";
import { reportFromSnapshot, useCompare, useJournal, useSnapshot } from "./api";
import { type Snapshot, type SnapshotDetail, STATUSES, useProjSub, useReport } from "./state";

const num = (v: unknown, n = 4) => (typeof v === "number" && Number.isFinite(v) ? String(+v.toPrecision(n)) : v == null ? "–" : String(v));
const when = (s: string) => s.slice(0, 16).replace("T", " ");

export function StatusPill({ status }: { status: string }) {
  const T = useT();
  const cls = status === "verified" ? "ok" : status === "deployed" ? "warn" : status === "rejected" ? "err" : "info";
  return <span className={`vtag ${cls}`} data-testid="jr-pill" data-status={status}>{T("jr_st_" + status)}</span>;
}

/** Krátký popis řádku: název verze, jinak druh záznamu, jinak parametry sady 2. */
function summary(s: Snapshot, T: (k: string) => string) {
  if (s.label) return s.label;
  if (s.kind !== "manual") return T("jr_kind_" + s.kind);
  const g = s.sets["2"] as { gain?: number; ti?: number; td?: number } | undefined;
  return g ? `Gain ${num(g.gain)} · TI ${num(g.ti)} · TD ${num(g.td)}` : "";
}

export function useErr() {
  const T = useT();
  const [err, setErr] = useState<string | null>(null);
  const run = async (fn: () => Promise<void>) => {
    setErr(null);
    try { await fn(); } catch (e) { setErr(e instanceof ApiError ? T(e.message) : String(e)); }
  };
  return { err, run };
}

function History() {
  const T = useT();
  const j = useJournal();
  const { sel, select, loop, setLoop, status, setStatus } = useProjSub();
  const all = j.data?.snapshots ?? [];
  const loops = [...new Set(all.map((s) => s.loop))];
  const rows = all.filter((s) => (!loop || s.loop === loop) && (!status || s.status === status));
  return (
    <Card title={T("jr_history")} help="h_jr_history" testid="jr-history"
      right={<span className="muted small" data-testid="jr-count">{T("jr_count").replace("{n}", String(all.length))}</span>}>
      <div className="row" style={{ gap: 8, flexWrap: "wrap", marginBottom: 8 }}>
        <label className="small" title={T("h_jr_loop")}>{T("jr_loop")}{" "}
          <select value={loop} onChange={(e) => setLoop(e.target.value)} data-testid="jr-f-loop" title={T("h_jr_loop")}>
            <option value="">{T("jr_all")}</option>
            {loops.map((l) => <option key={l} value={l}>{l}</option>)}
          </select></label>
        <label className="small" title={T("h_jr_state")}>{T("jr_state")}{" "}
          <select value={status} onChange={(e) => setStatus(e.target.value)} data-testid="jr-f-status" title={T("h_jr_state")}>
            <option value="">{T("jr_all")}</option>
            {STATUSES.map((s) => <option key={s} value={s}>{T("jr_st_" + s)} · {all.filter((x) => x.status === s).length}</option>)}
          </select></label>
      </div>
      {all.length === 0 && <div className="muted small" data-testid="jr-empty">{T("jr_empty")}</div>}
      {rows.length > 0 && (
        <table className="tbl" data-testid="jr-list">
          <tbody>
            {rows.map((s) => (
              <tr key={s.id} className={"pick" + (s.id === sel ? " sel" : "")} data-testid="jr-row" data-sid={s.id}
                title={T("jr_open_row").replace("{name}", `${s.loop} v${s.v}`)} onClick={() => select(s.id)}>
                <td><b>{s.loop}</b> v{s.v}</td>
                <td className="muted">{when(s.created)} · {s.author}</td>
                <td><StatusPill status={s.status} /></td>
                <td>{summary(s, T)}</td>
              </tr>))}
          </tbody>
        </table>)}
    </Card>
  );
}

function SetsTable({ d }: { d: SnapshotDetail }) {
  const T = useT();
  const res = d.results as Record<string, Record<string, number | null>>;
  const rows: [string, (n: "1" | "2") => unknown][] = [
    ["Gain", (n) => (d.sets[n] as Record<string, unknown>)?.gain], ["TI [s]", (n) => (d.sets[n] as Record<string, unknown>)?.ti],
    ["TD [s]", (n) => (d.sets[n] as Record<string, unknown>)?.td],
    ["Ms", (n) => res[n]?.Ms], ["GM", (n) => res[n]?.GM], ["PM [°]", (n) => res[n]?.PM],
    ["IAE SP", (n) => res[n]?.iae_sp], ["IAE DV", (n) => res[n]?.iae_d], ["Overshoot [%]", (n) => res[n]?.over],
  ];
  return (
    <table className="tbl" data-testid="jr-params">
      <thead><tr><th>{T("jr_param")}</th><th>{T("jr_set1")}</th><th>{T("jr_set2")}</th></tr></thead>
      <tbody>{rows.map(([k, f]) => <tr key={k}><td>{k}</td><td>{num(f("1"))}</td><td><b>{num(f("2"))}</b></td></tr>)}</tbody>
    </table>
  );
}

function Detail({ sid }: { sid: string }) {
  const T = useT();
  const wid = useUi((s) => s.wid);
  const qc = useQueryClient();
  const q = useSnapshot(sid);
  const all = useJournal().data?.snapshots ?? [];
  const { setCmp, cmp, setSub, lang: rlang } = useProjSub();
  const uiLang = useUi((s) => s.lang);
  const { err, run } = useErr();
  const [msg, setMsg] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const d = q.data;
  if (!d) return <Card title={T("jr_detail")} help="h_jr_detail" testid="jr-detail"><div className="muted small">{T("jr_pick")}</div></Card>;
  const refresh = () => qc.invalidateQueries({ queryKey: ["ws", wid] });
  const content = d.content as Record<string, Record<string, unknown> | null>;
  const src = ((content.data?.sources ?? []) as Record<string, unknown>[]);

  const setStatus = (status: string) => run(async () => { await request("PATCH", `/workspaces/${wid}/journal/${sid}`, { status }); await refresh(); });
  const restore = () => run(async () => {
    const r = await request<{ autosave: Snapshot; data_changed: string[] }>("POST", `/workspaces/${wid}/journal/${sid}/restore`);
    await refresh();
    setMsg(T("jr_restored").replace("{name}", `${r.autosave.loop} v${r.autosave.v}`)
      + (r.data_changed.length ? " " + T("jr_data_changed").replace("{files}", r.data_changed.join(", ")) : ""));
  });
  const report = () => run(async () => {
    useReport.getState().set({ busy: true, err: null });
    try {
      const html = await reportFromSnapshot(wid ?? "", sid, { meta: {}, sections: ["model", "tuning", "data", "controller", "scenario", "field", "history"], chart_mode: "inline" }, rlang ?? uiLang);
      useReport.getState().set({ html, busy: false });
      setSub("report");
    } catch (e) { useReport.getState().set({ busy: false, html: null, err: e instanceof ApiError ? T(e.message) : String(e) }); }
  });
  const addNote = () => run(async () => { await request("PATCH", `/workspaces/${wid}/journal/${sid}`, { note }); setNote(""); await refresh(); });
  const attach = (f: File | undefined) => run(async () => {
    if (!f) return;
    const b64 = btoa(Array.from(new Uint8Array(await f.arrayBuffer()), (c) => String.fromCharCode(c)).join(""));
    await request("POST", `/workspaces/${wid}/journal/${sid}/attachments`, { name: f.name, data_b64: b64, mime: f.type || "application/octet-stream" });
    await refresh();
  });
  const download = (aid: string, name: string) => run(async () => {
    const a = await request<{ data_b64: string; mime: string }>("GET", `/workspaces/${wid}/journal/${sid}/attachments/${aid}`);
    const url = URL.createObjectURL(new Blob([Uint8Array.from(atob(a.data_b64), (c) => c.charCodeAt(0))], { type: a.mime }));
    const el = document.createElement("a");
    el.href = url; el.download = name; document.body.appendChild(el); el.click(); el.remove();
    setTimeout(() => URL.revokeObjectURL(url), 10000);
  });
  const model = d.model as { code?: string; names?: string[]; params?: number[]; fit?: number | null } | null;
  const ctl = d.controller as { name?: string; version?: unknown } | null;
  return (
    <Card title={<>{d.loop} · v{d.v} <StatusPill status={d.status} /></>} help="h_jr_detail" testid="jr-detail"
      right={<>
        <button className="btn primary" onClick={() => void restore()} title={T("h_jr_restore")} data-testid="jr-restore">{T("jr_restore")}</button>
        <label className="small" title={T("h_jr_compare")}>
          <select value={cmp ?? ""} onChange={(e) => setCmp(e.target.value || null)} data-testid="jr-cmp-sel" title={T("h_jr_compare")} aria-label={T("jr_compare")}>
            <option value="">{T("jr_compare")}</option>
            {all.filter((s) => s.id !== sid).map((s) => <option key={s.id} value={s.id}>{s.loop} v{s.v}</option>)}
          </select></label>
        <button className="btn" onClick={() => void report()} title={T("h_jr_report")} data-testid="jr-report">{T("jr_report")}</button>
      </>}>
      {err && <div className="err small" role="alert" data-testid="jr-err">{err}</div>}
      {msg && <div className="ok small" role="status" data-testid="jr-msg">{msg}</div>}
      <div className="row" style={{ gap: 8, alignItems: "center", marginBottom: 8 }}>
        <span className="small">{T("jr_set_state")}</span>
        <Seg value={d.status as (typeof STATUSES)[number]} options={STATUSES} label={T("jr_set_state")} testid="jr-status" small help="h_jr_set_state"
          fmt={(v) => T("jr_st_" + v)} onChange={(v) => void setStatus(v)} />
      </div>
      <h3 className="small">{T("jr_h_header")}</h3>
      <table className="tbl" data-testid="jr-header"><tbody>
        <tr><td>{T("jr_created")}</td><td>{when(d.created)} · {d.author}{d.label ? ` · ${d.label}` : ""}</td></tr>
        <tr><td>{T("jr_app")}</td><td>PID Tools {d.app_version}</td></tr>
        <tr><td>{T("jr_profile")}</td><td>{ctl?.name ?? "–"} · {T("rp_c_version")} {num(ctl?.version)}</td></tr>
        <tr><td>{T("jr_fingerprint")}</td><td><code>{d.sha256.slice(0, 16)}…</code>{" "}
          <span className={d.verified ? "ok small" : "err small"} data-testid="jr-verified" data-ok={String(d.verified)}>{d.verified ? T("jr_intact") : T("jr_tampered")}</span></td></tr>
      </tbody></table>
      {d.live && <div className="small" data-testid="jr-live">{T("jr_live_kpi")
        .replace("{i1}", num((d.live as { kpi?: Record<string, { iae?: number }> }).kpi?.["1"]?.iae)).replace("{i2}", num((d.live as { kpi?: Record<string, { iae?: number }> }).kpi?.["2"]?.iae))}</div>}
      <h3 className="small">{T("jr_h_params")}</h3>
      <SetsTable d={d} />
      <h3 className="small">{T("jr_h_model")}</h3>
      {model ? <div className="small" data-testid="jr-model">{model.code}: {(model.names ?? []).map((n, i) => `${n} = ${num(model.params?.[i])}`).join(", ")}
        {model.fit != null && ` · FIT ${num(model.fit, 3)} %`}</div> : <div className="muted small">{T("jr_no_model")}</div>}
      <h3 className="small">{T("jr_h_data")}</h3>
      <table className="tbl"><tbody>
        {src.map((x) => <tr key={String(x.id)}><td>{String(x.name)}</td><td>{String(x.rows)}</td><td><code>{String(x.sha256).slice(0, 12)}…</code></td></tr>)}
      </tbody></table>
      <h3 className="small">{T("jr_h_hist")}</h3>
      <div className="small" data-testid="jr-hist">{d.history.map((h, i) => (
        <div key={i}>{when(h.when)} → {T("jr_st_" + h.status)} · {h.author}{h.note ? ` · ${h.note}` : ""}</div>))}</div>
      <h3 className="small">{T("jr_h_notes")}</h3>
      {d.notes.length === 0 && <div className="muted small">{T("jr_no_notes")}</div>}
      {d.notes.map((n, i) => <div key={i} className="small" data-testid="jr-note"><span className="muted">{when(n.when)} · {n.author}</span> {n.text}</div>)}
      <div className="row" style={{ gap: 6, marginTop: 6 }}>
        <input value={note} onChange={(e) => setNote(e.target.value)} placeholder={T("jr_note_ph")} aria-label={T("jr_note")} title={T("h_jr_note_add")}
          data-testid="jr-note-in" style={{ flex: 1 }} />
        <button className="btn" disabled={!note.trim()} onClick={() => void addNote()} title={T("h_jr_note_add")} data-testid="jr-note-add">{T("jr_note_add")}</button>
      </div>
      <h3 className="small">{T("jr_h_att")}</h3>
      {d.attachments.length === 0 && <div className="muted small">{T("jr_no_att")}</div>}
      {d.attachments.map((a) => (
        <div key={a.id} className="small" data-testid="jr-att">
          <button className="btn" onClick={() => void download(a.id, a.name)} title={T("jr_att_dl").replace("{name}", a.name)}>{a.name}</button>{" "}
          <span className="muted">{num(a.size / 1024, 3)} kB</span>
        </div>))}
      <label className="btn" title={T("h_jr_att_add")} style={{ marginTop: 6 }}>
        {T("jr_att_add")}
        <input type="file" hidden data-testid="jr-att-in" onChange={(e) => { void attach(e.target.files?.[0]); e.target.value = ""; }} />
      </label>
    </Card>
  );
}

function CompareCard({ a, b }: { a: string; b: string }) {
  const T = useT();
  const q = useCompare(a, b);
  const setCmp = useProjSub((s) => s.setCmp);
  const c = q.data;
  if (!c) return null;
  const nameOf = (s: Snapshot) => `${s.loop} v${s.v}`;
  const secs = [...new Set(c.rows.map((r) => r.section))];
  return (
    <Card title={T("jr_cmp_title").replace("{a}", nameOf(c.a)).replace("{b}", nameOf(c.b))} help="h_jr_cmp" testid="jr-compare"
      right={<button className="btn" onClick={() => setCmp(null)} data-testid="jr-cmp-close" title={T("jr_cmp_close")}>{T("jr_cmp_close")}</button>}>
      {c.rows.length === 0 && <div className="muted small">{T("jr_cmp_same")}</div>}
      {c.rows.length > 0 && (
        <table className="tbl">
          <thead><tr><th>{T("jr_cmp_item")}</th><th>{nameOf(c.a)}</th><th>{nameOf(c.b)}</th></tr></thead>
          <tbody>
            {secs.map((sec) => (
              [<tr key={sec}><th colSpan={3}>{T("jr_sec_" + sec)}</th></tr>,
                ...c.rows.filter((r) => r.section === sec).map((r) => (
                  <tr key={sec + r.key} data-testid="jr-diff"><td>{r.key}</td><td>{num(r.a)}</td><td><b>{num(r.b)}</b></td></tr>))]))}
          </tbody>
        </table>)}
    </Card>
  );
}

export function JournalMain() {
  const sel = useProjSub((s) => s.sel);
  const cmp = useProjSub((s) => s.cmp);
  return (
    <div className="stack" data-testid="journal">
      <History />
      {sel && cmp && <CompareCard a={sel} b={cmp} />}
      {sel && <Detail sid={sel} />}
    </div>
  );
}
