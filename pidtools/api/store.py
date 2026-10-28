"""
Pracovní prostory API: projekt (app.workspace.loops.Project – smyčky nad jedním souborem, aktivní smyčka je
Workspace) pod náhodným ID, s vypršením po nečinnosti a limitem počtu. V týmovém režimu (M26) patří prostor
uživateli (`owner`): cizí ID vypadá jako neexistující a počet prostorů na uživatele je omezený (nový prostor uvolní
jeho nejdéle nepoužitý – zapomenuté záložky prohlížeče uživatele nezablokují).
"""
import secrets
import threading
import time

from ..app.workspace.loops import Project


class WorkspaceStore:
    def __init__(self, ttl_s=3600.0, max_count=20):
        self.ttl_s, self.max_count = float(ttl_s), int(max_count)
        self._d = {}                         # id → [Project, poslední přístup, vlastník]
        self._lock = threading.Lock()

    def _sweep(self, now):
        for k in [k for k, v in self._d.items() if now - v[1] > self.ttl_s]:
            del self._d[k]

    def create(self, owner=None, max_per_owner=None):
        """
        Nový prázdný projekt; při plném úložišti se uvolní nejdéle nepoužitý. Vrací (id, Project).
        S vlastníkem a max_per_owner platí limit na uživatele: uvolní se jeho nejdéle nepoužitý prostor.
        """
        now = time.time()
        with self._lock:
            self._sweep(now)
            if owner is not None and max_per_owner is not None:
                mine = sorted((v[1], k) for k, v in self._d.items() if v[2] == owner)
                for _, k in mine[:max(0, len(mine) - int(max_per_owner) + 1)]:
                    del self._d[k]
            while len(self._d) >= self.max_count:
                del self._d[min(self._d, key=lambda k: self._d[k][1])]
            wid = secrets.token_urlsafe(9)
            proj = Project()
            self._d[wid] = [proj, now, owner]
            return wid, proj

    def get(self, wid, owner=None):
        """Projekt podle ID (obnoví čas přístupu), jinak KeyError; s vlastníkem i cizí prostor je KeyError."""
        now = time.time()
        with self._lock:
            self._sweep(now)
            item = self._d[wid]
            if owner is not None and item[2] != owner:
                raise KeyError(wid)
            item[1] = now
            return item[0]

    def delete(self, wid, owner=None):
        with self._lock:
            if wid in self._d and owner is not None and self._d[wid][2] != owner:
                return False
            return self._d.pop(wid, None) is not None

    def count(self, owner):
        """Počet prostorů uživatele."""
        return sum(v[2] == owner for v in list(self._d.values()))

    def __len__(self):
        return len(self._d)
