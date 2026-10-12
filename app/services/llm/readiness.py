"""Bounded live model checks and cached successful inference; never mock readiness."""
from __future__ import annotations
import json
import threading
import time
from contextlib import contextmanager
from urllib import request

_lock = threading.Lock()
_successful: dict[tuple[str, str], tuple[float, str]] = {}
_pending: set[tuple[str, str]] = set()
TTL_SECONDS = 300
REFRESH_BEFORE_SECONDS = 60
_inference = threading.Condition()
_active: set[tuple[str, str]] = set()
_business_waiters: dict[tuple[str, str], int] = {}


class ProbeDeferred(RuntimeError):
    """An idle-only probe must not queue ahead of real generation."""


@contextmanager
def inference_slot(base_url: str, model: str, *, probe: bool = False):
    key = (base_url.rstrip('/'), model)
    with _inference:
        if probe:
            if key in _active or _business_waiters.get(key, 0):
                raise ProbeDeferred()
        else:
            _business_waiters[key] = _business_waiters.get(key, 0) + 1
            try:
                while key in _active:
                    _inference.wait()
            finally:
                _business_waiters[key] -= 1
                if not _business_waiters[key]:
                    _business_waiters.pop(key)
        _active.add(key)
    try:
        yield
    finally:
        with _inference:
            _active.discard(key)
            _inference.notify_all()

def model_digest(base_url: str, model: str) -> str:
    with request.urlopen(base_url.rstrip('/') + '/api/tags', timeout=2) as response:
        models = json.load(response).get('models', [])
    return next((m.get('digest', '') for m in models if m.get('name') == model or m.get('model') == model), '')


def record_success(base_url: str, model: str, digest: str | None = None):
    if digest is None:
        digest = model_digest(base_url, model)
    with _lock:
        _successful[(base_url.rstrip('/'), model)] = (time.monotonic(), digest)

def start_probe(base_url: str, model: str):
    key = (base_url.rstrip('/'), model)
    with _lock:
        if key in _pending:
            return
        _pending.add(key)
    def run():
        try:
            from app.services.llm.ollama_provider import OllamaLLMProvider
            provider = OllamaLLMProvider(base_url=base_url, model=model)
            provider.readiness_probe = True
            provider.generate_fields_json("患者：发热3天。", timeout_seconds=120)
        except ProbeDeferred:
            pass  # Valid success remains valid; the next idle tick can refresh.
        except Exception:
            with _lock:
                _successful.pop(key, None)
        finally:
            with _lock:
                _pending.discard(key)
    thread = threading.Thread(target=run, name="local-llm-prewarm", daemon=True)
    thread.start()
    return thread


def start_monitor(base_url: str, model: str, *, interval_seconds: float = 15):
    """Application-owned refresh, independent of an open browser."""
    stop = threading.Event()
    def run():
        while not stop.is_set():
            check(base_url, model)
            stop.wait(interval_seconds)
    thread = threading.Thread(target=run, name="local-llm-readiness", daemon=True)
    thread.start()
    return stop, thread

def check(base_url: str, model: str) -> dict:
    key = (base_url.rstrip('/'), model)
    try:
        with request.urlopen(base_url.rstrip('/') + '/api/tags', timeout=2) as response:
            models = json.load(response).get('models', [])
        selected = next((m for m in models if m.get('name') == model or m.get('model') == model), None)
        if not selected:
            raise RuntimeError("selected model is not installed")
        with request.urlopen(base_url.rstrip('/') + '/api/ps', timeout=2) as response:
            resident = json.load(response).get('models', [])
        loaded = any(m.get('name') == model or m.get('model') == model for m in resident)
        with _lock:
            last_time, last_digest = _successful.get(key, (float('-inf'), ''))
            age = time.monotonic() - last_time
        if not loaded or age > TTL_SECONDS or not last_digest or last_digest != selected.get('digest'):
            with _lock:
                _successful.pop(key, None)
            start_probe(base_url, model)
            return {'ok':False,'error':'model inference warmup pending or expired','model_digest':selected.get('digest')}
        if age >= max(0, TTL_SECONDS - REFRESH_BEFORE_SECONDS):
            start_probe(base_url, model)
        return {'ok':True,'error':None,'model_digest':selected.get('digest'),'inference_age_seconds':round(age,3)}
    except Exception:
        with _lock:
            _successful.pop(key, None)
        return {'ok':False,'error':'local model service unreachable or model unavailable'}
