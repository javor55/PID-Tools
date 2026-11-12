// Start (návrh Start): obrazovka bez projektu – načtení dat (výběr, přetažení, OPC UA), otevření projektu, nedávné projekty,
// ukázková data, „Jak začít“ a nabídka obnovy záchranné kopie po pádu.
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { ApiError, rawRequest, request } from "../api/client";
import { uploadFile } from "../data";
import { useT } from "../i18n";
import { OpcButton } from "../tabs/OpcDialog";
import { useSources } from "../tabs/data/sources/api";
import { FilesCard } from "../tabs/data/sources/FilesCard";
import { useUi } from "../store";
import { type RecentItem, useRecent, useRecovery } from "./project";
import "./start.css";

const ACCEPT = ".csv,.txt,.xlsx,.xls";
const STEPS = ["data", "model", "tuning", "apc", "live"] as const;

const fmtWhen = (epoch: number, lang: string) =>
  new Date(epoch * 1000).toLocaleString(lang === "cs" ? "cs-CZ" : "en-GB", { day: "numeric", month: "numeric", hour: "2-digit", minute: "2-digit" });

function Recovery() {
  const T = useT();
  const lang = useUi((s) => s.lang);
  const wid = useUi((s) => s.wid);
  const qc = useQueryClient();
  const rec = useRecovery().data;
  const [err, setErr] = useState("");
  if (!rec?.available) return null;
  const restore = async () => {
    setErr("");
    try {
      await request("POST", `/workspaces/${wid}/autosave/restore`);
      await qc.invalidateQueries({ queryKey: ["ws", wid] });
    } catch (e) { setErr(e instanceof ApiError ? e.message : String(e)); }
  };
  const discard = async () => { await request("DELETE", "/autosave"); await qc.invalidateQueries({ queryKey: ["recovery"] }); };
  return (
    <div className="st-recover" role="status" data-testid="start-recovery">
      <div><b>{T("app_rec_title")}</b>
        <span>{T("app_rec_text", { name: rec.name || "–", n: rec.loops, t: rec.at ? fmtWhen(rec.at, lang) : "" })}</span></div>
      <button type="button" className="btn primary" data-testid="start-restore" title={T("app_rec_restore_h")} onClick={() => void restore()}>{T("app_rec_restore")}</button>
      <button type="button" className="btn" data-testid="start-discard" title={T("app_rec_discard_h")} onClick={() => void discard()}>{T("app_rec_discard")}</button>
      {err && <span className="err small" role="alert">{err}</span>}
    </div>
  );
}

function Recent({ open }: { open: (r: RecentItem) => void }) {
  const T = useT();
  const lang = useUi((s) => s.lang);
  const qc = useQueryClient();
  const items = useRecent().data ?? [];
  const drop = async (id: string) => { await request("DELETE", `/recent/${id}`).catch(() => undefined); await qc.invalidateQueries({ queryKey: ["recent"] }); };
  return (
    <section className="card st-card" data-testid="start-recent">
      <h2>{T("app_start_recent")}</h2>
      {items.length === 0 && <p className="rg-note">{T("app_start_recent_none")}</p>}
      <ul className="st-recent">
        {items.map((r) => (
          <li key={r.id} data-testid="start-recent-item">
            <button type="button" className="st-recent-open" disabled={!r.snapshot} title={r.snapshot ? T("app_start_recent_open_h") : T("app_start_recent_nocopy")}
              onClick={() => open(r)}><b>{r.name}</b><span>{T("app_start_recent_meta", { n: r.loops, t: fmtWhen(r.at, lang) })}</span></button>
            <button type="button" className="btn small" title={T("app_start_recent_remove_h")} onClick={() => void drop(r.id)}>{T("app_start_recent_remove")}</button>
          </li>))}
      </ul>
    </section>
  );
}

/**
 * `compact` = Data › Zdroje a smyčky bez dat: místo vlastní plochy pro soubory zůstává karta Soubory (více souborů najednou,
 * OPC UA), Start k ní přidává otevření projektu, ukázky, obnovu, nedávné projekty a kroky.
 */
export function StartScreen({ compact = false }: { compact?: boolean }) {
  const T = useT();
  const wid = useUi((s) => s.wid);
  const qc = useQueryClient();
  const [err, setErr] = useState("");
  const [over, setOver] = useState(false);
  const sources = useSources();
  const run = async (f: () => Promise<unknown>) => {
    setErr("");
    try { await f(); await qc.invalidateQueries({ queryKey: ["ws", wid] }); await qc.invalidateQueries({ queryKey: ["recent"] }); }
    catch (e) { setErr(e instanceof ApiError ? T(e.message) : String(e)); }
  };
  const load = (f: File | undefined) => { if (f && wid) void run(() => uploadFile(wid, f)); };
  const openProject = (f: File | undefined) => { if (f && wid) void run(async () => rawRequest("PUT", `/workspaces/${wid}/project`, await f.arrayBuffer())); };
  const post = (path: string) => void run(() => request("POST", `/workspaces/${wid}${path}`));
  return (
    <div className="start" data-testid="start-screen">
      <div className="st-main" data-testid="no-data">
        <h1>{T("app_start_title")}</h1>
        <Recovery />
        {compact && (
          <div className="st-btns st-row">
            <label className="btn" title={T("app_start_open_h")}>
              {T("app_start_open")}
              <input type="file" accept=".pidproj,.json" hidden data-testid="start-open-file" aria-label={T("app_start_open")}
                onChange={(e) => { openProject(e.target.files?.[0]); e.target.value = ""; }} />
            </label>
            <button type="button" className="btn" data-testid="start-demo" title={T("app_start_demo_h")} onClick={() => post("/data/demo")}>{T("app_start_demo")}</button>
            <button type="button" className="btn" data-testid="start-example-ff" title={T("app_start_ff_h")} onClick={() => post("/data/example?name=ff")}>{T("app_start_ff")}</button>
          </div>)}
        {compact && err && <div className="err small" role="alert">{err}</div>}
        {compact && <div className="src-main" data-testid="sources-main"><FilesCard data={sources.data} /></div>}
        {!compact && (
        <div className={"st-drop" + (over ? " over" : "")} data-testid="drop-zone"
          onDragOver={(e) => { if (e.dataTransfer.types.includes("Files")) { e.preventDefault(); setOver(true); } }}
          onDragLeave={() => setOver(false)}
          onDrop={(e) => { e.preventDefault(); setOver(false); load(e.dataTransfer.files[0]); }}>
          <h2>⇪ {T("app_start_drop")}</h2>
          <p>{T("app_start_drop_h")}</p>
          <div className="st-btns">
            <label className="btn primary" title={T("app_start_pick_h")}>
              {T("app_start_pick")}
              <input type="file" accept={ACCEPT} hidden data-testid="load-file" aria-label={T("app_start_pick")}
                onChange={(e) => { load(e.target.files?.[0]); e.target.value = ""; }} />
            </label>
            <OpcButton />
            <label className="btn" title={T("app_start_open_h")}>
              {T("app_start_open")}
              <input type="file" accept=".pidproj,.json" hidden data-testid="start-open-file" aria-label={T("app_start_open")}
                onChange={(e) => { openProject(e.target.files?.[0]); e.target.value = ""; }} />
            </label>
          </div>
          <div className="st-btns">
            <button type="button" className="btn" data-testid="start-demo" title={T("app_start_demo_h")} onClick={() => post("/data/demo")}>{T("app_start_demo")}</button>
            <button type="button" className="btn" data-testid="start-example-ff" title={T("app_start_ff_h")} onClick={() => post("/data/example?name=ff")}>{T("app_start_ff")}</button>
          </div>
          {err && <div className="err small" role="alert">{err}</div>}
        </div>
        )}
        <p className="rg-note">{T("app_start_tip")}</p>
      </div>
      <aside className="st-side">
        <Recent open={(r) => void run(() => request("POST", `/workspaces/${wid}/recent/${r.id}/open`))} />
        <section className="card st-card" data-testid="start-steps">
          <h2>{T("app_start_steps")}</h2>
          <ol className="st-steps">
            {STEPS.map((k, i) => <li key={k}><span className="st-n">{i + 1}</span><span><b>{T(`app_start_step_${k}`)}</b> – {T(`app_start_step_${k}_d`)}</span></li>)}
          </ol>
        </section>
      </aside>
    </div>
  );
}
