// Zástupné hodnoty textů ve tvaru Pythonu (pidtools/i18n/*.json): {název}, {název:.4g}, {název:.0f}, {název:g}.
// Stejný výsledek jako str.format v Pythonu pro formáty, které texty používají (test v tests/format.test.ts).

function fmtG(x: number, prec: number): string {
  if (!Number.isFinite(x)) return Number.isNaN(x) ? "nan" : x > 0 ? "inf" : "-inf";
  if (x === 0) return "0";
  const p = Math.max(prec, 1);
  const exp = Math.floor(Math.log10(Math.abs(x)));
  let s: string;
  if (exp < -4 || exp >= p) {
    s = x.toExponential(p - 1);
    let [m, e] = s.split("e");
    if (m.includes(".")) m = m.replace(/0+$/, "").replace(/\.$/, "");
    const n = parseInt(e, 10);
    e = (n < 0 ? "-" : "+") + String(Math.abs(n)).padStart(2, "0");
    return `${m}e${e}`;
  }
  s = x.toFixed(Math.max(p - 1 - exp, 0));
  if (s.includes(".")) s = s.replace(/0+$/, "").replace(/\.$/, "");
  return s;
}

export function formatValue(v: unknown, spec: string): string {
  if (!spec) return String(v);
  const m = /^\.?(\d*)([fg])?$/.exec(spec);
  if (!m || typeof v !== "number") return String(v);
  const prec = m[1] === "" ? (m[2] === "f" ? 6 : 6) : parseInt(m[1], 10);
  if (m[2] === "f") return v.toFixed(prec);
  return fmtG(v, prec);
}

export function format(text: string, args: Record<string, unknown> = {}): string {
  return text.replace(/\{(\w+)(?::([^}]*))?\}/g, (whole, name: string, spec?: string) =>
    name in args ? formatValue(args[name], spec ?? "") : whole,
  );
}

/** Doba čitelně jako app.timefmt.dur: 45 s, 12.5 min, 2 h 05 min; dec = desetinný oddělovač. */
export function dur(sec: number | null | undefined, dec = "."): string {
  if (sec === null || sec === undefined || !Number.isFinite(sec)) return "–";
  const a = Math.abs(sec);
  const d = (s: string) => (dec === "," ? s.replace(".", ",") : s);
  if (a < 120) return d(`${formatValue(sec, ".3g")} s`);
  if (a < 2 * 3600) return d(`${formatValue(sec / 60, ".3g")} min`);
  const tot = Math.round(a / 60), h = Math.floor(tot / 60), m = tot % 60;
  return `${sec < 0 ? "-" : ""}${h} h ${String(m).padStart(2, "0")} min`;
}
