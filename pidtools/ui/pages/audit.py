"""
Záložka Přehled smyček (web, stejně jako desktop): více smyček z jednoho souboru. Vpravo tabulka smyček
(PV / MV / SP / poloha – návrh z názvů tagů), vlevo pořadí podle problémů, společné oscilace a graf vybrané
smyčky. Výpočty v pidtools.app.audit.
"""
import pandas as pd
import streamlit as st

from ...app import audit
from ...app.dataset import Signals
from ...i18n import T
from .. import loops
from ..charts import mkfig, show, style, tr
from ..layout import section, workspace
from ..theme import C_MV, C_PV, C_SP

ss = st.session_state
COLS = ("name", "pv", "mv", "sp", "pos", "theta", "integ")


def _sig(ctx):
    return Signals(t_all=ctx.t_all, sigs=list(ctx.sigs), get=ctx.get)


def _frame(defs):
    return pd.DataFrame([{"name": d.name, "pv": d.pv, "mv": d.mv, "sp": d.sp or "—", "pos": d.pos or "—",
                          "theta": d.extra.get("theta"), "integ": d.integ} for d in defs], columns=list(COLS))


def _defs(df):
    recs = []
    for _, r in df.iterrows():
        th = r.get("theta")
        recs.append(dict(name=str(r.get("name") or ""), pv=r.get("pv"), mv=r.get("mv"), sp=r.get("sp"), pos=r.get("pos"),
                         theta=None if th is None or pd.isna(th) else float(th), integ=bool(r.get("integ"))))
    return recs


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
        ctx.gph["audit"] = st.container()
        ws = workspace()
        sig = _sig(ctx)
        ekey = f"au_ed|{ctx.fname}"
        with ws.side:
            top = st.container()
        with section(ws.side, T("au_sec_loops"), "au_loops", icon=":material/list:"):
            st.caption(T("au_loops_help"))
            if ss.get("au_propose_req") or f"{ekey}|init" not in ss:
                ss.pop("au_propose_req", None)
                saved = audit.from_records(ss.get("audit_loops"), sig.sigs)
                ss[f"{ekey}|init"] = _frame(saved or audit.propose(sig.sigs, sig.get))
                ss.pop(ekey, None)
            opts = list(sig.sigs)
            df = st.data_editor(
                ss[f"{ekey}|init"], key=ekey, num_rows="dynamic", hide_index=True, width="stretch",
                column_config={
                    "name": st.column_config.TextColumn(T("au_c_name")),
                    "pv": st.column_config.SelectboxColumn(T("au_c_pv"), options=opts, required=True),
                    "mv": st.column_config.SelectboxColumn(T("au_c_mv"), options=opts, required=True),
                    "sp": st.column_config.SelectboxColumn(T("au_c_sp"), options=["—"] + opts),
                    "pos": st.column_config.SelectboxColumn(T("au_c_pos"), options=["—"] + opts),
                    "theta": st.column_config.NumberColumn(T("au_c_theta"), min_value=0.0, format="%.4g"),
                    "integ": st.column_config.CheckboxColumn(T("au_c_integ"))})
            recs = _defs(df)
            defs = audit.from_records(recs, sig.sigs)
            if st.button(T("au_propose"), key="g_au_propose", width="stretch"):
                ss["au_propose_req"] = True
                st.rerun()
        with section(ws.side, T("au_sec_window"), "au_window", expanded=False, icon=":material/date_range:"):
            T_ = float(ctx.t[-1])
            wkey = f"au_win|{ctx.fname}"
            if wkey not in ss or not (0.0 <= ss[wkey][0] < ss[wkey][1] <= T_ + 1e-9):
                ss[wkey] = (0.0, T_)
            win = st.slider(T("seg_diag"), 0.0, T_, step=float(max(ctx.Ts, T_ / 1000)), key=wkey)
        with section(ws.side, T("au_sec_help"), "au_help", expanded=False, icon=":material/help:"):
            st.markdown(T("au_help"))
        with top:
            run = st.button(T("au_run"), key="g_au_run", type="primary", icon=":material/play_arrow:", width="stretch")
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
        top.caption(T("au_done", n=len(res), b=sum(1 for r in res if r["score"] > 0)))
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
        with ws.main:
            ev = st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", on_select="rerun",
                              selection_mode="single-row", key=f"au_rank|{ctx.fname}")
            groups = audit.common_oscillations(res)
            if groups:
                for g in groups:
                    st.warning(T("au_common", p=f"{g['period']:.0f}", l=", ".join(g["loops"]), s=g["source"])
                               + (" " + T("au_common_stic") if g["by_stiction"] else ""), icon=":material/sync:")
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
                st.markdown(f"**{r['name']}**")
                show(style(fig, ctx.H, ["PV", "MV"], T("time_s"), rev=f"au|{r['name']}"), key="chart_audit",
                     fname="loop_overview")
                rec = next((x for x in recs if (x["name"] or x["pv"]) == r["name"]), None)
                if rec:
                    st.button(T("au_open_loop"), key="g_au_open", help=T("au_open_help"), on_click=_open_loop,
                              args=(ctx.fname, rec), icon=":material/add:")
