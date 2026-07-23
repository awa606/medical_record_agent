from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.enterprise.contracts import CapabilityState
from app.integrations.emr import mock_emr_write_count


class MetricsSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service: str = "enterprise_integration_skeleton"
    generated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    capabilities: dict[str, CapabilityState]
    counters: dict[str, int]


class BackupRestorePlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = "contract_only"
    backup_targets: list[str]
    restore_targets: list[str]
    notes: list[str]


class UpgradePreflight(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = "contract_only"
    checks: list[str]
    blockers: list[str]


class RollbackPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = "contract_only"
    rollback_points: list[str]
    notes: list[str]


def build_metrics_snapshot(capabilities: dict[str, CapabilityState]) -> MetricsSnapshot:
    return MetricsSnapshot(
        capabilities=capabilities,
        counters={
            "mock_emr_writebacks": mock_emr_write_count(),
            "real_hospital_writebacks": 0,
        },
    )


def build_backup_restore_plan() -> BackupRestorePlan:
    return BackupRestorePlan(
        backup_targets=["sqlite_database", "runtime_outputs", "configuration_manifest"],
        restore_targets=["sqlite_database", "runtime_outputs"],
        notes=[
            "Skeleton only; no backup command is executed by this contract.",
            "Production backup requires hospital-approved storage and retention policy.",
        ],
    )


def build_upgrade_preflight() -> UpgradePreflight:
    return UpgradePreflight(
        checks=[
            "feature_flags_disabled_by_default",
            "mock_adapters_only",
            "no_unreviewed_emr_writeback",
            "rollback_plan_documented",
        ],
        blockers=[
            "missing_real_idp_contract",
            "missing_real_his_emr_vendor_contract",
            "missing_durable_idempotency_store",
        ],
    )


def build_rollback_plan() -> RollbackPlan:
    return RollbackPlan(
        rollback_points=["disable_enterprise_feature_flag", "disable_mock_emr_adapter"],
        notes=[
            "Enterprise routes are additive and can be disabled by environment flags.",
            "No database migration is introduced by this skeleton.",
        ],
    )
