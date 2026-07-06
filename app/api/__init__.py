from app.api.llm import router as llm_router
from app.api.audio import router as audio_router
from app.api.records import router as records_router
from app.api.tasks import router as tasks_router

__all__ = ["audio_router", "llm_router", "records_router", "tasks_router"]
