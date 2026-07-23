from __future__ import annotations

from typing import Any

from app.enterprise.contracts import EnterpriseAuditEvent, RequestContext


REDACTED = "[REDACTED]"
SENSITIVE_KEY_PARTS = {
    "api_key",
    "apikey",
    "authorization",
    "password",
    "secret",
    "token",
}
SENSITIVE_EXACT_KEYS = {
    "conversation_text",
    "draft",
    "input_text",
    "patient_display_name",
    "patient_name",
    "patient_text",
}
PATIENT_CHILD_KEYS = {"display_name", "name", "text"}


def redact_sensitive_fields(value: Any, path: tuple[str, ...] = ()) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if _is_sensitive_key(key_text, path):
                redacted[key_text] = REDACTED
            else:
                redacted[key_text] = redact_sensitive_fields(item, (*path, key_text))
        return redacted
    if isinstance(value, list):
        return [redact_sensitive_fields(item, path) for item in value]
    return value


def build_audit_event(
    *,
    event_type: str,
    capability: str,
    outcome: str,
    context: RequestContext,
    task_id: int | None = None,
    details: dict[str, Any] | None = None,
) -> EnterpriseAuditEvent:
    return EnterpriseAuditEvent(
        event_type=event_type,
        capability=capability,
        outcome=outcome,
        correlation_id=context.correlation_id,
        task_id=task_id,
        actor_user_id=context.actor_user_id,
        details=redact_sensitive_fields(details or {}),
    )


def _is_sensitive_key(key: str, path: tuple[str, ...]) -> bool:
    normalized = key.strip().lower().replace("-", "_")
    if normalized in SENSITIVE_EXACT_KEYS:
        return True
    if any(part in normalized for part in SENSITIVE_KEY_PARTS):
        return True
    return "patient" in {item.lower() for item in path} and normalized in PATIENT_CHILD_KEYS
