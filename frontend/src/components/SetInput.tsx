// Vstup hodnoty sady ladění (Ladění › Sady, Model › Regulátor v záznamu): prázdný = zástupná sada „[z PLC]“,
// potvrzení Enterem nebo opuštěním pole; neplatné nebo nezměněné číslo se nezapíše.
import { useT } from "../i18n";
import "../styles/tuning.css";

/** Název parametru s jednotkou bloku („TI [s]“). */
export const paramLabel = (q: { name: string; unit?: string | null }) => (q.unit && q.unit !== "-" ? `${q.name} [${q.unit}]` : q.name);

export function SetInput({ value, placeholder, label, testid, onCommit }: { value: number; placeholder: boolean; label: string; testid: string;
  onCommit: (x: number) => void }) {
  const T = useT();
  return (
    <input type="number" step="any" className="tn-setin" aria-label={label} data-testid={testid} key={`${value}-${placeholder}`}
      defaultValue={placeholder ? "" : +value.toPrecision(5)} placeholder={placeholder ? T("ui_tuning_from_plc") : undefined}
      onBlur={(e) => { const v = e.target.value; if (v !== "" && Number.isFinite(+v) && +v !== value) onCommit(+v); }}
      onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }} />
  );
}
