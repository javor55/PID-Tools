"""
API jako samostatný program (sidecar okna desktopu, M22): python -m pidtools.api.sidecar nebo zabalený pidtools-api.

    pidtools-api --port 0 --token TAJNE --parent-pid 1234

Poslouchá jen na 127.0.0.1 (port 0 = volný port vybere systém). Až server poslouchá, vypíše na stdout jeden řádek
`PIDTOOLS_READY {"port": …, "token": "…", "version": "…"}`, který čte obal okna. Skončí, když zmizí rodičovský proces
(--parent-pid), takže po zavření okna nezůstane běžet. `--smoke` projde celou cestu (workspace, demo, identifikace
jako úloha, protokol) a skončí kódem 0 – kontrola zabaleného programu.
"""
import argparse
import json
import multiprocessing
import os
import secrets
import socket
import sys
import threading
import time
import urllib.request

READY = "PIDTOOLS_READY"
HOST = "127.0.0.1"
GRACE_S = 5.0                        # po žádosti o ukončení čekáme na korektní zastavení, pak proces skončí natvrdo


def free_socket(port=0):
    """Naslouchající soket na 127.0.0.1 (port 0 = volný); předá se serveru, takže mezi výběrem a startem není okno."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if os.name != "nt":
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, int(port)))
        s.listen(128)
        s.set_inheritable(False)
    except BaseException:
        s.close()
        raise
    return s


def ready_line(port, token, version):
    return f"{READY} " + json.dumps({"port": int(port), "token": token, "version": version})


def parse_ready(line):
    """Řádek `PIDTOOLS_READY {…}` → slovník; jiný řádek → None."""
    if not line.startswith(READY + " "):
        return None
    try:
        return json.loads(line[len(READY) + 1:])
    except ValueError:
        return None


def parent_alive(pid):
    """Žije proces pid? Windows: OpenProcess + WaitForSingleObject; POSIX: kill(pid, 0) a změna rodiče."""
    if os.name == "nt":
        import ctypes
        k32 = ctypes.windll.kernel32
        k32.OpenProcess.restype = ctypes.c_void_p
        k32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        h = k32.OpenProcess(0x00100000 | 0x1000, False, int(pid))      # SYNCHRONIZE | PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        try:
            return k32.WaitForSingleObject(h, 0) == 0x102              # WAIT_TIMEOUT = ještě běží
        finally:
            k32.CloseHandle(ctypes.c_void_p(h))
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def watch_parent(pid, on_gone, interval=0.5, alive=parent_alive):
    """Vlákno, které zavolá on_gone(), jakmile rodič pid zmizí (jednou). Vrací vlákno."""
    ppid0 = os.getppid() if os.name != "nt" else None

    def gone():
        if ppid0 is not None and int(pid) == ppid0 and os.getppid() != ppid0:
            return True                  # osiřelý proces převzal init – rodič skončil (i jako zombie)
        return not alive(pid)

    def loop():
        while not gone():
            time.sleep(interval)
        on_gone()

    t = threading.Thread(target=loop, name="pidtools-parent", daemon=True)
    t.start()
    return t


def make_server(app, sock):
    import uvicorn
    return uvicorn.Server(uvicorn.Config(app, log_level="warning", lifespan="on")), [sock]


def serve(token=None, port=0, parent_pid=None, out=None, cors=()):
    """Spustí server (blokuje do ukončení). out(řádek) dostane READY řádek; vrací kód ukončení."""
    from .. import __version__
    from . import create_app
    token = token or secrets.token_urlsafe(24)
    sock = free_socket(port)
    server, socks = make_server(create_app(token=token, cors_origins=list(cors)), sock)
    real_port = sock.getsockname()[1]

    def announce():
        while not server.started:
            if server.should_exit:
                return
            time.sleep(0.01)
        (out or (lambda s: print(s, flush=True)))(ready_line(real_port, token, __version__))

    def stop():
        server.should_exit = True
        threading.Timer(GRACE_S, lambda: os._exit(0)).start()      # úloha / spojení nesmí ukončení zdržet

    threading.Thread(target=announce, name="pidtools-ready", daemon=True).start()
    if parent_pid:
        watch_parent(parent_pid, stop)
    server.run(sockets=socks)
    return 0


# ---- smoke test zabaleného programu

def _call(base, token, method, path, body=None, timeout=120):
    req = urllib.request.Request(base + path, method=method, headers={"X-PID-Token": token},
                                 data=None if body is None else json.dumps(body).encode())
    if body is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
        return data if r.headers.get_content_type() != "application/json" else json.loads(data)


def smoke_steps(base, token, log=print):
    """Cesta přes API: health, workspace, demo, identifikace (úloha v samostatném procesu), protokol."""
    h = _call(base, token, "GET", "/health")
    assert h["status"] == "ok", h
    wid = _call(base, token, "POST", "/workspaces")["id"]
    w = f"/workspaces/{wid}"
    _call(base, token, "POST", w + "/data/demo")
    _call(base, token, "PATCH", w + "/settings", {"chosen": ["P1D"]})
    job = _call(base, token, "POST", w + "/identify")
    t0 = time.time()
    while job["state"] not in ("done", "error", "cancelled", "timeout"):
        if time.time() - t0 > 240:
            raise TimeoutError("identification job did not finish")
        time.sleep(0.2)
        job = _call(base, token, "GET", f"/jobs/{job['id']}")
    assert job["state"] == "done", job
    log(f"identification job: done in {time.time() - t0:.1f} s")
    m = _call(base, token, "GET", w + "/model")
    assert m["has_fit"] and m["results"], "no model"
    html = _call(base, token, "POST", w + "/report", {"meta": {}})
    assert b"<html" in html.lower() and len(html) > 10_000, "report too short"
    log(f"report: {len(html) // 1024} kB")
    ui = _call(base, token, "GET", "/") if os.environ.get("PIDTOOLS_SMOKE_UI") else None
    return {"version": h["version"], "ui": ui is not None}


def run_smoke(log=print):
    """Server ve vlákně téhož procesu na volném portu; vrací 0 / 1. Měří start do „ready“."""
    from .. import __version__
    from . import create_app
    t0 = time.perf_counter()
    token = secrets.token_urlsafe(16)
    sock = free_socket(0)
    server, socks = make_server(create_app(token=token), sock)
    th = threading.Thread(target=server.run, kwargs={"sockets": socks}, daemon=True)
    th.start()
    while not server.started:
        if not th.is_alive():
            log("smoke: server did not start")
            return 1
        time.sleep(0.01)
    log(f"smoke: ready in {time.perf_counter() - t0:.2f} s (from main, version {__version__})")
    try:
        smoke_steps(f"http://{HOST}:{sock.getsockname()[1]}", token, log)
        log("smoke: ok")
        code = 0
    except Exception as ex:                      # noqa: BLE001 – chyba kroku = neúspěch smoke testu
        log(f"smoke: FAILED {type(ex).__name__}: {ex}")
        code = 1
    server.should_exit = True
    th.join(10)
    return code


def main(argv=None):
    multiprocessing.freeze_support()             # zabalený program: podproces úlohy („spawn“) se tu vrátí do své role
    ap = argparse.ArgumentParser(prog="pidtools-api", description=__doc__.strip().splitlines()[0])
    ap.add_argument("--port", type=int, default=0, help="0 = free port")
    ap.add_argument("--token", default=None, help="default: random")
    ap.add_argument("--parent-pid", type=int, default=None, help="exit when this process disappears")
    ap.add_argument("--cors", nargs="*", default=[])
    ap.add_argument("--smoke", action="store_true", help="self-test of the built program and exit")
    a = ap.parse_args(argv)
    if a.smoke:
        return run_smoke()
    return serve(a.token, a.port, a.parent_pid, cors=a.cors)


if __name__ == "__main__":
    sys.exit(main())
