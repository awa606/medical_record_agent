from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.api.auth import assert_owner_or_admin, current_user_from_request, require_admin, require_current_user
from app.db import create_audit_log, get_active_approval_for_task, get_task
from app.enterprise.audit import build_audit_event
from app.enterprise.config import get_enterprise_config
from app.enterprise.contracts import (
    CapabilityState,
    EMRWritebackPayload,
    RequestContext,
)
from app.enterprise.idempotency import IdempotencyConflictError, enterprise_idempotency_store
from app.integrations.factory import AdapterUnavailableError, create_emr_adapter
from app.observability.enterprise import (
    build_backup_restore_plan,
    build_metrics_snapshot,
    build_rollback_plan,
    build_upgrade_preflight,
)
from app.schemas import MedicalRecordFields, SafetyCheckResult


router = APIRouter(prefix="/enterprise", tags=["enterprise"])


class EnterpriseEMRWritebackRequest(BaseModel):
    task_id: int = Field(gt=0)
    organization_id: str | None = Field(default=None, max_length=80)
    department_id: str | None = Field(default=None, max_length=80)


@router.get("/capabilities")
def read_enterprise_capabilities() -> dict[str, CapabilityState]:
    return get_enterprise_config().capability_states()


@router.get("/metrics")
def read_enterprise_metrics(_admin=Depends(require_admin)) -> dict[str, Any]:
    capabilities = get_enterprise_config().capability_states()
    return build_metrics_snapshot(capabilities).model_dump(mode="json")


@router.get("/backup/plan")
def read_enterprise_backup_plan(_admin=Depends(require_admin)) -> dict[str, Any]:
    return build_backup_restore_plan().model_dump(mode="json")


@router.get("/upgrade/preflight")
def read_enterprise_upgrade_preflight(_admin=Depends(require_admin)) -> dict[str, Any]:
    return build_upgrade_preflight().model_dump(mode="json")


@router.get("/rollback/plan")
def read_enterprise_rollback_plan(_admin=Depends(require_admin)) -> dict[str, Any]:
    return build_rollback_plan().model_dump(mode="json")


@router.post("/emr/writeback")
def writeback_to_mock_emr(
    payload: EnterpriseEMRWritebackRequest,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    _user=Depends(require_current_user),
) -> dict[str, Any]:
    key = _require_idempotency_key(idempotency_key)
    config = get_enterprise_config()
    emr_state = config.capability_states()["emr_adapter"]
    if emr_state != "mock":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "message": "Mock EMR adapter is not enabled.",
                "capability_state": emr_state,
            },
        )

    task = get_task(payload.task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    assert_owner_or_admin(
        int(task["owner_user_id"]) if task.get("owner_user_id") is not None else None,
        request,
        resource_name="task",
    )
    result = _decode_result(task)
    active_approval = get_active_approval_for_task(payload.task_id)
    context = _request_context(request, payload)
    errors = _writeback_blockers(result, active_approval)
    if errors:
        _audit_writeback_blocked(payload.task_id, context, errors, request)
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Record is not eligible for mock EMR writeback.",
                "errors": errors,
            },
        )

    fingerprint = _fingerprint(
        {
            "task_id": payload.task_id,
            "organization_id": payload.organization_id,
            "department_id": payload.department_id,
        }
    )

    def create_response() -> dict[str, Any]:
        try:
            adapter = create_emr_adapter(config)
        except AdapterUnavailableError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

        assert active_approval is not None
        writeback_payload = EMRWritebackPayload(
            task_id=payload.task_id,
            approval_id=int(active_approval["id"]),
            revision_id=int(active_approval["revision_id"]),
            idempotency_key=key,
            record_hash=_record_hash(result, active_approval),
            organization_id=payload.organization_id,
            department_id=payload.department_id,
        )
        receipt = adapter.write_record(payload=writeback_payload, context=context)
        audit_event = build_audit_event(
            event_type="enterprise_emr_writeback_completed",
            capability="emr_adapter",
            outcome="accepted",
            context=context,
            task_id=payload.task_id,
            details={
                "task_id": payload.task_id,
                "approval_id": active_approval["id"],
                "revision_id": active_approval["revision_id"],
                "adapter": receipt.adapter,
                "receipt_id": receipt.receipt_id,
                "idempotency_key": key,
            },
        )
        audit_event_id = create_audit_log(
            payload.task_id,
            audit_event.event_type,
            audit_event.model_dump(mode="json"),
        )
        return {
            "task_id": payload.task_id,
            "status": receipt.status,
            "capability": "emr_adapter",
            "capability_state": "mock",
            "receipt": receipt.model_dump(mode="json"),
            "audit_event_id": audit_event_id,
            "correlation_id": context.correlation_id,
        }

    try:
        return enterprise_idempotency_store.get_or_create(
            key=key,
            fingerprint=fingerprint,
            create_response=create_response,
        )
    except IdempotencyConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def _require_idempotency_key(value: str | None) -> str:
    key = (value or "").strip()
    if not key:
        raise HTTPException(status_code=400, detail="Idempotency-Key header is required")
    if len(key) > 200:
        raise HTTPException(status_code=400, detail="Idempotency-Key header is too long")
    return key


def _request_context(
    request: Request,
    payload: EnterpriseEMRWritebackRequest,
) -> RequestContext:
    user = current_user_from_request(request)
    correlation_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
    return RequestContext(
        request_id=str(uuid.uuid4()),
        correlation_id=correlation_id,
        actor_user_id=user.id if user is not None else None,
        actor_role=user.role if user is not None else None,
        organization_id=payload.organization_id,
        department_id=payload.department_id,
    )


def _decode_result(task: dict[str, Any]) -> dict[str, Any]:
    result_json = task.get("result_json")
    if isinstance(result_json, dict):
        return result_json
    if isinstance(result_json, str) and result_json:
        decoded = json.loads(result_json)
        if isinstance(decoded, dict):
            return decoded
    raise HTTPException(status_code=409, detail="Task has no generated result")


def _writeback_blockers(
    result: dict[str, Any],
    active_approval: dict[str, Any] | None,
) -> list[str]:
    errors: list[str] = []
    if active_approval is None:
        errors.append("Active doctor approval is required before mock EMR writeback.")
    if result.get("degraded") or _trace_has_fallback(result.get("llm_trace")):
        errors.append("Degraded or fallback-generated records cannot be written back.")
    try:
        safety_check = SafetyCheckResult.model_validate(result.get("safety_check"))
    except Exception:
        errors.append("Safety check result is missing or invalid.")
    else:
        if not safety_check.passed or safety_check.blocked:
            errors.append("Safety check must pass before mock EMR writeback.")
    try:
        fields = MedicalRecordFields.model_validate(result.get("fields"))
    except Exception:
        errors.append("Medical record fields are missing or invalid.")
    else:
        unconfirmed = [
            name
            for name, field in [
                ("chief_complaint", fields.chief_complaint),
                ("present_illness", fields.present_illness),
                ("previous_treatment", fields.previous_treatment),
                ("accompanying_symptoms", fields.accompanying_symptoms),
                ("past_history", fields.past_history),
                ("allergy_history", fields.allergy_history),
                ("physical_exam", fields.physical_exam),
            ]
            if not field.confirmed_by_doctor
        ]
        unconfirmed.extend(
            f"candidate_diagnosis:{diagnosis.name}"
            for diagnosis in fields.candidate_diagnoses
            if not diagnosis.confirmed_by_doctor
        )
        if unconfirmed:
            errors.append(f"Unconfirmed fields or diagnoses remain: {', '.join(unconfirmed)}.")
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


def _audit_writeback_blocked(
    task_id: int,
    context: RequestContext,
    errors: list[str],
    request: Request,
) -> None:
    audit_event = build_audit_event(
        event_type="enterprise_emr_writeback_blocked",
        capability="emr_adapter",
        outcome="blocked",
        context=context,
        task_id=task_id,
        details={
            "task_id": task_id,
            "errors": errors,
            "authorization": request.headers.get("authorization"),
        },
    )
    create_audit_log(task_id, audit_event.event_type, audit_event.model_dump(mode="json"))


def _record_hash(result: dict[str, Any], active_approval: dict[str, Any]) -> str:
    return _fingerprint(
        {
            "fields": result.get("fields"),
            "safety_check": result.get("safety_check"),
            "approval_id": active_approval.get("id"),
            "revision_id": active_approval.get("revision_id"),
        }
    )


def _fingerprint(value: dict[str, Any]) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
