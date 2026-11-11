"""
Zdroje dat projektu a mapování smyček (plán v2, E3): běhová vrstva nad doménovým modelem `app.domain`.

`SourceRT` drží popis zdroje (domain.Source) a jeho tabulku. `SourcesMixin` (část `loops.Project`) spravuje zdroje,
skládá z nich data smyček a převádí mapování rolí (`LoopSpec`) na sloupce pracovního prostoru:

  - smyčka z jediného zdroje dostane jeho tabulku přímo (výsledky jako dnes, žádné převzorkování navíc);
  - smyčka z více zdrojů dostane tabulku složenou na společné časové mřížce (`domain.timegrid`: posun a časové
    pásmo zdrojů, překryv, perioda, mezery); všechny další výpočty (`Workspace`) běží nad touto tabulkou beze změny.
Workspace zůstává fasádou výpočtů jedné smyčky a drží vybrané sloupce (`c_pv` …) pod jmény signálů; odkud signál
pochází (`SourceRef`), říká `Workspace.name_refs`.
"""
import numpy as np
import pandas as pd

from ...i18n import T
from .. import dataset as ds
from ..domain import registry as sreg
from ..domain import timegrid as tgm
from ..domain.model import DataRef, LoopSpec, Roles, Source, SourceRef, TimeGrid
from . import Workspace

DASH = "—"
EMBEDDED_TIME = "t_s"            # sloupec času uložených dat zdroje (sekundy od začátku záznamu)


def _name(c):
    return None if c in (None, "", DASH) else str(c)


def _snap(ws):
    """Stav pracovního prostoru pro vrácení zpět při chybě (nastavení se kopíruje, protože se mění na místě)."""
    d = dict(ws.__dict__)
    d["settings"] = dict(ws.settings)
    return d


def _restore(ws, d):
    ws.__dict__.clear()
    ws.__dict__.update(d)


class SourceRT:
    """Zdroj za běhu: popis + tabulka (pandas) a z ní přečtené signály podle voleb zdroje."""

    def __init__(self, src: Source, df=None, origin=None, auto=False):
        self.src, self.df, self.origin, self.auto = src, df, origin, auto
        self._sig = None

    @property
    def id(self):
        return self.src.id

    def invalidate(self):
        self._sig = None

    def read_options(self):
        """Volby čtení tabulky pro `ds.signals` / `Workspace.load_frame` (bez prázdných)."""
        o = {k: v for k, v in self.src.options.items() if v is not None and k != "layout"}
        if self.src.sampling_s and not o.get("row_dt"):
            o["row_dt"] = self.src.sampling_s            # bez času v souboru: co řádek, to vzorek s touto periodou
        return o

    def layout(self):
        return self.src.options.get("layout") or ds.default_layout(self.df)

    def signals(self):
        """Signály zdroje (čas od začátku záznamu [s], sloupce, počátek s hodinami); čte se jednou."""
        if self.df is None:
            raise ValueError(T("err_source_nodata", id=self.src.id))
        if self._sig is None:
            self._sig = self._read(self.src.options)
        return self._sig

    def _read(self, options):
        o = dict(self.read_options(), **{k: v for k, v in options.items() if k != "layout" and v is not None})
        layout = options.get("layout") or ds.default_layout(self.df)
        unit = o.get("unit") or "s"
        sig = ds.signals(self.df, layout, o.get("time_fmt") or "auto", unit, o.get("c_time"), o.get("c_tag"),
                         o.get("c_val"), float(o.get("row_dt") or 1.0))
        if sig.origin is None and self.origin is not None:
            sig.origin = self.origin + pd.Timedelta(seconds=float(np.nanmin(sig.t_all)))
        return sig

    def epoch(self):
        """Čas nuly záznamu jako UTC [s od 1970], z hodin v souboru a časového pásma zdroje; None = čas bez hodin."""
        o = self.signals().origin
        if o is None:
            return None
        ts = pd.Timestamp(o)
        if ts.tzinfo is None:
            ts = ts.tz_localize(self.src.timezone or "UTC", ambiguous=True, nonexistent="shift_forward")
        return float(ts.tz_convert("UTC").timestamp())

    def period(self):
        """Perioda vzorkování [s]: vlastní zdroje, jinak medián kroku prvního signálu s daty."""
        if self.src.sampling_s:
            return float(self.src.sampling_s)
        sig = self.signals()
        for c in sig.sigs[:20]:
            t, _v = tgm.clean(sig.t_all, sig.get(c))
            p = tgm.median_step(t)
            if p:
                return p
        return None

    def to_dict(self, embed=False, columns=()):
        """Popis zdroje pro soubor projektu; s `embed` i data vybraných sloupců na vlastní časové ose zdroje."""
        d = self.src.to_dict()
        d["data_ref"].update(rows=int(len(self.df)) if self.df is not None else 0, embedded=False)
        if embed and self.df is not None and columns:
            sig = self.signals()
            cols = {EMBEDDED_TIME: np.asarray(sig.t_all, float)}
            for c in columns:
                if c in sig.sigs:
                    cols[str(c)] = np.asarray(sig.get(c), float)
            d["data"] = dict(cols=cols, origin=None if sig.origin is None else str(pd.Timestamp(sig.origin)))
            d["options"] = dict(layout="wide")
            d["data_ref"]["embedded"] = True
        return d


def embedded_frame(data):
    """Uložená data zdroje (`{"cols": {t_s, …}, "origin"}`) → (tabulka, počátek s hodinami nebo None)."""
    cols = {k: np.asarray(v, float) for k, v in data["cols"].items()}
    origin = pd.Timestamp(data["origin"]) if data.get("origin") else None
    return pd.DataFrame(cols), origin


def unique_names(refs, rts):
    """Jména signálů složené tabulky: sloupec beze změny, při shodě sloupců různých zdrojů „sloupec (zdroj)“."""
    count = {}
    for r in refs:
        count[r.column] = count.get(r.column, 0) + 1
    label = {rt.id: rt.src.name for rt in rts}
    names, used = [], set()
    for r in refs:
        n = r.column if count[r.column] == 1 else f"{r.column} ({label[r.source_id]})"
        if n in used:
            n = f"{n} [{r.source_id}]"
        used.add(n)
        names.append(n)
    return names


class SourcesMixin:
    """Zdroje a mapování smyček `loops.Project` (stav: `self.sources`, `self.time_grid`, `self.loops`)."""

    # ---- zdroje
    def rt(self, sid) -> SourceRT:
        for r in self.sources:
            if r.id == sid:
                return r
        raise KeyError(T("err_source_unknown", id=sid))

    def _next_id(self):
        n = 1
        ids = {r.id for r in self.sources}
        while f"s{n}" in ids:
            n += 1
        return f"s{n}"

    def _by_df(self, df):
        return next((r for r in self.sources if r.df is df), None)

    def _layout_options(self, ws):
        """Čtení tabulky v pracovním prostoru → volby zdroje."""
        src = ws.sig.time_src[0] if ws.sig is not None and ws.sig.time_src else None
        return {k: v for k, v in dict(
            layout=ws.layout, time_fmt=ws.time_fmt, unit=ws.unit, c_time=ws.c_time or (src if ws.layout == "wide" else None),
            c_tag=ws.c_tag, c_val=ws.c_val, row_dt=ws.row_dt if ws.row_dt != 1.0 else None).items() if v is not None}

    def sync(self):
        """
        Sladí zdroje s pracovními prostory: tabulka načtená přímo do `Workspace` (desktop, testy) se zaregistruje jako
        zdroj, změněné čtení tabulky (rozložení, čas) se přenese do voleb zdroje a nepoužité zdroje, které vznikly
        automaticky, zaniknou.
        """
        for ws in self.loops:
            if not ws.has_data or (ws.merged_df is not None and ws.df is ws.merged_df):
                continue
            rt = self._by_df(ws.df)
            if rt is None:
                name = ws.fname or "data"
                kind = "opc" if name.lower().startswith(("opc", "opc ua")) else sreg.kind_for(name.split("|")[0])
                src = Source(self._next_id(), name.split("|")[0] or name, kind, {}, data=DataRef(
                    "opc" if kind == "opc" else "demo" if name == "demo" else "file", name.split("|")[0]))
                rt = SourceRT(src, ws.df, ws.origin_hint, auto=True)
                self.sources.append(rt)
            rt.src.options = self._layout_options(ws)
            rt._sig = ws.sig
            ws.src_ids = [rt.id]
            ws.name_refs = {str(c): SourceRef(rt.id, str(c)) for c in ws.sig.sigs}
        used = {i for ws in self.loops for i in ws.src_ids}
        self.sources[:] = [r for r in self.sources if r.id in used or not r.auto]

    def add_source(self, name, raw=None, frame=None, kind=None, options=None, timezone=None, offset_s=0.0,
                   sampling_s=None):
        """
        Nový zdroj ze souboru (`raw`) nebo hotové tabulky (`frame`, OPC UA). Čtení se zkusí hned (chybná data = výjimka
        a nic se nezmění). První zdroj prázdného projektu se rovnou stane daty smyčky.
        """
        self.sync()
        kind = kind or sreg.kind_for(name)
        if timezone:
            _check_tz(timezone)
        df = sreg.load(kind, name, raw, frame)
        src = Source(self._next_id(), name, kind, {k: v for k, v in (options or {}).items() if v is not None},
                     timezone or None, float(offset_s or 0.0), sampling_s or None,
                     DataRef("opc" if kind == "opc" else "file", name))
        rt = SourceRT(src, df)
        rt.signals()                                                           # čitelné rozvržení, jinak výjimka
        first = not any(ws.has_data for ws in self.loops)
        self.sources.append(rt)
        if first:
            try:
                self._feed(self.loops[0], [rt.id], fname=name)
            except Exception:
                self.sources.remove(rt)
                raise
        return rt

    def update_source(self, sid, **patch):
        """Změna zdroje (název, volby čtení, časové pásmo, posun, vlastní vzorkování); smyčky z něj se přeskládají."""
        self.sync()
        rt = self.rt(sid)
        if patch.get("timezone"):
            _check_tz(patch["timezone"])
        opts = {k: patch[k] for k in ("layout", "time_fmt", "unit", "c_time", "c_tag", "c_val", "row_dt") if k in patch}
        if opts.get("layout") not in (None, rt.layout()):          # jiné rozvržení = sloupce času / tagu / hodnoty znovu
            opts = {**dict.fromkeys(("c_time", "c_tag", "c_val")), **opts}
        old = (rt.src.name, dict(rt.src.options), rt.src.timezone, rt.src.offset_s, rt.src.sampling_s, rt._sig)
        affected = [ws for ws in self.loops if sid in ws.src_ids]
        saved = [(ws, _snap(ws)) for ws in affected]
        try:
            if opts:
                rt.src.options = {**rt.src.options, **opts}
                rt.invalidate()
            for k in ("name", "timezone", "offset_s", "sampling_s"):
                if k in patch:
                    setattr(rt.src, k, patch[k] if k == "name" else patch[k] or (0.0 if k == "offset_s" else None))
            if opts or "sampling_s" in patch:
                rt.invalidate()
                rt.signals()
            for ws in affected:
                self._feed(ws, list(ws.src_ids))
        except Exception:
            rt.src.name, rt.src.options, rt.src.timezone, rt.src.offset_s, rt.src.sampling_s, rt._sig = old
            for ws, d in saved:
                _restore(ws, d)
            raise
        return rt

    def remove_source(self, sid):
        """Zdroj, který nepoužívá žádná role smyčky, se odebere (smyčky ze složených dat se přeskládají)."""
        self.sync()
        rt = self.rt(sid)
        for i in range(len(self.loops)):
            if any(r.source_id == sid for r in self.loop_spec(i).roles.refs()):
                raise ValueError(T("err_source_used", id=sid, loop=i + 1))
        for ws in self.loops:
            if sid in ws.src_ids:
                self._feed(ws, [x for x in ws.src_ids if x != sid])
        self.sources.remove(rt)

    def set_time_grid(self, tg: TimeGrid):
        """Nastavení společné mřížky; smyčky ze složených dat se přeskládají, ruční perioda platí pro všechny smyčky."""
        self.sync()
        tg.check()
        old = self.time_grid
        saved = [(ws, _snap(ws)) for ws in self.loops]
        self.time_grid = tg
        try:
            for ws in self.loops:
                if ws.has_data and ws.src_ids:
                    self._feed(ws, list(ws.src_ids))
        except Exception:
            self.time_grid = old
            for ws, d in saved:
                _restore(ws, d)
            raise

    # ---- data smyčky ze zdrojů
    def _frame_of(self, rts, zoh_refs=()):
        """Tabulka složená ze zdrojů na společné mřížce: (DataFrame, {jméno: SourceRef}, počátek s hodinami)."""
        epochs = {rt.id: rt.epoch() for rt in rts}
        known = [e for e in epochs.values() if e is not None]
        base = min(known) if known else 0.0
        series, refs, own = [], [], []
        for rt in rts:
            sig = rt.signals()
            shift = (epochs[rt.id] if epochs[rt.id] is not None else base) + float(rt.src.offset_s or 0.0)
            for c in sig.sigs:
                t, v = tgm.clean(sig.t_all + shift, sig.get(c))
                if len(t) >= 2:                                    # sloupec bez dat (text, prázdný) se nepřenáší
                    series.append((t, v))
                    refs.append(SourceRef(rt.id, str(c)))
                    own.append(rt.src.sampling_s)
        zoh = {i for i, r in enumerate(refs) if r in set(zoh_refs)}
        g = tgm.common_grid(series, self.time_grid, zoh, own)
        names = unique_names(refs, rts)
        cols = {EMBEDDED_TIME: g.t - g.t0}
        cols.update({n: g.values[i] for i, n in enumerate(names)})
        origin = pd.Timestamp(g.t0, unit="s") if known else None
        return pd.DataFrame(cols), dict(zip(names, refs)), origin

    def _feed(self, ws, ids, fname=None, zoh_refs=()):
        """
        Data smyčky ze zdrojů `ids`: jediný zdroj přímo (jako dnes), víc zdrojů složených na společné mřížce.
        Vybrané sloupce, úsek a nastavení smyčky zůstanou, pokud jsou sloupce v nových datech.
        """
        rts = [self.rt(i) for i in ids]
        if not rts or any(r.df is None for r in rts):
            raise ValueError(T("err_source_nodata", id=ids[0] if ids else "-"))
        ws.ts_user = self.time_grid.period
        if len(rts) == 1:
            rt = rts[0]
            ws.origin_hint, ws.merged_df = rt.origin, None
            ws.swap_data(rt.df, fname or ws.fname or rt.src.name, rt.layout(), **rt.read_options())
            refs = {str(c): SourceRef(rt.id, str(c)) for c in ws.sig.sigs}
            rt._sig = ws.sig
        else:
            if not zoh_refs:
                zoh_refs = self._zoh_refs()
            df, refs, origin = self._frame_of(rts, zoh_refs)
            ws.origin_hint = origin
            ws.swap_data(df, fname or ws.fname or "+".join(r.src.name for r in rts), "wide", c_time=EMBEDDED_TIME,
                         unit="s", time_fmt="num")
            ws.merged_df = df
        ws.src_ids, ws.name_refs = [r.id for r in rts], refs
        return ws

    def _zoh_refs(self):
        """Sloupce, které se při skládání drží (MV a režim všech smyček): schodovitý průběh se neinterpoluje."""
        out = set()
        for i in range(len(self.loops)):
            r = self.loop_spec(i).roles
            out.update(x for x in (r.mv, r.mode) if x is not None)
        return out

    # ---- mapování smyčky
    def _name_to_ref(self, ws, c):
        n = _name(c)
        return None if n is None else ws.name_refs.get(n)

    def loop_spec(self, i) -> LoopSpec:
        """Popis smyčky z jejího pracovního prostoru (role → zdroj › sloupec, rozsahy, tag, popis, kaskáda)."""
        ws = self.loops[i]
        ref = lambda c: self._name_to_ref(ws, c)                                    # noqa: E731
        roles = Roles(pv=ref(ws.c_pv), sp=ref(ws.c_sp), mv=ref(ws.c_mv), pos=ref(ws.c_pos),
                      mode=SourceRef.from_dict(ws.extra["mode"]) if ws.extra.get("mode") else None,
                      dv=[r for r in (ref(c) for c in ws.c_d) if r is not None])
        return LoopSpec(tag=str(ws.get("loop_tag", "")), description=str(ws.extra.get("description", "")), roles=roles,
                        norm_pv=(ws.pv_lo, ws.pv_hi) if ws.has_data else None,
                        norm_mv=(ws.mv_lo, ws.mv_hi) if ws.has_data else None, cascade_to=ws.extra.get("cascade_to"))

    def _check_refs(self, spec):
        for r in spec.roles.refs():
            try:
                rt = self.rt(r.source_id)
            except KeyError as ex:
                raise ValueError(ex.args[0]) from None
            if r.column not in rt.signals().sigs:
                raise ValueError(T("err_column_unknown", id=r.source_id, column=r.column))

    def set_loop_spec(self, i, spec: LoopSpec):
        """
        Mapování rolí smyčky na sloupce zdrojů. Zdroje rolí určí data smyčky (jeden = přímo, víc = složená mřížka);
        PV a MV jsou povinné.
        """
        self.sync()
        ws = self.loops[i]
        r = spec.roles
        if r.pv is None or r.mv is None:
            raise ValueError(T("err_loop_roles"))
        if spec.cascade_to is not None and not (0 <= spec.cascade_to < len(self.loops) and spec.cascade_to != i):
            raise ValueError(T("err_loop_index", i=spec.cascade_to))
        self._check_refs(spec)
        ids = list(dict.fromkeys(x.source_id for x in r.refs()))
        saved = _snap(ws)
        try:
            if sorted(ids) != sorted(ws.src_ids) or any(x not in ws.name_refs.values() for x in r.refs()):
                self._feed(ws, [x.id for x in self.sources if x.id in ids], zoh_refs=self._zoh_refs() | {x for x in (r.mv, r.mode) if x})
            inv = {v: k for k, v in ws.name_refs.items()}
            for x in r.refs():
                if x not in inv:                                           # sloupec bez dat se do složených dat nedostal
                    raise ValueError(T("err_column_unknown", id=x.source_id, column=x.column))
            nm = lambda x: DASH if x is None else inv[x]                                # noqa: E731
            ws.set_columns(inv[r.pv], inv[r.mv], nm(r.sp), [inv[x] for x in r.dv], nm(r.pos))
            if spec.tag:
                ws.set(loop_tag=spec.tag)
            for k, rng in (("pv", spec.norm_pv), ("mv", spec.norm_mv)):
                if rng:
                    ws.set(**{f"{k}_lo": float(rng[0]), f"{k}_hi": float(rng[1]), f"{k}_rng_user": True})
            ws.extra = dict(description=spec.description, mode=r.mode.to_dict() if r.mode else None,
                            cascade_to=spec.cascade_to)
        except Exception:
            _restore(ws, saved)
            raise

    def add_loop_from_spec(self, spec: LoopSpec):
        """Nová smyčka podle mapování (data ze zdrojů rolí)."""
        ws = Workspace()
        ws.set(lang=self.state.get("lang"))
        first = spec.roles.pv or spec.roles.mv
        if first is None:
            raise ValueError(T("err_loop_roles"))
        self._feed(ws, [first.source_id])
        self.loops.append(ws)
        try:
            self.set_loop_spec(len(self.loops) - 1, spec)
        except Exception:
            self.loops.pop()
            raise
        self.active = len(self.loops) - 1
        return ws

    # ---- časová osa zdrojů (Trendy, přehled zdrojů)
    def axis(self):
        """
        Společná časová osa zdrojů: ({id: posun [s]}, {id: (od, do) [s]}, počátek jako ISO text nebo None). Čas 0 je
        začátek nejdřívějšího zdroje; posun a časové pásmo zdrojů jsou započtené, zdroj bez hodin je zarovnaný na
        nejdřívější zdroj s hodinami.
        """
        rts = [r for r in self.sources if r.df is not None]
        epochs = {r.id: r.epoch() for r in rts}
        known = [e for e in epochs.values() if e is not None]
        base = min(known) if known else 0.0
        raw = {}
        for r in rts:
            t = r.signals().t_all
            t = t[np.isfinite(t)]
            if len(t):
                shift = (epochs[r.id] if epochs[r.id] is not None else base) + float(r.src.offset_s or 0.0)
                raw[r.id] = (shift, float(t.min()) + shift, float(t.max()) + shift)
        zero = min((a for _s, a, _b in raw.values()), default=0.0)
        shifts = {k: v[0] - zero for k, v in raw.items()}
        spans = {k: (v[1] - zero, v[2] - zero) for k, v in raw.items()}
        return shifts, spans, (pd.Timestamp(zero, unit="s").isoformat() if known and raw else None)

    # ---- návrh smyček
    def column_refs(self, ids=None):
        """Všechny sloupce zdrojů jako odkazy (pořadí zdrojů a jejich sloupců)."""
        out = []
        for rt in self.sources:
            if (ids is None or rt.id in ids) and rt.df is not None:
                out += [SourceRef(rt.id, str(c)) for c in rt.signals().sigs]
        return out

    def source_tuples(self):
        """[(id, název, [sloupce])] pro import mapování z CSV."""
        return [(rt.id, rt.src.name, [str(c) for c in rt.signals().sigs]) for rt in self.sources if rt.df is not None]


def _check_tz(tz):
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
    try:
        ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        raise ValueError(T("err_timezone", tz=tz)) from None
