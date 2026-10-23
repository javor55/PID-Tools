"""Úlohy (pidtools.app.jobs): průběh, výsledek, chyba, zrušení do 1 s, časový limit, fronta, cache."""
import time

import pytest

from pidtools.app.jobs import JobManager, ResultCache
from tests import _jobs_fns as f


@pytest.fixture(scope="module")
def jm():
    m = JobManager(max_parallel=2, poll_s=0.02)
    yield m
    m.shutdown()


def _wait_state(jm, jid, states, t=20.0):
    t0 = time.time()
    while time.time() - t0 < t:
        st = jm.status(jid)
        if st["state"] in states:
            return st
        time.sleep(0.02)
    raise AssertionError(jm.status(jid))


def test_result_and_progress(jm):
    jid = jm.submit(f.slow, 20, 0.05)
    seen = set()
    while jm.status(jid)["state"] not in ("done", "error"):
        seen.add(round(jm.status(jid)["progress"], 2))
        time.sleep(0.03)
    assert jm.result(jid) == 40
    st = jm.status(jid)
    assert st["progress"] == 1.0 and st["text"].startswith("krok")
    assert len([p for p in seen if 0 < p < 1]) >= 3            # průběžné hlášení


def test_error(jm):
    jid = jm.submit(f.fail)
    st = _wait_state(jm, jid, ("error",))
    assert "ValueError: chybný vstup" in st["error"]
    with pytest.raises(RuntimeError, match="chybný vstup"):
        jm.result(jid)


def test_cancel_within_one_second(jm):
    jid = jm.submit(f.slow, 1000, 0.05)
    _wait_state(jm, jid, ("running",))
    time.sleep(0.5)
    t0 = time.time()
    assert jm.cancel(jid)
    assert time.time() - t0 < 1.0
    assert jm.status(jid)["state"] == "cancelled"
    assert not jm.cancel(jid)                                 # už hotová


def test_timeout(jm):
    jid = jm.submit(f.slow, 1000, 0.05, timeout=1.0)
    st = _wait_state(jm, jid, ("timeout",), t=15)
    assert "timeout" in st["error"]


def test_queue_limit():
    m = JobManager(max_parallel=1, poll_s=0.02)
    try:
        a, b = m.submit(f.slow, 1000, 0.05), m.submit(f.slow, 2, 0.01)
        _wait_state(m, a, ("running",))
        assert m.status(b)["state"] == "queued"
        m.cancel(a)
        assert m.result(b, timeout=20) == 4
    finally:
        m.shutdown()


def test_cache_hit_without_recompute(jm):
    jid = jm.submit(f.ident, "P1D", key=("ident", "demo", "P1D"))
    p = jm.result(jid, timeout=120)
    t0 = time.time()
    jid2 = jm.submit(f.ident, "P1D", key=("ident", "demo", "P1D"))
    assert jm.status(jid2)["state"] == "done" and jm.status(jid2)["cached"]
    assert jm.result(jid2) == p and time.time() - t0 < 0.1


def test_result_cache_limit():
    c = ResultCache(max_bytes=2000)
    for i in range(10):
        c.put(i, bytes(500))
    assert c.size <= 2000 and 0 not in c and 9 in c
    assert not c.put("big", bytes(5000))                      # větší než limit se neuloží
    assert c.get(9) is not None and c.hits == 1
