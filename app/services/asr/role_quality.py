from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from app.schemas.asr import (
    ASRResult,
    ASRSegment,
    SpeakerRoleAssignment,
    SpeakerRoleDecision,
    SpeakerRoleQualityMetrics,
    SpeakerRoleQualityResult,
)
from app.services.asr.speaker_role_policy import (
    ACTION_AUTO_ACCEPT,
    ACTION_BLOCKED,
    ACTION_NEEDS_REVIEW,
    CLINICAL_ROLES,
    CURRENT_SPEAKER_ROLE_POLICY_VERSION,
    DEFAULT_PROVIDER_POLICIES,
    ROLE_DOCTOR,
    ROLE_OTHER,
    ROLE_PATIENT,
    SpeakerRoleProviderPolicy,
    normalize_role,
    speaker_role_decision,
)


MANUAL_SOURCE_PREFIXES = ("manual",)


@dataclass(frozen=True)
class SpeakerRoleQualityPolicy:
    confidence_threshold: float = 0.9
    max_manual_confirmation_rate: float = 0.35
    max_mixed_utterance_rate: float = 0.05
    min_role_accuracy: float = 0.9
    provider_policies: Mapping[str, SpeakerRoleProviderPolicy] = field(
        default_factory=lambda: DEFAULT_PROVIDER_POLICIES
    )
    policy_version: str = CURRENT_SPEAKER_ROLE_POLICY_VERSION

    def evaluate(
        self,
        asr_result: ASRResult,
        *,
        expected_roles: dict[str, str] | None = None,
    ) -> SpeakerRoleQualityResult:
        segments = [segment for segment in asr_result.segments if not segment.provisional]
        speaker_ids = sorted(
            {
                *(_speaker_id(segment) for segment in segments if _speaker_id(segment)),
                *(assignment.speaker_id for assignment in asr_result.speaker_assignments),
            }
        )
        assignments = {item.speaker_id: item for item in asr_result.speaker_assignments}

        mixed = [
            {
                "segment_id": segment.segment_id,
                "speaker_id": _speaker_id(segment),
                "text": _compact(segment.text, 140),
            }
            for segment in segments
            if _looks_like_mixed_medical_utterance(segment.text)
        ]
        mixed_rate = len(mixed) / max(len(segments), 1)
        mixed_speakers = {
            str(item["speaker_id"])
            for item in mixed
            if item.get("speaker_id")
        }

        decisions = [
            _decision_for_speaker(
                speaker_id,
                segments=segments,
                assignment=assignments.get(speaker_id),
                speaker_count=len(speaker_ids),
                mixed_blocked=speaker_id in mixed_speakers and mixed_rate > self.max_mixed_utterance_rate,
                policy=self,
            )
            for speaker_id in speaker_ids
        ]
        expected_roles = expected_roles or {}
        role_accuracy, auto_accept_accuracy, high_confidence_error_count = _accuracy_metrics(
            decisions,
            expected_roles,
        )

        pending_confirmation = [
            decision
            for decision in decisions
            if decision.action in {ACTION_NEEDS_REVIEW, ACTION_BLOCKED}
        ]
        low_confidence = [
            _decision_payload(decision)
            for decision in decisions
            if (
                decision.action == ACTION_NEEDS_REVIEW
                and normalize_role(decision.predicted_role) in CLINICAL_ROLES
                and decision.provider != "manual"
            )
        ]
        unmapped = [
            _decision_payload(decision)
            for decision in decisions
            if decision.reason_code == "unmapped_speaker"
        ]
        unresolved = [
            _decision_payload(decision)
            for decision in pending_confirmation
        ]
        auto_accept_count = sum(1 for decision in decisions if decision.action == ACTION_AUTO_ACCEPT)
        manual_confirmation_rate = len(pending_confirmation) / max(len(speaker_ids), 1)

        metrics = SpeakerRoleQualityMetrics(
            segment_count=len(segments),
            speaker_count=len(speaker_ids),
            speaker_ids=speaker_ids,
            speaker_assignment_count=len(asr_result.speaker_assignments),
            low_confidence_clinical_role_count=len(low_confidence),
            unmapped_speaker_count=len(unmapped),
            unresolved_assignment_count=len(unresolved),
            mixed_utterance_candidate_count=len(mixed),
            mixed_utterance_candidate_rate=round(mixed_rate, 4),
            manual_confirmation_rate=round(manual_confirmation_rate, 4),
            role_accuracy=role_accuracy,
            auto_accept_accuracy=auto_accept_accuracy,
            auto_accept_coverage=round(auto_accept_count / max(len(speaker_ids), 1), 4)
            if speaker_ids
            else 0.0,
            auto_accept_count=auto_accept_count,
            high_confidence_error_count=high_confidence_error_count,
            confidence_threshold=self.confidence_threshold,
            max_manual_confirmation_rate=self.max_manual_confirmation_rate,
            max_mixed_utterance_rate=self.max_mixed_utterance_rate,
        )
        status = _status(
            metrics=metrics,
            decisions=decisions,
            role_accuracy=role_accuracy,
            mixed_rate=mixed_rate,
            policy=self,
            has_segments=bool(segments),
        )
        reasons = _reasons(
            low_confidence=low_confidence,
            unmapped=unmapped,
            unresolved=unresolved,
            mixed=mixed,
            mixed_rate=mixed_rate,
            role_accuracy=role_accuracy,
            manual_confirmation_rate=manual_confirmation_rate,
            decisions=decisions,
            policy=self,
            has_segments=bool(segments),
        )
        return SpeakerRoleQualityResult(
            status=status,
            reasons=reasons,
            metrics=metrics,
            policy_version=self.policy_version,
            decisions=decisions,
            pending_confirmation=pending_confirmation,
            low_confidence_clinical_roles=low_confidence,
            unmapped_speakers=unmapped,
            unresolved_assignments=unresolved,
            mixed_utterance_candidates=mixed,
        )

    def legacy_report(
        self,
        asr_result: ASRResult,
        *,
        expected_roles: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        quality = self.evaluate(asr_result, expected_roles=expected_roles)
        metrics = quality.metrics
        return {
            "status": quality.status,
            "summary": {
                "segment_count": metrics.segment_count,
                "speaker_count": metrics.speaker_count,
                "speaker_ids": metrics.speaker_ids,
                "speaker_assignment_count": metrics.speaker_assignment_count,
                "manual_confirmation_rate": metrics.manual_confirmation_rate,
                "role_accuracy": metrics.role_accuracy,
                "auto_accept_accuracy": metrics.auto_accept_accuracy,
                "auto_accept_coverage": metrics.auto_accept_coverage,
                "mixed_utterance_candidate_rate": metrics.mixed_utterance_candidate_rate,
            },
            "quality_gate": {
                "policy_version": quality.policy_version,
                "confidence_threshold": metrics.confidence_threshold,
                "max_manual_confirmation_rate": metrics.max_manual_confirmation_rate,
                "max_mixed_utterance_rate": metrics.max_mixed_utterance_rate,
                "low_confidence_clinical_role_count": metrics.low_confidence_clinical_role_count,
                "unmapped_speaker_count": metrics.unmapped_speaker_count,
                "unresolved_assignment_count": metrics.unresolved_assignment_count,
                "mixed_utterance_candidate_count": metrics.mixed_utterance_candidate_count,
                "high_confidence_error_count": metrics.high_confidence_error_count,
            },
            "decisions": [decision.model_dump(mode="json") for decision in quality.decisions],
            "pending_confirmation": [
                decision.model_dump(mode="json") for decision in quality.pending_confirmation
            ],
            "low_confidence_clinical_roles": quality.low_confidence_clinical_roles,
            "unmapped_speakers": quality.unmapped_speakers,
            "unresolved_assignments": quality.unresolved_assignments,
            "mixed_utterance_candidates": quality.mixed_utterance_candidates,
            "recommendations": quality.reasons,
            "role_quality": quality.model_dump(mode="json"),
        }


DEFAULT_SPEAKER_ROLE_QUALITY_POLICY = SpeakerRoleQualityPolicy()


def build_speaker_role_quality(
    asr_result: ASRResult,
    *,
    expected_roles: dict[str, str] | None = None,
    policy: SpeakerRoleQualityPolicy | None = None,
) -> SpeakerRoleQualityResult:
    return (policy or DEFAULT_SPEAKER_ROLE_QUALITY_POLICY).evaluate(
        asr_result,
        expected_roles=expected_roles,
    )


def attach_speaker_role_quality(
    asr_result: ASRResult,
    *,
    expected_roles: dict[str, str] | None = None,
    policy: SpeakerRoleQualityPolicy | None = None,
) -> ASRResult:
    quality = build_speaker_role_quality(
        asr_result,
        expected_roles=expected_roles,
        policy=policy,
    )
    return asr_result.model_copy(update={"role_quality": quality})


def legacy_speaker_role_quality_report(
    asr_result: ASRResult,
    *,
    expected_roles: dict[str, str] | None = None,
    policy: SpeakerRoleQualityPolicy | None = None,
) -> dict[str, Any]:
    return (policy or DEFAULT_SPEAKER_ROLE_QUALITY_POLICY).legacy_report(
        asr_result,
        expected_roles=expected_roles,
    )


def _decision_for_speaker(
    speaker_id: str,
    *,
    segments: list[ASRSegment],
    assignment: SpeakerRoleAssignment | None,
    speaker_count: int,
    mixed_blocked: bool,
    policy: SpeakerRoleQualityPolicy,
) -> SpeakerRoleDecision:
    speaker_segments = [
        segment for segment in segments if _speaker_id(segment) == speaker_id
    ]
    if assignment is None:
        assignment = _assignment_from_segments(speaker_id, speaker_segments)
    reviewed_by_doctor = _speaker_reviewed_by_doctor(speaker_segments, assignment)
    return speaker_role_decision(
        speaker_id=speaker_id,
        role=assignment.role,
        confidence=assignment.confidence,
        source=assignment.source,
        reason=assignment.reason,
        requires_confirmation=assignment.requires_confirmation,
        reviewed_by_doctor=reviewed_by_doctor,
        speaker_count=speaker_count,
        mixed_blocked=mixed_blocked,
        policies=policy.provider_policies,
    )


def _assignment_from_segments(
    speaker_id: str,
    segments: list[ASRSegment],
) -> SpeakerRoleAssignment:
    stable_segments = [segment for segment in segments if not segment.provisional]
    roles = [
        normalize_role(segment.role)
        for segment in stable_segments
        if normalize_role(segment.role) in CLINICAL_ROLES
    ]
    role = roles[0] if roles else None
    confidences = [
        float(segment.role_confidence)
        for segment in stable_segments
        if segment.role_confidence is not None
    ]
    sources = [segment.role_source for segment in stable_segments if segment.role_source]
    reviewed = all(segment.reviewed_by_doctor for segment in stable_segments) if stable_segments else False
    source = "manual_speaker_map" if reviewed else (sources[0] if sources else "unassigned")
    return SpeakerRoleAssignment(
        speaker_id=speaker_id,
        role=role,
        confidence=max(confidences) if confidences else 0.0,
        source=source,
        reason=None,
        requires_confirmation=not reviewed and role is None,
    )


def _speaker_reviewed_by_doctor(
    segments: list[ASRSegment],
    assignment: SpeakerRoleAssignment,
) -> bool:
    source = str(assignment.source or "").strip().lower()
    if any(source.startswith(prefix) for prefix in MANUAL_SOURCE_PREFIXES):
        return True
    stable_segments = [segment for segment in segments if not segment.provisional]
    return bool(stable_segments) and all(segment.reviewed_by_doctor for segment in stable_segments)


def _status(
    *,
    metrics: SpeakerRoleQualityMetrics,
    decisions: list[SpeakerRoleDecision],
    role_accuracy: float | None,
    mixed_rate: float,
    policy: SpeakerRoleQualityPolicy,
    has_segments: bool,
) -> str:
    if not has_segments:
        return "passed"
    if mixed_rate > policy.max_mixed_utterance_rate:
        return "blocked"
    if any(decision.action == ACTION_BLOCKED for decision in decisions):
        return "blocked"
    if role_accuracy is not None and role_accuracy < policy.min_role_accuracy:
        return "blocked"
    if (
        metrics.low_confidence_clinical_role_count
        or metrics.unmapped_speaker_count
        or metrics.unresolved_assignment_count
        or metrics.manual_confirmation_rate > policy.max_manual_confirmation_rate
    ):
        return "needs_review"
    return "passed"


def _accuracy_metrics(
    decisions: list[SpeakerRoleDecision],
    expected_roles: dict[str, str],
) -> tuple[float | None, float | None, int]:
    if not expected_roles:
        return None, None, 0
    total = 0
    correct = 0
    auto_total = 0
    auto_correct = 0
    high_confidence_errors = 0
    decision_map = {decision.speaker_id: decision for decision in decisions}
    for speaker_id, expected in expected_roles.items():
        expected_role = normalize_role(expected)
        if expected_role not in CLINICAL_ROLES:
            continue
        total += 1
        decision = decision_map.get(speaker_id)
        actual_role = normalize_role(decision.predicted_role if decision else None)
        if actual_role == expected_role:
            correct += 1
        if decision and decision.action == ACTION_AUTO_ACCEPT:
            auto_total += 1
            if actual_role == expected_role:
                auto_correct += 1
            else:
                high_confidence_errors += 1
    role_accuracy = round(correct / total, 4) if total else None
    auto_accept_accuracy = round(auto_correct / auto_total, 4) if auto_total else None
    return role_accuracy, auto_accept_accuracy, high_confidence_errors


def _speaker_id(segment: ASRSegment) -> str:
    return str(segment.speaker_id or segment.speaker or "").strip()


def _decision_payload(decision: SpeakerRoleDecision) -> dict[str, Any]:
    return decision.model_dump(mode="json")


def _looks_like_mixed_medical_utterance(text: str) -> bool:
    compact = "".join(str(text or "").split())
    if len(compact) < 10:
        return False
    doctor_markers = (
        "\u8bf7\u95ee",
        "\u6709\u6ca1\u6709",
        "\u662f\u5426",
        "\u54ea\u91cc",
        "\u4ec0\u4e48\u65f6\u5019",
        "\u591a\u5c11\u5c81",
        "\u505a\u4ec0\u4e48\u5de5\u4f5c",
    )
    patient_markers = (
        "\u6211\u662f",
        "\u6211\u6709",
        "\u6211\u53d1\u70ed",
        "\u6211\u54b3\u55fd",
        "\u5403\u8fc7",
        "\u7528\u8fc7",
        "\u75bc",
    )
    return any(marker in compact for marker in doctor_markers) and any(
        marker in compact for marker in patient_markers
    )


def _compact(text: str, limit: int = 80) -> str:
    value = " ".join(str(text or "").split())
    return value if len(value) <= limit else f"{value[:limit]}..."


def _reasons(
    *,
    low_confidence: list[dict[str, Any]],
    unmapped: list[dict[str, Any]],
    unresolved: list[dict[str, Any]],
    mixed: list[dict[str, Any]],
    mixed_rate: float,
    role_accuracy: float | None,
    manual_confirmation_rate: float,
    decisions: list[SpeakerRoleDecision],
    policy: SpeakerRoleQualityPolicy,
    has_segments: bool,
) -> list[str]:
    items: list[str] = []
    if not has_segments:
        items.append("未提供稳定说话人角色片段，兼容历史纯文本结果。")
    if low_confidence:
        items.append("低置信度临床角色需要一次全局说话人角色确认。")
    if unmapped:
        items.append("存在未映射的稳定说话人，需要先完成医生/患者/其他角色映射。")
    if unresolved:
        items.append("存在待确认的整位说话人角色，生成病历前需要一次全局确认。")
    if manual_confirmation_rate > policy.max_manual_confirmation_rate:
        items.append("人工确认率超过说话人角色质量策略阈值。")
    if mixed_rate > policy.max_mixed_utterance_rate or mixed:
        items.append("疑似混合语句需要先拆句或重新校准说话人边界。")
    if any(decision.reason_code == "single_speaker_counterexample" for decision in decisions):
        items.append("单人输入不能伪造成医生和患者两人对话。")
    if any(decision.reason_code == "unknown_provider" for decision in decisions):
        items.append("未知说话人角色 Provider 已安全降级为人工确认。")
    if role_accuracy is not None and role_accuracy < policy.min_role_accuracy:
        items.append("固定样本角色准确率未达到说话人角色质量策略。")
    if not items:
        items.append("说话人角色质量门禁已通过。")
    return items
