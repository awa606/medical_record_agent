from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict


class TaskStatus(str, Enum):
    CREATED = "CREATED"
    EXTRACTING_FIELDS = "EXTRACTING_FIELDS"
    GENERATING_DRAFT = "GENERATING_DRAFT"
    SAFETY_CHECKING = "SAFETY_CHECKING"
    WAITING_DOCTOR_REVIEW = "WAITING_DOCTOR_REVIEW"
    DEGRADED = "DEGRADED"
    DONE = "DONE"
    FAILED = "FAILED"


class StepStatus(str, Enum):
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"


class AgentTaskResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: int
    input_type: str
    input_text: str | None = None
    status: TaskStatus | str
    current_stage: str | None = None
    result_json: dict[str, Any] | None = None
    error_message: str | None = None
    retry_count: int = 0
    created_at: str
    updated_at: str
    completed_at: str | None = None


class AgentTaskStepResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: int
    task_id: int
    step_name: str
    status: StepStatus | str
    attempt_no: int = 1
    started_at: str
    ended_at: str | None = None
    duration_ms: int | None = None
    input_snapshot_json: dict[str, Any] | None = None
    output_snapshot_json: dict[str, Any] | None = None
    error_message: str | None = None
