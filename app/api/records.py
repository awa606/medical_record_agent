from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel, Field

from app.agents import MedicalRecordOrchestrator
from app.schemas import MedicalRecordFields
from app.services import MockLLM


router = APIRouter(prefix="/records", tags=["records"])


class GenerateRecordRequest(BaseModel):
    conversation_text: str = Field(min_length=1)


class PreviewRecordRequest(BaseModel):
    conversation_text: str = Field(min_length=1)
    source: str = "asr_partial"
    segments: list[dict[str, Any]] = Field(default_factory=list)


class PreviewRecordResponse(BaseModel):
    status: str
    source: str
    preview_notice: str
    updated_at: str
    character_count: int
    segment_count: int
    fields_preview: dict[str, Any]
    draft_preview: str
    candidate_diagnoses: list[dict[str, Any]]
    treatment_plan: dict[str, list[str]]
    diagnosis_evidence: list[str]
    missing_items: list[str]
    safety_preview: dict[str, Any]


FIELD_LABELS = {
    "chief_complaint": "主诉",
    "present_illness": "现病史",
    "previous_treatment": "既往处理",
    "accompanying_symptoms": "伴随症状",
    "past_history": "既往史",
    "allergy_history": "过敏史",
    "physical_exam": "查体",
}


def run_record_generation_task(task_id: int, conversation_text: str) -> None:
    MedicalRecordOrchestrator().run_existing_text_task(task_id, conversation_text)


def _missing_items(fields: MedicalRecordFields) -> list[str]:
    items: list[str] = []
    for key, label in FIELD_LABELS.items():
        field = getattr(fields, key)
        if field.missing or not field.value:
            items.append(label)
    return items


def _diagnosis_evidence(fields: MedicalRecordFields) -> list[str]:
    evidence: list[str] = []
    for key, label in FIELD_LABELS.items():
        field = getattr(fields, key)
        for span in field.source_spans:
            if span.text:
                evidence.append(f"{label}: {span.text}")
    for diagnosis in fields.candidate_diagnoses:
        if diagnosis.reason:
            evidence.append(f"{diagnosis.name}: {diagnosis.reason}")
        for span in diagnosis.evidence:
            if span.text:
                evidence.append(f"{diagnosis.name}: {span.text}")
    return evidence[:10]


def _treatment_plan(fields: MedicalRecordFields) -> dict[str, list[str]]:
    suggested_checks: list[str] = []
    medication_notes: list[str] = []
    risk_warnings: list[str] = []
    follow_up_questions: list[str] = []
    for diagnosis in fields.candidate_diagnoses:
        suggested_checks.extend(diagnosis.suggested_checks)
        medication_notes.extend(diagnosis.medication_notes)
        risk_warnings.extend(diagnosis.risk_warnings)
        follow_up_questions.extend(diagnosis.follow_up_questions)
    return {
        "suggested_checks": list(dict.fromkeys(suggested_checks)),
        "medication_notes": list(dict.fromkeys(medication_notes))
        or ["不自动生成处方，需医生确认。"],
        "risk_warnings": list(dict.fromkeys(risk_warnings)),
        "follow_up_questions": list(dict.fromkeys(follow_up_questions)),
    }


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


@router.post("/preview", response_model=PreviewRecordResponse)
def preview_record(payload: PreviewRecordRequest) -> PreviewRecordResponse:
    llm = MockLLM()
    fields = llm.extract_fields(payload.conversation_text)
    draft = llm.generate_draft(fields)
    safety = llm.safety_check(draft, fields, allow_export=False)

    return PreviewRecordResponse(
        status="preview_ready",
        source=payload.source,
        preview_notice="实时预览，需医生确认；不会创建正式任务，也不能直接导出。",
        updated_at=datetime.now(timezone.utc).isoformat(),
        character_count=len(payload.conversation_text),
        segment_count=len(payload.segments),
        fields_preview=fields.model_dump(mode="json"),
        draft_preview=draft,
        candidate_diagnoses=[
            diagnosis.model_dump(mode="json")
            for diagnosis in fields.candidate_diagnoses
        ],
        treatment_plan=_treatment_plan(fields),
        diagnosis_evidence=_diagnosis_evidence(fields),
        missing_items=_missing_items(fields),
        safety_preview=safety.model_dump(mode="json"),
    )
