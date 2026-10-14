/*
 * Prohlížeč záznamu (záložka Data) – běží přímo ve stránce (st.components.v2).
 *
 * Všechny signály ze souboru (bez převzorkování) v panelech pod sebou se společnou časovou osou; v panelu má každý
 * signál vlastní osu Y (nebo jednu sdílenou). Ovládání:
 *   kolečko = zoom času, Shift + kolečko = zoom Y panelu, kolečko nad osou Y = zoom té osy;
 *   tažení = posun času (Shift = posun Y), tažení osy Y = posun té osy; režimy Zoom ⬚ / X / Y = výběr obdélníkem;
 *   dvojklik = celý čas a automatické Y panelu (na ose jen ta osa); Backspace = zpět; ←/→ = posun kurzoru o vzorek.
 * Kurzory jako na osciloskopu: C1 / C2 (čas, hodnoty, Δ, Δ/Δt, min / max / průměr / σ mezi nimi) a vodorovné H1 / H2
 * pro zvolený signál. Tabulka hodnot zobrazeného úseku (klik = kurzor C1), export CSV výřezu nebo úseku mezi kurzory.
 *
 * Data z Pythonu: key, sig, view_key, sigs [{name, role, color, unit, ti, off, n}], times [{off, n}], T, decim, hash,
 * url + base (binární soubor) nebo b64, clock (ms epochy pro t = 0 nebo null), tunit, dec, dark, txt, fname,
 * layout (JSON text uloženého rozložení nebo null). Do Pythonu: stav „layout“ (JSON text).
 */
export default function (component) {
  "use strict";
  const D = component.data, root = component.parentElement, X = D.txt || {};
  const reg = (window.__pidView = window.__pidView || {});
  const prev = reg[D.key];
  if (prev && prev.sig === D.sig && prev.box && prev.box.isConnected && root.contains(prev.box)) {
    if (D.layout && D.layout !== prev.lastLay && prev.applyLayout) prev.applyLayout(D.layout);
    return;
  }
  root.querySelectorAll(".pidv").forEach((n) => n.remove());
  if (prev) {
    if (prev.ro) prev.ro.disconnect();
    if (prev.box && prev.box.isConnected) prev.box.remove();
  }

  // ------------------------------------------------------------------ pomocné
  const el = (tag, cls, html) => {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (html !== undefined) e.innerHTML = html;
    return e;
  };
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
  const dc = (s) => (D.dec === "," ? s.replace(".", ",") : s);
  const pad2 = (n) => String(n).padStart(2, "0");
  const lb = (a, x, n) => {                 // první index s a[i] >= x
    let lo = 0, hi = n;
    while (lo < hi) { const m = (lo + hi) >> 1; if (a[m] < x) lo = m + 1; else hi = m; }
    return lo;
  };
  function nearest(s, t) {
    if (!s.n) return -1;
    const i = lb(s.t, t, s.n);
    if (i <= 0) return 0;
    if (i >= s.n) return s.n - 1;
    return t - s.t[i - 1] <= s.t[i] - t ? i - 1 : i;
  }
  function nice(span, n) {
    const raw = span / Math.max(1, n), e = Math.pow(10, Math.floor(Math.log10(raw)));
    for (const m of [1, 2, 2.5, 5, 10]) if (m * e >= raw * (1 - 1e-9)) return m * e;
    return 10 * e;
  }
  const decFor = (step) => Math.max(0, Math.min(9, -Math.floor(Math.log10(step) + 1e-9) + (String(step / Math.pow(10, Math.floor(Math.log10(step)))).startsWith("2.5") ? 1 : 0)));
  const fmtTick = (v, step) => dc((Math.abs(v) < step * 1e-6 ? 0 : v).toFixed(decFor(step)));
  function fmtV(v, s) {
    if (v === null || v === undefined || !isFinite(v)) return "–";
    const d = s && s.dec !== undefined ? s.dec : 4;
    return dc(v.toFixed(d));
  }
  const fmtG = (v, p) => (v === null || !isFinite(v) ? "–" : dc(String(+v.toPrecision(p || 5))));
  const U = { s: 1, min: 60, h: 3600 };
  const unitFor = (span) => (D.tunit in U ? D.tunit : span <= 1200 ? "s" : span <= 72000 ? "min" : "h");
  function clockStr(s, mode) {             // mode: "tick" | "full"
    const d = new Date(D.clock + s * 1000);
    const hms = `${d.getUTCHours()}:${pad2(d.getUTCMinutes())}:${pad2(d.getUTCSeconds())}`;
    const ms = d.getUTCMilliseconds();
    if (mode === "full") return `${d.getUTCDate()}.${d.getUTCMonth() + 1}.${d.getUTCFullYear()} ${hms}` + (ms ? dc("." + String(ms).padStart(3, "0")) : "");
    return hms;
  }
  function fmtT(s) {                         // čas bodu (kurzor, tabulka)
    if (D.clock !== null && D.clock !== undefined) return clockStr(s, "full");
    const u = unitFor(S.view[1] - S.view[0]);
    const d = clamp(Math.ceil(-Math.log10(MIN_DT / U[u])) + 1, 0, 7);
    return `${dc((s / U[u]).toFixed(d))} ${u}`;
  }
  function fmtDur(dt, p) {                   // délka (Δt); p = platné číslice sekund
    const a = Math.abs(dt), sg = dt < 0 ? "−" : "";
    if (a < 120) return sg + fmtG(a, p || 6) + " s";
    if (a < 7200) return `${sg}${Math.floor(a / 60)} min ${fmtG(a % 60, 4)} s`;
    if (a < 172800) return `${sg}${Math.floor(a / 3600)} h ${Math.floor((a % 3600) / 60)} min ${Math.round(a % 60)} s`;
    return `${sg}${Math.floor(a / 86400)} d ${Math.floor((a % 86400) / 3600)} h ${Math.round((a % 3600) / 60)} min`;
  }

  // ------------------------------------------------------------------ kostra a načtení dat
  const box = el("div", "pidv" + (D.dark ? " dark" : ""));
  box.tabIndex = 0;
  root.appendChild(box);
  const me = (reg[D.key] = { sig: D.sig, box, lastLay: null });
  const DC = (window.__pidViewData = window.__pidViewData || {});

  async function fetchBuf() {
    if (DC[D.hash]) return DC[D.hash];
    let buf;
    if (D.b64) {
      const bin = atob(D.b64), u8 = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) u8[i] = bin.charCodeAt(i);
      buf = u8.buffer;
    } else {
      const rel = String(D.url).replace(/^\//, "");
      const dir = location.pathname.replace(/[^/]*$/, "");
      const cands = [dir + rel, (D.base ? "/" + D.base : "") + "/" + rel, D.url];
      let err = null;
      for (const u of [...new Set(cands)]) {
        try {
          const r = await fetch(u, { credentials: "same-origin" });
          if (r.ok) { buf = await r.arrayBuffer(); break; }
          err = new Error(r.status + " " + u);
        } catch (e) { err = e; }
      }
      if (!buf) throw err || new Error("fetch");
    }
    for (const k of Object.keys(DC)) delete DC[k];        // v paměti jen jeden záznam
    DC[D.hash] = { buf, sigs: {} };
    return DC[D.hash];
  }

  function load() {
    const msg = el("div", "pidv-card pidv-err", esc(X.loading || "…"));
    msg.style.color = "var(--pv-muted)";
    box.appendChild(msg);
    fetchBuf().then((entry) => {
      msg.remove();
      try { start(entry); } catch (e) { console.error(e); box.appendChild(el("div", "pidv-card pidv-err", esc(String(e)))); }
    }).catch((e) => {
      console.error(e);
      msg.style.color = "";
      msg.innerHTML = `${esc(X.load_err || "Error")} <button class="pidv-btn">${esc(X.retry || "↻")}</button>`;
      msg.querySelector("button").onclick = () => { msg.remove(); load(); };
    });
  }
  load();

  let S;                                  // stav (rozložení) – viz defaults()
  let MIN_DT = 1;                         // nejmenší perioda vzorků (počet desetinných míst času)
  function start(entry) {
    // ---------------------------------------------------------------- signály
    const SG = {}, order = [], AN = window.PIDViewAn;
    function initSig(s) {                     // perioda, práh výpadku, rozsah a počet desetinných míst
      if (s.gap !== undefined) return s;
      const k = Math.max(1, Math.floor(s.n / 2000)), dd = [];
      for (let i = k; i < s.n; i += k) dd.push(s.t[i] - s.t[i - 1]);
      dd.sort((a, b) => a - b);
      s.dt = dd.length ? Math.max(dd[dd.length >> 1], 1e-9) : 1;
      s.gap = Math.max(10 * s.dt, D.T * 1e-4) * Math.max(1, D.decim * 2);
      const r = mm(s, 0, s.n), span = r ? Math.max(r[1] - r[0], Math.max(Math.abs(r[0]), Math.abs(r[1])) * 0.1, 1e-9) : 1;
      s.lo0 = r ? r[0] : 0; s.hi0 = r ? r[1] : 1;
      s.dec = Math.max(0, Math.min(8, Math.ceil(-Math.log10(span)) + 3));
      return s;
    }
    for (const d of D.sigs) {
      const tt = D.times[d.ti];
      const s = entry.sigs[d.name] || (entry.sigs[d.name] = {
        t: new Float64Array(entry.buf, tt.off, tt.n), v: new Float32Array(entry.buf, d.off, d.n), n: d.n,
      });
      Object.assign(s, { name: d.name, role: d.role, color0: d.color, unit0: d.unit, ti: d.ti });
      SG[d.name] = initSig(s);
      order.push(d.name);
    }
    const nFile = order.length;
    if (!order.length) { box.appendChild(el("div", "pidv-card pidv-err", esc(X.no_sig || "–"))); return; }
    const minDt = Math.min(...order.map((n) => SG[n].dt));
    MIN_DT = minDt;
    const MINSPAN = Math.max(minDt * 5, D.T * 1e-9, 1e-6);

    // ---- vypočtené signály (vzorce) – po souborových, v pořadí zadání; může odkazovat jen na předchozí
    const CALC_COLORS = ["#0f766e", "#9333ea", "#b45309", "#be123c", "#1d4ed8", "#4d7c0f"];
    let calcErr = {}, events = null;
    function cleanCalc(list) {
      const out = [], names = new Set(order.slice(0, nFile));
      for (const c of Array.isArray(list) ? list.slice(0, 30) : []) {
        if (!c || typeof c.name !== "string" || typeof c.expr !== "string") continue;
        const name = c.name.trim().slice(0, 40);
        if (!name || names.has(name)) continue;
        names.add(name);
        out.push({ name, expr: c.expr.slice(0, 1000), unit: typeof c.unit === "string" ? c.unit.slice(0, 20) : "" });
      }
      return out;
    }
    function exprMsg(e) {
      if (!(e instanceof AN.ExprError)) return String(e && e.message || e);
      return (X["e_" + e.msg] || e.msg).replace("{a}", e.arg === undefined ? "" : e.arg) + ` (${X.e_pos || "@"} ${e.pos + 1})`;
    }
    function computeCalc(list) {
      for (const n of order.splice(nFile)) delete SG[n];
      calcErr = {};
      events = null;
      list.forEach((c, k) => {
        try {
          const P = AN.parse(c.expr, order);
          const base = P.refs.length ? P.refs.reduce((a, n) => (SG[n].n > SG[a].n ? n : a), P.refs[0])
            : order.slice(0, nFile).reduce((a, n) => (SG[n].n > SG[a].n ? n : a), order[0]);
          const b = SG[base], t = b.t, n = b.n;
          const cache = {};
          const sig = (nm) => cache[nm] || (cache[nm] = SG[nm].t === t ? Float64Array.from(SG[nm].v) : AN.zoh(SG[nm], t));
          const y = AN.evaluate(P.ast, { t, n, sig });
          let m = 0;
          for (let i = 0; i < n; i++) if (isFinite(y[i])) m++;
          if (m < 2) throw new Error(X.e_empty_res || "–");
          const tt = new Float64Array(m), vv = new Float32Array(m);
          for (let i = 0, j = 0; i < n; i++) if (isFinite(y[i])) { tt[j] = t[i]; vv[j] = y[i]; j++; }
          SG[c.name] = initSig({ t: tt, v: vv, n: m, name: c.name, role: "ƒ", color0: CALC_COLORS[k % CALC_COLORS.length],
                                 unit0: c.unit, ti: "c:" + c.name, calc: true });
          order.push(c.name);
        } catch (e) {
          calcErr[c.name] = exprMsg(e);
        }
      });
    }

    // ---------------------------------------------------------------- stav a rozložení
    function defaults() {
      const by = (r) => order.filter((n) => SG[n].role === r);
      const panels = [];
      const pv = by("PV").concat(by("SP")), mv = by("MV").concat(by("POS")), dv = by("DV");
      if (pv.length) panels.push({ sigs: pv, h: 230 });
      if (mv.length) panels.push({ sigs: mv, h: 150 });
      if (dv.length) panels.push({ sigs: dv, h: 150 });
      if (!panels.length) order.slice(0, 3).forEach((n, i) => panels.push({ sigs: [n], h: i ? 150 : 220 }));
      return { v: 1, panels: panels.map((p) => Object.assign({ shared: false, lo: null, hi: null }, p)), sig: {},
               view: [0, D.T], cur: { on: false, a: null, b: null }, hc: { on: false, a: null, b: null, sig: null },
               tab: false, list: true, mode: "pan", ya: "view", step: false, act: null, calc: [],
               an: null, evk: { mv: true, sp: true, dv: true, state: true, sat: true, flat: true, gap: true },
               stp: { u: null, y: null }, cor: { y: null, mode: "auto", lag: null }, xy: { x: null, y: null, line: false },
               cmp: { sigs: [], segs: [], rel: true } };
    }
    const num = (v) => (typeof v === "number" && isFinite(v) ? v : null);
    function sanitize(L) {
      const calc = cleanCalc(L && L.calc);
      computeCalc(calc);
      const d = Object.assign(defaults(), { calc });
      if (!L || typeof L !== "object" || !Array.isArray(L.panels)) return d;
      const used = new Set(), panels = [];
      for (const p of L.panels.slice(0, 30)) {
        if (!p || !Array.isArray(p.sigs)) continue;
        const sg = p.sigs.filter((n) => typeof n === "string" && SG[n] && !used.has(n) && used.add(n));
        if (!sg.length) continue;
        let lo = num(p.lo), hi = num(p.hi);
        if (lo === null || hi === null || !(hi > lo)) lo = hi = null;
        panels.push({ sigs: sg, h: clamp(num(p.h) || 160, 70, 900), shared: !!p.shared, lo, hi });
      }
      const out = Object.assign(d, { panels: panels.length ? panels : d.panels });
      if (L.sig && typeof L.sig === "object") for (const n in L.sig) {
        if (!SG[n] || !L.sig[n] || typeof L.sig[n] !== "object") continue;
        const q = L.sig[n], o = {};
        if (typeof q.c === "string" && /^#[0-9a-fA-F]{6}$/.test(q.c)) o.c = q.c;
        if (typeof q.u === "string") o.u = q.u.slice(0, 20);
        const lo = num(q.lo), hi = num(q.hi);
        if (lo !== null && hi !== null && hi > lo) { o.lo = lo; o.hi = hi; }
        out.sig[n] = o;
      }
      if (Array.isArray(L.view) && num(L.view[0]) !== null && num(L.view[1]) !== null && L.view[1] > L.view[0]) out.view = [L.view[0], L.view[1]];
      if (L.cur && typeof L.cur === "object") out.cur = { on: !!L.cur.on, a: num(L.cur.a), b: num(L.cur.b) };
      if (L.hc && typeof L.hc === "object") out.hc = { on: !!L.hc.on, a: num(L.hc.a), b: num(L.hc.b), sig: SG[L.hc.sig] ? L.hc.sig : null };
      for (const k of ["tab", "list", "step"]) if (typeof L[k] === "boolean") out[k] = L[k];
      if (["pan", "box", "x", "y"].includes(L.mode)) out.mode = L.mode;
      if (["view", "all"].includes(L.ya)) out.ya = L.ya;
      if (typeof L.act === "string" && SG[L.act]) out.act = L.act;
      if (["ev", "step", "corr", "xy", "cmp"].includes(L.an)) out.an = L.an;
      if (L.evk && typeof L.evk === "object") for (const k in out.evk) if (typeof L.evk[k] === "boolean") out.evk[k] = L.evk[k];
      const sgn = (v) => (typeof v === "string" && SG[v] ? v : null);
      if (L.stp && typeof L.stp === "object") out.stp = { u: sgn(L.stp.u), y: sgn(L.stp.y) };
      if (L.cor && typeof L.cor === "object") out.cor = { y: sgn(L.cor.y), mode: ["auto", "incr", "vals", "int"].includes(L.cor.mode) ? L.cor.mode : "auto", lag: num(L.cor.lag) };
      if (L.xy && typeof L.xy === "object") out.xy = { x: sgn(L.xy.x), y: sgn(L.xy.y), line: !!L.xy.line };
      if (L.cmp && typeof L.cmp === "object") out.cmp = {
        sigs: (Array.isArray(L.cmp.sigs) ? L.cmp.sigs : []).filter((n) => sgn(n)).slice(0, 4),
        segs: (Array.isArray(L.cmp.segs) ? L.cmp.segs : []).filter((q) => Array.isArray(q) && num(q[0]) !== null && num(q[1]) !== null && q[1] > q[0]).slice(0, 8),
        rel: L.cmp.rel !== false };
      fixView(out);
      return out;
    }
    function fixView(st) {
      let [a, b] = st.view;
      let L = clamp(b - a, MINSPAN, D.T);
      a = clamp(a, 0, D.T - L);
      st.view = [a, a + L];
    }
    const views = (window.__pidViewState = window.__pidViewState || {});
    let parsed = null;
    if (D.layout) { try { parsed = JSON.parse(D.layout); } catch (e) { parsed = null; } }
    if (parsed) { S = sanitize(parsed); me.lastLay = D.layout; }
    else if (views[D.view_key]) S = sanitize(views[D.view_key]);
    else S = sanitize(null);
    views[D.view_key] = S;

    let saveT = null;
    function save() {                        // rozložení do Pythonu (projekt) – s odstupem, ať se aplikace nespouští stále
      views[D.view_key] = S;
      clearTimeout(saveT);
      saveT = setTimeout(() => {
        const L = JSON.stringify(S);
        if (L === me.lastLay) return;
        me.lastLay = L;
        component.setStateValue("layout", L);
      }, 1500);
    }
    me.applyLayout = (txt) => {
      let L = null;
      try { L = JSON.parse(txt); } catch (e) { return; }
      me.lastLay = txt;
      S = sanitize(L);
      views[D.view_key] = S;
      hist.length = 0; hpos = -1;
      build();
    };

    // ---------------------------------------------------------------- min / max pyramida, součty
    function pyr(s) {
      if (s.P) return s.P;
      const P = [];
      let n = s.n, src = null;
      let mn = new Float32Array(Math.ceil(n / 4)), mx = new Float32Array(Math.ceil(n / 4));
      for (let i = 0, k = 0; i < n; i += 4, k++) {
        let a = Infinity, b = -Infinity;
        for (let j = i; j < Math.min(n, i + 4); j++) { const v = s.v[j]; if (v < a) a = v; if (v > b) b = v; }
        mn[k] = a; mx[k] = b;
      }
      P.push({ mn, mx });
      src = P[0];
      while (src.mn.length > 4) {
        const m = Math.ceil(src.mn.length / 4), a2 = new Float32Array(m), b2 = new Float32Array(m);
        for (let k = 0; k < m; k++) {
          let a = Infinity, b = -Infinity;
          for (let j = 4 * k; j < Math.min(src.mn.length, 4 * k + 4); j++) { if (src.mn[j] < a) a = src.mn[j]; if (src.mx[j] > b) b = src.mx[j]; }
          a2[k] = a; b2[k] = b;
        }
        src = { mn: a2, mx: b2 };
        P.push(src);
      }
      s.P = P;
      return P;
    }
    function mm(s, ja, jb) {                 // min, max na [ja, jb) nebo null
      ja = Math.max(0, ja); jb = Math.min(s.n, jb);
      if (jb <= ja) return null;
      let a = Infinity, b = -Infinity, i = ja;
      const v = s.v;
      if (jb - ja < 64) {
        for (; i < jb; i++) { if (v[i] < a) a = v[i]; if (v[i] > b) b = v[i]; }
        return [a, b];
      }
      const P = pyr(s);
      while (i < jb && (i & 3)) { if (v[i] < a) a = v[i]; if (v[i] > b) b = v[i]; i++; }
      while (i + 4 <= jb) {
        let k = 0, B = 4;
        while (k + 1 < P.length && i % (B * 4) === 0 && i + B * 4 <= jb) { k++; B *= 4; }
        const q = i / B;
        if (P[k].mn[q] < a) a = P[k].mn[q];
        if (P[k].mx[q] > b) b = P[k].mx[q];
        i += B;
      }
      for (; i < jb; i++) { if (v[i] < a) a = v[i]; if (v[i] > b) b = v[i]; }
      return [a, b];
    }
    function sums(s) {
      if (s.cs) return s;
      s.cs = new Float64Array(s.n + 1); s.cq = new Float64Array(s.n + 1);
      const m = s.lo0 + (s.hi0 - s.lo0) / 2;           // posun kvůli přesnosti σ
      for (let i = 0; i < s.n; i++) { const d = s.v[i] - m; s.cs[i + 1] = s.cs[i] + d; s.cq[i + 1] = s.cq[i] + d * d; }
      s.cm = m;
      return s;
    }
    function stats(s, a, b) {               // min, max, průměr, σ mezi časy a, b
      const ja = lb(s.t, Math.min(a, b), s.n), jb = lb(s.t, Math.max(a, b) + 1e-12, s.n);
      if (jb <= ja) return null;
      const r = mm(s, ja, jb);
      sums(s);
      const n = jb - ja, mu = (s.cs[jb] - s.cs[ja]) / n, q = (s.cq[jb] - s.cq[ja]) / n;
      return { min: r[0], max: r[1], mean: mu + s.cm, sd: Math.sqrt(Math.max(0, q - mu * mu)), n };
    }

    // ---------------------------------------------------------------- osy Y
    const colorOf = (n) => (S.sig[n] && S.sig[n].c) || SG[n].color0;
    const unitOf = (n) => (S.sig[n] && S.sig[n].u !== undefined ? S.sig[n].u : SG[n].unit0);
    const sigCfg = (n) => (S.sig[n] = S.sig[n] || {});
    function autoRange(names) {
      let a = Infinity, b = -Infinity;
      for (const n of names) {
        const s = SG[n];
        const r = S.ya === "all" ? [s.lo0, s.hi0] : mm(s, lb(s.t, S.view[0], s.n), lb(s.t, S.view[1], s.n) + 1);
        if (r) { a = Math.min(a, r[0]); b = Math.max(b, r[1]); }
      }
      if (!isFinite(a)) return [0, 1];
      if (b - a < Math.max(Math.abs(a), Math.abs(b), 1e-9) * 1e-9) { const d = Math.abs(a) * 0.01 || 1; a -= d; b += d; }
      const m = 0.06 * (b - a);
      return [a - m, b + m];
    }
    function axesOf(pi) {                    // osy panelu: [{key, names, color, unit, lo, hi, manual}]
      const p = S.panels[pi];
      if (p.shared) {
        const r = p.lo !== null ? [p.lo, p.hi] : autoRange(p.sigs);
        const us = [...new Set(p.sigs.map(unitOf).filter(Boolean))];
        return [{ key: "§" + pi, names: p.sigs, color: "var", unit: us.join(", "), lo: r[0], hi: r[1], manual: p.lo !== null }];
      }
      return p.sigs.map((n) => {
        const c = S.sig[n];
        const man = c && c.lo !== undefined;
        const r = man ? [c.lo, c.hi] : autoRange([n]);
        return { key: n, names: [n], color: colorOf(n), unit: unitOf(n), lo: r[0], hi: r[1], manual: man };
      });
    }
    function setAxis(pi, key, lo, hi) {
      if (!(hi > lo) || !isFinite(lo) || !isFinite(hi)) return;
      if (key[0] === "§") { S.panels[pi].lo = lo; S.panels[pi].hi = hi; }
      else { const c = sigCfg(key); c.lo = lo; c.hi = hi; }
    }
    function clearAxis(pi, key) {
      if (key[0] === "§") { S.panels[pi].lo = S.panels[pi].hi = null; }
      else if (S.sig[key]) { delete S.sig[key].lo; delete S.sig[key].hi; }
    }
    const panelOf = (n) => S.panels.findIndex((p) => p.sigs.includes(n));
    const visible = () => S.panels.flatMap((p) => p.sigs);

    // ---------------------------------------------------------------- historie zoomu
    const hist = [];
    let hpos = -1, lastPush = 0;
    const snap = () => JSON.stringify({ view: S.view, panels: S.panels.map((p) => [p.lo, p.hi]),
      sig: Object.fromEntries(Object.entries(S.sig).filter(([, c]) => c.lo !== undefined).map(([n, c]) => [n, [c.lo, c.hi]])) });
    function push(force) {
      const now = Date.now();
      if (!force && now - lastPush < 700) { lastPush = now; return; }
      lastPush = now;
      const s = snap();
      if (hpos >= 0 && hist[hpos] === s) return;
      hist.splice(hpos + 1);
      hist.push(s);
      if (hist.length > 60) hist.shift();
      hpos = hist.length - 1;
    }
    function restore(s) {
      const o = JSON.parse(s);
      S.view = o.view;
      for (const n in S.sig) { delete S.sig[n].lo; delete S.sig[n].hi; }
      for (const n in o.sig) { const c = sigCfg(n); c.lo = o.sig[n][0]; c.hi = o.sig[n][1]; }
      o.panels.forEach((q, i) => { if (S.panels[i]) { S.panels[i].lo = q[0]; S.panels[i].hi = q[1]; } });
    }
    function back() {
      const cur = snap();
      if (hpos >= 0 && hist[hpos] !== cur) { hist.splice(hpos + 1); hist.push(cur); hpos = hist.length - 1; }
      if (hpos <= 0) return;
      hpos--;
      restore(hist[hpos]);
      redraw(); save();
    }
    function fwd() {
      if (hpos >= hist.length - 1) return;
      hpos++;
      restore(hist[hpos]);
      redraw(); save();
    }

    // ---------------------------------------------------------------- DOM
    const AXW = 50, R = 12, TOP = 8, BOT = 6;
    let bar, body, listBox, plots, xcv, nav, readBox, anBox, tabBox, tip, panelsUI = [], L = AXW;

    function build() {
      box.innerHTML = "";
      box.classList.toggle("dark", !!D.dark);
      buildBar();
      body = el("div", "pidv-body" + (S.list ? "" : " nolist"));
      listBox = el("div", "pidv-card pidv-list");
      if (S.list) body.appendChild(listBox);
      plots = el("div", "pidv-plots");
      body.appendChild(plots);
      box.appendChild(body);
      readBox = el("div", "pidv-card pidv-read");
      anBox = el("div", "pidv-card pidv-an");
      tabBox = el("div", "pidv-card pidv-read");
      box.append(readBox, anBox, tabBox);
      tip = el("div", "pidv-tip");
      box.appendChild(tip);
      buildList();
      buildPanels();
      renderAn();
      redraw();
      if (!events) setTimeout(() => { evList(); renderAn(); redraw(); }, 30);
    }

    function buildBar() {
      bar = el("div", "pidv-card pidv-bar");
      const seg = (g, items, cur) => `<div class="pidv-seg" data-g="${g}">` + items.map(([v, t, h]) =>
        `<button data-v="${v}" class="${v === cur ? "on" : ""}" title="${esc(h || "")}">${esc(t)}</button>`).join("") + `</div>`;
      bar.innerHTML =
        `<div class="pidv-grp">${seg("mode", [["pan", X.pan], ["box", X.zoom_box], ["x", X.zoom_x], ["y", X.zoom_y]], S.mode)}</div>` +
        `<div class="pidv-grp"><button class="pidv-btn" data-a="back" title="Backspace">◀ ${esc(X.back)}</button>` +
        `<button class="pidv-btn" data-a="fwd">${esc(X.fwd)} ▶</button>` +
        `<button class="pidv-btn" data-a="full">${esc(X.full)}</button></div>` +
        `<div class="pidv-grp"><button class="pidv-btn" data-a="evp" title="${esc(X.ev_prev)}">◀ ⚑</button>` +
        `<button class="pidv-btn" data-a="evn" title="${esc(X.ev_next)}">⚑ ▶</button></div>` +
        `<div class="pidv-grp"><button class="pidv-btn ${S.cur.on ? "on" : ""}" data-a="cur" title="${esc(X.c_hint)}">${esc(X.cur)}</button>` +
        `<button class="pidv-btn ${S.hc.on ? "on" : ""}" data-a="hcur" title="${esc(X.h_hint)}">${esc(X.hcur)}</button></div>` +
        `<div class="pidv-grp"><span class="pidv-lab">${esc(X.yauto)}</span>${seg("ya", [["view", X.ya_view], ["all", X.ya_all]], S.ya)}</div>` +
        `<div class="pidv-grp"><span class="pidv-lab">${esc(X.interp)}</span>${seg("step", [["0", X.line], ["1", X.step]], S.step ? "1" : "0")}</div>` +
        `<div class="pidv-grp"><button class="pidv-btn ${S.list ? "on" : ""}" data-a="list">${esc(X.list)}</button>` +
        `<button class="pidv-btn ${S.tab ? "on" : ""}" data-a="tab">${esc(X.table)}</button>` +
        `<button class="pidv-btn" data-a="csv_view">${esc(X.csv_view)}</button>` +
        `<button class="pidv-btn" data-a="csv_cur" ${S.cur.on ? "" : "disabled"}>${esc(X.csv_cur)}</button>` +
        `<span class="pidv-help" title="${esc(X.help)}">?</span></div>` +
        (D.decim > 1 ? `<span class="pidv-note">${esc(String(X.decim || "").replace("{g}", D.decim))}</span>` : "");
      box.appendChild(bar);
      bar.querySelectorAll('[data-g="mode"] button').forEach((b) => b.onclick = () => { S.mode = b.dataset.v; rebar(); save(); });
      bar.querySelectorAll('[data-g="ya"] button').forEach((b) => b.onclick = () => { S.ya = b.dataset.v; rebar(); redraw(); save(); });
      bar.querySelectorAll('[data-g="step"] button').forEach((b) => b.onclick = () => { S.step = b.dataset.v === "1"; rebar(); redraw(); save(); });
      const act = {
        back, fwd,
        evp: () => evNav(-1),
        evn: () => evNav(1),
        full: () => { push(true); S.view = [0, D.T]; push(true); redraw(); save(); },
        cur: () => { S.cur.on = !S.cur.on; if (S.cur.on) initCursors(); rebar(); redraw(); renderAn(); save(); },
        hcur: () => { S.hc.on = !S.hc.on; if (S.hc.on) initH(); rebar(); redraw(); save(); },
        list: () => { S.list = !S.list; build(); save(); },
        tab: () => { S.tab = !S.tab; rebar(); redraw(); save(); },
        csv_view: () => exportCsv(S.view[0], S.view[1]),
        csv_cur: () => { if (S.cur.on) exportCsv(Math.min(S.cur.a, S.cur.b), Math.max(S.cur.a, S.cur.b)); },
      };
      bar.querySelectorAll("[data-a]").forEach((b) => b.onclick = act[b.dataset.a]);
    }
    function rebar() {
      const old = bar;
      buildBar();
      box.insertBefore(bar, old);
      old.remove();
    }

    // ---- seznam signálů
    const opened = new Set();
    let filter = "";
    function buildList() {
      if (!S.list) return;
      listBox.innerHTML = "";
      const q = el("input");
      q.type = "search";
      q.placeholder = X.search || "";
      q.value = filter;
      q.oninput = () => { filter = q.value; rows(); };
      listBox.appendChild(q);
      const wrap = el("div");
      listBox.appendChild(wrap);
      function rows() {
        wrap.innerHTML = "";
        const f = filter.trim().toLowerCase();
        for (const n of order) {
          if (f && !n.toLowerCase().includes(f)) continue;
          const pi = panelOf(n), on = pi >= 0;
          const r = el("div", "pidv-sig" + (S.act === n ? " act" : ""));
          const opts = S.panels.map((_, i) => `<option value="${i}" ${i === pi ? "selected" : ""}>${esc(X.panel)} ${i + 1}</option>`).join("") +
            `<option value="new">+ ${esc(X.new_panel)}</option>`;
          r.innerHTML = `<input type="checkbox" ${on ? "checked" : ""} title="${esc(X.hide)}">` +
            `<button class="pidv-dot" style="background:${colorOf(n)}" title="${esc(X.color)}"></button>` +
            `<span class="nm" title="${esc(n)}">${esc(n)}${SG[n].role ? `<span class="role">${esc(SG[n].role)}</span>` : ""}</span>` +
            (on ? `<select title="${esc(X.panel)}">${opts}</select>` : "<span></span>") +
            `<button class="pidv-x" title="${esc(X.more)}">${opened.has(n) ? "▴" : "⋯"}</button>`;
          const [cb] = r.querySelectorAll("input");
          cb.onchange = () => {
            if (cb.checked) S.panels.push({ sigs: [n], h: 150, shared: false, lo: null, hi: null });
            else removeSig(n);
            buildPanels(); rows(); redraw(); save();
          };
          const dot = r.querySelector(".pidv-dot");
          dot.onclick = () => {
            const ci = el("input");
            ci.type = "color";
            ci.value = colorOf(n);
            ci.style.cssText = "position:absolute;opacity:0;width:0;height:0";
            box.appendChild(ci);
            ci.oninput = () => { sigCfg(n).c = ci.value; dot.style.background = ci.value; buildPanels(); redraw(); };
            ci.onchange = () => { save(); ci.remove(); };
            ci.click();
          };
          r.querySelector(".nm").onclick = () => { setAct(n); rows(); };
          const sel = r.querySelector("select");
          if (sel) sel.onchange = () => {
            removeSig(n);
            if (sel.value === "new") S.panels.push({ sigs: [n], h: 150, shared: false, lo: null, hi: null });
            else S.panels[Math.min(+sel.value, S.panels.length - 1)].sigs.push(n);
            buildPanels(); rows(); redraw(); save();
          };
          r.querySelector(".pidv-x").onclick = () => { if (opened.has(n)) opened.delete(n); else opened.add(n); rows(); };
          wrap.appendChild(r);
          if (opened.has(n)) {
            const c = S.sig[n] || {}, mo = el("div", "pidv-more");
            const ax = on ? axesOf(pi).find((a) => a.names.includes(n)) : null;
            mo.innerHTML = `<span>${esc(X.unit)}</span><input data-k="u" value="${esc(unitOf(n))}">` +
              `<span>${esc(X.ymin)}</span><input data-k="lo" placeholder="${ax ? esc(fmtV(ax.lo, SG[n])) : ""}" value="${c.lo !== undefined ? esc(fmtV(c.lo, SG[n])) : ""}">` +
              `<span>${esc(X.ymax)}</span><input data-k="hi" placeholder="${ax ? esc(fmtV(ax.hi, SG[n])) : ""}" value="${c.hi !== undefined ? esc(fmtV(c.hi, SG[n])) : ""}">` +
              `<span></span><div class="row"><button class="pidv-btn" data-k="auto">${esc(X.auto)}</button>` +
              `<button class="pidv-btn" data-k="reset">${esc(X.reset)}</button></div>`;
            const [iu, ilo, ihi] = mo.querySelectorAll("input");
            iu.onchange = () => { sigCfg(n).u = iu.value.slice(0, 20); buildPanels(); redraw(); save(); };
            const setLim = () => {
              const a = parseFloat(ilo.value.replace(",", ".")), b = parseFloat(ihi.value.replace(",", "."));
              const cur = ax || { lo: SG[n].lo0, hi: SG[n].hi0 };
              const lo = isFinite(a) ? a : cur.lo, hi = isFinite(b) ? b : cur.hi;
              if (hi > lo) { push(true); const cc = sigCfg(n); cc.lo = lo; cc.hi = hi; if (on) S.panels[pi].shared = false; buildPanels(); redraw(); save(); }
            };
            ilo.onchange = setLim; ihi.onchange = setLim;
            for (const i of [iu, ilo, ihi]) i.onkeydown = (e) => { if (e.key === "Enter") i.blur(); };
            mo.querySelector('[data-k="auto"]').onclick = () => { push(true); clearAxis(pi, n); redraw(); rows(); save(); };
            mo.querySelector('[data-k="reset"]').onclick = () => { delete S.sig[n]; buildPanels(); redraw(); rows(); save(); };
            wrap.appendChild(mo);
            if (SG[n].calc) wrap.appendChild(calcForm(S.calc.find((c) => c.name === n), false));
          }
        }
        for (const c of S.calc) {                // vypočtené signály s chybou ve vzorci (nejsou v grafu)
          if (SG[c.name]) continue;
          const r = el("div", "pidv-sig", `<span></span><span class="pidv-dot" style="background:#b91c1c"></span>` +
            `<span class="nm" title="${esc(c.name)}">${esc(c.name)}<span class="role">ƒ</span></span><span></span>` +
            `<button class="pidv-x">${opened.has(c.name) ? "▴" : "⋯"}</button>`);
          r.querySelector(".pidv-x").onclick = () => { if (opened.has(c.name)) opened.delete(c.name); else opened.add(c.name); rows(); };
          wrap.appendChild(r);
          wrap.appendChild(el("div", "pidv-cerr", esc(calcErr[c.name] || "")));
          if (opened.has(c.name)) wrap.appendChild(calcForm(c, false));
        }
        if (newCalc) wrap.appendChild(calcForm(newCalc, true));
        else {
          const add = el("button", "pidv-add", "+ ƒ " + esc(X.calc_add));
          add.title = X.calc_help || "";
          add.onclick = () => { newCalc = { name: "", expr: "", unit: "" }; rows(); };
          wrap.appendChild(add);
        }
      }
      rows();
      me.rows = rows;
    }
    let newCalc = null;
    function calcForm(c, isNew) {               // formulář vypočteného signálu (nový / úprava)
      const f = el("div", "pidv-calc");
      f.innerHTML = `<input data-k="name" placeholder="${esc(X.calc_name)}" value="${esc(c.name)}">` +
        `<textarea data-k="expr" rows="3" spellcheck="false" placeholder="${esc(X.calc_ph)}">${esc(c.expr)}</textarea>` +
        `<input data-k="unit" placeholder="${esc(X.unit)}" value="${esc(c.unit || "")}">` +
        `<div class="pidv-note">${esc(X.calc_help)}</div><div class="pidv-cerr"></div>` +
        `<div class="row"><button class="pidv-btn on" data-k="ok">${esc(X.calc_save)}</button>` +
        `<button class="pidv-btn" data-k="cancel">${esc(X.calc_cancel)}</button>` +
        (isNew ? "" : `<button class="pidv-btn" data-k="del">${esc(X.calc_del)}</button>`) + `</div>`;
      const g = (k) => f.querySelector(`[data-k="${k}"]`), err = f.querySelector(".pidv-cerr");
      g("ok").onclick = () => {
        const name = g("name").value.trim().slice(0, 40), expr = g("expr").value, unit = g("unit").value.slice(0, 20);
        const idx = isNew ? S.calc.length : S.calc.indexOf(c);
        const before = order.slice(0, nFile).concat(S.calc.slice(0, idx).map((q) => q.name).filter((q) => SG[q]));
        if (!name || order.slice(0, nFile).includes(name) || S.calc.some((q, i) => q.name === name && i !== idx)) {
          err.textContent = X.calc_badname || "–";
          return;
        }
        try { AN.parse(expr, before); } catch (e) { err.textContent = exprMsg(e); return; }
        const old = isNew ? null : c.name;
        const item = { name, expr, unit };
        if (isNew) S.calc.push(item); else S.calc[idx] = item;
        computeCalc(S.calc);
        if (old && old !== name) {                // přejmenování: panely, nastavení a volby analýz
          for (const p of S.panels) p.sigs = p.sigs.map((q) => (q === old ? name : q));
          if (S.sig[old]) { S.sig[name] = S.sig[old]; delete S.sig[old]; }
          opened.delete(old); opened.add(name);
        }
        if (calcErr[name]) { err.textContent = calcErr[name]; if (isNew) { S.calc.pop(); computeCalc(S.calc); } return; }
        if (isNew) { S.panels.push({ sigs: [name], h: 150, shared: false, lo: null, hi: null }); newCalc = null; }
        S.panels = S.panels.map((p) => Object.assign(p, { sigs: p.sigs.filter((q) => SG[q]) })).filter((p) => p.sigs.length);
        build(); save();
      };
      g("cancel").onclick = () => { if (isNew) newCalc = null; else opened.delete(c.name); me.rows && me.rows(); };
      const del = g("del");
      if (del) del.onclick = () => {
        S.calc = S.calc.filter((q) => q !== c);
        removeSig(c.name);
        computeCalc(S.calc);
        S.panels = S.panels.map((p) => Object.assign(p, { sigs: p.sigs.filter((q) => SG[q]) })).filter((p) => p.sigs.length);
        build(); save();
      };
      for (const k of ["name", "unit"]) g(k).onkeydown = (e) => { if (e.key === "Enter") g("ok").click(); };
      return f;
    }
    function removeSig(n) {
      for (const p of S.panels) { const i = p.sigs.indexOf(n); if (i >= 0) p.sigs.splice(i, 1); }
      S.panels = S.panels.filter((p) => p.sigs.length);
    }
    function setAct(n) {
      S.act = n;
      if (S.hc.on && S.hc.sig !== n) { S.hc.sig = n; S.hc.a = S.hc.b = null; initH(); }
      for (const P of panelsUI) P.chips.forEach((c) => c.classList.toggle("act", c.dataset.n === n));
      redraw();
      save();
    }

    // ---- panely
    function buildPanels() {
      plots.innerHTML = "";
      panelsUI = [];
      L = Math.max(1, ...S.panels.map((p) => (p.shared ? 1 : p.sigs.length))) * AXW + 4;
      if (!S.panels.length) plots.appendChild(el("div", "pidv-card pidv-err", esc(X.no_sig || "–")));
      S.panels.forEach((p, pi) => {
        const c = el("section", "pidv-card pidv-panel");
        const ph = el("div", "pidv-ph");
        const chips = p.sigs.map((n) => {
          const u = unitOf(n);
          const ch = el("span", "pidv-chip" + (S.act === n ? " act" : ""), `<i style="border-top-color:${colorOf(n)}"></i>` +
            `<span style="color:${colorOf(n)}">${esc(n)}</span>` + (u ? `<span class="pidv-lab">[${esc(u)}]</span>` : ""));
          ch.dataset.n = n;
          ch.onclick = () => setAct(n);
          ph.appendChild(ch);
          return ch;
        });
        ph.appendChild(el("span", "sp"));
        if (p.sigs.length > 1) {
          const lab = el("label", "pidv-lab", `<input type="checkbox" ${p.shared ? "checked" : ""}> ${esc(X.shared)}`);
          lab.style.cssText = "display:inline-flex;gap:4px;align-items:center;cursor:pointer";
          lab.querySelector("input").onchange = (e) => { p.shared = e.target.checked; p.lo = p.hi = null; buildPanels(); redraw(); save(); };
          ph.appendChild(lab);
        }
        const mk = (t, h, f, dis) => { const b = el("button", "pidv-x", t); b.title = h; b.disabled = !!dis; b.onclick = f; ph.appendChild(b); };
        mk("↑", X.up, () => { S.panels.splice(pi - 1, 0, S.panels.splice(pi, 1)[0]); buildPanels(); me.rows && me.rows(); redraw(); save(); }, pi === 0);
        mk("↓", X.down, () => { S.panels.splice(pi + 1, 0, S.panels.splice(pi, 1)[0]); buildPanels(); me.rows && me.rows(); redraw(); save(); }, pi === S.panels.length - 1);
        mk("×", X.remove, () => { S.panels.splice(pi, 1); buildPanels(); me.rows && me.rows(); redraw(); save(); });
        c.appendChild(ph);
        const wrap = el("div");
        wrap.style.position = "relative";
        const cv = el("canvas", "pidv-cv"), ov = el("canvas", "pidv-cv");
        ov.style.cssText = "position:absolute;left:0;top:0";
        wrap.append(cv, ov);
        c.appendChild(wrap);
        const rs = el("div", "pidv-rs");
        rs.title = X.drag || "";
        c.appendChild(rs);
        plots.appendChild(c);
        const P = { pi, p, c, cv, ov, chips, axes: [] };
        panelsUI.push(P);
        hookPanel(P);
        rs.addEventListener("pointerdown", (e) => {
          e.preventDefault();
          const y0 = e.clientY, h0 = p.h;
          const mv = (ev) => { p.h = clamp(h0 + ev.clientY - y0, 70, 900); sizePanel(P); drawPanel(P); drawOverlay(P); };
          const up = () => { window.removeEventListener("pointermove", mv); window.removeEventListener("pointerup", up); save(); };
          window.addEventListener("pointermove", mv);
          window.addEventListener("pointerup", up);
        });
      });
      const xc = el("div", "pidv-card pidv-xcard");
      xcv = el("canvas", "pidv-xax");
      nav = el("canvas", "pidv-nav");
      xc.append(xcv, nav);
      plots.appendChild(xc);
      hookXAxis();
      hookNav();
    }
    function cssW(node) { return Math.max(200, node.clientWidth || node.parentElement.clientWidth || 600); }
    function sizeCanvas(cv, w, h) {
      const r = window.devicePixelRatio || 1;
      if (cv.width !== Math.round(w * r) || cv.height !== Math.round(h * r)) {
        cv.width = Math.round(w * r); cv.height = Math.round(h * r);
        cv.style.width = w + "px"; cv.style.height = h + "px";
      }
      const g = cv.getContext("2d");
      g.setTransform(r, 0, 0, r, 0, 0);
      return g;
    }
    function sizePanel(P) {
      const w = cssW(P.c) - 16;
      P.w = w; P.h = P.p.h;
      P.g = sizeCanvas(P.cv, w, P.h);
      P.go = sizeCanvas(P.ov, w, P.h);
    }
    const col = (name) => getComputedStyle(box).getPropertyValue(name).trim() || "#888";

    // ---------------------------------------------------------------- kreslení
    const tx = (t, P) => L + (t - S.view[0]) / (S.view[1] - S.view[0]) * (P.w - L - R);
    const xt = (x, P) => S.view[0] + (x - L) / (P.w - L - R) * (S.view[1] - S.view[0]);
    const ty = (v, a, P) => P.h - BOT - (v - a.lo) / (a.hi - a.lo) * (P.h - TOP - BOT);
    const yv = (y, a, P) => a.lo + (P.h - BOT - y) / (P.h - TOP - BOT) * (a.hi - a.lo);

    function xTicks(w) {                     // [[t, text]] pro šířku w
      const span = S.view[1] - S.view[0], n = Math.max(2, Math.floor(w / 110)), out = [];
      if (D.clock !== null && D.clock !== undefined) {
        const steps = [0.001, 0.002, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600, 7200, 10800, 21600, 43200, 86400, 172800, 604800];
        const st = steps.find((s) => span / s <= n) || 604800;
        const off = (((D.clock / 1000) % st) + st) % st;
        let lastDay = null;
        for (let v = Math.ceil((S.view[0] + off) / st) * st - off; v <= S.view[1] + 1e-9; v += st) {
          const d = new Date(D.clock + v * 1000);
          const day = `${d.getUTCDate()}.${d.getUTCMonth() + 1}.`;
          let s = st >= 86400 ? day : st >= 60 ? `${d.getUTCHours()}:${pad2(d.getUTCMinutes())}` :
            `${d.getUTCHours()}:${pad2(d.getUTCMinutes())}:${pad2(d.getUTCSeconds())}` + (st < 1 ? dc("." + String(d.getUTCMilliseconds()).padStart(3, "0")) : "");
          if (st < 86400 && (lastDay === null ? span > 43200 : day !== lastDay)) s = day + " " + s;
          lastDay = day;
          out.push([v, s]);
        }
        return { ticks: out, unit: "" };
      }
      const u = unitFor(span), f = U[u], st = nice(span / f, n);
      for (let v = Math.ceil(S.view[0] / f / st) * st; v <= S.view[1] / f + 1e-9; v += st) out.push([v * f, fmtTick(v, st)]);
      return { ticks: out, unit: u };
    }

    function drawSig(g, P, s, a) {
      const t = s.t, v = s.v, n = s.n, x0 = L, x1 = P.w - R, W = x1 - x0;
      const va = S.view[0], vb = S.view[1], kx = W / (vb - va);
      const i0 = Math.max(0, lb(t, va, n) - 1), i1 = Math.min(n, lb(t, vb, n) + 1);
      if (i1 - i0 < 1) return;
      const ky = (P.h - TOP - BOT) / (a.hi - a.lo), yb = P.h - BOT;
      const Y = (q) => yb - (q - a.lo) * ky;
      g.beginPath();
      const spp = (i1 - i0) / W;
      if (spp <= 3) {
        let pen = false, ly = 0, lt = -Infinity;
        for (let i = i0; i < i1; i++) {
          const x = x0 + (t[i] - va) * kx, y = Y(v[i]);
          if (pen && t[i] - lt > s.gap) pen = false;
          if (!pen) g.moveTo(x, y);
          else { if (S.step) g.lineTo(x, ly); g.lineTo(x, y); }
          pen = true; ly = y; lt = t[i];
        }
        g.stroke();
        if (spp < 0.12) {                       // přiblíženo na jednotlivé vzorky → body
          g.fillStyle = g.strokeStyle;
          for (let i = i0; i < i1; i++) { const x = x0 + (t[i] - va) * kx; if (x < x0 - 3 || x > x1 + 3) continue; g.fillRect(x - 1.5, Y(v[i]) - 1.5, 3, 3); }
        }
        return;
      }
      let pen = false, lt = -Infinity, ly = 0;
      let ja = i0;
      for (let px = 0; px < W; px++) {
        const tb = va + (px + 1) / kx;
        const jb = px === W - 1 ? i1 : Math.min(i1, lb(t, tb, n));
        if (jb > ja) {
          const r = mm(s, ja, jb), x = x0 + px + 0.5;
          const yf = Y(v[ja]), yl = Y(v[jb - 1]);
          if (pen && t[ja] - lt > s.gap) pen = false;
          if (!pen) g.moveTo(x, yf);
          else { if (S.step) g.lineTo(x, ly); g.lineTo(x, yf); }
          g.lineTo(x, Y(r[0])); g.lineTo(x, Y(r[1])); g.lineTo(x, yl);
          pen = true; lt = t[jb - 1]; ly = yl;
          ja = jb;
        }
      }
      g.stroke();
    }

    function drawPanel(P) {
      const g = P.g, w = P.w, h = P.h;
      g.clearRect(0, 0, w, h);
      P.axes = axesOf(P.pi);
      const grid = col("--pv-grid"), axc = col("--pv-axis"), text = col("--pv-text");
      // mřížka
      g.lineWidth = 1;
      g.strokeStyle = grid;
      g.beginPath();
      for (const [t] of xTicks(w - L - R).ticks) { const x = Math.round(tx(t, P)) + 0.5; g.moveTo(x, TOP); g.lineTo(x, h - BOT); }
      const a0 = P.axes[0];
      if (a0) {
        const st = nice(a0.hi - a0.lo, Math.max(2, Math.floor((h - TOP - BOT) / 38)));
        for (let v = Math.ceil(a0.lo / st) * st; v <= a0.hi + 1e-12; v += st) { const y = Math.round(ty(v, a0, P)) + 0.5; g.moveTo(L, y); g.lineTo(w - R, y); }
      }
      g.stroke();
      g.strokeStyle = axc;
      g.strokeRect(L + 0.5, TOP + 0.5, w - L - R - 1, h - TOP - BOT - 1);
      // osy Y
      g.font = "11px 'IBM Plex Mono', monospace";
      g.textBaseline = "middle";
      P.axes.forEach((a, k) => {
        const xr = L - 4 - k * AXW;
        const c = a.color === "var" ? text : a.color;
        const act = a.names.includes(S.act);
        g.strokeStyle = c;
        g.lineWidth = act ? 2.5 : 1;
        g.beginPath(); g.moveTo(xr + 0.5, TOP); g.lineTo(xr + 0.5, h - BOT); g.stroke();
        g.lineWidth = 1;
        g.fillStyle = c;
        g.textAlign = "right";
        const st = nice(a.hi - a.lo, Math.max(2, Math.floor((h - TOP - BOT) / 38)));
        const top = a.unit ? TOP + 16 : TOP + 5;          // nahoře jednotka osy
        for (let v = Math.ceil(a.lo / st) * st; v <= a.hi + 1e-12; v += st) {
          const y = ty(v, a, P);
          if (y < top || y > h - BOT - 2) continue;
          g.beginPath(); g.moveTo(xr - 3, y); g.lineTo(xr, y); g.stroke();
          let s = fmtTick(v, st);
          while (s.length > 1 && g.measureText(s).width > AXW - 8) s = s.slice(0, -1);
          g.fillText(s, xr - 5, y);
        }
        if (a.unit) {
          g.textAlign = "right";
          g.fillStyle = c;
          g.font = "10px sans-serif";
          let u = a.unit;
          while (u.length > 1 && g.measureText(u).width > AXW - 8) u = u.slice(0, -1);
          g.fillText(u, xr - 5, TOP + 6);
          g.font = "11px 'IBM Plex Mono', monospace";
        }
      });
      // průběhy
      g.save();
      g.beginPath();
      g.rect(L, TOP, w - L - R, h - TOP - BOT);
      g.clip();
      g.lineJoin = "round";
      for (const a of P.axes) for (const n of a.names) {
        g.strokeStyle = colorOf(n);
        g.lineWidth = S.act === n ? 2 : 1.4;
        drawSig(g, P, SG[n], a);
      }
      if (events) {                             // značky událostí signálů panelu
        const x0 = L, x1 = w - R;
        for (const e of evList()) {
          if (!P.p.sigs.includes(e.sig)) continue;
          const xa = tx(e.t, P), xb = e.t1 !== undefined ? tx(e.t1, P) : xa;
          if (xb < x0 - 6 || xa > x1 + 6) continue;
          g.fillStyle = EVC[e.kind];
          if (xb > xa + 1) { g.globalAlpha = 0.18; g.fillRect(Math.max(x0, xa), TOP, Math.min(x1, xb) - Math.max(x0, xa), h - TOP - BOT); g.globalAlpha = 1; }
          g.beginPath(); g.moveTo(xa - 4, TOP); g.lineTo(xa + 4, TOP); g.lineTo(xa, TOP + 7); g.closePath(); g.fill();
        }
      }
      g.restore();
    }

    let hoverT = null, band = null;
    function drawOverlay(P) {
      const g = P.go, w = P.w, h = P.h;
      g.clearRect(0, 0, w, h);
      const line = (x, c, dash, lab) => {
        if (x < L - 1 || x > w - R + 1) return;
        g.strokeStyle = c; g.lineWidth = 1.3; g.setLineDash(dash || []);
        g.beginPath(); g.moveTo(Math.round(x) + 0.5, TOP); g.lineTo(Math.round(x) + 0.5, h - BOT); g.stroke();
        g.setLineDash([]);
        if (lab && P.pi === 0) { g.fillStyle = c; g.font = "bold 10px sans-serif"; g.textAlign = "left"; g.textBaseline = "top"; g.fillText(lab, x + 3, TOP + 2); }
      };
      if (hoverT !== null) line(tx(hoverT, P), col("--pv-muted"), [2, 3]);
      if (S.cur.on) {
        line(tx(S.cur.a, P), "#d97706", null, "C1");
        line(tx(S.cur.b, P), "#7c3aed", null, "C2");
      }
      if (S.hc.on && S.hc.sig && P.p.sigs.includes(S.hc.sig)) {
        const a = P.axes.find((q) => q.names.includes(S.hc.sig));
        if (a) for (const [v, c, lab] of [[S.hc.a, "#0891b2", "H1"], [S.hc.b, "#db2777", "H2"]]) {
          const y = ty(v, a, P);
          if (y < TOP || y > h - BOT) continue;
          g.strokeStyle = c; g.lineWidth = 1.3; g.setLineDash([6, 3]);
          g.beginPath(); g.moveTo(L, Math.round(y) + 0.5); g.lineTo(w - R, Math.round(y) + 0.5); g.stroke();
          g.setLineDash([]);
          g.fillStyle = c; g.font = "bold 10px sans-serif"; g.textAlign = "right"; g.textBaseline = "bottom";
          g.fillText(`${lab} ${fmtV(v, SG[S.hc.sig])}`, w - R - 3, y - 2);
        }
      }
      if (S.an === "step" && stepRes && stepRes.ok && P.p.sigs.includes(S.stp.y)) {
        const a = P.axes.find((q) => q.names.includes(S.stp.y)), r = stepRes;
        if (a) {
          g.setLineDash([5, 3]); g.lineWidth = 1.2; g.strokeStyle = "#16a34a";
          const hl = (v) => { const y = ty(v, a, P); if (y >= TOP && y <= h - BOT) { g.beginPath(); g.moveTo(L, y); g.lineTo(w - R, y); g.stroke(); } };
          hl(r.y0);
          if (!r.integ) hl(r.yinf);
          g.setLineDash([]);
          g.fillStyle = "#16a34a"; g.font = "bold 10px sans-serif"; g.textAlign = "left"; g.textBaseline = "top";
          const vl = (t, lab, dash) => {
            if (t === null || t === undefined) return;
            const x = tx(t, P);
            if (x < L || x > w - R) return;
            g.setLineDash(dash || []); g.beginPath(); g.moveTo(x, TOP); g.lineTo(x, h - BOT); g.stroke(); g.setLineDash([]);
            g.fillText(lab, x + 3, TOP + 12);
          };
          vl(r.ts, "u", null);
          if (r.theta !== null) vl(r.ts + r.theta, "θ", [2, 3]);
          if (!r.integ && r.t63 !== null) {
            vl(r.t63, "63 %", [2, 3]);
            const y = ty(r.y0 + 0.632 * r.dy, a, P);
            g.beginPath(); g.arc(tx(r.t63, P), y, 4, 0, 2 * Math.PI); g.stroke();
          }
        }
      }
      if (band && band.P === P) {
        g.fillStyle = "rgba(31,95,168,0.12)"; g.strokeStyle = "rgba(31,95,168,0.7)"; g.lineWidth = 1;
        const x0 = band.kind === "y" ? L : Math.min(band.x0, band.x1), x1 = band.kind === "y" ? w - R : Math.max(band.x0, band.x1);
        const y0 = band.kind === "x" ? TOP : Math.min(band.y0, band.y1), y1 = band.kind === "x" ? h - BOT : Math.max(band.y0, band.y1);
        g.fillRect(x0, y0, x1 - x0, y1 - y0); g.strokeRect(x0 + 0.5, y0 + 0.5, x1 - x0, y1 - y0);
      }
    }
    function drawX() {
      if (!xcv) return;
      const w = cssW(xcv.parentElement) - 16, g = sizeCanvas(xcv, w, 22);
      g.clearRect(0, 0, w, 22);
      g.font = "11px 'IBM Plex Mono', monospace";
      g.fillStyle = col("--pv-muted");
      g.textBaseline = "top";
      g.textAlign = "center";
      const P = { w };
      const { ticks, unit } = xTicks(w - L - R);
      for (const [t, s] of ticks) { const x = tx(t, P); if (x < L + 10 || x > w - R - 30) continue; g.fillText(s, x, 4); }
      if (unit) { g.textAlign = "right"; g.fillText(unit, w - 2, 4); }
      g.textAlign = "left";
      g.fillText(D.clock !== null && D.clock !== undefined ? "" : (X.time || ""), 2, 4);
    }
    let navImg = null;
    function drawNav() {
      if (!nav) return;
      const w = cssW(nav.parentElement) - 16, h = 34, g = sizeCanvas(nav, w, h);
      g.clearRect(0, 0, w, h);
      const x0 = L, W = w - L - R;
      g.strokeStyle = col("--pv-axis");
      g.strokeRect(x0 + 0.5, 0.5, W - 1, h - 1);
      const ref = visible()[0];
      const nkey = [ref, w, L, ref && colorOf(ref), window.devicePixelRatio].join("|");
      if (navImg && navImg.key === nkey) {             // přehled celého záznamu se nemění – jen obdélník výřezu
        g.save(); g.setTransform(1, 0, 0, 1, 0, 0); g.drawImage(navImg.cv, 0, 0); g.restore();
      } else if (ref) {
        const s = SG[ref];
        g.strokeStyle = colorOf(ref); g.lineWidth = 1;
        const lo = s.lo0, hi = s.hi0 > s.lo0 ? s.hi0 : s.lo0 + 1;
        g.beginPath();
        let ja = 0;
        for (let px = 0; px < W; px++) {
          const jb = px === W - 1 ? s.n : lb(s.t, (px + 1) / W * D.T, s.n);
          if (jb > ja) { const r = mm(s, ja, jb); const yA = h - 3 - (r[0] - lo) / (hi - lo) * (h - 6), yB = h - 3 - (r[1] - lo) / (hi - lo) * (h - 6); if (!px) g.moveTo(x0 + px, yA); g.lineTo(x0 + px, yA); g.lineTo(x0 + px, yB); ja = jb; }
        }
        g.stroke();
        const cc = document.createElement("canvas");
        cc.width = nav.width; cc.height = nav.height;
        cc.getContext("2d").drawImage(nav, 0, 0);
        navImg = { key: nkey, cv: cc };
      }
      if (events) {
        let k = 0;
        for (const e of evList()) {
          if (k++ > 3000) break;
          g.fillStyle = EVC[e.kind];
          g.fillRect(Math.round(x0 + e.t / D.T * W), h - 7, 1.5, 6);
        }
      }
      const a = x0 + S.view[0] / D.T * W, b = x0 + S.view[1] / D.T * W;
      g.fillStyle = "rgba(31,95,168,0.16)";
      g.fillRect(a, 1, Math.max(2, b - a), h - 2);
      g.strokeStyle = col("--pv-acc"); g.lineWidth = 1.5;
      g.strokeRect(a + 0.5, 1, Math.max(2, b - a), h - 2);
      nav.title = X.drag || "";
    }
    let raf = 0;
    function redraw() {
      if (raf) return;
      raf = requestAnimationFrame(() => {
        raf = 0;
        for (const P of panelsUI) { sizePanel(P); drawPanel(P); drawOverlay(P); }
        drawX(); drawNav(); readout(); table();
        if (S.an === "xy" && !S.cur.on) renderAn();
      });
    }
    let raf2 = 0, curDirty = false;
    function redrawOverlay(cur) {             // cur = kurzory se změnily → i odečet a tabulka
      if (cur) curDirty = true;
      if (raf2) return;
      raf2 = requestAnimationFrame(() => {
        raf2 = 0;
        for (const P of panelsUI) drawOverlay(P);
        if (curDirty) { curDirty = false; readout(); table(true); if (S.an === "step" || S.an === "xy") renderAn(); }
      });
    }

    // ---------------------------------------------------------------- kurzory
    const ref = () => SG[S.act && panelOf(S.act) >= 0 ? S.act : visible()[0]] || SG[order[0]];
    const snapT = (t) => { const s = ref(), i = nearest(s, t); return i >= 0 ? s.t[i] : t; };
    function initCursors() {
      const [a, b] = S.view, inView = (t) => t !== null && t >= a && t <= b;
      if (!inView(S.cur.a)) S.cur.a = snapT(a + (b - a) / 3);
      if (!inView(S.cur.b)) S.cur.b = snapT(a + 2 * (b - a) / 3);
    }
    function initH() {
      if (!S.hc.sig || panelOf(S.hc.sig) < 0) S.hc.sig = S.act && panelOf(S.act) >= 0 ? S.act : visible()[0];
      if (!S.hc.sig) { S.hc.on = false; return; }
      const pi = panelOf(S.hc.sig), a = axesOf(pi).find((q) => q.names.includes(S.hc.sig));
      const inR = (v) => v !== null && v >= a.lo && v <= a.hi;
      if (!inR(S.hc.a)) S.hc.a = a.lo + (a.hi - a.lo) / 3;
      if (!inR(S.hc.b)) S.hc.b = a.lo + 2 * (a.hi - a.lo) / 3;
    }
    function valAt(s, t) { const i = nearest(s, t); return i >= 0 ? s.v[i] : null; }
    function readout() {
      if (!readBox) return;
      readBox.style.display = S.cur.on || S.hc.on ? "" : "none";
      if (!(S.cur.on || S.hc.on)) return;
      let h = "";
      if (S.cur.on) {
        const a = S.cur.a, b = S.cur.b, dt = b - a;
        h += `<div class="pidv-rhead"><span><span style="color:#d97706">C1</span> <b>${esc(fmtT(a))}</b></span>` +
          `<span><span style="color:#7c3aed">C2</span> <b>${esc(fmtT(b))}</b></span>` +
          `<span>Δt <b>${esc(fmtDur(dt))}</b></span>` + (dt ? `<span>1/Δt <b>${esc(fmtG(1 / Math.abs(dt), 4))} Hz</b></span>` : "") +
          `<span class="pidv-note">${esc(X.nearest)}</span></div>`;
        h += `<table class="pidv-tbl"><thead><tr><th>${esc(X.signal)}</th><th>C1</th><th>C2</th><th>Δ</th><th>${esc(X.slope)}</th>` +
          `<th>${esc(X.min)}</th><th>${esc(X.max)}</th><th>${esc(X.mean)}</th><th>σ</th></tr></thead><tbody>`;
        for (const n of visible()) {
          const s = SG[n], v1 = valAt(s, a), v2 = valAt(s, b), st = stats(s, a, b), u = unitOf(n);
          const d = v1 !== null && v2 !== null ? v2 - v1 : null;
          h += `<tr data-n="${esc(n)}"><td><span style="color:${colorOf(n)};font-weight:600">${esc(n)}</span>${u ? ` <span class="pidv-lab">[${esc(u)}]</span>` : ""}</td>` +
            `<td>${fmtV(v1, s)}</td><td>${fmtV(v2, s)}</td><td>${fmtV(d, s)}</td><td>${d !== null && dt ? fmtG(d / dt, 4) + "/s" : "–"}</td>` +
            `<td>${st ? fmtV(st.min, s) : "–"}</td><td>${st ? fmtV(st.max, s) : "–"}</td><td>${st ? fmtV(st.mean, s) : "–"}</td>` +
            `<td>${st ? fmtG(st.sd, 4) : "–"}</td></tr>`;
        }
        h += "</tbody></table>";
      }
      if (S.hc.on && S.hc.sig) {
        const s = SG[S.hc.sig], u = unitOf(S.hc.sig);
        h += `<div class="pidv-rhead" style="margin-top:${S.cur.on ? 8 : 0}px"><span style="color:${colorOf(S.hc.sig)};font-weight:600">${esc(S.hc.sig)}</span>` +
          `<span><span style="color:#0891b2">H1</span> <b>${fmtV(S.hc.a, s)}</b> ${esc(u)}</span>` +
          `<span><span style="color:#db2777">H2</span> <b>${fmtV(S.hc.b, s)}</b> ${esc(u)}</span>` +
          `<span>ΔH <b>${fmtV(S.hc.b - S.hc.a, s)}</b> ${esc(u)}</span></div>`;
      }
      readBox.innerHTML = h;
      readBox.querySelectorAll("tbody tr").forEach((r) => r.onclick = () => setAct(r.dataset.n));
    }

    // ---------------------------------------------------------------- tabulka hodnot
    const ROWH = 22, MAXROWS = 500000;
    let tabScroll = null, tabBase = null;
    function table(light) {
      if (!tabBox) return;
      tabBox.style.display = S.tab ? "" : "none";
      if (!S.tab) { tabScroll = null; return; }
      const vis = visible();
      if (!vis.length) { tabBox.innerHTML = ""; return; }
      const base = vis.reduce((a, n) => (SG[n].n > SG[a].n ? n : a), vis[0]), s = SG[base];
      const i0 = lb(s.t, S.view[0], s.n), i1 = Math.min(lb(s.t, S.view[1] + 1e-12, s.n), i0 + MAXROWS);
      const N = Math.max(0, i1 - i0);
      const key = base + "|" + i0 + "|" + i1 + "|" + vis.join("|");
      if (!tabScroll || tabBase !== key) {
        tabBase = key;
        const more = lb(s.t, S.view[1] + 1e-12, s.n) - i0 > MAXROWS;
        tabBox.innerHTML = `<div class="pidv-rhead"><span>${esc(X.rows.replace("{n}", String(N).replace(/\B(?=(\d{3})+(?!\d))/g, D.dec === "," ? "\u00a0" : ",")).replace("{s}", base))}</span>` +
          (more ? `<span class="pidv-note">${esc(X.rows_more)}</span>` : "") + `</div>`;
        tabScroll = el("div", "pidv-dtab");
        tabBox.appendChild(tabScroll);
        tabScroll.onscroll = () => fill();
        light = false;
      }
      const curRow = S.cur.on ? nearest(s, S.cur.a) - i0 : -1;
      function fill() {
        const top = tabScroll.scrollTop, hgt = tabScroll.clientHeight || 280;
        const f = Math.max(0, Math.floor(top / ROWH) - 5), l = Math.min(N, f + Math.ceil(hgt / ROWH) + 12);
        let h = `<table class="pidv-tbl"><thead><tr><th>${esc(X.time)}</th>` +
          vis.map((n) => `<th style="color:${colorOf(n)}">${esc(n)}${unitOf(n) ? " [" + esc(unitOf(n)) + "]" : ""}</th>`).join("") + `</tr></thead><tbody>`;
        h += `<tr style="height:${f * ROWH}px"></tr>`;
        for (let r = f; r < l; r++) {
          const i = i0 + r, t = s.t[i];
          h += `<tr data-t="${t}" class="${r === curRow ? "sel" : ""}" style="height:${ROWH}px"><td>${esc(fmtT(t))}</td>` + vis.map((n) => {
            const q = SG[n];
            const j = q.ti === s.ti ? i : (() => { const k = lb(q.t, t + 1e-12, q.n) - 1; return k; })();
            return `<td>${j >= 0 && j < q.n ? fmtV(q.v[j], q) : "–"}</td>`;
          }).join("") + `</tr>`;
        }
        h += `<tr style="height:${Math.max(0, (N - l) * ROWH)}px"></tr></tbody></table>`;
        tabScroll.innerHTML = h;
        tabScroll.scrollTop = top;
        tabScroll.querySelectorAll("tbody tr[data-t]").forEach((tr) => tr.onclick = () => {
          const t = +tr.dataset.t;
          if (!S.cur.on) { S.cur.on = true; initCursors(); rebar(); }
          S.cur.a = t; S.acur = "a";
          redrawOverlay(true); save();
        });
      }
      if (light && curRow >= 0 && me.followRow) {
        const y = curRow * ROWH, top = tabScroll.scrollTop, hgt = tabScroll.clientHeight || 280;
        if (y < top || y > top + hgt - 2 * ROWH) tabScroll.scrollTop = Math.max(0, y - hgt / 2);
        me.followRow = false;
      }
      fill();
    }

    // ---------------------------------------------------------------- export CSV
    function exportCsv(a, b) {
      const vis = visible();
      if (!vis.length) return;
      const base = vis.reduce((x, n) => (SG[n].n > SG[x].n ? n : x), vis[0]), s = SG[base];
      const i0 = lb(s.t, a, s.n), i1 = lb(s.t, b + 1e-12, s.n);
      const sep = D.dec === "," ? ";" : ",";
      const num_ = (v, q) => (v === null || !isFinite(v) ? "" : dc(String(+v.toFixed(Math.min(9, q.dec + 2)))));
      const hasClock = D.clock !== null && D.clock !== undefined;
      const tstr = (t) => {
        if (!hasClock) return dc(String(+t.toFixed(6)));
        const d = new Date(D.clock + t * 1000);
        return `${d.getUTCFullYear()}-${pad2(d.getUTCMonth() + 1)}-${pad2(d.getUTCDate())} ${pad2(d.getUTCHours())}:${pad2(d.getUTCMinutes())}:${pad2(d.getUTCSeconds())}.${String(d.getUTCMilliseconds()).padStart(3, "0")}`;
      };
      const parts = [[hasClock ? "time" : "t [s]"].concat(vis.map((n) => n + (unitOf(n) ? ` [${unitOf(n)}]` : ""))).map((c) => `"${c.replace(/"/g, '""')}"`).join(sep) + "\n"];
      let chunk = "";
      const ptr = {};
      for (const n of vis) ptr[n] = Math.max(0, lb(SG[n].t, s.t[i0] || a, SG[n].n) - 1);
      for (let i = i0; i < i1; i++) {
        const t = s.t[i];
        let row = tstr(t);
        for (const n of vis) {
          const q = SG[n];
          let j;
          if (q.ti === s.ti) j = i;
          else { while (ptr[n] + 1 < q.n && q.t[ptr[n] + 1] <= t + 1e-12) ptr[n]++; j = q.t[ptr[n]] <= t + 1e-12 ? ptr[n] : -1; }
          row += sep + (j >= 0 ? num_(q.v[j], q) : "");
        }
        chunk += row + "\n";
        if (chunk.length > 1 << 20) { parts.push(chunk); chunk = ""; }
      }
      parts.push(chunk);
      const blob = new Blob(["﻿", ...parts], { type: "text/csv;charset=utf-8" });
      const url = URL.createObjectURL(blob), lnk = document.createElement("a");
      lnk.href = url;
      lnk.download = (D.fname || "data").replace(/\.[^.]+$/, "") + "_view.csv";
      document.body.appendChild(lnk);
      lnk.click();
      setTimeout(() => { URL.revokeObjectURL(url); lnk.remove(); }, 2000);
    }

    // ---------------------------------------------------------------- analýza: události, odezva, korelace, XY, srovnání
    const EVC = { mv: "#c2410c", sp: "#64748b", dv: "#0d9488", state: "#7c3aed", sat: "#dc2626", flat: "#ca8a04", gap: "#475569" };
    const SEGC = ["#1f5fa8", "#c2410c", "#16a34a", "#9333ea", "#db2777", "#0891b2", "#ca8a04", "#475569"];
    let stepRes = null, corRes = null, corSel = null, curEv = null;
    function evList() {
      if (!events) events = AN.events(order.map((n) => SG[n]), {});
      return events.filter((e) => S.evk[e.kind] && SG[e.sig]);
    }
    const roleSig = (r) => order.find((n) => SG[n].role === r);
    const firstOf = (...c) => c.find((n) => n && SG[n]) || null;
    const span2 = () => (S.cur.on ? [Math.min(S.cur.a, S.cur.b), Math.max(S.cur.a, S.cur.b)] : [S.view[0], S.view[1]]);
    const sigSel = (k, cur) => `<select data-k="${k}">` + order.map((n) =>
      `<option value="${esc(n)}" ${n === cur ? "selected" : ""}>${esc(n)}</option>`).join("") + `</select>`;
    function gotoEvent(e) {
      curEv = e;
      const span = S.view[1] - S.view[0];
      let Ln = span > D.T * 0.5 ? Math.max(MINSPAN, D.T / 12) : span;
      if (e.t1 !== undefined) Ln = Math.min(D.T, Math.max(Ln, (e.t1 - e.t) * 1.5));
      push(true);
      const a = clamp(e.t - Ln * 0.3, 0, D.T - Ln);
      S.view = [a, a + Ln];
      if (S.cur.on) {
        S.cur.a = e.t;
        if (e.t1 !== undefined) S.cur.b = e.t1;
        else if (!(S.cur.b > e.t && S.cur.b < a + Ln)) S.cur.b = Math.min(D.T, e.t + Ln * 0.5);
        me.followRow = true;
      }
      push(true);
      redraw(); renderAn(); save();
    }
    function evNav(dir) {
      const L_ = evList();
      if (!L_.length) return;
      const ref_ = curEv && curEv.t >= S.view[0] && curEv.t <= S.view[1] ? curEv.t : S.cur.on ? S.cur.a : (S.view[0] + S.view[1]) / 2;
      const e = dir > 0 ? L_.find((q) => q.t > ref_ + 1e-9) : [...L_].reverse().find((q) => q.t < ref_ - 1e-9);
      if (e) gotoEvent(e);
    }
    function renderAn() {
      if (!anBox) return;
      anBox.innerHTML = "";
      const tabs = el("div", "pidv-antabs");
      const nEv = events ? evList().length : "…";
      const items = [["ev", `${X.an_ev} (${nEv})`], ["step", X.an_step], ["corr", X.an_corr], ["xy", X.an_xy], ["cmp", X.an_cmp]];
      tabs.innerHTML = `<span class="pidv-lab">${esc(X.an)}</span>` + items.map(([k, t]) =>
        `<button class="pidv-tabb ${S.an === k ? "on" : ""}" data-an="${k}">${esc(t)}</button>`).join("") +
        (S.an ? `<span class="sp"></span><button class="pidv-x" data-an="" title="${esc(X.close)}">×</button>` : "");
      tabs.querySelectorAll("[data-an]").forEach((b) => b.onclick = () => {
        S.an = b.dataset.an && b.dataset.an !== S.an ? b.dataset.an : null;
        renderAn(); redraw(); save();
      });
      anBox.appendChild(tabs);
      if (!S.an) { stepRes = null; return; }
      const bd = el("div", "pidv-anbody");
      anBox.appendChild(bd);
      ({ ev: anEvents, step: anStep, corr: anCorr, xy: anXY, cmp: anCmp })[S.an](bd);
    }
    function anEvents(bd) {
      if (!events) { bd.innerHTML = `<span class="pidv-note">${esc(X.loading)}</span>`; return; }
      const cnt = {};
      for (const e of events) if (SG[e.sig]) cnt[e.kind] = (cnt[e.kind] || 0) + 1;
      const f = el("div", "pidv-row");
      f.innerHTML = Object.keys(EVC).map((k) => `<label class="pidv-chk"><input type="checkbox" data-k="${k}" ${S.evk[k] ? "checked" : ""}>` +
        `<i style="background:${EVC[k]}"></i>${esc(X["ev_" + k])} (${cnt[k] || 0})</label>`).join("") +
        `<span class="pidv-note">${esc(X.ev_hint)}</span>`;
      f.querySelectorAll("input").forEach((i) => i.onchange = () => { S.evk[i.dataset.k] = i.checked; renderAn(); redraw(); save(); });
      bd.appendChild(f);
      const L_ = evList();
      if (!L_.length) { bd.appendChild(el("div", "pidv-note", esc(X.ev_none))); return; }
      const wrap = el("div", "pidv-dtab");
      wrap.style.height = Math.min(320, 30 + 24 * L_.length) + "px";
      const det = (e) => {
        const s = SG[e.sig], u = unitOf(e.sig);
        if (e.kind === "mv" || e.kind === "sp" || e.kind === "dv")
          return `${fmtV(e.a, s)} → ${fmtV(e.b, s)} ${esc(u)} (Δ ${fmtV(e.d, s)})`;
        if (e.kind === "state") return `${fmtV(e.a, s)} → ${fmtV(e.b, s)}`;
        if (e.kind === "gap") return esc(fmtDur(e.d));
        return `${fmtV(e.a, s)} ${esc(u)} · ${esc(fmtDur(e.d))}`;
      };
      wrap.innerHTML = `<table class="pidv-tbl pidv-left"><thead><tr><th>${esc(X.time)}</th><th>${esc(X.ev_kind)}</th><th>${esc(X.signal)}</th>` +
        `<th>${esc(X.ev_detail)}</th></tr></thead><tbody>` + L_.slice(0, 1000).map((e, i) =>
        `<tr data-i="${i}" class="${e === curEv ? "sel" : ""}"><td>${esc(fmtT(e.t))}</td><td><span style="color:${EVC[e.kind]}">■</span> ${esc(X["ev_" + e.kind])}</td>` +
        `<td>${esc(e.sig)}</td><td>${det(e)}</td></tr>`).join("") + `</tbody></table>`;
      wrap.querySelectorAll("tbody tr").forEach((tr) => tr.onclick = () => gotoEvent(L_[+tr.dataset.i]));
      bd.appendChild(wrap);
    }
    function anStep(bd) {
      S.stp.u = firstOf(S.stp.u, roleSig("MV"), visible()[0], order[0]);
      S.stp.y = firstOf(S.stp.y, roleSig("PV"), visible()[1], order[0]);
      const c = el("div", "pidv-row");
      c.innerHTML = `<span class="pidv-lab">${esc(X.st_in)}</span>${sigSel("u", S.stp.u)}` +
        `<span class="pidv-lab">${esc(X.st_out)}</span>${sigSel("y", S.stp.y)}` +
        `<button class="pidv-btn" data-k="find">${esc(X.st_find)}</button><span class="pidv-note">${esc(X.st_hint)}</span>`;
      c.querySelectorAll("select").forEach((q) => q.onchange = () => { S.stp[q.dataset.k] = q.value; renderAn(); save(); });
      c.querySelector('[data-k="find"]').onclick = () => {      // další skok vstupu → kurzory kolem něj
        const st = AN.steps(SG[S.stp.u], 0.01);
        if (!st.length) return;
        const refT = S.cur.on ? Math.max(S.cur.a, S.cur.b) - 1e-9 : S.view[0];
        let k = st.findIndex((e) => e.t > refT + MIN_DT * 0.5);
        if (k < 0) k = 0;
        const e = st[k], prevT = k > 0 ? st[k - 1].t : 0, nextT = k + 1 < st.length ? st[k + 1].t : D.T;
        const a = Math.max(prevT + 0.6 * (e.t - prevT), e.t - 0.25 * (nextT - e.t)), b = nextT - 0.02 * (nextT - e.t);
        S.cur.on = true; S.cur.a = snapT(a); S.cur.b = snapT(b);
        push(true);
        const m = 0.08 * (b - a);
        S.view = [Math.max(0, a - m), Math.min(D.T, b + m)];
        fixView(S);
        push(true);
        rebar(); redraw(); renderAn(); save();
      };
      bd.appendChild(c);
      stepRes = null;
      if (!S.cur.on) { bd.appendChild(el("div", "pidv-note", esc(X.st_need_cur))); return; }
      const [a, b] = span2();
      const r = AN.step(SG[S.stp.u], SG[S.stp.y], a, b);
      stepRes = r;
      for (const P of panelsUI) drawOverlay(P);
      if (!r.ok) { bd.appendChild(el("div", "pidv-cerr", esc(X["st_" + r.err] || r.err))); return; }
      const uu = unitOf(S.stp.u), uy = unitOf(S.stp.y), su = SG[S.stp.u], sy = SG[S.stp.y];
      const kU = `${uy || "Y"}/${uu || "U"}`;
      const rows = [
        [X.st_du, `${fmtV(r.u0, su)} → ${fmtV(r.u1, su)} (Δ ${fmtV(r.du, su)}) ${esc(uu)}`],
        [X.st_dy, r.integ ? "–" : `${fmtV(r.y0, sy)} → ${fmtV(r.yinf, sy)} (Δ ${fmtV(r.dy, sy)}) ${esc(uy)}`],
      ];
      if (r.integ) rows.push([X.st_ki, `${fmtG(r.Ki, 4)} ${esc(kU)}/s`], [X.st_th, r.theta === null ? "–" : fmtDur(r.theta)]);
      else rows.push([X.st_k, `${fmtG(r.K, 4)} ${esc(kU)}`], [X.st_th, r.theta === null ? "–" : fmtDur(r.theta)],
        [X.st_t, r.T === null ? "–" : fmtDur(r.T)], [X.st_tr, r.tr === null ? "–" : fmtDur(r.tr)],
        [X.st_ovs, `${fmtG(100 * r.ovs, 3)} %`], [X.st_set, r.tset === null ? X.st_noset : fmtDur(r.tset)]);
      const t = el("table", "pidv-tbl pidv-kv");
      t.innerHTML = rows.map(([k, v]) => `<tr><td>${esc(k)}</td><td>${v}</td></tr>`).join("");
      bd.appendChild(t);
      bd.appendChild(el("div", "pidv-note", esc(r.integ ? X.st_integ : X.st_model) +
        (r.integ ? "" : ` K = ${fmtG(r.K, 4)}, T = ${r.T === null ? "–" : fmtG(r.T, 4)} s, θ = ${r.theta === null ? "–" : fmtG(r.theta, 4)} s`)));
    }
    function anCorr(bd) {
      S.cor.y = firstOf(S.cor.y, roleSig("PV"), visible()[0], order[0]);
      const [a, b] = span2();
      const c = el("div", "pidv-row");
      c.innerHTML = `<span class="pidv-lab">${esc(X.cor_target)}</span>${sigSel("y", S.cor.y)}` +
        `<div class="pidv-seg">` + [["auto", X.cor_auto, X.cor_auto_h], ["incr", X.cor_incr, X.cor_incr_h], ["int", X.cor_int, X.cor_int_h], ["vals", X.cor_vals, X.cor_vals_h]].map(([m, t, h]) =>
          `<button data-m="${m}" class="${S.cor.mode === m ? "on" : ""}" title="${esc(h)}">${esc(t)}</button>`).join("") + `</div>` +
        `<span class="pidv-lab">${esc(X.cor_lag)}</span><input data-k="lag" size="7" placeholder="${esc(fmtG((b - a) / 4, 3))}" value="${S.cor.lag === null ? "" : esc(fmtG(S.cor.lag, 4))}"><span class="pidv-lab">s</span>` +
        `<button class="pidv-btn on" data-k="run">${esc(X.cor_run)}</button>` +
        `<span class="pidv-note">${esc((S.cur.on ? X.rng_cur : X.rng_view) + ": " + fmtDur(b - a))}</span>`;
      c.querySelector("select").onchange = (e) => { S.cor.y = e.target.value; corRes = null; renderAn(); save(); };
      c.querySelectorAll("[data-m]").forEach((q) => q.onclick = () => { S.cor.mode = q.dataset.m; corRes = null; renderAn(); save(); });
      const li = c.querySelector('[data-k="lag"]');
      li.onchange = () => { const v = parseFloat(li.value.replace(",", ".")); S.cor.lag = isFinite(v) && v > 0 ? v : null; save(); };
      c.querySelector('[data-k="run"]').onclick = () => {
        const tgt = SG[S.cor.y], cands = order.filter((n) => n !== S.cor.y).slice(0, 80).map((n) => SG[n]);
        const run = (m) => Object.assign(AN.xcorr(tgt, cands, a, b, { mode: m, maxLag: S.cor.lag || (b - a) / 4 }), { mode: m });
        const best = (r) => (r.list.length ? Math.abs(r.list[0].r) : 0);
        if (S.cor.mode === "auto") {             // přírůstky obou, nebo přírůstky cíle (integrační proces) – silnější
          const r1 = run("incr"), r2 = run("int");
          corRes = best(r2) > 1.3 * best(r1) ? r2 : r1;
        } else corRes = run(S.cor.mode);
        corRes.target = S.cor.y;
        corSel = corRes.list.length ? corRes.list[0].name : null;
        renderAn();
      };
      bd.appendChild(c);
      bd.appendChild(el("div", "pidv-note", esc(X.cor_hint)));
      if (!corRes || corRes.target !== S.cor.y) return;
      if (S.cor.mode === "auto") bd.appendChild(el("div", "pidv-note", esc(X.cor_used.replace("{m}", corRes.mode === "int" ? X.cor_int : X.cor_incr))));
      const t = el("table", "pidv-tbl");
      t.innerHTML = `<thead><tr><th>${esc(X.signal)}</th><th>r</th><th>${esc(X.cor_lagc)}</th><th>${esc(X.cor_mean)}</th></tr></thead><tbody>` +
        corRes.list.map((q) => {
          const w = Math.round(Math.abs(q.r) * 60);
          const txt = Math.abs(q.r) < 0.15 ? X.cor_weak : q.lag > 0 ? X.cor_leads.replace("{s}", q.name).replace("{y}", S.cor.y).replace("{d}", fmtDur(q.lag, 3))
            : q.lag < 0 ? X.cor_lags.replace("{s}", q.name).replace("{y}", S.cor.y).replace("{d}", fmtDur(-q.lag, 3)) : X.cor_same;
          return `<tr data-n="${esc(q.name)}" class="${q.name === corSel ? "sel" : ""}"><td><span style="color:${colorOf(q.name)};font-weight:600">${esc(q.name)}</span></td>` +
            `<td><span class="pidv-bar2" style="width:${w}px;background:${q.r >= 0 ? "#16a34a" : "#dc2626"}"></span> ${fmtG(q.r, 3)}</td>` +
            `<td>${esc(fmtDur(q.lag, 3))}</td><td style="text-align:left">${esc(txt)}</td></tr>`;
        }).join("") + `</tbody>`;
      t.querySelectorAll("tbody tr").forEach((tr) => tr.onclick = () => { corSel = tr.dataset.n; renderAn(); });
      bd.appendChild(t);
      const q = corRes.list.find((x) => x.name === corSel);
      if (q) {
        const cv = el("canvas", "pidv-mini");
        bd.appendChild(cv);
        const n = q.curve.length, xs = new Float64Array(n);
        for (let i = 0; i < n; i++) xs[i] = (i - corRes.maxLag) * corRes.dt;
        mini(cv, 200, [{ xs, ys: q.curve, color: colorOf(q.name) }],
          { yr: [-1, 1], xtime: true, vmark: q.lag, hmark: 0, title: `r(τ): ${q.name} → ${S.cor.y}` });
      }
    }
    function anXY(bd) {
      S.xy.x = firstOf(S.xy.x, roleSig("MV"), visible()[0], order[0]);
      S.xy.y = firstOf(S.xy.y, roleSig("PV"), visible()[1], order[1], order[0]);
      const [a, b] = span2();
      const c = el("div", "pidv-row");
      c.innerHTML = `<span class="pidv-lab">X</span>${sigSel("x", S.xy.x)}<span class="pidv-lab">Y</span>${sigSel("y", S.xy.y)}` +
        `<label class="pidv-chk"><input type="checkbox" ${S.xy.line ? "checked" : ""}> ${esc(X.xy_line)}</label>` +
        `<span class="pidv-note">${esc((S.cur.on ? X.rng_cur : X.rng_view) + ": " + fmtDur(b - a) + " · " + X.xy_hint)}</span>`;
      c.querySelectorAll("select").forEach((q) => q.onchange = () => { S.xy[q.dataset.k] = q.value; renderAn(); save(); });
      c.querySelector("input").onchange = (e) => { S.xy.line = e.target.checked; renderAn(); save(); };
      bd.appendChild(c);
      const sx = SG[S.xy.x], sy = SG[S.xy.y];
      const base = sx.n >= sy.n ? sx : sy, i0 = lb(base.t, a, base.n), i1 = lb(base.t, b + 1e-12, base.n);
      const st = Math.max(1, Math.ceil((i1 - i0) / 20000)), m = Math.max(0, Math.ceil((i1 - i0) / st));
      const tq = new Float64Array(m);
      for (let i = 0; i < m; i++) tq[i] = base.t[i0 + i * st];
      const xs = AN.zoh(sx, tq), ys = AN.zoh(sy, tq), fit = AN.linfit(xs, ys);
      const cv = el("canvas", "pidv-mini");
      bd.appendChild(cv);
      mini(cv, 360, [], { scatter: { xs, ys }, line: S.xy.line, fit, xlab: S.xy.x + (unitOf(S.xy.x) ? ` [${unitOf(S.xy.x)}]` : ""),
                          ylab: S.xy.y + (unitOf(S.xy.y) ? ` [${unitOf(S.xy.y)}]` : ""), sx, sy });
      if (fit) bd.appendChild(el("div", "pidv-note", esc(X.xy_fit.replace("{k}", fmtG(fit.k, 4)).replace("{q}", fmtG(fit.q, 4))
        .replace("{r2}", fmtG(fit.r2, 3)).replace("{n}", fit.n))));
    }
    function anCmp(bd) {
      if (!S.cmp.sigs.length) S.cmp.sigs = [firstOf(roleSig("PV"), visible()[0], order[0])].filter(Boolean);
      const c = el("div", "pidv-row");
      c.innerHTML = `<span class="pidv-lab">${esc(X.cmp_sigs)}</span>` + order.filter((n) => panelOf(n) >= 0 || S.cmp.sigs.includes(n)).map((n) =>
        `<label class="pidv-chk"><input type="checkbox" value="${esc(n)}" ${S.cmp.sigs.includes(n) ? "checked" : ""}> <span style="color:${colorOf(n)}">${esc(n)}</span></label>`).join("") +
        `<button class="pidv-btn" data-k="view">+ ${esc(X.cmp_add_view)}</button>` +
        `<button class="pidv-btn" data-k="cur" ${S.cur.on ? "" : "disabled"}>+ ${esc(X.cmp_add_cur)}</button>` +
        `<label class="pidv-chk"><input type="checkbox" data-k="rel" ${S.cmp.rel ? "checked" : ""}> ${esc(X.cmp_rel)}</label>`;
      c.querySelectorAll("input[value]").forEach((i) => i.onchange = () => {
        S.cmp.sigs = order.filter((n) => (n === i.value ? i.checked : S.cmp.sigs.includes(n))).slice(0, 4);
        renderAn(); save();
      });
      c.querySelector('[data-k="rel"]').onchange = (e) => { S.cmp.rel = e.target.checked; renderAn(); save(); };
      const add = (q) => { if (S.cmp.segs.length < 8) { S.cmp.segs.push(q); renderAn(); save(); } };
      c.querySelector('[data-k="view"]').onclick = () => add([S.view[0], S.view[1]]);
      c.querySelector('[data-k="cur"]').onclick = () => add(span2());
      bd.appendChild(c);
      const chips = el("div", "pidv-row");
      S.cmp.segs.forEach((q, i) => {
        const ch = el("span", "pidv-segchip", `<i style="background:${SEGC[i]}"></i>${esc(fmtT(q[0]))} · ${esc(fmtDur(q[1] - q[0]))}` +
          ` <button class="pidv-x" title="${esc(X.cmp_go)}">↗</button><button class="pidv-x" title="${esc(X.remove)}">×</button>`);
        const [go, del] = ch.querySelectorAll("button");
        go.onclick = () => { push(true); S.view = [q[0], q[1]]; fixView(S); push(true); redraw(); save(); };
        del.onclick = () => { S.cmp.segs.splice(i, 1); renderAn(); save(); };
        chips.appendChild(ch);
      });
      bd.appendChild(chips);
      if (!S.cmp.segs.length) { bd.appendChild(el("div", "pidv-note", esc(X.cmp_hint))); return; }
      for (const n of S.cmp.sigs) {
        const s = SG[n];
        if (!s) continue;
        const series = S.cmp.segs.map((q, i) => {
          const j0 = lb(s.t, q[0], s.n), j1 = lb(s.t, q[1] + 1e-12, s.n), st = Math.max(1, Math.ceil((j1 - j0) / 4000));
          const m = Math.max(0, Math.ceil((j1 - j0) / st)), xs = new Float64Array(m), ys = new Float64Array(m);
          const v0 = j1 > j0 ? s.v[j0] : 0;
          for (let k = 0; k < m; k++) { const j = j0 + k * st; xs[k] = s.t[j] - q[0]; ys[k] = s.v[j] - (S.cmp.rel ? v0 : 0); }
          return { xs, ys, color: SEGC[i] };
        });
        const cv = el("canvas", "pidv-mini");
        bd.appendChild(cv);
        mini(cv, 190, series, { xtime: true, title: (S.cmp.rel ? "Δ " : "") + n + (unitOf(n) ? ` [${unitOf(n)}]` : ""), sy: s });
      }
    }
    function mini(cv, h, series, o) {          // malý graf: čáry (series) nebo body (o.scatter) s osami
      const w = cssW(anBox) - 24, g = sizeCanvas(cv, w, h);
      g.clearRect(0, 0, w, h);
      const LL = 62, RR = 12, TT = o.title ? 20 : 8, BB = 24;
      let xr = o.xr, yr = o.yr;
      const ext = (arrs) => { let a = Infinity, b = -Infinity; for (const A of arrs) for (let i = 0; i < A.length; i++) if (isFinite(A[i])) { if (A[i] < a) a = A[i]; if (A[i] > b) b = A[i]; } return [a, b]; };
      const pts = o.scatter ? [[o.scatter.xs], [o.scatter.ys]] : [series.map((q) => q.xs), series.map((q) => q.ys)];
      if (!xr) xr = ext(pts[0]);
      if (!yr) { yr = ext(pts[1]); const m = 0.06 * (yr[1] - yr[0] || Math.abs(yr[0]) || 1); yr = [yr[0] - m, yr[1] + m]; }
      if (!isFinite(xr[0]) || !isFinite(yr[0])) return;
      if (!(xr[1] > xr[0])) xr = [xr[0] - 1, xr[0] + 1];
      if (o.scatter) { const m = 0.04 * (xr[1] - xr[0]); xr = [xr[0] - m, xr[1] + m]; }
      const X_ = (v) => LL + (v - xr[0]) / (xr[1] - xr[0]) * (w - LL - RR), Y_ = (v) => h - BB - (v - yr[0]) / (yr[1] - yr[0]) * (h - TT - BB);
      g.strokeStyle = col("--pv-grid"); g.lineWidth = 1;
      g.font = "11px 'IBM Plex Mono', monospace"; g.fillStyle = col("--pv-muted");
      const u = o.xtime ? unitFor(Math.max(Math.abs(xr[0]), Math.abs(xr[1]))) : null, f = o.xtime ? U[u] : 1;
      const sx = nice((xr[1] - xr[0]) / f, Math.max(2, Math.floor(w / 110))), sy = nice(yr[1] - yr[0], Math.max(2, Math.floor(h / 40)));
      g.textAlign = "center"; g.textBaseline = "top";
      for (let v = Math.ceil(xr[0] / f / sx) * sx; v <= xr[1] / f + 1e-9; v += sx) {
        const x = Math.round(X_(v * f)) + 0.5;
        g.beginPath(); g.moveTo(x, TT); g.lineTo(x, h - BB); g.stroke();
        g.fillText(fmtTick(v, sx), x, h - BB + 5);
      }
      g.textAlign = "right"; g.textBaseline = "middle";
      for (let v = Math.ceil(yr[0] / sy) * sy; v <= yr[1] + 1e-12; v += sy) {
        const y = Math.round(Y_(v)) + 0.5;
        g.beginPath(); g.moveTo(LL, y); g.lineTo(w - RR, y); g.stroke();
        g.fillText(fmtTick(v, sy), LL - 5, y);
      }
      g.strokeStyle = col("--pv-axis");
      g.strokeRect(LL + 0.5, TT + 0.5, w - LL - RR - 1, h - TT - BB - 1);
      g.textAlign = "right"; g.textBaseline = "bottom";
      if (u) g.fillText(u, w - 2, h - 2);
      if (o.xlab) g.fillText(o.xlab, w - RR, h - BB - 3);
      if (o.title || o.ylab) { g.textAlign = "left"; g.textBaseline = "top"; g.fillStyle = col("--pv-text"); g.fillText(o.title || o.ylab, LL, 3); }
      g.save(); g.beginPath(); g.rect(LL, TT, w - LL - RR, h - TT - BB); g.clip();
      if (o.hmark !== undefined) { g.strokeStyle = col("--pv-muted"); g.beginPath(); g.moveTo(LL, Y_(o.hmark)); g.lineTo(w - RR, Y_(o.hmark)); g.stroke(); }
      if (o.vmark !== undefined) { g.strokeStyle = "#d97706"; g.setLineDash([4, 3]); g.beginPath(); g.moveTo(X_(o.vmark), TT); g.lineTo(X_(o.vmark), h - BB); g.stroke(); g.setLineDash([]); }
      g.lineWidth = 1.5;
      for (const q of series) {
        g.strokeStyle = q.color; g.beginPath();
        let pen = false;
        for (let i = 0; i < q.xs.length; i++) {
          if (!isFinite(q.ys[i])) { pen = false; continue; }
          const x = X_(q.xs[i]), y = Y_(q.ys[i]);
          if (pen) g.lineTo(x, y); else g.moveTo(x, y);
          pen = true;
        }
        g.stroke();
      }
      if (o.scatter) {
        const { xs, ys } = o.scatter, n = xs.length;
        if (o.line) {
          g.strokeStyle = col("--pv-axis"); g.lineWidth = 0.8; g.beginPath();
          for (let i = 0; i < n; i++) if (isFinite(xs[i]) && isFinite(ys[i])) { if (i) g.lineTo(X_(xs[i]), Y_(ys[i])); else g.moveTo(X_(xs[i]), Y_(ys[i])); }
          g.stroke();
        }
        for (let i = 0; i < n; i++) {
          if (!isFinite(xs[i]) || !isFinite(ys[i])) continue;
          g.fillStyle = `hsl(${220 - 220 * i / Math.max(1, n - 1)}, 70%, 45%)`;
          g.fillRect(X_(xs[i]) - 1.5, Y_(ys[i]) - 1.5, 3, 3);
        }
        if (o.fit) {
          g.strokeStyle = "#111827"; g.setLineDash([6, 4]); g.lineWidth = 1.3; g.beginPath();
          g.moveTo(X_(xr[0]), Y_(o.fit.k * xr[0] + o.fit.q)); g.lineTo(X_(xr[1]), Y_(o.fit.k * xr[1] + o.fit.q)); g.stroke(); g.setLineDash([]);
        }
      }
      g.restore();
      if (o.scatter) {                            // legenda barvy = čas
        g.textAlign = "left"; g.textBaseline = "top"; g.fillStyle = col("--pv-muted");
        const gx = w - RR - 140;
        const grad = g.createLinearGradient(gx, 0, gx + 80, 0);
        grad.addColorStop(0, "hsl(220,70%,45%)"); grad.addColorStop(1, "hsl(0,70%,45%)");
        g.fillStyle = grad; g.fillRect(gx, 6, 80, 6);
        g.fillStyle = col("--pv-muted"); g.fillText(X.xy_time || "", gx + 86, 2);
      }
    }

    // ---------------------------------------------------------------- ovládání
    function zoomX(f, tc) {
      const L0 = S.view[1] - S.view[0];
      const Ln = clamp(L0 * f, MINSPAN, D.T);
      const fr = (tc - S.view[0]) / L0;
      const a = clamp(tc - fr * Ln, 0, D.T - Ln);
      S.view = [a, a + Ln];
    }
    function panX(dt) {
      const Ln = S.view[1] - S.view[0];
      const a = clamp(S.view[0] + dt, 0, D.T - Ln);
      S.view = [a, a + Ln];
    }
    function axisAt(P, x) {                    // osa pod x v oblasti os, nebo null
      if (x >= L) return null;
      const k = Math.floor((L - 4 - x + 2) / AXW);
      return P.axes[k] || null;
    }
    const fresh = (P, a) => axesOf(P.pi).find((q) => q.key === a.key) || a;      // aktuální rozsah osy
    function zoomAxis(P, a, f, v0) { a = fresh(P, a); setAxis(P.pi, a.key, v0 - (v0 - a.lo) * f, v0 + (a.hi - v0) * f); }
    function panAxis(P, a, dy) { a = fresh(P, a); const dv = dy / (P.h - TOP - BOT) * (a.hi - a.lo); setAxis(P.pi, a.key, a.lo + dv, a.hi + dv); }
    const local = (node, e) => { const r = node.getBoundingClientRect(); return [e.clientX - r.left, e.clientY - r.top]; };

    function hookPanel(P) {
      const ov = P.ov;
      ov.addEventListener("wheel", (e) => {
        e.preventDefault();
        if (!P.axes.length) return;
        const [x, y] = local(ov, e), d = e.deltaY || e.deltaX, f = d > 0 ? 1.25 : 0.8;
        push();
        const ax = axisAt(P, x);
        if (ax) zoomAxis(P, ax, f, yv(y, ax, P));
        else if (e.shiftKey) for (const a of P.axes) zoomAxis(P, a, f, yv(y, a, P));
        else zoomX(f, xt(clamp(x, L, P.w - R), P));
        redraw(); save();
      }, { passive: false });
      ov.addEventListener("pointerdown", (e) => {
        if (e.button !== 0 || !P.axes.length) return;
        box.focus({ preventScroll: true });
        const [x, y] = local(ov, e);
        const ax = axisAt(P, x);
        let moved = false;
        const sx = e.clientX, sy = e.clientY;
        const finish = (mv, up) => {
          window.addEventListener("pointermove", mv);
          const u = (ev) => { window.removeEventListener("pointermove", mv); window.removeEventListener("pointerup", u); up(ev); };
          window.addEventListener("pointerup", u);
        };
        if (ax) {                                // tažení osy = posun té osy
          push(true);
          let ly = e.clientY;
          finish((ev) => { if (Math.abs(ev.clientY - sy) > 2) moved = true; panAxis(P, ax, ev.clientY - ly); ly = ev.clientY; redraw(); },
            () => { if (!moved) setAct(ax.names[0]); else { push(true); save(); } });
          return;
        }
        // kurzory
        const near = (xx) => Math.abs(xx - x) <= 6;
        let grab = null;
        if (S.cur.on) { if (near(tx(S.cur.a, P))) grab = "a"; else if (near(tx(S.cur.b, P))) grab = "b"; }
        let hgrab = null;
        if (!grab && S.hc.on && P.p.sigs.includes(S.hc.sig)) {
          const a = P.axes.find((q) => q.names.includes(S.hc.sig));
          if (a) { if (Math.abs(ty(S.hc.a, a, P) - y) <= 6) hgrab = ["a", a]; else if (Math.abs(ty(S.hc.b, a, P) - y) <= 6) hgrab = ["b", a]; }
        }
        if (grab) {
          S.acur = grab;
          finish((ev) => { const [xx] = local(ov, ev); S.cur[grab] = snapT(clamp(xt(xx, P), 0, D.T)); me.followRow = true; redrawOverlay(true); }, () => save());
          return;
        }
        if (hgrab) {
          finish((ev) => { const [, yy] = local(ov, ev); S.hc[hgrab[0]] = yv(clamp(yy, TOP, P.h - BOT), hgrab[1], P); redrawOverlay(true); }, () => save());
          return;
        }
        if (S.mode === "pan") {
          let lx = e.clientX, ly = e.clientY;
          push(true);
          finish((ev) => {
            if (Math.abs(ev.clientX - sx) + Math.abs(ev.clientY - sy) > 3) moved = true;
            if (!moved) return;
            if (e.shiftKey) for (const a of P.axes) panAxis(P, a, ev.clientY - ly);
            else panX(-(ev.clientX - lx) / (P.w - L - R) * (S.view[1] - S.view[0]));
            lx = ev.clientX; ly = ev.clientY;
            redraw();
          }, () => {
            if (moved) { push(true); save(); return; }
            if (S.cur.on) {                      // klik = nejbližší kurzor sem
              const t = snapT(clamp(xt(x, P), 0, D.T));
              const k = Math.abs(t - S.cur.a) <= Math.abs(t - S.cur.b) ? "a" : "b";
              S.cur[k] = t; S.acur = k; me.followRow = true;
              redrawOverlay(true); save();
            }
          });
          return;
        }
        band = { P, kind: S.mode, x0: x, y0: y, x1: x, y1: y };
        finish((ev) => { const [xx, yy] = local(ov, ev); band.x1 = clamp(xx, L, P.w - R); band.y1 = clamp(yy, TOP, P.h - BOT); drawOverlay(P); }, () => {
          const b = band;
          band = null;
          const okx = Math.abs(b.x1 - b.x0) > 4, oky = Math.abs(b.y1 - b.y0) > 4;
          push(true);
          if ((b.kind === "box" || b.kind === "x") && okx) {
            const a = xt(Math.min(b.x0, b.x1), P), c = xt(Math.max(b.x0, b.x1), P);
            S.view = [a, Math.max(c, a + MINSPAN)];
            fixView(S);
          }
          if ((b.kind === "box" || b.kind === "y") && oky) for (const a of P.axes) {
            const lo = yv(Math.max(b.y0, b.y1), a, P), hi = yv(Math.min(b.y0, b.y1), a, P);
            setAxis(P.pi, a.key, lo, hi);
          }
          push(true);
          redraw(); save();
        });
      });
      ov.addEventListener("dblclick", (e) => {
        const [x] = local(ov, e);
        const ax = axisAt(P, x);
        push(true);
        if (ax) clearAxis(P.pi, ax.key);
        else { S.view = [0, D.T]; for (const a of P.axes) clearAxis(P.pi, a.key); }
        push(true);
        redraw(); save(); me.rows && me.rows();
      });
      ov.addEventListener("mousemove", (e) => {
        const [x, y] = local(ov, e);
        const ax = axisAt(P, x);
        ov.style.cursor = ax ? "ns-resize" : S.mode === "pan" ? "grab" : "crosshair";
        if (S.cur.on && (Math.abs(tx(S.cur.a, P) - x) <= 6 || Math.abs(tx(S.cur.b, P) - x) <= 6)) ov.style.cursor = "ew-resize";
        if (x < L) { hoverT = null; tip.style.display = "none"; redrawOverlay(); return; }
        hoverT = xt(x, P);
        redrawOverlay();
        const own = P.p.sigs, rest = visible().filter((n) => !own.includes(n));
        const rows_ = own.concat(rest).slice(0, 14).map((n) => {
          const s = SG[n], i = nearest(s, hoverT);
          const far = i < 0 || Math.abs(s.t[i] - hoverT) > s.gap;
          return `<div><span style="color:${colorOf(n)}">■</span> ${esc(n)} <b>${far ? "–" : fmtV(s.v[i], s)}</b> ${esc(unitOf(n))}</div>`;
        });
        tip.innerHTML = `<div><b>${esc(fmtT(hoverT))}</b></div>` + rows_.join("");
        const br = box.getBoundingClientRect();
        tip.style.display = "block";
        const px = e.clientX - br.left, py = e.clientY - br.top;
        tip.style.left = (px + 16 + tip.offsetWidth > br.width ? px - tip.offsetWidth - 12 : px + 16) + "px";
        tip.style.top = (py + 14) + "px";
        void y;
      });
      ov.addEventListener("mouseleave", () => { hoverT = null; tip.style.display = "none"; redrawOverlay(); });
    }
    function hookXAxis() {
      const P = { get w() { return cssW(xcv.parentElement) - 16; } };
      xcv.addEventListener("wheel", (e) => {
        e.preventDefault();
        const [x] = local(xcv, e);
        push();
        zoomX((e.deltaY || e.deltaX) > 0 ? 1.25 : 0.8, xt(clamp(x, L, P.w - R), P));
        redraw(); save();
      }, { passive: false });
      xcv.addEventListener("pointerdown", (e) => {
        if (e.button !== 0) return;
        let lx = e.clientX;
        push(true);
        const mv = (ev) => { panX(-(ev.clientX - lx) / (P.w - L - R) * (S.view[1] - S.view[0])); lx = ev.clientX; redraw(); };
        const up = () => { window.removeEventListener("pointermove", mv); window.removeEventListener("pointerup", up); push(true); save(); };
        window.addEventListener("pointermove", mv);
        window.addEventListener("pointerup", up);
      });
      xcv.addEventListener("dblclick", () => { push(true); S.view = [0, D.T]; push(true); redraw(); save(); });
      xcv.style.cursor = "ew-resize";
    }
    function hookNav() {
      const W = () => cssW(nav.parentElement) - 16 - L - R;
      const tOf = (x) => clamp((x - L) / W() * D.T, 0, D.T);
      nav.addEventListener("pointerdown", (e) => {
        if (e.button !== 0) return;
        const [x] = local(nav, e);
        const xa = L + S.view[0] / D.T * W(), xb = L + S.view[1] / D.T * W();
        let kind = Math.abs(x - xa) <= 6 ? "a" : Math.abs(x - xb) <= 6 ? "b" : x > xa && x < xb ? "move" : "jump";
        push(true);
        if (kind === "jump") {
          const Ln = S.view[1] - S.view[0], c = tOf(x);
          const a = clamp(c - Ln / 2, 0, D.T - Ln);
          S.view = [a, a + Ln];
          kind = "move";
          redraw();
        }
        let lx = e.clientX;
        const mv = (ev) => {
          const dt = (ev.clientX - lx) / W() * D.T;
          lx = ev.clientX;
          if (kind === "move") panX(dt);
          else if (kind === "a") S.view[0] = clamp(S.view[0] + dt, 0, S.view[1] - MINSPAN);
          else S.view[1] = clamp(S.view[1] + dt, S.view[0] + MINSPAN, D.T);
          redraw();
        };
        const up = () => { window.removeEventListener("pointermove", mv); window.removeEventListener("pointerup", up); push(true); save(); };
        window.addEventListener("pointermove", mv);
        window.addEventListener("pointerup", up);
      });
      nav.addEventListener("mousemove", (e) => {
        const [x] = local(nav, e);
        const xa = L + S.view[0] / D.T * W(), xb = L + S.view[1] / D.T * W();
        nav.style.cursor = Math.abs(x - xa) <= 6 || Math.abs(x - xb) <= 6 ? "ew-resize" : x > xa && x < xb ? "grab" : "pointer";
      });
      nav.addEventListener("dblclick", () => { push(true); S.view = [0, D.T]; push(true); redraw(); save(); });
    }
    box.addEventListener("keydown", (e) => {
      if (e.target !== box) return;
      if (e.key === "Backspace") { e.preventDefault(); back(); }
      else if ((e.key === "ArrowLeft" || e.key === "ArrowRight") && S.cur.on) {
        e.preventDefault();
        const k = S.acur || "a", s = ref(), i = nearest(s, S.cur[k]);
        const j = clamp(i + (e.key === "ArrowLeft" ? -1 : 1) * (e.shiftKey ? 10 : 1), 0, s.n - 1);
        S.cur[k] = s.t[j];
        me.followRow = true;
        if (S.cur[k] < S.view[0] || S.cur[k] > S.view[1]) { const Ln = S.view[1] - S.view[0]; const a = clamp(S.cur[k] - Ln / 2, 0, D.T - Ln); S.view = [a, a + Ln]; redraw(); }
        else redrawOverlay(true);
        save();
      } else if (e.key === "Escape" && band) { band = null; redrawOverlay(); }
    });

    build();
    push(true);
    let lastW = box.clientWidth;
    const ro = new ResizeObserver(() => { if (box.clientWidth !== lastW) { lastW = box.clientWidth; redraw(); } });
    ro.observe(box);
    me.ro = ro;
  }
}
