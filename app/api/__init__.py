from app.api.auth import router as auth_router
from app.api.encounters import router as encounters_router
from app.api.llm import router as llm_router
from app.api.capabilities import router as capabilities_router
from app.api.audio import router as audio_router
from app.api.asr_prewarm import router as asr_prewarm_router
from app.api.asr_sessions import router as asr_sessions_router
from app.api.records import router as records_router
from app.api.tasks import router as tasks_router
from app.api.speaker_profiles import router as speaker_profiles_router

__all__ = [
    "asr_sessions_router",
    "asr_prewarm_router",
    "auth_router",
    "encounters_router",
    "audio_router",
    "capabilities_router",
    "llm_router",
    "records_router",
    "speaker_profiles_router",
    "tasks_router",
]
