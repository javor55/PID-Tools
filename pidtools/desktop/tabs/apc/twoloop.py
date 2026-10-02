"""APC › struktury dvou smyček (rozvazbení, override): výběr druhé smyčky projektu."""
from ....i18n import T
from ... import widgets as w
from .common import Panel


class TwoLoopPanel(Panel):
    """Panel s výběrem druhé smyčky; potomek implementuje update(a, b)."""

    kind = ""

    def __init__(self, win, intro_key):
        super().__init__(win, intro_key)
        self.other = w.combo([])
        self.other.currentIndexChanged.connect(self._changed)
        self.left.addWidget(w.group(T(f"apc_{self.kind}_b"), w.form([("", self.other)])))
        self.need = w.note("")
        self.left.addWidget(self.need)

    def refresh(self):
        s = self.s
        if s.model is None:
            return
        others = self.win.project.others(include_without_model=True)
        self._busy = True
        cur = self.other.currentData()
        self.other.clear()
        for i, rec in others:
            self.other.addItem(rec["name"], i)
        if cur is not None and self.other.findData(cur) >= 0:
            self.other.setCurrentIndex(self.other.findData(cur))
        self._busy = False
        self.need.setText("" if others else T("apc_need_loop"))
        self._changed()

    def pair(self):
        """(a, b) – aktivní smyčka a vybraná druhá smyčka jako záznamy, nebo None."""
        i = self.other.currentData()
        if i is None:
            return None
        b = dict(self.win.project.others(include_without_model=True))[i]
        a = dict(self.s.report_record(), name=self.win.project.names()[self.win.project.active])
        return a, b

    def _changed(self, *_):
        if self._busy:
            return
        p = self.pair()
        if p is None:
            return
        a, b = p
        if b["model"] is None:
            self.need.setText(T("g_chk_model", n=b["name"]))
            return
        self.need.setText("")
        self.update_pair(a, b)
