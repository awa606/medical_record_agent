from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel, Field

from app.agents import MedicalRecordOrchestrator


router = APIRouter(prefix="/records", tags=["records"])


class GenerateRecordRequest(BaseModel):
    conversation_text: str = Field(min_length=1)


def run_record_generation_task(task_id: int, conversation_text: str) -> None:
    MedicalRecordOrchestrator().run_existing_text_task(task_id, conversation_text)


@router.post("/generate")
def generate_record(
    payload: GenerateRecordRequest,
    background_tasks: BackgroundTasks,
) -> dict[str, object]:
    orchestrator = MedicalRecordOrchestrator()
    task_id = orchestrator.create_text_task(payload.conversation_text)
    background_tasks.add_task(run_record_generation_task, task_id, payload.conversation_text)

    return {
        "task_id": task_id,
        "status": MedicalRecordOrchestrator.STATUS_CREATED,
        "events_url": f"/api/tasks/{task_id}/events",
    }
