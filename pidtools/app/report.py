"""
Report = protokol z ladění regulačních smyček (samostatný HTML soubor, tisk do PDF z prohlížeče).

Obsah se dopočítá z modelů a parametrů všech smyček projektu – nezávisle na tom, co je zrovna rozbalené v aplikaci:
hlavička protokolu, shrnutí (co nastavit v PCS 7, původně / nově), a pro každou smyčku parametry bloku PIDConL,
robustnost (Ms, GM, PM), očekávané chování (skok SP a porucha – sada 1 vs. sada 2), model a jeho shoda s daty,
doporučené struktury APC; nakonec místo pro podpisy.

Vstupem jsou záznamy smyček (dict: id, name, active, model, ctrl = sada 2, ctrl1 = sada 1, fit, rng, c_pv, c_mv,
c_sp, c_d, pv_rng, mv_rng, u_pv, u_mv); data pro graf modelu a hodnoty APC dodá frontend.
"""
import datetime as _dt
import html

import numpy as np

from .. import __version__
from ..core import MODELS, iae, pidconl_sim_full, predict, propfac, robustness
from ..i18n import T, lang
from .colors import C_DIST
from .plots import C_MV, C_PV, C_SET1, C_SET2, C_SP, mkfig, report_template, tr

SECTIONS = ["model", "tuning", "response", "apc", "signoff"]
STATUSES = ["draft", "deployed", "verified"]
E = html.escape


# ---------------------------------------------------------------- výpočty
def _tchar(code, p):
    return p[-1] + (p[1] if code in ("P1D", "P2D", "I1D") else 0.0) + (p[2] if code == "P2D" else 0.0)


def _clean(c):
    return {k: v for k, v in c.items() if k not in ("FF", "FF_LL")}


def _response(r):
    """Skok SP (+5 %) a v polovině porucha na vstupu procesu (+5 %) pro sadu 1 i 2 → průběhy a ukazatele."""
    code, p = r["model"][0], list(r["model"][1])
    samp = r["ctrl"].get("SampleTime", 1.0)
    t_end = 30 * _tchar(code, p) + 200 * samp
    h = float(min(samp, max(t_end / 6000, samp / 10)))
    h = max(h, t_end / 30000)              # velmi pomalý proces: nejvýš ~30 000 kroků
    n = int(t_end / h) + 1
    t = np.arange(n) * h
    sp = np.where(t >= 0.05 * t_end, 55.0, 50.0)
    d = np.where(t >= 0.5 * t_end, 5.0, 0.0)
    half = t < 0.5 * t_end
    res = {}
    for nm, ctrl in (("1", r["ctrl1"]), ("2", r["ctrl"])):
        o = pidconl_sim_full(code, p, [], h, sp, 50.0, 50.0, _clean(ctrl), [], d)
        pv, mv = o["PV"], o["MV"]
        ok = bool(np.all(np.isfinite(pv)) and np.abs(pv).max() < 1e4)
        e = sp - pv
        out_band = np.where(half & (np.abs(e) > 0.1))[0]           # ±2 % skoku 5 %
        res[nm] = dict(t=t, sp=sp, pv=pv, mv=mv, ok=ok,
                       iae_sp=iae(t[half], sp[half], pv[half]) if ok else np.nan,
                       iae_d=iae(t[~half], sp[~half], pv[~half]) if ok else np.nan,
                       over=max(0.0, (pv[half].max() - 55.0) / 5.0 * 100) if ok else np.nan,
                       settle=(t[out_band[-1]] - 0.05 * t_end) if ok and len(out_band) else np.nan,
                       travel=float(np.abs(np.diff(mv)).sum()) if ok else np.nan)
    return res


def _robust(r):
    code, p = r["model"][0], list(r["model"][1])
    out = {}
    for nm, ctrl in (("1", r["ctrl1"]), ("2", r["ctrl"])):
        try:
            out[nm] = robustness(code, p, _clean(ctrl))
        except Exception:
            out[nm] = dict(Ms=np.nan, GM=np.nan, PM=np.nan, stable=False)
    return out


# ---------------------------------------------------------------- formátování
def _f(v, d=4):
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return "∞" if v is not None and isinstance(v, float) and np.isinf(v) else "—"
    if isinstance(v, bool):
        return "✓" if v else "✗"
    return f"{v:.{d}g}"


def _rng(rng, unit):
    return E(f"{_f(rng[0])}–{_f(rng[1])}" + (f" {unit}" if unit else ""))


def _ti(c):
    v = c.get("TI")
    return np.inf if v is None or not np.isfinite(v) or v <= 0 else v


def _param_rows(r):
    """Parametry k nastavení v PIDConL: (název, původně, nově, jednotka) – sady a společná konfigurace bloku."""
    c1, c2 = r["ctrl1"], r["ctrl"]
    PR, MR = r["pv_rng"][1] - r["pv_rng"][0], r["mv_rng"][1] - r["mv_rng"][0]
    mv = lambda x: r["mv_rng"][0] + x * MR / 100  # noqa: E731
    rows = [("Gain", c1["Gain"], c2["Gain"], ""), ("TI", _ti(c1), _ti(c2), "s"), ("TD", c1.get("TD", 0.0), c2.get("TD", 0.0), "s")]
    blk = [("DiffGain", c2.get("DiffGain"), ""), ("SampleTime", c2.get("SampleTime"), "s"),
           ("PropFacSP", propfac(c2), ""), ("DiffToFbk", 1 if c2.get("DiffFbk") else 0, ""),
           ("DeadBand", c2.get("DeadBand", 0.0) * PR / 100 if c2.get("DeadBand") is not None else None, r["u_pv"] or "PV"),
           ("MV_LoLim", mv(c2["MV_Lo"]) if c2.get("MV_Lo") is not None else None, r["u_mv"]),
           ("MV_HiLim", mv(c2["MV_Hi"]) if c2.get("MV_Hi") is not None else None, r["u_mv"]),
           (T("pvfilt"), c2.get("PVFilt"), "s"),
           (T("rp_mvrate"), c2.get("MVRate", 0.0) * MR / 100 if c2.get("MVRate") is not None else None, f"{r['u_mv'] or 'MV'}/s"),
           (T("rp_sprate"), c2.get("SPRate", 0.0) * PR / 100 if c2.get("SPRate") is not None else None, f"{r['u_pv'] or 'PV'}/s")]
    ff = [g for g in (c2.get("FF") or []) if g]
    ffll = list(c2.get("FF_LL") or [])
    for j, g in enumerate(c2.get("FF") or []):
        if g:
            nm = r["c_d"][j] if j < len(r["c_d"]) else f"#{j + 1}"
            blk.append((T("rp_ff", d=nm), g * MR / 100, f"{r['u_mv'] or 'MV'} / 1 {nm}"))   # vstup FFwd: jednotky MV
            lead, lag_, delay = ffll[j] if j < len(ffll) else (0.0, 0.0, 0.0)
            if lag_ > 0:
                blk += [(T("rp_ff_lead", d=nm), lead, "s"), (T("rp_ff_lag", d=nm), lag_, "s")]
            if delay > 0:
                blk.append((T("rp_ff_delay", d=nm), delay, "s"))
    return rows, [b for b in blk if b[1] is not None], bool(ff)


# ---------------------------------------------------------------- grafy
def ff_used(r):
    """Dopředná vazba zapnutá v sadě 2: [(porucha, zesílení [jedn. MV / jedn. poruchy], (lead, lag, zpoždění))]."""
    c = r.get("ctrl") or {}
    ffs, ll = list(c.get("FF") or []), list(c.get("FF_LL") or [])
    mr = r["mv_rng"][1] - r["mv_rng"][0]
    out = []
    for j, g in enumerate(ffs):
        if g and np.isfinite(g) and j < len(r.get("c_d") or []):
            lead, lag, dl = (list(ll[j]) + [0.0, 0.0, 0.0])[:3] if j < len(ll) and ll[j] is not None else (0.0, 0.0, 0.0)
            out.append((str(r["c_d"][j]), float(g) * mr / 100, (float(lead), float(lag), float(dl))))
    return out


def _apc_used_html(r):
    """Použité APC: dopředná vazba v sadě 2 (hodnoty pro FFwd), jinak informace, že žádná struktura v sadě není."""
    ff = ff_used(r)
    if not ff:
        return f"<p>{E(T('rp_apc_none'))}</p>"
    u = r["u_mv"] or "MV"
    rows = "".join(
        f"<tr><td>{E(dn)}</td><td class='num'>{_f(g)}</td><td>{E(u)}/{E(dn)}</td>"
        f"<td>{E(T('rp_ff_dyn') if any(x > 0 for x in ll) else T('rp_ff_static'))}</td>"
        f"<td class='num'>{_f(ll[0])}</td><td class='num'>{_f(ll[1])}</td><td class='num'>{_f(ll[2])}</td></tr>"
        for dn, g, ll in ff)
    head = "".join(f"<th>{E(h)}</th>" for h in (T("rp_dv"), T("rp_ff_gain"), T("rp_unit"), T("rp_ff_kind"),
                                                 "lead [s]", "lag [s]", T("ff_delay")))
    return (f"<p>{E(T('rp_apc_ff'))}</p><table><tr>{head}</tr>{rows}</table>"
            f"<p class='muted'>{E(T('rp_apc_ff_note'))}</p>")


def _fig_html(fig, first, mode):
    fig.layout.template = report_template()
    inc = ("cdn" if mode == "cdn" else True) if first else False
    return fig.to_html(full_html=False, include_plotlyjs=inc, config={"displaylogo": False, "responsive": True})


def _fig_response(r, resp):
    EP = lambda x: r["pv_rng"][0] + np.asarray(x) * (r["pv_rng"][1] - r["pv_rng"][0]) / 100  # noqa: E731
    EM = lambda x: r["mv_rng"][0] + np.asarray(x) * (r["mv_rng"][1] - r["mv_rng"][0]) / 100  # noqa: E731
    f = mkfig(2, [0.62, 0.38])
    a, b = resp["1"], resp["2"]
    f.add_trace(tr(a["t"], EP(a["sp"]), "SP", C_SP, 1.3, "dash", "hv"), 1, 1)
    if a["ok"]:
        f.add_trace(tr(a["t"], EP(a["pv"]), T("rp_orig"), C_SET1, 1.6, "dot"), 1, 1)
        f.add_trace(tr(a["t"], EM(a["mv"]), T("rp_orig"), C_SET1, 1.4, "dot", show=False), 2, 1)
    if b["ok"]:
        f.add_trace(tr(b["t"], EP(b["pv"]), T("rp_new"), C_SET2, 2.2), 1, 1)
        f.add_trace(tr(b["t"], EM(b["mv"]), T("rp_new"), C_SET2, 1.8, show=False), 2, 1)
    u = lambda n, x: f"{n} [{x}]" if x else n  # noqa: E731
    f.update_layout(height=430, margin=dict(l=60, r=20, t=30, b=40))
    f.update_yaxes(title_text=u("PV", r["u_pv"]), row=1, col=1)
    f.update_yaxes(title_text=u("MV", r["u_mv"]), row=2, col=1)
    f.update_xaxes(title_text=T("time_s"), row=2, col=1)
    return f


def _fig_model(r, md):
    """Model vs. data na identifikačním úseku smyčky. md = (t, pv_e, mv_e, poruchy, Ts) na společné mřížce."""
    try:
        code, p, pdl = r["model"]
        t, pv_e, mv_e, dl, Ts = md
        PR, MR = r["pv_rng"][1] - r["pv_rng"][0], r["mv_rng"][1] - r["mv_rng"][0]
        sel = np.ones_like(t, bool) if not r.get("rng") else (t >= r["rng"][0]) & (t <= r["rng"][1])
        if sel.sum() < 20:
            return None, None
        ts = t[sel] - t[sel][0]
        pv = (pv_e[sel] - r["pv_rng"][0]) / PR * 100
        mv = (mv_e[sel] - r["mv_rng"][0]) / MR * 100
        dd = [d[sel] for d in dl][:len(pdl)]
        yhat, fit = predict(code, list(p), [list(x) for x in pdl][:len(dd)], ts, pv, mv, dd, Ts)
        dv = [(str(n), d[sel]) for n, d in zip(r.get("c_d") or [], dl)]       # měřené poruchy (DV) v jejich jednotkách
        f = mkfig(3, [0.5, 0.25, 0.25]) if dv else mkfig(2, [0.65, 0.35])
        f.add_trace(tr(ts, pv_e[sel], "PV", C_PV, 1.3), 1, 1)
        f.add_trace(tr(ts, r["pv_rng"][0] + yhat * PR / 100, T("rp_model"), "#ea580c", 2.0), 1, 1)
        f.add_trace(tr(ts, mv_e[sel], "MV", C_MV, 1.4, shape="hv"), 2, 1)
        for i, (n, d) in enumerate(dv):
            f.add_trace(tr(ts, d, n, C_DIST[i % len(C_DIST)], 1.4), 3, 1)
        u = lambda n, x: f"{n} [{x}]" if x else n  # noqa: E731
        f.update_layout(height=460 if dv else 380, margin=dict(l=60, r=20, t=30, b=40))
        f.update_yaxes(title_text=u("PV", r["u_pv"]), row=1, col=1)
        f.update_yaxes(title_text=u("MV", r["u_mv"]), row=2, col=1)
        if dv:
            f.update_yaxes(title_text="DV", row=3, col=1)
        f.update_xaxes(title_text=T("time_s"), row=3 if dv else 2, col=1)
        return f, fit
    except Exception:
        return None, None


# ---------------------------------------------------------------- report
_CSS = """
body{font-family:Inter,'Segoe UI',Roboto,Arial,sans-serif;max-width:1050px;margin:28px auto;color:#1f2937;padding:0 22px;
     font-size:14px;line-height:1.45}
h1{font-weight:650;font-size:1.6rem;margin:0 0 4px}h2{margin:34px 0 10px;font-size:1.2rem;border-bottom:2px solid #1f5fa8;
padding-bottom:4px}h3{font-size:1rem;margin:22px 0 6px}.muted{color:#6b7280}
table{border-collapse:collapse;margin:6px 0 10px;font-size:.92rem}td,th{border:1px solid #e5e7eb;padding:4px 10px;text-align:left}
th{background:#f3f5f8;font-weight:600}td.num{text-align:right;font-variant-numeric:tabular-nums}
.meta td{border:none;padding:2px 18px 2px 0}.meta td:first-child{color:#6b7280}
.badge{display:inline-block;padding:2px 10px;border-radius:999px;font-size:.85rem;font-weight:600}
.b-draft{background:#fef3c7;color:#92400e}.b-deployed{background:#dbeafe;color:#1e40af}.b-verified{background:#dcfce7;color:#166534}
.note{background:#f9fafb;border-left:4px solid #1f5fa8;padding:10px 14px;white-space:pre-wrap}
.key{background:#f0f6ff;border:1px solid #c7dbf5;border-radius:10px;padding:10px 16px;margin:8px 0}
.chg{font-weight:600}.better{color:#166534}.worse{color:#b91c1c}
.sign td{height:46px;min-width:170px}.print{position:fixed;top:14px;right:18px;padding:6px 14px;border-radius:8px;
border:1px solid #1f5fa8;background:#1f5fa8;color:#fff;cursor:pointer;font:inherit}
.loop{break-before:page}footer{margin-top:40px;color:#9ca3af;font-size:.8rem}
@media print{.print{display:none}body{margin:0;max-width:none;font-size:12px}h2{break-after:avoid}
table,.key,.js-plotly-plot{break-inside:avoid}.modebar{display:none!important}@page{size:A4;margin:14mm}}
"""


def build_report(recs, meta, sections, chart_mode="inline", model_data=None, apc=None):
    """
    Celý report jako HTML text. recs: záznamy smyček s modelem a oběma sadami; meta: plant, author, status, comment;
    sections: podmnožina SECTIONS; chart_mode: "inline" (Plotly v souboru, funguje offline) nebo "cdn" (malý soubor,
    grafy z internetu); model_data(r) → (t, pv_e, mv_e, poruchy, Ts) nebo None pro graf modelu;
    apc: hodnoty APC aktivní smyčky – dict(items = doporučení, smith = řádky šablony nebo None,
    gs = (tabulka GainSched, podle ER) nebo None).
    """
    apc = apc or {}
    now = _dt.datetime.now()
    status = meta.get("status") or "draft"
    parts = [f"<button class='print' onclick='window.print()'>{E(T('rp_print'))}</button>",
             f"<h1>{E(T('rp_title'))}</h1>",
             "<table class='meta'>"
             f"<tr><td>{E(T('rp_plant'))}</td><td><b>{E(meta.get('plant') or '—')}</b></td></tr>"
             f"<tr><td>{E(T('rp_loops'))}</td><td>{E(', '.join(r['name'] for r in recs) or '—')}</td></tr>"
             f"<tr><td>{E(T('rp_author'))}</td><td>{E(meta.get('author') or '—')}</td></tr>"
             f"<tr><td>{E(T('rp_date'))}</td><td>{now:%d.%m.%Y %H:%M}</td></tr>"
             f"<tr><td>{E(T('rp_status'))}</td><td><span class='badge b-{status}'>{E(T('rp_st_' + status))}</span></td></tr>"
             "</table>"]
    if meta.get("comment"):
        parts.append(f"<div class='note'>{E(meta['comment'])}</div>")
    if not recs:
        parts.append(f"<p>{E(T('rp_no_model'))}</p>")

    # ---- shrnutí: co nastavit (všechny smyčky)
    data = {r["id"]: dict(resp=_response(r), rob=_robust(r)) for r in recs}
    if recs:
        parts.append(f"<h2>{E(T('rp_summary'))}</h2><p class='muted'>{E(T('rp_summary_help'))}</p>")
        head = "".join(f"<th>{E(h)}</th>" for h in (T("rp_loop"), T("rp_model"), "FIT", "Gain", "TI [s]", "TD [s]", "Ms",
                                                     T("rp_iae_sp"), T("rp_iae_d"), "APC"))
        rows = []
        for r in recs:
            d = data[r["id"]]
            def chg(a, b, better_low=None, fmt=_f):
                cls = ""
                if better_low is not None and np.isfinite(a) and np.isfinite(b) and a != b:
                    cls = "better" if (b < a) == better_low else "worse"
                return f"<td class='num'>{fmt(a)} → <span class='chg {cls}'>{fmt(b)}</span></td>"
            def ms_cell(a, b):   # Ms je v pořádku do ≈ 2; červeně jen nad tím (vyšší Ms = rychlejší, ale méně robustní)
                cls = "worse" if np.isfinite(b) and b > 2.0 else ("better" if np.isfinite(a) and a > 2.0 >= b else "")
                return f"<td class='num'>{_f(a, 3)} → <span class='chg {cls}'>{_f(b, 3)}</span></td>"
            c1, c2 = r["ctrl1"], r["ctrl"]
            rows.append("<tr>" + f"<td><b>{E(r['name'])}</b></td><td>{E(T('model_' + r['model'][0]))}</td>"
                        f"<td class='num'>{_f(r.get('fit'), 3)} %</td>"
                        + chg(c1["Gain"], c2["Gain"]) + chg(_ti(c1), _ti(c2)) + chg(c1.get("TD", 0), c2.get("TD", 0))
                        + ms_cell(d["rob"]["1"]["Ms"], d["rob"]["2"]["Ms"])
                        + chg(d["resp"]["1"]["iae_sp"], d["resp"]["2"]["iae_sp"], True, lambda v: _f(v, 3))
                        + chg(d["resp"]["1"]["iae_d"], d["resp"]["2"]["iae_d"], True, lambda v: _f(v, 3))
                        + f"<td>{E(', '.join('FF ' + dn for dn, _, _ in ff_used(r)) or '—')}</td></tr>")
        parts.append(f"<table><tr>{head}</tr>{''.join(rows)}</table>")

    first_fig = True
    for r in recs:
        d = data[r["id"]]
        code, p, pdl = r["model"]
        parts.append(f"<section class='loop'><h2>{E(T('rp_loop'))} {E(r['name'])}</h2>")
        parts.append("<table class='meta'>"
                     f"<tr><td>PV</td><td>{E(str(r['c_pv']))} ({_rng(r['pv_rng'], r['u_pv'])})</td></tr>"
                     f"<tr><td>MV</td><td>{E(str(r['c_mv']))} ({_rng(r['mv_rng'], r['u_mv'])})</td></tr>"
                     f"<tr><td>SP</td><td>{E(str(r.get('c_sp') or '—'))}</td></tr>"
                     f"<tr><td>{E(T('rp_dv'))}</td><td>{E(', '.join(map(str, r['c_d'])) or '—')}</td></tr></table>")
        if "tuning" in sections:
            rows, blk, _ = _param_rows(r)
            parts.append(f"<h3>{E(T('rp_params'))}</h3><div class='key'><table><tr><th>{E(T('rp_param'))}</th>"
                         f"<th>{E(T('rp_orig'))}</th><th>{E(T('rp_new'))}</th><th>{E(T('rp_unit'))}</th></tr>"
                         + "".join(f"<tr><td><b>{E(n)}</b></td><td class='num'>{_f(a)}</td><td class='num'><b>{_f(b)}</b></td>"
                                   f"<td>{E(u)}</td></tr>" for n, a, b, u in rows)
                         + "</table></div>"
                         f"<p class='muted'>{E(T('rp_block'))}</p><table>"
                         + "".join(f"<tr><td>{E(n)}</td><td class='num'>{_f(v)}</td><td>{E(u)}</td></tr>" for n, v, u in blk)
                         + "</table>")
            rb, rs = d["rob"], d["resp"]
            head = "".join(f"<th>{E(h)}</th>" for h in ("", "Ms", "GM", "PM [°]", T("rp_iae_sp"), T("rp_iae_d"),
                                                         T("rp_over"), T("rp_settle"), T("rp_travel")))
            body = "".join(
                f"<tr><td><b>{E(T('rp_orig') if nm == '1' else T('rp_new'))}</b></td>"
                f"<td class='num'>{_f(rb[nm].get('Ms'), 3)}</td><td class='num'>{_f(rb[nm].get('GM'), 3)}</td>"
                f"<td class='num'>{_f(rb[nm].get('PM'), 3)}</td><td class='num'>{_f(rs[nm]['iae_sp'], 3)}</td>"
                f"<td class='num'>{_f(rs[nm]['iae_d'], 3)}</td><td class='num'>{_f(rs[nm]['over'], 3)} %</td>"
                f"<td class='num'>{_f(rs[nm]['settle'], 3)} s</td><td class='num'>{_f(rs[nm]['travel'], 3)} %</td></tr>"
                for nm in ("1", "2"))
            parts.append(f"<h3>{E(T('rp_robust'))}</h3><table><tr>{head}</tr>{body}</table>"
                         f"<p class='muted'>{E(T('rp_robust_help'))}</p>")
        if "response" in sections:
            parts.append(f"<h3>{E(T('rp_response'))}</h3><p class='muted'>{E(T('rp_response_help'))}</p>")
            parts.append(_fig_html(_fig_response(r, d["resp"]), first_fig, chart_mode))
            first_fig = False
        if "model" in sections:
            names = MODELS[code]["params"]
            parts.append(f"<h3>{E(T('rp_model_title'))}</h3><p>{E(T('model_' + code))}: "
                         + ", ".join(f"{E(n)} = {_f(v)}" for n, v in zip(names, p))
                         + (f" · FIT {_f(r.get('fit'), 3)} %" if r.get("fit") is not None else "")
                         + (f" · {E(T('seg_id'))} {r['rng'][0]:.0f}–{r['rng'][1]:.0f} s" if r.get("rng") else "") + "</p>"
                         f"<p class='muted'>{E(T('units_note'))}</p>")
            md = model_data(r) if model_data else None
            fm, fit = _fig_model(r, md) if md is not None else (None, None)
            if fm is not None:
                parts.append(_fig_html(fm, first_fig, chart_mode))
                first_fig = False
        if "apc" in sections:
            parts.append(f"<h3>{E(T('rp_apc_used'))}</h3>" + _apc_used_html(r))
        if "apc" in sections and r["active"]:
            items = apc.get("items") or []
            if items:
                parts.append(f"<h3>{E(T('rp_apc'))}</h3><ul>" + "".join(f"<li>{E(txt)}</li>" for _, txt, _ in items) + "</ul>")
            srows = apc.get("smith")
            if srows and any(k == "smith" for k, _, _ in items) and not MODELS[code]["integ"]:
                parts.append(f"<h3>{E(T('rp_smith'))}</h3><table><tr>"
                             + "".join(f"<th>{E(T('sm_apl_' + h))}</th>" for h in ("block", "input", "value", "unit"))
                             + "</tr>" + "".join(f"<tr><td>{E(b)}</td><td>{E(i)}</td><td>{_f(x)}</td><td>{E(u)}</td></tr>"
                                                 for b, i, x, u in srows) + "</table>"
                             f"<p class='muted'>{E(T('sm_apl_note'))}</p>")
            gv = apc.get("gs") if not MODELS[code]["integ"] else None
            if gv:
                gtab, by_er = gv
                parts.append(f"<h3>{E(T('rp_gs'))}</h3><table><tr><th>{E(T('gs_in'))}</th>"
                             + "".join(f"<th>{E(T('gs_point', i=i))}</th>" for i in (1, 2, 3))
                             + f"<th>{E(T('sm_apl_unit'))}</th></tr>"
                             + "".join(f"<tr><td>{E(nm)}</td>" + "".join(f"<td>{_f(v)}</td>" for v in vals)
                                       + f"<td>{E(u)}</td></tr>" for nm, vals, u in gtab) + "</table>"
                             f"<p class='muted'>{E(T('rp_gs_note_er' if by_er else 'rp_gs_note'))}</p>")
        parts.append("</section>")

    if "signoff" in sections:
        parts.append(f"<h2>{E(T('rp_signoff'))}</h2><table class='sign'><tr><th></th><th>{E(T('rp_name'))}</th>"
                     f"<th>{E(T('rp_date'))}</th><th>{E(T('rp_signature'))}</th></tr>"
                     + "".join(f"<tr><td>{E(T(k))}</td><td></td><td></td><td></td></tr>"
                               for k in ("rp_sig_made", "rp_sig_approved", "rp_sig_deployed")) + "</table>")
    parts.append(f"<footer>{E(T('rp_footer', d=f'{now:%d.%m.%Y %H:%M}', v=__version__))}</footer>")
    title = f"{T('rp_title')} – {meta.get('plant') or ', '.join(r['name'] for r in recs)}"
    return (f"<!doctype html><html lang='{lang()}'><head><meta charset='utf-8'>"
            f"<meta name='viewport' content='width=device-width,initial-scale=1'><title>{E(title)}</title>"
            f"<style>{_CSS}</style></head><body>{''.join(parts)}</body></html>")
