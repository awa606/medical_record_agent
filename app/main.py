from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import (
    asr_prewarm_router,
    asr_sessions_router,
    auth_router,
    encounters_router,
    enterprise_router,
    audio_router,
    capabilities_router,
    llm_router,
    records_router,
    runtime_router,
    speaker_profiles_router,
    tasks_router,
)
from app.db import init_db
from app.services.asr.prewarm import is_prewarm_enabled, start_funasr_prewarm


PROJECT_ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = PROJECT_ROOT / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    if is_prewarm_enabled():
        start_funasr_prewarm()
    yield


app = FastAPI(title="Medical Record Agent", lifespan=lifespan)
app.include_router(auth_router, prefix="/api")
app.include_router(encounters_router, prefix="/api")
app.include_router(enterprise_router, prefix="/api")
app.include_router(asr_prewarm_router, prefix="/api")
app.include_router(asr_sessions_router, prefix="/api")
app.include_router(audio_router, prefix="/api")
app.include_router(capabilities_router, prefix="/api")
app.include_router(llm_router, prefix="/api")
app.include_router(records_router, prefix="/api")
app.include_router(speaker_profiles_router, prefix="/api")
app.include_router(tasks_router, prefix="/api")
app.include_router(runtime_router)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
