from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Mapping

from app.schemas.asr import SpeakerRoleDecision


ROLE_DOCTOR = "\u533b\u751f"
ROLE_PATIENT = "\u60a3\u8005"
ROLE_OTHER = "\u5176\u4ed6"
CLINICAL_ROLES = {ROLE_DOCTOR, ROLE_PATIENT, ROLE_OTHER}

ACTION_AUTO_ACCEPT = "auto_accept"
ACTION_NEEDS_REVIEW = "needs_review"
ACTION_BLOCKED = "blocked"
VALID_ACTIONS = {ACTION_AUTO_ACCEPT, ACTION_NEEDS_REVIEW, ACTION_BLOCKED}

CURRENT_SPEAKER_ROLE_POLICY_VERSION = "speaker-role-policy-v1"

SOURCE_PROVIDER_MAP = {
    "speaker_context_rules": "rules",
    "global_two_party_constraint": "rules",
    "single_speaker": "rules",
    "multi_speaker_fallback": "rules",
    "mock_deterministic": "rules",
    "doctor_voice_profile": "voiceprint",
    "doctor_profile_two_party_constraint": "voiceprint",
    "ollama_qwen3_speaker_context": "llm",
}
MANUAL_SOURCE_PREFIXES = ("manual",)

ROLE_ALIASES = {
    ROLE_DOCTOR: ROLE_DOCTOR,
    ROLE_PATIENT: ROLE_PATIENT,
    ROLE_OTHER: ROLE_OTHER,
    "doctor": ROLE_DOCTOR,
    "physician": ROLE_DOCTOR,
    "patient": ROLE_PATIENT,
    "other": ROLE_OTHER,
    "family": ROLE_OTHER,
    "relative": ROLE_OTHER,
    "\u5bb6\u5c5e": ROLE_OTHER,
}


@dataclass(frozen=True)
class SpeakerRoleProviderPolicy:
    provider: str
    provider_version: str
    policy_version: str
    auto_accept_threshold: float
    review_threshold: float
    confidence_mapping: str = "identity"
    fallback_action: str = ACTION_NEEDS_REVIEW
    enabled: bool = True

    def calibrated_confidence(self, raw_confidence: float | None) -> float | None:
        if raw_confidence is None:
            return None
        value = max(0.0, min(1.0, float(raw_confidence)))
        if self.confidence_mapping == "identity":
            return value
        if self.confidence_mapping == "llm_conservative":
            return max(0.0, min(1.0, value - 0.02))
        if self.confidence_mapping == "voiceprint_conservative":
            return max(0.0, min(1.0, value - 0.01))
        return value

    def action_for_confidence(self, calibrated_confidence: float | None) -> str:
        if not self.enabled:
            return self.fallback_action
        if calibrated_confidence is None:
            return self.fallback_action
        if calibrated_confidence >= self.auto_accept_threshold:
            return ACTION_AUTO_ACCEPT
        if calibrated_confidence >= self.review_threshold:
            return ACTION_NEEDS_REVIEW
        return ACTION_BLOCKED

    def model_dump(self) -> dict[str, object]:
        return asdict(self)


DEFAULT_PROVIDER_POLICIES: dict[str, SpeakerRoleProviderPolicy] = {
    "rules": SpeakerRoleProviderPolicy(
        provider="rules",
        provider_version="rules-v1",
        policy_version=CURRENT_SPEAKER_ROLE_POLICY_VERSION,
        auto_accept_threshold=0.9,
        review_threshold=0.65,
    ),
    "voiceprint": SpeakerRoleProviderPolicy(
        provider="voiceprint",
        provider_version="voiceprint-v1",
        policy_version=CURRENT_SPEAKER_ROLE_POLICY_VERSION,
        auto_accept_threshold=0.9,
        review_threshold=0.65,
        confidence_mapping="voiceprint_conservative",
    ),
    "llm": SpeakerRoleProviderPolicy(
        provider="llm",
        provider_version="llm-v1",
        policy_version=CURRENT_SPEAKER_ROLE_POLICY_VERSION,
        auto_accept_threshold=0.9,
        review_threshold=0.7,
        confidence_mapping="llm_conservative",
    ),
    "manual": SpeakerRoleProviderPolicy(
        provider="manual",
        provider_version="manual-review-v1",
        policy_version=CURRENT_SPEAKER_ROLE_POLICY_VERSION,
        auto_accept_threshold=0.0,
        review_threshold=0.0,
        fallback_action=ACTION_AUTO_ACCEPT,
    ),
    "unknown": SpeakerRoleProviderPolicy(
        provider="unknown",
        provider_version="unknown-v1",
        policy_version=CURRENT_SPEAKER_ROLE_POLICY_VERSION,
        auto_accept_threshold=1.01,
        review_threshold=1.01,
        fallback_action=ACTION_NEEDS_REVIEW,
        enabled=False,
    ),
}


def normalize_role(role: str | None) -> str | None:
    value = str(role or "").strip()
    if not value:
        return None
    return ROLE_ALIASES.get(value) or ROLE_ALIASES.get(value.lower())


def provider_from_source(source: str | None) -> str:
    normalized = str(source or "").strip().lower()
    if any(normalized.startswith(prefix) for prefix in MANUAL_SOURCE_PREFIXES):
        return "manual"
    return SOURCE_PROVIDER_MAP.get(normalized, "unknown")


def policy_for_provider(
    provider: str,
    policies: Mapping[str, SpeakerRoleProviderPolicy] | None = None,
) -> SpeakerRoleProviderPolicy:
    policy_map = policies or DEFAULT_PROVIDER_POLICIES
    return policy_map.get(provider) or policy_map.get("unknown") or DEFAULT_PROVIDER_POLICIES["unknown"]


def provider_config_payload(
    policies: Mapping[str, SpeakerRoleProviderPolicy] | None = None,
) -> dict[str, dict[str, object]]:
    policy_map = policies or DEFAULT_PROVIDER_POLICIES
    return {name: policy.model_dump() for name, policy in sorted(policy_map.items())}


def speaker_role_decision(
    *,
    speaker_id: str,
    role: str | None,
    confidence: float | None,
    source: str | None,
    reason: str | None = None,
    requires_confirmation: bool = False,
    reviewed_by_doctor: bool = False,
    speaker_count: int = 0,
    mixed_blocked: bool = False,
    policies: Mapping[str, SpeakerRoleProviderPolicy] | None = None,
) -> SpeakerRoleDecision:
    provider = provider_from_source(source)
    policy = policy_for_provider(provider, policies)
    predicted_role = normalize_role(role)
    if predicted_role is None and str(source or "").strip().lower() == "single_speaker":
        predicted_role = ROLE_OTHER
    raw_confidence = confidence
    calibrated_confidence = policy.calibrated_confidence(raw_confidence)

    reason_code = _reason_code(
        provider=provider,
        source=source,
        reason=reason,
        role=predicted_role,
        speaker_count=speaker_count,
        mixed_blocked=mixed_blocked,
    )
    action = _action(
        policy=policy,
        provider=provider,
        predicted_role=predicted_role,
        calibrated_confidence=calibrated_confidence,
        requires_confirmation=requires_confirmation,
        reviewed_by_doctor=reviewed_by_doctor,
        speaker_count=speaker_count,
        mixed_blocked=mixed_blocked,
        reason_code=reason_code,
    )
    if provider == "manual" and reviewed_by_doctor:
        raw_confidence = max(float(raw_confidence or 0.0), 0.99)
        calibrated_confidence = raw_confidence

    return SpeakerRoleDecision(
        speaker_id=speaker_id,
        provider=policy.provider,
        provider_version=policy.provider_version,
        policy_version=policy.policy_version,
        raw_confidence=_rounded_confidence(raw_confidence),
        calibrated_confidence=_rounded_confidence(calibrated_confidence),
        predicted_role=predicted_role,
        reason_code=reason_code,
        action=action,
    )


def _action(
    *,
    policy: SpeakerRoleProviderPolicy,
    provider: str,
    predicted_role: str | None,
    calibrated_confidence: float | None,
    requires_confirmation: bool,
    reviewed_by_doctor: bool,
    speaker_count: int,
    mixed_blocked: bool,
    reason_code: str,
) -> str:
    if provider == "manual" and reviewed_by_doctor and predicted_role in CLINICAL_ROLES:
        return ACTION_AUTO_ACCEPT
    if mixed_blocked:
        return ACTION_BLOCKED
    if reason_code == "single_speaker_counterexample":
        return ACTION_BLOCKED
    if predicted_role not in CLINICAL_ROLES:
        return ACTION_NEEDS_REVIEW
    action = policy.action_for_confidence(calibrated_confidence)
    if action == ACTION_BLOCKED and predicted_role in CLINICAL_ROLES:
        return ACTION_NEEDS_REVIEW
    if requires_confirmation and action == ACTION_AUTO_ACCEPT:
        return ACTION_NEEDS_REVIEW
    return action if action in VALID_ACTIONS else ACTION_NEEDS_REVIEW


def _reason_code(
    *,
    provider: str,
    source: str | None,
    reason: str | None,
    role: str | None,
    speaker_count: int,
    mixed_blocked: bool,
) -> str:
    source_value = str(source or "").strip().lower()
    if mixed_blocked:
        return "mixed_utterance_candidate"
    if source_value == "single_speaker":
        return "single_speaker_counterexample"
    if role is None:
        return "unmapped_speaker"
    if provider == "unknown":
        return "unknown_provider"
    if source_value:
        return f"{provider}_{source_value}"
    return f"{provider}_policy_threshold"


def _rounded_confidence(value: float | None) -> float | None:
    return round(float(value), 4) if value is not None else None
