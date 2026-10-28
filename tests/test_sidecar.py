"""
Sidecar (M22): řádek READY, volný port, hlídání rodičovského procesu; spuštěný program (z kódu i zabalený
PyInstallerem – ten se přeskočí, když není sestavený: tools/build_sidecar.py, nebo PIDTOOLS_SIDECAR_EXE).
"""
import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from pidtools.api import sidecar  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def _frozen_exe():
    p = os.environ.get("PIDTOOLS_SIDECAR_EXE")
    if p:
        return Path(p)
    sys.path.insert(0, str(ROOT / "tools"))
    import build_sidecar
    return ROOT / "dist" / build_sidecar.NAME / build_sidecar.exe_name(build_sidecar.target_triple())


def _variants():
    frozen = _frozen_exe()
    return [pytest.param([sys.executable, "-m", "pidtools.api.sidecar"], id="python"),
            pytest.param([str(frozen)], id="frozen",
                         marks=pytest.mark.skipif(not frozen.exists(), reason="sidecar not built"))]


def test_ready_line_roundtrip():
    line = sidecar.ready_line(51234, "tok", "1.2")
    assert line.startswith("PIDTOOLS_READY {") and "\n" not in line
    assert sidecar.parse_ready(line) == {"port": 51234, "token": "tok", "version": "1.2"}
    assert sidecar.parse_ready("token abc") is None and sidecar.parse_ready("PIDTOOLS_READY {x") is None


def test_free_socket_is_loopback_and_distinct():
    a, b = sidecar.free_socket(0), sidecar.free_socket(0)
    try:
        assert a.getsockname()[0] == "127.0.0.1" and a.getsockname()[1] != b.getsockname()[1] > 0
        with pytest.raises(OSError):
            sidecar.free_socket(a.getsockname()[1]).close()          # obsazený port
    finally:
        a.close()
        b.close()


def test_parent_alive_self_and_dead():
    assert sidecar.parent_alive(os.getpid())
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    assert not sidecar.parent_alive(p.pid)


def test_watch_parent_calls_once_when_gone():
    state = {"alive": True}
    hit = threading.Event()
    calls = []
    sidecar.watch_parent(os.getpid() + 10 ** 6, lambda: (calls.append(1), hit.set()), interval=0.01,
                         alive=lambda pid: state["alive"])
    time.sleep(0.1)
    assert not hit.is_set()
    state["alive"] = False
    assert hit.wait(2)
    time.sleep(0.1)
    assert calls == [1]


def _read_ready(proc, timeout=60):
    t0 = time.time()
    while time.time() - t0 < timeout:
        line = proc.stdout.readline()
        if not line:
            break
        info = sidecar.parse_ready(line.strip())
        if info:
            return info, time.time() - t0
    raise AssertionError("no READY line")


def _get(info, path):
    req = urllib.request.Request(f"http://127.0.0.1:{info['port']}{path}", headers={"X-PID-Token": info["token"]})
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.status, r.read()


@pytest.mark.parametrize("cmd", _variants())
def test_start_serves_health_and_requires_token(cmd):
    p = subprocess.Popen(cmd + ["--port", "0", "--token", "sekret"], stdout=subprocess.PIPE, text=True, cwd=ROOT)
    try:
        info, dt = _read_ready(p)
        assert info["token"] == "sekret" and info["port"] > 0
        print(f"sidecar ready after {dt:.2f} s")
        assert json.loads(_get(info, "/health")[1])["status"] == "ok"
        assert _get(info, "/i18n/cs")[0] == 200
        with pytest.raises(urllib.error.HTTPError) as ex:
            urllib.request.urlopen(f"http://127.0.0.1:{info['port']}/i18n/cs", timeout=10)      # bez tokenu
        assert ex.value.code == 401
    finally:
        p.kill()
        p.wait()


HELPER = (
    "import os, subprocess, sys, time\n"
    "p = subprocess.Popen(sys.argv[1:] + ['--parent-pid', str(os.getpid())], stdout=subprocess.PIPE, text=True)\n"
    "print(p.pid, flush=True)\n"
    "print(p.stdout.readline().strip(), flush=True)\n"
    "time.sleep(300)\n")


@pytest.mark.parametrize("cmd", _variants())
def test_exits_when_parent_dies(cmd):
    """Rodič (pomocný proces) spustí sidecar s --parent-pid; po zabití rodiče sidecar sám skončí."""
    par = subprocess.Popen([sys.executable, "-c", HELPER] + cmd, stdout=subprocess.PIPE, text=True, cwd=ROOT)
    try:
        child = int(par.stdout.readline())
        info = sidecar.parse_ready(par.stdout.readline().strip())
        assert info, "no READY line"
        assert sidecar.parent_alive(child)
        par.kill()
        par.wait()
        t0 = time.time()
        while sidecar.parent_alive(child) and time.time() - t0 < 20:
            time.sleep(0.1)
        assert not sidecar.parent_alive(child), "sidecar still running after its parent died"
        print(f"sidecar ended {time.time() - t0:.1f} s after its parent")
    finally:
        par.kill()


@pytest.mark.parametrize("cmd", _variants())
def test_smoke(cmd):
    """Celá cesta včetně úlohy v podprocesu (u zabaleného programu ověřuje spawn zmrazeného programu)."""
    r = subprocess.run(cmd + ["--smoke"], capture_output=True, text=True, timeout=600, cwd=ROOT)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "smoke: ok" in r.stdout
