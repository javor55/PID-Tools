"""
APC – rozvazbení 2×2: RGA, párování, decouplery (statické a lead-lag), simulace změn SP obou smyček.
"""
import numpy as np
import pandas as pd
import streamlit as st

from ....core.apc import rga_advice
from ....i18n import T
from ... import loops
from ...charts import mkfig, show, style, tr
from ...theme import C_MV, C_PV, C_SET2, C_SP
from ...widgets import num, seg
from . import guide
from ....app import guides as app_guides
from ....app.apc import decouple as adec
from ....app.apc.decouple import gain_eng
from .common import C_B, C_REF, active_model, clean, eng, lab, mimo_sim


# ---------------------------------------------------------------- rozvazbení 2×2
def _gain_eng(d_, src, dst):
    return gain_eng(d_, src, dst)


def decouple_render(ctx, bi, b):
    a = active_model(ctx)
    dz = adec.design(a, b)
    xab, xba, dab, dba = dz["xab"], dz["xba"], dz["dab"], dz["dba"]
    checks = app_guides.apc_decouple(a, b, loops.active(), bi, xab, xba)
    impl = T("g_impl_decouple") + "".join(
        "\n" + T("g_impl_dec_line", src=src["c_mv"], dst=dst["name"], g=f"{_gain_eng(d_, src, dst):.4g}",
                  lead=f"{d_['lead']:.3g}", lag=f"{d_['lag']:.3g}", dt=f"{d_['delay']:.3g}")
        for d_, src, dst in ((dab, b, a), (dba, a, b)) if d_)
    guide.render("decouple", checks, impl)
    if xab is None and xba is None:
        st.warning(T("dec_need_cross", a=a["name"], b=b["name"], mva=a["c_mv"], mvb=b["c_mv"]),
                   icon=":material/link_off:")
        return
    if xab is None or xba is None:
        st.caption(T("dec_one_way", x=a["name"] if xab is None else b["name"],
                     mv=b["c_mv"] if xab is None else a["c_mv"]))

    # ---- RGA
    lam = dz["lam"]
    with st.container(border=True):
        r1, r2 = st.columns([1, 3], vertical_alignment="center")
        r1.metric("RGA λ₁₁", "∞" if not np.isfinite(lam) else f"{lam:.2f}", help=T("h_rga"))
        r2.markdown(T(rga_advice(lam), a=a["name"], b=b["name"], mva=a["c_mv"], mvb=b["c_mv"]))

    # ---- decouplery a scénář
    c1, c2, c3 = st.columns([1.4, 1, 1], vertical_alignment="bottom")
    dtype = seg(c1, T("dec_type"), ["static", "dyn"], "dyn", "apc_dec_type", format_func=lambda x: T("dec_" + x),
                help=T("h_dec_type")) or "dyn"
    amp_a = num(T("dec_step", n=a["name"]), "apc_dec_spa", 5.0, c2, format="%.4g", help=T("h_dec_step"))
    amp_b = num(T("dec_step", n=b["name"]), "apc_dec_spb", 5.0, c3, format="%.4g", help=T("h_dec_step"))
    ctrl_a, ctrl_b = clean(a["ctrl"]), clean(b["ctrl"])
    runs = adec.simulate(dz, ctrl_a, ctrl_b, amp_a, amp_b, mimo_sim)
    EA, EB = eng(a["pv_rng"]), eng(b["pv_rng"])
    MA, MB = eng(a["mv_rng"]), eng(b["mv_rng"])
    tt, o_ref = runs["none"]
    _, o = runs[dtype]
    f = mkfig(3, [0.36, 0.36, 0.28])
    f.add_trace(tr(tt, EA(o["SP_A"]), f"SP {a['name']}", C_SP, 1.3, "dash", "hv"), 1, 1)
    f.add_trace(tr(tt, EA(o_ref["PV_A"]), T("dec_without"), C_REF, 1.3, "dot", group="ref"), 1, 1)
    f.add_trace(tr(tt, EA(o["PV_A"]), f"PV {a['name']}", C_PV, 2.0), 1, 1)
    f.add_trace(tr(tt, EB(o["SP_B"]), f"SP {b['name']}", C_SP, 1.3, "dash", "hv", show=False), 2, 1)
    f.add_trace(tr(tt, EB(o_ref["PV_B"]), T("dec_without"), C_REF, 1.3, "dot", show=False, group="ref"), 2, 1)
    f.add_trace(tr(tt, EB(o["PV_B"]), f"PV {b['name']}", C_B, 2.0), 2, 1)
    f.add_trace(tr(tt, MA(o["MV_A"]), f"MV {a['name']}", C_MV, 1.6), 3, 1)
    f.add_trace(tr(tt, MB(o["MV_B"]), f"MV {b['name']}", C_SET2, 1.6), 3, 1)
    show(style(f, ctx.H + 120, [lab(a["name"], a["u_pv"]), lab(b["name"], b["u_pv"]), "MV"], ctx.lab_t,
               rev="apc_dec"), key="chart_apc_dec", fname="decoupling", report=T("apc_decouple"))
    st.caption(T("dec_sim_help"))

    rows = [{T("dec_variant"): T("dec_" + v_), f"IAE {a['name']}": round(ia, 4), f"IAE {b['name']}": round(ib, 4)}
            for v_, ia, ib in adec.iae_table(runs, a, b)]
    st.dataframe(pd.DataFrame(rows), hide_index=True)

    # ---- parametry pro implementaci (dopředná vazba z MV druhé smyčky)
    prm = [{T("dec_path"): f"{src} → MV {dst}", T("dec_gain_pct"): round(g, 4), T("dec_gain_eng"): round(ge, 4),
            "Lead [s]": round(ld, 3), "Lag [s]": round(lg, 3), T("ff_delay"): round(dl, 3)}
           for src, dst, g, ge, ld, lg, dl in adec.params(dz, a, b)]
    st.markdown(f"**{T('dec_params')}**")
    st.dataframe(pd.DataFrame(prm), hide_index=True)
    st.caption(T("dec_params_help"))
