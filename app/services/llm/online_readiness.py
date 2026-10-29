"""Short-lived authenticated connectivity check; never generates a record."""
from __future__ import annotations

import hashlib
import threading
import time

_lock = threading.Lock()
_cached_key: bytes | None = None
_cached_result: dict | None = None
_expires_at = 0.0


def check(provider) -> dict:
    # Keep credentials only in process memory; never publish this fingerprint.
    identity = "\0".join((provider.endpoint, provider.model, provider.api_key))
    key = hashlib.sha256(identity.encode("utf-8")).digest()
    global _cached_key, _cached_result, _expires_at
    with _lock:
        if key == _cached_key and _cached_result is not None and time.monotonic() < _expires_at:
            return {**_cached_result, "cached": True}
        try:
            result = provider.probe(timeout_seconds=5)
            ok = result.get("reachable") is True
            code = result.get("error_code")
            # Only our fixed machine codes are public. Never echo network bodies.
            error = None if ok else (code if isinstance(code, str) and
                                     code.replace("_", "").isalnum() and len(code) < 80
                                     else "ONLINE_CONNECTION_UNAVAILABLE")
        except Exception:
            ok, error = False, "ONLINE_CONNECTION_UNAVAILABLE"
        _cached_key = key
        _cached_result = {"ok": ok, "error": error, "inference_called": False,
                          "scope": "authenticated_model_availability", "cached": False}
        _expires_at = time.monotonic() + (30 if ok else 5)
        return dict(_cached_result)
