from __future__ import annotations

from typing import Callable, TypeVar


T = TypeVar("T")


def retry_llm_call(
    operation: Callable[[], T],
    *,
    max_retries: int = 2,
    on_failure: Callable[[int, Exception], None] | None = None,
) -> T:
    attempts = max_retries + 1
    last_error: Exception | None = None

    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except Exception as exc:
            last_error = exc
            if on_failure is not None:
                on_failure(attempt, exc)
            if attempt >= attempts:
                break

    if last_error is None:
        raise RuntimeError("LLM call failed without an exception")
    raise last_error
