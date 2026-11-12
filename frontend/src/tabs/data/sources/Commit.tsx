// Pole, které uloží hodnotu až po opuštění / Enteru (a vrátí se k hodnotě ze serveru); převod čísla z textu.
import { useState } from "react";

/** Číslo z textového pole; prázdné = null, nečíselné = undefined (nic se neuloží). */
export const parse = (s: string): number | null | undefined => (s.trim() === "" ? null : Number.isFinite(+s.replace(",", ".")) ? +s.replace(",", ".") : undefined);

/** Pole, které uloží hodnotu až po opuštění / Enteru (a vrátí se k hodnotě ze serveru). */
export function Commit({ value, onCommit, label, title, type = "text", list, className, placeholder, testid, min }: {
  value: string; onCommit: (v: string) => void; label: string; title?: string; type?: string; list?: string; className?: string;
  placeholder?: string; testid?: string; min?: number;
}) {
  const [v, setV] = useState<string | null>(null);
  const done = () => { if (v !== null && v !== value) onCommit(v); setV(null); };
  return (
    <input type={type} aria-label={label} title={title ?? label} list={list} className={className} placeholder={placeholder} data-testid={testid}
      min={min} step={type === "number" ? "any" : undefined} value={v ?? value} onChange={(e) => setV(e.target.value)} onBlur={done}
      onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); if (e.key === "Escape") setV(null); }} />
  );
}
