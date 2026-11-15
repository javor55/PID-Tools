// Oddíly globálního Nastavení aplikace podle návrhu (Obecné, Vzhled a jazyk, Grafy a jednotky, Diagnostika, Výchozí hodnoty
// nových smyček, Deník, Report, Připojení, Export / import). Vše se ukládá na server (`/app-settings`), změna platí hned.
import { useQuery } from "@tanstack/react-query";
import { type ReactNode, useEffect, useRef, useState } from "react";
import { api, ApiError, bytes } from "../api/client";
import { LabelHelp } from "../components/Ui";
import { useLanguages, useT } from "../i18n";
import { Commit, parse } from "../tabs/data/sources/Commit";
import { type AppSettings, exportSettings, importSettings, patchSettings, removeLogo, resetSettings, uploadLogo, useAppSettings, useThresholdSchema } from "./appSettings";
import { saveBlob, useControllers } from "./ctlApi";
import { usePublic } from "../deploy";

type Upd = (fn: (s: AppSettings) => void) => void;

function useSet(): Upd {
  return (fn) => { void patchSettings(fn).catch(() => undefined); };
}

function Sec({ id, title, note, children }: { id: string; title: string; note?: string; children: ReactNode }) {
  return (
    <section className="card rg-sec rg-general" data-testid={`settings-${id}`}>
      <h2>{title}</h2>
      {note && <p className="rg-note">{note}</p>}
      {children}
    </section>
  );
}

function Row({ label, help, children, testid }: { label: string; help: string; children: ReactNode; testid?: string }) {
  const T = useT();
  return (
    <label className="field" data-testid={testid}>
      <span className="lbl"><span>{label}</span><LabelHelp text={T(help)} /></span>
      {children}
    </label>
  );
}

function Choice<V extends string | number>({ value, options, onChange, fmt, label, testid }: {
  value: V; options: readonly V[]; onChange: (v: V) => void; fmt: (v: V) => string; label: string; testid: string;
}) {
  return (
    <select aria-label={label} data-testid={testid} value={String(value)}
      onChange={(e) => onChange((typeof options[0] === "number" ? Number(e.target.value) : e.target.value) as V)}>
      {options.map((o) => <option key={String(o)} value={String(o)}>{fmt(o)}</option>)}
    </select>
  );
}

function Check({ checked, onChange, label, help, testid }: { checked: boolean; onChange: (v: boolean) => void; label: string; help: string; testid: string }) {
  const T = useT();
  return (
    <label className="field chk-help" title={T(help)}>
      <span className="lbl"><input type="checkbox" data-testid={testid} checked={checked} onChange={(e) => onChange(e.target.checked)} />
        <span>{label}</span><LabelHelp text={T(help)} /></span>
    </label>
  );
}

const num = (v: string, lo: number, hi: number): number | undefined => { const n = parse(v); return typeof n === "number" ? Math.min(Math.max(n, lo), hi) : undefined; };

export function GeneralSec({ s }: { s: AppSettings }) {
  const T = useT();
  const set = useSet();
  const ver = useQuery({ queryKey: ["health"], queryFn: api.health, staleTime: Infinity }).data?.version;
  return (
    <Sec id="general" title={T("rg_ui_nav_general")} note={T("app_s_general_note")}>
      <Row label={T("app_s_autosave")} help="app_s_autosave_h">
        <Choice value={s.general.autosave_min} options={[0, 1, 5, 15, 30] as const} label={T("app_s_autosave")} testid="set-autosave"
          fmt={(v) => (v === 0 ? T("app_s_autosave_off") : T("app_s_autosave_n", { n: v }))} onChange={(v) => set((n) => { n.general.autosave_min = v; })} />
      </Row>
      <Check checked={s.general.embed_data} label={T("app_s_embed")} help="app_s_embed_h" testid="set-embed"
        onChange={(v) => set((n) => { n.general.embed_data = v; })} />
      <Row label={T("app_s_about")} help="app_s_about_h"><span data-testid="set-version">{ver ?? "…"}</span></Row>
    </Sec>
  );
}

export function AppearanceSec({ s }: { s: AppSettings }) {
  const T = useT();
  const langs = useLanguages();
  const langName = (c: string) => langs.find((l) => l.code === c)?.name ?? c;
  const set = useSet();
  return (
    <Sec id="appearance" title={T("app_s_appearance")} note={T("app_s_appearance_note")}>
      <Row label={T("ui_lang")} help="rg_ui_lang_h">
        <Choice value={s.appearance.language || "en"} options={langs.map((l) => l.code)} label={T("ui_lang")} testid="set-lang"
          fmt={(v) => langName(v)} onChange={(v) => set((n) => { n.appearance.language = v; })} />
      </Row>
      <Row label={T("ui_theme")} help="rg_ui_theme_h">
        <Choice value={s.appearance.theme || "system"} options={["system", "light", "dark"] as const} label={T("ui_theme")} testid="set-theme"
          fmt={(v) => T(`ui_theme_${v}`)} onChange={(v) => set((n) => { n.appearance.theme = v; })} />
      </Row>
      <Row label={T("app_s_font")} help="app_s_font_h">
        <Choice value={s.appearance.font_size} options={["s", "m", "l", "xl"] as const} label={T("app_s_font")} testid="set-font"
          fmt={(v) => T(`app_s_font_${v}`)} onChange={(v) => set((n) => { n.appearance.font_size = v; })} />
      </Row>
    </Sec>
  );
}

export function ChartsSec({ s }: { s: AppSettings }) {
  const T = useT();
  const set = useSet();
  const c = s.charts;
  return (
    <Sec id="charts" title={T("app_s_charts")} note={T("app_s_charts_note")}>
      <Row label={`${T("app_s_chart_h")} [px]`} help="app_s_chart_h_h">
        <Commit type="number" min={120} value={String(c.height)} label={T("app_s_chart_h")} title={T("app_s_chart_h_h")} testid="set-chart-h"
          onCommit={(v) => { const n = num(v, 120, 1000); if (n !== undefined) set((x) => { x.charts.height = Math.round(n); }); }} />
      </Row>
      <Row label={T("app_s_tunit")} help="app_s_tunit_help">
        <Choice value={c.time_unit} options={["auto", "s", "min", "h", "clock"] as const} label={T("app_s_tunit")} testid="set-tunit"
          fmt={(v) => T(`app_s_tunit_${v}`)} onChange={(v) => set((n) => { n.charts.time_unit = v; })} />
      </Row>
      <Row label={T("app_s_decimal")} help="app_s_decimal_h">
        <Choice value={c.decimal} options={["auto", "comma", "dot"] as const} label={T("app_s_decimal")} testid="set-decimal"
          fmt={(v) => T(`app_s_decimal_${v}`)} onChange={(v) => set((n) => { n.charts.decimal = v; })} />
      </Row>
      <Row label={T("app_s_tiunit")} help="app_s_tiunit_h">
        <Choice value={c.ti_unit} options={["s", "min"] as const} label={T("app_s_tiunit")} testid="set-tiunit"
          fmt={(v) => v} onChange={(v) => set((n) => { n.charts.ti_unit = v; })} />
      </Row>
      <Row label={T("app_s_gainview")} help="app_s_gainview_h">
        <Choice value={c.gain_view} options={["kc", "pb"] as const} label={T("app_s_gainview")} testid="set-gainview"
          fmt={(v) => T(`app_s_gainview_${v}`)} onChange={(v) => set((n) => { n.charts.gain_view = v; })} />
      </Row>
    </Sec>
  );
}

export function DiagnosticsSec({ s }: { s: AppSettings }) {
  const T = useT();
  const set = useSet();
  const items = useThresholdSchema().data ?? [];
  return (
    <Sec id="diagnostics" title={T("app_s_diag")} note={T("app_s_diag_note")}>
      {items.map((it) => {
        const cur = s.diagnostics.thresholds[it.rule]?.[it.name] ?? it.default;
        return (
          <Row key={`${it.rule}.${it.name}`} label={`${T(it.name_label)}${it.unit ? ` [${it.unit}]` : ""}`} help={`tri_vd_${it.rule}`}>
            <Commit type="number" min={it.lo} value={String(+cur.toPrecision(4))} label={T(it.name_label)} title={T(`tri_vd_${it.rule}`)}
              testid={`set-thr-${it.rule}-${it.name}`}
              onCommit={(v) => { const n = num(v, it.lo, it.hi); if (n !== undefined) set((x) => { x.diagnostics.thresholds[it.rule] = { ...(x.diagnostics.thresholds[it.rule] ?? {}), [it.name]: n }; }); }} />
          </Row>
        );
      })}
      <div className="rg-actions">
        <button type="button" className="btn" data-testid="set-thr-reset" title={T("app_s_diag_reset_h")}
          onClick={() => set((n) => { n.diagnostics.thresholds = {}; })}>{T("app_s_diag_reset")}</button>
      </div>
    </Sec>
  );
}

export function DefaultsSec({ s }: { s: AppSettings }) {
  const T = useT();
  const set = useSet();
  const ctl = useControllers().data ?? [];
  const sim = s.defaults.sim;
  const known = ctl.some((c) => c.id === s.defaults.controller);
  return (
    <Sec id="defaults" title={T("app_s_defaults")} note={T("app_s_defaults_note")}>
      <Row label={T("app_s_def_ctl")} help="app_s_def_ctl_h">
        <select aria-label={T("app_s_def_ctl")} data-testid="set-def-ctl" value={s.defaults.controller}
          onChange={(e) => { const v = e.target.value; set((n) => { n.defaults.controller = v; }); }}>
          {!known && <option value={s.defaults.controller}>{s.defaults.controller}</option>}
          {ctl.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
      </Row>
      <Row label={T("app_s_def_ctype")} help="app_s_def_ctype_h">
        <Choice value={sim.ctype} options={["PI", "PID", "PD"] as const} label={T("app_s_def_ctype")} testid="set-def-ctype"
          fmt={(v) => v} onChange={(v) => set((n) => { n.defaults.sim.ctype = v; })} />
      </Row>
      <Row label={T("app_s_def_ms")} help="app_s_def_ms_h">
        <Commit type="number" min={1.1} value={String(sim.opt_ms)} label={T("app_s_def_ms")} title={T("app_s_def_ms_h")} testid="set-def-ms"
          onCommit={(v) => { const n = num(v, 1.1, 2.5); if (n !== undefined) set((x) => { x.defaults.sim.opt_ms = n; }); }} />
      </Row>
      <Row label={`${T("app_s_def_ovs")} [%]`} help="app_s_def_ovs_h">
        <Commit type="number" min={0} value={String(sim.opt_ovs)} label={T("app_s_def_ovs")} title={T("app_s_def_ovs_h")} testid="set-def-ovs"
          onCommit={(v) => { const n = num(v, 0, 50); if (n !== undefined) set((x) => { x.defaults.sim.opt_ovs = Math.round(n); }); }} />
      </Row>
      <Check checked={sim.opt_robust} label={T("app_s_def_robust")} help="app_s_def_robust_h" testid="set-def-robust"
        onChange={(v) => set((n) => { n.defaults.sim.opt_robust = v; })} />
      <p className="rg-note">{T("app_s_def_thr_note")}</p>
    </Sec>
  );
}

export function JournalSec({ s }: { s: AppSettings }) {
  const T = useT();
  const set = useSet();
  return (
    <Sec id="journal" title={T("app_s_journal")} note={T("app_s_journal_note")}>
      <Row label={T("app_s_author")} help="app_s_author_h">
        <Commit value={s.journal.author} label={T("app_s_author")} title={T("app_s_author_h")} testid="set-author"
          onCommit={(v) => set((n) => { n.journal.author = v.trim(); })} />
      </Row>
      <Check checked={s.journal.require_note} label={T("app_s_req_note")} help="app_s_req_note_h" testid="set-req-note"
        onChange={(v) => set((n) => { n.journal.require_note = v; })} />
    </Sec>
  );
}

/** Logo ze serveru jako objektová adresa (požadavek nese přihlášení, obrázek ho přes src poslat neumí). */
function useLogo(name: string) {
  const [got, setGot] = useState<{ name: string; url: string } | null>(null);
  useEffect(() => {
    if (!name) return;
    let u = "";
    let live = true;
    bytes("GET", "/app-settings/logo").then((b) => {
      if (!live) return;
      u = URL.createObjectURL(new Blob([b], { type: name.endsWith(".svg") ? "image/svg+xml" : name.endsWith(".png") ? "image/png" : "image/jpeg" }));
      setGot({ name, url: u });
    }).catch(() => undefined);
    return () => { live = false; if (u) URL.revokeObjectURL(u); };
  }, [name]);
  return got && got.name === name ? got.url : "";
}

export function ReportSec({ s }: { s: AppSettings }) {
  const T = useT();
  const langs = useLanguages();
  const langName = (c: string) => langs.find((l) => l.code === c)?.name ?? c;
  const set = useSet();
  const file = useRef<HTMLInputElement>(null);
  const [err, setErr] = useState("");
  const r = s.report;
  const pub = usePublic();
  const logoUrl = useLogo(r.logo);
  const up = async (f: File | undefined) => {
    if (!f) return;
    setErr("");
    try { await uploadLogo(f); } catch (e) { setErr(e instanceof ApiError ? e.message : String(e)); }
  };
  return (
    <Sec id="report" title={T("app_s_report")} note={T("app_s_report_note")}>
      <Row label={T("app_s_company")} help="app_s_company_h">
        <Commit value={r.company} label={T("app_s_company")} title={T("app_s_company_h")} testid="set-company"
          onCommit={(v) => set((n) => { n.report.company = v.trim(); })} />
      </Row>
      {!pub && <div className="field" data-testid="set-logo-row">
        <span className="lbl"><span>{T("app_s_logo")}</span><LabelHelp text={T("app_s_logo_h")} /></span>
        <span className="rg-actions">
          {r.logo && logoUrl && <img className="set-logo" alt={T("app_s_logo")} data-testid="set-logo-img" src={logoUrl} />}
          <button type="button" className="btn" data-testid="set-logo-pick" title={T("app_s_logo_h")} onClick={() => file.current?.click()}>{T("app_s_logo_pick")}</button>
          {r.logo && <button type="button" className="btn" data-testid="set-logo-remove" title={T("app_s_logo_remove_h")}
            onClick={() => void removeLogo().catch(() => undefined)}>{T("app_s_logo_remove")}</button>}
          <input ref={file} type="file" hidden accept=".png,.jpg,.jpeg" data-testid="set-logo-file"
            onChange={(e) => { void up(e.target.files?.[0]); e.target.value = ""; }} />
        </span>
      </div>}
      {err && <div className="rg-err" role="alert">{err}</div>}
      <Row label={T("app_s_rep_lang")} help="app_s_rep_lang_h">
        <Choice value={r.language} options={["app", ...langs.map((l) => l.code)]} label={T("app_s_rep_lang")} testid="set-rep-lang"
          fmt={(v) => (v === "app" ? T("app_s_rep_lang_app") : langName(v))} onChange={(v) => set((n) => { n.report.language = v; })} />
      </Row>
      <Row label={T("app_s_rep_header")} help="app_s_rep_header_h">
        <Commit value={r.header} label={T("app_s_rep_header")} title={T("app_s_rep_header_h")} testid="set-rep-header"
          onCommit={(v) => set((n) => { n.report.header = v.trim(); })} />
      </Row>
      <Row label={T("app_s_rep_footer")} help="app_s_rep_footer_h">
        <Commit value={r.footer} label={T("app_s_rep_footer")} title={T("app_s_rep_footer_h")} testid="set-rep-footer"
          onCommit={(v) => set((n) => { n.report.footer = v.trim(); })} />
      </Row>
    </Sec>
  );
}

export function ConnectionsSec({ s }: { s: AppSettings }) {
  const T = useT();
  const set = useSet();
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const pub = usePublic();
  const ok = name.trim() !== "" && url.trim().toLowerCase().startsWith("opc.tcp://");
  const hist = [["pcs7", "app_s_h_pcs7"], ["deltav", "app_s_h_deltav"], ["pi", "app_s_h_pi"]] as const;
  if (pub) return <Sec id="connections" title={T("app_s_conn")} note={T("opc_disabled")}>{null}</Sec>;
  return (
    <Sec id="connections" title={T("app_s_conn")} note={T("app_s_conn_note")}>
      <h3>{T("app_s_opc")}<LabelHelp text={T("app_s_opc_h")} /></h3>
      <ul className="rg-list set-opc" data-testid="set-opc-list">
        {s.connections.opc.map((o, i) => (
          <li key={o.name} data-testid={`set-opc-${i}`}>
            <b>{o.name}</b><code>{o.url}</code>
            <button type="button" className="btn small" title={T("app_s_opc_del_h")} onClick={() => set((n) => { n.connections.opc.splice(i, 1); })}>{T("app_s_opc_del")}</button>
          </li>))}
        {s.connections.opc.length === 0 && <li className="rg-note">{T("app_s_opc_none")}</li>}
      </ul>
      <div className="rg-actions">
        <input aria-label={T("app_s_opc_name")} title={T("app_s_opc_name")} placeholder={T("app_s_opc_name")} data-testid="set-opc-name" value={name} onChange={(e) => setName(e.target.value)} />
        <input aria-label={T("app_s_opc_url")} title={T("app_s_opc_url_h")} placeholder="opc.tcp://host:4840" data-testid="set-opc-url" value={url} onChange={(e) => setUrl(e.target.value)} />
        <button type="button" className="btn" data-testid="set-opc-add" disabled={!ok} title={T("app_s_opc_add_h")}
          onClick={() => { set((n) => { n.connections.opc.push({ name: name.trim(), url: url.trim() }); }); setName(""); setUrl(""); }}>{T("app_s_opc_add")}</button>
      </div>
      <h3>{T("app_s_hist")}<LabelHelp text={T("app_s_hist_h")} /></h3>
      {hist.map(([k, label]) => (
        <Row key={k} label={T(label)} help="app_s_hist_ep_h">
          <Commit value={s.connections.historians[k]} label={T(label)} title={T("app_s_hist_ep_h")} testid={`set-hist-${k}`}
            onCommit={(v) => set((n) => { n.connections.historians[k] = v.trim(); })} />
        </Row>))}
      <p className="rg-note">{T("app_s_conn_readonly")}</p>
    </Sec>
  );
}

export function IoSec() {
  const T = useT();
  const file = useRef<HTMLInputElement>(null);
  const [msg, setMsg] = useState<{ ok: boolean; t: string } | null>(null);
  const run = async (f: () => Promise<void>, ok: string) => {
    setMsg(null);
    try { await f(); setMsg({ ok: true, t: ok }); } catch (e) { setMsg({ ok: false, t: e instanceof ApiError ? e.message : String(e) }); }
  };
  return (
    <Sec id="io" title={T("app_s_io")} note={T("app_s_io_note")}>
      <div className="rg-actions">
        <button type="button" className="btn" data-testid="set-export" title={T("app_s_export_h")}
          onClick={() => void run(async () => saveBlob(await exportSettings(), "pidtools_settings.json"), T("app_s_exported"))}>{T("app_s_export")}</button>
        <button type="button" className="btn" data-testid="set-import" title={T("app_s_import_h")} onClick={() => file.current?.click()}>{T("app_s_import")}</button>
        <input ref={file} type="file" hidden accept=".json,application/json" data-testid="set-import-file"
          onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) void run(() => importSettings(f), T("app_s_imported")); }} />
        <button type="button" className="btn" data-testid="set-reset" title={T("app_s_reset_h")}
          onClick={() => { if (window.confirm(T("app_s_reset_confirm"))) void run(resetSettings, T("app_s_reset_done")); }}>{T("app_s_reset")}</button>
      </div>
      {msg && <div className={"rg-msg" + (msg.ok ? " ok" : "")} role={msg.ok ? "status" : "alert"} data-testid="set-io-msg">{msg.t}</div>}
    </Sec>
  );
}

export function AppSection({ id }: { id: string }) {
  const s = useAppSettings().data;
  if (!s) return <section className="card rg-sec">…</section>;
  switch (id) {
    case "general": return <GeneralSec s={s} />;
    case "appearance": return <AppearanceSec s={s} />;
    case "charts": return <ChartsSec s={s} />;
    case "diagnostics": return <DiagnosticsSec s={s} />;
    case "defaults": return <DefaultsSec s={s} />;
    case "journal": return <JournalSec s={s} />;
    case "report": return <ReportSec s={s} />;
    case "connections": return <ConnectionsSec s={s} />;
    default: return <IoSec />;
  }
}
