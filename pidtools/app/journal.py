"""
Deník ladění (plán v2, E10): operace nad snímky `app.domain.journal.Snapshot` v projektu (`loops.Project.journal`).

Snímek = neměnný záznam stavu jedné smyčky: otisky dat (SHA-256 z hodnot zdrojů) a mapování, úseky, model, profil regulátoru
(s verzí), nastavení bloku, sady, metoda, scénář, výsledky (Ms, IAE …), APC a úplný záznam smyčky pro obnovu
(„Otevřít tento stav“). Vytvoření, seznam, změna stavu (s historií), poznámky a přílohy (malé soubory v base64),
porovnání dvou snímků (strukturovaný rozdíl), obnova (nejdřív se aktuální stav uloží jako „autosave před obnovením“),
převod starších souhrnů živé simulace (`live_runs`) do deníku a report ze snímku.
"""
import base64
import binascii
import datetime as _dt
import hashlib

import numpy as np

from .. import __version__
from ..core import MODELS
from ..i18n import T
from . import project as prj
from .domain.journal import KINDS, STATUSES, Snapshot  # noqa: F401

MAX_ATTACHMENT = 1_500_000          # největší příloha [bajty původního souboru]
MAX_ATTACHMENTS_TOTAL = 8_000_000   # všechny přílohy projektu dohromady [bajty]

# nastavení smyčky podle skupin (ostatní klíče jsou jen v úplném záznamu pro obnovu)
GROUPS = dict(
    block=("samp", "diffgain", "pfb", "propfac", "dfb", "db", "db_mode", "mvl_lo", "mvl_hi", "pvfilt", "mvrate", "sprate",
           "pv_lo", "pv_hi", "mv_lo", "mv_hi", "u_pv", "u_mv"),
    sets=("set1_gain", "set1_ti", "set1_td", "set2_gain", "set2_ti", "set2_td"),
    method=("ctype", "mcode", "mtype", "proc_type", "opt_ms", "opt_noise", "opt_robust", "opt_crit", "opt_target",
            "opt_ovs", "avg_dpv", "avg_dmv"),
    scenario=("scen_kind", "scen_d_in", "scen_d_pv", "scen2", "sim_len_u", "sim_J", "sim_noise", "val_rng"),
)


def now():
    return _dt.datetime.now().isoformat(timespec="seconds")


def _num(x):
    """Číslo pro JSON (NaN / inf → None)."""
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return x if np.isfinite(x) else None


def _clean(v):
    """Hodnota do JSON bez NaN a bez objektů numpy."""
    v = prj.jsonable(v)
    if isinstance(v, float):
        return v if np.isfinite(v) else None
    if isinstance(v, list):
        return [_clean(x) for x in v]
    if isinstance(v, dict):
        return {k: _clean(x) for k, x in v.items()}
    return v


def _fingerprints(p, i):
    """Zdroje dat používané smyčkou: soubor, rozsah času, vzorkování, počet vzorků a SHA-256 hodnot použitých sloupců."""
    out = []
    try:
        spec = p.loop_spec(i)
        used = {}
        for ref in spec.roles.refs():
            used.setdefault(ref.source_id, []).append(ref.column)
        for sid, cols in used.items():
            rt = p.rt(sid)
            sig = rt.signals()
            t = np.asarray(sig.t_all, float)
            h = hashlib.sha256(np.ascontiguousarray(t).tobytes())
            for c in dict.fromkeys(cols):
                h.update(np.ascontiguousarray(np.asarray(sig.get(c), float)).tobytes())
            out.append(dict(id=sid, name=rt.src.name, kind=rt.src.kind, rows=int(len(t)), t0=_num(t[0]) if len(t) else None,
                            t1=_num(t[-1]) if len(t) else None,
                            ts=_num(np.median(np.diff(t))) if len(t) > 1 else None, columns=list(dict.fromkeys(cols)),
                            origin=None if sig.origin is None else str(sig.origin), sha256=h.hexdigest(),
                            stored=bool(rt.src.data.embedded)))
    except Exception:       # noqa: BLE001 – otisk je doplněk; snímek bez dat nebo se vzdáleným zdrojem se uloží i bez něj
        pass
    return out


def _results(ls):
    """Ukazatele sady 1 (původně) a 2 (nově): Ms, GM, PM, IAE skoku SP a poruchy, překmit, ustálení, pohyb MV."""
    if ls.model is None:
        return {}
    from . import report as rp
    try:
        r = ls.report_record()
        resp, rob = rp._response(r), rp._robust(r)
    except Exception:       # noqa: BLE001 – nestabilní nebo nepočitatelná sada: bez výsledků
        return {}
    out = {}
    for n in ("1", "2"):
        out[n] = {k: _num(v) for k, v in dict(Ms=rob[n].get("Ms"), GM=rob[n].get("GM"), PM=rob[n].get("PM"),
                                                iae_sp=resp[n]["iae_sp"], iae_d=resp[n]["iae_d"], over=resp[n]["over"],
                                                settle=resp[n]["settle"], travel=resp[n]["travel"]).items()}
    return out


def capture(p, i):
    """Obsah snímku smyčky `i` z aktuálního stavu projektu (slovník; `record` slouží k obnově)."""
    p.sync()
    ls = p.loops[i]
    rec = ls.to_project(False)
    for k in ("version", "fname"):
        rec.pop(k, None)
    rec["state"] = {k: v for k, v in rec["state"].items() if k != "live_runs"}
    rec["spec"] = p.loop_spec(i).to_dict()
    st = rec["state"]
    content = {g: {k: st[k] for k in keys if k in st} for g, keys in GROUPS.items()}
    content["method"].update({k: v for k, v in st.items() if k.startswith("method|")})
    prof = ls.controller
    if prof is None:
        from . import ctl_tuning
        prof = ctl_tuning.profile_data(None)
    content["controller"] = dict(id=prof.get("id"), name=prof.get("name"), version=prof.get("version"),
                                 verification=prof.get("verification"), custom=ls.controller is not None)
    content["data"] = dict(sources=_fingerprints(p, i), mapping=rec["map"], spec=rec["spec"], ranges=rec.get("ranges"),
                           windows=rec.get("windows"), norm=dict(pv=[ls.pv_lo, ls.pv_hi], mv=[ls.mv_lo, ls.mv_hi]))
    content["model"] = None
    if ls.model is not None:
        code, par, pdl = ls.model
        fr = (ls.fit or {}).get("res", {}).get(code, {})
        content["model"] = dict(code=code, names=list(MODELS[code]["params"]), params=list(par), pdl=pdl,
                                fit=_num(fr.get("fit")), level=fr.get("level"), Th=_num(fr.get("Th")))
        content["rec"] = {k: v for k, v in ls.report_record().items() if k != "id"}
    content["results"] = _results(ls)
    content["apc"] = dict(ff=rec.get("ff") or [])
    content["record"] = rec
    return _clean(content)


def _author(author):
    return str(author or "local")


def next_id(p):
    n = 1 + max([int(s.id[1:]) for s in p.journal if s.id[1:].isdigit()] + [0])
    return f"j{n}"


def _loop_index(p, loop):
    """Smyčka podle indexu, názvu (tagu), jinak aktivní."""
    if loop is None:
        return p.active
    if isinstance(loop, int):
        if not 0 <= loop < len(p.loops):
            raise KeyError(T("err_journal_loop"))
        return loop
    names = p.names()
    if loop in names:
        return names.index(loop)
    raise KeyError(T("err_journal_loop"))


def create(p, loop=None, label="", note="", author="local", kind="manual", status="draft", extra=None, when=None):
    """Nový snímek smyčky (index / název; výchozí aktivní). Vrací `Snapshot` (už uložený v `p.journal`)."""
    i = _loop_index(p, loop)
    name = p.names()[i]
    when = when or now()
    v = 1 + max([s.v for s in p.journal if s.loop == name] + [0])
    s = Snapshot(id=next_id(p), loop=name, v=v, created=when, author=_author(author), content=dict(capture(p, i), **(extra or {})), kind=kind,
                 label=label, app_version=__version__)
    s.history.append(dict(status="draft", when=when, author=s.author, note=""))
    if status != "draft":
        s.set_status(status, when, s.author)
    if note:
        s.notes.append(dict(when=when, author=s.author, text=note))
    p.journal.append(s)
    return s


def get(p, sid):
    for s in p.journal:
        if s.id == sid:
            return s
    raise KeyError(T("err_journal_unknown", id=sid))


def listing(p, loop=None, status=None):
    """Snímky (nové první), případně jen smyčky / stavu."""
    out = [s for s in p.journal if (loop is None or s.loop == loop) and (status is None or s.status == status)]
    return sorted(out, key=lambda s: (s.created, int(s.id[1:]) if s.id[1:].isdigit() else 0), reverse=True)


def set_status(p, sid, status, author="local", note=""):
    s = get(p, sid)
    s.set_status(status, now(), _author(author), note)
    return s


def add_note(p, sid, text, author="local"):
    s = get(p, sid)
    text = str(text or "").strip()
    if not text:
        raise ValueError(T("err_journal_empty"))
    s.notes.append(dict(when=now(), author=_author(author), text=text))
    return s


def add_attachment(p, sid, name, data_b64, mime="application/octet-stream", desc="", author="local"):
    """Příloha (malý soubor, base64) – největší velikost `MAX_ATTACHMENT`, všech příloh projektu `MAX_ATTACHMENTS_TOTAL`."""
    s = get(p, sid)
    try:
        raw = base64.b64decode(data_b64, validate=True)
    except (binascii.Error, ValueError) as ex:
        raise ValueError(T("err_journal_attach_b64")) from ex
    if not str(name or "").strip():
        raise ValueError(T("err_journal_empty"))
    if len(raw) > MAX_ATTACHMENT:
        raise ValueError(T("err_journal_attach_big", mb=f"{MAX_ATTACHMENT / 1e6:.1f}"))
    total = sum(a.get("size", 0) for x in p.journal for a in x.attachments)
    if total + len(raw) > MAX_ATTACHMENTS_TOTAL:
        raise ValueError(T("err_journal_attach_total", mb=f"{MAX_ATTACHMENTS_TOTAL / 1e6:.0f}"))
    n = 1 + max([int(a["id"][1:]) for a in s.attachments if str(a.get("id", ""))[1:].isdigit()] + [0])
    a = dict(id=f"a{n}", name=str(name)[:200], mime=str(mime)[:100], size=len(raw), when=now(), author=_author(author),
             desc=str(desc or "")[:500], data=base64.b64encode(raw).decode("ascii"))
    s.attachments.append(a)
    return s, a


def attachment(p, sid, aid):
    for a in get(p, sid).attachments:
        if a["id"] == aid:
            return a
    raise KeyError(T("err_journal_unknown", id=aid))


# ---------------------------------------------------------------- porovnání
def flatten(content):
    """Obsah snímku → {sekce: {klíč: hodnota}} pro rozdíl (jen to, co se v deníku porovnává a zobrazuje)."""
    sec = {}
    d = content.get("data") or {}
    sec["data"] = {f"src:{x['name']}": f"{x['rows']} · {x['sha256'][:12]}" for x in d.get("sources", [])}
    sec["mapping"] = {k: v for k, v in (d.get("mapping") or {}).items()}
    sec["mapping"].update({f"norm_{k}": v for k, v in (d.get("norm") or {}).items()})
    sec["mapping"].update({f"range_{k}": v for k, v in (d.get("ranges") or {}).items()})
    m = content.get("model")
    sec["model"] = {} if not m else dict({"type": m["code"], "fit": m.get("fit")}, **dict(zip(m["names"], m["params"])))
    c = content.get("controller") or {}
    sec["controller"] = {k: c.get(k) for k in ("id", "version", "custom")}
    for g in GROUPS:
        sec[g] = dict(content.get(g) or {})
    for n, vals in (content.get("results") or {}).items():
        sec[f"results_{n}"] = dict(vals)
    sec["apc"] = {f"ff{j + 1}": f for j, f in enumerate((content.get("apc") or {}).get("ff") or [])}
    return sec


def _same(a, b):
    if isinstance(a, float) and isinstance(b, float):
        return abs(a - b) <= 1e-9 * max(1.0, abs(a), abs(b))
    return a == b


def compare(p, a, b):
    """Strukturovaný rozdíl snímků `a` → `b`: změněné položky [{section, key, a, b}] (jen sekce, kde se něco liší)."""
    sa, sb = get(p, a), get(p, b)
    fa, fb = flatten(sa.content), flatten(sb.content)
    rows = []
    for sec in dict.fromkeys(list(fa) + list(fb)):
        ka, kb = fa.get(sec, {}), fb.get(sec, {})
        for k in dict.fromkeys(list(ka) + list(kb)):
            va, vb = ka.get(k), kb.get(k)
            if not _same(va, vb):
                rows.append(dict(section=sec, key=str(k), a=va, b=vb))
    return dict(a=sa.to_dict(light=True), b=sb.to_dict(light=True), rows=rows)


# ---------------------------------------------------------------- obnova
def restore(p, sid, author="local"):
    """
    „Otevřít tento stav“: obnoví nastavení, mapování, modely a profil smyčky ze snímku. Nedestruktivní – aktuální stav smyčky
    se nejdřív uloží jako snímek „autosave před obnovením“. Data se neobnovují (zůstávají načtená); liší-li se od dat snímku,
    vrátí se varování.
    """
    s = get(p, sid)
    names = p.names()
    i = names.index(s.loop) if s.loop in names else p.active
    before = create(p, i, label=T("jr_autosave_restore", name=s.name), author=author, kind="restore")
    fp_now = {x["name"]: x["sha256"] for x in _fingerprints(p, i)}
    warn = [x["name"] for x in s.content["data"].get("sources", []) if fp_now.get(x["name"]) not in (None, x["sha256"])]
    p.loops[i].apply_project(dict(s.content["record"]))
    p.active = i
    return dict(snapshot=s, autosave=before, data_changed=warn)


# ---------------------------------------------------------------- starší souhrny živé simulace
def migrate_live_runs(p):
    """`live_runs` v nastavení smyček (E9) → záznamy deníku (druh `live_migrated`); ze stavu smyčky se odstraní."""
    n = 0
    for i, ls in enumerate(p.loops):
        runs = ls.settings.get("live_runs")
        if not isinstance(runs, list) or not runs:
            ls.settings.pop("live_runs", None)
            continue
        ls.settings.pop("live_runs", None)
        for r in runs:
            if isinstance(r, dict):
                add_live(p, r, i, kind="live_migrated")
                n += 1
    return n


def add_live(p, run, loop=None, author="local", kind="live"):
    """Souhrn běhu živé simulace (`{when, struct, kpi}`) → snímek deníku s výsledky z běhu."""
    live = {str(k): {kk: _num(vv) for kk, vv in (v or {}).items()} for k, v in (run.get("kpi") or {}).items()
            if isinstance(v, dict)}
    struct = str(run.get("struct") or "pid")
    when = str(run["when"])[:19] if run.get("when") else None
    return create(p, loop, label=T("jr_live_label", struct=struct), author=author, kind=kind, when=when,
                  extra=dict(live=dict(when=when, struct=struct, kpi=live)))


# ---------------------------------------------------------------- report
CHANGE_SECTIONS = ("sets", "block", "model", "method", "controller", "mapping")


def _change_text(prev, cur):
    """Krátký popis změny proti předchozí verzi smyčky („set2_gain 1 → 2, …“)."""
    if prev is None:
        return ""
    fa, fb = flatten(prev.content), flatten(cur.content)

    def f(x):
        return f"{x:.4g}" if isinstance(x, float) else str(x)
    out = []
    for sec in CHANGE_SECTIONS:
        for k in dict.fromkeys(list(fa.get(sec, {})) + list(fb.get(sec, {}))):
            a, b = fa.get(sec, {}).get(k), fb.get(sec, {}).get(k)
            if not _same(a, b):
                out.append(f"{k} {f(a)} → {f(b)}")
    return ", ".join(out[:5]) + (" …" if len(out) > 5 else "")


def history_rows(p, loop=None, upto=None):
    """Historie změn pro report: snímky (od nejstaršího; jedné smyčky nebo všech, do snímku `upto`) se změnou proti předchozí verzi."""
    snaps = sorted([s for s in p.journal if loop is None or s.loop == loop], key=lambda s: (s.loop, s.v))
    rows, last = [], {}
    for s in snaps:
        if upto is not None and s.loop == upto.loop and s.v > upto.v:
            continue
        rows.append(dict(loop=s.loop, v=s.v, created=s.created, author=s.author, status=s.status, label=s.label,
                         change=_change_text(last.get(s.loop), s)))
        last[s.loop] = s
    return rows


def ab_kpis(ls, a, b):
    """Porovnání A / B z diagnostiky: KPI dvou úseků [s] aktivní smyčky (pro sekci „Ověření v provozu“)."""
    return dict(a=_clean(ls.diag_kpis(*a)), b=_clean(ls.diag_kpis(*b)))


def _report_rec(content):
    """Záznam smyčky pro `report.build_report` z obsahu snímku (po JSON jsou n-tice seznamy)."""
    r = dict(content["rec"])
    code, par, pdl = r["model"]
    r.update(id=1, active=True, model=(code, list(par), [list(d) for d in pdl]), rng=tuple(r["rng"]),
             pv_rng=tuple(r["pv_rng"]), mv_rng=tuple(r["mv_rng"]), c_d=list(r.get("c_d") or []))
    return r


def report_snapshot(p, sid, meta, sections, chart_mode="inline", ab=None):
    """Report ze snímku: stejné sekce jako běžný protokol, ale z uložených hodnot (bez grafu modelu z dat)."""
    from . import report as rp
    s = get(p, sid)
    c = s.content
    att = [{k: v for k, v in a.items() if k != "data"} for a in s.attachments]
    ctx = dict(content={1: c}, ab=ab, live=bool(c.get("live")), attachments=bool(att),
               history=history_rows(p, s.loop, s), snapshot=dict(attachments=att))
    meta = dict(meta, status=s.status, version=f"v{s.v} · {s.created[:16].replace('T', ' ')}")
    recs = [_report_rec(c)] if c.get("rec") else []
    return rp.build_report(recs, meta, sections, chart_mode, None, {}, ctx)


def report_ctx(p, recs, sections, ab=None):
    """Podklady nových sekcí běžného protokolu: obsah smyček (aktuální stav), A / B, historie změn."""
    from . import report as rp
    ctx = dict(ab=ab, history=history_rows(p), attachments=any(s.attachments for s in p.journal))
    if any(x.scope == "loop" and x.render and x.id in sections for x in rp.REGISTRY):
        ctx["content"] = {r["id"]: capture(p, r["id"] - 1) for r in recs}
    return ctx


def summary_rows(p, extra=None):
    """Řádky souhrnného reportu: všechny smyčky projektu (model, sada 2, Ms, poslední verze deníku) + nálezy z auditu / triáže."""
    from . import report as rp
    extra = {str(x.get("name")): str(x.get("finding") or "") for x in (extra or [])}
    rows = []
    for i, name in enumerate(p.names()):
        ls = p.loops[i]
        last = max([s for s in p.journal if s.loop == name], key=lambda s: s.v, default=None)
        row = dict(name=name, status=last.status if last else None, version=f"v{last.v}" if last else "",
                   finding=extra.get(name, ""))
        if ls.model is not None:
            r = ls.report_record()
            try:
                ms = _num(rp._robust(r)["2"].get("Ms"))
            except Exception:       # noqa: BLE001
                ms = None
            c2 = r["ctrl"]
            row.update(model=ls.model[0], fit=r.get("fit"), gain=_num(c2.get("Gain")), ti=_num(rp._ti(c2)),
                       td=_num(c2.get("TD")), ms=ms)
        rows.append(row)
    return rows
