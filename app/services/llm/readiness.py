"""Bounded live model checks and cached successful inference; never mock readiness."""
from __future__ import annotations
import json
import threading
import time
from urllib import request

_lock = threading.Lock()
_successful: dict[tuple[str, str], tuple[float, str]] = {}
_pending: set[tuple[str, str]] = set()
TTL_SECONDS = 300

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
            provider.generate_fields_json("患者：发热3天。", timeout_seconds=120)
        except Exception:
            with _lock:
                _successful.pop(key, None)
        finally:
            with _lock:
                _pending.discard(key)
    threading.Thread(target=run, name="local-llm-prewarm", daemon=True).start()

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
            start_probe(base_url, model)
            return {'ok':False,'error':'model inference warmup pending or expired','model_digest':selected.get('digest')}
        return {'ok':True,'error':None,'model_digest':selected.get('digest'),'inference_age_seconds':round(age,3)}
    except Exception:
        with _lock:
            _successful.pop(key, None)
        return {'ok':False,'error':'local model service unreachable or model unavailable'}
