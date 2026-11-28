// Prvky nastavení smyčky navázané na klíče projektu (PATCH /settings): číslo, výběr, zaškrtnutí.
import { useId, useState } from "react";
import { usePatchSettings, useSettings } from "../data";
import { useT } from "../i18n";
import { LabelHelp } from "./Ui";

/** Popisek pole s „?“ (nápověda = `help`, jinak `title`; klíč překladu nebo text). */
function Lbl({ id, label, help }: { id: string; label: string; help?: string }) {
  return <span className="lbl"><span id={id}>{label}</span>{help && <LabelHelp text={help} />}</span>;
}

/** Text jako číslo (desetinná čárka → tečka); `null` = prázdné nebo nečíselné. */
export function parseNum(text: string): number | null {
  const t = text.trim().replace(",", ".");
  if (t === "") return null;
  const x = Number(t);
  return Number.isFinite(x) ? x : null;
}

/** Meze číselného pole (shodné s `RANGES` v pidtools/app/project.py). */
export type NumLimits = { min?: number; max?: number; integer?: boolean; minExclusive?: boolean };

/** Klíč chybového textu pro hodnotu mimo meze (+ argumenty), jinak `null`. */
export function numError(x: number | null, lim: NumLimits): [string, Record<string, number>?] | null {
  if (x === null) return ["num_err_number"];
  if (lim.integer && !Number.isInteger(x)) return ["num_err_int"];
  if (lim.min !== undefined && (lim.minExclusive ? x <= lim.min : x < lim.min))
    return [lim.minExclusive ? "num_err_gt" : "num_err_min", { min: lim.min }];
  if (lim.max !== undefined && x > lim.max) return ["num_err_max", { max: lim.max }];
  return null;
}

export function NumSetting({ k, label, def, title, help, min, max, integer, minExclusive, step, extra }: { k: string; label: string; def?: number;
  title?: string; help?: string; step?: number; extra?: Record<string, unknown> } & NumLimits) {
  const id = useId();
  const errId = useId();
  const T = useT();
  const st = useSettings().data ?? {};
  const patch = usePatchSettings();
  const [v, setV] = useState<string | null>(null);      // rozepsaný text (null = zobrazit uloženou hodnotu)
  const [err, setErr] = useState<string | null>(null);   // chyba lokální kontroly nebo odpověď serveru (422)
  const cur = st[k] ?? def ?? "";
  const done = () => {
    if (v === null) return;
    const e = numError(parseNum(v), { min, max, integer, minExclusive });
    if (e) { setErr(T(e[0], e[1])); return; }           // text zůstane v poli, nic se neposílá
    setErr(null);
    // Chyba serveru (422) se ukáže u pole; text zůstane, ať jde opravit. Toast zobrazí `usePatchSettings`.
    patch({ [k]: parseNum(v), ...extra }).then(() => setV(null), (ex: unknown) => setErr(ex instanceof Error ? ex.message : String(ex)));
  };
  return (
    <label className="field">
      <Lbl id={id} label={label} help={help ?? title} />
      <input type="number" aria-labelledby={id} step={step ?? "any"} min={min} max={max} value={v ?? (typeof cur === "number" ? +cur.toPrecision(6) : String(cur))}
        aria-invalid={err ? "true" : undefined} aria-describedby={err ? errId : undefined}
        data-testid={`set-${k}`} onChange={(e) => { setV(e.target.value); setErr(null); }} onBlur={done}
        onKeyDown={(e) => {
          if (e.key === "Enter") (e.target as HTMLInputElement).blur();
          else if (e.key === "Escape") { setV(null); setErr(null); }   // zpět na původní hodnotu
        }} />
      {err && <span id={errId} className="field-err" data-testid={`set-${k}-err`}>{err}</span>}
    </label>
  );
}

export function SelectSetting<V extends string | number>({ k, label, options, def, title, help, fmt }: { k: string; label: string;
  options: readonly V[]; def: V; title?: string; help?: string; fmt?: (v: V) => string }) {
  const id = useId();
  const st = useSettings().data ?? {};
  const patch = usePatchSettings();
  const cur = (st[k] ?? def) as V;
  return (
    <label className="field">
      <Lbl id={id} label={label} help={help ?? title} />
      <select aria-labelledby={id} value={String(cur)} data-testid={`set-${k}`}
        onChange={(e) => { const o = options.find((x) => String(x) === e.target.value); if (o !== undefined) void patch({ [k]: o }); }}>
        {options.map((o) => <option key={String(o)} value={String(o)}>{fmt ? fmt(o) : String(o)}</option>)}
      </select>
    </label>
  );
}

export function CheckSetting({ k, label, def, title, help }: { k: string; label: string; def?: boolean; title?: string; help?: string }) {
  const h = help ?? title;
  const st = useSettings().data ?? {};
  const patch = usePatchSettings();
  return (
    <span className="chk-help">
      <label className="small">
        <input type="checkbox" checked={!!(st[k] ?? def)} data-testid={`set-${k}`}
          onChange={(e) => void patch({ [k]: e.target.checked })} /> {label}
      </label>
      {h && <LabelHelp text={h} />}
    </span>
  );
}

/** Text navázaný na klíč nastavení (jednotka, tag, hlavička protokolu); uloží se po opuštění pole / Enter. */
export function TextSetting({ k, label, title, help, placeholder, multiline }: { k: string; label: string; title?: string;
  help?: string; placeholder?: string; multiline?: boolean }) {
  const id = useId();
  const st = useSettings().data ?? {};
  const patch = usePatchSettings();
  const [v, setV] = useState<string | null>(null);
  const cur = String(st[k] ?? "");
  const done = () => { if (v !== null && v !== cur) void patch({ [k]: v }); setV(null); };
  return (
    <label className="field">
      <Lbl id={id} label={label} help={help ?? title} />
      {multiline
        ? <textarea aria-labelledby={id} rows={3} value={v ?? cur} placeholder={placeholder} data-testid={`set-${k}`}
            onChange={(e) => setV(e.target.value)} onBlur={done} />
        : <input type="text" aria-labelledby={id} value={v ?? cur} placeholder={placeholder} data-testid={`set-${k}`}
            onChange={(e) => setV(e.target.value)} onBlur={done}
            onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }} />}
    </label>
  );
}
