from __future__ import annotations

import os
from typing import Any

from app.services.llm.base import LLMProvider, LLMProviderUnavailableError
from app.services.llm.json_repair import parse_json_object
from app.services.llm.llm_record_generator import LLMRecordGenerator
from app.services.llm.mock_provider import MockLLMProvider
from app.services.llm.ollama_provider import OllamaLLMProvider
from app.services.llm.online_provider import OnlineLLMProvider


SUPPORTED_LLM_PROVIDERS = {"mock", "online", "ollama"}
FALLBACK_PROVIDER = "mock"
SUPPORTED_RECORD_PROVIDER_MODES = {"demo", "live", "edge"}
STRICT_RECORD_PROVIDER_MODES = {"live", "edge"}


def _record_provider_mode(mode: str | None = None) -> str:
    selected = (mode or os.environ.get("RECORD_PROVIDER_MODE") or "demo").strip().lower()
    if selected not in SUPPORTED_RECORD_PROVIDER_MODES:
        raise ValueError(
            f"Unsupported RECORD_PROVIDER_MODE '{selected}'. Supported modes: demo, live, edge"
        )
    return selected


def _fallback_allowed(mode: str) -> bool:
    return mode not in STRICT_RECORD_PROVIDER_MODES


def _provider_name(provider_name: str | None = None) -> str:
    provider = (provider_name or os.environ.get("LLM_PROVIDER") or "mock").strip().lower()
    if provider not in SUPPORTED_LLM_PROVIDERS:
        raise ValueError(
            f"Unsupported LLM_PROVIDER '{provider}'. Supported providers: mock, online, ollama"
        )
    return provider


def create_llm_provider(provider_name: str | None = None) -> LLMProvider:
    provider = _provider_name(provider_name)
    if provider == "mock":
        return MockLLMProvider()
    if provider == "online":
        return OnlineLLMProvider(
            api_base=os.environ.get("ONLINE_LLM_API_BASE", ""),
            api_key=os.environ.get("ONLINE_LLM_API_KEY", ""),
            model=os.environ.get("ONLINE_LLM_MODEL", ""),
        )
    if provider == "ollama":
        return OllamaLLMProvider(
            base_url=os.environ.get("OLLAMA_BASE_URL", ""),
            model=os.environ.get("OLLAMA_MODEL", ""),
        )
    raise AssertionError(f"Unhandled LLM provider: {provider}")


def create_llm_record_generator(
    provider_name: str | None = None,
    *,
    mode: str | None = None,
) -> LLMRecordGenerator:
    try:
        selected_mode = _record_provider_mode(mode)
    except ValueError as exc:
        raise LLMProviderUnavailableError(str(exc)) from exc
    allow_mock_fallback = _fallback_allowed(selected_mode)
    try:
        requested_provider = _provider_name(provider_name)
    except Exception as exc:  # noqa: BLE001 - invalid runtime config must not break demos.
        requested_provider = (provider_name or os.environ.get("LLM_PROVIDER") or "unknown").strip() or "unknown"
        if not allow_mock_fallback:
            raise LLMProviderUnavailableError(str(exc)) from exc
        return LLMRecordGenerator(
            provider=MockLLMProvider(),
            requested_provider=requested_provider,
            requested_model="not_configured",
            init_fallback_reason=str(exc),
            mode=selected_mode,
            allow_mock_fallback=allow_mock_fallback,
        )

    requested_model = _requested_model_for(requested_provider)
    if not allow_mock_fallback and requested_provider == "mock":
        raise LLMProviderUnavailableError("RECORD_PROVIDER_MODE live/edge requires online or ollama provider")
    try:
        provider = create_llm_provider(requested_provider)
    except Exception as exc:  # noqa: BLE001 - provider config failures must fallback.
        if not allow_mock_fallback:
            raise LLMProviderUnavailableError(str(exc)) from exc
        return LLMRecordGenerator(
            provider=MockLLMProvider(),
            requested_provider=requested_provider,
            requested_model=requested_model or "not_configured",
            init_fallback_reason=str(exc),
            mode=selected_mode,
            allow_mock_fallback=allow_mock_fallback,
        )
    return LLMRecordGenerator(
        provider=provider,
        requested_provider=requested_provider,
        requested_model=requested_model or provider.model,
        mode=selected_mode,
        allow_mock_fallback=allow_mock_fallback,
    )


def _requested_model_for(provider: str) -> str | None:
    if provider == "online":
        return os.environ.get("ONLINE_LLM_MODEL") or None
    if provider == "ollama":
        return os.environ.get("OLLAMA_MODEL") or None
    return MockLLMProvider.model


def get_llm_status(*, check_reachable: bool = False) -> dict[str, Any]:
    raw_provider = (os.environ.get("LLM_PROVIDER") or "mock").strip().lower() or "mock"
    try:
        mode = _record_provider_mode()
    except ValueError:
        mode = "demo"
    fallback_allowed = _fallback_allowed(mode)
    status: dict[str, Any] = {
        "provider": raw_provider,
        "model": _requested_model_for(raw_provider) or "not_configured",
        "mode": mode,
        "fallback_allowed": fallback_allowed,
        "configured": False,
        "reachable": False,
        "checked": check_reachable,
        "fallback_provider": FALLBACK_PROVIDER,
        "fallback": fallback_allowed,
        "fallback_reason": None,
    }

    if raw_provider not in SUPPORTED_LLM_PROVIDERS:
        status["fallback_reason"] = (
            f"Unsupported LLM_PROVIDER '{raw_provider}'. Supported providers: mock, online, ollama"
        )
        return status

    if raw_provider == "mock" and not fallback_allowed:
        status["fallback"] = False
        status["fallback_reason"] = "RECORD_PROVIDER_MODE live/edge requires online or ollama provider"
        return status

    missing = _missing_config(raw_provider)
    status["configured"] = not missing
    if missing:
        status["fallback_reason"] = f"Missing environment variables: {', '.join(missing)}"
        return status

    if raw_provider == "mock":
        status.update(
            {
                "model": MockLLMProvider.model,
                "reachable": True,
                "fallback": False,
                "fallback_reason": None,
            }
        )
        return status

    if not check_reachable:
        status["fallback"] = False
        status["fallback_reason"] = "Reachability not checked. Use POST /api/llm/test."
        return status

    try:
        provider = create_llm_provider(raw_provider)
        timeout = _timeout_seconds()
        response = provider.generate_fields_json(
            "患者发热3天，最高体温40℃，服用布洛芬后仍反复发热。",
            timeout_seconds=timeout,
        )
        parse_json_object(response.content)
    except Exception as exc:  # noqa: BLE001 - status endpoint must report fallback, not leak failures.
        status["fallback_reason"] = _safe_status_error(exc)
        return status

    status.update(
        {
            "model": provider.model,
            "reachable": True,
            "fallback": False,
            "fallback_reason": None,
        }
    )
    return status


def _missing_config(provider: str) -> list[str]:
    if provider == "online":
        keys = ["ONLINE_LLM_API_BASE", "ONLINE_LLM_API_KEY", "ONLINE_LLM_MODEL"]
    elif provider == "ollama":
        keys = ["OLLAMA_BASE_URL", "OLLAMA_MODEL"]
    else:
        keys = []
    return [key for key in keys if not os.environ.get(key)]


def _timeout_seconds() -> float:
    try:
        return float(os.environ.get("LLM_TIMEOUT_SECONDS", "30"))
    except ValueError:
        return 30.0


def _safe_status_error(exc: BaseException) -> str:
    return str(exc)[:500] or exc.__class__.__name__
