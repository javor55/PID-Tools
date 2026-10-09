"""
Záložka Projekt a report.

Projekt = soubor s celou prací (všechny smyčky, modely, ladění, volitelně data) pro pokračování později nebo předání
kolegovi; navíc se práce průběžně ukládá do prohlížeče. Report = protokol z ladění (HTML, tisk do PDF) s tím,
co nastavit v PCS 7, robustností a očekávaným chováním původních a nových parametrů.
"""
import datetime as _dt
import html
import re

import streamlit as st

from ...i18n import T
from .. import loops
from ..project import gather_project, serialize_project
from ..report import SECTIONS, STATUSES, build_report
from ..layout import section, workspace
from ..widgets import seg, sel, tog
from ..kit import card, head, lrow

ss = st.session_state


def _base_name():
    """Základ názvu souboru: zařízení nebo názvy smyček + datum."""
    base = ss.get("rep_plant") or "_".join(loops.name(i) for i in loops.ids()) or "pid"
    return re.sub(r"[^\w.-]+", "_", base, flags=re.UNICODE).strip("_")[:60] + f"_{_dt.date.today():%Y-%m-%d}"


def render(ctx):
    with ctx.tabs["project"]:
        ctx.gph["project"] = True
        if ctx.tabs["project"].open is False:   # sestavení projektu a reportu jen na otevřené záložce
            return
        ws = workspace()
        base = _base_name()
        with section(ws.side, T("proj_title"), "pj_proj", expanded=True):
            st.caption(T("pj_intro"))
            tog(st, T("proj_include_data"), True, "proj_inc", help=T("h_proj_inc"))
            payload = gather_project(ctx, bool(ss.get("proj_inc", True)))
            ss["_proj_payload"] = payload
            st.download_button(T("proj_save"), lambda p=payload: serialize_project(p), f"{base}_projekt.json",
                               "application/json", type="primary", width="stretch", on_click="ignore")
            st.caption(T("proj_save_help") + " " + T("pj_load_hint"))
        rr = (0.8, 2.2)
        with section(ws.side, T("rep_title"), "pj_rep", expanded=True):
            st.caption(T("rep_help"))
            seg(lrow(T("rp_status"), None, rr), T("rp_status"), STATUSES, "draft", "rep_status",
                format_func=lambda x: T("rp_st_" + x), label_visibility="collapsed")
            lrow(T("rp_plant"), None, rr).text_input(T("rp_plant"), key="rep_plant", placeholder=T("rp_plant_ph"),
                                                     label_visibility="collapsed")
            lrow(T("rp_author"), None, rr).text_input(T("rp_author"), key="rep_author", label_visibility="collapsed")
            charts = sel(lrow(T("rp_charts"), T("h_rp_charts"), rr), T("rp_charts"), ["inline", "cdn"], 0,
                         "rep_charts", format_func=lambda x: T("rp_ch_" + x), label_visibility="collapsed")
            st.text_area(T("rep_comment"), key="rep_comment", height=80, placeholder=T("rp_comment_ph"))
        with section(ws.side, T("rp_sections"), "pj_sections", expanded=True):
            if "rep_sections" not in ss:
                ss["rep_sections"] = list(SECTIONS)
            st.pills(T("rp_sections"), SECTIONS, selection_mode="multi", key="rep_sections",
                     format_func=lambda x: T("rp_sec_" + x), help=T("h_rp_sections"), label_visibility="collapsed")
        with ws.side.container(key="pid_cta_report"):
            if st.button(T("rep_build"), type="primary", width="stretch"):
                ss["rep_pending"] = True          # další běh spočítá všechny záložky a sestaví report
                st.rerun()
            if ss.pop("rep_pending", False):
                with st.spinner(T("rp_building")):
                    meta = {k: ss.get("rep_" + k) for k in ("plant", "author", "status", "comment")}
                    ss.report_html = build_report(ctx, meta, ss.get("rep_sections") or [], charts)
        with ws.main:
            with card("pj_prev"):
                h1, h2 = st.columns([3, 1], vertical_alignment="center")
                head(T("rp_preview"), note=html.escape(T("rp_pdf_hint")) if ss.get("report_html") else None, cont=h1)
                if ss.get("report_html"):
                    h2.download_button(T("rep_dl"), ss.report_html, f"{base}_protokol.html", "text/html",
                                       icon=":material/download:", width="stretch", on_click="ignore")
            if ss.get("report_html"):
                st.iframe(ss.report_html, height=900)
            else:
                st.info(T("rp_preview_hint"), icon=":material/description:")
