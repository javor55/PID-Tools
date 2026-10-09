"""
Záložka Přehled smyček (web, stejně jako desktop): více smyček z jednoho souboru. Vpravo tabulka smyček
(PV / MV / SP / poloha – návrh z názvů tagů), vlevo pořadí podle problémů, společné oscilace a graf vybrané
smyčky. Výpočty v pidtools.app.audit.
"""
import html

import pandas as pd
import streamlit as st

from ...app import audit
from ...app.dataset import Signals
from ...i18n import T
from .. import loops
from ..charts import mkfig, show, style, tr
from ..layout import section, workspace
from ..theme import C_MV, C_PV, C_SP
from ..table import table
from ..kit import card, head, lrow

ss = st.session_state


def _sig(ctx):
    return Signals(t_all=ctx.t_all, sigs=list(ctx.sigs), get=ctx.get)


def _open_loop(fname, rec):
    """Callback: smyčka z přehledu jako nová smyčka projektu (sloupce se předvyplní)."""
    loops.add()
    ss[f"c_pv|{fname}"], ss[f"c_mv|{fname}"] = rec["pv"], rec["mv"]
    ss[f"c_sp|{fname}"] = rec["sp"] or "—"
    ss[f"c_pos|{fname}"] = rec["pos"] or "—"
    ss["loop_tag"] = rec["name"]
    ss["main_tab"] = T("tab2")


def render(ctx):
    with ctx.tabs["audit"]:
        ctx.gph["audit"] = True
        ws = workspace()
        sig = _sig(ctx)
        dkey = f"au_defs|{ctx.fname}"
        fkey = f"au_f|{ctx.fname}|"           # klíče polí vybrané smyčky
        with section(ws.side, T("au_sec_loops"), "au_loops", expanded=True):
            st.caption(T("au_loops_help"))
            if ss.get("au_propose_req") or dkey not in ss:
                prop = ss.pop("au_propose_req", None)
                saved = None if prop else audit.from_records(ss.get("audit_loops"), sig.sigs)
                ss[dkey] = audit.to_records(saved or audit.propose(sig.sigs, sig.get))
                for k_ in [k_ for k_ in ss if str(k_).startswith(fkey)]:
                    del ss[k_]
            recs = ss[dkey]
            opts = list(sig.sigs)
            skey = f"au_sel|{ctx.fname}"
            if "au_del_req" in ss:                 # odebrání smyčky (výběr se mění před vytvořením widgetu)
                j_ = ss.pop("au_del_req")
                if 0 <= j_ < len(recs):
                    recs.pop(j_)
                for k_ in [k_ for k_ in ss if str(k_).startswith(fkey)]:
                    del ss[k_]
                ss[skey] = max(0, j_ - 1)
            b3 = st.container()
            b1, b2 = st.columns(2)
            if b1.button(T("au_add"), key="g_au_add", icon=":material/add:", width="stretch"):
                recs.append(dict(name=f"{T('au_c_name')} {len(recs) + 1}", pv=opts[0], mv=opts[min(1, len(opts) - 1)],
                                 sp=None, pos=None, theta=None, integ=False))
                ss[skey] = len(recs) - 1
            if b3.button(T("au_propose"), key="g_au_propose", icon=":material/auto_awesome:", width="stretch"):
                ss["au_propose_req"] = True
                st.rerun()
            if recs:
                if not (0 <= ss.get(skey, 0) < len(recs)):
                    ss[skey] = 0
                # přehled smyček (klepnutím se vybere smyčka k úpravě níže)
                ovw = pd.DataFrame([{T("au_c_name"): x["name"] or x["pv"],
                                     "PV · MV · SP": " · ".join(str(v) for v in (x["pv"], x["mv"], x["sp"]) if v),
                                     T("au_c_integ_s"): "✓" if x["integ"] else "",
                                     "θ [s]": float(x["theta"]) if x["theta"] else None} for x in recs])
                ev_o = table(ovw, key=f"au_ovw|{ctx.fname}|{len(recs)}", select=True)
                if ev_o.selection.rows and ss.get(f"{skey}|tab") != ev_o.selection.rows[0]:
                    ss[skey] = ss[f"{skey}|tab"] = ev_o.selection.rows[0]
                i = st.selectbox(T("au_c_name"), list(range(len(recs))), key=skey, label_visibility="collapsed",
                                 format_func=lambda j: f"{j + 1} · {recs[j]['name'] or recs[j]['pv']}")
                if b2.button(T("au_del"), key="g_au_del", icon=":material/remove:", width="stretch"):
                    ss["au_del_req"] = i
                    st.rerun()
                r_ = recs[i]
                k_ = f"{fkey}{i}|"
                for f_, v_ in (("name", r_["name"] or ""), ("pv", r_["pv"]), ("mv", r_["mv"]), ("sp", r_["sp"] or "—"),
                               ("pos", r_["pos"] or "—"), ("theta", float(r_["theta"] or 0.0)),
                               ("integ", bool(r_["integ"]))):
                    if k_ + f_ not in ss:
                        ss[k_ + f_] = v_
                for f_ in ("pv", "mv"):
                    if ss[k_ + f_] not in opts:
                        ss[k_ + f_] = opts[0]
                for f_ in ("sp", "pos"):
                    if ss[k_ + f_] not in ["—"] + opts:
                        ss[k_ + f_] = "—"
                rr = (0.7, 2.3)                  # popisek vlevo, pole vpravo
                r_["name"] = lrow(T("au_c_name"), None, rr).text_input(T("au_c_name"), key=k_ + "name",
                                                                        label_visibility="collapsed")
                r_["pv"] = lrow("PV", None, rr, color=C_PV).selectbox("PV", opts, key=k_ + "pv",
                                                                      label_visibility="collapsed")
                r_["mv"] = lrow("MV", None, rr, color=C_MV).selectbox("MV", opts, key=k_ + "mv",
                                                                      label_visibility="collapsed")
                sp_ = lrow("SP", None, rr, color=C_SP).selectbox("SP", ["—"] + opts, key=k_ + "sp",
                                                                 label_visibility="collapsed")
                pos_ = lrow(T("pos_short"), None, rr).selectbox(T("au_c_pos"), ["—"] + opts, key=k_ + "pos",
                                                                label_visibility="collapsed")
                r_["sp"], r_["pos"] = (None if sp_ == "—" else sp_), (None if pos_ == "—" else pos_)
                th_ = lrow("θ [s]", T("au_theta_help"), rr).number_input(
                    T("au_c_theta"), min_value=0.0, key=k_ + "theta", format="%.4g", label_visibility="collapsed")
                r_["theta"] = float(th_) if th_ > 0 else None
                r_["integ"] = st.toggle(T("au_c_integ"), key=k_ + "integ")
            else:
                st.info(T("au_none"), icon=":material/info:")
            defs = audit.from_records(recs, sig.sigs)
        with section(ws.side, T("au_sec_window"), "au_window", expanded=True):
            T_ = float(ctx.t[-1])
            wkey = f"au_win|{ctx.fname}"
            if wkey not in ss or not (0.0 <= ss[wkey][0] < ss[wkey][1] <= T_ + 1e-9):
                ss[wkey] = (0.0, T_)
            win = st.slider(T("seg_diag"), 0.0, T_, step=float(max(ctx.Ts, T_ / 1000)), key=wkey)
        with ws.side.container(key="pid_cta_audit"):
            run = st.button(T("au_run"), key="g_au_run", type="primary", width="stretch")
        with section(ws.side, T("au_sec_help"), "au_help"):
            st.markdown(T("au_help"))
        if run and defs:
            ss["audit_loops"] = audit.to_records(defs)
            with ws.main, st.spinner(T("dk_calculating")):
                full = win[0] <= 0 and win[1] >= float(ctx.t[-1])
                ts_user = ss.get("ts_user") if ss.get("ts_manual") else None
                ss["au_res"] = dict(fname=ctx.fname, res=audit.analyse(sig, defs, ts_user, None if full else win))
        res = (ss.get("au_res") or {}).get("res") if (ss.get("au_res") or {}).get("fname") == ctx.fname else None
        if not res:
            ws.main.info(T("au_hint"), icon=":material/info:")
            return
        rows = []
        for i, r in enumerate(res):
            if not r["ok"]:
                rows.append({"#": i + 1, T("au_c_name"): r["name"], T("au_score"): None,
                             T("au_problems"): T(r["err"] or "err_fit_failed")})
                continue
            k = r["kpis"]
            rows.append({"#": i + 1, T("au_c_name"): r["name"], T("au_score"): r["score"],
                         T("au_problems"): ", ".join(T("au_p_" + p) for p, _ in r["problems"]) or "✓ " + T("au_ok"),
                         T("au_std"): float(f"{k['std_e']:.4g}"), T("au_iae"): float(f"{k['iae_h']:.4g}"),
                         T("au_travel"): float(f"{k['travel_h']:.4g}"), T("au_rev"): round(k["rev_h"], 1),
                         T("au_lim"): round(k["at_lim"], 1), T("au_frozen"): round(k["frozen"], 1),
                         T("au_period"): round(k["period"]) if k["period"] else None,
                         T("au_stic"): T("stic_short_" + k["stic"]) if k["stic"] else "—",
                         T("kpi_harris"): None if k["harris"] is None else round(k["harris"], 2)})
        nbad = sum(1 for r in res if r["score"] > 0)
        rdf = pd.DataFrame(rows)
        sc_cls = [["", "", ("bad" if (r["score"] or 0) >= 6 else "warn" if (r["score"] or 0) >= 3 else
                           "ok" if r["ok"] and not r["score"] else ""),
                   ("ok" if r["ok"] and not r["problems"] else "warn")] + [""] * (rdf.shape[1] - 4)
                  for r in res]
        with ws.main:
            with card("au_rank"):
                head(T("au_rank_title"), T("au_rank_help"),
                     note=f"<span class='pid-chip {'s2' if nbad else 's0'}'>{T('au_n_bad', b=nbad, n=len(res))}</span>")
                ev = table(rdf, key=f"au_rank|{ctx.fname}", select=True, cell_class=sc_cls)
                st.caption(T("au_done", n=len(res), b=nbad))
            groups = audit.common_oscillations(res)
            with card("au_common"):
                head(T("au_common_title"), T("au_common_help"))
                if groups:
                    for g in groups:
                        st.markdown(f"<span class='pid-chip s1'>! {T('au_common_chip')}</span>&nbsp; "
                                    + html.escape(T("au_common", p=f"{g['period']:.0f}", l=", ".join(g["loops"]),
                                                    s=g["source"]) + (" " + T("au_common_stic") if g["by_stiction"]
                                                                      else "")), unsafe_allow_html=True)
                else:
                    st.caption(T("au_common_none"))
            sel_ = getattr(getattr(ev, "selection", None), "rows", []) or [0]
            r = res[sel_[0]]
            if r["ok"]:
                fig = mkfig(2, [0.6, 0.4])
                if r["sp"] is not None:
                    fig.add_trace(tr(r["t"], r["sp"], "SP", C_SP, 1.3, "dash", "hv"), 1, 1)
                fig.add_trace(tr(r["t"], r["pv"], "PV", C_PV, 1.4), 1, 1)
                fig.add_trace(tr(r["t"], r["mv"], "MV", C_MV, 1.5), 2, 1)
                dcard = card("au_detail")
                h1, h2 = dcard.columns([3, 1], vertical_alignment="center")
                head(f"{T('au_detail')} · {r['name']}", cont=h1)
                with dcard:
                    show(style(fig, ctx.H, ["PV", "MV"], T("time_s"), rev=f"au|{r['name']}"), key="chart_audit",
                         fname="loop_overview")
                rec = next((x for x in recs if (x["name"] or x["pv"]) == r["name"]), None)
                if rec:
                    h2.button(T("au_open_loop"), key="g_au_open", help=T("au_open_help"), on_click=_open_loop,
                              args=(ctx.fname, rec), width="stretch")
