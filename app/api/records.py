from __future__ import annotations

from datetime import datetime, timezone
import math
import os
import re
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.agents import MedicalRecordOrchestrator
from app.api.auth import current_user_from_request, require_current_user
from app.db import bind_task_to_encounter, can_retry_failed_encounter, get_encounter, set_task_owner, update_task
from app.schemas import ASRResult, ASRSegment, MedicalRecordFields, SafetyCheckResult, SourceSpan
from app.services import LLMProviderUnavailableError, create_llm_record_generator
from app.services.asr.role_quality import build_speaker_role_quality
from app.services.asr.speaker_role_policy import normalize_role
from app.services.clinical_facts import clinical_segment_contexts, split_clinical_segments
from app.services.field_alignment import comparison_without_role
from app.services.record_quality import build_record_quality_report


router = APIRouter(prefix="/records", tags=["records"], dependencies=[Depends(require_current_user)])


class GenerateRecordRequest(BaseModel):
    conversation_text: str = Field(min_length=1)
    encounter_id: int | None = None


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
    evidence_links: list[dict[str, Any]]
    structured_updates: list[dict[str, Any]]
    missing_items: list[str]
    safety_preview: dict[str, Any]
    quality_preview: dict[str, Any]
    extraction_info: dict[str, Any]


class ExtractFieldsRequest(BaseModel):
    conversation_text: str = Field(min_length=1)
    source: str = "external_api"
    segments: list[dict[str, Any]] = Field(default_factory=list)


class ExtractFieldsResponse(BaseModel):
    status: str
    source: str
    character_count: int
    segment_count: int
    fields: dict[str, Any]
    candidate_diagnoses: list[dict[str, Any]]
    treatment_plan: dict[str, list[str]]
    diagnosis_evidence: list[str]
    evidence_links: list[dict[str, Any]]
    quality_report: dict[str, Any]
    extraction_info: dict[str, Any]
    creates_task: bool = False


class BuildDraftRequest(BaseModel):
    fields: MedicalRecordFields
    allow_export: bool = False


class BuildDraftResponse(BaseModel):
    status: str
    draft: str
    safety_check: dict[str, Any]
    quality_report: dict[str, Any]
    generation_info: dict[str, Any]
    creates_task: bool = False
    export_allowed: bool = False


class QualityRequest(BaseModel):
    fields: MedicalRecordFields
    draft: str | None = None
    safety_check: SafetyCheckResult | None = None


class QualityResponse(BaseModel):
    status: str
    quality_report: dict[str, Any]
    provider_info: dict[str, Any] | None = None
    creates_task: bool = False


FIELD_LABELS = {
    "chief_complaint": "主诉",
    "present_illness": "现病史",
    "previous_treatment": "既往处理",
    "accompanying_symptoms": "伴随症状",
    "past_history": "既往史",
    "allergy_history": "过敏史",
    "physical_exam": "查体",
}

VALID_STABLE_ROLES = {"医生", "患者", "其他"}
PLACEHOLDER_FIELD_VALUES = {
    "待医生查体补充",
    "待医生查体补充舌象、脉象、咽部和肺部情况",
    "未提及",
    "未提及，待补充",
    "建议补问",
}


def run_record_generation_task(task_id: int, conversation_text: str, asr_source: dict | None = None) -> None:
    MedicalRecordOrchestrator().run_existing_text_task(task_id, conversation_text, asr_source)


def _missing_items(fields: MedicalRecordFields) -> list[str]:
    items: list[str] = []
    for key, label in FIELD_LABELS.items():
        field = getattr(fields, key)
        if (
            not _has_real_field_value(field)
            or field.status in {"partial", "conflicting"}
        ):
            items.append(label)
    return items


def _has_real_field_value(field: Any) -> bool:
    value = (field.value or "").strip() if field is not None else ""
    if not value or field.missing:
        return False
    return value not in PLACEHOLDER_FIELD_VALUES


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
        or ["系统不自动生成处方，治疗和用药必须由医生确认。"],
        "risk_warnings": list(dict.fromkeys(risk_warnings)),
        "follow_up_questions": list(dict.fromkeys(follow_up_questions)),
    }


def _quote_text(value: str) -> str:
    return re.sub(r"[\s，。！？!?、,]+", "", comparison_without_role(value))


def _audio_time(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value if math.isfinite(value) and value >= 0 else None


class _AudioCitations:
    """Relate zero-based model sentence numbers to ASR turns only when their texts align."""

    def __init__(self, conversation: str, segments: list[dict[str, Any]]):
        self.sentences = clinical_segment_contexts(conversation)
        self.rows = []
        self.by_id = {}
        owners = []
        normalized_sentences = []
        for index, segment in enumerate(segments):
            text = str(segment.get("text") or "")
            segment_id = str(segment.get("segment_id") or f"segment-{index}")
            start = _audio_time(segment.get("start_time"))
            end = _audio_time(segment.get("end_time"))
            if start is not None and end is not None and end < start:
                start = end = None
            row = {"segment_id": segment_id, "index": index, "start_time": start, "end_time": end,
                   "speaker_id": segment.get("speaker_id") or segment.get("speaker"),
                   "role": segment.get("role"), "text": text}
            self.rows.append(row)
            self.by_id[segment_id] = None if segment_id in self.by_id else row
            for sentence in split_clinical_segments(text):
                owners.append(row)
                normalized_sentences.append(_quote_text(sentence))
        self.owners = owners if normalized_sentences == [_quote_text(s.text) for s in self.sentences] else []

    def bind(self, span: SourceSpan) -> SourceSpan:
        # Preserve the original quote and model index even when the proposed audio link is rejected.
        unbound = span.model_copy(update={"segment_id": None, "start_time": None, "end_time": None})
        quote = _quote_text(span.text)
        if not quote:
            return unbound
        contexts = clinical_segment_contexts(span.text)
        role = normalize_role(contexts[0].speaker) if contexts else None
        candidates = self.rows
        if span.index is not None:
            if not 0 <= span.index < len(self.sentences):
                return unbound
            sentence = self.sentences[span.index]
            if quote not in _quote_text(sentence.text):
                return unbound
            if self.owners:
                candidates = [self.owners[span.index]]
            sentence_role = normalize_role(sentence.speaker)
            if role and sentence_role and role != sentence_role:
                return unbound
            role = role or sentence_role
        matches = [row for row in candidates
                   if quote in _quote_text(row["text"])
                   and (span.segment_id is None or row["segment_id"] == span.segment_id)
                   and (role is None or not row["role"] or normalize_role(row["role"]) == role)]
        if len(matches) != 1 or self.by_id[matches[0]["segment_id"]] is None:
            return unbound
        row = matches[0]
        start, end = row["start_time"], row["end_time"]
        supplied = [v for v in (span.start_time, span.end_time) if v is not None]
        if any(_audio_time(v) is None or (start is not None and v < start)
               or (end is not None and v > end) for v in supplied):
            return unbound
        if span.start_time is not None and span.end_time is not None and span.start_time > span.end_time:
            return unbound
        return span.model_copy(update={"segment_id": row["segment_id"],
            "start_time": span.start_time if span.start_time is not None and start is not None else start,
            "end_time": span.end_time if span.end_time is not None and end is not None else end})

    def enrich(self, fields: MedicalRecordFields) -> MedicalRecordFields:
        enriched = fields.model_copy(deep=True)
        for key in FIELD_LABELS:
            field = getattr(enriched, key)
            field.source_spans = [self.bind(span) for span in field.source_spans]
        for diagnosis in enriched.candidate_diagnoses:
            diagnosis.evidence = [self.bind(span) for span in diagnosis.evidence]
        return enriched


def _structured_updates(fields: MedicalRecordFields) -> list[dict[str, Any]]:
    updates: list[dict[str, Any]] = []
    for key, label in FIELD_LABELS.items():
        field = getattr(fields, key)
        value = field.value or ""
        source_text = field.source_spans[0].text if field.source_spans else ""
        source_segment_ids = [span.segment_id for span in field.source_spans[:1] if span.segment_id]
        updates.append(
            {
                "key": key,
                "label": label,
                "status": (
                    "missing"
                    if not _has_real_field_value(field)
                    else "preview" if field.status == "complete" else field.status
                ),
                "value_preview": value[:120],
                "confidence": field.confidence,
                "source_text": source_text,
                "source_segment_ids": source_segment_ids,
                "notice": "实时预览，需医生确认",
            }
        )
    if fields.candidate_diagnoses:
        diagnosis_source = (
            fields.candidate_diagnoses[0].evidence[0].text
            if fields.candidate_diagnoses[0].evidence
            else fields.candidate_diagnoses[0].reason or ""
        )
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
                "source_text": diagnosis_source,
                "source_segment_ids": [span.segment_id for span in fields.candidate_diagnoses[0].evidence[:1] if span.segment_id],
                "notice": "候选结果，需医生确认",
            }
        )
    return updates


def _evidence_links(
    fields: MedicalRecordFields,
    citations: _AudioCitations,
) -> list[dict[str, Any]]:
    links: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    groups = [(label, getattr(fields, key).source_spans) for key, label in FIELD_LABELS.items()]
    groups.extend((f"候选诊断：{d.name}", d.evidence) for d in fields.candidate_diagnoses)
    for label, spans in groups:
        for span in spans:
            row = citations.by_id.get(span.segment_id)
            identity = (label, span.segment_id)
            if row is not None and identity not in seen:
                seen.add(identity)
                links.append({"label": label, "evidence": span.text, **row})
    return links[:12]


def _preview_stage(fields: MedicalRecordFields) -> str:
    if fields.candidate_diagnoses:
        return "diagnosis_preview"
    if any(
        _has_real_field_value(getattr(fields, key))
        for key in FIELD_LABELS
    ):
        return "structured_preview"
    return "collecting"


def _ready_for_formal_generation(fields: MedicalRecordFields, conversation_text: str) -> bool:
    has_core_fields = (
        _has_real_field_value(fields.chief_complaint)
        and _has_real_field_value(fields.present_illness)
    )
    return has_core_fields or len(conversation_text.strip()) >= 120


def _stable_preview_input(payload: PreviewRecordRequest) -> tuple[str, list[dict[str, Any]]]:
    if not payload.segments:
        return payload.conversation_text, []
    stable = [segment for segment in payload.segments if not segment.get("provisional")]
    mapped = [
        segment
        for segment in stable
        if segment.get("role") in VALID_STABLE_ROLES
    ]
    if not mapped:
        raise HTTPException(
            status_code=409,
            detail="结构化预览需要先完成稳定的说话人角色映射。",
        )
    # Check every stable speaker before dropping unmapped turns from the preview.
    _require_segments_role_quality(payload.conversation_text, stable)
    conversation = "\n".join(
        f"[{segment['role']}] {str(segment.get('text') or '').strip()}"
        for segment in mapped
        if str(segment.get("text") or "").strip()
    )
    if not conversation:
        raise HTTPException(status_code=409, detail="暂无可用于预览的稳定转写文本。")
    return conversation, mapped


def _stable_segments_for_external_api(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [segment for segment in segments if not segment.get("provisional")]


def _require_segments_role_quality(
    conversation_text: str,
    segments: list[dict[str, Any]],
) -> None:
    if not segments:
        return
    asr_segments = [ASRSegment.model_validate(segment) for segment in segments]
    asr_result = ASRResult(
        audio_id="external_api",
        engine="external_api",
        text="\n".join(segment.text for segment in asr_segments if segment.text.strip()),
        conversation_text=conversation_text,
        segments=asr_segments,
    )
    quality = build_speaker_role_quality(asr_result)
    if quality.status != "passed":
        first_pending = quality.pending_confirmation[0] if quality.pending_confirmation else None
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Speaker role quality gate did not pass.",
                "policy_version": quality.policy_version,
                "reason_code": first_pending.reason_code if first_pending else None,
                "pending_confirmation": [
                    item.model_dump(mode="json") for item in quality.pending_confirmation
                ],
                "role_quality": quality.model_dump(mode="json"),
            },
        )


def _record_generator_or_503():
    try:
        return create_llm_record_generator()
    except LLMProviderUnavailableError as exc:
        raise _provider_unavailable_http(str(exc)) from exc


def _provider_unavailable_http(reason: str, trace: dict[str, Any] | None = None) -> HTTPException:
    detail = _extraction_info(trace)
    if trace is None:
        detail["requested_provider"] = os.environ.get("LLM_PROVIDER") or "mock"
        detail["mode"] = os.environ.get("RECORD_PROVIDER_MODE") or "demo"
    detail.update(
        {
            "message": "Requested record generation provider is unavailable.",
            "actual_provider": None,
            "fallback": False,
            "fallback_reason": reason,
        }
    )
    return HTTPException(status_code=503, detail=detail)


def ensure_record_provider_available() -> dict[str, Any]:
    generator = _record_generator_or_503()
    return _extraction_info(generator.get_trace())


def _generation_owner_for_encounter(encounter_id: int, request: Request | None) -> int:
    user = current_user_from_request(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    encounter = get_encounter(encounter_id)
    if encounter is None:
        raise HTTPException(status_code=404, detail="Encounter not found")
    encounter_doctor_id = encounter.get("doctor_user_id")
    if encounter_doctor_id is None:
        raise HTTPException(status_code=409, detail="Encounter has no doctor owner")
    if user.role != "admin" and int(encounter_doctor_id) != user.id:
        raise HTTPException(status_code=403, detail="You are not allowed to access this encounter")
    check_in_status = encounter.get("check_in_status") or "checked_in"
    if check_in_status == "registered":
        raise HTTPException(status_code=409, detail="Encounter must be checked in before record generation")
    if check_in_status in {"completed", "cancelled"}:
        raise HTTPException(status_code=409, detail="Encounter is closed and cannot generate a record")
    existing_task_id = encounter.get("task_id")
    if existing_task_id is not None and not can_retry_failed_encounter(encounter_id):
        raise HTTPException(status_code=409, detail="Encounter is already bound to a task")
    return int(encounter_doctor_id)


def _extract_fields_for_service(
    conversation_text: str,
    segments: list[dict[str, Any]],
) -> tuple[MedicalRecordFields, dict[str, Any], _AudioCitations]:
    generator = _record_generator_or_503()
    try:
        fields = generator.extract_fields(conversation_text)
    except LLMProviderUnavailableError as exc:
        raise _provider_unavailable_http(str(exc), generator.get_trace()) from exc
    citations = _AudioCitations(conversation_text, segments)
    return citations.enrich(fields), _extraction_info(generator.get_trace()), citations


def _extraction_info(trace: dict[str, Any] | None) -> dict[str, Any]:
    trace = trace or {}
    return {
        "requested_provider": trace.get("llm_provider") or "mock",
        "actual_provider": trace.get("actual_provider") or trace.get("llm_provider") or "mock",
        "model": trace.get("model") or "mock-deterministic-extractor",
        "fallback": bool(trace.get("fallback", False)),
        "fallback_reason": trace.get("fallback_reason"),
        "mode": trace.get("mode") or "demo",
        "fallback_allowed": bool(trace.get("fallback_allowed", True)),
        "operation": trace.get("operation") or "field_extraction",
        "extraction_mode": "clinical_fact_rules_v1",
    }


@router.post("/extract-fields", response_model=ExtractFieldsResponse)
def extract_fields(payload: ExtractFieldsRequest) -> ExtractFieldsResponse:
    stable_segments = _stable_segments_for_external_api(payload.segments)
    _require_segments_role_quality(payload.conversation_text, stable_segments)
    fields, extraction_info, citations = _extract_fields_for_service(payload.conversation_text, stable_segments)
    quality_report = build_record_quality_report(fields)
    return ExtractFieldsResponse(
        status="fields_extracted",
        source=payload.source,
        character_count=len(payload.conversation_text),
        segment_count=len(stable_segments),
        fields=fields.model_dump(mode="json"),
        candidate_diagnoses=[
            diagnosis.model_dump(mode="json")
            for diagnosis in fields.candidate_diagnoses
        ],
        treatment_plan=_treatment_plan(fields),
        diagnosis_evidence=_diagnosis_evidence(fields),
        evidence_links=_evidence_links(fields, citations),
        quality_report=quality_report,
        extraction_info=extraction_info,
    )


@router.post("/build-draft", response_model=BuildDraftResponse)
def build_draft(payload: BuildDraftRequest) -> BuildDraftResponse:
    generator = _record_generator_or_503()
    draft = generator.generate_draft(payload.fields)
    generation_info = _extraction_info(generator.get_trace())
    safety = generator.safety_check(draft, payload.fields, allow_export=payload.allow_export)
    safety_info = _extraction_info(generator.get_trace())
    generation_info["safety_check"] = safety_info
    quality_report = build_record_quality_report(payload.fields, safety, draft=draft)
    return BuildDraftResponse(
        status="draft_built",
        draft=draft,
        safety_check=safety.model_dump(mode="json"),
        quality_report=quality_report,
        generation_info=generation_info,
        export_allowed=False,
    )


@router.post("/quality", response_model=QualityResponse)
def evaluate_record_quality(payload: QualityRequest) -> QualityResponse:
    safety = payload.safety_check
    provider_info = None
    if safety is None and payload.draft:
        generator = _record_generator_or_503()
        safety = generator.safety_check(payload.draft, payload.fields)
        provider_info = _extraction_info(generator.get_trace())
    quality_report = build_record_quality_report(
        payload.fields,
        safety,
        draft=payload.draft,
    )
    return QualityResponse(
        status=quality_report["status"],
        quality_report=quality_report,
        provider_info=provider_info,
    )


@router.post("/generate")
def generate_record(
    payload: GenerateRecordRequest,
    background_tasks: BackgroundTasks,
    request: Request = None,
) -> dict[str, object]:
    ensure_record_provider_available()
    encounter_owner_id = (
        _generation_owner_for_encounter(payload.encounter_id, request)
        if payload.encounter_id is not None
        else None
    )
    orchestrator = MedicalRecordOrchestrator()
    task_id = orchestrator.create_text_task(payload.conversation_text)
    user = current_user_from_request(request)
    if payload.encounter_id is not None:
        try:
            bind_task_to_encounter(
                task_id,
                payload.encounter_id,
                owner_user_id=encounter_owner_id,
                check_in_status="in_progress",
                allow_failed_replacement=True,
            )
        except ValueError as exc:
            update_task(task_id, status="FAILED", current_stage="failed", error_message="Encounter binding rejected; generation was not started")
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    elif user is not None:
        set_task_owner(task_id, user.id)
    background_tasks.add_task(run_record_generation_task, task_id, payload.conversation_text)

    return {
        "task_id": task_id,
        "status": MedicalRecordOrchestrator.STATUS_CREATED,
        "events_url": f"/api/tasks/{task_id}/events",
    }


@router.post("/preview", response_model=PreviewRecordResponse)
def preview_record(payload: PreviewRecordRequest) -> PreviewRecordResponse:
    conversation_text, stable_segments = _stable_preview_input(payload)
    generator = _record_generator_or_503()
    try:
        fields = generator.extract_fields(conversation_text)
    except LLMProviderUnavailableError as exc:
        raise _provider_unavailable_http(str(exc), generator.get_trace()) from exc
    citations = _AudioCitations(conversation_text, stable_segments)
    fields = citations.enrich(fields)
    extraction_info = _extraction_info(generator.get_trace())
    draft = generator.generate_draft(fields)
    draft_info = _extraction_info(generator.get_trace())
    safety = generator.safety_check(draft, fields, allow_export=False)
    safety_info = _extraction_info(generator.get_trace())
    extraction_info["draft_generation"] = draft_info
    extraction_info["safety_check"] = safety_info
    updates = _structured_updates(fields)
    quality_preview = build_record_quality_report(fields, safety, draft=draft)

    return PreviewRecordResponse(
        status="preview_ready",
        source=payload.source,
        preview_notice="实时预览，需医生确认；不会创建正式任务，也不能直接导出。",
        preview_stage=_preview_stage(fields),
        ready_for_formal_generation=_ready_for_formal_generation(fields, conversation_text),
        updated_at=datetime.now(timezone.utc).isoformat(),
        character_count=len(conversation_text),
        segment_count=len(stable_segments),
        fields_preview=fields.model_dump(mode="json"),
        draft_preview=draft,
        candidate_diagnoses=[
            diagnosis.model_dump(mode="json")
            for diagnosis in fields.candidate_diagnoses
        ],
        treatment_plan=_treatment_plan(fields),
        diagnosis_evidence=_diagnosis_evidence(fields),
        evidence_links=_evidence_links(fields, citations),
        structured_updates=updates,
        missing_items=_missing_items(fields),
        safety_preview=safety.model_dump(mode="json"),
        quality_preview=quality_preview,
        extraction_info=extraction_info,
    )
