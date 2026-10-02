"""
Nápověda a průvodci společné pro web i desktop: obsah (texty v i18n) a kontrolní seznamy podle stavu projektu.

Průvodce záložky = oddíly „k čemu / postup“, „kterou metodu kdy“, „tipy z praxe“ (markdown) a kontrolní seznam.
Průvodce struktury APC = kdy použít, příklady, kontrolní seznam a implementace v PCS 7.
Položka seznamu: (stav, text, akce) – stav True (splněno) / False (chybí) / None (připomínka);
akce je identifikátor, který si frontend převede na tlačítko: "tab:<záložka>", "add_loop", nebo None.
Frontend sestaví z vlastního stavu `GuideState`; výpočty kontrol jsou zde, aby se obě verze nerozcházely.
"""
from dataclasses import dataclass, field

import numpy as np

from ..core import robustness
from ..i18n import T, TEXTS

TABS = ("data", "model", "tuning", "live", "apc", "project", "diag")


@dataclass
class GuideState:
    """Co průvodci potřebují vědět o aktivní smyčce a projektu (vše volitelné)."""
    loop_name: str = ""
    n_samples: int = 0
    Ts: float = 0.0
    c_pv: str = ""
    c_mv: str = ""
    norm: tuple = (0.0, 100.0, 0.0, 100.0)
    dq: dict = field(default_factory=dict)          # kvalita dat úseku (core.data_quality)
    model: tuple = None                             # (kód, parametry, poruchy)
    fit: float = None                               # shoda vybraného modelu [%]
    stale: bool = False                             # model patří k jiným datům / úseku / nastavení
    t_seg: float = 0.0                              # délka úseku identifikace [s]
    val_status: int = None                          # validace: 0 dobrá, 1 stejný úsek, 2 špatná, None neprovedená
    set1: tuple = (1.0, 100.0, 0.0)                 # Gain, TI, TD
    set2: tuple = (1.0, 100.0, 0.0)
    set2_ctrl: dict = None                          # sada 2 jako ctrl (pro Ms)
    n_loops: int = 1
    autosave: bool = None                           # web: automatické ukládání v prohlížeči
    report: bool = None                             # protokol vytvořen
    plant_meta: bool = None                         # vyplněná hlavička protokolu


def has(key):
    return key in TEXTS["en"]


def sections(key):
    """Oddíly průvodce záložky: [(nadpis, markdown)] – chybějící části se vynechají."""
    out = []
    for part in ("what", "choose", "tips"):
        k = f"tg_{key}_{part}"
        if has(k):
            out.append((T("tg_tab_" + part), T(k)))
    return out


def title(key):
    return T("tg_title", m=T("tg_name_" + key)) if has("tg_name_" + key) else T("tb_help")


def apc_sections(kind, impl=None):
    """Průvodce strukturou APC: [(nadpis, markdown)] – kdy použít, příklady, implementace v PCS 7."""
    out = [("", T(f"g_{kind}_when")), ("", T(f"g_{kind}_examples"))]
    if impl:
        out.append((T("g_impl"), impl))
    return out


def help_sections(version):
    """Obecná nápověda: postup, slovníček, o aplikaci."""
    return [(T("guide_title") if has("guide_title") else "", T("guide_body")), (T("gloss_title"), T("gloss_body")),
            (T("about_title"), T("about_body", v=version))]


# ---------------------------------------------------------------- kontroly
def _model(g, here=False):
    if g.model is not None:
        return True, T("g_chk_model_ok", n=g.loop_name, m=T("model_" + g.model[0])), None
    return False, T("g_chk_model", n=g.loop_name), None if here else "tab:model"


def _data(g):
    default_rng = tuple(g.norm) == (0.0, 100.0, 0.0, 100.0)
    return [(True, T("tgc_data_loaded", n=g.n_samples, ts=f"{g.Ts:.3g}"), None),
            (g.c_pv != g.c_mv, T("tgc_data_cols", pv=g.c_pv, mv=g.c_mv), None),
            (None if default_rng else True, T("tgc_data_ranges"), "tab:tuning")]


def _model_checks(g):
    out = []
    if g.dq:
        n = int(g.dq.get("n_steps") or 0)
        out.append((True if n >= 2 else (None if n == 1 else False), T("tgc_data_steps", n=n), None))
        lvl = g.dq.get("level", 2)
        out.append((True if lvl == 0 else (None if lvl == 1 else False), T("tgc_data_quality_" + str(lvl)), None))
    out.append(_model(g, here=True))
    if g.model is not None:
        if g.fit is not None:
            out.append((True if g.fit >= 80 else (None if g.fit >= 70 else False), T("tgc_model_fit", f=f"{g.fit:.1f}"),
                        None))
        if g.stale:
            out.append((False, T("tgc_model_stale"), None))
        code, p = g.model[0], g.model[1]
        if code in ("P1D", "P2D") and g.t_seg and p[1] > g.t_seg:
            out.append((None, T("tgc_model_long_T"), None))
        out.append((True if g.val_status == 0 else None, T("tgc_model_val"), None))
    return out


def _tuning(g):
    out = [_model(g)]
    if g.model is None or g.set2_ctrl is None:
        return out
    out.append((None if tuple(g.set1[:2]) == (1.0, 100.0) else True, T("tgc_tune_set1"), None))
    out.append((None, T("tgc_tune_block"), None))
    try:
        rb = robustness(g.model[0], list(g.model[1]), {k: v for k, v in g.set2_ctrl.items() if k not in ("FF", "FF_LL")})
        ms = rb["Ms"]
        ok = rb["stable"] and np.isfinite(ms)
        out.append((True if ok and ms <= 1.8 else (None if ok and ms <= 2.0 else False),
                    T("tgc_tune_ms", m=f"{ms:.2f}" if ok else "∞"), None))
    except Exception:
        pass
    out.append((None if tuple(g.set2) == tuple(g.set1) else True, T("tgc_tune_set2"), None))
    out.append((None, T("tgc_tune_verify"), "tab:live"))
    return out


def _live(g):
    out = [_model(g)]
    if g.model is not None:
        out += [(None, T("tgc_live_sets"), "tab:tuning"), (None, T("tgc_live_robust"), None)]
    return out


def _apc(g):
    return [_model(g), (True if g.n_loops > 1 else None, T("tgc_apc_loops", n=g.n_loops),
                        None if g.n_loops > 1 else "add_loop")]


def _project(g):
    out = [_model(g)]
    if g.autosave is not None:
        out.append((True if g.autosave else None, T("tgc_proj_autosave"), None))
    out.append((True if g.report else None, T("tgc_proj_report"), None))
    out.append((True if g.plant_meta else None, T("tgc_proj_meta"), None))
    return out


def _diag(g):
    return [_model(g)]


CHECKS = {"data": _data, "model": _model_checks, "tuning": _tuning, "live": _live, "apc": _apc,
          "project": _project, "diag": _diag}


def checks(key, g):
    """Kontrolní seznam záložky podle stavu g (prázdný při chybě – průvodce se vykreslí i tak)."""
    try:
        return CHECKS[key](g) if key in CHECKS else []
    except Exception:
        return []


def icon(ok):
    """Textová ikona stavu pro jednoduchá rozhraní."""
    return "✅" if ok else ("⬜" if ok is False else "ℹ️")
