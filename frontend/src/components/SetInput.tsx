// Vstup hodnoty sady ladění (Ladění › Sady, Model › Regulátor v záznamu): prázdný = zástupná sada „[z PLC]“,
// potvrzení Enterem nebo opuštěním pole; nezměněné číslo se nezapíše. Neplatný vstup (text, u zapsané sady i prázdno)
// se neposílá: pole dostane `aria-invalid`, červený rámeček a důvod v `title` a ve skrytém popisu (`aria-describedby`).
// Text pod polem by rozbil úzký sloupec tabulky sad, proto se nezobrazuje. Esc vrátí původní hodnotu.
import { useId, useState } from "react";
import { useT } from "../i18n";
import "../styles/tuning.css";

/** Název parametru s jednotkou bloku („TI [s]“). */
export const paramLabel = (q: { name: string; unit?: string | null }) => (q.unit && q.unit !== "-" ? `${q.name} [${q.unit}]` : q.name);

export function SetInput({ value, placeholder, label, testid, onCommit }: { value: number; placeholder: boolean; label: string; testid: string;
  onCommit: (x: number) => void }) {
  const T = useT();
  const errId = useId();
  const [err, setErr] = useState<string | null>(null);
  const shown = placeholder ? "" : String(+value.toPrecision(5));
  return (
    <>
      <input type="number" step="any" className="tn-setin" aria-label={label} data-testid={testid} key={`${value}-${placeholder}`}
        defaultValue={shown} placeholder={placeholder ? T("ui_tuning_from_plc") : undefined}
        aria-invalid={err ? "true" : undefined} aria-describedby={err ? errId : undefined} title={err ?? undefined}
        onChange={() => setErr(null)}
        onBlur={(e) => {
          const el = e.target, v = el.value;
          // číselné pole vrací u textu prázdný řetězec; text (badInput) je chyba vždy, prázdno jen u zapsané sady
          const bad = el.validity.badInput || (v === "" && !placeholder) || (v !== "" && !Number.isFinite(+v));
          if (bad) { setErr(T("num_err_number")); return; }
          setErr(null);
          if (v !== "" && +v !== value) onCommit(+v);
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter") e.currentTarget.blur();
          else if (e.key === "Escape") { e.currentTarget.value = shown; setErr(null); }
        }} />
      {err && <span id={errId} className="sr-only">{err}</span>}
    </>
  );
}
