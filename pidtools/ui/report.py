"""
Report = protokol z ladění regulačních smyček (samostatný HTML soubor, tisk do PDF z prohlížeče).

Obsah se dopočítá z modelů a parametrů všech smyček projektu – nezávisle na tom, co je zrovna rozbalené v aplikaci:
hlavička protokolu, shrnutí (co nastavit v PCS 7, původně / nově), a pro každou smyčku parametry bloku PIDConL,
robustnost (Ms, GM, PM), očekávané chování (skok SP a porucha – sada 1 vs. sada 2), model a jeho shoda s daty,
doporučené struktury APC; nakonec místo pro podpisy.
"""
import datetime as _dt
import html

import numpy as np
import streamlit as st

from ..core import MODELS, iae, pidconl_sim_full, predict, robustness
from ..i18n import T
from . import loops
from .charts import mkfig, tr
from .theme import C_MV, C_PV, C_SET1, C_SET2, C_SP, report_template

ss = st.session_state
SECTIONS = ["model", "tuning", "response", "apc", "signoff"]
STATUSES = ["draft", "deployed", "verified"]
E = html.escape


# ---------------------------------------------------------------- data smyček
def loop_records(ctx):
    """Smyčky projektu (aktivní z aktuálního běhu, ostatní ze snímků) – jen ty s modelem."""
    out = []
    for i in loops.ids():
        r = loops.loop_data(i, ctx.fname)
        r["id"], r["active"] = i, i == loops.active()
        if r["active"]:
            r.update(model=ctx.model, ctrl=ctx.set2_ctrl, ctrl1=ctx.set1_ctrl, rng=tuple(ctx.rng),
                     c_pv=ctx.c_pv, c_mv=ctx.c_mv, c_sp=ctx.c_sp, c_d=list(ctx.c_d),
                     pv_rng=(ctx.pv_lo, ctx.pv_hi), mv_rng=(ctx.mv_lo, ctx.mv_hi), u_pv=ctx.u_pv, u_mv=ctx.u_mv)
            fit = ss.get("fit") or {}
            r["fit"] = fit.get("res", {}).get(ctx.model[0], {}).get("fit") if ctx.model else None
        if r["model"] is not None and r["ctrl"] is not None and r["ctrl1"] is not None:
            out.append(r)
    return out


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
           (T("rp_pfb"), c2.get("PropFbk"), ""), (T("rp_dfb"), c2.get("DiffFbk"), ""),
           ("DeadBand", c2.get("DeadBand", 0.0) * PR / 100 if c2.get("DeadBand") is not None else None, r["u_pv"] or "PV"),
           ("MV_LoLim", mv(c2["MV_Lo"]) if c2.get("MV_Lo") is not None else None, r["u_mv"]),
           ("MV_HiLim", mv(c2["MV_Hi"]) if c2.get("MV_Hi") is not None else None, r["u_mv"]),
           (T("pvfilt"), c2.get("PVFilt"), "s"),
           (T("rp_mvrate"), c2.get("MVRate", 0.0) * MR / 100 if c2.get("MVRate") is not None else None, f"{r['u_mv'] or 'MV'}/s"),
           (T("rp_sprate"), c2.get("SPRate", 0.0) * PR / 100 if c2.get("SPRate") is not None else None, f"{r['u_pv'] or 'PV'}/s")]
    ff = [g for g in (c2.get("FF") or []) if g]   # noqa: F841 – jen pro přehlednost
    for j, g in enumerate(c2.get("FF") or []):
        if g:
            nm = r["c_d"][j] if j < len(r["c_d"]) else f"#{j + 1}"
            blk.append((T("rp_ff", d=nm), g, f"%/{T('rp_unit')}"))
    return rows, [b for b in blk if b[1] is not None], bool(ff)


# ---------------------------------------------------------------- grafy
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


def _fig_model(ctx, r):
    """Model vs. data na identifikačním úseku smyčky (data z aktuálního souboru na společné mřížce)."""
    try:
        code, p, pdl = r["model"]
        PR, MR = r["pv_rng"][1] - r["pv_rng"][0], r["mv_rng"][1] - r["mv_rng"][0]
        t = ctx.t
        sel = np.ones_like(t, bool) if not r.get("rng") else (t >= r["rng"][0]) & (t <= r["rng"][1])
        if r["active"]:
            pv_e, mv_e, dl = ctx.pv_e, ctx.mv_e, list(ctx.dists)
        else:
            pv_e, mv_e = ctx.on_grid(r["c_pv"]), ctx.on_grid(r["c_mv"], zoh=True)
            dl = [ctx.on_grid(c) for c in r["c_d"]]
        if sel.sum() < 20:
            return None, None
        ts = t[sel] - t[sel][0]
        pv = (pv_e[sel] - r["pv_rng"][0]) / PR * 100
        mv = (mv_e[sel] - r["mv_rng"][0]) / MR * 100
        dd = [d[sel] for d in dl][:len(pdl)]
        yhat, fit = predict(code, list(p), [list(x) for x in pdl][:len(dd)], ts, pv, mv, dd, ctx.Ts)
        f = mkfig(2, [0.65, 0.35])
        f.add_trace(tr(ts, pv_e[sel], "PV", C_PV, 1.3), 1, 1)
        f.add_trace(tr(ts, r["pv_rng"][0] + yhat * PR / 100, T("rp_model"), "#ea580c", 2.0), 1, 1)
        f.add_trace(tr(ts, mv_e[sel], "MV", C_MV, 1.4, shape="hv"), 2, 1)
        f.update_layout(height=380, margin=dict(l=60, r=20, t=30, b=40))
        f.update_xaxes(title_text=T("time_s"), row=2, col=1)
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


def build_report(ctx, meta, sections, chart_mode="inline"):
    """
    Celý report jako HTML text. meta: plant, author, status, comment; sections: podmnožina SECTIONS;
    chart_mode: "inline" (Plotly v souboru, funguje offline) nebo "cdn" (malý soubor, grafy z internetu).
    """
    from .pages.apc import gs_values, recommend, smith_values   # až zde – stránka APC importuje moduly UI
    recs = loop_records(ctx)
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
                                                     T("rp_iae_sp"), T("rp_iae_d")))
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
                        + chg(d["resp"]["1"]["iae_d"], d["resp"]["2"]["iae_d"], True, lambda v: _f(v, 3)) + "</tr>")
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
                     f"<tr><td>{E(T('col_dist'))}</td><td>{E(', '.join(map(str, r['c_d'])) or '—')}</td></tr></table>")
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
            fm, fit = _fig_model(ctx, r)
            if fm is not None:
                parts.append(_fig_html(fm, first_fig, chart_mode))
                first_fig = False
        if "apc" in sections and r["active"]:
            items = recommend(ctx)
            if items:
                parts.append(f"<h3>{E(T('rp_apc'))}</h3><ul>" + "".join(f"<li>{E(txt)}</li>" for _, txt, _ in items) + "</ul>")
            if any(k == "smith" for k, _, _ in items) and not MODELS[code]["integ"]:
                try:
                    _, _, srows = smith_values(ctx)
                    parts.append(f"<h3>{E(T('rp_smith'))}</h3><table><tr>"
                                 + "".join(f"<th>{E(T('sm_apl_' + h))}</th>" for h in ("block", "input", "value", "unit"))
                                 + "</tr>" + "".join(f"<tr><td>{E(b)}</td><td>{E(i)}</td><td>{_f(x)}</td><td>{E(u)}</td></tr>"
                                                     for b, i, x, u in srows) + "</table>"
                                 f"<p class='muted'>{E(T('sm_apl_note'))}</p>")
                except Exception:
                    pass
            try:
                gv = gs_values(ctx) if not MODELS[code]["integ"] else None
            except Exception:
                gv = None
            if gv:
                _, gtab, _ = gv
                parts.append(f"<h3>{E(T('rp_gs'))}</h3><table><tr><th>{E(T('gs_in'))}</th>"
                             + "".join(f"<th>{E(T('gs_point', i=i))}</th>" for i in (1, 2, 3))
                             + f"<th>{E(T('sm_apl_unit'))}</th></tr>"
                             + "".join(f"<tr><td>{E(nm)}</td>" + "".join(f"<td>{_f(v)}</td>" for v in vals)
                                       + f"<td>{E(u)}</td></tr>" for nm, vals, u in gtab) + "</table>"
                             f"<p class='muted'>{E(T('rp_gs_note_er' if ss.get('gs_x') == 'er' else 'rp_gs_note'))}</p>")
        parts.append("</section>")

    if "signoff" in sections:
        parts.append(f"<h2>{E(T('rp_signoff'))}</h2><table class='sign'><tr><th></th><th>{E(T('rp_name'))}</th>"
                     f"<th>{E(T('rp_date'))}</th><th>{E(T('rp_signature'))}</th></tr>"
                     + "".join(f"<tr><td>{E(T(k))}</td><td></td><td></td><td></td></tr>"
                               for k in ("rp_sig_made", "rp_sig_approved", "rp_sig_deployed")) + "</table>")
    parts.append(f"<footer>{E(T('rp_footer', d=f'{now:%d.%m.%Y %H:%M}'))}</footer>")
    title = f"{T('rp_title')} – {meta.get('plant') or ', '.join(r['name'] for r in recs)}"
    return (f"<!doctype html><html lang='{ss.get('lang', 'en')}'><head><meta charset='utf-8'>"
            f"<meta name='viewport' content='width=device-width,initial-scale=1'><title>{E(title)}</title>"
            f"<style>{_CSS}</style></head><body>{''.join(parts)}</body></html>")
