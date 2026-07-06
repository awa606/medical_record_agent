from app.api.llm import router as llm_router
from app.api.audio import router as audio_router
from app.api.asr_sessions import router as asr_sessions_router
from app.api.records import router as records_router
from app.api.tasks import router as tasks_router

__all__ = [
    "asr_sessions_router",
    "audio_router",
    "llm_router",
    "records_router",
    "tasks_router",
]
