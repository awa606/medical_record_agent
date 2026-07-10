from __future__ import annotations

import re
from collections import defaultdict

from app.schemas.asr import ASRResult, ASRSegment
from app.services.asr.role_strategy import conversation_from_segments


ROLE_DOCTOR = "医生"
ROLE_PATIENT = "患者"
ROLE_OTHER = "其他"
ROLE_PENDING = "待确认"

DOCTOR_KEYWORDS = [
    "你好",
    "请问",
    "哪里",
    "什么时候",
    "多长时间",
    "有没有",
    "是否",
    "怎么了",
    "哪里不舒服",
    "做什么工作",
    "多大",
    "用过什么药",
    "过敏",
    "查体",
    "检查",
    "处理过",
    "现在",
    "之前",
]

PATIENT_KEYWORDS = [
    "我",
    "嗯",
    "是的",
    "没有",
    "发烧",
    "发热",
    "咳嗽",
    "头晕",
    "胸闷",
    "疼",
    "痛",
    "不舒服",
    "吃了",
    "用了",
    "小时",
    "天前",
    "卫生院",
]

QUESTION_MARKERS = ["?", "？", "吗", "呢", "么"]
TURN_WARNING = (
    "Speaker roles were inferred by lightweight text/speaker rules and require doctor review."
)


def enhance_speaker_diarization(result: ASRResult) -> ASRResult:
    """Add lightweight speaker/role turns without claiming true acoustic diarization."""
    updated = result.model_copy(deep=True)
    raw_segments = updated.segments or [ASRSegment(speaker="asr", text=updated.text)]
    expanded_segments = _expand_long_segments(raw_segments)
    speaker_role_map = _infer_speaker_role_map(expanded_segments)

    enhanced: list[ASRSegment] = []
    for index, segment in enumerate(expanded_segments):
        role, confidence, source = _infer_role(segment, speaker_role_map)
        note = _role_note(role, confidence, source)
        enhanced.append(
            segment.model_copy(
                update={
                    "role": role,
                    "role_confidence": confidence,
                    "role_source": source,
                    "role_note": note,
                    "speaker_id": segment.speaker_id or segment.speaker,
                    "speaker_turn": index + 1,
                    "needs_review": segment.needs_review
                    or source != "manual"
                    or confidence < 0.85
                    or role == ROLE_PENDING,
                }
            )
        )

    updated.segments = _merge_adjacent_same_role(enhanced)
    updated.text = "\n".join(segment.text for segment in updated.segments if segment.text.strip())
    updated.conversation_text = conversation_from_segments(updated.segments)
    updated.needs_review = any(segment.needs_review for segment in updated.segments)
    if updated.segments and not updated.role_strategy:
        updated.role_strategy = "speaker_diarization_assist"
    if updated.needs_review and TURN_WARNING not in updated.warnings:
        updated.warnings.append(TURN_WARNING)
    return updated


def _expand_long_segments(segments: list[ASRSegment]) -> list[ASRSegment]:
    expanded: list[ASRSegment] = []
    for segment in segments:
        parts = _split_turn_candidates(segment.text)
        if len(parts) <= 1:
            expanded.append(segment)
            continue
        total_chars = max(sum(len(part) for part in parts), 1)
        cursor = 0
        for offset, part in enumerate(parts):
            start_ratio = cursor / total_chars
            cursor += len(part)
            end_ratio = cursor / total_chars
            expanded.append(
                segment.model_copy(
                    update={
                        "segment_id": (
                            f"{segment.segment_id}-part-{offset + 1:02d}"
                            if segment.segment_id
                            else None
                        ),
                        "text": part,
                        "start_time": _interpolate_time(segment.start_time, segment.end_time, start_ratio),
                        "end_time": _interpolate_time(segment.start_time, segment.end_time, end_ratio),
                        "speaker_turn": None,
                    }
                )
            )
    return expanded


def _split_turn_candidates(text: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", text or "").strip()
    if not normalized:
        return []
    clauses = [
        item.strip()
        for item in re.split(r"(?<=[。！？!?])|(?<=，)\s*", normalized)
        if item.strip()
    ]
    if len(clauses) <= 1 and len(normalized) > 220:
        clauses = [normalized[index:index + 120] for index in range(0, len(normalized), 120)]

    turns: list[str] = []
    buffer = ""
    last_role = ""
    for clause in clauses:
        role, _, _ = _classify_text_role(clause)
        should_flush = (
            buffer
            and (
                len(buffer) + len(clause) > 160
                or (last_role and role and role != last_role)
                or (role == ROLE_DOCTOR and any(marker in clause for marker in QUESTION_MARKERS))
            )
        )
        if should_flush:
            turns.append(buffer.strip())
            buffer = clause
        else:
            buffer = f"{buffer}{clause}" if buffer else clause
        if role != ROLE_PENDING:
            last_role = role
    if buffer.strip():
        turns.append(buffer.strip())
    return turns or [normalized]


def _infer_speaker_role_map(segments: list[ASRSegment]) -> dict[str, tuple[str, float]]:
    unique_speakers = {
        _normalized_speaker(segment.speaker_id or segment.speaker)
        for segment in segments
        if _normalized_speaker(segment.speaker_id or segment.speaker)
    }
    if len(unique_speakers) < 2:
        return {}

    scores: dict[str, dict[str, int]] = defaultdict(lambda: {ROLE_DOCTOR: 0, ROLE_PATIENT: 0})
    for segment in segments:
        speaker = _normalized_speaker(segment.speaker_id or segment.speaker)
        if not speaker:
            continue
        role, confidence, _ = _classify_text_role(segment.text)
        if role in {ROLE_DOCTOR, ROLE_PATIENT}:
            scores[speaker][role] += max(1, round(confidence * 10))

    mapping: dict[str, tuple[str, float]] = {}
    for speaker, role_scores in scores.items():
        doctor_score = role_scores[ROLE_DOCTOR]
        patient_score = role_scores[ROLE_PATIENT]
        if doctor_score == patient_score:
            continue
        total = max(doctor_score + patient_score, 1)
        role = ROLE_DOCTOR if doctor_score > patient_score else ROLE_PATIENT
        mapping[speaker] = (role, min(0.88, 0.55 + abs(doctor_score - patient_score) / total * 0.35))

    if len(unique_speakers) >= 3:
        text_lengths = defaultdict(int)
        for segment in segments:
            speaker = _normalized_speaker(segment.speaker_id or segment.speaker)
            if speaker:
                text_lengths[speaker] += len((segment.text or "").strip())
        for speaker in unique_speakers:
            if speaker not in mapping and text_lengths[speaker] >= 12:
                mapping[speaker] = (ROLE_OTHER, 0.58)
    return mapping


def _infer_role(segment: ASRSegment, speaker_role_map: dict[str, tuple[str, float]]) -> tuple[str, float, str]:
    if segment.reviewed_by_doctor and segment.role in {ROLE_DOCTOR, ROLE_PATIENT, ROLE_OTHER}:
        return segment.role, 0.98, "manual"
    if segment.role in {ROLE_DOCTOR, ROLE_PATIENT, ROLE_OTHER}:
        return segment.role, segment.role_confidence or 0.86, segment.role_source or "existing"

    speaker = _normalized_speaker(segment.speaker_id or segment.speaker)
    if speaker and speaker in speaker_role_map:
        role, confidence = speaker_role_map[speaker]
        return role, confidence, "speaker_map"

    return _classify_text_role(segment.text)


def _classify_text_role(text: str) -> tuple[str, float, str]:
    value = text or ""
    doctor_score = sum(1 for keyword in DOCTOR_KEYWORDS if keyword in value)
    patient_score = sum(1 for keyword in PATIENT_KEYWORDS if keyword in value)
    if any(marker in value for marker in QUESTION_MARKERS):
        doctor_score += 1
    if "我" in value and not any(marker in value for marker in QUESTION_MARKERS):
        patient_score += 1

    if doctor_score == patient_score:
        return ROLE_PENDING, 0.4, "text_rule"
    role = ROLE_DOCTOR if doctor_score > patient_score else ROLE_PATIENT
    total = max(doctor_score + patient_score, 1)
    confidence = min(0.82, 0.52 + abs(doctor_score - patient_score) / total * 0.3)
    return role, confidence, "text_rule"


def _role_note(role: str, confidence: float, source: str) -> str:
    if source == "manual":
        return "医生已人工确认"
    if role == ROLE_PENDING:
        return "角色待确认"
    if role == ROLE_OTHER:
        return "已区分为其他说话人，身份仍需医生确认"
    return "低置信度初判，需医生校正" if confidence < 0.85 else "按说话人/文本规则初判，需医生复核"


def _merge_adjacent_same_role(segments: list[ASRSegment]) -> list[ASRSegment]:
    for index, segment in enumerate(segments, start=1):
        segment.speaker_turn = index
    return segments


def _normalized_speaker(speaker: str | None) -> str:
    return re.sub(r"\s+", "", (speaker or "").strip().lower())


def _interpolate_time(start: float | None, end: float | None, ratio: float) -> float | None:
    if start is None or end is None:
        return None
    return round(start + (end - start) * ratio, 3)
