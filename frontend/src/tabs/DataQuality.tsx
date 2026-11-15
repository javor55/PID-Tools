// Karta „Kvalita dat“ pod záznamem (podle návrhu): odznak, počty a seznam kontrol se stavem, výsledkem a vysvětlením
// (/dataquality, texty dq_*); pod ním kvalita úseku identifikace (/quality, q_*) a režim MAN / AUTO (/loopmode).
import type { components } from "../api/schema";
import { Help } from "../components/Ui";
import { type LoopMode, type Quality, useWsQuery } from "../data";
import { decOf, useT } from "../i18n";
import { useUi } from "../store";
import "../styles/data.css";

type DataQualityT = components["schemas"]["DataQuality"];

/** Čísla v argumentech textů: desetinný oddělovač podle jazyka, delší reálná čísla se zaokrouhlí na 4 platné číslice. */
function loc(args: Record<string, unknown>, lang: string): Record<string, unknown> {
  return Object.fromEntries(Object.entries(args).map(([k, v]) => [k,
    typeof v === "number" && Number.isFinite(v) ? (+v.toPrecision(4)).toLocaleString(lang, { maximumFractionDigits: 6 })
      : typeof v === "string" && decOf(lang) !== "." ? v.replace(/(\d)\.(\d)/g, `$1${decOf(lang)}$2`) : v]));
}

const ICON = { ok: "✓", warn: "!", info: "i" } as const;

export function DataQualityCard() {
  const T = useT();
  const lang = useUi((s) => s.lang);
  const dq = useWsQuery<DataQualityT>("dataquality", "/dataquality").data;
  const quality = useWsQuery<Quality>("quality", "/quality").data;
  const lm = useWsQuery<LoopMode>("loopmode", "/loopmode").data;
  if (!dq) return null;
  return (
    <section className="dt-card" aria-label={T("dq_title")} data-testid="dataquality">
      <div className="dt-head">
        <h2>{T("dq_title")}<Help text={T("dq_help")} /></h2>
        <span className={"dt-badge" + (dq.usable ? "" : " bad")} data-testid="dq-badge">
          {T(dq.usable ? "dq_usable" : "dq_unusable")}</span>
        <span className="dt-sub" data-testid="dq-counts">{T("dq_counts", dq.counts)}</span>
      </div>
      <ul className="dt-checks">
        {dq.checks.map((c, i) => (
          <li key={`${c.id}${i}`} className={`dt-check dt-${c.status}`} data-testid={`dq-${c.id}`} data-status={c.status}>
            <span className="dt-ic" aria-hidden="true">{ICON[c.status]}</span>
            <span className="dt-name">{T(`dq_${c.id}_name`, loc(c.args, lang))}</span>
            <span>
              <span className="dt-res">{T(c.res, loc(c.args, lang))}</span>
              <span className="dt-why">{T(`dq_${c.id}_why`)}</span>
            </span>
          </li>))}
      </ul>
      {(quality || lm) && (
        <div className="dt-ident">
          {quality && (
            <section data-testid="quality">
              <h3>{T("q_title")}
                <span className={"dt-badge" + (quality.level === 0 ? "" : " bad")}>{T(`q_level${Math.min(quality.level, 2)}`)}</span></h3>
              <ul className="checks">
                {quality.checks.map((c) => (
                  <li key={c.key} className={c.level >= 2 ? "err" : c.level === 1 ? "warn" : "ok"}>{T(c.key, loc(c.args, lang))}</li>
                ))}
              </ul>
            </section>)}
          {lm && (
            <div className="dt-lm" data-testid="loopmode">
              {T("lm_status", { a: Math.round(100 * lm.auto_frac), m: 100 - Math.round(100 * lm.auto_frac) })}
            </div>)}
        </div>)}
    </section>
  );
}
