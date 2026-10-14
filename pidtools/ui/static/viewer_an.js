/*
 * Výpočty prohlížeče záznamu (záložka Data) bez DOM – testuje je tests/test_viewer_js.py přes Node.js:
 *   expr   – bezpečné vzorce vypočtených signálů (vlastní parser, žádné eval / new Function);
 *   events – události v záznamu (skoky MV / SP / poruch, změny stavových signálů, MV na limitu, signál beze změny,
 *            výpadky dat);
 *   step   – odezva na skok mezi kurzory (zesílení, zpoždění, T63, náběh, překmit, ustálení; integrační proces);
 *   xcorr  – vzájemná korelace se zpožděním (FFT);
 *   zoh    – hodnoty signálu v zadaných časech (poslední známá hodnota).
 * Signál: {t: časy [s] vzestupně, v: hodnoty, n}.
 */
(function (root) {
  "use strict";

  // ------------------------------------------------------------------ pomocné
  function lb(a, x, n) {
    var lo = 0, hi = n;
    while (lo < hi) { var m = (lo + hi) >> 1; if (a[m] < x) lo = m + 1; else hi = m; }
    return lo;
  }
  function zoh(s, tq) {                     // hodnoty s v časech tq (poslední hodnota v čase ≤ t; před začátkem NaN)
    var out = new Float64Array(tq.length), j = 0;
    for (var i = 0; i < tq.length; i++) {
      while (j < s.n && s.t[j] <= tq[i] + 1e-12) j++;
      out[i] = j > 0 ? s.v[j - 1] : NaN;
    }
    return out;
  }
  function median(a) {
    var b = Array.prototype.slice.call(a).filter(function (x) { return isFinite(x); }).sort(function (x, y) { return x - y; });
    return b.length ? b[b.length >> 1] : NaN;
  }
  function medDt(s) {
    var k = Math.max(1, Math.floor(s.n / 4000)), d = [];
    for (var i = k; i < s.n; i += k) d.push(s.t[i] - s.t[i - 1]);
    var m = median(d);
    return isFinite(m) && m > 0 ? m : 1;
  }
  function range(s, i0, i1) {
    var a = Infinity, b = -Infinity;
    for (var i = i0; i < i1; i++) { var v = s.v[i]; if (v < a) a = v; if (v > b) b = v; }
    return [a, b];
  }

  // ------------------------------------------------------------------ vzorce
  // Gramatika: výraz s + - * / ^, porovnáním (< > <= >= == !=), and / or / not, čísly, signály (jméno nebo [jméno]
  // nebo "jméno"), proměnnými t (čas [s]) a pi a funkcemi FUNCS. Vyhodnocuje se po vektorech nad časy signálu.
  var FUNCS = {
    abs: [1, 1], sqrt: [1, 1], exp: [1, 1], ln: [1, 1], log10: [1, 1], sin: [1, 1], cos: [1, 1], sign: [1, 1],
    round: [1, 1], floor: [1, 1], min: [2, 9], max: [2, 9], clip: [3, 3], "if": [3, 3],
    lag: [2, 2], avg: [2, 2], der: [1, 1], diff: [1, 1], integ: [1, 1], delay: [2, 2],
  };
  var MAXLEN = 1000, MAXNODES = 300;
  function ExprError(msg, pos, arg) { this.msg = msg; this.pos = pos; this.arg = arg; }

  function tokenize(src) {
    var out = [], i = 0, n = src.length;
    while (i < n) {
      var c = src[i];
      if (/\s/.test(c)) { i++; continue; }
      var st = i;
      if (/[0-9.]/.test(c)) {
        var m = /^(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?/.exec(src.slice(i));
        if (!m) throw new ExprError("bad_number", i);
        out.push({ k: "num", v: parseFloat(m[0]), p: st });
        i += m[0].length;
      } else if (/[A-Za-z_]/.test(c)) {
        var m2 = /^[A-Za-z_][A-Za-z0-9_.]*/.exec(src.slice(i));
        var w = m2[0];
        i += w.length;
        if (w === "and" || w === "or" || w === "not") out.push({ k: "op", v: w, p: st });
        else out.push({ k: "id", v: w, p: st });
      } else if (c === "[" || c === '"') {
        var end = src.indexOf(c === "[" ? "]" : '"', i + 1);
        if (end < 0) throw new ExprError("unclosed", i);
        out.push({ k: "sig", v: src.slice(i + 1, end), p: st });
        i = end + 1;
      } else {
        var two = src.slice(i, i + 2);
        if (["<=", ">=", "==", "!="].indexOf(two) >= 0) { out.push({ k: "op", v: two, p: st }); i += 2; }
        else if ("+-*/^<>(),".indexOf(c) >= 0) { out.push({ k: c === "(" || c === ")" || c === "," ? c : "op", v: c, p: st }); i++; }
        else throw new ExprError("bad_char", i, c);
      }
    }
    out.push({ k: "end", p: n });
    return out;
  }

  var BP = { or: 1, and: 2, "<": 3, ">": 3, "<=": 3, ">=": 3, "==": 3, "!=": 3, "+": 4, "-": 4, "*": 5, "/": 5, "^": 7 };

  // parse(src, names) → {ast, refs}; names = známé signály (pole nebo Set)
  function parse(src, names) {
    if (typeof src !== "string" || !src.trim()) throw new ExprError("empty", 0);
    if (src.length > MAXLEN) throw new ExprError("too_long", MAXLEN);
    var known = names instanceof Set ? names : new Set(names || []);
    var tk = tokenize(src), i = 0, nodes = 0, refs = new Set();
    function node(o) { if (++nodes > MAXNODES) throw new ExprError("too_long", o.p || 0); return o; }
    function peek() { return tk[i]; }
    function next() { return tk[i++]; }
    function expect(k) { var t = next(); if (t.k !== k) throw new ExprError("expected", t.p, k); return t; }
    function prefix() {
      var t = next();
      if (t.k === "num") return node({ k: "num", v: t.v, p: t.p });
      if (t.k === "sig") {
        if (!known.has(t.v)) throw new ExprError("unknown_sig", t.p, t.v);
        refs.add(t.v);
        return node({ k: "sig", v: t.v, p: t.p });
      }
      if (t.k === "id") {
        if (peek().k === "(") {
          if (!Object.prototype.hasOwnProperty.call(FUNCS, t.v)) throw new ExprError("unknown_fn", t.p, t.v);
          next();
          var args = [];
          if (peek().k !== ")") {
            args.push(expr(0));
            while (peek().k === ",") { next(); args.push(expr(0)); }
          }
          expect(")");
          var ar = FUNCS[t.v];
          if (args.length < ar[0] || args.length > ar[1]) throw new ExprError("bad_args", t.p, t.v);
          return node({ k: "fn", v: t.v, a: args, p: t.p });
        }
        if (t.v === "t" || t.v === "pi") return node({ k: "var", v: t.v, p: t.p });
        if (!known.has(t.v)) throw new ExprError("unknown_sig", t.p, t.v);
        refs.add(t.v);
        return node({ k: "sig", v: t.v, p: t.p });
      }
      if (t.k === "(") { var e = expr(0); expect(")"); return e; }
      if (t.k === "op" && (t.v === "-" || t.v === "+")) return node({ k: "neg", s: t.v === "-", a: expr(6), p: t.p });
      if (t.k === "op" && t.v === "not") return node({ k: "not", a: expr(2.5), p: t.p });
      throw new ExprError(t.k === "end" ? "unexpected_end" : "unexpected", t.p);
    }
    function expr(minbp) {
      var left = prefix();
      for (;;) {
        var t = peek();
        if (t.k !== "op" || !(t.v in BP)) break;
        var bp = BP[t.v];
        if (bp < minbp || (bp === minbp && t.v !== "^")) break;
        next();
        var right = expr(t.v === "^" ? bp : bp + 0.01);
        left = node({ k: "bin", v: t.v, a: left, b: right, p: t.p });
      }
      return left;
    }
    var ast = expr(0);
    if (peek().k !== "end") throw new ExprError("unexpected", peek().p);
    return { ast: ast, refs: Array.from(refs) };
  }

  // evaluate(ast, ctx) → Float64Array; ctx = {t: časy (Float64Array), n, sig: jméno → Float64Array zarovnané na t}
  function evaluate(ast, ctx) {
    var n = ctx.n, t = ctx.t;
    var isA = function (x) { return typeof x !== "number"; };
    function map1(a, f) {
      if (!isA(a)) return f(a);
      var o = new Float64Array(n);
      for (var i = 0; i < n; i++) o[i] = f(a[i]);
      return o;
    }
    function map2(a, b, f) {
      if (!isA(a) && !isA(b)) return f(a, b);
      var o = new Float64Array(n);
      for (var i = 0; i < n; i++) o[i] = f(isA(a) ? a[i] : a, isA(b) ? b[i] : b);
      return o;
    }
    function vec(a) { if (isA(a)) return a; var o = new Float64Array(n); o.fill(a); return o; }
    function scalar(a, p, fn) {
      if (isA(a)) throw new ExprError("need_number", p, fn);
      return a;
    }
    var B = {
      "+": function (x, y) { return x + y; }, "-": function (x, y) { return x - y; },
      "*": function (x, y) { return x * y; }, "/": function (x, y) { return x / y; },
      "^": function (x, y) { return Math.pow(x, y); },
      "<": function (x, y) { return x < y ? 1 : 0; }, ">": function (x, y) { return x > y ? 1 : 0; },
      "<=": function (x, y) { return x <= y ? 1 : 0; }, ">=": function (x, y) { return x >= y ? 1 : 0; },
      "==": function (x, y) { return x === y ? 1 : 0; }, "!=": function (x, y) { return x !== y ? 1 : 0; },
      and: function (x, y) { return x && y ? 1 : 0; }, or: function (x, y) { return x || y ? 1 : 0; },
    };
    var U = { abs: Math.abs, sqrt: Math.sqrt, exp: Math.exp, ln: Math.log, log10: Math.log10, sin: Math.sin,
              cos: Math.cos, sign: Math.sign, round: Math.round, floor: Math.floor };
    function ev(e) {
      switch (e.k) {
        case "num": return e.v;
        case "var": return e.v === "pi" ? Math.PI : t;
        case "sig": return ctx.sig(e.v);
        case "neg": { var a = ev(e.a); return e.s ? map1(a, function (x) { return -x; }) : a; }
        case "not": return map1(ev(e.a), function (x) { return x ? 0 : 1; });
        case "bin": return map2(ev(e.a), ev(e.b), B[e.v]);
        case "fn": {
          var f = e.v, A = e.a.map(ev);
          if (U[f]) return map1(A[0], U[f]);
          if (f === "min" || f === "max") {
            var r = A[0];
            for (var k = 1; k < A.length; k++) r = map2(r, A[k], Math[f]);
            return r;
          }
          if (f === "clip") return map2(map2(A[0], A[1], Math.max), A[2], Math.min);
          if (f === "if") {
            var c = A[0], a1 = A[1], a2 = A[2];
            if (!isA(c) && !isA(a1) && !isA(a2)) return c ? a1 : a2;
            var o = new Float64Array(n);
            for (var i = 0; i < n; i++) o[i] = (isA(c) ? c[i] : c) ? (isA(a1) ? a1[i] : a1) : (isA(a2) ? a2[i] : a2);
            return o;
          }
          var x = vec(A[0]), y = new Float64Array(n), j;
          if (f === "lag") {                     // filtr 1. řádu s časovou konstantou T [s]
            var T = scalar(A[1], e.p, f);
            var st = NaN;
            for (j = 0; j < n; j++) {
              if (!isFinite(x[j])) { y[j] = st; continue; }
              if (!isFinite(st) || T <= 0) st = x[j];
              else st += (1 - Math.exp(-(t[j] - t[j - 1]) / T)) * (x[j] - st);
              y[j] = st;
            }
            return y;
          }
          if (f === "avg") {                     // klouzavý průměr za posledních T [s]
            var W = scalar(A[1], e.p, f), s0 = 0, cnt = 0, lo = 0;
            for (j = 0; j < n; j++) {
              if (isFinite(x[j])) { s0 += x[j]; cnt++; }
              while (t[lo] < t[j] - W) { if (isFinite(x[lo])) { s0 -= x[lo]; cnt--; } lo++; }
              y[j] = cnt ? s0 / cnt : NaN;
            }
            return y;
          }
          if (f === "der" || f === "diff") {
            y[0] = f === "diff" ? 0 : NaN;
            for (j = 1; j < n; j++) y[j] = f === "diff" ? x[j] - x[j - 1] : (x[j] - x[j - 1]) / Math.max(t[j] - t[j - 1], 1e-12);
            if (f === "der" && n > 1) y[0] = y[1];
            return y;
          }
          if (f === "integ") {
            y[0] = 0;
            for (j = 1; j < n; j++) y[j] = y[j - 1] + (isFinite(x[j]) && isFinite(x[j - 1]) ? 0.5 * (x[j] + x[j - 1]) * (t[j] - t[j - 1]) : 0);
            return y;
          }
          if (f === "delay") {                   // hodnota před T [s]
            var D = scalar(A[1], e.p, f), q = 0;
            for (j = 0; j < n; j++) {
              var tt = t[j] - D;
              while (q < n && t[q] <= tt + 1e-12) q++;
              y[j] = q > 0 ? x[q - 1] : NaN;
            }
            return y;
          }
          throw new ExprError("unknown_fn", e.p, f);
        }
      }
      throw new ExprError("unexpected", e.p);
    }
    return vec(ev(ast));
  }

  // ------------------------------------------------------------------ události
  // events(sigs, opts) → [{t, t1, kind, sig, d (změna / délka), a, b}] seřazené podle času
  //   sigs: [{name, role, t, v, n, ti}]; kind: "mv" | "sp" | "dv" (skok), "state" (změna stavu), "sat" (MV na limitu),
  //   "flat" (signál beze změny), "gap" (výpadek dat)
  var MAXEV = 400;
  function stepsOf(s, kind, frac) {
    var n = s.n, out = [];
    if (n < 5) return out;
    var dv = new Float64Array(n - 1);
    for (var i = 1; i < n; i++) dv[i - 1] = s.v[i] - s.v[i - 1];
    var k = Math.max(1, Math.floor((n - 1) / 20000)), smp = [];
    for (var j = 0; j < n - 1; j += k) smp.push(dv[j]);
    var med = median(smp), dev = median(smp.map(function (x) { return Math.abs(x - med); })) * 1.4826;
    var r = range(s, 0, n), span = r[1] - r[0];
    if (!(span > 0)) return out;
    var thr = Math.max(6 * dev, frac * span, 1e-12);
    for (i = 0; i < n - 1; i++) {
      if (Math.abs(dv[i]) <= thr) continue;
      var sg = Math.sign(dv[i]), a = i, b = i;      // souvislá řada změn stejného směru (rampa přes pár vzorků)
      while (b + 1 < n - 1 && b - a < 6 && Math.sign(dv[b + 1]) === sg && Math.abs(dv[b + 1]) > thr / 3) b++;
      var d = s.v[b + 1] - s.v[a];
      if (Math.abs(d) > thr) out.push({ t: s.t[a + 1], kind: kind, sig: s.name, d: d, a: s.v[a], b: s.v[b + 1] });
      i = b;
      if (out.length > MAXEV) return [];          // signál je příliš živý – skoky nemají smysl
    }
    return out;
  }
  function stateValues(s) {                       // stavový signál: nejvýš 6 různých hodnot
    var set = new Set();
    for (var i = 0; i < s.n; i++) { set.add(s.v[i]); if (set.size > 6) return null; }
    return set.size >= 2 ? set : null;
  }
  function events(sigs, opts) {
    opts = opts || {};
    var out = [], gapsDone = new Set();
    sigs.forEach(function (s) {
      if (s.n < 3) return;
      var dt = medDt(s), ev = [];
      var states = s.role ? null : stateValues(s);   // smyčkové signály (MV, SP…) se hodnotí jako skoky
      if (states) {
        for (var i = 1; i < s.n; i++) if (s.v[i] !== s.v[i - 1]) ev.push({ t: s.t[i], kind: "state", sig: s.name, a: s.v[i - 1], b: s.v[i] });
        if (ev.length > MAXEV) ev = [];
      } else {
        if (s.role === "MV" || s.role === "SP" || s.role === "DV")
          ev = ev.concat(stepsOf(s, s.role.toLowerCase(), s.role === "SP" ? 0.002 : s.role === "MV" ? 0.01 : 0.03));
        var r = range(s, 0, s.n), span = r[1] - r[0];
        var minRun = Math.max(30 * dt, opts.flatMin || 60);
        if (s.role === "MV" && span > 0 && r[0] >= -5 && r[1] <= 105) {   // MV [%] na limitu 0 / 100 %
          [[r[0], 1], [r[1], -1]].filter(function (lim) { return lim[0] <= 1 || lim[0] >= 99; }).forEach(function (lim) {
            var tol = 0.002 * span, i0 = -1, cnt = 0;
            for (var i = 0; i <= s.n; i++) {
              var on = i < s.n && Math.abs(s.v[i] - lim[0]) <= tol;
              if (on && i0 < 0) i0 = i;
              if (!on && i0 >= 0) {
                if (s.t[i - 1] - s.t[i0] >= minRun && cnt++ < MAXEV) ev.push({ t: s.t[i0], t1: s.t[i - 1], kind: "sat", sig: s.name, a: lim[0], d: s.t[i - 1] - s.t[i0] });
                i0 = -1;
              }
            }
          });
        }
        if (s.role !== "SP" && span > 0) {          // beze změny: přesně stejná hodnota déle než minRun u živého signálu
          var same = 0;
          for (var q = 1; q < s.n; q++) if (s.v[q] === s.v[q - 1]) same++;
          if (same < 0.5 * (s.n - 1)) {
            var j0 = 0, cf = 0;
            for (var j = 1; j <= s.n; j++) {
              if (j < s.n && s.v[j] === s.v[j0]) continue;
              var dur = s.t[j - 1] - s.t[j0];
              if (j - 1 > j0 && dur >= minRun && cf++ < MAXEV) {
                var atLim = s.role === "MV" && (s.v[j0] <= r[0] + 0.002 * span || s.v[j0] >= r[1] - 0.002 * span);
                if (!atLim) ev.push({ t: s.t[j0], t1: s.t[j - 1], kind: "flat", sig: s.name, a: s.v[j0], d: dur });
              }
              j0 = j;
            }
          }
        }
      }
      if (!gapsDone.has(s.ti)) {                    // výpadky dat (jednou pro každou časovou osu)
        gapsDone.add(s.ti);
        var gmin = Math.max(5 * dt, opts.gapMin || 0), cg = 0;
        for (var g = 1; g < s.n; g++) if (s.t[g] - s.t[g - 1] > gmin && cg++ < MAXEV)
          ev.push({ t: s.t[g - 1], t1: s.t[g], kind: "gap", sig: s.name, d: s.t[g] - s.t[g - 1] });
      }
      out = out.concat(ev);
    });
    out.sort(function (x, y) { return x.t - y.t; });
    return out;
  }

  // ------------------------------------------------------------------ odezva na skok
  function mean(s, i0, i1) { var a = 0, c = 0; for (var i = i0; i < i1; i++) { a += s.v[i]; c++; } return c ? a / c : NaN; }
  function slope(s, i0, i1) {                     // směrnice regresní přímky [1/s]
    var n = i1 - i0;
    if (n < 3) return 0;
    var mt = 0, mv = 0, i;
    for (i = i0; i < i1; i++) { mt += s.t[i]; mv += s.v[i]; }
    mt /= n; mv /= n;
    var sxy = 0, sxx = 0;
    for (i = i0; i < i1; i++) { sxy += (s.t[i] - mt) * (s.v[i] - mv); sxx += (s.t[i] - mt) * (s.t[i] - mt); }
    return sxx > 0 ? sxy / sxx : 0;
  }
  // step(u, y, a, b) → {ok, err, ts, du, u0, u1, y0, yinf, dy, K, theta, T, t63, tr, ovs, tset, integ, Ki, tth}
  function step(u, y, a, b) {
    var ua = lb(u.t, a, u.n), ub = lb(u.t, b + 1e-12, u.n);
    if (ub - ua < 4) return { ok: false, err: "few" };
    var best = -1, bi = -1;
    for (var i = ua + 1; i < ub; i++) {
      var d = Math.abs(u.v[i] - u.v[i - 1]);
      if (d > best) { best = d; bi = i; }
    }
    var ts = u.t[bi];
    var u0 = mean(u, ua, bi), u1 = mean(u, bi, ub);
    var ru = range(u, ua, ub);
    if (!(Math.abs(u1 - u0) > 1e-9 * Math.max(1, Math.abs(ru[1]))) || bi - ua < 1) return { ok: false, err: "no_step" };
    // ustálená hodnota vstupu po skoku: druhá polovina
    var um = lb(u.t, ts + 0.5 * (b - ts), u.n);
    u1 = mean(u, Math.max(bi, um), ub);
    var du = u1 - u0;
    var ya = lb(y.t, a, y.n), ys = lb(y.t, ts, y.n), yb = lb(y.t, b + 1e-12, y.n);
    if (ys - ya < 3) return { ok: false, err: "c1_late" };
    if (yb - ys < 8) return { ok: false, err: "c2_early" };
    var y0 = mean(y, ya, ys), sd = 0;
    for (i = ya; i < ys; i++) sd += (y.v[i] - y0) * (y.v[i] - y0);
    sd = Math.sqrt(sd / (ys - ya));
    var sPre = slope(y, ya, ys);
    var tail = Math.max(ys + 1, lb(y.t, b - 0.1 * (b - ts), y.n));
    if (yb - tail < 5) tail = Math.max(ys + 1, yb - 5);
    var yinf = mean(y, tail, yb);
    var dy = yinf - y0;
    var q3 = lb(y.t, b - 0.25 * (b - ts), y.n), sEnd = slope(y, q3, yb);
    var integ = Math.abs((sEnd - sPre) * (b - ts)) > 0.3 * Math.max(Math.abs(dy), 1e-12) && Math.abs(sEnd) * (b - ts) > 4 * sd;
    var res = { ok: true, ts: ts, du: du, u0: u0, u1: u1, y0: y0, yinf: yinf, dy: dy, sd: sd, integ: integ };
    if (integ) {
      res.Ki = (sEnd - sPre) / du;
      res.K = null;
    } else res.K = dy / du;
    var ref = integ ? (sEnd - sPre) * (b - ts) : dy;  // směr a velikost změny výstupu
    var sg = ref >= 0 ? 1 : -1, thr = Math.max(4 * sd, 0.03 * Math.abs(ref));
    var tth = null;
    for (i = ys; i < yb; i++) if (sg * (y.v[i] - y0 - sPre * (y.t[i] - ts)) > thr) { tth = y.t[i]; break; }
    res.theta = tth === null ? null : tth - ts;
    res.tth = tth;
    if (integ) return res;
    function cross(f) {
      var lvl = y0 + f * dy;
      for (var k = ys; k < yb; k++) if (sg * (y.v[k] - lvl) >= 0) return y.t[k];
      return null;
    }
    var t10 = cross(0.1), t28 = cross(0.283), t63 = cross(0.632), t90 = cross(0.9);
    res.t63 = t63;
    if (t28 !== null && t63 !== null) {          // dvoubodová metoda (28,3 % a 63,2 %): T a θ modelu 1. řádu se zpožděním
      res.T = 1.5 * (t63 - t28);
      res.theta = Math.max(0, t63 - ts - res.T);
    } else res.T = null;
    res.tr = t10 !== null && t90 !== null ? t90 - t10 : null;
    var ext = sg > 0 ? -Infinity : Infinity;
    for (i = ys; i < yb; i++) ext = sg > 0 ? Math.max(ext, y.v[i]) : Math.min(ext, y.v[i]);
    res.ovs = Math.abs(dy) > 0 ? Math.max(0, sg * (ext - yinf) / Math.abs(dy)) : 0;
    var band = 0.05 * Math.abs(dy), last = null;
    for (i = ys; i < yb; i++) if (Math.abs(y.v[i] - yinf) > band) last = y.t[i];
    res.tset = last === null ? 0 : (last < y.t[yb - 1] - 1e-9 ? last - ts : null);
    return res;
  }

  // ------------------------------------------------------------------ vzájemná korelace
  function fft(re, im, inv) {                     // na místě, délka = mocnina 2
    var n = re.length, i, j, k;
    for (i = 1, j = 0; i < n; i++) {
      var bit = n >> 1;
      for (; j & bit; bit >>= 1) j ^= bit;
      j ^= bit;
      if (i < j) { var tr = re[i]; re[i] = re[j]; re[j] = tr; var ti = im[i]; im[i] = im[j]; im[j] = ti; }
    }
    for (var len = 2; len <= n; len <<= 1) {
      var ang = 2 * Math.PI / len * (inv ? 1 : -1), wr = Math.cos(ang), wi = Math.sin(ang);
      for (i = 0; i < n; i += len) {
        var cr = 1, ci = 0;
        for (k = 0; k < len / 2; k++) {
          var a = i + k, b = a + len / 2;
          var xr = re[b] * cr - im[b] * ci, xi = re[b] * ci + im[b] * cr;
          re[b] = re[a] - xr; im[b] = im[a] - xi; re[a] += xr; im[a] += xi;
          var nr = cr * wr - ci * wi; ci = cr * wi + ci * wr; cr = nr;
        }
      }
    }
    if (inv) for (i = 0; i < n; i++) { re[i] /= n; im[i] /= n; }
  }
  function grid(a, b, dt) {
    var n = Math.max(2, Math.floor((b - a) / dt) + 1), g = new Float64Array(n);
    for (var i = 0; i < n; i++) g[i] = a + i * dt;
    return g;
  }
  function prep(x, incr) {                         // přírůstky (nebo hodnoty) bez průměru; NaN → 0
    var n = x.length, o = new Float64Array(incr ? n - 1 : n), m = 0, c = 0, i;
    for (i = 0; i < o.length; i++) { o[i] = incr ? x[i + 1] - x[i] : x[i]; if (isFinite(o[i])) { m += o[i]; c++; } }
    m = c ? m / c : 0;
    var ss = 0;
    for (i = 0; i < o.length; i++) { o[i] = isFinite(o[i]) ? o[i] - m : 0; ss += o[i] * o[i]; }
    return { x: o, sd: Math.sqrt(ss / Math.max(1, o.length)) };
  }
  function binMean(s, g, dt) {                   // průměr vzorků v intervalech [g, g + dt) (méně šumu); prázdný = poslední
    var out = new Float64Array(g.length), j = lb(s.t, g[0], s.n), last = j > 0 ? s.v[j - 1] : NaN;
    for (var i = 0; i < g.length; i++) {
      var e = g[i] + dt, a = 0, c = 0;
      while (j < s.n && s.t[j] < e) { a += s.v[j]; c++; j++; }
      if (c) last = a / c;
      out[i] = last;
    }
    return out;
  }
  // xcorr(target, cands, a, b, opts{dt, maxLag, mode}) → {dt, maxLag, list: [{name, r, lag, curve}]} seřazené podle |r|
  //   mode: "incr" = přírůstky obou, "vals" = hodnoty, "int" = přírůstky cíle a hodnoty signálu (integrační proces);
  //   lag > 0 = signál předbíhá cíl (změna signálu se v cíli projeví o lag později)
  function xcorr(target, cands, a, b, opts) {
    opts = opts || {};
    var dt = opts.dt || Math.max(medDt(target), (b - a) / 2048);
    var g = grid(a, b, dt), N = g.length;
    var mode = opts.mode || (opts.incr === false ? "vals" : "incr");
    var Y = prep(binMean(target, g, dt), mode !== "vals"), M = Y.x.length;
    var maxLag = Math.min(Math.floor((opts.maxLag || (b - a) / 4) / dt), M - 2);
    var L = 1;
    while (L < 2 * M) L <<= 1;
    var yr = new Float64Array(L), yi = new Float64Array(L);
    yr.set(Y.x);
    fft(yr, yi, false);
    var list = [];
    cands.forEach(function (s) {
      var X = prep(binMean(s, g, dt), mode === "incr");
      if (X.x.length > M) X.x = X.x.subarray(1);   // hodnoty k přírůstkům cíle: zarovnat na konec intervalu
      if (!(X.sd > 0) || !(Y.sd > 0)) return;
      var xr = new Float64Array(L), xi = new Float64Array(L);
      xr.set(X.x);
      fft(xr, xi, false);
      // c[k] = Σ x[i] · y[i + k]  →  IFFT(conj(X) · Y)
      var cr = new Float64Array(L), ci = new Float64Array(L);
      for (var i = 0; i < L; i++) { cr[i] = xr[i] * yr[i] + xi[i] * yi[i]; ci[i] = xr[i] * yi[i] - xi[i] * yr[i]; }
      fft(cr, ci, true);
      var curve = new Float64Array(2 * maxLag + 1), best = 0, bl = 0, norm = M * X.sd * Y.sd;
      for (var k = -maxLag; k <= maxLag; k++) {
        var v = cr[(k + L) % L] / norm;
        curve[k + maxLag] = v;
        if (Math.abs(v) > Math.abs(best)) { best = v; bl = k; }
      }
      list.push({ name: s.name, r: best, lag: bl * dt, curve: curve });
    });
    list.sort(function (p, q) { return Math.abs(q.r) - Math.abs(p.r); });
    void N;
    return { dt: dt, maxLag: maxLag, list: list };
  }

  // lineární regrese y = k·x + q, R²
  function linfit(x, y) {
    var n = 0, mx = 0, my = 0, i;
    for (i = 0; i < x.length; i++) if (isFinite(x[i]) && isFinite(y[i])) { mx += x[i]; my += y[i]; n++; }
    if (n < 3) return null;
    mx /= n; my /= n;
    var sxy = 0, sxx = 0, syy = 0;
    for (i = 0; i < x.length; i++) if (isFinite(x[i]) && isFinite(y[i])) {
      sxy += (x[i] - mx) * (y[i] - my); sxx += (x[i] - mx) * (x[i] - mx); syy += (y[i] - my) * (y[i] - my);
    }
    if (!(sxx > 0)) return null;
    var k = sxy / sxx;
    return { k: k, q: my - k * mx, r2: syy > 0 ? sxy * sxy / (sxx * syy) : 1, n: n };
  }

  function steps(s, frac) { return stepsOf(s, "step", frac === undefined ? 0.01 : frac); }

  var api = { lb: lb, zoh: zoh, median: median, medDt: medDt, parse: parse, evaluate: evaluate, ExprError: ExprError, steps: steps,
              FUNCS: FUNCS, events: events, step: step, fft: fft, xcorr: xcorr, linfit: linfit, grid: grid };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.PIDViewAn = api;
})(typeof window !== "undefined" ? window : globalThis);
