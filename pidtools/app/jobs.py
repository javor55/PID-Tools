"""
Dlouhé výpočty jako úlohy (identifikace, optimalizace ladění, nejistota, APC): běží v samostatném procesu,
hlásí průběh, dají se zrušit a mají časový limit; výsledek se uloží do cache podle klíče vstupů.

Každá úloha má vlastní proces (multiprocessing, „spawn“ – stejně na Windows i Linuxu): běžící výpočet v numpy /
scipy nejde přerušit jinak než ukončením procesu, a to musí být okamžité (zrušení do 1 s). Funkce úlohy musí být
importovatelná (definovaná na úrovni modulu) a její argumenty i výsledek přenositelné (pickle). Přijímá-li funkce
argument `progress`, dostane funkci progress(podíl 0–1, text="").

    jm = JobManager(max_parallel=2)
    jid = jm.submit(mdl.identify_all, ts, pv, mv, Ts, d, s, key=("ident", ...), timeout=600)
    jm.status(jid)      # {"state": "running", "progress": 0.4, "text": "P1D", ...}
    jm.result(jid, timeout=60)
    jm.cancel(jid)

Bez závislosti na UI; použije ho API (docs/cs/milniky.md, M5 / M6).
"""
import inspect
import itertools
import multiprocessing as mp
import pickle
import queue
import sys
import threading
import time
import traceback
import types
from collections import OrderedDict
from contextlib import contextmanager

STATES = ("queued", "running", "done", "error", "cancelled", "timeout")
FINAL = ("done", "error", "cancelled", "timeout")


class ResultCache:
    """Výsledky podle klíče (LRU) s limitem velikosti (odhad z délky pickle)."""

    def __init__(self, max_bytes=256 * 2 ** 20):
        self.max_bytes = int(max_bytes)
        self._d = OrderedDict()             # klíč → (výsledek, velikost)
        self._size = 0
        self._lock = threading.Lock()
        self.hits = self.misses = 0

    def get(self, key, default=None):
        with self._lock:
            if key in self._d:
                self._d.move_to_end(key)
                self.hits += 1
                return self._d[key][0]
            self.misses += 1
            return default

    def __contains__(self, key):
        with self._lock:
            return key in self._d

    def put(self, key, value):
        try:
            size = len(pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL))
        except Exception:
            return False
        if size > self.max_bytes:
            return False
        with self._lock:
            if key in self._d:
                self._size -= self._d.pop(key)[1]
            self._d[key] = (value, size)
            self._size += size
            while self._size > self.max_bytes and self._d:
                _, (_, s) = self._d.popitem(last=False)
                self._size -= s
        return True

    def clear(self):
        with self._lock:
            self._d.clear()
            self._size = 0

    @property
    def size(self):
        return self._size

    def __len__(self):
        return len(self._d)


@contextmanager
def _bare_main():
    """
    Při startu procesu „spawn“ by se v něm znovu spustil hlavní skript rodiče (sys.modules["__main__"]) – např.
    aplikace Streamlit v testech nebo spouštěcí skript. Funkce úloh se importují ze svých modulů, hlavní skript
    proces nepotřebuje: po dobu startu se nahradí prázdným modulem.
    """
    main = sys.modules.get("__main__")
    sys.modules["__main__"] = types.ModuleType("__main__")
    try:
        yield
    finally:
        if main is not None:
            sys.modules["__main__"] = main


def _wants_progress(fn):
    try:
        return "progress" in inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return False


def _worker(fn, args, kwargs, q):
    """Tělo procesu úlohy: průběh a výsledek posílá frontou („p“, podíl, text) / („ok“, výsledek) / („err“, text)."""
    try:
        if _wants_progress(fn):
            def progress(frac, text=""):
                q.put(("p", float(frac), str(text)))
            kwargs = dict(kwargs, progress=progress)
        q.put(("ok", fn(*args, **kwargs)))
    except BaseException as ex:          # noqa: BLE001 – chyba se předá volajícímu, proces končí
        q.put(("err", f"{type(ex).__name__}: {ex}", traceback.format_exc()))


class Job:
    def __init__(self, jid, fn, args, kwargs, key, timeout):
        self.id, self.fn, self.args, self.kwargs, self.key, self.timeout = jid, fn, args, kwargs, key, timeout
        self.state, self.progress, self.text = "queued", 0.0, ""
        self.result = self.error = self.trace = None
        self.cached = False
        self.created, self.started, self.finished = time.time(), None, None
        self.proc = self.q = None
        self.done = threading.Event()

    def info(self):
        return dict(id=self.id, state=self.state, progress=self.progress, text=self.text, error=self.error,
                    cached=self.cached, created=self.created, started=self.started, finished=self.finished)


class JobManager:
    """
    Fronta úloh: nejvýš max_parallel současně běžících procesů, ostatní čekají. Hotové úlohy se drží keep_s sekund
    (pak se zapomenou, výsledek zůstává v cache).
    """

    def __init__(self, max_parallel=2, cache=None, keep_s=3600.0, poll_s=0.05):
        self.max_parallel = max(1, int(max_parallel))
        self.cache = cache if cache is not None else ResultCache()
        self.keep_s, self.poll_s = float(keep_s), float(poll_s)
        self._ctx = mp.get_context("spawn")
        self._jobs = OrderedDict()
        self._lock = threading.RLock()
        self._ids = itertools.count(1)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, name="pidtools-jobs", daemon=True)
        self._thread.start()

    # ---- veřejné rozhraní
    def submit(self, fn, *args, key=None, timeout=None, **kwargs):
        """Nová úloha; s klíčem v cache je hotová hned (cached=True). Vrací ID úlohy."""
        jid = f"j{next(self._ids)}"
        job = Job(jid, fn, args, kwargs, key, timeout)
        if key is not None and key in self.cache:
            job.result, job.cached = self.cache.get(key), True
            self._finish(job, "done", progress=1.0)
        with self._lock:
            self._jobs[jid] = job
        return jid

    def status(self, jid):
        return self._get(jid).info()

    def result(self, jid, timeout=None):
        """Výsledek hotové úlohy (čeká nejvýš timeout s); jinak RuntimeError se stavem / chybou úlohy."""
        job = self._get(jid)
        job.done.wait(timeout)
        if job.state != "done":
            raise RuntimeError(job.error or job.state)
        return job.result

    def cancel(self, jid):
        """Zrušit čekající nebo běžící úlohu (běžící proces se ukončí). Vrací True, když se úloha zrušila."""
        job = self._get(jid)
        with self._lock:
            if job.state in FINAL:
                return False
            self._kill(job)
            self._finish(job, "cancelled")
        return True

    def jobs(self):
        with self._lock:
            return [j.info() for j in self._jobs.values()]

    def shutdown(self):
        self._stop.set()
        with self._lock:
            for j in self._jobs.values():
                if j.state not in FINAL:
                    self._kill(j)
                    self._finish(j, "cancelled")
        self._thread.join(2)

    # ---- vnitřek
    def _get(self, jid):
        with self._lock:
            if jid not in self._jobs:
                raise KeyError(jid)
            return self._jobs[jid]

    def _finish(self, job, state, progress=None, error=None):
        job.state = state
        job.finished = time.time()
        if progress is not None:
            job.progress = progress
        if error is not None:
            job.error = error
        job.done.set()

    def _kill(self, job):
        if job.proc is not None and job.proc.is_alive():
            job.proc.terminate()
            job.proc.join(1.0)
            if job.proc.is_alive():
                job.proc.kill()

    def _start(self, job):
        job.q = self._ctx.Queue()
        job.proc = self._ctx.Process(target=_worker, args=(job.fn, job.args, job.kwargs, job.q), daemon=True)
        job.state, job.started = "running", time.time()
        with _bare_main():
            job.proc.start()

    def _drain(self, job):
        while True:
            try:
                msg = job.q.get_nowait()
            except queue.Empty:
                return
            if msg[0] == "p":
                job.progress, job.text = msg[1], msg[2]
            elif msg[0] == "ok":
                job.result = msg[1]
                if job.key is not None:
                    self.cache.put(job.key, job.result)
                self._finish(job, "done", progress=1.0)
            else:
                job.trace = msg[2]
                self._finish(job, "error", error=msg[1])

    def _loop(self):
        while not self._stop.is_set():
            with self._lock:
                now = time.time()
                running = [j for j in self._jobs.values() if j.state == "running"]
                for j in running:
                    self._drain(j)
                    if j.state != "running":
                        j.proc.join(0)                     # proces po odeslání výsledku končí; nečekat se zámkem
                    elif j.timeout and now - j.started > j.timeout:
                        self._kill(j)
                        self._finish(j, "timeout", error=f"timeout {j.timeout:g} s")
                    elif not j.proc.is_alive():
                        self._drain(j)                     # výsledek mohl přijít těsně před koncem procesu
                        if j.state == "running":
                            self._finish(j, "error", error=f"process exited ({j.proc.exitcode})")
                n_run = sum(j.state == "running" for j in self._jobs.values())
                for j in self._jobs.values():
                    if n_run >= self.max_parallel:
                        break
                    if j.state == "queued":
                        self._start(j)
                        n_run += 1
                for jid in [k for k, j in self._jobs.items() if j.state in FINAL and now - j.finished > self.keep_s]:
                    del self._jobs[jid]
            time.sleep(self.poll_s)
