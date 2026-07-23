from __future__ import annotations

import os
from dataclasses import dataclass

from app.enterprise.contracts import CapabilityState


CAPABILITY_NAMES = (
    "identity_provider",
    "his_adapter",
    "emr_adapter",
    "audit_events",
    "metrics",
    "backup_restore",
    "upgrade_rollback",
)

TRUE_VALUES = {"1", "true", "yes", "on", "enabled", "verified"}
DISABLED_VALUES = {"", "0", "false", "no", "off", "disabled", "none"}
MOCK_VALUES = {"mock", "local", "mock_oidc"}


@dataclass(frozen=True)
class EnterpriseConfig:
    enabled: bool = False
    identity_provider: str = "disabled"
    identity_verified: bool = False
    his_adapter: str = "disabled"
    his_verified: bool = False
    emr_adapter: str = "disabled"
    emr_verified: bool = False
    audit_enabled: bool = False
    audit_verified: bool = False
    metrics_enabled: bool = False
    metrics_verified: bool = False
    backup_restore_enabled: bool = False
    backup_restore_verified: bool = False
    upgrade_rollback_enabled: bool = False
    upgrade_rollback_verified: bool = False

    @classmethod
    def from_env(cls) -> "EnterpriseConfig":
        return cls(
            enabled=_env_bool("MRA_ENTERPRISE_ENABLED", False),
            identity_provider=_env_text("MRA_ENTERPRISE_IDENTITY_PROVIDER", "disabled"),
            identity_verified=_env_bool("MRA_ENTERPRISE_IDENTITY_VERIFIED", False),
            his_adapter=_env_text("MRA_ENTERPRISE_HIS_ADAPTER", "disabled"),
            his_verified=_env_bool("MRA_ENTERPRISE_HIS_VERIFIED", False),
            emr_adapter=_env_text("MRA_ENTERPRISE_EMR_ADAPTER", "disabled"),
            emr_verified=_env_bool("MRA_ENTERPRISE_EMR_VERIFIED", False),
            audit_enabled=_env_bool("MRA_ENTERPRISE_AUDIT_ENABLED", False),
            audit_verified=_env_bool("MRA_ENTERPRISE_AUDIT_VERIFIED", False),
            metrics_enabled=_env_bool("MRA_ENTERPRISE_METRICS_ENABLED", False),
            metrics_verified=_env_bool("MRA_ENTERPRISE_METRICS_VERIFIED", False),
            backup_restore_enabled=_env_bool("MRA_ENTERPRISE_BACKUP_RESTORE_ENABLED", False),
            backup_restore_verified=_env_bool("MRA_ENTERPRISE_BACKUP_RESTORE_VERIFIED", False),
            upgrade_rollback_enabled=_env_bool("MRA_ENTERPRISE_UPGRADE_ROLLBACK_ENABLED", False),
            upgrade_rollback_verified=_env_bool("MRA_ENTERPRISE_UPGRADE_ROLLBACK_VERIFIED", False),
        )

    def capability_states(self) -> dict[str, CapabilityState]:
        if not self.enabled:
            return {name: "disabled" for name in CAPABILITY_NAMES}
        return {
            "identity_provider": _mode_state(self.identity_provider, self.identity_verified),
            "his_adapter": _mode_state(self.his_adapter, self.his_verified),
            "emr_adapter": _mode_state(self.emr_adapter, self.emr_verified),
            "audit_events": _flag_state(self.audit_enabled, self.audit_verified),
            "metrics": _flag_state(self.metrics_enabled, self.metrics_verified),
            "backup_restore": _flag_state(
                self.backup_restore_enabled,
                self.backup_restore_verified,
            ),
            "upgrade_rollback": _flag_state(
                self.upgrade_rollback_enabled,
                self.upgrade_rollback_verified,
            ),
        }


def get_enterprise_config() -> EnterpriseConfig:
    return EnterpriseConfig.from_env()


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in TRUE_VALUES


def _env_text(name: str, default: str) -> str:
    return (os.environ.get(name) or default).strip().lower()


def _mode_state(mode: str, verified: bool) -> CapabilityState:
    selected = mode.strip().lower()
    if selected in DISABLED_VALUES:
        return "disabled"
    if selected in MOCK_VALUES:
        return "mock"
    return "verified" if verified else "configured_unverified"


def _flag_state(enabled: bool, verified: bool) -> CapabilityState:
    if not enabled:
        return "disabled"
    return "verified" if verified else "mock"
