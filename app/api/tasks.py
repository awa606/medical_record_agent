from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.db import create_audit_log, get_audit_logs, get_task, get_task_steps, json_dumps, update_task
from app.schemas import MedicalRecordFields, SafetyCheckResult
from app.services import MockLLM, export_record
from app.services.agent_trace import build_agent_trace, load_asr_result_for_audio


router = APIRouter(prefix="/tasks", tags=["tasks"])
TERMINAL_EVENTS = {"WAITING_DOCTOR_REVIEW", "FAILED"}


class ReviewRequest(BaseModel):
    fields: MedicalRecordFields


class ExportReadinessResponse(BaseModel):
    task_id: int
    ready: bool
    blocked: bool
    errors: list[str]
    next_action: str
    current_stage: str | None = None
    exports: dict[str, str] | None = None


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


def _load_task_result(task_id: int) -> tuple[dict[str, Any], dict[str, Any]]:
    task = get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
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
) -> None:
    update_task(
        task_id,
        current_stage=current_stage,
        result_json=json_dumps(result),
    )
    create_audit_log(task_id, event_type, event_detail)


@router.get("/{task_id}")
def read_task(task_id: int) -> dict[str, Any]:
    task = get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return _decode_result_json(task)


@router.get("/{task_id}/steps")
def read_task_steps(task_id: int) -> list[dict[str, Any]]:
    task = get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return [_decode_step_json(step) for step in get_task_steps(task_id)]


@router.get("/{task_id}/trace")
def read_task_agent_trace(
    task_id: int,
    audio_id: str | None = Query(default=None),
) -> dict[str, Any]:
    task = get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    decoded_task = _decode_result_json(task)
    decoded_steps = [_decode_step_json(step) for step in get_task_steps(task_id)]
    asr_result = load_asr_result_for_audio(audio_id)
    return build_agent_trace(
        task=decoded_task,
        steps=decoded_steps,
        asr_result=asr_result,
    )


@router.post("/{task_id}/review")
def review_task(task_id: int, payload: ReviewRequest) -> dict[str, Any]:
    task, result = _load_task_result(task_id)
    fields = payload.fields
    draft = MockLLM().generate_draft(fields)
    safety_check = MockLLM().safety_check(draft, fields)

    result["fields"] = fields.model_dump()
    result["draft"] = draft
    result["safety_check"] = safety_check.model_dump()
    result["reviewed"] = True

    _save_task_result(
        task_id,
        result,
        current_stage="reviewed",
        event_type="doctor_review_saved",
        event_detail={"task_id": task_id},
    )
    task["result_json"] = result
    task["current_stage"] = "reviewed"
    return task


@router.post("/{task_id}/approve")
def approve_task(task_id: int) -> dict[str, Any]:
    task, result = _load_task_result(task_id)
    fields = MedicalRecordFields.model_validate(result["fields"])

    for field in _iter_medical_fields(fields):
        field.confirmed_by_doctor = True
    for diagnosis in fields.candidate_diagnoses:
        diagnosis.confirmed_by_doctor = True

    result["fields"] = fields.model_dump()
    result["approved"] = True

    _save_task_result(
        task_id,
        result,
        current_stage="approved",
        event_type="doctor_approved",
        event_detail={"task_id": task_id},
    )
    task["result_json"] = result
    task["current_stage"] = "approved"
    return task


@router.post("/{task_id}/export")
def export_task(task_id: int) -> dict[str, Any]:
    task, result = _load_task_result(task_id)
    readiness = _build_export_readiness(
        task_id,
        result,
        current_stage=task.get("current_stage"),
    )
    if readiness["errors"]:
        raise HTTPException(status_code=400, detail=readiness)

    try:
        exports = export_record(task_id, result)
    except Exception as exc:
        create_audit_log(
            task_id,
            "export_failed",
            {"task_id": task_id, "error": str(exc)},
        )
        raise HTTPException(status_code=500, detail=f"导出失败：{exc}") from exc

    result["exports"] = exports
    _save_task_result(
        task_id,
        result,
        current_stage="exported",
        event_type="export_completed",
        event_detail={"task_id": task_id, **exports},
    )
    task["result_json"] = result
    task["current_stage"] = "exported"
    export_readiness = _build_export_readiness(
        task_id,
        result,
        current_stage="exported",
    )
    return {"task_id": task_id, "exports": exports, "export_readiness": export_readiness}


@router.get("/{task_id}/export-readiness", response_model=ExportReadinessResponse)
def read_export_readiness(task_id: int) -> ExportReadinessResponse:
    task, result = _load_task_result(task_id)
    return ExportReadinessResponse(
        **_build_export_readiness(
            task_id,
            result,
            current_stage=task.get("current_stage"),
        )
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

    if not safety_check.passed or safety_check.blocked:
        errors.append("安全校验未通过，禁止导出。")

    unconfirmed_fields = [
        field_name
        for field_name, field in [
            ("主诉", fields.chief_complaint),
            ("现病史", fields.present_illness),
            ("既往处理", fields.previous_treatment),
            ("伴随症状", fields.accompanying_symptoms),
            ("既往史", fields.past_history),
            ("过敏史", fields.allergy_history),
            ("查体", fields.physical_exam),
        ]
        if not field.confirmed_by_doctor
    ]
    if unconfirmed_fields:
        errors.append(f"存在未确认字段：{'、'.join(unconfirmed_fields)}。")

    unconfirmed_diagnoses = [
        diagnosis.name
        for diagnosis in fields.candidate_diagnoses
        if not diagnosis.confirmed_by_doctor
    ]
    if unconfirmed_diagnoses:
        errors.append(f"存在未确认候选诊断：{'、'.join(unconfirmed_diagnoses)}。")

    return errors


def _build_export_readiness(
    task_id: int,
    result: dict[str, Any],
    *,
    current_stage: str | None = None,
) -> dict[str, Any]:
    errors = _validate_export_ready(result)
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
def read_task_events(task_id: int) -> StreamingResponse:
    task = get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    return StreamingResponse(
        _task_event_stream(task_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
