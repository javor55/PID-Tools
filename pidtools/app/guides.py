"""
Nápověda a průvodci společné pro web i desktop: obsah (texty v i18n) a kontrolní seznamy podle stavu projektu.

Průvodce záložky = oddíly „k čemu / postup“, „kterou metodu kdy“, „tipy z praxe“ (markdown) a kontrolní seznam.
Průvodce struktury APC = kdy použít, příklady, kontrolní seznam a implementace v PCS 7.
Položka seznamu: (stav, text, akce) – stav True (splněno) / False (chybí) / None (připomínka);
akce je identifikátor, který si frontend převede na tlačítko: "tab:<záložka>", "add_loop", nebo None.
Frontend sestaví z vlastního stavu `GuideState`; výpočty kontrol jsou zde, aby se obě verze nerozcházely.
"""
import re
from dataclasses import dataclass, field

import numpy as np

from ..core import robustness
from ..i18n import T, TEXTS

TABS = ("data", "model", "tuning", "live", "apc", "project", "diag", "audit")


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
            (None if default_rng else True, T("tgc_data_ranges"), Act("tab:tuning", "set-pv_hi", T("tgb_ranges")))]


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
    out.append((None if tuple(g.set1[:2]) == (1.0, 100.0) else True, T("tgc_tune_set1"),
                Act("tab:tuning", "set1-gain", T("tgb_set1"))))
    out.append((None, T("tgc_tune_block"), Act("tab:tuning", "set-pv_hi", T("tgb_block"))))
    try:
        rb = robustness(g.model[0], list(g.model[1]), {k: v for k, v in g.set2_ctrl.items() if k not in ("FF", "FF_LL")})
        ms = rb["Ms"]
        ok = rb["stable"] and np.isfinite(ms)
        out.append((True if ok and ms <= 1.8 else (None if ok and ms <= 2.0 else False),
                    T("tgc_tune_ms", m=f"{ms:.2f}" if ok else "∞"), Act("tab:tuning", "method", T("tgb_method"))))
    except Exception:
        pass
    out.append((None if tuple(g.set2) == tuple(g.set1) else True, T("tgc_tune_set2"),
                Act("tab:tuning", "calc", T("tgb_calc"))))
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
    out.append((True if g.report else None, T("tgc_proj_report"), None))
    out.append((True if g.plant_meta else None, T("tgc_proj_meta"), None))
    return out


def _diag(g):
    return [_model(g)]


# ---------------------------------------------------------------- kontroly struktur APC
# Akce navíc: "loop:<id>:<záložka>" (přepnout smyčku a záložku). a / b = záznamy smyček (name, model, c_mv, c_sp …).
def _ok_model(name, model):
    return True, T("g_chk_model_ok", n=name, m=T("model_" + model[0])), None


def apc_no_model(name, loop=None):
    """Smyčka bez modelu – jediná položka seznamu (loop = id smyčky pro tlačítko, None = aktivní)."""
    return [(False, T("g_chk_model", n=name), "tab:model" if loop is None else f"loop:{loop}:model")]


def apc_need_loop(a):
    return [_ok_model(a["name"], a["model"]), (False, T("apc_need_loop"), "add_loop")]


def apc_cascade(a, others):
    """others: [(id, záznam)] ostatních smyček."""
    if a["model"] is None:
        return apc_no_model(a["name"])
    out = [_ok_model(a["name"], a["model"])]
    with_model = [b["name"] for _, b in others if b["model"] is not None]
    out.append((True, T("g_chk_cas_inner", n=", ".join(with_model)), None) if with_model
               else (None, T("g_chk_cas_noinner"), "add_loop"))
    inner = [b["name"] for _, b in others if b["c_sp"] not in (None, "—") and b["c_sp"] == a["c_mv"]]
    out.append((True, T("g_chk_cas_mvsp_ok", mv=a["c_mv"], n=", ".join(inner)), None) if inner
               else (None, T("g_chk_cas_mvsp", mv=a["c_mv"]), None))
    out.append((None, T("g_chk_cas_speed"), None))
    return out


def apc_override(a, b, bi):
    same = b["c_mv"] == a["c_mv"]
    return [_ok_model(a["name"], a["model"]), _ok_model(b["name"], b["model"]),
            (same, T("g_chk_same_mv", a=a["name"], b=b["name"], mv=a["c_mv"]), f"loop:{bi}:data"),
            (None, T("g_chk_ov_dir", b=b["name"]), None), (None, T("g_chk_tuned"), None)]


def apc_decouple(a, b, ai, bi, xab, xba):
    return [_ok_model(a["name"], a["model"]), _ok_model(b["name"], b["model"]),
            (xab is not None, T("g_chk_cross", n=a["name"], mv=b["c_mv"]), f"loop:{ai}:data"),
            (xba is not None, T("g_chk_cross", n=b["name"], mv=a["c_mv"]), f"loop:{bi}:data"),
            (None, T("g_chk_tuned"), None)]


def apc_ff(a, names, des, p):
    """names: názvy poruch, des: návrhy feedforward.design, p: parametry modelu (zpoždění = p[-1])."""
    if not names:
        return [_ok_model(a["name"], a["model"]), (False, T("g_chk_ff_dist"), "tab:data")]
    slow = [n for n, pdm, d in zip(names, a["model"][2], des) if d["use"] and pdm[2] < p[-1]]
    return [_ok_model(a["name"], a["model"]), (True, T("g_chk_ff_dist_ok", d=", ".join(names)), None),
            (any(d["use"] for d in des), T("g_chk_ff_on"), None),
            ((None if slow else True), T("g_chk_ff_fast", d=", ".join(slow)) if slow else T("g_chk_ff_fast_ok"), None),
            (None, T("g_chk_ff_indep"), None), (None, T("g_chk_ff_commission"), None)]


def apc_smith(a, integ, ratio, th_lag):
    return [_ok_model(a["name"], a["model"]), (not integ, T("g_chk_sm_integ"), None),
            (True if ratio >= 0.5 else None, T("g_chk_sm_ratio", r=f"{ratio:.2f}"), None),
            (True if th_lag <= 3 else None, T("g_chk_sm_th3", r=f"{th_lag:.2f}"), None),
            (None, T("g_chk_sm_model"), None)]


def apc_gainsched(a, integ, spread=None, pts=(), stale=False, issues=()):
    if integ:
        return [_ok_model(a["name"], a["model"]), (False, T("g_chk_gs_integ"), None)]
    fits_ok = all(q["fit"] >= 70 for q in pts) if pts else None
    return [_ok_model(a["name"], a["model"]),
            (True if spread and spread > 1.5 else None,
             T("g_chk_gs_nl", s=f"{spread:.1f}") if spread else T("g_chk_gs_nl_unknown"), None),
            (bool(pts) and not stale, T("g_chk_gs_pts"), None),
            (fits_ok if pts else None, T("g_chk_gs_fit"), None),
            (not issues if pts else None, T("g_chk_gs_mono"), None),
            (None, T("g_chk_gs_x"), None)]


def apc_gs_er(a, ms_k):
    ok = bool(np.isfinite(ms_k) and ms_k <= 2.0)
    return [_ok_model(a["name"], a["model"]),
            (ok, T("g_chk_gser_ms", m="∞" if not np.isfinite(ms_k) else f"{ms_k:.2f}"), None),
            (None, T("g_chk_gser_noise"), None), (None, T("g_chk_gser_sat"), None),
            (None, T("g_chk_gser_bumpless"), None)]


def _audit(g):
    return [(True, T("tgc_data_loaded", n=g.n_samples, ts=f"{g.Ts:.3g}"), None)] if g.n_samples else []


def apc_actuators(a, kind):
    """Split range / VPC: model smyčky, model druhého akčního členu (zadaný), sada 2, ladění v provozu."""
    return [_ok_model(a["name"], a["model"]), (None, T(f"g_chk_{kind}_model"), None),
            (None, T(f"g_chk_{kind}_tune"), None), (None, T("g_chk_tuned"), None)]


def apc_ratio(a, n_other):
    return [_ok_model(a["name"], a["model"]),
            (True if n_other else None, T("g_chk_ratio_air"), None if n_other else "add_loop"),
            (None, T("g_chk_ratio_R"), None), (None, T("g_chk_ratio_safety"), None)]


def apc_rga(a, n_loops, n_cross):
    return [_ok_model(a["name"], a["model"]),
            (n_loops > 1, T("tgc_apc_loops", n=n_loops), None if n_loops > 1 else "add_loop"),
            (True if n_cross else False, T("g_chk_rga_cross", n=n_cross), None if n_cross else "tab:data")]


CHECKS = {"audit": _audit, "data": _data, "model": _model_checks, "tuning": _tuning, "live": _live, "apc": _apc,
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


# ================================================================ průvodce záložky jako data (UI-nezávislé)
# Stejný obsah pro API (GET /workspaces/{wid}/guide/{tab}), desktop i web: postup, kontrolní seznam podle stavu
# projektu, tabulky „která volba kdy“ (markdown) a slovníček. Texty jsou v i18n (tg_*, gloss_body).
GUIDE_TABS = ("data", "model", "tuning", "apc", "live", "diag", "loops", "project")
_KEY = {"loops": "audit"}                      # klíč textů průvodce záložky (tg_<klíč>_*)
_TAB_BUTTON = {"model": "g_btn_model", "data": "tgb_data", "tuning": "tgb_tuning", "live": "tgb_live"}


class Act(str):
    """Akce kontroly („tab:<záložka>“ …) s volitelným cílem na záložce (data-testid prvku) a popiskem tlačítka."""
    target = None
    label = None

    def __new__(cls, action, target=None, label=None):
        o = super().__new__(cls, action)
        o.target, o.label = target, label
        return o


def tab_key(tab):
    """Klíč textů průvodce pro záložku API (loops → audit)."""
    return _KEY.get(tab, tab)


def action_info(a):
    """Akce kontroly → {"tab", "target", "label"} nebo None. add_loop → záložka Data, cíl „add-loop“."""
    if not a:
        return None
    tab, target, label = None, getattr(a, "target", None), getattr(a, "label", None)
    if a == "add_loop":
        tab, target, label = "data", target or "add-loop", label or T("loop_add")
    elif a.startswith("tab:"):
        tab = a[4:]
    elif a.startswith("loop:"):
        _, lid, tab = a.split(":", 2)
        target = target or f"loop:{lid}"
    if not tab:
        return None
    if label is None:
        label = T(_TAB_BUTTON[tab]) if tab in _TAB_BUTTON else T("dk_help_go")
    return {"tab": tab, "target": target, "label": label}


def check_status(ok):
    """True → „ok“ (splněno), False → „warn“ (vyžaduje pozornost), None → „todo“ (ještě neprovedeno / připomínka)."""
    return "ok" if ok is True else ("warn" if ok is False else "todo")


def _strip_md(s):
    return s.replace("**", "").replace("`", "").strip()


def parse_steps(md):
    """Číslované (nebo odrážkové) kroky z markdownu → [{"title", "text"}]; název = tučný začátek / první věta."""
    items = re.findall(r"^\s*\d+\.\s+(.+)$", md, flags=re.M) or re.findall(r"^\s*[-*]\s+(.+)$", md, flags=re.M)
    out = []
    for it in items:
        m = re.match(r"\*\*(.+?)\*\*\s*[:–-]\s*(.+)$", it)               # „**Název** – text“
        if not m:
            m = re.match(r"(.{4,110}?)(?:(?<=[^\W\d_]{4})(?:\.\s+(?=[^\W\d_a-zěščřžýáíéúůďťň])|:\s+)|\s+[–-]\s+)(.+)$", it)
        title, text = (m.group(1), m.group(2)) if m else (it, "")
        out.append({"title": _strip_md(title).rstrip(".:"), "text": text})
    return out


def intro_of(md):
    """Úvod („K čemu: …“) – text před „Postup“ / prvním číslovaným krokem."""
    m = re.search(r"^\s*(\*\*(?:Postup|Procedure)\*\*|\d+\.\s)", md, flags=re.M)
    return (md[:m.start()] if m else md).strip()


def parse_sections(md, default_title=""):
    """Markdown „která volba kdy“ → [{"title", "md"}]: oddíl začíná řádkem jen s **tučným** nadpisem (nebo je jediný)."""
    out, cur = [], None
    for line in md.split("\n"):
        m = re.fullmatch(r"\s*\*\*([^*]+)\*\*\s*", line)
        if m:
            cur = {"title": m.group(1).strip(), "lines": []}
            out.append(cur)
            continue
        if cur is None:
            cur = {"title": default_title, "lines": []}
            out.append(cur)
        cur["lines"].append(line)
    return [{"title": s["title"], "md": "\n".join(s["lines"]).strip()} for s in out if "".join(s["lines"]).strip()]


def parse_glossary(md):
    """Slovníček „- **pojem** – vysvětlení“ → [{"term", "text"}]."""
    out = []
    for it in re.findall(r"^\s*[-*]\s+(.+)$", md, flags=re.M):
        m = re.match(r"\*\*(.+?)\*\*\s*[–-]\s*(.+)$", it)
        out.append({"term": m.group(1), "text": m.group(2)} if m else {"term": "", "text": it})
    return out


def state_of(proj):
    """GuideState z projektu (app.workspace.loops.Project): vše počítané živě ze stavu aktivní smyčky."""
    s = proj.state
    names = proj.names()
    name, n_loops = str(names[proj.active]), len(names)
    if not s.has_data:
        return GuideState(loop_name=name, n_loops=n_loops)
    q = s.quality() or {}
    m = s.model
    fit = None
    if m is not None and s.fit:
        fit = (s.fit.get("res", {}).get(m[0]) or {}).get("fit")
    ts, _, _, _ = s.segment()
    set2_ctrl = None
    if m is not None:
        try:
            set2_ctrl = s.set_ctrl(2)
        except Exception:
            set2_ctrl = None
    return GuideState(
        loop_name=name, n_samples=len(s.t), Ts=float(s.grid.Ts), c_pv=str(s.c_pv), c_mv=str(s.c_mv), norm=s.norm,
        dq=q, model=m, fit=fit, stale=bool(s.stale), t_seg=float(ts[-1]) if len(ts) else 0.0, val_status=s.val_status,
        set1=tuple(float(s.get(f"set1_{k}", d)) for k, d in (("gain", 1.0), ("ti", 100.0), ("td", 0.0))),
        set2=tuple(float(s.get(f"set2_{k}", d)) for k, d in (("gain", 1.0), ("ti", 100.0), ("td", 0.0))),
        set2_ctrl=set2_ctrl, n_loops=n_loops, report=None, plant_meta=bool(s.get("rep_plant")))


def guide(tab, g):
    """
    Průvodce záložky jako data: {"tab", "title", "intro", "steps", "checklist", "tables", "tips", "glossary"}.
    checklist: [{"ok": "ok"|"warn"|"todo", "text", "action": {"tab", "target", "label"} | None}] – podle stavu `g`.
    """
    key = tab_key(tab)
    what = T(f"tg_{key}_what") if has(f"tg_{key}_what") else ""
    choose = T(f"tg_{key}_choose") if has(f"tg_{key}_choose") else ""
    tips = T(f"tg_{key}_tips") if has(f"tg_{key}_tips") else ""
    chk = checks(key, g) if g.n_samples else []
    if not g.n_samples and key != "project":
        chk = [(False, T("ui_no_data"), Act("tab:data"))]
    return {
        "tab": tab, "title": title(key), "intro": intro_of(what), "steps": parse_steps(what),
        "checklist": [{"ok": check_status(ok), "text": text, "action": action_info(act)} for ok, text, act in chk],
        "tables": parse_sections(choose, T("tg_tab_choose")) if choose else [], "tips": tips,
        "glossary": parse_glossary(T("gloss_body")),
    }
