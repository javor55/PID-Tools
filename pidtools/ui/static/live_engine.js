/*
 * Živá simulace v prohlížeči – přepis pidtools/core/simulation.py (ProcStep, PIDConL, Valve, LiveLoop).
 * Musí se chovat stejně jako Python (ověřuje tests/test_live_js.py přes Node.js). Vše v % normovacích rozsahů.
 */
(function (root) {
  "use strict";

  function ProcStep(code, p, h) {
    this.code = code; this.p = p.slice(); this.h = h;
    var n = Math.max(1, Math.round(p[p.length - 1] / h));
    this.q = new Array(n).fill(0); this.qi = 0;              // kruhová fronta dopravního zpoždění
    this.a1 = (code === "P1D" || code === "P2D" || code === "I1D") ? Math.exp(-h / p[1]) : 0;
    this.a2 = code === "P2D" ? Math.exp(-h / p[2]) : 0;
    this.x1 = 0; this.x2 = 0; this.z = 0;
  }
  ProcStep.prototype.output = function () {
    var c = this.code;
    if (c === "P0D") return this.p[0] * this.q[this.qi];
    if (c === "P1D") return this.p[0] * this.x1;
    if (c === "P2D") return this.p[0] * this.x2;
    return this.z;
  };
  ProcStep.prototype.step = function (u) {
    var ud = this.q[this.qi];
    this.q[this.qi] = u; this.qi = (this.qi + 1) % this.q.length;
    var c = this.code;
    if (c === "P1D" || c === "P2D" || c === "I1D") {
      var x1n = this.a1 * this.x1 + (1 - this.a1) * ud;
      if (c === "P2D") this.x2 = this.a2 * this.x2 + (1 - this.a2) * this.x1;
      this.x1 = x1n;
    }
    if (c === "I0D") this.z += this.p[0] * ud * this.h;
    else if (c === "I1D") this.z += this.p[0] * this.x1 * this.h;
  };

  function deadband(e, db, mode) {
    if (db <= 0 || Math.abs(e) >= db) return (db > 0 && (mode === "cont" || mode === "spojité")) ? e - Math.sign(e) * db : e;
    return 0;
  }
  function num(v, d) { return (v === undefined || v === null) ? d : v; }

  function PIDConL(ctrl, h) {
    this.h = h;
    this.m = Math.max(1, Math.round(ctrl.SampleTime / h));
    this.Tc = this.m * h;
    this.lo = num(ctrl.MV_Lo, -Infinity); this.hi = num(ctrl.MV_Hi, Infinity);
    this.db = num(ctrl.DeadBand, 0); this.dbm = num(ctrl.DbMode, "cont");                 // "cont" | "step" (starší projekty: "spojité" / "skokové")
    this.b = (ctrl.PropFacSP === undefined || ctrl.PropFacSP === null) ? (ctrl.PropFbk ? 0 : 1)
      : Math.min(Math.max(ctrl.PropFacSP, 0), 1);
    this.dfb = !!ctrl.DiffFbk;
    this.Tpv = num(ctrl.PVFilt, 0) || 0;
    this.apv = this.Tpv > 0 ? Math.exp(-h / this.Tpv) : 0;
    this.rate = num(ctrl.MVRate, 0) || 0; this.sprate = num(ctrl.SPRate, 0) || 0;
    this.N = Math.max(num(ctrl.DiffGain, 5), 1e-6);
    this.setGains(ctrl.Gain, ctrl.TI, ctrl.TD);
    this.k = 0;
  }
  PIDConL.prototype.setGains = function (Kc, Ti, Td) {
    this.Kc = Kc; this.Ti = Ti; this.Td = Td;
    this.useI = Ti !== null && isFinite(Ti) && Ti > 0;
    this.Tf = Td > 0 ? Td / this.N : 0;
  };
  PIDConL.prototype.pTerm = function (e) { return this.Kc * (this.b * e - (1 - this.b) * this.yf); };
  PIDConL.prototype.init = function (sp, y, u0) {
    this.yf = y; this.spr = sp;
    var e = deadband(this.spr - this.yf, this.db, this.dbm);
    this.I = u0 - this.pTerm(e); this.D = 0;
    this.xdPrev = this.dfb ? -this.yf : e;
    this.u = this.uPrev = u0;
  };
  PIDConL.prototype.setTuning = function (Kc, Ti, Td) {      // bez rázu výstupu
    var e = deadband(this.spr - this.yf, this.db, this.dbm);
    var pOld = this.pTerm(e);
    this.setGains(Kc, Ti, Td);
    this.I += pOld - this.pTerm(e);
  };
  PIDConL.prototype.track = function (sp, y, uMan) {        // ruční režim, bezrázový přechod do automatu
    this.yf = this.Tpv > 0 ? this.apv * this.yf + (1 - this.apv) * y : y;
    this.spr = sp;
    var e = deadband(this.spr - this.yf, this.db, this.dbm);
    this.xdPrev = this.dfb ? -this.yf : e;
    this.D = 0;
    this.I = uMan - this.pTerm(e);
    this.u = this.uPrev = uMan;
    this.k += 1;
    return uMan;
  };
  PIDConL.prototype.step = function (sp, y) {
    this.yf = this.Tpv > 0 ? this.apv * this.yf + (1 - this.apv) * y : y;
    if (this.k % this.m === 0) {
      var Tc = this.Tc;
      if (this.sprate > 0) {
        var ds = Math.min(Math.max(sp - this.spr, -this.sprate * Tc), this.sprate * Tc);
        this.spr = this.spr + ds;
      } else this.spr = sp;
      var e = deadband(this.spr - this.yf, this.db, this.dbm);
      var P = this.pTerm(e);
      var xd = this.dfb ? -this.yf : e;
      if (this.Td > 0) this.D = this.Tf / (this.Tf + Tc) * this.D + this.Kc * this.Td / (this.Tf + Tc) * (xd - this.xdPrev);
      this.xdPrev = xd;
      var inc = this.useI ? this.Kc * Tc / this.Ti * e : 0;
      var uUn = P + this.I + inc + this.D;
      var u = Math.min(Math.max(uUn, this.lo), this.hi);
      if (this.rate > 0) u = Math.min(Math.max(u, this.uPrev - this.rate * Tc), this.uPrev + this.rate * Tc);
      if (u === uUn || (uUn > u && inc < 0) || (uUn < u && inc > 0)) this.I += inc;
      this.u = this.uPrev = u;
    }
    this.k += 1;
    return this.u;
  };

  function valveCharFn(gains) {
    if (!gains || !gains.length) return null;
    var g = gains.concat(new Array(10).fill(1)).slice(0, 10);
    if (g.every(function (x) { return Math.abs(x - 1) < 1e-12; })) return null;
    var cum = [0];
    for (var i = 0; i < 10; i++) cum.push(cum[i] + g[i] * 10);
    return function (x) {
      x = Math.min(Math.max(x, 0), 100);
      var j = Math.min(Math.floor(x / 10), 9);
      return cum[j] + g[j] * (x - 10 * j);
    };
  }
  function Valve(S, J, gains, v0) {
    this.S = S || 0;
    this.J = (J === undefined || J === null) ? this.S : Math.min(Math.max(J, 0), this.S);
    this.fch = valveCharFn(gains);
    this.v = v0;
    this.f0 = this.fch ? this.fch(v0) : v0;
  }
  Valve.prototype.step = function (u) {
    if (this.S > 0) {
      var dv = u - this.v;
      if (Math.abs(dv) > this.S) this.v = u - Math.sign(dv) * (this.S - this.J);
    } else this.v = u;
    return this.fch ? this.fch(this.v) - this.f0 : this.v - this.f0;
  };

  function gauss(rng) {                                    // Box–Muller
    var u = 0, v = 0;
    while (u === 0) u = rng();
    while (v === 0) v = rng();
    return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
  }
  function mulberry32(a) {
    return function () {
      a |= 0; a = a + 0x6D2B79F5 | 0;
      var t = Math.imul(a ^ a >>> 15, 1 | a);
      t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
      return ((t ^ t >>> 14) >>> 0) / 4294967296;
    };
  }

  /* Poruchy měřené (DV): přenos poruchy K·e^(−θs)/(Ts+1)[·1/(T2s+1)], u integračního procesu integrace (jako
     core.simulate_dist) a dopředná vazba g·lead-lag·zpoždění (jako core.pidconl_sim_full). Vstup v jednotkách DV. */
  function DelayLine(th, h) {
    var d = th > 0 ? th / h : 0;
    this.i = Math.floor(d + 1e-9); this.f = d - this.i; if (this.f < 1e-9) this.f = 0;
    this.buf = new Array(this.i + 2).fill(0); this.k = 0;
  }
  DelayLine.prototype.push = function (x) {
    var n = this.buf.length;
    this.buf[this.k % n] = x;
    var a = this.buf[(this.k - this.i + n * 4) % n], b = this.buf[(this.k - this.i - 1 + n * 4) % n];
    var y = this.k - this.i < 0 ? 0 : (this.f ? (1 - this.f) * a + this.f * (this.k - this.i - 1 < 0 ? 0 : b) : a);
    this.k++;
    return y;
  };
  function Lag(T, h) { this.a = T > 0 ? Math.exp(-h / T) : 0; this.on = T > 0; this.y = 0; }
  Lag.prototype.push = function (x) { if (!this.on) return x; this.y = this.a * this.y + (1 - this.a) * x; return this.y; };

  function DvChannel(spec, h, integProc) {
    var pd = spec.pd;                                    // [K, T, θ, druh, T2]
    this.K = pd[0]; this.dl = new DelayLine(pd[2], h); this.l1 = new Lag(pd[1], h);
    this.l2 = new Lag(pd.length > 4 ? pd[4] : 0, h);
    var kind = pd.length > 3 ? Math.round(pd[3]) : 0;
    this.integ = kind === 0 ? !!integProc : kind === 2;
    this.z = 0; this.h = h;
    var ff = spec.ff || {};                              // {g, lead, lag, delay}
    this.g = ff.g || 0;
    if (this.g !== 0) {
      this.fdl = new DelayLine(ff.delay || 0, h);
      this.fl = ff.lag > 0 ? new Lag(ff.lag, h) : null; this.fr = ff.lag > 0 ? ff.lead / ff.lag : 0;
    }
  }
  DvChannel.prototype.setFF = function (on) { this.ffOn = !!on; };
  DvChannel.prototype.step = function (d) {              // vrací [příspěvek k PV, příspěvek k FF]
    var y = this.K * this.l2.push(this.l1.push(this.dl.push(d)));
    if (this.integ) { this.z += y * this.h; y = this.z; }
    var f = 0;
    if (this.g !== 0 && this.ffOn) {
      var x = this.fdl.push(d);
      if (this.fl) x = this.fr * x + (1 - this.fr) * this.fl.push(x);
      f = this.g * x;
    }
    return [y, f];
  };

  /* Smyčka: stejné rozhraní jako Python LiveLoop.advance (sp, uMan, dIn v % rozsahů).
     opts (volitelné): profile = profil regulátoru (CtrlEngine; bez něj dnešní PIDConL), engine = CtrlEngine,
     dvs = [{pd, ff:{g, lead, lag, delay}}] měřené poruchy, ff = zapnout dopřednou vazbu. */
  function LiveLoop(code, p, ctrl, h, pv0, mv0, plant, opts) {
    plant = plant || {}; opts = opts || {};
    this.h = h; this.pv0 = pv0; this.mv0 = mv0;
    this.proc = new ProcStep(code, p, h);
    var CE = opts.engine || root.CtrlEngine;
    this.profile = opts.profile && CE ? CE.profile(opts.profile) : null;
    this.pid = this.profile ? new CE.Controller(this.profile, ctrl, h) : new PIDConL(ctrl, h);
    this.valve = new Valve(plant.Stic || 0, plant.SticJ, plant.ValveChar, mv0);
    this.sigma = plant.Noise || 0;
    this.rng = mulberry32(plant.Seed || 1);
    this.pid.init(pv0, pv0, mv0);
    var integ = code === "I0D" || code === "I1D";
    this.dv = (opts.dvs || []).map(function (s) { var c = new DvChannel(s, h, integ); c.setFF(!!opts.ff); return c; });
    this.t = 0;
  }
  LiveLoop.prototype.setTuning = function (c) {
    var ti = c.TI === null || c.TI === undefined ? Infinity : c.TI;
    if (this.pid.setIdeal) this.pid.setIdeal(c.Gain, ti, c.TD); else this.pid.setTuning(c.Gain, ti, c.TD);
  };

  /* Změny za běhu (živá simulace v prohlížeči; Python je nepotřebuje). */
  LiveLoop.prototype.setPlant = function (p) {
    // nový proces se stejným výstupem (bez skoku PV): stav členů se přepočte, fronta zpoždění převzorkuje
    var old = this.proc, out = old.output(), np_ = new ProcStep(old.code, p, this.h), c = old.code;
    var n0 = old.q.length, n1 = np_.q.length;
    for (var k = 0; k < n1; k++) {
      var src = Math.min(n0 - 1, Math.floor(k * n0 / n1));
      np_.q[k] = old.q[(old.qi + src) % n0];
    }
    np_.qi = 0;
    if (c === "P1D") np_.x1 = p[0] !== 0 ? out / p[0] : 0;
    else if (c === "P2D") { np_.x2 = p[0] !== 0 ? out / p[0] : 0; np_.x1 = np_.x2 + (old.x1 - old.x2); }
    else if (c === "I0D" || c === "I1D") { np_.z = old.z; np_.x1 = old.x1; }
    this.proc = np_;
  };
  LiveLoop.prototype.setStiction = function (S, J) {
    this.valve.S = S || 0;
    this.valve.J = (J === undefined || J === null) ? this.valve.S : Math.min(Math.max(J, 0), this.valve.S);
  };
  LiveLoop.prototype.setNoise = function (sigma) { this.sigma = sigma || 0; };
  LiveLoop.prototype.setPVFilter = function (T) {
    setPvFilter(this.pid, T || 0, this.h);
  };
  function setPvFilter(pid, T, h) {
    if (pid._apv !== undefined) {                       // CtrlEngine.Controller
      if (pid.profile && !pid.profile.pvLag) return;
      pid._lag = T > 0; pid._apv = T > 0 ? Math.exp(-h / T) : 0; pid._bpv = 1 - pid._apv;
    } else { pid.Tpv = T; pid.apv = T > 0 ? Math.exp(-h / T) : 0; }
  }

  /* Jeden krok h; vrací [t, SP, PV, MV, V]. dOut = porucha přičtená k PV (volitelně), dvs = měřené poruchy
     (pole hodnot v jednotkách DV; působí přes jejich přenosy a dopřednou vazbu). */
  LiveLoop.prototype.tick = function (sp, auto, uMan, dIn, dOut, dvs) {
    var yd = dOut || 0, ff = 0;
    for (var j = 0; j < this.dv.length; j++) {
      var r = this.dv[j].step(dvs && dvs[j] ? dvs[j] : 0);
      yd += r[0]; ff += r[1];
    }
    var y = this.pv0 + this.proc.output() + yd;
    var ym = this.sigma > 0 ? y + this.sigma * gauss(this.rng) : y;
    var u = auto ? this.pid.step(sp, ym, ff) : this.pid.track(sp, ym, uMan === undefined || uMan === null ? this.mv0 : uMan, ff);
    var uin = this.valve.step(u);
    this.proc.step(uin + (dIn || 0));
    this.t += this.h;
    return [this.t, auto ? this.pid.spr : sp, y, u, this.valve.v];
  };

  /* Kaskáda (APC): vnější regulátor (profil) → SP vnitřního PI → ventil → vnitřní proces; vnější proces dostává PV
     vnitřní smyčky jako vstup (jako core.cascade_sim). opts.inner = {code, p, ctrl}; dIn působí na vstup vnitřního
     procesu, měřené poruchy na vnější PV. Ladění za běhu se ignoruje (vnější regulátor je naladěný podle kaskády). */
  function CascadeLoop(code, p, octrl, h, pv0, mv0, plant, opts) {
    LiveLoop.call(this, code, p, octrl, h, pv0, mv0, plant, opts);
    var inn = opts.inner;
    this.inner = new ProcStep(inn.code, inn.p, h);
    this.ipid = new PIDConL(inn.ctrl, h);
    this.ipid.init(mv0, mv0, mv0);
    this.pid.init(pv0, pv0, mv0);
  }
  CascadeLoop.prototype = Object.create(LiveLoop.prototype);
  CascadeLoop.prototype.constructor = CascadeLoop;
  CascadeLoop.prototype.setTuning = function () {};
  CascadeLoop.prototype.tick = function (sp, auto, uMan, dIn, dOut, dvs) {
    var yd = dOut || 0, ff = 0;
    for (var j = 0; j < this.dv.length; j++) {
      var r = this.dv[j].step(dvs && dvs[j] ? dvs[j] : 0);
      yd += r[0]; ff += r[1];
    }
    var y = this.pv0 + this.proc.output() + yd;
    var ym = this.sigma > 0 ? y + this.sigma * gauss(this.rng) : y;
    var yi = this.mv0 + this.inner.output(), spi, u;
    if (auto) { spi = this.pid.step(sp, ym, ff); u = this.ipid.step(spi, yi); }
    else {
      spi = this.pid.track(sp, ym, yi, ff);
      u = this.ipid.track(spi, yi, uMan === undefined || uMan === null ? this.mv0 : uMan);
    }
    var uin = this.valve.step(u);
    this.inner.step(uin + (dIn || 0));
    this.proc.step(yi - this.mv0);
    this.t += this.h;
    return [this.t, auto ? this.pid.spr : sp, y, u, this.valve.v];
  };

  var api = { ProcStep: ProcStep, PIDConL: PIDConL, Valve: Valve, LiveLoop: LiveLoop, CascadeLoop: CascadeLoop };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.PIDLive = api;
})(typeof window !== "undefined" ? window : globalThis);
