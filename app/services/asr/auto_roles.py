from __future__ import annotations

from collections import OrderedDict

from app.schemas.asr import ASRResult, ASRSegment, SpeakerRoleAssignment
from app.services.asr.role_quality import build_speaker_role_quality
from app.services.asr.speaker_diarization import ROLE_DOCTOR, ROLE_OTHER, ROLE_PATIENT, enhance_speaker_diarization


AUTO_ROLE_WARNING = "系统自动推定说话人角色，最终病历字段仍需医生审核。"
ROLE_LABEL_ALIASES = {
    "医生": ROLE_DOCTOR,
    "doctor": ROLE_DOCTOR,
    "dr": ROLE_DOCTOR,
    "患者": ROLE_PATIENT,
    "patient": ROLE_PATIENT,
    "陪同人员": ROLE_OTHER,
    "陪诊": ROLE_OTHER,
    "家属": ROLE_OTHER,
    "其他": ROLE_OTHER,
    "other": ROLE_OTHER,
}
PRESERVED_ROLE_STRATEGIES = {"manual_speaker_role_map"}


def ensure_automatic_speaker_roles(result: ASRResult) -> ASRResult:
    """Assign stable provisional clinical roles without requiring manual speaker mapping."""
    original_strategy = result.role_strategy
    updated = enhance_speaker_diarization(result)
    segments = updated.segments or [ASRSegment(speaker="speaker_0", speaker_id="speaker_0", text=updated.text)]
    speaker_ids = _ordered_speaker_ids(segments)
    existing = {item.speaker_id: item for item in updated.speaker_assignments}
    assigned_roles = {item.role for item in existing.values() if item.role}
    replacements: dict[str, SpeakerRoleAssignment] = {}

    for index, speaker_id in enumerate(speaker_ids):
        current = existing.get(speaker_id)
        role = current.role if current and current.role else None
        confidence = current.confidence if current else 0.0
        source = current.source if current else "unassigned"
        reason = current.reason if current else None
        requires_warning = bool(current and current.requires_confirmation)
        label_role = _role_from_label(speaker_id)
        if label_role and (role is None or role == ROLE_OTHER or source in {"unassigned", "single_speaker", "multi_speaker_fallback"}):
            role = label_role
            assigned_roles.add(role)
            confidence = max(float(confidence or 0.0), 0.96)
            source = "auto_role_from_speaker_label"
            reason = "说话人标签已明确指向临床角色，系统自动沿用。"
            requires_warning = False
        if role is None:
            role = _fallback_role(index, speaker_count=len(speaker_ids), assigned_roles=assigned_roles)
            assigned_roles.add(role)
            confidence = 0.55 if len(speaker_ids) == 1 else 0.6
            source = "auto_provisional_single_speaker" if len(speaker_ids) == 1 else "auto_provisional_multi_speaker"
            reason = AUTO_ROLE_WARNING
            requires_warning = True
        elif confidence < 0.9:
            requires_warning = True
        replacements[speaker_id] = SpeakerRoleAssignment(
            speaker_id=speaker_id,
            role=role,
            confidence=round(float(confidence or 0.0), 4),
            source=source if not source.startswith("manual") else source,
            reason=reason,
            requires_confirmation=False,
        )

    enhanced_segments: list[ASRSegment] = []
    for index, segment in enumerate(segments, start=1):
        speaker_id = _segment_speaker_id(segment, index)
        assignment = replacements[speaker_id]
        low_confidence = assignment.confidence < 0.9 or assignment.source.startswith("auto_provisional")
        enhanced_segments.append(
            segment.model_copy(
                update={
                    "speaker": speaker_id,
                    "speaker_id": speaker_id,
                    "speaker_turn": segment.speaker_turn or index,
                    "role": assignment.role,
                    "role_confidence": assignment.confidence,
                    "role_source": assignment.source,
                    "role_warning": AUTO_ROLE_WARNING if low_confidence else None,
                    "needs_review": False,
                    "reviewed_by_doctor": False if assignment.source.startswith("auto") else segment.reviewed_by_doctor,
                }
            )
        )

    warnings = list(updated.warnings or [])
    if any(segment.role_warning for segment in enhanced_segments) and AUTO_ROLE_WARNING not in warnings:
        warnings.append(AUTO_ROLE_WARNING)
    stabilized = updated.model_copy(
        update={
            "segments": enhanced_segments,
            "speaker_assignments": [replacements[speaker_id] for speaker_id in speaker_ids],
            "text": "\n".join(segment.text for segment in enhanced_segments if segment.text.strip()),
            "conversation_text": _conversation_from_segments(enhanced_segments),
            "needs_review": False,
            "reviewed_by_doctor": False,
            "warnings": warnings,
            "role_strategy": (
                original_strategy
                if original_strategy in PRESERVED_ROLE_STRATEGIES
                else updated.role_strategy
                if updated.role_strategy in PRESERVED_ROLE_STRATEGIES
                else "automatic_provisional_roles"
            ),
        }
    )
    return stabilized.model_copy(update={"role_quality": build_speaker_role_quality(stabilized)})


def _ordered_speaker_ids(segments: list[ASRSegment]) -> list[str]:
    ordered: "OrderedDict[str, None]" = OrderedDict()
    for index, segment in enumerate(segments, start=1):
        ordered.setdefault(_segment_speaker_id(segment, index), None)
    return list(ordered)


def _segment_speaker_id(segment: ASRSegment, index: int) -> str:
    return str(segment.speaker_id or segment.speaker or f"speaker_{index - 1}").strip() or f"speaker_{index - 1}"


def _fallback_role(index: int, *, speaker_count: int, assigned_roles: set[str]) -> str:
    if speaker_count == 1:
        return ROLE_PATIENT
    if ROLE_DOCTOR not in assigned_roles and index == 0:
        return ROLE_DOCTOR
    if ROLE_PATIENT not in assigned_roles:
        return ROLE_PATIENT
    return ROLE_OTHER


def _role_from_label(label: str | None) -> str | None:
    normalized = str(label or "").strip().lower()
    return ROLE_LABEL_ALIASES.get(normalized)


def _conversation_from_segments(segments: list[ASRSegment]) -> str:
    return "\n".join(
        f"[{segment.role or segment.speaker_id or segment.speaker or 'speaker'}] {segment.text}"
        for segment in segments
        if segment.text.strip()
    )
