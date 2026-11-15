// Karta hlavní plochy podle návrhu: nadpis 15 px tučně, „?“ s nápovědou, volitelně akce / legenda vpravo.
import type { ReactNode } from "react";
import { Help } from "./Ui";
import "../styles/state.css";

export function Card({ title, help, right, children, testid, className, busy }: {
  title?: ReactNode; help?: string; right?: ReactNode; children: ReactNode; testid?: string; className?: string;
  busy?: boolean; // probíhá přepočet: pruh průběhu a ztlumený obsah po 300 ms
}) {
  return (
    <section className={"card dcard" + (className ? " " + className : "") + (busy ? " is-busy" : "")}
      data-testid={testid} aria-busy={busy ? "true" : undefined}>
      {(title || right) && (
        <div className="dhead">
          {title && <h2>{title}{help && <Help text={help} />}</h2>}
          {right && <span className="dright">{right}</span>}
        </div>)}
      {children}
    </section>
  );
}
