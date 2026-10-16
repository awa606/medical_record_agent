import json
import threading
from io import BytesIO

import pytest

from app.services.llm import readiness as r


@pytest.fixture(autouse=True)
def empty_cache():
    r._successful.clear()
    yield
    r._successful.clear()


def transport(monkeypatch, digest="same"):
    monkeypatch.setattr(r.request, "urlopen", lambda *a, **kw: BytesIO(
        json.dumps({"models": [{"name": "model", "digest": digest}]}).encode()))


def test_refresh_before_expiry_keeps_valid_success_but_expiry_blocks(monkeypatch):
    key = ("http://test", "model")
    now = [0]
    monkeypatch.setattr(r.time, "monotonic", lambda: now[0])
    transport(monkeypatch)
    probes = []
    monkeypatch.setattr(r, "start_probe", lambda *a: probes.append(a))
    r.record_success(*key, digest="same")
    now[0] = 245
    assert r.check(*key)["ok"]
    assert probes == [key]
    now[0] = 301
    assert not r.check(*key)["ok"]


def test_digest_change_invalidates_even_unexpired_success(monkeypatch):
    key = ("http://test", "model")
    r.record_success(*key, digest="old")
    transport(monkeypatch, "new")
    monkeypatch.setattr(r, "start_probe", lambda *a: None)
    assert not r.check(*key)["ok"]
    assert key not in r._successful


def test_business_inflight_defers_probe_without_erasing_success():
    key = ("http://test", "model")
    r.record_success(*key, digest="same")
    with r.inference_slot(*key):
        with pytest.raises(r.ProbeDeferred):
            with r.inference_slot(*key, probe=True):
                pytest.fail("probe competed with business")
    assert key in r._successful
    with r.inference_slot(*key, probe=True):
        pass


def test_slot_releases_on_failure():
    key = ("http://test", "model")
    with pytest.raises(ValueError):
        with r.inference_slot(*key):
            raise ValueError("failed")
    with r.inference_slot(*key, probe=True):
        pass


def test_queued_business_prevents_probe_overtaking():
    key = ("http://priority", "model")
    entered, release = threading.Event(), threading.Event()
    def business():
        with r.inference_slot(*key):
            entered.set()
            release.wait(2)
    with r.inference_slot(*key):
        worker = threading.Thread(target=business)
        worker.start()
        # The condition releases while waiting, so observe the queued request.
        import time
        deadline = time.monotonic() + 2
        while r._business_waiters.get(key, 0) == 0 and time.monotonic() < deadline:
            time.sleep(.001)
        assert r._business_waiters.get(key) == 1
        with pytest.raises(r.ProbeDeferred):
            with r.inference_slot(*key, probe=True):
                pytest.fail("probe overtook queued generation")
    assert entered.wait(2)
    release.set()
    worker.join(2)
    assert not worker.is_alive()


def test_probe_single_inflight_and_failed_refresh_removes_success(monkeypatch):
    from app.services.llm.ollama_provider import OllamaLLMProvider
    key = ("http://test", "model")
    entered, release = threading.Event(), threading.Event()
    calls = []
    def failed(self, *a, **kw):
        calls.append(1)
        entered.set()
        release.wait(2)
        raise OSError("offline")
    monkeypatch.setattr(OllamaLLMProvider, "generate_fields_json", failed)
    r.record_success(*key, digest="same")
    thread = r.start_probe(*key)
    assert entered.wait(2)
    assert r.start_probe(*key) is None
    release.set()
    thread.join(2)
    assert calls == [1]
    assert key not in r._successful and key not in r._pending


def test_monitor_runs_without_page_polling_and_stops(monkeypatch):
    called = threading.Event()
    monkeypatch.setattr(r, "check", lambda *a: called.set())
    stop, thread = r.start_monitor("http://test", "model", interval_seconds=.01)
    assert called.wait(2)
    stop.set()
    thread.join(2)
    assert not thread.is_alive()
