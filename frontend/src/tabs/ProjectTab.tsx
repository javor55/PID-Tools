// Záložka Projekt a report (M21): uložení / otevření projektu (soubor), údaje a volby protokolu, náhled protokolu
// (HTML v izolovaném iframe) a jeho stažení.
import { useQueryClient } from "@tanstack/react-query";
import { type ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { ApiError, bytes } from "../api/client";
import { Card } from "../components/Card";
import { TextSetting } from "../components/Fields";
import { PrimaryAction, SideCard, Seg } from "../components/Ui";
import { usePatchSettings, useSettings } from "../data";
import { useLanguages, useT } from "../i18n";
import { useUi } from "../store";
import { PROJECT_EXT, projectBaseName, saveAs, saveProject, useSaveOpts } from "../start/project";
import { useSections } from "./project/api";
import { JournalMain } from "./project/JournalMain";
import { JournalSide } from "./project/JournalSide";
import { openProject, useProjMsg } from "./project/pendingOpen";
import { STATUSES, useProjSub, useReport } from "./project/state";
import "../styles/project.css";

/** Výběr souboru při otevření projektu: vedle `.pidproj` (PROJECT_EXT ve start/project.ts) jde i starší `.json`. */
export const PROJECT_ACCEPT = `${PROJECT_EXT},.json,application/json`;
function hashOf(s: string): string {
  let h = 5381;
  for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) | 0;
  return `${s.length}:${h}`;
}

function useBaseName() {
  const tag = String(useSettings().data?.loop_tag ?? "");
  return projectBaseName(tag);
}

export function ProjectMain() {
  const sub = useProjSub((s) => s.sub);
  const setSub = useProjSub((s) => s.setSub);
  const T = useT();
  return (
    <div className="stack">
      <Seg value={sub} options={["report", "journal"] as const} label={T("jr_tab_report")} testid="proj-sub" help="h_jr_tabs"
        fmt={(v) => T("jr_tab_" + v)} onChange={setSub} />
      {sub === "journal" ? <JournalMain /> : <ReportMain />}
    </div>
  );
}

function ReportMain() {
  const T = useT();
  const { html, busy, err } = useReport();
  const base = useBaseName();
  const frame = useRef<HTMLIFrameElement>(null);
  // Protokol se do izolovaného rámce posílá zprávou (stránka rámce má vlastní CSP, `srcdoc` by zdědil přísné CSP aplikace)
  const htmlKey = useMemo(() => (html ? hashOf(html) : ""), [html]);
  useEffect(() => {
    if (!html) return;
    // v náhledu je „Tisk / PDF“ nad rámečkem – tlačítko uvnitř protokolu (pro samostatný soubor) se skryje
    const hide = "<style>button.print{display:none}</style>";
    const shown = html.includes("</head>") ? html.replace("</head>", hide + "</head>") : hide + html;
    const on = (e: MessageEvent) => {
      if (e.source === frame.current?.contentWindow && (e.data as { pidReportReady?: boolean } | null)?.pidReportReady)
        frame.current?.contentWindow?.postMessage({ pidReport: shown }, "*");
    };
    window.addEventListener("message", on);
    return () => window.removeEventListener("message", on);
  }, [html, htmlKey]);
  return (
    <div className="stack">
      <Card title={T("rp_preview")} help={T("rp_pdf_hint")} testid="report-card"
        right={html && <>
          <button className="btn" data-testid="report-download" onClick={() => saveAs(`${base}_protokol.html`, html, "text/html")}>{T("rep_dl")}</button>
          <button className="btn primary" data-testid="report-print" onClick={() => frame.current?.contentWindow?.print()}>{T("rp_print")}</button>
        </>}>
        {err && <div className="err small" role="alert" data-testid="report-err">{err}</div>}
        {busy && <div className="muted small">{T("rp_building")}</div>}
        {!html && !busy && <div className="muted small" data-testid="report-hint">{T("rp_preview_hint")}</div>}
      </Card>
      {html && (
        <div className="rcanvas">
          <iframe key={htmlKey} ref={frame} className="report-frame" title="report" sandbox="allow-scripts allow-modals"
            src="/report-host.html" data-testid="report-frame" data-report-len={html.length} />
        </div>)}
    </div>
  );
}

function ProjectBox() {
  const T = useT();
  const wid = useUi((s) => s.wid);
  const qc = useQueryClient();
  const base = useBaseName();
  const withData = useSaveOpts((s) => s.withData);
  const setWithData = useSaveOpts((s) => s.setWithData);
  const { msg, set: setMsg } = useProjMsg();

  async function save() {
    if (!wid) return;
    setMsg(null);
    try { await saveProject({ wid, withData, base }); }
    catch (e) { setMsg({ err: true, text: e instanceof ApiError ? T(e.message) : String(e) }); }
  }
  async function open(f: File | undefined) {
    if (f && wid) await openProject(wid, await f.arrayBuffer(), qc, T);
  }
  return (
    <SideCard title={T("proj_title")} help={T("pj_intro")} testid="proj-card">
      <div className="row pbtns">
        <button className="btn primary" onClick={() => void save()} data-testid="proj-save">{T("proj_save")}</button>
        <label className="btn" title={T("h_proj_load")}>
          {T("proj_load")}
          <input type="file" accept={PROJECT_ACCEPT} hidden data-testid="proj-open"
            onChange={(e) => { void open(e.target.files?.[0]); e.target.value = ""; }} />
        </label>
      </div>
      <label className="small" title={T("h_proj_inc")}>
        <input type="checkbox" checked={withData} onChange={(e) => setWithData(e.target.checked)} data-testid="proj-data" />{" "}
        {T("proj_include_data")}
      </label>
      {msg && <div className={msg.err ? "err small" : "ok small"} role={msg.err ? "alert" : "status"} data-testid="proj-msg">{msg.text}</div>}
      <div className="muted small">{T("proj_save_help")} {T("pj_load_hint")}</div>
    </SideCard>
  );
}

function ReportBox({ pre }: { pre?: ReactNode }) {
  const T = useT();
  const wid = useUi((s) => s.wid);
  const st = useSettings().data ?? {};
  const busy = useReport((s) => s.busy);
  const uiLang = useUi((s) => s.lang);
  const { lang: rlang, setLang } = useProjSub();
  const lang = rlang ?? uiLang;
  const langs = useLanguages();
  const sections = useSections(lang).data ?? [];
  const [picked, setPicked] = useState<string[] | null>(null);
  const secs = picked ?? sections.filter((x) => x.default).map((x) => x.id);
  const [charts, setCharts] = useState<"inline" | "cdn">("inline");

  async function build() {
    if (!wid) return;
    const rep = useReport.getState();
    rep.set({ busy: true, err: null });
    try {
      const meta = Object.fromEntries(["plant", "author", "status", "comment"].map((k) => [k, st[`rep_${k}`] ?? (k === "status" ? "draft" : "")]));
      const dg = useUi.getState().diag;                       // úseky A / B z Diagnostiky (sekce Ověření v provozu)
      const ab = dg?.cmp ? { a: dg.a, b: dg.b } : undefined;
      const raw = await bytes("POST", `/workspaces/${wid}/report?lang=${lang}`, { meta, sections: secs, chart_mode: charts, ab });
      rep.set({ html: new TextDecoder().decode(raw), busy: false });
    } catch (e) {
      rep.set({ busy: false, html: null, err: e instanceof ApiError ? (e.status === 409 ? T("need_model") : T(e.message)) : String(e) });
    }
  }
  const patch = usePatchSettings();
  const status = (STATUSES as readonly string[]).includes(String(st.rep_status)) ? String(st.rep_status) as (typeof STATUSES)[number] : "draft";
  async function summary() {
    if (!wid) return;
    const rep = useReport.getState();
    rep.set({ busy: true, err: null });
    try {
      const meta = Object.fromEntries(["plant", "author", "comment"].map((k) => [k, st[`rep_${k}`] ?? ""]));
      rep.set({ html: new TextDecoder().decode(await bytes("POST", `/workspaces/${wid}/report/summary?lang=${lang}`, { meta })), busy: false });
    } catch (e) { rep.set({ busy: false, html: null, err: e instanceof ApiError ? T(e.message) : String(e) }); }
  }
  return (
    <>
      <PrimaryAction disabled={busy} onClick={() => void build()} testid="report-build">{T("rep_build")}</PrimaryAction>
      <button type="button" className="btn" disabled={busy} onClick={() => void summary()} title={T("h_jr_sum_btn")} data-testid="report-summary">{T("jr_sum_btn")}</button>
      {pre}
      <SideCard title={T("rep_title")} help={T("rep_help")} testid="report-opts">
        <div className="field wide"><span>{T("rp_status")}</span>
          <Seg value={status} options={STATUSES} label={T("rp_status")} testid="set-rep_status" small help="h_rp_status" fmt={(v) => T("rp_st_" + v)}
            onChange={(v) => void patch({ rep_status: v })} /></div>
        <TextSetting k="rep_plant" label={T("rp_plant")} placeholder={T("rp_plant_ph")} help="h_rp_plant" />
        <TextSetting k="rep_author" label={T("rp_author")} help="h_rp_author" />
        <div className="field wide"><span>{T("rp_lang")}</span>
          <Seg value={lang} options={langs.map((l) => l.code)} label={T("rp_lang")} testid="rep-lang" small help="h_rp_lang"
            fmt={(v) => v.toUpperCase()} onChange={setLang} /></div>
        <div className="field wide"><span>{T("rp_charts")}</span>
          <Seg value={charts} options={["inline", "cdn"] as const} label={T("rp_charts")} testid="rep-charts" small help="h_rp_charts"
            fmt={(v) => T("rp_ch_" + v)} onChange={setCharts} /></div>
        <TextSetting k="rep_comment" label={T("rep_comment")} placeholder={T("rp_comment_ph")} help="h_rp_comment" multiline />
      </SideCard>
      <SideCard title={T("rp_sections")} help={T("h_rp_sections")} testid="rep-sections">
        {sections.map((s) => (
          <label key={s.id} className="small" title={s.help} style={{ display: "block" }}>
            <input type="checkbox" checked={secs.includes(s.id)} data-testid={`rep-sec-${s.id}`}
              onChange={(e) => setPicked(sections.map((x) => x.id).filter((x) => (x === s.id ? e.target.checked : secs.includes(x))))} /> {s.title}
            {!s.available && <span className="muted"> {T("rp_sec_unavail")}</span>}
          </label>))}
      </SideCard>
    </>
  );
}

export function ProjectSide() {
  const sub = useProjSub((s) => s.sub);
  if (sub === "journal") return <><JournalSide /><ProjectBox /></>;
  return <ReportBox pre={<ProjectBox />} />;
}
