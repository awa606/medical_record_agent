from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.api.auth import assert_owner_or_admin, current_user_from_request, require_current_user
from app.db import (
    create_encounter,
    get_encounter,
    get_record_revision,
    list_encounters,
    list_record_revisions_for_encounter,
)
from app.schemas.auth import AuthenticatedUser


router = APIRouter(prefix="/encounters", tags=["encounters"], dependencies=[Depends(require_current_user)])


class CreateEncounterRequest(BaseModel):
    patient_deidentified_id: str | None = Field(default=None, max_length=80)
    patient_display_name: str | None = Field(default="模拟患者", max_length=80)


def _parse_json(value: str | None) -> Any:
    if not value:
        return None
    return json.loads(value)


def _assert_encounter_access(encounter: dict[str, Any], request: Request | None) -> None:
    owner = encounter.get("doctor_user_id")
    assert_owner_or_admin(int(owner) if owner is not None else None, request, resource_name="encounter")


def _summary(encounter: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": encounter["id"],
        "patient_id": encounter["patient_id"],
        "patient_deidentified_id": encounter.get("patient_deidentified_id"),
        "patient_display_name": encounter.get("patient_display_name"),
        "doctor_user_id": encounter.get("doctor_user_id"),
        "task_id": encounter.get("task_id"),
        "status": encounter.get("status"),
        "current_revision_id": encounter.get("current_revision_id"),
        "task_status": encounter.get("task_status"),
        "task_current_stage": encounter.get("task_current_stage"),
        "created_at": encounter.get("created_at"),
        "updated_at": encounter.get("updated_at"),
    }


def _detail(encounter: dict[str, Any]) -> dict[str, Any]:
    current_revision = None
    if encounter.get("current_revision_id"):
        current_revision = get_record_revision(int(encounter["current_revision_id"]))
    task_result = _parse_json(encounter.get("task_result_json"))
    revisions = list_record_revisions_for_encounter(int(encounter["id"]))
    return {
        **_summary(encounter),
        "task": {
            "id": encounter.get("task_id"),
            "status": encounter.get("task_status"),
            "current_stage": encounter.get("task_current_stage"),
            "result_json": task_result,
        } if encounter.get("task_id") else None,
        "current_revision": current_revision,
        "revisions": revisions,
    }


@router.get("")
def read_encounters(
    request: Request,
    status: str | None = Query(default=None),
    mine: bool = Query(default=True),
    q: str | None = Query(default=None),
) -> dict[str, Any]:
    user = current_user_from_request(request)
    assert user is not None
    rows = list_encounters(
        user_id=user.id,
        role=user.role,
        status=status,
        mine=mine,
        q=q,
    )
    return {"encounters": [_summary(row) for row in rows]}


@router.post("")
def create_encounter_route(
    payload: CreateEncounterRequest,
    user: AuthenticatedUser = Depends(require_current_user),
) -> dict[str, Any]:
    deidentified_id = payload.patient_deidentified_id or f"SIM-MANUAL-{uuid.uuid4().hex[:8]}"
    row = create_encounter(
        doctor_user_id=user.id,
        deidentified_id=deidentified_id,
        display_name=payload.patient_display_name or deidentified_id,
    )
    return _detail(row)


@router.get("/{encounter_id}")
def read_encounter(encounter_id: int, request: Request) -> dict[str, Any]:
    row = get_encounter(encounter_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Encounter not found")
    _assert_encounter_access(row, request)
    return _detail(row)
