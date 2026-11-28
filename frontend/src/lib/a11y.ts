// Pomůcky přístupnosti: výběr řádku tabulky klávesnicí.
import type { KeyboardEvent } from "react";

/** Vlastnosti pro řádek `<tr className="pick">`: dosažitelný klávesou Tab, Enter / mezerník = klik.
 *  Klávesa z vnořeného tlačítka nebo pole (cíl události není řádek sám) se ignoruje. */
export function rowPick(onPick: () => void, selected?: boolean) {
  return {
    tabIndex: 0,
    onClick: onPick,
    onKeyDown: (e: KeyboardEvent<HTMLElement>) => {
      if (e.target !== e.currentTarget) return;
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onPick(); }
    },
    "aria-selected": selected,
  };
}
