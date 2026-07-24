from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.services.asr.funasr_reliability import classify_funasr_error, funasr_cache_status


@dataclass
class PrewarmState:
    status: str = "idle"
    started_at: str | None = None
    completed_at: str | None = None
    last_error: str | None = None
    error_category: str | None = None
    retryable: bool = False
    model_load_seconds: float | None = None
    components: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "last_error": self.last_error,
            "error_category": self.error_category,
            "retryable": self.retryable,
            "model_load_seconds": self.model_load_seconds,
            "components": list(self.components),
            "model_cache": funasr_cache_status(),
        }


_STATE = PrewarmState()
_LOCK = threading.Lock()
_THREAD: threading.Thread | None = None


def _now() -> str:
    return datetime.now(UTC).isoformat()


def is_prewarm_enabled() -> bool:
    value = os.environ.get("ASR_PREWARM_ENABLED", "0").strip().lower()
    return value in {"1", "true", "yes", "on"}


def get_prewarm_status() -> dict[str, Any]:
    with _LOCK:
        return _STATE.to_dict()


def reset_prewarm_state_for_tests() -> None:
    global _THREAD
    with _LOCK:
        _STATE.status = "idle"
        _STATE.started_at = None
        _STATE.completed_at = None
        _STATE.last_error = None
        _STATE.error_category = None
        _STATE.retryable = False
        _STATE.model_load_seconds = None
        _STATE.components = []
        _THREAD = None


def start_funasr_prewarm(*, force: bool = False) -> dict[str, Any]:
    """Start FunASR model warmup in a daemon thread.

    The warmup intentionally runs outside the request path. If it fails, ASR
    upload can still fall back to normal lazy loading or Mock ASR.
    """

    global _THREAD
    with _LOCK:
        if not force and _STATE.status in {"warming", "ready"}:
            return _STATE.to_dict()
        _STATE.status = "warming"
        _STATE.started_at = _now()
        _STATE.completed_at = None
        _STATE.last_error = None
        _STATE.error_category = None
        _STATE.retryable = False
        _STATE.model_load_seconds = None
        _STATE.components = []
        _THREAD = threading.Thread(target=_run_prewarm, name="funasr-prewarm", daemon=True)
        _THREAD.start()
        return _STATE.to_dict()


def _run_prewarm() -> None:
    started = time.perf_counter()
    components: list[str] = []
    try:
        from app.api.asr_sessions import (
            _create_funasr_reconciliation_engine,
            _create_funasr_streaming_engine,
        )

        _create_funasr_streaming_engine()
        components.append("ParaformerStreaming")
        _create_funasr_reconciliation_engine()
        components.extend(["Paraformer", "fsmn-vad", "ct-punc", "cam++"])
        with _LOCK:
            _STATE.status = "ready"
            _STATE.completed_at = _now()
            _STATE.last_error = None
            _STATE.error_category = None
            _STATE.retryable = False
            _STATE.model_load_seconds = round(time.perf_counter() - started, 3)
            _STATE.components = components
    except Exception as exc:  # pragma: no cover - exact dependency failure is environment-specific.
        classified = classify_funasr_error(exc)
        with _LOCK:
            _STATE.status = "failed"
            _STATE.completed_at = _now()
            _STATE.last_error = str(exc)
            _STATE.error_category = classified["category"]
            _STATE.retryable = classified["retryable"]
            _STATE.model_load_seconds = round(time.perf_counter() - started, 3)
            _STATE.components = components
