"""
Záložka APC: výběr regulační struktury – kaskáda, dopředná vazba z měřených poruch, rozvazbení 2×2 (RGA,
decouplery), override (výběr MIN/MAX), Smithův prediktor a gain scheduling (parametry PID podle pracovního bodu
nebo regulační odchylky). Hlavní (vnější) smyčka je vždy aktivní smyčka projektu; druhá smyčka se vybírá z ostatních.
Každá struktura má vlastní modul v této složce.
"""
import streamlit as st

from ....i18n import T
from ... import loops
from ...widgets import seg
from . import cascade, guide
from .common import KINDS, ss
from .decouple import decouple_render
from .feedforward import ff_render
from .gainsched import gainsched_render, gs_values  # noqa: F401 (protokol)
from .override import override_render
from ....app import guides as app_guides
from .recommend import checks_cascade, rec_a, recommend
from .smith import smith_render, smith_values  # noqa: F401 (protokol)
from .more import ratio_render, rga_render, split_render, vpc_render
from ...layout import section, workspace

MORE = {"split": split_render, "vpc": vpc_render, "ratio": ratio_render, "rga": rga_render}


def render(ctx):
    with ctx.tabs["cascade"]:
        ctx.gph["apc"] = st.container()
        st.caption(ctx.block_summary)
        kind = seg(st, T("apc_kind"), KINDS, "cascade", "apc_kind", format_func=lambda x: T("apc_" + x),
                   help=T("h_apc_kind")) or "cascade"
        if ctx.model is not None:
            guide.recommendations(recommend(ctx))
        if kind == "cascade":
            guide.render("cascade", checks_cascade(ctx), T("g_impl_cascade"))
            cascade.render_body(ctx)
            return
        st.markdown(T("apc_intro_" + kind))
        if ctx.model is None or ctx.set2_ctrl is None:
            guide.render(kind, app_guides.apc_no_model(loops.name(loops.active())), None)
            st.info(T("need_model"), icon=":material/arrow_back:")
            return
        if kind == "smith":
            smith_render(ctx)
            return
        if kind in MORE:
            MORE[kind](ctx)
            return
        if kind == "gainsched":
            gainsched_render(ctx)
            return
        if kind == "ff":
            ff_render(ctx)
            return
        other = [i for i in loops.ids() if i != loops.active()]
        if not other:
            guide.render(kind, app_guides.apc_need_loop(rec_a(ctx)), None)
            return
        names = {i: loops.name(i) for i in other}
        if ss.get(f"apc_{kind}_b") not in other:  # výchozí druhá smyčka = ta, kterou doporučení navrhuje
            pref = [it[2] for it in (recommend(ctx)) if it[0] == kind and it[2] in other]
            ss[f"apc_{kind}_b"] = pref[0] if pref else other[0]
        ws = workspace()
        with section(ws.side, T(f"apc_{kind}_b"), f"apc_{kind}_b_sec", icon=":material/link:"):
            bi = st.selectbox(T(f"apc_{kind}_b"), other, format_func=names.get, key=f"apc_{kind}_b",
                              help=T(f"h_apc_{kind}_b", a=loops.name(loops.active())))
        b = loops.loop_data(bi, ctx.fname)
        if b["model"] is None:
            with ws.main:
                guide.render(kind, [app_guides.apc_need_loop(rec_a(ctx))[0]] + app_guides.apc_no_model(b["name"], bi),
                             None)
            return
        (decouple_render if kind == "decouple" else override_render)(ctx, bi, b, ws)


def tuning_hint(ctx):
    """Jednořádkové upozornění v záložce Ladění, když by aktivní smyčce mohla pomoct struktura APC."""
    items = recommend(ctx)
    if items:
        r = st.columns([0.8, 0.2], vertical_alignment="center")
        r[0].caption(":material/lightbulb: " + T("g_tuning_hint", m=", ".join(dict.fromkeys(T("apc_" + k)
                                                                                         for k, _, _ in items))))
        r[1].button(T("g_open", m="APC"), key="g_tuning_apc", on_click=guide.goto,
                    kwargs=dict(tab="apc", kind=items[0][0], other=items[0][2]), type="tertiary")
