// Nastavení › Regulátory › Test použitelnosti (návrh RegTest): verdikt, 12 kontrol s podrobnostmi, tisknutelný protokol.
import { useCallback, useEffect, useState } from "react";
import { ApiError } from "../api/client";
import { useT } from "../i18n";
import { ctlApi, type Protocol, saveBlob, useControllers } from "./ctlApi";
import { countChecks, problemText } from "./ctlHelpers";
import { useSettingsUi } from "./settingsStore";

const MARK: Record<string, string> = { ok: "✓", warn: "!", fail: "✕" };

/** Řádky podrobností kontroly (např. referenční procesy) jako tabulka. */
function Rows({ rows }: { rows: Record<string, unknown>[] }) {
  const T = useT();
  const cols = Object.keys(rows[0] ?? {});
  const f = (v: unknown) => (typeof v === "number" ? String(+v.toPrecision(4)) : String(v));
  return (
    <table className="tbl rg-rows">
      <thead><tr>{cols.map((c) => <th key={c} title={T(`rg_ui_row_${c}_h`)}>{T(`rg_ui_row_${c}`)}</th>)}</tr></thead>
      <tbody>{rows.map((r, i) => <tr key={i}>{cols.map((c) => <td key={c}>{f(r[c])}</td>)}</tr>)}</tbody>
    </table>
  );
}

/** Protokol jako prostý text (uložení souboru). */
export function protocolText(name: string, p: Protocol, at: string): string {
  const lines = [`${name} – ${p.verdict_text} (${at})`, ""];
  p.checks.forEach((c, i) => lines.push(`${i + 1}. [${c.status.toUpperCase()}] ${c.name}: ${c.message}`));
  if (p.reasons.length) lines.push("", ...p.reasons);
  return lines.join("\n") + "\n";
}

export function RegTest() {
  const T = useT();
  const { id, go, putTest } = useSettingsUi();
  const list = useControllers().data ?? [];
  const name = list.find((c) => c.id === id)?.name ?? id ?? "";
  const [res, setRes] = useState<{ p: Protocol; at: string } | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(true);
  const exec = useCallback((alive: () => boolean = () => true) => {
    if (!id) return;
    ctlApi.test(id).then((p) => {
      if (!alive()) return;
      const at = new Date().toLocaleString();
      setRes({ p, at }); setBusy(false);
      putTest(id, { verdict: p.verdict, text: p.verdict_text, ...countChecks(p.checks), at });
    }).catch((e) => { if (alive()) { setErr(problemText(e instanceof ApiError ? e.message : String(e))); setBusy(false); } });
  }, [id, putTest]);
  const run = () => { setBusy(true); setErr(""); exec(); };
  useEffect(() => { let dead = false; exec(() => !dead); return () => { dead = true; }; }, [exec]);
  const n = res ? countChecks(res.p.checks) : null;
  const v = res?.p.verdict;
  const lin = res?.p.checks.find((c) => c.id === "linearity")?.status;
  const procs = res?.p.checks.find((c) => c.id === "processes")?.rows;
  return (
    <div className="rg-test" data-testid="reg-test">
      <div className="rg-ehead card">
        <button type="button" className="btn" data-testid="rg-back" title={T("rg_ui_back_lib_h")} onClick={() => go("library")}>{T("rg_ui_back_lib")}</button>
        <div className="rg-crumb">{T("rg_ui_test_crumb", { name })}</div>
        <span className="rg-grow" />
        <button type="button" className="btn" data-testid="rg-print" disabled={!res} title={T("rg_ui_print_h")} onClick={() => window.print()}>{T("rg_ui_print")}</button>
        <button type="button" className="btn" data-testid="rg-save-protocol" disabled={!res} title={T("rg_ui_save_protocol_h")}
          onClick={() => res && saveBlob(protocolText(name, res.p, res.at), `${id}-test.txt`, "text/plain")}>{T("rg_ui_save_protocol")}</button>
        <button type="button" className="btn primary" data-testid="rg-rerun" disabled={busy} title={T("rg_ui_rerun_h")} onClick={run}>{T("rg_ui_rerun")}</button>
      </div>
      {err && <pre className="rg-err" role="alert">{err}</pre>}
      {busy && !res && <p className="rg-note" data-testid="rg-running">{T("rg_ui_running")}</p>}
      {res && n && (
        <div className="rg-protocol" data-testid="rg-protocol">
          <section className={`card rg-verdict rg-verdict-${v}`}>
            <div className="rg-vmark" aria-hidden="true">{v === "suitable" ? "✓" : v === "unsuitable" ? "✕" : "!"}</div>
            <div>
              <h2 data-testid="rg-verdict" data-verdict={v}>{res.p.verdict_text}</h2>
              <p>{T("rg_ui_counts", n)}</p>
              {res.p.reasons.length > 0 && <p className="rg-note" data-testid="rg-reasons">{T("rg_ui_reason")} {res.p.reasons.map((r) => res.p.checks.find((c) => c.id === r)?.name ?? r).join(", ")}</p>}
              <div className="rg-caps">
                <span className={"rg-tag " + (v === "suitable" ? "rg-tag-verified" : "rg-tag-unverified")} title={T("rg_ui_cap_rules_h")}>{T("rg_ui_cap_rules")} {v === "suitable" ? "✓" : "✕"}</span>
                <span className={"rg-tag " + (v === "unsuitable" ? "rg-tag-unverified" : "rg-tag-verified")} title={T("rg_ui_cap_opt_h")}>{T("rg_ui_cap_opt")} {v === "unsuitable" ? "✕" : "✓"}</span>
                <span className="rg-tag" title={T("rg_ui_cap_rob_h")}>{T("rg_ui_cap_rob")} {lin === "ok" ? "✓" : "≈"}</span>
              </div>
            </div>
          </section>
          <section className="card rg-sec">
            <h3>{T("rg_ui_checks")}</h3>
            <ol className="rg-checks" data-testid="rg-checks">
              {res.p.checks.map((c) => (
                <li key={c.id} data-status={c.status} data-testid={`rg-check-${c.id}`}>
                  <span className={`rg-mark ${c.status}`}>{MARK[c.status] ?? "?"}</span>
                  <div><b>{c.name}</b><div>{c.message}</div>{c.rows && c.id !== "processes" && c.rows.length > 0 && <Rows rows={c.rows} />}</div>
                </li>))}
            </ol>
          </section>
          {procs && procs.length > 0 && (
            <section className="card rg-sec"><h3>{T("rg_ui_procs")}</h3><Rows rows={procs} /></section>)}
        </div>)}
    </div>
  );
}
