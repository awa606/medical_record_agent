from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.auth import require_admin
from app.schemas.auth import AuthenticatedUser
from app.services.asr.prewarm import get_prewarm_status, start_funasr_prewarm


router = APIRouter(prefix="/asr/prewarm", tags=["asr-prewarm"])


@router.get("/status")
def read_asr_prewarm_status() -> dict[str, object]:
    return get_prewarm_status()


@router.post("/start")
def start_asr_prewarm(
    _admin: AuthenticatedUser = Depends(require_admin),
) -> dict[str, object]:
    """Warm the ASR models. Admin-only: it pins CPU/RAM for minutes."""
    return start_funasr_prewarm(force=True)
