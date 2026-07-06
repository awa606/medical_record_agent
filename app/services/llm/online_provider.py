from __future__ import annotations

import json
import time
from urllib import error, request

from app.prompts.medical_record_prompts import (
    MEDICAL_RECORD_SYSTEM_PROMPT,
    build_field_extraction_prompt,
)
from app.services.llm.base import LLMProviderResponse


def _chat_completions_url(api_base: str) -> str:
    cleaned = api_base.rstrip("/")
    if cleaned.endswith("/chat/completions"):
        return cleaned
    if cleaned.endswith("/v1"):
        return f"{cleaned}/chat/completions"
    return f"{cleaned}/v1/chat/completions"


class OnlineLLMProvider:
    name = "online"

    def __init__(self, *, api_base: str, api_key: str, model: str) -> None:
        if not api_base or not api_key or not model:
            raise RuntimeError(
                "ONLINE_LLM_API_BASE, ONLINE_LLM_API_KEY, and ONLINE_LLM_MODEL are required for LLM_PROVIDER=online"
            )
        self.api_base = api_base
        self.api_key = api_key
        self.model = model

    def generate_fields_json(
        self,
        conversation_text: str,
        *,
        timeout_seconds: float,
    ) -> LLMProviderResponse:
        payload = {
            "model": self.model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": MEDICAL_RECORD_SYSTEM_PROMPT},
                {"role": "user", "content": build_field_extraction_prompt(conversation_text)},
            ],
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = request.Request(
            _chat_completions_url(self.api_base),
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )

        start = time.perf_counter()
        try:
            with request.urlopen(req, timeout=timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")[:300]
            raise RuntimeError(f"online LLM HTTP {exc.code}: {detail}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"online LLM request failed: {exc.reason}") from exc

        latency_ms = int((time.perf_counter() - start) * 1000)
        data = json.loads(raw)
        content = _content_from_openai_compatible_response(data)
        return LLMProviderResponse(
            provider=self.name,
            model=self.model,
            content=content,
            latency_ms=latency_ms,
        )


def _content_from_openai_compatible_response(data: dict) -> str:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError("online LLM response has no choices")
    first = choices[0]
    if not isinstance(first, dict):
        raise RuntimeError("online LLM choice is not an object")
    message = first.get("message")
    if isinstance(message, dict) and isinstance(message.get("content"), str):
        return message["content"]
    if isinstance(first.get("text"), str):
        return first["text"]
    raise RuntimeError("online LLM response has no text content")
