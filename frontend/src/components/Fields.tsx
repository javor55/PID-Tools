// Prvky nastavení smyčky navázané na klíče projektu (PATCH /settings): číslo, výběr, zaškrtnutí.
import { useState } from "react";
import { usePatchSettings, useSettings } from "../data";

export function NumSetting({ k, label, def, title, min, step }: { k: string; label: string; def?: number; title?: string;
  min?: number; step?: number }) {
  const st = useSettings().data ?? {};
  const patch = usePatchSettings();
  const [v, setV] = useState<string | null>(null);
  const cur = st[k] ?? def ?? "";
  return (
    <label className="field" title={title}>
      <span>{label}</span>
      <input type="number" step={step ?? "any"} min={min} value={v ?? (typeof cur === "number" ? +cur.toPrecision(6) : String(cur))}
        data-testid={`set-${k}`} onChange={(e) => setV(e.target.value)}
        onBlur={() => { if (v !== null && v !== "" && Number.isFinite(+v)) void patch({ [k]: +v }); setV(null); }}
        onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }} />
    </label>
  );
}

export function SelectSetting<V extends string | number>({ k, label, options, def, title, fmt }: { k: string; label: string;
  options: readonly V[]; def: V; title?: string; fmt?: (v: V) => string }) {
  const st = useSettings().data ?? {};
  const patch = usePatchSettings();
  const cur = (st[k] ?? def) as V;
  return (
    <label className="field" title={title}>
      <span>{label}</span>
      <select value={String(cur)} data-testid={`set-${k}`}
        onChange={(e) => { const o = options.find((x) => String(x) === e.target.value); if (o !== undefined) void patch({ [k]: o }); }}>
        {options.map((o) => <option key={String(o)} value={String(o)}>{fmt ? fmt(o) : String(o)}</option>)}
      </select>
    </label>
  );
}

export function CheckSetting({ k, label, def, title }: { k: string; label: string; def?: boolean; title?: string }) {
  const st = useSettings().data ?? {};
  const patch = usePatchSettings();
  return (
    <label className="small" title={title}>
      <input type="checkbox" checked={!!(st[k] ?? def)} data-testid={`set-${k}`}
        onChange={(e) => void patch({ [k]: e.target.checked })} /> {label}
    </label>
  );
}
