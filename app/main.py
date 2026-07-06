from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import audio_router, llm_router, records_router, tasks_router
from app.db import init_db


PROJECT_ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = PROJECT_ROOT / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Medical Record Agent", lifespan=lifespan)
app.include_router(audio_router, prefix="/api")
app.include_router(llm_router, prefix="/api")
app.include_router(records_router, prefix="/api")
app.include_router(tasks_router, prefix="/api")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
