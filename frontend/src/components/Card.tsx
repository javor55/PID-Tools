// Karta hlavní plochy podle návrhu: nadpis 15 px tučně, „?“ s nápovědou, volitelně akce / legenda vpravo.
import type { ReactNode } from "react";
import { Help } from "./Ui";

export function Card({ title, help, right, children, testid, className }: {
  title?: ReactNode; help?: string; right?: ReactNode; children: ReactNode; testid?: string; className?: string;
}) {
  return (
    <section className={"card dcard" + (className ? " " + className : "")} data-testid={testid}>
      {(title || right) && (
        <div className="dhead">
          {title && <h2>{title}{help && <Help text={help} />}</h2>}
          {right && <span className="dright">{right}</span>}
        </div>)}
      {children}
    </section>
  );
}
