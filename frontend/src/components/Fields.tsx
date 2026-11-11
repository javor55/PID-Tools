// Prvky nastavení smyčky navázané na klíče projektu (PATCH /settings): číslo, výběr, zaškrtnutí.
import { useId, useState } from "react";
import { usePatchSettings, useSettings } from "../data";
import { LabelHelp } from "./Ui";

/** Popisek pole s „?“ (nápověda = `help`, jinak `title`; klíč překladu nebo text). */
function Lbl({ id, label, help }: { id: string; label: string; help?: string }) {
  return <span className="lbl"><span id={id}>{label}</span>{help && <LabelHelp text={help} />}</span>;
}

export function NumSetting({ k, label, def, title, help, min, step, extra }: { k: string; label: string; def?: number; title?: string;
  help?: string; min?: number; step?: number; extra?: Record<string, unknown> }) {
  const id = useId();
  const st = useSettings().data ?? {};
  const patch = usePatchSettings();
  const [v, setV] = useState<string | null>(null);
  const cur = st[k] ?? def ?? "";
  return (
    <label className="field">
      <Lbl id={id} label={label} help={help ?? title} />
      <input type="number" aria-labelledby={id} step={step ?? "any"} min={min} value={v ?? (typeof cur === "number" ? +cur.toPrecision(6) : String(cur))}
        data-testid={`set-${k}`} onChange={(e) => setV(e.target.value)}
        onBlur={() => { if (v !== null && v !== "" && Number.isFinite(+v)) void patch({ [k]: +v, ...extra }); setV(null); }}
        onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }} />
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
