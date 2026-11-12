// Nastavení › Regulátory › Editor regulátoru (návrh RegEditor): Skládání z částí / Rovnice (text), živá rovnice, schéma,
// rychlé kontroly a přepočet návrhu. Ukládá do knihovny (PUT /controllers/{id}).
import { useQueryClient } from "@tanstack/react-query";
import { type ReactNode, useEffect, useRef, useState } from "react";
import { ApiError } from "../api/client";
import { LabelHelp, Seg } from "../components/Ui";
import { useT } from "../i18n";
import { type CompileResult, ctlApi, type MapResult, type Part, type Profile, useParts, useProfile } from "./ctlApi";
import {
  equationText, isProgram, markersByLine, NEW_PROGRAM, offsetOf, problemText, selectedPart, setPart, SNIPPETS, syncParams,
} from "./ctlHelpers";
import { BlockChain } from "./RegLibrary";
import { useSettingsUi } from "./settingsStore";

type Mode = "compose" | "text";

function Field({ label, help, children }: { label: string; help: string; children: ReactNode }) {
  return <label className="field"><span className="lbl"><span>{label}</span><LabelHelp text={help} /></span>{children}</label>;
}

/** Řádky se značkami chyb vlevo, textové pole vpravo (bez zalamování, posouvají se spolu). */
function CodeEditor({ value, onChange, markers, taRef, title }: {
  value: string; onChange: (v: string) => void; markers: ReturnType<typeof markersByLine>;
  taRef: React.RefObject<HTMLTextAreaElement | null>; title: string;
}) {
  const gut = useRef<HTMLDivElement>(null);
  const n = value.split("\n").length;
  return (
    <div className="rg-code" data-testid="rg-code">
      <div className="rg-gutter" ref={gut} aria-hidden="true">
        {Array.from({ length: n }, (_, i) => {
          const m = markers.get(i + 1);
          return <div key={i} className={"rg-ln" + (m ? ` ${m.kind}` : "")} title={m?.message} data-line={i + 1} data-kind={m?.kind}>{m ? (m.kind === "error" ? "✕" : "!") : ""}{i + 1}</div>;
        })}
      </div>
      <textarea ref={taRef} className="rg-ta" spellCheck={false} wrap="off" value={value} title={title} aria-label={title} data-testid="rg-source"
        onChange={(e) => onChange(e.target.value)} onScroll={(e) => { if (gut.current) gut.current.scrollTop = e.currentTarget.scrollTop; }} />
    </div>
  );
}

function PartPicker({ kind, parts, p, onPick }: { kind: string; parts: Part[]; p: Profile; onPick: (kind: string, id: string) => void }) {
  const T = useT();
  const ids = parts.filter((x) => x.kind === kind).map((x) => x.id);
  const opts = kind === "deadbands" ? ["none", ...ids] : ids;
  const cur = selectedPart(p, kind);
  return (
    <div className="rg-pick" data-testid={`rg-pick-${kind}`}>
      <Seg value={cur} options={opts} label={T(`rg_ui_kind_${kind}`)} help={`rg_ui_kind_${kind}_h`} small testid={`rg-seg-${kind}`}
        fmt={(v) => T(`rg_ui_p_${kind}_${v}`)} titles={(v) => T(v === "none" && kind === "deadbands" ? "rg_ui_p_deadbands_none" : `ctl_part_${kind}_${v}`)}
        onChange={(v) => onPick(kind, v)} />
      <div className="rg-pick-desc">{kind === "deadbands" && cur === "none" ? T("rg_ui_p_deadbands_none") : T(`ctl_part_${kind}_${cur}`)}</div>
    </div>
  );
}

const SECTIONS: { id: string; kinds: string[] }[] = [
  { id: "struct", kinds: ["forms", "d_sources", "d_filters"] },
  { id: "params", kinds: [] },
  { id: "error", kinds: ["deadbands", "nl_gains", "pv_filters"] },
  { id: "integ", kinds: ["antiwindups", "algorithms", "normalisations"] },
  { id: "out", kinds: ["output_stages"] },
];

function Body({ profile }: { profile: Profile }) {
  const T = useT();
  const qc = useQueryClient();
  const { go } = useSettingsUi();
  const parts = useParts().data ?? [];
  const [draft, setDraft] = useState<Profile>(profile);
  const [mode, setMode] = useState<Mode>(isProgram(profile) ? "text" : "compose");
  const [source, setSource] = useState(profile.source ?? "");
  const [res, setRes] = useState<CompileResult | null>(null);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [mapRes, setMapRes] = useState<MapResult | null>(null);
  const [mapErr, setMapErr] = useState("");
  const ta = useRef<HTMLTextAreaElement>(null);
  const id = profile.id as string;

  // živý překlad textu (po krátké pauze v psaní); zastaralé odpovědi se zahodí
  useEffect(() => {
    if (mode !== "text") return;
    let dead = false;
    const t = setTimeout(() => { ctlApi.compile(source).then((r) => { if (!dead) setRes(r); }).catch(() => { /* server nedostupný */ }); }, 350);
    return () => { dead = true; clearTimeout(t); };
  }, [mode, source]);

  const recompute = () => {
    setMapErr("");
    ctlApi.map(id, { Kc: 2, Ti: 60, Td: 10, b: 1, c: 1, N: 10 }).then(setMapRes).catch((e) => { setMapRes(null); setMapErr(problemText(e instanceof ApiError ? e.message : String(e))); });
  };
  useEffect(() => { ctlApi.map(id, { Kc: 2, Ti: 60, Td: 10, b: 1, c: 1, N: 10 }).then(setMapRes).catch(() => setMapRes(null)); }, [id]);

  const pick = (kind: string, pid: string) => setDraft((d) => syncParams(setPart(d, kind, pid), parts));
  const setParam = (key: string, patch: Record<string, unknown>) =>
    setDraft((d) => ({ ...d, params: d.params.map((p) => (p.key === key ? { ...p, ...patch } : p)) }));
  const toText = () => {
    if (!isProgram(draft) && !source) setSource(NEW_PROGRAM);
    setMode("text");
  };
  const payload = (): Profile => {
    if (mode === "compose") return { ...draft, kind: undefined, source: undefined };
    const { program: _p, ...rest } = draft as Profile & { program?: unknown };
    void _p;
    return { ...rest, kind: "program", source, structure: {}, params: [] };
  };
  const save = async (): Promise<boolean> => {
    setMsg(null);
    try {
      const out = await ctlApi.update(id, payload());
      await qc.invalidateQueries({ queryKey: ["ctl"] });
      setDraft(isProgram(out) ? { ...out } : out);
      setMsg({ ok: true, text: T("rg_ui_saved") });
      recompute();
      return true;
    } catch (e) {
      setMsg({ ok: false, text: problemText(e instanceof ApiError ? e.message : String(e)) });
      return false;
    }
  };
  const insert = (s: string) => {
    const el = ta.current;
    const a = el?.selectionStart ?? source.length, b = el?.selectionEnd ?? source.length;
    setSource(source.slice(0, a) + s + source.slice(b));
    requestAnimationFrame(() => { el?.focus(); el?.setSelectionRange(a + s.length, a + s.length); });
  };
  const jump = (line: number, col: number) => {
    const el = ta.current;
    if (!el) return;
    const o = offsetOf(source, line, col);
    el.focus(); el.setSelectionRange(o, Math.min(source.length, o + 1));
    el.scrollTop = Math.max(0, (line - 3) * 20);
  };
  const markers = markersByLine(source, res);
  const eqProfile = mode === "text" ? { ...draft, kind: "program" } : { ...draft, kind: undefined };
  const quick = mode === "text" ? res?.checks?.checks : undefined;
  const unitOf = (k: string) => profile.params.find((p) => p.key === k);

  return (
    <div className="rg-editor" data-testid="reg-editor">
      <div className="rg-ehead card">
        <button type="button" className="btn" data-testid="rg-back" title={T("rg_ui_back_lib_h")} onClick={() => go("library")}>{T("rg_ui_back_lib")}</button>
        <div className="rg-crumb">{T("rg_ui_crumb")}{profile.derived_from ? ` (${T("rg_ui_derived", { id: profile.derived_from })})` : ""}</div>
        <Field label={T("rg_ui_name")} help="rg_ui_name_h">
          <input type="text" value={draft.name ?? ""} data-testid="rg-name-input" onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
        </Field>
        <Seg value={mode} options={isProgram(profile) ? (["text"] as const) : (["compose", "text"] as const)} label={T("rg_ui_mode")} help="rg_ui_mode_h"
          testid="rg-mode" fmt={(v) => T(v === "compose" ? "rg_ui_mode_compose" : "rg_ui_mode_text")}
          onChange={(m) => (m === "text" ? toText() : setMode("compose"))} />
        <span className="rg-grow" />
        <button type="button" className="btn" data-testid="rg-full-test" title={T("rg_ui_full_test_h")}
          onClick={async () => { if (await save()) go("test", id); }}>{T("rg_ui_full_test")}</button>
        <button type="button" className="btn primary" data-testid="rg-save" title={T("rg_ui_save_h")} onClick={() => void save()}>{T("rg_ui_save")}</button>
      </div>
      {msg && <pre className={"rg-msg " + (msg.ok ? "ok" : "bad")} role="status" data-testid="rg-msg">{msg.text}</pre>}
      <div className="rg-egrid">
        <div className="rg-main">
          {mode === "compose" ? (
            <>
              {SECTIONS.map((s) => (
                <section key={s.id} className="card rg-sec" data-testid={`rg-sec-${s.id}`}>
                  <h3>{T(`rg_ui_sec_${s.id}`)}</h3>
                  {s.id === "params" ? (
                    <table className="tbl rg-params">
                      <thead><tr>
                        <th title={T("rg_ui_col_name_h")}>{T("rg_ui_col_name")}</th><th title={T("rg_ui_col_unit_h")}>{T("rg_ui_col_unit")}</th>
                        <th title={T("rg_ui_col_role_h")}>{T("rg_ui_col_role")}</th><th title={T("rg_ui_col_default_h")}>{T("rg_ui_col_default")}</th>
                        <th title={T("rg_ui_col_range_h")}>{T("rg_ui_col_range")}</th></tr></thead>
                      <tbody>{draft.params.map((p) => (
                        <tr key={p.key}>
                          <td><input type="text" value={p.name ?? p.key} title={T("rg_ui_col_name_h")} onChange={(e) => setParam(p.key, { name: e.target.value })} /></td>
                          <td>{p.unit ?? ""}</td><td>{p.role}</td>
                          <td>{typeof p.default === "number"
                            ? <input type="number" step="any" value={p.default} title={T("rg_ui_col_default_h")}
                              onChange={(e) => { if (e.target.value !== "" && Number.isFinite(+e.target.value)) setParam(p.key, { default: +e.target.value }); }} />
                            : p.default === undefined || p.default === null ? "" : String(p.default)}</td>
                          <td>{p.range ? `${p.range[0]} … ${p.range[1]}` : ""}</td></tr>))}</tbody>
                    </table>
                  ) : s.kinds.map((k) => <PartPicker key={k} kind={k} parts={parts} p={draft} onPick={pick} />)}
                </section>))}
            </>
          ) : (
            <section className="card rg-sec" data-testid="rg-text">
              <div className="rg-text-head">
                <h3>{T("rg_ui_prog")}</h3>
                <span className={"rg-status " + (res ? (res.ok ? "ok" : "bad") : "")} data-testid="rg-compile-status">
                  {!res ? "…" : res.ok ? `✓ ${T("rg_ui_compiled")}` : `✕ ${T("rg_ui_errors_n", { n: res.errors.length })}`}</span>
              </div>
              <div className="rg-snip">
                <span>{T("rg_ui_insert")}</span>
                {SNIPPETS.map(([l, s]) => <button key={l} type="button" className="btn small" title={s.trim()} onClick={() => insert(s)}>{l}</button>)}
              </div>
              <CodeEditor value={source} onChange={setSource} markers={markers} taRef={ta} title={T("rg_ui_source_h")} />
              {res && (res.errors.length > 0 || res.warnings.length > 0) && (
                <ul className="rg-issues" data-testid="rg-issues">
                  {[...res.errors.map((e) => ({ ...e, k: "error" })), ...res.warnings.map((e) => ({ ...e, k: "warning" }))].map((e, i) => (
                    <li key={i} className={e.k}><button type="button" title={T("rg_ui_jump_h")} onClick={() => jump(e.line, e.col)}>
                      <code>{e.line}:{e.col}</code> {e.message}</button></li>))}
                </ul>)}
              <div className="rg-map">
                <h4>{T("rg_ui_mapping")}<LabelHelp text="rg_ui_mapping_h" /></h4>
                <p className="rg-note">{res?.ok ? (res.has_mapping ? T("rg_ui_mapping_yes", { roles: (res.tuning_roles ?? []).join(", ") }) : T("rg_ui_mapping_no")) : T("rg_ui_mapping_hint")}</p>
              </div>
            </section>)}
        </div>
        <aside className="rg-side">
          <section className="card rg-sec">
            <h3>{T("rg_ui_equation")}</h3>
            <pre className="rg-eq" data-testid="rg-eq">{equationText(eqProfile as Profile)}</pre>
            <BlockChain p={eqProfile as Profile} />
          </section>
          <section className="card rg-sec" data-testid="rg-quick">
            <h3>{T("rg_ui_quick")}<LabelHelp text="rg_ui_quick_h" /></h3>
            {quick ? (
              <ul className="rg-list">{quick.map((c) => (
                <li key={c.id}><span className={`rg-mark ${c.status}`}>{c.status === "ok" ? "✓" : c.status === "warn" ? "!" : "✕"}</span>
                  <b>{c.name}</b><span>{c.message}</span></li>))}</ul>)
              : <p className="rg-note">{T(mode === "text" ? "rg_ui_quick_wait" : "rg_ui_quick_compose")}</p>}
          </section>
          <section className="card rg-sec" data-testid="rg-recalc">
            <h3>{T("rg_ui_recalc")}<LabelHelp text="rg_ui_recalc_h" /></h3>
            <p className="rg-note">{T("rg_ui_recalc_note")}</p>
            <button type="button" className="btn small" title={T("rg_ui_recalc_btn_h")} onClick={recompute}>{T("rg_ui_recalc_btn")}</button>
            {mapRes && (
              <table className="tbl">
                <thead><tr><th title={T("rg_ui_col_name_h")}>{T("rg_ui_col_name")}</th><th title={T("rg_ui_col_unit_h")}>{T("rg_ui_col_unit")}</th>
                  <th title={T("rg_ui_col_value_h")}>{T("rg_ui_col_value")}</th></tr></thead>
                <tbody>{Object.entries(mapRes.values).map(([k, v]) => (
                  <tr key={k}><td>{unitOf(k)?.name ?? k}</td><td>{unitOf(k)?.unit ?? ""}</td>
                    <td>{typeof v === "number" ? +v.toPrecision(5) : String(v)}</td></tr>))}</tbody>
              </table>)}
            {mapRes?.warnings.map((w, i) => <p key={i} className="rg-warn">{w.text}</p>)}
            {mapErr && <p className="rg-warn">{mapErr}</p>}
          </section>
        </aside>
      </div>
    </div>
  );
}

export function RegEditor() {
  const { id } = useSettingsUi();
  const prof = useProfile(id);
  if (!prof.data) return <p className="rg-note">…</p>;
  return <Body key={id} profile={prof.data} />;
}
