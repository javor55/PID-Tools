// Karta hlavní plochy podle návrhu: nadpis 15 px tučně, „?“ s nápovědou, volitelně akce / legenda vpravo.
import { type ReactNode, useRef } from "react";
import { useT } from "../i18n";
import { copyText, tableToTsv } from "../lib/clipboard";
import { Help } from "./Ui";
import { toastError, useToasts } from "./Toasts";
import "../styles/state.css";

/** Tlačítko „Copy table“: zkopíruje tabulku (TSV) a potvrdí toastem; chyba se hlásí toastem. */
export function CopyTableButton({ target, className }: { target: () => HTMLTableElement | null; className?: string }) {
  const T = useT();
  const go = () => {
    const t = target();
    if (!t) return;
    copyText(tableToTsv(t))
      .then(() => useToasts.getState().push({ kind: "ok", text: T("copied") }))
      .catch(toastError);
  };
  return (
    <button type="button" className={"btn copybtn" + (className ? " " + className : "")} data-testid="copy-table"
      aria-label={T("copy_table")} title={T("copy_table")} onClick={go}>⧉ {T("copy_table")}</button>
  );
}

/** Cíl tlačítka „Copy table“: první tabulka v obsahu prvku. */
export const firstTable = (el: HTMLElement | null) => el?.querySelector<HTMLTableElement>("table") ?? null;

export function Card({ title, help, right, children, testid, className, busy, copy }: {
  title?: ReactNode; help?: string; right?: ReactNode; children: ReactNode; testid?: string; className?: string;
  copy?: boolean; // v hlavičce tlačítko „Copy table“ (první tabulka karty)
  busy?: boolean; // probíhá přepočet: pruh průběhu a ztlumený obsah po 300 ms
}) {
  const ref = useRef<HTMLElement>(null);
  return (
    <section ref={ref} className={"card dcard" + (className ? " " + className : "") + (busy ? " is-busy" : "")}
      data-testid={testid} aria-busy={busy ? "true" : undefined}>
      {(title || right || copy) && (
        <div className="dhead">
          {title && <h2>{title}{help && <Help text={help} />}</h2>}
          {(right || copy) && <span className="dright">{copy && <CopyTableButton target={() => firstTable(ref.current)} />}{right}</span>}
        </div>)}
      {children}
    </section>
  );
}
