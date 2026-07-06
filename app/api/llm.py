from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.services.llm import get_llm_status


router = APIRouter(prefix="/llm", tags=["llm"])


@router.get("/status")
def read_llm_status() -> dict[str, Any]:
    """Return LLM configuration status without calling the provider."""
    return get_llm_status(check_reachable=False)


@router.post("/test")
def test_llm_connection() -> dict[str, Any]:
    """Check provider reachability and JSON output without exposing API keys."""
    return get_llm_status(check_reachable=True)
