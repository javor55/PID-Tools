// Záložka Projekt a report (M21): uložení / otevření projektu (soubor), údaje a volby protokolu, náhled protokolu
// (HTML v izolovaném iframe) a jeho stažení.
import { useQueryClient, type QueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { create } from "zustand";
import { ApiError, bytes, rawRequest } from "../api/client";
import { SelectSetting, TextSetting } from "../components/Fields";
import { useSettings } from "../data";
import { useT } from "../i18n";
import { useUi } from "../store";

const SECTIONS = ["model", "tuning", "response", "apc", "signoff"] as const;
const STATUSES = ["draft", "deployed", "verified"] as const;

interface ReportState { html: string | null; busy: boolean; err: string | null; set: (p: Partial<ReportState>) => void }
const useReport = create<ReportState>((set) => ({ html: null, busy: false, err: null, set: (p) => set(p) }));

/** Přípona souborů projektu: výchozí `.pidproj`, otevřít jde i starší `.json` (obsah je stejný JSON). */
export const PROJECT_EXT = ".pidproj";
export const PROJECT_ACCEPT = `${PROJECT_EXT},.json,application/json`;
const PENDING_EVENT = "pidtools:pending-open";      // okno desktopu ho vyvolá po uložení souboru k otevření

interface ProjMsg { err: boolean; text: string }
const useProjMsg = create<{ msg: ProjMsg | null; set: (m: ProjMsg | null) => void }>((set) => ({ msg: null, set: (msg) => set({ msg }) }));

/** Nahraje projekt (bajty souboru) do prostoru a zneplatní jeho dotazy. */
async function openProject(wid: string, raw: ArrayBuffer, qc: QueryClient, T: (k: string) => string) {
  useProjMsg.getState().set(null);
  try {
    await rawRequest("PUT", `/workspaces/${wid}/project`, raw);
    await qc.invalidateQueries({ queryKey: ["ws", wid] });
    useReport.getState().set({ html: null, err: null });
    useProjMsg.getState().set({ err: false, text: T("ui_proj_opened") });
  } catch (e) {
    useProjMsg.getState().set({ err: true, text: e instanceof ApiError ? T(e.message) : String(e) });
  }
}

/** Projekt otevřený poklepem na soubor v okně desktopu: při startu a po události od okna se vyzvedne z `/pending-open`. */
export function usePendingOpen() {
  const T = useT();
  const wid = useUi((s) => s.wid);
  const qc = useQueryClient();
  useEffect(() => {
    if (!wid) return;
    let busy = false;
    const check = async () => {
      if (busy) return;
      busy = true;
      try {
        const raw = await bytes("GET", "/pending-open");
        if (raw.byteLength > 0) { useUi.getState().setTab("project"); await openProject(wid, raw, qc, T); }
      } catch { /* bez čekajícího souboru / nedostupné (týmový režim) */ } finally { busy = false; }
    };
    void check();
    window.addEventListener(PENDING_EVENT, check);
    return () => window.removeEventListener(PENDING_EVENT, check);
  }, [wid, qc, T]);
}

function saveAs(name: string, data: BlobPart, type: string) {
  const a = document.createElement("a");
  const url = URL.createObjectURL(new Blob([data], { type }));
  a.href = url; a.download = name;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10000);
}

function useBaseName() {
  const tag = String(useSettings().data?.loop_tag ?? "");
  const base = (tag || "pidtools").replace(/[^\w.-]+/gu, "_").replace(/^_+|_+$/g, "").slice(0, 60) || "pidtools";
  return `${base}_${new Date().toISOString().slice(0, 10)}`;
}

export function ProjectMain() {
  const T = useT();
  const { html, busy, err } = useReport();
  const base = useBaseName();
  return (
    <div className="stack">
      <div className="card stack" data-testid="report-card">
        <div className="row" style={{ alignItems: "center" }}>
          <h3 style={{ margin: 0 }}>{T("rp_preview")}</h3>
          {html && <button className="btn" style={{ marginLeft: "auto" }} data-testid="report-download"
            onClick={() => saveAs(`${base}_protokol.html`, html, "text/html")}>{T("rep_dl")}</button>}
        </div>
        {err && <div className="err small" role="alert" data-testid="report-err">{err}</div>}
        {busy && <div className="muted small">{T("rp_building")}</div>}
        {html
          ? (<>
            <div className="muted small">{T("rp_pdf_hint")}</div>
            <iframe className="report-frame" title="report" sandbox="allow-scripts allow-modals" srcDoc={html}
              data-testid="report-frame" />
          </>)
          : !busy && <div className="muted small" data-testid="report-hint">{T("rp_preview_hint")}</div>}
      </div>
    </div>
  );
}

function ProjectBox() {
  const T = useT();
  const wid = useUi((s) => s.wid);
  const qc = useQueryClient();
  const base = useBaseName();
  const [withData, setWithData] = useState(true);
  const { msg, set: setMsg } = useProjMsg();

  async function save() {
    if (!wid) return;
    setMsg(null);
    try { saveAs(`${base}_projekt${PROJECT_EXT}`, await bytes("GET", `/workspaces/${wid}/project?data=${withData}`), "application/json"); }
    catch (e) { setMsg({ err: true, text: e instanceof ApiError ? T(e.message) : String(e) }); }
  }
  async function open(f: File | undefined) {
    if (f && wid) await openProject(wid, await f.arrayBuffer(), qc, T);
  }
  return (
    <section>
      <h3>{T("proj_title")}</h3>
      <div className="muted small">{T("pj_intro")}</div>
      <label className="small" title={T("h_proj_inc")}>
        <input type="checkbox" checked={withData} onChange={(e) => setWithData(e.target.checked)} data-testid="proj-data" />{" "}
        {T("proj_include_data")}
      </label>
      <div className="row">
        <button className="btn primary" onClick={() => void save()} data-testid="proj-save">{T("proj_save")}</button>
        <label className="btn" title={T("h_proj_load")}>
          {T("proj_load")}
          <input type="file" accept={PROJECT_ACCEPT} hidden data-testid="proj-open"
            onChange={(e) => { void open(e.target.files?.[0]); e.target.value = ""; }} />
        </label>
      </div>
      {msg && <div className={msg.err ? "err small" : "ok small"} role={msg.err ? "alert" : "status"} data-testid="proj-msg">{msg.text}</div>}
    </section>
  );
}

function ReportBox() {
  const T = useT();
  const wid = useUi((s) => s.wid);
  const st = useSettings().data ?? {};
  const busy = useReport((s) => s.busy);
  const [secs, setSecs] = useState<string[]>([...SECTIONS]);
  const [charts, setCharts] = useState<"inline" | "cdn">("inline");

  async function build() {
    if (!wid) return;
    const rep = useReport.getState();
    rep.set({ busy: true, err: null });
    try {
      const meta = Object.fromEntries(["plant", "author", "status", "comment"].map((k) => [k, st[`rep_${k}`] ?? (k === "status" ? "draft" : "")]));
      const raw = await bytes("POST", `/workspaces/${wid}/report`, { meta, sections: secs, chart_mode: charts });
      rep.set({ html: new TextDecoder().decode(raw), busy: false });
    } catch (e) {
      rep.set({ busy: false, html: null, err: e instanceof ApiError ? (e.status === 409 ? T("need_model") : T(e.message)) : String(e) });
    }
  }
  return (
    <section>
      <h3>{T("rep_title")}</h3>
      <div className="muted small">{T("rep_help")}</div>
      <TextSetting k="rep_plant" label={T("rp_plant")} placeholder={T("rp_plant_ph")} />
      <TextSetting k="rep_author" label={T("rp_author")} />
      <SelectSetting k="rep_status" label={T("rp_status")} options={STATUSES} def="draft" fmt={(v) => T("rp_st_" + v)} />
      <TextSetting k="rep_comment" label={T("rep_comment")} placeholder={T("rp_comment_ph")} multiline />
      <label className="field" title={T("h_rp_charts")}>
        <span>{T("rp_charts")}</span>
        <select value={charts} onChange={(e) => setCharts(e.target.value as "inline" | "cdn")} data-testid="rep-charts">
          {(["inline", "cdn"] as const).map((v) => <option key={v} value={v}>{T("rp_ch_" + v)}</option>)}
        </select>
      </label>
      <div className="small" title={T("h_rp_sections")} data-testid="rep-sections">
        <div className="muted">{T("rp_sections")}</div>
        {SECTIONS.map((s) => (
          <label key={s} style={{ display: "block" }}>
            <input type="checkbox" checked={secs.includes(s)} data-testid={`rep-sec-${s}`}
              onChange={(e) => setSecs(SECTIONS.filter((x) => (x === s ? e.target.checked : secs.includes(x))))} /> {T("rp_sec_" + s)}
          </label>))}
      </div>
      <button className="btn primary" disabled={busy} onClick={() => void build()} data-testid="report-build">{T("rep_build")}</button>
    </section>
  );
}

export function ProjectSide() {
  return (
    <div className="stack">
      <ProjectBox />
      <ReportBox />
    </div>
  );
}
