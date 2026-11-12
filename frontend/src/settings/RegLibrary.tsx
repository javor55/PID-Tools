// Nastavení › Regulátory: knihovna (seznam vlevo, detail vpravo se záložkami), podle návrhu RegLibrary.
import { useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { ApiError } from "../api/client";
import { useT } from "../i18n";
import { ctlApi, type Profile, saveBlob, type Summary, useControllers, useParts, useProfile } from "./ctlApi";
import { blockChain, equationText, facts, groupControllers, isProgram, problemText, specials, tagsOf } from "./ctlHelpers";
import { useSettingsUi } from "./settingsStore";
import "./settings.css";

const TABS = ["eq", "par", "fn", "io", "test"] as const;
type DTab = (typeof TABS)[number];

export function TagChip({ tag }: { tag: string }) {
  const T = useT();
  return <span className={`rg-tag rg-tag-${tag}`} title={T(`rg_ui_tag_${tag}_h`)}>{T(`rg_ui_tag_${tag}`)}</span>;
}

export function BlockChain({ p }: { p: Profile }) {
  const T = useT();
  return (
    <div className="rg-chain" data-testid="rg-chain">
      {blockChain(p).map((k, i) => <span key={i} className="rg-chain-i">{i > 0 && <span className="rg-arrow" aria-hidden="true">→</span>}<span className="rg-block">{T(k)}</span></span>)}
    </div>
  );
}

function Detail({ id, sum }: { id: string; sum: Summary }) {
  const T = useT();
  const qc = useQueryClient();
  const prof = useProfile(id).data;
  const parts = useParts().data ?? [];
  const { go, defaultCtl, setDefault, tests } = useSettingsUi();
  const [tab, setTab] = useState<DTab>("eq");
  const [err, setErr] = useState("");
  const memo = tests[id];
  const custom = sum.tag === "custom";
  const run = async (f: () => Promise<void>) => { setErr(""); try { await f(); } catch (e) { setErr(problemText(e instanceof ApiError ? e.message : String(e))); } };
  const makeCustom = () => run(async () => { const c = await ctlApi.create(id); await qc.invalidateQueries({ queryKey: ["ctl"] }); go("editor", c.id); });
  const remove = () => run(async () => {
    if (!window.confirm(T("rg_ui_confirm_delete", { name: sum.name }))) return;
    await ctlApi.remove(id); await qc.invalidateQueries({ queryKey: ["ctl"] }); go("library", null);
  });
  const exp = () => run(async () => saveBlob(await ctlApi.exportFile(id), `${id}.pidctrl`));
  if (!prof) return <section className="card rg-detail" data-testid="rg-detail">…</section>;
  const part = (k: string) => parts.find((x) => `${x.kind}/${x.id}` === k);
  return (
    <section className="card rg-detail" data-testid="rg-detail" data-id={id}>
      <div className="rg-dhead">
        <div>
          <div className="rg-vendor">{sum.vendor}</div>
          <h2 data-testid="rg-name">{sum.name}</h2>
          <div className="rg-sub">{prof.system ?? ""}{prof.block ? ` · ${prof.block}` : ""}</div>
        </div>
        <div className="rg-tags">
          {tagsOf(sum).map((t) => <TagChip key={t} tag={t} />)}
          {memo && <span className={`rg-tag rg-verdict-${memo.verdict}`} data-testid="rg-memo">{memo.text}</span>}
        </div>
      </div>
      <div className="rg-actions">
        {custom
          ? <button type="button" className="btn primary" data-testid="rg-edit" title={T("rg_ui_edit_h")} onClick={() => go("editor", id)}>{T("rg_ui_edit")}</button>
          : <button type="button" className="btn primary" data-testid="rg-make-custom" title={T("rg_ui_make_custom_h")} onClick={makeCustom}>{T("rg_ui_make_custom")}</button>}
        <button type="button" className="btn" data-testid="rg-run-test" title={T("rg_ui_run_test_h")} onClick={() => go("test", id)}>{T("rg_ui_run_test")}</button>
        <button type="button" className="btn" data-testid="rg-default" aria-pressed={defaultCtl === id} title={T("rg_ui_default_h")}
          onClick={() => setDefault(id)}>{defaultCtl === id ? "✓ " : ""}{T("rg_ui_default")}</button>
        <button type="button" className="btn" data-testid="rg-export" title={T("rg_ui_export_h")} onClick={exp}>{T("rg_ui_export")}</button>
        {custom && <button type="button" className="btn" data-testid="rg-delete" title={T("rg_ui_delete_h")} onClick={remove}>{T("rg_ui_delete")}</button>}
      </div>
      {err && <pre className="rg-err" role="alert">{err}</pre>}
      <div role="tablist" className="rg-tabs" aria-label={T("rg_ui_detail_tabs")}>
        {TABS.map((t) => <button key={t} role="tab" type="button" aria-selected={tab === t} data-testid={`rg-tab-${t}`} title={T(`rg_ui_tab_${t}_h`)}
          onClick={() => setTab(t)}>{T(`rg_ui_tab_${t}`)}</button>)}
      </div>
      {tab === "eq" && (
        <div data-testid="rg-pane-eq">
          <pre className="rg-eq" data-testid="rg-eq">{equationText(prof)}</pre>
          {isProgram(prof)
            ? <pre className="rg-src" data-testid="rg-src">{prof.source}</pre>
            : <dl className="rg-facts">{facts(prof).map(([k, v]) => (
              <div key={k}><dt>{T(`rg_ui_kind_${k}`)}</dt><dd title={T(`ctl_part_${k}_${v}`)}>{T(`rg_ui_p_${k}_${v}`)}</dd></div>))}</dl>}
          <BlockChain p={prof} />
          {prof.verification && <p className="rg-note">{String((prof.verification as { note?: string }).note ?? "")}</p>}
        </div>)}
      {tab === "par" && (
        <table className="tbl rg-params" data-testid="rg-pane-par">
          <thead><tr>
            <th title={T("rg_ui_col_name_h")}>{T("rg_ui_col_name")}</th><th title={T("rg_ui_col_unit_h")}>{T("rg_ui_col_unit")}</th>
            <th title={T("rg_ui_col_role_h")}>{T("rg_ui_col_role")}</th><th title={T("rg_ui_col_default_h")}>{T("rg_ui_col_default")}</th>
            <th title={T("rg_ui_col_range_h")}>{T("rg_ui_col_range")}</th></tr></thead>
          <tbody>{prof.params.map((p) => (
            <tr key={p.key}><td>{p.name ?? p.key}</td><td>{p.unit ?? ""}</td><td>{p.role}{p.repr ? ` (${p.repr})` : ""}</td>
              <td>{p.default === undefined || p.default === null ? "" : String(p.default)}</td>
              <td>{p.range ? `${p.range[0]} … ${p.range[1]}` : ""}</td></tr>))}</tbody>
        </table>)}
      {tab === "fn" && (
        <div data-testid="rg-pane-fn">
          {specials(prof).length === 0
            ? <p className="rg-note">{T(isProgram(prof) ? "rg_ui_fn_program" : "rg_ui_fn_none")}</p>
            : <ul className="rg-list">{specials(prof).map((k) => (
              <li key={k}><span className="rg-mark ok">✓</span><b>{T(`rg_ui_p_${k.replace("/", "_")}`)}</b><span>{part(k) ? T(`ctl_part_${k.replace("/", "_")}`) : ""}</span></li>))}</ul>}
        </div>)}
      {tab === "io" && (
        <table className="tbl" data-testid="rg-pane-io">
          <thead><tr><th title={T("rg_ui_io_sig_h")}>{T("rg_ui_io_sig")}</th><th title={T("rg_ui_io_dir_h")}>{T("rg_ui_io_dir")}</th>
            <th title={T("rg_ui_io_desc_h")}>{T("rg_ui_io_desc")}</th></tr></thead>
          <tbody>{["SP", "PV", "FF", "MAN", "TR", "MV", "MV2"].map((s) => (
            <tr key={s}><td><code>{s}</code></td><td>{T(["MV", "MV2"].includes(s) ? "rg_ui_io_out" : "rg_ui_io_in")}</td><td>{T(`rg_ui_io_${s}`)}</td></tr>))}</tbody>
        </table>)}
      {tab === "test" && (
        <div data-testid="rg-pane-test">
          {memo
            ? <p>{T("rg_ui_last_test")} <b>{memo.text}</b> · {T("rg_ui_checks_n", { n: memo.ok + memo.warn + memo.fail })} · {memo.at}</p>
            : <p className="rg-note">{T("rg_ui_no_test")}</p>}
          <button type="button" className="btn" title={T("rg_ui_open_test_h")} onClick={() => go("test", id)}>{T("rg_ui_open_test")}</button>
        </div>)}
    </section>
  );
}

export function RegLibrary() {
  const T = useT();
  const qc = useQueryClient();
  const list = useControllers();
  const { id, go, tests, defaultCtl } = useSettingsUi();
  const [q, setQ] = useState("");
  const [msg, setMsg] = useState("");
  const file = useRef<HTMLInputElement>(null);
  const all = list.data ?? [];
  const groups = groupControllers(all, q);
  const cur = all.find((c) => c.id === id) ?? all.find((c) => c.id === defaultCtl) ?? all[0];
  const fail = (e: unknown) => setMsg(problemText(e instanceof ApiError ? e.message : String(e)));
  const create = async () => { setMsg(""); try { const c = await ctlApi.create("isa_ideal", T("rg_ui_new_name")); await qc.invalidateQueries({ queryKey: ["ctl"] }); go("editor", c.id); } catch (e) { fail(e); } };
  const onFile = async (f?: File) => {
    if (!f) return;
    setMsg("");
    try {
      const c = await ctlApi.import(JSON.parse(await f.text()) as Profile);
      await qc.invalidateQueries({ queryKey: ["ctl"] });
      go("library", c.id);
    } catch (e) { fail(e); }
    if (file.current) file.current.value = "";
  };
  return (
    <div className="rg-lib" data-testid="reg-library">
      <aside className="card rg-aside" aria-label={T("rg_ui_library")}>
        <div className="rg-list-head">
          <input type="search" className="rg-search" placeholder={T("rg_ui_search")} aria-label={T("rg_ui_search")} title={T("rg_ui_search_h")}
            value={q} data-testid="rg-search" onChange={(e) => setQ(e.target.value)} />
          <div className="rg-list-btns">
            <button type="button" className="btn primary" data-testid="rg-new" title={T("rg_ui_new_h")} onClick={create}>{T("rg_ui_new")}</button>
            <button type="button" className="btn" data-testid="rg-import" title={T("rg_ui_import_h")} onClick={() => file.current?.click()}>{T("rg_ui_import")}</button>
            <input ref={file} type="file" accept=".pidctrl,application/json" hidden data-testid="rg-import-file" onChange={(e) => void onFile(e.target.files?.[0])} />
          </div>
        </div>
        {msg && <pre className="rg-err" role="alert">{msg}</pre>}
        {groups.map((g) => (
          <div key={g.id} className="rg-group" data-testid={`rg-group-${g.id}`}>
            <h3>{T(`rg_ui_group_${g.id}`)}</h3>
            <ul>{g.items.map((c) => (
              <li key={c.id}>
                <button type="button" className={"rg-item" + (cur?.id === c.id ? " sel" : "")} data-testid={`rg-item-${c.id}`} aria-current={cur?.id === c.id}
                  onClick={() => go("library", c.id)}>
                  <span className="rg-item-name">{c.name}</span>
                  <span className="rg-item-tags">
                    {tagsOf(c).map((t) => <TagChip key={t} tag={t} />)}
                    {tests[c.id] && <span className={`rg-tag rg-verdict-${tests[c.id].verdict}`}>{tests[c.id].text}</span>}
                    {defaultCtl === c.id && <span className="rg-tag rg-tag-default" title={T("rg_ui_default_h")}>{T("rg_ui_tag_default")}</span>}
                  </span>
                </button>
              </li>))}</ul>
          </div>))}
        {groups.length === 0 && !list.isLoading && <p className="rg-note">{T("rg_ui_none_found")}</p>}
      </aside>
      {cur ? <Detail key={cur.id} id={cur.id} sum={cur} /> : <section className="card rg-detail" />}
    </div>
  );
}
