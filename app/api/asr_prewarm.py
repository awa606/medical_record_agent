from __future__ import annotations

from fastapi import APIRouter

from app.services.asr.prewarm import get_prewarm_status, start_funasr_prewarm


router = APIRouter(prefix="/asr/prewarm", tags=["asr-prewarm"])


@router.get("/status")
def read_asr_prewarm_status() -> dict[str, object]:
    return get_prewarm_status()


@router.post("/start")
def start_asr_prewarm() -> dict[str, object]:
    return start_funasr_prewarm(force=True)
