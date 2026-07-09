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
    preview_stage: str
    ready_for_formal_generation: bool
    updated_at: str
    character_count: int
    segment_count: int
    fields_preview: dict[str, Any]
    draft_preview: str
    candidate_diagnoses: list[dict[str, Any]]
    treatment_plan: dict[str, list[str]]
    diagnosis_evidence: list[str]
    structured_updates: list[dict[str, Any]]
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


def _structured_updates(fields: MedicalRecordFields) -> list[dict[str, Any]]:
    updates: list[dict[str, Any]] = []
    for key, label in FIELD_LABELS.items():
        field = getattr(fields, key)
        value = field.value or ""
        updates.append(
            {
                "key": key,
                "label": label,
                "status": "missing" if field.missing or not value else "preview",
                "value_preview": value[:120],
                "confidence": field.confidence,
                "source_text": field.source_spans[0].text if field.source_spans else "",
                "notice": "实时预览，需医生确认",
            }
        )
    if fields.candidate_diagnoses:
        updates.append(
            {
                "key": "candidate_diagnoses",
                "label": "候选诊断",
                "status": "preview",
                "value_preview": "；".join(diagnosis.name for diagnosis in fields.candidate_diagnoses[:3]),
                "confidence": max(
                    (diagnosis.confidence or 0.0 for diagnosis in fields.candidate_diagnoses),
                    default=None,
                ),
                "source_text": fields.candidate_diagnoses[0].reason or "",
                "notice": "候选结果，需医生确认",
            }
        )
    return updates


def _preview_stage(fields: MedicalRecordFields) -> str:
    if fields.candidate_diagnoses:
        return "diagnosis_preview"
    if any(
        not getattr(fields, key).missing and getattr(fields, key).value
        for key in FIELD_LABELS
    ):
        return "structured_preview"
    return "collecting"


def _ready_for_formal_generation(fields: MedicalRecordFields, conversation_text: str) -> bool:
    has_core_fields = (
        bool(fields.chief_complaint.value)
        and bool(fields.present_illness.value)
    )
    return has_core_fields or len(conversation_text.strip()) >= 120


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
    updates = _structured_updates(fields)

    return PreviewRecordResponse(
        status="preview_ready",
        source=payload.source,
        preview_notice="实时预览，需医生确认；不会创建正式任务，也不能直接导出。",
        preview_stage=_preview_stage(fields),
        ready_for_formal_generation=_ready_for_formal_generation(fields, payload.conversation_text),
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
        structured_updates=updates,
        missing_items=_missing_items(fields),
        safety_preview=safety.model_dump(mode="json"),
    )
