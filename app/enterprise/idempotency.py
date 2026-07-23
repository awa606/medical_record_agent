from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Any, Callable


class IdempotencyConflictError(RuntimeError):
    """Raised when an idempotency key is reused for a different operation."""


@dataclass(frozen=True)
class IdempotencyEntry:
    key: str
    fingerprint: str
    response: dict[str, Any]


class InMemoryIdempotencyStore:
    def __init__(self) -> None:
        self._lock = Lock()
        self._entries: dict[str, IdempotencyEntry] = {}

    def get_or_create(
        self,
        *,
        key: str,
        fingerprint: str,
        create_response: Callable[[], dict[str, Any]],
    ) -> dict[str, Any]:
        with self._lock:
            entry = self._entries.get(key)
            if entry is not None:
                if entry.fingerprint != fingerprint:
                    raise IdempotencyConflictError("Idempotency-Key was already used for a different writeback")
                return dict(entry.response)
            response = create_response()
            self._entries[key] = IdempotencyEntry(
                key=key,
                fingerprint=fingerprint,
                response=dict(response),
            )
            return response

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


enterprise_idempotency_store = InMemoryIdempotencyStore()


def reset_enterprise_idempotency_store() -> None:
    enterprise_idempotency_store.clear()
