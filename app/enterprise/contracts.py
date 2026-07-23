from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


CapabilityState = Literal["disabled", "mock", "configured_unverified", "verified"]


class Organization(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=160)
    status: Literal["pilot", "active", "inactive"] = "pilot"


class Department(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=80)
    organization_id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=160)
    code: str | None = Field(default=None, max_length=80)
    status: Literal["pilot", "active", "inactive"] = "pilot"


class Membership(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: int
    organization_id: str = Field(min_length=1, max_length=80)
    department_ids: list[str] = Field(default_factory=list)
    roles: list[str] = Field(default_factory=list)


class RequestContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1, max_length=120)
    correlation_id: str = Field(min_length=1, max_length=120)
    actor_user_id: int | None = None
    actor_role: str | None = None
    organization_id: str | None = Field(default=None, max_length=80)
    department_id: str | None = Field(default=None, max_length=80)
    membership: Membership | None = None
    source: str = "enterprise_api"


class IdentityPrincipal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: str = Field(min_length=1, max_length=160)
    display_name: str | None = Field(default=None, max_length=160)
    email: str | None = Field(default=None, max_length=200)
    organization_id: str | None = Field(default=None, max_length=80)
    department_ids: list[str] = Field(default_factory=list)
    claims: dict[str, Any] = Field(default_factory=dict)


class IdentityAuthResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["authenticated", "rejected"]
    provider: str
    principal: IdentityPrincipal | None = None
    reason: str | None = None


class HISPatientSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    deidentified_patient_id: str = Field(min_length=1, max_length=120)
    organization_id: str | None = Field(default=None, max_length=80)
    department_id: str | None = Field(default=None, max_length=80)
    source: Literal["mock_his"] = "mock_his"
    status: Literal["found", "not_found"] = "found"


class EMRWritebackPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: int
    approval_id: int
    revision_id: int
    idempotency_key: str = Field(min_length=1, max_length=200)
    record_hash: str = Field(min_length=1, max_length=128)
    organization_id: str | None = Field(default=None, max_length=80)
    department_id: str | None = Field(default=None, max_length=80)


class EMRWritebackReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    adapter: Literal["mock_emr"] = "mock_emr"
    status: Literal["accepted"] = "accepted"
    receipt_id: str
    task_id: int
    approval_id: int
    revision_id: int
    idempotency_key: str
    created_at: str


class EnterpriseAuditEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: str = Field(min_length=1, max_length=120)
    capability: str = Field(min_length=1, max_length=120)
    outcome: Literal["accepted", "blocked", "replayed", "failed"]
    correlation_id: str = Field(min_length=1, max_length=120)
    task_id: int | None = None
    actor_user_id: int | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
