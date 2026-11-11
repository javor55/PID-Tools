// Společné prvky vzhledu podle návrhu (artefakt „PID Tools – nový návrh UI“): karta panelu, přepínač, nápověda „?“.
import { type ReactNode, useId, useRef, useState } from "react";
import { useTexts } from "../i18n";
import { useUi } from "../store";

/**
 * Karta pravého panelu: sbalitelná (▾), nadpis, volitelně „?“ s nápovědou. „Rozbalit vše / Sbalit vše“ nad panelem
 * pošle příkaz všem kartám (store.sideCmd); jinak si každá drží vlastní stav.
 */
export function SideCard({ title, help, children, testid, defaultOpen = true, aside }: {
  title: ReactNode; help?: string; children: ReactNode; testid?: string; defaultOpen?: boolean; aside?: ReactNode;
}) {
  const cmd = useUi((s) => s.sideCmd);
  // vlastní stav karty platí, dokud nepřijde nový příkaz „Rozbalit / Sbalit vše“ (cmd.n se změní)
  const [st, setSt] = useState({ open: defaultOpen, n: cmd.n });
  const open = st.n === cmd.n ? st.open : cmd.open;
  return (
    <details className="scard" open={open} data-testid={testid}
      onToggle={(e) => setSt({ open: (e.currentTarget as HTMLDetailsElement).open, n: cmd.n })}>
      <summary title={title && typeof title === "string" ? title : undefined}>
        <span className="chev" aria-hidden="true">▾</span>
        <h2>{title}</h2>
        {help && <Help text={help} />}
        {aside}
      </summary>
      <div className="scard-body">{children}</div>
    </details>
  );
}

/**
 * Kulaté „?“ s nápovědou k popisku pole: tlačítko (aria-label + title), kliknutí nebo Enter / mezerník otevře bublinu,
 * Esc nebo opuštění ji zavře. `text` je klíč překladu nebo rovnou text. Bublina je `position: fixed` (neořízne ji karta).
 */
export function LabelHelp({ text }: { text: string }) {
  const texts = useTexts();
  const t = texts?.[text] ?? text;
  const [pos, setPos] = useState<{ x: number; y: number } | null>(null);
  const id = useId();
  const btn = useRef<HTMLButtonElement>(null);
  if (!t) return null;
  const close = () => setPos(null);
  const toggle = () => {
    if (pos) return close();
    const r = btn.current?.getBoundingClientRect();
    if (r) setPos({ x: Math.max(8, Math.min(r.left, window.innerWidth - 328)), y: r.bottom + 6 });
  };
  return (
    <span className="qm-wrap">
      <button ref={btn} type="button" className="qm" aria-label={t} title={t} aria-expanded={pos !== null} aria-describedby={pos ? id : undefined}
        data-help="" onClick={toggle} onBlur={close} onKeyDown={(e) => { if (e.key === "Escape" && pos) { e.stopPropagation(); e.preventDefault(); close(); } }}>?</button>
      {pos && <span id={id} role="tooltip" className="qm-bubble" style={{ left: pos.x, top: pos.y }}>{t}</span>}
    </span>
  );
}

/** Starší název: „?“ s nápovědou (např. v nadpisu karty). */
export function Help({ text }: { text: string }) {
  return <LabelHelp text={text} />;
}

/** Přepínač (segmented control): jedna volba z několika, aktivní modře. */
export function Seg<V extends string | number>({ value, options, onChange, label, fmt, stretch, testid, small, titles, help }: {
  value: V; options: readonly V[]; onChange: (v: V) => void; label: string; fmt?: (v: V) => ReactNode;
  stretch?: boolean; testid?: string; small?: boolean; titles?: (v: V) => string | undefined;
  help?: string;                      // klíč překladu / text nápovědy: „?“ za přepínačem (a title skupiny)
}) {
  const texts = useTexts();
  const ht = help ? (texts?.[help] ?? help) : undefined;
  const group = (
    <div role="group" aria-label={label} title={ht} className={"seg" + (stretch ? " stretch" : "") + (small ? " small" : "")}
      data-testid={testid}>
      {options.map((o) => (
        <button key={String(o)} type="button" aria-pressed={o === value} title={titles?.(o)}
          data-value={String(o)} onClick={() => { if (o !== value) onChange(o); }}>
          {fmt ? fmt(o) : String(o)}
        </button>
      ))}
    </div>
  );
  if (!help) return group;
  return <span className={"seg-help" + (stretch ? " stretch" : "")}>{group}<LabelHelp text={help} /></span>;
}

/** Hlavní tlačítko záložky nahoře v panelu (např. „Identifikovat model“). */
export function PrimaryAction({ children, onClick, disabled, testid, title }: {
  children: ReactNode; onClick: () => void; disabled?: boolean; testid?: string; title?: string;
}) {
  return (
    <button type="button" className="btn primary big" onClick={onClick} disabled={disabled} data-testid={testid}
      title={title}>{children}</button>
  );
}

// ---- jednoduchý markdown průvodců (odstavce, odrážky, číslování, **tučně**, *kurzíva*, `kód`)
function inline(s: string, key = 0): ReactNode[] {
  const out: ReactNode[] = [];
  const re = /(\*\*[^*]+\*\*|\*[^*\s][^*]*\*|`[^`]+`)/g;
  let last = 0, m: RegExpExecArray | null, i = 0;
  while ((m = re.exec(s))) {
    if (m.index > last) out.push(s.slice(last, m.index));
    const t = m[0];
    const k = `${key}-${i++}`;
    out.push(t.startsWith("**") ? <b key={k}>{t.slice(2, -2)}</b> : t.startsWith("`") ? <code key={k}>{t.slice(1, -1)}</code>
      : <i key={k}>{t.slice(1, -1)}</i>);
    last = m.index + t.length;
  }
  if (last < s.length) out.push(s.slice(last));
  return out;
}

// ---- tabulky v zápisu GitHub: záhlaví | oddělovač |---|:---:|---:| | řádky (zarovnání je volitelné)
const SEP = /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/;

function cells(line: string): string[] {
  const t = line.trim().replace(/^\|/, "").replace(/(?<!\\)\|$/, "");
  return t.split(/(?<!\\)\|/).map((c) => c.replace(/\\\|/g, "|").trim());
}

type Align = "left" | "center" | "right" | undefined;
const alignOf = (c: string): Align => (c.startsWith(":") && c.endsWith(":") ? "center" : c.endsWith(":") ? "right" : c.startsWith(":") ? "left" : undefined);

function Table({ head, align, rows, k }: { head: string[]; align: Align[]; rows: string[][]; k: number }) {
  return (
    <div className="md-table" key={k}>
      <table>
        <thead><tr>{head.map((h, i) => <th key={i} style={{ textAlign: align[i] }}>{inline(h, i)}</th>)}</tr></thead>
        <tbody>{rows.map((r, ri) => (
          <tr key={ri}>{head.map((_, i) => <td key={i} style={{ textAlign: align[i] }}>{inline(r[i] ?? "", i)}</td>)}</tr>))}</tbody>
      </table>
    </div>
  );
}

function textBlock(lines: string[], bi: number): ReactNode {
  if (!lines.length) return null;
  if (lines.every((l) => /^\s*[-*] /.test(l)))
    return <ul key={bi}>{lines.map((l, i) => <li key={i}>{inline(l.replace(/^\s*[-*] /, ""), i)}</li>)}</ul>;
  if (lines.every((l) => /^\s*\d+\. /.test(l)))
    return <ol key={bi}>{lines.map((l, i) => <li key={i}>{inline(l.replace(/^\s*\d+\. /, ""), i)}</li>)}</ol>;
  return <p key={bi}>{lines.map((l, i) => <span key={i}>{i > 0 && <br />}{inline(l, i)}</span>)}</p>;
}

/** Blok řádků → uzly: tabulky (záhlaví + oddělovač) a zbytek jako odstavce / seznamy. */
function block(lines: string[], bi: number): ReactNode[] {
  const out: ReactNode[] = [];
  let buf: string[] = [];
  const flush = () => { if (buf.length) out.push(textBlock(buf, bi * 1000 + out.length)); buf = []; };
  for (let i = 0; i < lines.length; i++) {
    if (/^#+ /.test(lines[i])) {
      flush();
      out.push(<h4 key={bi * 1000 + out.length}>{inline(lines[i].replace(/^#+ /, ""))}</h4>);
      continue;
    }
    if (lines[i].includes("|") && i + 1 < lines.length && SEP.test(lines[i + 1]) && lines[i + 1].includes("-")) {
      const head = cells(lines[i]);
      const sep = cells(lines[i + 1]);
      if (sep.length === head.length) {
        flush();
        const rows: string[][] = [];
        let j = i + 2;
        while (j < lines.length && lines[j].includes("|")) rows.push(cells(lines[j++]));
        out.push(<Table key={bi * 1000 + out.length} k={bi} head={head} align={sep.map(alignOf)} rows={rows} />);
        i = j - 1;
        continue;
      }
    }
    buf.push(lines[i]);
  }
  flush();
  return out;
}

export function Md({ text }: { text: string }) {
  const blocks = text.replace(/\r/g, "").split(/\n\s*\n/);
  return <div className="md">{blocks.map((b, bi) => block(b.split("\n").filter((l) => l.trim()), bi))}</div>;
}
