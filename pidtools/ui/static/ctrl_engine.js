/*
 * Obecný regulátor v prohlížeči (E1) – stejný interpret profilu jako pidtools/core/controller.py.
 * Čte stejný profil (`.pidctrl`, JSON, např. pidtools/controllers/presets/pcs7_pidconl.json); shoda s Pythonem
 * se hlídá testem tests/test_ctrl_engine_js.py (Node, odchylka < 1e-9). Vše v % normovacích rozsahů.
 *
 *   var prof = CtrlEngine.profile(jsonObject);
 *   var c = new CtrlEngine.Controller(prof, {Gain: 1, TI: 30, TD: 0, SampleTime: 1}, h);
 *   c.init(sp, y, u0, ff); c.step(sp, y, ff); c.track(sp, y, uMan, ff); c.setTuning(Gain, TI, TD);
 */
(function (root) {
  "use strict";

  /* ---- registry (stejné položky jako v Pythonu; rozšíření = přidat položku) */
  function Registry(name) { this.name = name; this.items = {}; }
  Registry.prototype.register = function (key, obj, planned) { this.items[key] = { obj: obj, planned: !!planned }; return obj; };
  Registry.prototype.get = function (key) {
    var it = this.items[key];
    if (!it) throw new Error(this.name + ": neznámá položka '" + key + "' (známé: " + Object.keys(this.items).sort().join(", ") + ")");
    if (it.planned) throw new Error(this.name + ": '" + key + "' je v návrhu a bude doplněno (fáze R3 / R4)");
    return it.obj;
  };
  var FORMS = new Registry("forma"), DEADBANDS = new Registry("mrtvé pásmo"), D_SOURCES = new Registry("zdroj D"),
    D_FILTERS = new Registry("filtr D"), ANTIWINDUPS = new Registry("anti-windup"), ALGORITHMS = new Registry("algoritmus"),
    NORMALISATIONS = new Registry("normování"), PV_FILTERS = new Registry("filtr PV"),
    NL_GAINS = new Registry("nelineární zesílení"), OUTPUT_STAGES = new Registry("výstupní stupeň");

  function form(fn, roles) { fn.roles = roles; return fn; }
  FORMS.register("ideal", form(function (a, b, c) { return [a, b, c]; }, ["Kc", "Ti", "Td"]));
  FORMS.register("parallel", form(function (kp, ki, kd) {
    if (kp === 0) throw new Error("paralelní forma: Kp = 0 nelze převést na ideální tvar");
    return [kp, (ki && ki > 0) ? kp / ki : null, kd / kp];
  }, ["Kp", "Ki", "Kd"]));
  FORMS.register("series", form(function (kc, ti, td) {
    if (ti === null || ti === undefined || !(ti > 0) || !isFinite(ti)) return [kc, ti, td];
    return [kc * (1.0 + td / ti), ti + td, ti * td / (ti + td)];
  }, ["Kc", "Ti", "Td"]));

  DEADBANDS.register("continuous", function (db) {
    return function (e) { return Math.abs(e) >= db ? e - (e > 0 ? 1.0 : -1.0) * db : 0.0; };
  });
  DEADBANDS.register("step", function (db) {
    return function (e) { return Math.abs(e) >= db ? e : 0.0; };
  });
  DEADBANDS.register("gap", function (db, P) {
    var k = (P && P.gap_gain !== undefined) ? P.gap_gain : 0.0;
    return function (e) {
      if (Math.abs(e) < db) return k * e;
      return e - (e > 0 ? 1.0 : -1.0) * db * (1.0 - k);
    };
  });

  D_SOURCES.register("error", function () { return 0; });
  D_SOURCES.register("pv", function () { return 1; });
  D_SOURCES.register("error_or_pv", function (p) { return p.d_on_pv ? 1 : 0; });

  D_FILTERS.register("td_over_n", function (p, Td) {
    var N = Math.max(p.N === undefined ? 5.0 : p.N, 1e-6);
    return Td > 0 ? Td / N : 0.0;
  });
  D_FILTERS.register("none", function () { return 0.0; });
  D_FILTERS.register("fixed", function (p, Td) { return Td > 0 ? (p.Tf || 0.0) : 0.0; });

  ANTIWINDUPS.register("clamp_conditional", function (iOld, inc, uUn, u) {
    if (u === uUn || (uUn > u && inc < 0) || (uUn < u && inc > 0)) return iOld + inc;
    return iOld;
  });
  ANTIWINDUPS.register("back_calculation", function (iOld, inc, uUn, u, kAw) { return iOld + inc + (u - uUn) * kAw; });
  ANTIWINDUPS.register("none", function (iOld, inc) { return iOld + inc; });
  function awExternal(ctl, P) {      // externí reset (BKCAL), viz Python
    var tt = P.Tt;
    return function (iOld, inc, uUn, u) {
      var ub = ctl.extReset !== null ? ctl.extReset : u;
      var k = tt ? ctl.Tc / tt : (ctl.useI ? ctl.Tc / ctl.Ti : 0.0);
      return iOld + inc + (ub - uUn) * k;
    };
  }
  awExternal.factory = true;
  ANTIWINDUPS.register("external_reset", awExternal);

  ALGORITHMS.register("position", true);
  ALGORITHMS.register("velocity", function (iOld, inc, uUn, u) { return iOld + inc + (u - uUn); });
  NORMALISATIONS.register("percent", true);
  NORMALISATIONS.register("engineering", null, true);
  PV_FILTERS.register("lag1", true);
  PV_FILTERS.register("none", false);

  /* ---- nelineární zesílení (tvarovač odchylky) */
  function interp(xs, ys, x) {
    if (x <= xs[0]) return ys[0];
    for (var i = 1; i < xs.length; i++)
      if (x < xs[i]) return ys[i - 1] + (ys[i] - ys[i - 1]) * (x - xs[i - 1]) / (xs[i] - xs[i - 1]);
    return ys[ys.length - 1];
  }
  NL_GAINS.register("none", function () { return null; });
  NL_GAINS.register("squared", function (ctl, P) {
    var e0 = P.nl_e0;
    if (!e0 || e0 <= 0) return null;
    return function (e) { return Math.abs(e) < e0 ? e * Math.abs(e) / e0 : e; };
  });
  NL_GAINS.register("table", function (ctl, P, spec) {
    var xs = spec.x.map(Number), ys = spec.y.map(Number), src = spec.input || "pv";
    if (xs.length < 2 || xs.length !== ys.length || xs.some(function (v, i) { return i > 0 && v <= xs[i - 1]; }))
      throw new Error("tabulka zesílení: x musí být rostoucí a mít stejný počet bodů jako y (min. 2)");
    if (src === "pv") return function (e) { return e * interp(xs, ys, ctl.yf); };
    if (src === "sp") return function (e) { return e * interp(xs, ys, ctl.spr); };
    if (src === "mv") return function (e) { return e * interp(xs, ys, ctl.uPrev); };
    if (src === "error") return function (e) { return e * interp(xs, ys, e); };
    throw new Error("tabulka zesílení: neznámý vstup '" + src + "' (pv, sp, mv, error)");
  });

  /* ---- výstupní stupně: továrna (regulátor, parametry) → funkce u → ekvivalentní poloha, `.outputs` = signály */
  OUTPUT_STAGES.register("none", null);
  OUTPUT_STAGES.register("split_range", function (ctl, P) {
    var s = P.split_point, g = P.split_gap, kh = P.k_heat, kc = P.k_cool;
    var f = function (u) {
      var a = s - g / 2, b = s + g / 2;
      var heat = u > b ? Math.min(100.0, (u - b) / Math.max(100.0 - b, 1e-9) * 100.0 * kh) : 0.0;
      var cool = u < a ? Math.min(100.0, (a - u) / Math.max(a, 1e-9) * 100.0 * kc) : 0.0;
      f.outputs.MV = heat; f.outputs.MV2 = cool;
      return s + heat / 100.0 * (100.0 - s) - cool / 100.0 * s;
    };
    f.outputs = { MV: 0.0, MV2: 0.0 };
    return f;
  });
  OUTPUT_STAGES.register("three_step", function (ctl, P) {
    var h = ctl.h, tm = Math.max(P.motor_time, 1e-9), thr = P.tri_threshold, tmin = P.min_pulse, tpause = P.min_pause;
    var pos = null, left = 0.0, dir = 0, pause = 0.0;
    var f = function (u) {
      if (pos === null) pos = u;
      if (left <= 0 && pause > 0) pause -= h;
      else if (left <= 0) {
        var d = u - pos, need = Math.abs(d) / 100.0 * tm;
        if (Math.abs(d) >= thr && need > 0 && need >= tmin) { left = need; dir = d > 0 ? 1 : -1; }
      }
      var on = 0.0;
      if (left > 0) {
        var dt = Math.min(h, left);
        pos = Math.min(Math.max(pos + dir * dt / tm * 100.0, 0.0), 100.0);
        left -= dt;
        on = dt / h;
        if (left <= 1e-12) { left = 0.0; pause = tpause; }
      }
      f.outputs.PULSE_UP = dir > 0 ? on : 0.0; f.outputs.PULSE_DN = dir < 0 ? on : 0.0;
      return pos;
    };
    f.outputs = { PULSE_UP: 0.0, PULSE_DN: 0.0 };
    return f;
  });
  OUTPUT_STAGES.register("pwm", function (ctl, P) {
    var h = ctl.h, tp = Math.max(P.pwm_period, h), tmin = P.min_pulse, t = null, duty = 0.0;
    var f = function (u) {
      if (t === null || t >= tp - 1e-9) {
        t = 0.0;
        duty = Math.min(Math.max(u, 0.0), 100.0) / 100.0;
        var on = duty * tp;
        if (tmin > 0) {
          if (on < tmin / 2) duty = 0.0;
          else if (on < tmin) duty = tmin / tp;
          else if (tp - on < tmin / 2) duty = 1.0;
          else if (tp - on < tmin) duty = 1.0 - tmin / tp;
        }
      }
      f.outputs.PWM = t < duty * tp - 1e-12 ? 1.0 : 0.0;
      t += h;
      return duty * 100.0;
    };
    f.outputs = { PWM: 0.0 };
    return f;
  });

  /* ---- profil */
  function num(v) {
    if (typeof v === "string" && /^[+-]?inf$/.test(v)) return v[0] === "-" ? -Infinity : Infinity;
    return v === undefined ? null : v;
  }
  function has(o, k) { return Object.prototype.hasOwnProperty.call(o, k); }

  function Profile(data) {
    if (!data || data.format !== "pidctrl") throw new Error("není profil regulátoru (chybí format = 'pidctrl')");
    if (!(data.version >= 1)) throw new Error("profil regulátoru nemá platnou verzi");
    if (data.version > 1) throw new Error("profil verze " + data.version + " je novější než podporovaná 1");
    var st = data.structure, d = st.d || {};
    this.data = data; this.id = data.id;
    this.form = st.form || "ideal";
    this.formFn = FORMS.get(this.form);
    this.tuningRoles = this.formFn.roles;
    this.dSource = D_SOURCES.get(d.source || "error");
    this.dFilter = D_FILTERS.get(d.filter || "td_over_n");
    this.antiwindup = ANTIWINDUPS.get(st.antiwindup || "clamp_conditional");
    var alg = ALGORITHMS.get(st.algorithm || "position");
    if (alg !== true) this.antiwindup = alg;
    NORMALISATIONS.get((st.normalisation || {}).kind || "percent");
    this.pvLag = !!PV_FILTERS.get((st.pv || {}).filter || "lag1");
    var db = (st.error || {}).deadband;
    this.dbModes = (db && db.modes) || {};
    this.dbOther = (db && db.other) || "step";
    var self = this;
    Object.keys(this.dbModes).map(function (k) { return self.dbModes[k]; }).concat([this.dbOther])
      .forEach(function (m) { DEADBANDS.get(m); });
    var out = st.output || {};
    this.stage = OUTPUT_STAGES.get(out.stage || "none");
    var nl = (st.error || {}).nonlinear || {};
    this.nl = [NL_GAINS.get(nl.kind || "none"), nl];
    this.useRate = !!out.rate_limit; this.useZone = !!out.control_zone;
    this.useSpRate = !!(st.sp || {}).rate_limit;
    this.params = data.params.map(function (p) {
      return { key: p.key, role: p.role, def: num(p.default), required: !!p.required, nullable: !!p.nullable,
        range: p.range || null, alias: p.alias || null };
    });
  }
  var ROLE_DEFAULTS = { b: 1.0, d_on_pv: false, deadband: 0.0, deadband_mode: "", mv_lo: -Infinity, mv_hi: Infinity,
    pv_filter: 0.0, mv_rate: 0.0, sp_rate: 0.0, con_zone: 0.0, N: 5.0, Tf: 0.0, gap_gain: 0.0, nl_e0: 0.0, split_point: 50.0, split_gap: 0.0, k_heat: 1.0, k_cool: 1.0,
    motor_time: 60.0, tri_threshold: 1.0, min_pulse: 0.0, min_pause: 0.0, pwm_period: 10.0 };
  Profile.prototype.resolve = function (ctrl) {
    var out = {};
    this.params.forEach(function (p) {
      var v = ctrl[p.key];
      if ((v === undefined || v === null) && p.alias && ctrl[p.alias.key] !== undefined && ctrl[p.alias.key] !== null)
        v = ctrl[p.alias.key] ? p.alias["true"] : p.alias["false"];
      if (v === undefined || v === null) {
        if (p.nullable && has(ctrl, p.key)) { out[p.role] = null; return; }
        if (p.required) throw new Error("chybí parametr " + p.key);
        v = p.def;
      }
      out[p.role] = p.range ? Math.min(Math.max(v, p.range[0]), p.range[1]) : v;
    });
    Object.keys(ROLE_DEFAULTS).forEach(function (r) { if (!has(out, r)) out[r] = ROLE_DEFAULTS[r]; });
    return out;
  };

  /* ---- regulátor */
  function Controller(profile, ctrl, h) {
    var prof = profile instanceof Profile ? profile : new Profile(profile);
    this.profile = prof;
    var P = prof.resolve(ctrl);
    this._params = P;
    this.h = h;
    this.m = Math.max(1, Math.round(P.Ts / h));
    var Tc = this.Tc = this.m * h;
    this.lo = P.mv_lo; this.hi = P.mv_hi;
    this._db = null;
    if (P.deadband > 0) this._db = DEADBANDS.get(has(prof.dbModes, P.deadband_mode) ? prof.dbModes[P.deadband_mode] : prof.dbOther)(P.deadband, P);
    this.yf = this.spr = this.u = this.uPrev = 0.0;
    this.extReset = null;                      // externí reset (BKCAL) pro anti-windup external_reset
    var shaper = prof.nl[0](this, P, prof.nl[1]);
    if (shaper !== null) {
      var base = this._db;
      this._db = base === null ? shaper : function (e) { return shaper(base(e)); };
    }
    this.b = P.b; this._omb = 1.0 - this.b;
    this._dsrc = prof.dSource(P);
    var Tpv = prof.pvLag ? (P.pv_filter || 0.0) : 0.0;
    this._lag = Tpv > 0;
    this._apv = Tpv > 0 ? Math.exp(-h / Tpv) : 0.0;
    this._bpv = 1 - this._apv;
    this._rate = prof.useRate ? (P.mv_rate || 0.0) : 0.0;
    this._sprate = prof.useSpRate ? (P.sp_rate || 0.0) : 0.0;
    this._rlim = this._rate * Tc; this._slim = this._sprate * Tc;
    var cz = prof.useZone ? (P.con_zone || 0.0) : 0.0;
    this._cz = (cz > 0 && isFinite(this.lo) && isFinite(this.hi)) ? cz : 0.0;
    this._aw = prof.antiwindup.factory ? prof.antiwindup(this, P) : prof.antiwindup;
    this._kAw = P.Tt ? Tc / P.Tt : 0.0;
    this.k = 0; this.dem = 0.0;
    this._setGains.apply(this, prof.tuningRoles.map(function (r) { return P[r]; }));
    this.outputs = {};
    if (prof.stage !== null) {                 // výstupní stupeň obalí step / track
      var self = this, stage = prof.stage(this, P), bStep = Controller.prototype.step, bTrack = Controller.prototype.track;
      this.stage = stage; this.outputs = stage.outputs;
      this.step = function (sp, y, ff) { return stage(bStep.call(self, sp, y, ff)); };
      this.track = function (sp, y, uMan, ff) { return stage(bTrack.call(self, sp, y, uMan, ff)); };
    }
  }
  Controller.prototype.setLimits = function (lo, hi) {   // dynamické meze výstupu
    this.lo = lo; this.hi = hi;
    var cz = this.profile.useZone ? (this._params.con_zone || 0.0) : 0.0;
    this._cz = (cz > 0 && isFinite(lo) && isFinite(hi)) ? cz : 0.0;
  };
  Controller.prototype._setGains = function (a, b, c) {
    var g = this.profile.formFn(a, b, c), Kc = g[0], Ti = g[1], Td = g[2], Tc = this.Tc;
    this.Kc = Kc; this.Ti = Ti; this.Td = Td;
    this.useI = Ti !== null && Ti !== undefined && isFinite(Ti) && Ti > 0;
    var Tf = this.Tf = this.profile.dFilter(this._params, Td);
    this._ki = this.useI ? Kc * Tc / Ti : 0.0;
    this._useD = Td > 0;
    this._ad = this._useD ? Tf / (Tf + Tc) : 0.0;
    this._kd = this._useD ? Kc * Td / (Tf + Tc) : 0.0;
    this._ksign = Kc >= 0 ? 1.0 : -1.0;
  };
  Controller.prototype.setTuning = function (a, b, c) {      // bez rázu výstupu (přepočet I složky)
    var e = this._err(), pOld = this._pTerm(e);
    this._setGains(a, b, c);
    this.I += pOld - this._pTerm(e);
  };
  Controller.prototype._err = function () {
    var e = this.spr - this.yf;
    return this._db !== null ? this._db(e) : e;
  };
  Controller.prototype._pTerm = function (e) { return this.Kc * (this.b * e - this._omb * this.yf); };
  Controller.prototype._xd = function (e) { return this._dsrc ? -this.yf : e; };
  Controller.prototype.init = function (sp, y, u0, ff) {
    ff = ff || 0.0;
    this.uPrev = u0;
    this.yf = y; this.spr = sp;
    var e = this._err();
    this.I = u0 - this._pTerm(e) - ff; this.D = 0.0;
    this.xdPrev = this._xd(e);
    this.u = this.uPrev = u0;
  };
  Controller.prototype.track = function (sp, y, uMan, ff) {
    ff = ff || 0.0;
    this.yf = this._lag ? this._apv * this.yf + this._bpv * y : y;
    this.spr = sp;
    var e = this._err();
    this.xdPrev = this._xd(e);
    this.D = 0.0;
    this.I = uMan - this._pTerm(e) - ff;
    this.u = this.uPrev = uMan;
    this.k += 1;
    return uMan;
  };
  Controller.prototype.step = function (sp, y, ff) {
    ff = ff || 0.0;
    var yf = this.yf = this._lag ? this._apv * this.yf + this._bpv * y : y;
    var k = this.k;
    this.k = k + 1;
    if (k % this.m) return this.u;
    var spr = this.spr;
    if (this._sprate > 0) {
      var lim = this._slim;
      spr = spr + Math.min(Math.max(sp - spr, -lim), lim);
    } else spr = sp;
    this.spr = spr;
    var e = spr - yf;
    if (this._db !== null) e = this._db(e);
    var Kc = this.Kc;
    var P = Kc * (this.b * e - this._omb * yf);
    var xd = this._dsrc ? -yf : e, D;
    if (this._useD) this.D = D = this._ad * this.D + this._kd * (xd - this.xdPrev);
    else D = this.D;
    this.xdPrev = xd;
    var uPrev = this.uPrev, u, rl;
    var cz = this._cz;
    if (cz > 0 && Math.abs(e) > cz) {                // regulační zóna
      u = e * this._ksign > 0 ? this.hi : this.lo;
      if (this._rate > 0) { rl = this._rlim; u = Math.min(Math.max(u, uPrev - rl), uPrev + rl); }
      this.I = u - P - D - ff;
      this.u = this.uPrev = u;
      return u;
    }
    var inc = this.useI ? this._ki * e : 0.0;
    var uUn = P + this.I + inc + D + ff;
    var dem = Math.abs(uUn - uPrev);
    if (dem > this.dem) this.dem = dem;
    u = Math.min(Math.max(uUn, this.lo), this.hi);
    if (this._rate > 0) { rl = this._rlim; u = Math.min(Math.max(u, uPrev - rl), uPrev + rl); }
    this.I = this._aw(this.I, inc, uUn, u, this._kAw);
    this.u = this.uPrev = u;
    return u;
  };

  var api = { Profile: Profile, Controller: Controller, profile: function (d) { return new Profile(d); },
    registries: { forms: FORMS, deadbands: DEADBANDS, dSources: D_SOURCES, dFilters: D_FILTERS, antiwindups: ANTIWINDUPS,
      algorithms: ALGORITHMS, normalisations: NORMALISATIONS, pvFilters: PV_FILTERS, nlGains: NL_GAINS,
      outputStages: OUTPUT_STAGES } };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.CtrlEngine = api;
})(typeof window !== "undefined" ? window : globalThis);
