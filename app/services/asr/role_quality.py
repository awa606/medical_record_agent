from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.schemas.asr import (
    ASRResult,
    ASRSegment,
    SpeakerRoleAssignment,
    SpeakerRoleQualityMetrics,
    SpeakerRoleQualityResult,
)
from app.services.asr.speaker_diarization import ROLE_COMPANION, ROLE_DOCTOR, ROLE_OTHER, ROLE_PATIENT


ROLE_ALIASES = {
    ROLE_DOCTOR: ROLE_DOCTOR,
    ROLE_PATIENT: ROLE_PATIENT,
    ROLE_COMPANION: ROLE_COMPANION,
    ROLE_OTHER: ROLE_OTHER,
    "doctor": ROLE_DOCTOR,
    "patient": ROLE_PATIENT,
    "companion": ROLE_COMPANION,
    "family": ROLE_COMPANION,
    "陪同": ROLE_COMPANION,
    "家属": ROLE_COMPANION,
    "other": ROLE_OTHER,
}
CLINICAL_ROLES = {ROLE_DOCTOR, ROLE_PATIENT, ROLE_COMPANION, ROLE_OTHER}
MANUAL_SOURCE_PREFIXES = ("manual",)


@dataclass(frozen=True)
class SpeakerRoleQualityPolicy:
    confidence_threshold: float = 0.9
    max_manual_confirmation_rate: float = 0.35
    max_mixed_utterance_rate: float = 0.05
    min_role_accuracy: float = 0.9

    def evaluate(
        self,
        asr_result: ASRResult,
        *,
        expected_roles: dict[str, str] | None = None,
    ) -> SpeakerRoleQualityResult:
        segments = [segment for segment in asr_result.segments if not segment.provisional]
        speaker_ids = sorted({_speaker_id(segment) for segment in segments if _speaker_id(segment)})
        assignments = {item.speaker_id: item for item in asr_result.speaker_assignments}
        assignments_present = bool(asr_result.speaker_assignments)

        low_confidence = [
            _segment_payload(segment)
            for segment in segments
            if _is_low_confidence_clinical(
                segment,
                threshold=self.confidence_threshold,
                assignments_present=assignments_present,
            )
        ]
        unmapped = [
            _segment_payload(segment)
            for segment in segments
            if _speaker_id(segment) and not _normalize_role(segment.role)
        ]
        unresolved = [
            item.model_dump(mode="json")
            for item in asr_result.speaker_assignments
            if item.requires_confirmation or not _normalize_role(item.role)
        ]
        mixed = [
            {
                "segment_id": segment.segment_id,
                "speaker_id": _speaker_id(segment),
                "text": _compact(segment.text, 140),
            }
            for segment in segments
            if _looks_like_mixed_medical_utterance(segment.text)
        ]

        role_accuracy = _role_accuracy(assignments, expected_roles or {})
        manual_confirmation_rate = len(unresolved) / max(len(speaker_ids), 1)
        mixed_rate = len(mixed) / max(len(segments), 1)

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
            confidence_threshold=self.confidence_threshold,
            max_manual_confirmation_rate=self.max_manual_confirmation_rate,
            max_mixed_utterance_rate=self.max_mixed_utterance_rate,
        )
        reasons = _reasons(
            low_confidence=low_confidence,
            unmapped=unmapped,
            unresolved=unresolved,
            mixed=mixed,
            mixed_rate=mixed_rate,
            role_accuracy=role_accuracy,
            manual_confirmation_rate=manual_confirmation_rate,
            policy=self,
            has_segments=bool(segments),
        )
        status = _status(
            metrics=metrics,
            role_accuracy=role_accuracy,
            mixed_rate=mixed_rate,
            policy=self,
        )
        return SpeakerRoleQualityResult(
            status=status,
            reasons=reasons,
            metrics=metrics,
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
                "mixed_utterance_candidate_rate": metrics.mixed_utterance_candidate_rate,
            },
            "quality_gate": {
                "confidence_threshold": metrics.confidence_threshold,
                "max_manual_confirmation_rate": metrics.max_manual_confirmation_rate,
                "max_mixed_utterance_rate": metrics.max_mixed_utterance_rate,
                "low_confidence_clinical_role_count": metrics.low_confidence_clinical_role_count,
                "unmapped_speaker_count": metrics.unmapped_speaker_count,
                "unresolved_assignment_count": metrics.unresolved_assignment_count,
                "mixed_utterance_candidate_count": metrics.mixed_utterance_candidate_count,
            },
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


def _status(
    *,
    metrics: SpeakerRoleQualityMetrics,
    role_accuracy: float | None,
    mixed_rate: float,
    policy: SpeakerRoleQualityPolicy,
) -> str:
    if mixed_rate > policy.max_mixed_utterance_rate:
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


def _normalize_role(role: str | None) -> str | None:
    return ROLE_ALIASES.get(str(role or "").strip())


def _speaker_id(segment: ASRSegment) -> str:
    return str(segment.speaker_id or segment.speaker or "").strip()


def _is_manual_source(segment: ASRSegment) -> bool:
    if segment.reviewed_by_doctor:
        return True
    source = str(segment.role_source or "").strip().lower()
    return any(source.startswith(prefix) for prefix in MANUAL_SOURCE_PREFIXES)


def _is_low_confidence_clinical(
    segment: ASRSegment,
    *,
    threshold: float,
    assignments_present: bool,
) -> bool:
    if _normalize_role(segment.role) not in CLINICAL_ROLES:
        return False
    if _is_manual_source(segment):
        return False
    if not (_speaker_id(segment) or assignments_present or segment.role_confidence is not None):
        return False
    confidence = segment.role_confidence
    return confidence is None or confidence < threshold


def _segment_payload(segment: ASRSegment) -> dict[str, Any]:
    return {
        "segment_id": segment.segment_id,
        "speaker_id": _speaker_id(segment),
        "role": segment.role,
        "role_confidence": segment.role_confidence,
        "role_source": segment.role_source,
        "text": _compact(segment.text),
    }


def _role_accuracy(
    assignments: dict[str, SpeakerRoleAssignment],
    expected_roles: dict[str, str],
) -> float | None:
    if not expected_roles:
        return None
    total = 0
    correct = 0
    for speaker_id, expected in expected_roles.items():
        expected_role = _normalize_role(expected)
        if expected_role not in CLINICAL_ROLES:
            continue
        total += 1
        actual = assignments.get(speaker_id)
        if actual and _normalize_role(actual.role) == expected_role:
            correct += 1
    return round(correct / total, 4) if total else None


def _looks_like_mixed_medical_utterance(text: str) -> bool:
    compact = "".join(str(text or "").split())
    if len(compact) < 10:
        return False
    doctor_markers = ("请问", "有没有", "是否", "哪里", "什么时候", "多少岁", "做什么工作")
    patient_markers = ("我是", "我有", "我发热", "我咳嗽", "没有", "吃过", "用过", "疼")
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
    policy: SpeakerRoleQualityPolicy,
    has_segments: bool,
) -> list[str]:
    items: list[str] = []
    if not has_segments:
        items.append("ASRResult 未提供稳定说话人片段，本次不应用说话人角色门禁。")
    if low_confidence:
        items.append("低置信度自动角色不能直接用于正式病历生成，需要医生全局确认。")
    if unmapped:
        items.append("存在未映射的稳定说话人片段，需要先完成医生/患者/其他角色映射。")
    if unresolved:
        items.append("存在需要确认的整位说话人角色，生成病历前需要一次全局确认。")
    if manual_confirmation_rate > policy.max_manual_confirmation_rate:
        items.append("人工确认率超过门禁阈值，当前自动角色覆盖率不足。")
    if mixed_rate > policy.max_mixed_utterance_rate:
        items.append("疑似混合语句率超过门禁阈值，需要先拆句或重新校准说话人边界。")
    if role_accuracy is not None and role_accuracy < policy.min_role_accuracy:
        items.append("固定样本角色准确率未达门禁，不能自动通过。")
    if not items:
        items.append("当前 ASRResult 满足服务端说话人角色质量门禁。")
    return items
