from __future__ import annotations

import json
import time
from urllib import error, request

from app.prompts.medical_record_prompts import (
    MEDICAL_RECORD_SYSTEM_PROMPT,
    build_field_extraction_prompt,
)
from app.services.llm.base import LLMProviderResponse


class OllamaLLMProvider:
    name = "ollama"

    def __init__(self, *, base_url: str, model: str) -> None:
        if not base_url or not model:
            raise RuntimeError(
                "OLLAMA_BASE_URL and OLLAMA_MODEL are required for LLM_PROVIDER=ollama"
            )
        self.base_url = base_url.rstrip("/")
        self.model = model

    def generate_fields_json(
        self,
        conversation_text: str,
        *,
        timeout_seconds: float,
    ) -> LLMProviderResponse:
        payload = {
            "model": self.model,
            "stream": False,
            "messages": [
                {"role": "system", "content": MEDICAL_RECORD_SYSTEM_PROMPT},
                {"role": "user", "content": build_field_extraction_prompt(conversation_text)},
            ],
            "options": {"temperature": 0},
        }
        req = request.Request(
            f"{self.base_url}/api/chat",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json"},
        )

        start = time.perf_counter()
        try:
            with request.urlopen(req, timeout=timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")[:300]
            raise RuntimeError(f"ollama LLM HTTP {exc.code}: {detail}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"ollama LLM request failed: {exc.reason}") from exc

        latency_ms = int((time.perf_counter() - start) * 1000)
        data = json.loads(raw)
        content = _content_from_ollama_response(data)
        return LLMProviderResponse(
            provider=self.name,
            model=self.model,
            content=content,
            latency_ms=latency_ms,
        )


def _content_from_ollama_response(data: dict) -> str:
    message = data.get("message")
    if isinstance(message, dict) and isinstance(message.get("content"), str):
        return message["content"]
    if isinstance(data.get("response"), str):
        return data["response"]
    raise RuntimeError("ollama LLM response has no text content")
