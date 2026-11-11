// Společné prvky vzhledu podle návrhu (artefakt „PID Tools – nový návrh UI“): karta panelu, přepínač, nápověda „?“.
import { type ReactNode, useState } from "react";
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

/** Kulatý „?“ s nápovědou v bublině (title) – jako u polí v návrhu. */
export function Help({ text }: { text: string }) {
  return <span className="qm" role="img" aria-label={text} title={text}>?</span>;
}

/** Přepínač (segmented control): jedna volba z několika, aktivní modře. */
export function Seg<V extends string | number>({ value, options, onChange, label, fmt, stretch, testid, small, titles }: {
  value: V; options: readonly V[]; onChange: (v: V) => void; label: string; fmt?: (v: V) => ReactNode;
  stretch?: boolean; testid?: string; small?: boolean; titles?: (v: V) => string | undefined;
}) {
  return (
    <div role="group" aria-label={label} className={"seg" + (stretch ? " stretch" : "") + (small ? " small" : "")}
      data-testid={testid}>
      {options.map((o) => (
        <button key={String(o)} type="button" aria-pressed={o === value} title={titles?.(o)}
          data-value={String(o)} onClick={() => { if (o !== value) onChange(o); }}>
          {fmt ? fmt(o) : String(o)}
        </button>
      ))}
    </div>
  );
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

export function Md({ text }: { text: string }) {
  const blocks = text.replace(/\r/g, "").split(/\n\s*\n/);
  return (
    <div className="md">
      {blocks.map((b, bi) => {
        const lines = b.split("\n").filter((l) => l.trim());
        if (lines.length && lines.every((l) => /^\s*[-*] /.test(l)))
          return <ul key={bi}>{lines.map((l, i) => <li key={i}>{inline(l.replace(/^\s*[-*] /, ""), i)}</li>)}</ul>;
        if (lines.length && lines.every((l) => /^\s*\d+\. /.test(l)))
          return <ol key={bi}>{lines.map((l, i) => <li key={i}>{inline(l.replace(/^\s*\d+\. /, ""), i)}</li>)}</ol>;
        if (/^#+ /.test(b)) return <h4 key={bi}>{inline(b.replace(/^#+ /, ""))}</h4>;
        return <p key={bi}>{lines.map((l, i) => <span key={i}>{i > 0 && <br />}{inline(l, i)}</span>)}</p>;
      })}
    </div>
  );
}
