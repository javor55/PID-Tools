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
    if (db <= 0 || Math.abs(e) >= db) return (db > 0 && mode === "spojité") ? e - Math.sign(e) * db : e;
    return 0;
  }
  function num(v, d) { return (v === undefined || v === null) ? d : v; }

  function PIDConL(ctrl, h) {
    this.h = h;
    this.m = Math.max(1, Math.round(ctrl.SampleTime / h));
    this.Tc = this.m * h;
    this.lo = num(ctrl.MV_Lo, -Infinity); this.hi = num(ctrl.MV_Hi, Infinity);
    this.db = num(ctrl.DeadBand, 0); this.dbm = num(ctrl.DbMode, "spojité");
    this.pfb = !!ctrl.PropFbk; this.dfb = !!ctrl.DiffFbk;
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
  PIDConL.prototype.pTerm = function (e) { return this.pfb ? this.Kc * (-this.yf) : this.Kc * e; };
  PIDConL.prototype.init = function (sp, y, u0) {
    this.yf = y; this.spr = sp;
    var e = deadband(this.spr - this.yf, this.db, this.dbm);
    this.I = u0 - this.pTerm(e); this.D = 0;
    this.xdPrev = this.dfb ? -this.yf : this.spr - this.yf;
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
    this.xdPrev = this.dfb ? -this.yf : this.spr - this.yf;
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
      var xd = this.dfb ? -this.yf : this.spr - this.yf;
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

  /* Smyčka: stejné rozhraní jako Python LiveLoop.advance (sp, uMan, dIn v % rozsahů). */
  function LiveLoop(code, p, ctrl, h, pv0, mv0, plant) {
    plant = plant || {};
    this.h = h; this.pv0 = pv0; this.mv0 = mv0;
    this.proc = new ProcStep(code, p, h);
    this.pid = new PIDConL(ctrl, h);
    this.valve = new Valve(plant.Stic || 0, plant.SticJ, plant.ValveChar, mv0);
    this.sigma = plant.Noise || 0;
    this.rng = mulberry32(plant.Seed || 1);
    this.pid.init(pv0, pv0, mv0);
    this.t = 0;
  }
  LiveLoop.prototype.setTuning = function (c) { this.pid.setTuning(c.Gain, c.TI, c.TD); };
  /* Jeden krok h; vrací [t, SP, PV, MV, V]. */
  LiveLoop.prototype.tick = function (sp, auto, uMan, dIn) {
    var y = this.pv0 + this.proc.output();
    var ym = this.sigma > 0 ? y + this.sigma * gauss(this.rng) : y;
    var u = auto ? this.pid.step(sp, ym) : this.pid.track(sp, ym, uMan === undefined || uMan === null ? this.mv0 : uMan);
    var uin = this.valve.step(u);
    this.proc.step(uin + (dIn || 0));
    this.t += this.h;
    return [this.t, auto ? this.pid.spr : sp, y, u, this.valve.v];
  };

  var api = { ProcStep: ProcStep, PIDConL: PIDConL, Valve: Valve, LiveLoop: LiveLoop };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.PIDLive = api;
})(this);
