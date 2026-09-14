from __future__ import annotations

from typing import Any

from app.db import get_record_revision, get_task


FIELD_KEYS = [
    "chief_complaint",
    "present_illness",
    "previous_treatment",
    "accompanying_symptoms",
    "past_history",
    "allergy_history",
    "physical_exam",
]


def _revision_identity(task_id: int) -> dict[str, Any]:
    task = get_task(task_id)
    if task is None or task["current_record_revision_id"] is None:
        raise AssertionError(f"Task {task_id} has no current record revision")
    revision = get_record_revision(int(task["current_record_revision_id"]))
    if revision is None:
        raise AssertionError(f"Task {task_id} current revision is missing")
    return {
        "revision_id": revision["id"],
        "content_hash": revision["content_hash"],
    }


def approval_payload_for_fields(fields: Any, *, task_id: int | None = None) -> dict[str, Any]:
    data = fields.model_dump(mode="json") if hasattr(fields, "model_dump") else fields
    payload: dict[str, Any] = {
        "confirm_all_regular_fields": True,
        "fields": [],
        "diagnoses": [],
        "high_risk_conflicts": [],
    }
    if task_id is not None:
        payload.update(_revision_identity(task_id))
    for key in FIELD_KEYS:
        field = data[key]
        value = str(field.get("value") or "").strip()
        status = field.get("status")
        if field.get("missing") or status in {"missing", "partial"} or not value:
            payload["fields"].append({"key": key, "action": "accept_missing"})
        elif status == "conflicting":
            payload["fields"].append({"key": key, "action": "confirm_content"})

    for index, diagnosis in enumerate(data.get("candidate_diagnoses") or []):
        payload["diagnoses"].append(
            {
                "index": index,
                "action": "confirm_candidate",
                "high_risk_confirmed": bool(diagnosis.get("risk_warnings")),
            }
        )
    return payload


def review_payload_for_fields(task_id: int, fields: Any) -> dict[str, Any]:
    return {
        "fields": fields.model_dump(mode="json") if hasattr(fields, "model_dump") else fields,
        "expected_revision_id": _revision_identity(task_id)["revision_id"],
        "expected_content_hash": _revision_identity(task_id)["content_hash"],
    }
