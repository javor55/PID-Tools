"""
Nápověda v desktopu: samostatné okno (nepřekáží, když už postup znáte) s průvodcem aktuální záložky – postup,
volba metody, tipy, kontrolní seznam podle stavu projektu – a s obecnou nápovědou a slovníčkem. Obsah i kontroly
jsou sdílené s webem (pidtools.app.guides, texty v i18n).
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QTextBrowser, QVBoxLayout

from .. import __version__
from ..app import guides
from ..i18n import T


def guide_state(win):
    """GuideState z desktopového stavu."""
    s = win.state
    if not s.has_data:
        return guides.GuideState(loop_name=win.project.names()[win.project.active])
    q = s.quality() or {}
    m = s.model
    fit = s.fit["res"][m[0]]["fit"] if m is not None else None
    ts, _, _, _ = s.segment()
    return guides.GuideState(
        loop_name=win.project.names()[win.project.active], n_samples=len(s.t), Ts=s.grid.Ts, c_pv=str(s.c_pv),
        c_mv=str(s.c_mv), norm=s.norm, dq=q, model=m, fit=fit, stale=s.stale, t_seg=float(ts[-1]) if len(ts) else 0.0,
        val_status=getattr(s, "val_status", None),
        set1=tuple(float(s.get(f"set1_{k}")) for k in ("gain", "ti", "td")),
        set2=tuple(float(s.get(f"set2_{k}")) for k in ("gain", "ti", "td")),
        set2_ctrl=s.set_ctrl(2) if m is not None else None, n_loops=len(win.project.loops),
        report=None, plant_meta=bool(s.get("rep_plant")))


def _qt_md(md):
    """Úprava markdownu pro Qt: před tabulkou musí být prázdný řádek (web ho nevyžaduje)."""
    out = []
    for line in md.split("\n"):
        if line.lstrip().startswith("|") and out and out[-1].strip() and not out[-1].lstrip().startswith("|"):
            out.append("")
        out.append(line)
    return "\n".join(out)


def tab_markdown(key, state, extra=()):
    """Průvodce záložky jako markdown; kontroly s odkazy „action:…“ (okno je převede na akce)."""
    parts = [f"# {guides.title(key)}"]
    for head, body in guides.sections(key):
        parts.append(f"### {head}\n\n{body}")
    for head, body in extra:
        parts.append((f"### {head}\n\n" if head else "") + body)
    chk = guides.checks(key, state)
    if chk:
        parts.append(checklist_markdown(chk))
    return "\n\n".join(parts)


def checklist_markdown(chk, title=None):
    """Kontrolní seznam [(stav, text, akce)] jako markdown s odkazy action:<akce>."""
    lines = [f"### {title or T('g_checklist')}", ""]
    for ok, txt, act in chk:
        link = f" — [{T('dk_help_go')}](action:{act})" if act and ok is not True else ""
        lines.append(f"- {guides.icon(ok)} {txt}{link}")
    return "\n".join(lines)


def general_markdown():
    return "\n\n".join((f"## {h}\n\n{b}" if h else b) for h, b in guides.help_sections(__version__))


class HelpWindow(QDialog):
    """Nemodální okno nápovědy; odkazy action:<akce> předá hlavnímu oknu."""

    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.setWindowTitle(T("tb_help"))
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.resize(720, 760)
        lay = QVBoxLayout(self)
        self.view = QTextBrowser()
        self.view.setOpenLinks(False)
        self.view.anchorClicked.connect(self._link)
        lay.addWidget(self.view)

    def show_markdown(self, md, title=None):
        self.setWindowTitle(title or T("tb_help"))
        self.view.setMarkdown(_qt_md(md))
        self.show()
        self.raise_()
        self.activateWindow()

    def _link(self, url):
        u = url.toString()
        if u.startswith("action:"):
            self.win.do_action(u[len("action:"):])
            self.win.show_guide()        # obnovit kontroly po akci
        elif u.startswith("http"):
            from PySide6.QtGui import QDesktopServices
            QDesktopServices.openUrl(url)
