from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from app.agents import MedicalRecordOrchestrator
from app.schemas import ASRResult, ASRSegment, MedicalRecordFields, SafetyCheckResult, SourceSpan
from app.services import MockLLM, create_llm_record_generator
from app.services.asr.role_quality import build_speaker_role_quality
from app.services.record_quality import build_record_quality_report


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
    creates_task: bool = False
    export_allowed: bool = False


class QualityRequest(BaseModel):
    fields: MedicalRecordFields
    draft: str | None = None
    safety_check: SafetyCheckResult | None = None


class QualityResponse(BaseModel):
    status: str
    quality_report: dict[str, Any]
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


def run_record_generation_task(task_id: int, conversation_text: str) -> None:
    MedicalRecordOrchestrator().run_existing_text_task(task_id, conversation_text)


def _missing_items(fields: MedicalRecordFields) -> list[str]:
    items: list[str] = []
    for key, label in FIELD_LABELS.items():
        field = getattr(fields, key)
        if (
            not _has_real_field_value(field)
            or field.status in {"partial", "negative", "conflicting"}
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


def _matching_source_segments(
    source_text: str,
    segments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    def normalize(value: str) -> str:
        without_role = re.sub(r"^\s*\[[^\]]+\]\s*", "", value or "")
        return re.sub(r"[\s，。！？!?、,]+", "", without_role)

    normalized_source = normalize(source_text)
    if not normalized_source:
        return []
    matches: list[dict[str, Any]] = []
    for index, segment in enumerate(segments):
        segment_text = normalize(str(segment.get("text") or ""))
        if not segment_text:
            continue
        overlap = (
            normalized_source in segment_text
            or segment_text in normalized_source
            or (len(normalized_source) >= 6 and normalized_source[:6] in segment_text)
        )
        if not overlap:
            continue
        matches.append(
            {
                "segment_id": segment.get("segment_id") or f"segment-{index}",
                "index": index,
                "start_time": segment.get("start_time"),
                "end_time": segment.get("end_time"),
                "speaker_id": segment.get("speaker_id") or segment.get("speaker"),
                "role": segment.get("role"),
                "text": segment.get("text") or "",
            }
        )
    return matches


def _segment_lookup(segments: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        str(segment.get("segment_id") or f"segment-{index}"): {
            "segment_id": segment.get("segment_id") or f"segment-{index}",
            "index": index,
            "start_time": segment.get("start_time"),
            "end_time": segment.get("end_time"),
            "speaker_id": segment.get("speaker_id") or segment.get("speaker"),
            "role": segment.get("role"),
            "text": segment.get("text") or "",
        }
        for index, segment in enumerate(segments)
    }


def _matches_for_span(
    span: SourceSpan,
    segments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if span.segment_id:
        match = _segment_lookup(segments).get(str(span.segment_id))
        if match:
            return [match]
    return _matching_source_segments(span.text, segments)


def _source_segment_ids_for_span(span: SourceSpan, segments: list[dict[str, Any]]) -> list[str]:
    return [
        str(item["segment_id"])
        for item in _matches_for_span(span, segments)
        if item.get("segment_id")
    ]


def _source_segment_ids(source_text: str, segments: list[dict[str, Any]]) -> list[str]:
    return [
        str(item["segment_id"])
        for item in _matching_source_segments(source_text, segments)
        if item.get("segment_id")
    ]


def _enrich_span(span: SourceSpan, segments: list[dict[str, Any]]) -> SourceSpan:
    if span.segment_id:
        return span
    matches = _matching_source_segments(span.text, segments)
    if not matches:
        return span
    match = matches[0]
    return span.model_copy(
        update={
            "segment_id": match.get("segment_id"),
            "index": span.index if span.index is not None else match.get("index"),
            "start_time": span.start_time if span.start_time is not None else match.get("start_time"),
            "end_time": span.end_time if span.end_time is not None else match.get("end_time"),
        }
    )


def _enrich_spans(spans: list[SourceSpan], segments: list[dict[str, Any]]) -> list[SourceSpan]:
    return [_enrich_span(span, segments) for span in spans]


def _enrich_field_evidence(
    fields: MedicalRecordFields,
    segments: list[dict[str, Any]],
) -> MedicalRecordFields:
    if not segments:
        return fields
    enriched = fields.model_copy(deep=True)
    for key in FIELD_LABELS:
        field = getattr(enriched, key)
        field.source_spans = _enrich_spans(field.source_spans, segments)
    for diagnosis in enriched.candidate_diagnoses:
        diagnosis.evidence = _enrich_spans(diagnosis.evidence, segments)
    return enriched


def _structured_updates(
    fields: MedicalRecordFields,
    segments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    updates: list[dict[str, Any]] = []
    for key, label in FIELD_LABELS.items():
        field = getattr(fields, key)
        value = field.value or ""
        source_text = field.source_spans[0].text if field.source_spans else ""
        source_segment_ids = (
            _source_segment_ids_for_span(field.source_spans[0], segments)
            if field.source_spans
            else []
        )
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
                "source_segment_ids": source_segment_ids or _source_segment_ids(source_text, segments),
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
                "source_segment_ids": _source_segment_ids(diagnosis_source, segments),
                "notice": "候选结果，需医生确认",
            }
        )
    return updates


def _evidence_links(
    fields: MedicalRecordFields,
    segments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    links: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for key, label in FIELD_LABELS.items():
        field = getattr(fields, key)
        for span in field.source_spans:
            for match in _matches_for_span(span, segments):
                identity = (label, str(match.get("segment_id") or ""))
                if identity in seen:
                    continue
                seen.add(identity)
                links.append({"label": label, "evidence": span.text, **match})
    for diagnosis in fields.candidate_diagnoses:
        for span in diagnosis.evidence:
            for match in _matches_for_span(span, segments):
                label = f"候选诊断：{diagnosis.name}"
                identity = (label, str(match.get("segment_id") or ""))
                if identity in seen:
                    continue
                seen.add(identity)
                links.append({"label": label, "evidence": span.text, **match})
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
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Speaker role quality gate did not pass.",
                "role_quality": quality.model_dump(mode="json"),
            },
        )


def _extract_fields_for_service(
    conversation_text: str,
    segments: list[dict[str, Any]],
) -> tuple[MedicalRecordFields, dict[str, Any]]:
    generator = create_llm_record_generator()
    fields = generator.extract_fields(conversation_text)
    fields = _enrich_field_evidence(fields, _stable_segments_for_external_api(segments))
    return fields, _extraction_info(generator.get_trace())


def _extraction_info(trace: dict[str, Any] | None) -> dict[str, Any]:
    trace = trace or {}
    return {
        "requested_provider": trace.get("llm_provider") or "mock",
        "actual_provider": trace.get("actual_provider") or trace.get("llm_provider") or "mock",
        "model": trace.get("model") or "mock-deterministic-extractor",
        "fallback": bool(trace.get("fallback", False)),
        "fallback_reason": trace.get("fallback_reason"),
        "extraction_mode": "clinical_fact_rules_v1",
    }


@router.post("/extract-fields", response_model=ExtractFieldsResponse)
def extract_fields(payload: ExtractFieldsRequest) -> ExtractFieldsResponse:
    stable_segments = _stable_segments_for_external_api(payload.segments)
    _require_segments_role_quality(payload.conversation_text, stable_segments)
    fields, extraction_info = _extract_fields_for_service(payload.conversation_text, stable_segments)
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
        evidence_links=_evidence_links(fields, stable_segments),
        quality_report=quality_report,
        extraction_info=extraction_info,
    )


@router.post("/build-draft", response_model=BuildDraftResponse)
def build_draft(payload: BuildDraftRequest) -> BuildDraftResponse:
    llm = MockLLM()
    draft = llm.generate_draft(payload.fields)
    safety = llm.safety_check(draft, payload.fields, allow_export=payload.allow_export)
    quality_report = build_record_quality_report(payload.fields, safety, draft=draft)
    return BuildDraftResponse(
        status="draft_built",
        draft=draft,
        safety_check=safety.model_dump(mode="json"),
        quality_report=quality_report,
        export_allowed=False,
    )


@router.post("/quality", response_model=QualityResponse)
def evaluate_record_quality(payload: QualityRequest) -> QualityResponse:
    safety = payload.safety_check
    if safety is None and payload.draft:
        safety = MockLLM().safety_check(payload.draft, payload.fields)
    quality_report = build_record_quality_report(
        payload.fields,
        safety,
        draft=payload.draft,
    )
    return QualityResponse(
        status=quality_report["status"],
        quality_report=quality_report,
    )


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
    conversation_text, stable_segments = _stable_preview_input(payload)
    generator = create_llm_record_generator()
    fields = generator.extract_fields(conversation_text)
    fields = _enrich_field_evidence(fields, stable_segments)
    extraction_info = _extraction_info(generator.get_trace())
    llm = MockLLM()
    draft = llm.generate_draft(fields)
    safety = llm.safety_check(draft, fields, allow_export=False)
    updates = _structured_updates(fields, stable_segments)
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
        evidence_links=_evidence_links(fields, stable_segments),
        structured_updates=updates,
        missing_items=_missing_items(fields),
        safety_preview=safety.model_dump(mode="json"),
        quality_preview=quality_preview,
        extraction_info=extraction_info,
    )
