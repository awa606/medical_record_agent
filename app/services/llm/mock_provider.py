from __future__ import annotations

import json
import time

from app.services.llm.base import LLMProviderResponse
from app.services.mock_llm import MockLLM


class MockLLMProvider:
    name = "mock"
    model = "mock-deterministic-extractor"

    def __init__(self, mock_llm: MockLLM | None = None) -> None:
        self.mock_llm = mock_llm or MockLLM()

    def generate_fields_json(
        self,
        conversation_text: str,
        *,
        timeout_seconds: float,
    ) -> LLMProviderResponse:
        start = time.perf_counter()
        fields = self.mock_llm.extract_fields(conversation_text)
        latency_ms = int((time.perf_counter() - start) * 1000)
        return LLMProviderResponse(
            provider=self.name,
            model=self.model,
            content=json.dumps({"fields": fields.model_dump()}, ensure_ascii=False),
            latency_ms=latency_ms,
        )
