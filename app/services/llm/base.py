from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class LLMProviderResponse:
    provider: str
    model: str
    content: str
    latency_ms: int


class LLMProvider(Protocol):
    name: str
    model: str

    def generate_fields_json(
        self,
        conversation_text: str,
        *,
        timeout_seconds: float,
    ) -> LLMProviderResponse:
        """Return raw JSON text for field extraction."""
