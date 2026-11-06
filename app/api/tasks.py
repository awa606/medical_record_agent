from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field, ValidationError

from app.api.auth import assert_owner_or_admin, current_user_from_request, require_current_user
from app.db import (
    StaleRecordRevisionError,
    apply_review_revision_transaction,
    create_approval_for_task,
    create_audit_log,
    create_export_event_for_task,
    get_active_approval_for_task,
    get_audit_logs,
    get_record_revision,
    get_task,
    get_task_encounter,
    get_task_steps,
    json_dumps,
    list_approval_items_for_approval,
    record_content_hash,
    update_task,
)
from app.schemas import MedicalRecordFields, SafetyCheckResult
from app.services import LLMProviderUnavailableError, create_llm_record_generator, export_record
from app.services.agent_trace import build_agent_trace, load_asr_result_for_audio
from app.services.exporter import DEFAULT_OUTPUT_DIR


router = APIRouter(prefix="/tasks", tags=["tasks"], dependencies=[Depends(require_current_user)])
TERMINAL_EVENTS = {"WAITING_DOCTOR_REVIEW", "FAILED"}
EXPORT_DOWNLOADS = {
    "markdown": {
        "path_key": "markdown_path",
        "extension": "md",
        "media_type": "text/markdown; charset=utf-8",
    },
    "docx": {
        "path_key": "word_path",
        "extension": "docx",
        "media_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    },
}


class ReviewRequest(BaseModel):
    fields: MedicalRecordFields
    expected_revision_id: int
    expected_content_hash: str
    manual_takeover_fields: list[str] = Field(default_factory=list)
    source_corrected_fields: list[str] = Field(default_factory=list)


class FieldApprovalItem(BaseModel):
    key: str
    action: Literal[
        "confirm_content",
        "keep_pending",
        "confirm_not_asked",
        "accept_missing",
    ]
    note: str | None = None


class DiagnosisApprovalItem(BaseModel):
    index: int
    action: Literal["confirm_candidate", "delete_ai_candidate", "keep_pending"]
    high_risk_confirmed: bool = False
    note: str | None = None


class HighRiskConflictApprovalItem(BaseModel):
    key: str
    confirmed: bool
    note: str | None = None


class TaskApprovalRequest(BaseModel):
    revision_id: int
    content_hash: str
    confirm_all_regular_fields: bool = False
    fields: list[FieldApprovalItem] = Field(default_factory=list)
    diagnoses: list[DiagnosisApprovalItem] = Field(default_factory=list)
    high_risk_conflicts: list[HighRiskConflictApprovalItem] = Field(default_factory=list)


class ExportReadinessResponse(BaseModel):
    task_id: int
    ready: bool
    blocked: bool
    errors: list[str]
    next_action: str
    current_stage: str | None = None
    exports: dict[str, str] | None = None
    revision_id: int | None = None
    revision_number: int | None = None
    content_hash: str | None = None
    approval_id: int | None = None
    pending_review_count: int = 0


def _decode_result_json(task: dict[str, Any]) -> dict[str, Any]:
    result_json = task.get("result_json")
    if result_json:
        task["result_json"] = json.loads(result_json)
    return task


def _decode_step_json(step: dict[str, Any]) -> dict[str, Any]:
    for key in ("input_snapshot_json", "output_snapshot_json"):
        snapshot = step.get(key)
        if snapshot:
            step[key] = json.loads(snapshot)
    return step


def _assert_task_access(
    task: dict[str, Any],
    request: Request | None,
    *,
    high_risk_operation: bool = False,
) -> None:
    owner_user_id = task.get("owner_user_id")
    assert_owner_or_admin(
        int(owner_user_id) if owner_user_id is not None else None,
        request,
        resource_name="task",
    )
    user = current_user_from_request(request)
    if user is None:
        return

    encounter = get_task_encounter(int(task["id"]))
    if encounter is None:
        return
    task_encounter_id = task.get("encounter_id")
    if task_encounter_id is not None and int(task_encounter_id) != int(encounter["id"]):
        if user.role == "admin" and not high_risk_operation:
            return
        raise HTTPException(
            status_code=409 if high_risk_operation else 403,
            detail="Task encounter link is inconsistent",
        )
    encounter_task_id = encounter.get("task_id")
    if encounter_task_id is not None and int(encounter_task_id) != int(task["id"]):
        if user.role == "admin" and not high_risk_operation:
            return
        raise HTTPException(
            status_code=409 if high_risk_operation else 403,
            detail="Encounter task link is inconsistent",
        )
    encounter_doctor_id = encounter.get("doctor_user_id")
    if encounter_doctor_id is None:
        if high_risk_operation:
            raise HTTPException(status_code=409, detail="Task encounter has no doctor owner")
        if user.role != "admin":
            raise HTTPException(status_code=403, detail="You are not allowed to access this task encounter")
        return
    if user.role != "admin" and int(encounter_doctor_id) != user.id:
        raise HTTPException(status_code=403, detail="You are not allowed to access this task encounter")
    if owner_user_id is None:
        if high_risk_operation:
            raise HTTPException(status_code=409, detail="Task has no owner")
        return
    if int(owner_user_id) != int(encounter_doctor_id):
        if user.role == "admin" and not high_risk_operation:
            return
        raise HTTPException(
            status_code=409 if high_risk_operation else 403,
            detail="Task owner does not match encounter doctor",
        )


def _actor_detail(request: Request | None) -> dict[str, Any]:
    user = current_user_from_request(request)
    if user is None:
        return {}
    return {
        "actor_user_id": user.id,
        "actor_role": user.role,
        "actor_username": user.username,
    }


def _load_task_result(
    task_id: int,
    request: Request | None = None,
    *,
    high_risk_operation: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    task = get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    _assert_task_access(task, request, high_risk_operation=high_risk_operation)
    decoded_task = _decode_result_json(task)
    result = decoded_task.get("result_json")
    if not isinstance(result, dict):
        raise HTTPException(status_code=400, detail="Task has no generated result")
    return decoded_task, result


def _save_task_result(
    task_id: int,
    result: dict[str, Any],
    *,
    current_stage: str,
    event_type: str,
    event_detail: dict[str, Any],
    request: Request | None = None,
) -> None:
    update_task(
        task_id,
        current_stage=current_stage,
        result_json=json_dumps(result),
    )
    create_audit_log(task_id, event_type, {**event_detail, **_actor_detail(request)})


def _record_generator_or_503():
    try:
        return create_llm_record_generator()
    except LLMProviderUnavailableError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "message": "Requested record generation provider is unavailable.",
                "fallback": False,
                "fallback_reason": str(exc),
            },
        ) from exc


FIELD_LABELS = {
    "chief_complaint": "主诉",
    "present_illness": "现病史",
    "previous_treatment": "既往处理",
    "accompanying_symptoms": "伴随症状",
    "past_history": "既往史",
    "allergy_history": "过敏史",
    "physical_exam": "查体",
}

MANUAL_DOCTOR_EDIT_NOTE = "manual_doctor_edit_v1: 医生手工修改；原始转写证据仅供对照，不作为该修改的自动证据。"


def _field_items(fields: MedicalRecordFields) -> list[tuple[str, str, Any]]:
    return [
        ("chief_complaint", "主诉", fields.chief_complaint),
        ("present_illness", "现病史", fields.present_illness),
        ("previous_treatment", "既往处理", fields.previous_treatment),
        ("accompanying_symptoms", "伴随症状", fields.accompanying_symptoms),
        ("past_history", "既往史", fields.past_history),
        ("allergy_history", "过敏史", fields.allergy_history),
        ("physical_exam", "查体", fields.physical_exam),
    ]


def _field_by_key(fields: MedicalRecordFields, key: str):
    if key not in FIELD_LABELS:
        raise HTTPException(status_code=422, detail=f"未知病历字段：{key}")
    return getattr(fields, key)


def _has_confirmable_content(field: Any) -> bool:
    return bool(field and not field.missing and field.value)


def _reset_review_state(fields: MedicalRecordFields) -> MedicalRecordFields:
    for _key, _label, field in _field_items(fields):
        field.confirmed_by_doctor = False
        field.doctor_review_status = "pending"
        field.high_risk_confirmed_by_doctor = False
        field.doctor_review_note = None
    for diagnosis in fields.candidate_diagnoses:
        diagnosis.confirmed_by_doctor = False
        diagnosis.doctor_review_status = "pending"
        diagnosis.deleted_by_doctor = False
        diagnosis.high_risk_confirmed_by_doctor = False
        diagnosis.doctor_review_note = None
    return fields


def _mark_manual_doctor_edits(
    fields: MedicalRecordFields,
    previous_fields: MedicalRecordFields | None,
    *,
    manual_takeover_fields: list[str] | None = None,
    source_corrected_fields: list[str] | None = None,
) -> list[str]:
    if previous_fields is None:
        return []
    changed: list[str] = []
    manual = set(manual_takeover_fields or [])
    corrected = set(source_corrected_fields or [])
    for key, _label, field in _field_items(fields):
        previous = getattr(previous_fields, key)
        current_value = str(field.value or "").strip()
        previous_value = str(previous.value or "").strip()
        content_changed = current_value != previous_value or bool(field.missing) != bool(previous.missing)
        if key in corrected:
            # Validate doctor-selected evidence as evidence, never as a manual
            # exemption from grounding. The provenance note is set afterwards.
            field.doctor_review_note = None
            changed.append(key)
            continue
        if key in manual:
            field.source_spans = []
            field.fact_ids = []
            field.confidence = None
            field.status = "missing" if field.missing else "partial"
            field.doctor_review_note = "manual_doctor_edit_v1: 医生补录；新内容为人工来源，原模型内容和错误引用保留在旧版本。"
            changed.append(key)
            continue
        if not content_changed:
            # Only the server's previous revision can carry manual provenance.
            # A later edit to another field must not lose this source marker.
            field.doctor_review_note = previous.doctor_review_note
            field.source_spans = [span.model_copy(deep=True) for span in previous.source_spans]
            field.status = previous.status
            continue
        if previous.status == "conflicting":
            field.source_spans = [span.model_copy(deep=True) for span in previous.source_spans]
            field.status = "conflicting"
            field.hint = "请根据原文修正，或明确选择医生补录；原模型冲突仍保留。"
            continue
        # Normal editing may clear client citations. Restore only that empty
        # case from the immediately previous server state, for comparison only.
        # Nonempty typed quotes retain their existing grounding checks; never
        # infer missing quotes from older revision history.
        if not field.source_spans:
            field.source_spans = [span.model_copy(deep=True) for span in previous.source_spans]
        field.doctor_review_note = MANUAL_DOCTOR_EDIT_NOTE
        changed.append(key)
    return changed


def _retained_source_corrections(
    fields: MedicalRecordFields,
    previous: MedicalRecordFields | None,
    trace: dict[str, Any],
) -> set[str]:
    """Carry successful source correction only from unchanged server history.

    Inspect submitted values/citations before _mark_manual_doctor_edits restores
    any prior citations. A client note cannot establish this provenance.
    """
    if previous is None:
        return set()
    history = trace.get("field_resolution_history") or []
    retained = set()
    for key in ("chief_complaint", "present_illness"):
        old, new = getattr(previous, key), getattr(fields, key)
        if (old.status == "conflicting"
                or not str(old.doctor_review_note or "").startswith("doctor_source_correction_v1:")
                or (old.value, old.missing, old.fact_ids) != (new.value, new.missing, new.fact_ids)
                or [s.model_dump() for s in old.source_spans] != [s.model_dump() for s in new.source_spans]):
            continue
        if any(isinstance(item, dict) and item.get("field") == key
               and item.get("method") == "source_correction" and item.get("value") == old.value
               for item in history):
            retained.add(key)
    return retained


def _validate_field_resolutions(payload: ReviewRequest, previous: MedicalRecordFields | None) -> None:
    manual, corrected = payload.manual_takeover_fields, payload.source_corrected_fields
    if (len(manual) != len(set(manual)) or len(corrected) != len(set(corrected))
            or set(manual) & set(corrected) or (set(manual) | set(corrected)) - set(FIELD_LABELS)):
        raise HTTPException(status_code=422, detail="字段处置声明包含未知、重复或相互冲突的字段。")
    if not manual and not corrected:
        return
    if previous is None:
        raise HTTPException(status_code=422, detail="没有可核对的原病历版本，不能声明字段处置。")
    for key in manual + corrected:
        old, new = getattr(previous, key), getattr(payload.fields, key)
        value_changed = (str(old.value or "").strip(), old.missing) != (str(new.value or "").strip(), new.missing)
        evidence_changed = [s.model_dump() for s in old.source_spans] != [s.model_dump() for s in new.source_spans]
        if not value_changed and (key in manual or not evidence_changed):
            raise HTTPException(status_code=422, detail=f"{FIELD_LABELS[key]}没有实际修正，不能仅勾选消除冲突。")
        if key in corrected and (new.missing or not new.value or not new.source_spans):
            raise HTTPException(status_code=422, detail=f"{FIELD_LABELS[key]}原文修正必须提供内容及可核验引用。")


def _current_revision_or_error(task: dict[str, Any]) -> dict[str, Any]:
    revision_id = task.get("current_record_revision_id")
    if revision_id is None:
        raise HTTPException(status_code=409, detail="当前任务尚未创建病历版本，请先生成或保存病历。")
    revision = get_record_revision(int(revision_id))
    if revision is None:
        raise HTTPException(status_code=409, detail="当前病历版本不存在，请刷新后重试。")
    return revision


def _revision_content_hash(revision: dict[str, Any]) -> str:
    current = revision.get("content_hash")
    if current:
        return str(current)
    try:
        result = json.loads(revision.get("result_json") or "{}")
    except json.JSONDecodeError:
        result = {}
    return record_content_hash(result)


def _assert_approval_matches_revision(payload: TaskApprovalRequest, revision: dict[str, Any]) -> str:
    revision_id = int(revision["id"])
    content_hash = _revision_content_hash(revision)
    if payload.revision_id != revision_id:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "病历版本已更新，请刷新后重新审核。",
                "current_revision_id": revision_id,
                "submitted_revision_id": payload.revision_id,
            },
        )
    if payload.content_hash != content_hash:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "病历内容已变化，请刷新后重新审核。",
                "current_revision_id": revision_id,
                "content_hash": content_hash,
            },
        )
    return content_hash


def _apply_field_approval(fields: MedicalRecordFields, item: FieldApprovalItem) -> dict[str, Any] | None:
    if item.action == "keep_pending":
        return None
    field = _field_by_key(fields, item.key)
    if item.action == "confirm_content":
        if not _has_confirmable_content(field):
            raise HTTPException(status_code=422, detail=f"{FIELD_LABELS[item.key]}没有可确认内容")
        field.confirmed_by_doctor = True
        field.doctor_review_status = "content_confirmed"
    elif item.action == "confirm_not_asked":
        field.confirmed_by_doctor = True
        field.doctor_review_status = "not_asked_confirmed"
    elif item.action == "accept_missing":
        field.confirmed_by_doctor = True
        field.doctor_review_status = "missing_accepted"
    source_note = str(field.doctor_review_note or "")
    if source_note.startswith(("manual_doctor_edit_v1:", "doctor_source_correction_v1:")):
        # Approval must not erase the server-established source of a doctor's
        # correction, otherwise a later revision loses its provenance.
        if item.note:
            field.doctor_review_note = source_note + "；审核说明：" + item.note
    else:
        field.doctor_review_note = item.note
    return {
        "item_type": "field",
        "item_key": item.key,
        "action": item.action,
        "status": "completed",
        "note": item.note,
    }


def _apply_diagnosis_approval(fields: MedicalRecordFields, item: DiagnosisApprovalItem) -> dict[str, Any] | None:
    if item.action == "keep_pending":
        return None
    if item.index < 0 or item.index >= len(fields.candidate_diagnoses):
        raise HTTPException(status_code=422, detail=f"候选诊断序号不存在：{item.index}")
    diagnosis = fields.candidate_diagnoses[item.index]
    if item.action == "confirm_candidate":
        diagnosis.confirmed_by_doctor = True
        diagnosis.doctor_review_status = "candidate_confirmed"
        diagnosis.deleted_by_doctor = False
    elif item.action == "delete_ai_candidate":
        diagnosis.confirmed_by_doctor = True
        diagnosis.doctor_review_status = "ai_candidate_deleted"
        diagnosis.deleted_by_doctor = True
    diagnosis.high_risk_confirmed_by_doctor = bool(item.high_risk_confirmed)
    diagnosis.doctor_review_note = item.note
    return {
        "item_type": "candidate_diagnosis",
        "item_key": str(item.index),
        "action": item.action,
        "status": "completed",
        "high_risk_confirmed": bool(item.high_risk_confirmed),
        "note": item.note,
    }


def _apply_high_risk_approval(
    fields: MedicalRecordFields,
    item: HighRiskConflictApprovalItem,
) -> dict[str, Any] | None:
    if not item.confirmed:
        return None
    if item.key.startswith("diagnosis:"):
        try:
            index = int(item.key.split(":", 1)[1])
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"高风险项标识无效：{item.key}") from exc
        if index < 0 or index >= len(fields.candidate_diagnoses):
            raise HTTPException(status_code=422, detail=f"高风险候选诊断不存在：{item.key}")
        fields.candidate_diagnoses[index].high_risk_confirmed_by_doctor = True
    elif item.key.startswith("field:"):
        key = item.key.split(":", 1)[1]
        _field_by_key(fields, key).high_risk_confirmed_by_doctor = True
    return {
        "item_type": "high_risk",
        "item_key": item.key,
        "action": "confirm_high_risk",
        "status": "completed",
        "high_risk_confirmed": True,
        "note": item.note,
    }


def _approval_completion_errors(fields: MedicalRecordFields) -> list[str]:
    errors: list[str] = []
    unconfirmed_fields: list[str] = []
    unresolved_missing: list[str] = []
    for key, label, field in _field_items(fields):
        if _has_confirmable_content(field):
            if field.doctor_review_status != "content_confirmed" or not field.confirmed_by_doctor:
                unconfirmed_fields.append(label)
        else:
            if field.doctor_review_status not in {"not_asked_confirmed", "missing_accepted"}:
                unresolved_missing.append(label)
        if field.status == "conflicting":
            errors.append(f"{label}存在证据冲突，必须先修正内容和证据。")
    if unconfirmed_fields:
        errors.append(f"存在未显式确认的普通字段：{'、'.join(unconfirmed_fields)}。")
    if unresolved_missing:
        errors.append(f"存在未处理缺失项：{'、'.join(unresolved_missing)}。")

    pending_diagnoses: list[str] = []
    unconfirmed_risks: list[str] = []
    for index, diagnosis in enumerate(fields.candidate_diagnoses):
        if diagnosis.doctor_review_status not in {"candidate_confirmed", "ai_candidate_deleted"}:
            pending_diagnoses.append(diagnosis.name or f"候选{index + 1}")
        if diagnosis.risk_warnings and not diagnosis.high_risk_confirmed_by_doctor:
            unconfirmed_risks.append(diagnosis.name or f"候选{index + 1}")
    if pending_diagnoses:
        errors.append(f"存在未处理 AI 候选诊断：{'、'.join(pending_diagnoses)}。")
    if unconfirmed_risks:
        errors.append(f"存在未单独确认的高风险项：{'、'.join(unconfirmed_risks)}。")
    return errors


def _approval_review_state(fields: MedicalRecordFields) -> tuple[list[dict[str, Any]], list[str]]:
    items: list[dict[str, Any]] = []
    for key, _label, field in _field_items(fields):
        if field.confirmed_by_doctor and field.doctor_review_status != "pending":
            items.append(
                {
                    "item_type": "field",
                    "item_key": key,
                    "action": field.doctor_review_status,
                    "status": "completed",
                    "high_risk_confirmed": field.high_risk_confirmed_by_doctor,
                    "note": field.doctor_review_note,
                }
            )
    for index, diagnosis in enumerate(fields.candidate_diagnoses):
        if diagnosis.doctor_review_status != "pending":
            items.append(
                {
                    "item_type": "candidate_diagnosis",
                    "item_key": str(index),
                    "action": diagnosis.doctor_review_status,
                    "status": "completed",
                    "high_risk_confirmed": diagnosis.high_risk_confirmed_by_doctor,
                    "note": diagnosis.doctor_review_note,
                }
            )
    return items, _approval_completion_errors(fields)


@router.get("/{task_id}")
def read_task(task_id: int, request: Request = None) -> dict[str, Any]:
    task = get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    _assert_task_access(task, request)
    return _decode_result_json(task)


@router.get("/{task_id}/steps")
def read_task_steps(task_id: int, request: Request = None) -> list[dict[str, Any]]:
    task = get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    _assert_task_access(task, request)
    return [_decode_step_json(step) for step in get_task_steps(task_id)]


@router.get("/{task_id}/trace")
def read_task_agent_trace(
    task_id: int,
    request: Request = None,
    audio_id: str | None = Query(default=None),
) -> dict[str, Any]:
    task = get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    _assert_task_access(task, request)

    decoded_task = _decode_result_json(task)
    decoded_steps = [_decode_step_json(step) for step in get_task_steps(task_id)]
    asr_result = load_asr_result_for_audio(audio_id)
    return build_agent_trace(
        task=decoded_task,
        steps=decoded_steps,
        asr_result=asr_result,
    )


@router.post("/{task_id}/review")
def review_task(
    task_id: int,
    payload: dict[str, Any] | None = Body(default=None),
    request: Request = None,
) -> dict[str, Any]:
    task, result = _load_task_result(task_id, request, high_risk_operation=True)
    try:
        review_payload = ReviewRequest.model_validate(payload or {})
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc

    revision = _current_revision_or_error(task)
    if (review_payload.expected_revision_id != int(revision["id"])
            or review_payload.expected_content_hash != _revision_content_hash(revision)):
        raise HTTPException(status_code=409, detail={
            "error_code": "stale_record_revision",
            "expected_revision_id": review_payload.expected_revision_id,
            "current_revision_id": int(revision["id"]),
            "current_content_hash": _revision_content_hash(revision),
            "message": "病历版本已更新，请加载最新版本后保存；本地修改仍保留。",
        })
    # The transaction below repeats this check atomically against concurrent
    # saves. This early check prevents stale resolution declarations from
    # being judged against a different doctor's revision.
    try:
        previous_fields = MedicalRecordFields.model_validate(result.get("fields") or {})
    except ValidationError:
        previous_fields = None
    _validate_field_resolutions(review_payload, previous_fields)
    fields = _reset_review_state(review_payload.fields)
    trusted_source_corrections = set(review_payload.source_corrected_fields) | _retained_source_corrections(
        fields, previous_fields, result.get("llm_trace") or {},
    )
    manual_edited_fields = _mark_manual_doctor_edits(
        fields, previous_fields,
        manual_takeover_fields=review_payload.manual_takeover_fields,
        source_corrected_fields=review_payload.source_corrected_fields,
    )
    coverage_source = None
    if os.getenv("RECORD_PROVIDER_MODE", "demo") in {"live", "edge"}:
        from app.services.field_grounding import ground_fields
        from app.services.privacy import anonymize_text
        coverage_source = anonymize_text(task.get("input_text") or result.get("conversation_text") or "")
        fields = ground_fields(fields, coverage_source,
                               (result.get("asr_source") or {}).get("segments"),
                               source_corrected_fields=trusted_source_corrections)
    if previous_fields:
        resolved = set(review_payload.manual_takeover_fields + review_payload.source_corrected_fields)
        for key, _label, field in _field_items(fields):
            if getattr(previous_fields, key).status == "conflicting" and key not in resolved:
                field.status = "conflicting"
                field.hint = "原模型冲突尚未处置，请选择根据原文修正或医生补录后保存。"
    for key in review_payload.source_corrected_fields:
        getattr(fields, key).doctor_review_note = "doctor_source_correction_v1: 医生根据原文修正，已重新校验证据；需审核当前版本。"
    from app.services.field_alignment import refresh_existing_coverage_hints
    fields = refresh_existing_coverage_hints(fields, source=coverage_source)
    generator = _record_generator_or_503()
    draft = generator.generate_draft(fields)
    safety_check = generator.safety_check(draft, fields)

    result["fields"] = fields.model_dump()
    result["draft"] = draft
    result["safety_check"] = safety_check.model_dump()
    prior_trace = result.get("llm_trace") or {}
    review_trace = generator.get_trace()
    result["llm_trace"] = {**prior_trace, "review_components": review_trace}
    if not prior_trace:
        result["llm_trace"].update(review_trace)
    result["reviewed"] = True
    result["approved"] = False
    if manual_edited_fields:
        result["llm_trace"]["manual_edited_fields"] = manual_edited_fields
    resolutions = [
        {"field": key, "method": method, "previous_revision_id": review_payload.expected_revision_id,
         "previous_value": getattr(previous_fields, key).value,
         "previous_source_spans": [s.model_dump() for s in getattr(previous_fields, key).source_spans],
         "value": getattr(fields, key).value}
        for method, keys in (("doctor_entry", review_payload.manual_takeover_fields),
                             ("source_correction", review_payload.source_corrected_fields))
        for key in keys
    ]
    if resolutions:
        result["llm_trace"]["field_resolution_history"] = [
            *(prior_trace.get("field_resolution_history") or []), *resolutions,
        ]
    from app.services.record_quality import build_record_quality_report
    result["quality_report"] = build_record_quality_report(fields, safety_check, draft=draft)

    actor = current_user_from_request(request)
    try:
        updated_task = apply_review_revision_transaction(
            task_id,
            result,
            expected_revision_id=review_payload.expected_revision_id,
            expected_content_hash=review_payload.expected_content_hash,
            actor_user_id=actor.id if actor else None,
            status="WAITING_DOCTOR_REVIEW",
            current_stage="waiting_doctor_review",
            source="doctor_review",
            workflow_status="waiting_review",
            event_type="doctor_review_saved",
            event_detail={"task_id": task_id, "manual_edited_fields": manual_edited_fields,
                          "field_resolutions": [{"field": r["field"], "method": r["method"]} for r in resolutions],
                          **_actor_detail(request)},
        )
    except StaleRecordRevisionError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error_code": "stale_record_revision",
                "expected_revision_id": exc.expected_revision_id,
                "current_revision_id": exc.current_revision_id,
                "current_content_hash": exc.current_content_hash,
                "message": "Record revision is stale; reload the latest record before saving.",
            },
        ) from exc
    updated_task["result_json"] = result
    return updated_task


@router.post("/{task_id}/approve")
def approve_task(
    task_id: int,
    payload: TaskApprovalRequest | None = Body(default=None),
    request: Request = None,
) -> dict[str, Any]:
    if payload is None:
        raise HTTPException(status_code=400, detail="审核请求不能为空，请显式提交分项审核结果。")
    task, result = _load_task_result(task_id, request, high_risk_operation=True)
    if task.get("current_stage") == "approved" and get_active_approval_for_task(task_id) is not None:
        raise HTTPException(status_code=409, detail="Current record revision is already approved")
    revision = _current_revision_or_error(task)
    content_hash = _assert_approval_matches_revision(payload, revision)
    fields = MedicalRecordFields.model_validate(result["fields"])

    approval_items: list[dict[str, Any]] = []
    if payload.confirm_all_regular_fields:
        for key, _label, field in _field_items(fields):
            if _has_confirmable_content(field) and field.status != "conflicting":
                field.confirmed_by_doctor = True
                field.doctor_review_status = "content_confirmed"
                approval_items.append(
                    {
                        "item_type": "field",
                        "item_key": key,
                        "action": "confirm_content",
                        "status": "completed",
                    }
                )
    for item in payload.fields:
        applied = _apply_field_approval(fields, item)
        if applied:
            approval_items.append(applied)
    for item in payload.diagnoses:
        applied = _apply_diagnosis_approval(fields, item)
        if applied:
            approval_items.append(applied)
    for item in payload.high_risk_conflicts:
        applied = _apply_high_risk_approval(fields, item)
        if applied:
            approval_items.append(applied)

    errors = _approval_completion_errors(fields)
    if errors:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "病历分项审核尚未完成。",
                "errors": errors,
                "revision_id": int(revision["id"]),
                "content_hash": content_hash,
            },
        )

    result["fields"] = fields.model_dump()
    result["approved"] = True
    try:
        approval = create_approval_for_task(
            task_id,
            actor_user_id=current_user_from_request(request).id if current_user_from_request(request) else None,
            content_hash=content_hash,
            approval_items=approval_items,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    result["record_revision"] = {
        "id": revision["id"],
        "revision_no": revision["revision_no"],
        "source": revision["source"],
        "content_hash": content_hash,
    }
    result["approval"] = {
        "id": approval["id"],
        "revision_id": approval["revision_id"],
        "content_hash": approval.get("content_hash"),
        "approved_by_user_id": approval["approved_by_user_id"],
        "created_at": approval["created_at"],
    }
    result["approval_summary"] = {
        "item_count": len(approval_items),
        "items": approval_items,
    }

    _save_task_result(
        task_id,
        result,
        current_stage="approved",
        event_type="doctor_approved",
        event_detail={"task_id": task_id},
        request=request,
    )
    task["result_json"] = result
    task["current_stage"] = "approved"
    return task


@router.post("/{task_id}/export")
def export_task(task_id: int, request: Request = None) -> dict[str, Any]:
    task, result = _load_task_result(task_id, request, high_risk_operation=True)
    approval = get_active_approval_for_task(task_id)
    readiness = _build_export_readiness(
        task_id,
        result,
        current_stage=task.get("current_stage"),
        active_approval=approval,
        current_revision=_current_revision_or_error(task),
    )
    if readiness["errors"]:
        raise HTTPException(status_code=400, detail=readiness)

    try:
        exports = export_record(task_id, result)
    except Exception as exc:
        create_audit_log(
            task_id,
            "export_failed",
            {"task_id": task_id, "error": str(exc), **_actor_detail(request)},
        )
        raise HTTPException(status_code=500, detail=f"导出失败：{exc}") from exc

    result["exports"] = exports
    export_event = create_export_event_for_task(
        task_id,
        approval_id=int(approval["id"]),
        actor_user_id=current_user_from_request(request).id if current_user_from_request(request) else None,
        exports=exports,
    )
    result["export_event"] = {
        "id": export_event["id"],
        "revision_id": export_event["revision_id"],
        "approval_id": export_event["approval_id"],
        "exported_by_user_id": export_event["exported_by_user_id"],
        "created_at": export_event["created_at"],
    }
    _save_task_result(
        task_id,
        result,
        current_stage="exported",
        event_type="export_completed",
        event_detail={"task_id": task_id, **exports},
        request=request,
    )
    task["result_json"] = result
    task["current_stage"] = "exported"
    export_readiness = _build_export_readiness(
        task_id,
        result,
        current_stage="exported",
        active_approval=approval,
        current_revision=_current_revision_or_error(task),
    )
    return {"task_id": task_id, "exports": exports, "export_readiness": export_readiness}


@router.get("/{task_id}/export-readiness", response_model=ExportReadinessResponse)
def read_export_readiness(task_id: int, request: Request = None) -> ExportReadinessResponse:
    task, result = _load_task_result(task_id, request, high_risk_operation=True)
    return ExportReadinessResponse(
        **_build_export_readiness(
            task_id,
            result,
            current_stage=task.get("current_stage"),
            active_approval=get_active_approval_for_task(task_id),
            current_revision=_current_revision_or_error(task),
        )
    )


def _export_output_root() -> Path:
    return Path(os.environ.get("MEDICAL_RECORD_AGENT_OUTPUT_DIR", DEFAULT_OUTPUT_DIR)).resolve()


def _resolve_export_download_path(exports: dict[str, str], export_format: str) -> tuple[Path, str, str]:
    config = EXPORT_DOWNLOADS.get(export_format)
    if config is None:
        raise HTTPException(status_code=404, detail="Export format not found")

    raw_path = exports.get(config["path_key"])
    if not raw_path:
        raise HTTPException(status_code=404, detail="Export file not found")

    output_root = _export_output_root()
    export_path = Path(raw_path).resolve()
    try:
        export_path.relative_to(output_root)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail="Stored export path is outside the output directory") from exc

    if not export_path.is_file():
        raise HTTPException(status_code=404, detail="Export file not found")

    return export_path, config["extension"], config["media_type"]


@router.get("/{task_id}/exports/{export_format}")
def download_task_export(task_id: int, export_format: str, request: Request = None) -> FileResponse:
    task, result = _load_task_result(task_id, request, high_risk_operation=True)
    approval = get_active_approval_for_task(task_id)
    readiness = _build_export_readiness(
        task_id,
        result,
        current_stage=task.get("current_stage"),
        active_approval=approval,
        current_revision=_current_revision_or_error(task),
    )
    exports = result.get("exports")
    if readiness["errors"] or not isinstance(exports, dict):
        raise HTTPException(status_code=409, detail=readiness)

    export_path, extension, media_type = _resolve_export_download_path(exports, export_format.lower())
    create_audit_log(
        task_id,
        "export_downloaded",
        {"task_id": task_id, "format": export_format.lower(), **_actor_detail(request)},
    )
    return FileResponse(
        export_path,
        media_type=media_type,
        filename=f"task_{task_id}_medical_record.{extension}",
    )


def _iter_medical_fields(fields: MedicalRecordFields):
    yield fields.chief_complaint
    yield fields.present_illness
    yield fields.previous_treatment
    yield fields.accompanying_symptoms
    yield fields.past_history
    yield fields.allergy_history
    yield fields.physical_exam


def _validate_export_ready(result: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    fields = MedicalRecordFields.model_validate(result.get("fields"))
    safety_check = SafetyCheckResult.model_validate(result.get("safety_check"))

    if result.get("degraded") or _trace_has_fallback(result.get("llm_trace")):
        errors.append("当前病历生成处于降级模式，禁止导出。")

    if not safety_check.passed or safety_check.blocked:
        errors.append("安全校验未通过，禁止导出。")

    errors.extend(_approval_completion_errors(fields))

    return errors


def _trace_has_fallback(trace: Any) -> bool:
    if not isinstance(trace, dict):
        return False
    if trace.get("fallback"):
        return True
    operations = trace.get("operations")
    if isinstance(operations, dict):
        return any(isinstance(item, dict) and item.get("fallback") for item in operations.values())
    return False


def _build_export_readiness(
    task_id: int,
    result: dict[str, Any],
    *,
    current_stage: str | None = None,
    active_approval: dict[str, Any] | None = None,
    current_revision: dict[str, Any] | None = None,
) -> dict[str, Any]:
    errors = _validate_export_ready(result)
    revision_id = int(current_revision["id"]) if current_revision else None
    revision_number = int(current_revision["revision_no"]) if current_revision else None
    content_hash = _revision_content_hash(current_revision) if current_revision else None
    if active_approval is None:
        errors.append("病历尚未完成医生批准，禁止导出。")
    elif current_revision is None:
        errors.append("当前病历版本不存在，禁止导出。")
    elif int(active_approval["revision_id"]) != int(current_revision["id"]):
        errors.append("医生批准不属于当前病历版本，禁止导出。")
    elif active_approval.get("content_hash") != content_hash:
        errors.append("医生批准的内容哈希与当前病历不一致，禁止导出。")
    exports = result.get("exports")
    if not isinstance(exports, dict):
        exports = None

    return {
        "task_id": task_id,
        "ready": not errors,
        "blocked": bool(errors),
        "errors": errors,
        "next_action": "可以导出。" if not errors else "请先完成医生确认和安全校验，再导出。",
        "current_stage": current_stage,
        "exports": exports,
        "revision_id": revision_id,
        "revision_number": revision_number,
        "content_hash": content_hash,
        "approval_id": int(active_approval["id"]) if active_approval and not errors else None,
        "pending_review_count": len(errors),
    }


def _decode_event_detail(event_detail: str | None) -> dict[str, Any]:
    if not event_detail:
        return {}
    return json.loads(event_detail)


def _sse_message(event: str, data: dict[str, Any], event_id: int | None = None) -> str:
    payload = json.dumps(data, ensure_ascii=False, default=str)
    lines = []
    if event_id is not None:
        lines.append(f"id: {event_id}")
    lines.extend([f"event: {event}", f"data: {payload}", ""])
    return "\n".join(lines) + "\n"


def _event_from_audit_log(log: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    if log["event_type"] not in {"task_created", "status_changed"}:
        return None

    detail = _decode_event_detail(log.get("event_detail"))
    status = detail.get("status")
    if not status:
        return None

    return status, {
        "task_id": log["task_id"],
        "status": status,
        "current_stage": detail.get("current_stage"),
        "event_type": log["event_type"],
        "created_at": log["created_at"],
        "detail": detail,
    }


async def _task_event_stream(task_id: int):
    last_audit_id = 0
    sent_terminal = False

    while True:
        logs = [log for log in get_audit_logs(task_id) if log["id"] > last_audit_id]
        for log in logs:
            last_audit_id = log["id"]
            event = _event_from_audit_log(log)
            if event is None:
                continue

            event_name, payload = event
            if event_name in TERMINAL_EVENTS:
                payload["task"] = _decode_result_json(get_task(task_id) or {})
                sent_terminal = True
            yield _sse_message(event_name, payload, event_id=log["id"])

        if sent_terminal:
            break

        await asyncio.sleep(0.5)


@router.get("/{task_id}/events")
def read_task_events(task_id: int, request: Request = None) -> StreamingResponse:
    task = get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    _assert_task_access(task, request)

    return StreamingResponse(
        _task_event_stream(task_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
