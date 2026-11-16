// Schránka (FEATURE-002): kopírování textu a tabulky ve formátu TSV (vloží se do Excelu po buňkách).

/** Záloha pro nezabezpečený kontext (bez navigator.clipboard): skrytý textarea + execCommand("copy"). */
function copyViaTextarea(text: string): void {
  const ta = document.createElement("textarea");
  ta.value = text;
  ta.setAttribute("readonly", "");
  ta.setAttribute("aria-hidden", "true");
  ta.style.cssText = "position:fixed;left:-9999px;top:0;opacity:0";
  const prev = document.activeElement instanceof HTMLElement ? document.activeElement : null;
  document.body.appendChild(ta);
  try {
    ta.select();
    if (!document.execCommand("copy")) throw new Error("Clipboard copy failed");
  } finally {
    ta.remove();
    prev?.focus();
  }
}

/** Zkopíruje text do schránky; při chybě vyhodí výjimku (volající ji hlásí uživateli). */
export async function copyText(text: string): Promise<void> {
  if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text);
      return;
    } catch {
      // oprávnění zamítnuto nebo nezabezpečený kontext: zkusí se záloha, její chyba se vyhodí dál
    }
  }
  copyViaTextarea(text);
}

const cellText = (c: HTMLElement): string => (c.innerText ?? c.textContent ?? "").replace(/[\t\r\n]+/g, " ").trim();

/** Tabulka jako TSV: řádky thead + tbody (ne tfoot), skryté řádky se vynechají. */
export function tableToTsv(table: HTMLTableElement): string {
  const rows: HTMLTableRowElement[] = [];
  for (const sec of Array.from(table.children)) {
    if (sec.tagName === "THEAD" || sec.tagName === "TBODY") rows.push(...Array.from((sec as HTMLTableSectionElement).rows));
  }
  return rows
    .filter((r) => getComputedStyle(r).display !== "none")
    .map((r) => Array.from(r.cells).map(cellText).join("\t"))
    .join("\n");
}
