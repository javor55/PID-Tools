"""Pracovní prostory API: Workspace pod náhodným ID, s vypršením po nečinnosti a limitem počtu."""
import secrets
import threading
import time

from ..app.workspace import Workspace


class WorkspaceStore:
    def __init__(self, ttl_s=3600.0, max_count=20):
        self.ttl_s, self.max_count = float(ttl_s), int(max_count)
        self._d = {}                         # id → [Workspace, poslední přístup]
        self._lock = threading.Lock()

    def _sweep(self, now):
        for k in [k for k, (_, t) in self._d.items() if now - t > self.ttl_s]:
            del self._d[k]

    def create(self):
        """Nový prázdný prostor; při plném úložišti se uvolní nejdéle nepoužitý. Vrací (id, Workspace)."""
        now = time.time()
        with self._lock:
            self._sweep(now)
            while len(self._d) >= self.max_count:
                del self._d[min(self._d, key=lambda k: self._d[k][1])]
            wid = secrets.token_urlsafe(9)
            ws = Workspace()
            self._d[wid] = [ws, now]
            return wid, ws

    def get(self, wid):
        """Prostor podle ID (obnoví čas přístupu), jinak KeyError."""
        now = time.time()
        with self._lock:
            self._sweep(now)
            item = self._d[wid]
            item[1] = now
            return item[0]

    def delete(self, wid):
        with self._lock:
            return self._d.pop(wid, None) is not None

    def __len__(self):
        return len(self._d)
