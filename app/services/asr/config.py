from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ASRBackendCapabilities:
    supports_full_audio: bool
    supports_chunked_audio: bool
    supports_live_streaming: bool


BACKEND_CAPABILITIES: dict[str, ASRBackendCapabilities] = {
    "mock": ASRBackendCapabilities(True, True, False),
    "funasr": ASRBackendCapabilities(True, True, True),
    "sensevoice": ASRBackendCapabilities(True, True, False),
    "whisper": ASRBackendCapabilities(True, False, False),
    "qwen3": ASRBackendCapabilities(True, False, False),
    "online": ASRBackendCapabilities(True, False, False),
}


def configured_asr_backend(
    requested_engine: str | None = None,
    *,
    user_role: str | None = None,
) -> str:
    configured = (
        os.environ.get("MEDICAL_RECORD_AGENT_ASR_ENGINE")
        or os.environ.get("ASR_ENGINE")
        or "mock"
    ).strip().lower()
    requested = (requested_engine or "").strip().lower()
    debug_enabled = str(os.environ.get("ASR_DEBUG_ENGINE_SELECTOR_ENABLED", "0")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if user_role is None and requested:
        return requested
    if user_role == "admin" and debug_enabled and requested:
        return requested
    return configured or "mock"


def requested_asr_engine_mismatch(
    requested_engine: str | None,
    effective_engine: str | None,
) -> dict[str, str | bool | None] | None:
    requested = (requested_engine or "").strip().lower()
    effective = (effective_engine or "").strip().lower()
    if not requested or requested == effective:
        return None
    return {
        "error_code": "asr_engine_unavailable",
        "message": (
            f"Requested ASR engine '{requested}' is not active. "
            f"Current effective ASR engine is '{effective or 'unconfigured'}'."
        ),
        "requested_engine": requested,
        "effective_engine": effective or None,
        "fallback": False,
        "fallback_reason": "requested_engine_not_active",
    }


def backend_capabilities(engine_name: str) -> ASRBackendCapabilities:
    return BACKEND_CAPABILITIES.get(engine_name.strip().lower(), ASRBackendCapabilities(False, False, False))
