from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass

from app.schemas.asr import (
    ASRResult,
    ASRSegment,
    DiarizationTurn,
    SpeakerRoleAssignment,
)
from app.services.asr.role_strategy import conversation_from_segments


ROLE_DOCTOR = "医生"
ROLE_PATIENT = "患者"
ROLE_OTHER = "其他"
FINAL_ROLES = {ROLE_DOCTOR, ROLE_PATIENT, ROLE_OTHER}

DOCTOR_ANCHORS = (
    "我是医生",
    "我是实习医生",
    "主治医生",
    "接诊医生",
    "请问",
)
DOCTOR_KEYWORDS = (
    "哪里不舒服",
    "什么时候",
    "多长时间",
    "有没有",
    "是否",
    "怎么了",
    "多大",
    "多少岁",
    "做什么工作",
    "用过什么药",
    "药物过敏",
    "测过体温",
    "做过检查",
    "还有其他",
    "既往",
)
PATIENT_KEYWORDS = (
    "我发烧",
    "我发热",
    "我咳嗽",
    "我头晕",
    "我胸闷",
    "我疼",
    "我痛",
    "不舒服",
    "吃了",
    "用了",
    "天前",
    "小时前",
    "一直",
    "症状",
)
FILLER_PATTERN = re.compile(r"[嗯呃哦啊对是好的没有]+[，。！？,.!?\s]*")
GLOBAL_REVIEW_WARNING = (
    "Speaker identities are acoustically grouped; uncertain clinical roles require one global mapping confirmation."
)


@dataclass
class _SpeakerStats:
    speaker_id: str
    text: str
    text_length: int
    meaningful_length: int
    duration: float
    max_turn_duration: float
    turn_count: int
    doctor_score: float
    patient_score: float


def enhance_speaker_diarization(result: ASRResult) -> ASRResult:
    """Normalize acoustic speakers and assign roles once per speaker.

    Streaming windows are deliberately excluded: without a VAD/speaker boundary
    they may contain multiple people and must not enter medical previews.
    """
    updated = result.model_copy(deep=True)
    raw_segments = updated.segments or [
        ASRSegment(speaker="speaker_0", speaker_id="speaker_0", text=updated.text)
    ]
    stable_segments = [segment for segment in raw_segments if not segment.provisional]
    if not stable_segments:
        updated.segments = raw_segments
        updated.speaker_assignments = []
        updated.diarization_turns = []
        updated.conversation_text = ""
        updated.needs_review = True
        return updated

    boundary_segments = _split_segments_by_diarization_turns(stable_segments, updated.diarization_turns)
    normalized = _normalize_speaker_ids(boundary_segments)
    merged = _merge_stable_utterances(_merge_short_speaker_clusters(normalized))
    assignments = _assign_roles_by_speaker(merged)
    assignment_map = {item.speaker_id: item for item in assignments}

    enhanced: list[ASRSegment] = []
    for index, segment in enumerate(merged, start=1):
        speaker_id = _normalized_speaker(segment.speaker_id or segment.speaker)
        assignment = assignment_map.get(speaker_id)
        manual_role = segment.role if segment.reviewed_by_doctor and segment.role in FINAL_ROLES else None
        role = manual_role or (assignment.role if assignment else None)
        role_source = "manual" if manual_role else (assignment.source if assignment else "unassigned")
        confidence = 0.99 if manual_role else (assignment.confidence if assignment else 0.0)
        requires_confirmation = False if manual_role else bool(
            assignment is None or assignment.requires_confirmation
        )
        enhanced.append(
            segment.model_copy(
                update={
                    "speaker": speaker_id,
                    "speaker_id": speaker_id,
                    "speaker_turn": index,
                    "role": role,
                    "role_confidence": confidence if role else None,
                    "role_source": role_source,
                    "role_note": assignment.reason if assignment else "需要确认整位说话人的角色",
                    "needs_review": requires_confirmation,
                }
            )
        )

    updated.segments = enhanced
    updated.speaker_assignments = assignments
    updated.diarization_turns = _diarization_turns(enhanced)
    updated.text = "\n".join(segment.text for segment in enhanced if segment.text.strip())
    updated.conversation_text = _conversation_with_speaker_fallback(enhanced)
    updated.needs_review = any(item.requires_confirmation for item in assignments)
    updated.reviewed_by_doctor = bool(assignments) and all(
        not item.requires_confirmation for item in assignments
    )
    updated.role_strategy = "global_speaker_role_assignment"
    if updated.needs_review and GLOBAL_REVIEW_WARNING not in updated.warnings:
        updated.warnings.append(GLOBAL_REVIEW_WARNING)
    return updated


def _split_segments_by_diarization_turns(
    segments: list[ASRSegment],
    turns: list[DiarizationTurn],
) -> list[ASRSegment]:
    valid_turns = sorted(
        [turn for turn in turns if turn.end_time > turn.start_time],
        key=lambda item: (item.start_time, item.end_time),
    )
    if not valid_turns:
        return segments

    split_segments: list[ASRSegment] = []
    for segment_index, segment in enumerate(segments):
        if segment.start_time is None or segment.end_time is None or segment.end_time <= segment.start_time:
            split_segments.append(segment)
            continue

        overlaps = _segment_turn_overlaps(segment, valid_turns)
        if not overlaps:
            split_segments.append(segment)
            continue

        speakers = {_normalized_speaker(item["speaker_id"]) for item in overlaps}
        if len(speakers) <= 1:
            speaker_id = str(overlaps[0]["speaker_id"])
            split_segments.append(
                segment.model_copy(
                    update={
                        "speaker": speaker_id,
                        "speaker_id": speaker_id,
                        "speaker_confidence": overlaps[0]["confidence"],
                        "overlap": bool(segment.overlap or overlaps[0]["overlap"]),
                    }
                )
            )
            continue

        text_chunks = _split_text_by_duration(segment.text, [float(item["duration"]) for item in overlaps])
        base_id = segment.segment_id or f"segment-{segment_index + 1}"
        for split_index, (item, text) in enumerate(zip(overlaps, text_chunks, strict=False), start=1):
            cleaned_text = text.strip()
            if not cleaned_text:
                continue
            speaker_id = str(item["speaker_id"])
            split_segments.append(
                segment.model_copy(
                    update={
                        "segment_id": f"{base_id}-speaker-{split_index}",
                        "revision": segment.revision + 1,
                        "provisional": False,
                        "speaker": speaker_id,
                        "speaker_id": speaker_id,
                        "speaker_confidence": item["confidence"],
                        "role": None,
                        "role_confidence": None,
                        "role_source": "diarization_turn_split",
                        "role_note": None,
                        "speaker_turn": None,
                        "needs_review": False,
                        "reviewed_by_doctor": False,
                        "original_text": segment.original_text or segment.text,
                        "overlap": bool(segment.overlap or item["overlap"]),
                        "text": cleaned_text,
                        "start_time": round(float(item["start_time"]), 3),
                        "end_time": round(float(item["end_time"]), 3),
                    }
                )
            )
    return split_segments


def _segment_turn_overlaps(
    segment: ASRSegment,
    turns: list[DiarizationTurn],
) -> list[dict[str, object]]:
    assert segment.start_time is not None
    assert segment.end_time is not None
    raw_overlaps: list[dict[str, object]] = []
    for turn in turns:
        start = max(float(segment.start_time), float(turn.start_time))
        end = min(float(segment.end_time), float(turn.end_time))
        duration = end - start
        if duration < 0.05:
            continue
        raw_overlaps.append(
            {
                "start_time": start,
                "end_time": end,
                "duration": duration,
                "speaker_id": turn.speaker_id,
                "confidence": turn.confidence,
                "overlap": turn.overlap,
            }
        )
    if not raw_overlaps:
        return []

    merged: list[dict[str, object]] = []
    for item in raw_overlaps:
        if (
            merged
            and _normalized_speaker(str(merged[-1]["speaker_id"])) == _normalized_speaker(str(item["speaker_id"]))
            and float(item["start_time"]) - float(merged[-1]["end_time"]) <= 0.15
            and bool(item["overlap"]) == bool(merged[-1]["overlap"])
        ):
            previous = merged[-1]
            previous["end_time"] = item["end_time"]
            previous["duration"] = float(previous["duration"]) + float(item["duration"])
            previous["confidence"] = _minimum_optional(
                previous["confidence"] if isinstance(previous["confidence"], float) else None,
                item["confidence"] if isinstance(item["confidence"], float) else None,
            )
        else:
            merged.append(item)
    return merged


def _split_text_by_duration(text: str, durations: list[float]) -> list[str]:
    if not durations:
        return [text]
    cleaned = text.strip()
    if not cleaned:
        return ["" for _ in durations]
    if len(durations) == 1:
        return [cleaned]

    total = sum(max(0.001, duration) for duration in durations)
    cursor = 0
    chunks: list[str] = []
    for index, duration in enumerate(durations[:-1], start=1):
        remaining_parts = len(durations) - index
        target = round(len(cleaned) * sum(max(0.001, value) for value in durations[:index]) / total)
        target = max(cursor + 1, min(target, len(cleaned) - remaining_parts))
        target = _nearest_text_boundary(cleaned, target, cursor + 1, len(cleaned) - remaining_parts)
        chunks.append(cleaned[cursor:target])
        cursor = target
    chunks.append(cleaned[cursor:])
    return chunks


def _nearest_text_boundary(text: str, target: int, lower: int, upper: int) -> int:
    boundary_chars = set(" ,.;:!?，。！？；、")
    if lower >= upper:
        return target
    window = min(12, max(target - lower, upper - target))
    candidates = []
    for offset in range(window + 1):
        for candidate in (target - offset, target + offset):
            if lower <= candidate <= upper and candidate < len(text) and text[candidate] in boundary_chars:
                candidates.append(candidate + 1)
    return min(candidates, key=lambda item: abs(item - target), default=target)


def _normalize_speaker_ids(segments: list[ASRSegment]) -> list[ASRSegment]:
    aliases: dict[str, str] = {}
    normalized: list[ASRSegment] = []
    for segment in segments:
        raw = _normalized_speaker(segment.speaker_id or segment.speaker)
        if not raw:
            raw = "speaker_0"
        aliases.setdefault(raw, raw)
        normalized.append(
            segment.model_copy(update={"speaker": aliases[raw], "speaker_id": aliases[raw]})
        )
    return normalized


def _merge_short_speaker_clusters(segments: list[ASRSegment]) -> list[ASRSegment]:
    groups: dict[str, list[int]] = defaultdict(list)
    for index, segment in enumerate(segments):
        groups[_normalized_speaker(segment.speaker_id or segment.speaker)].append(index)
    if len(groups) < 2:
        return segments

    stats = {speaker: _speaker_stats(speaker, [segments[i] for i in indexes]) for speaker, indexes in groups.items()}
    short_speakers = {
        speaker
        for speaker, item in stats.items()
        if (
            item.duration < 3.0
            or item.max_turn_duration < 1.0 and item.duration < 5.0
            or (
                12 <= item.text_length <= 40
                and item.meaningful_length / max(item.text_length, 1) <= 0.25
            )
        )
    }
    substantial = set(groups) - short_speakers
    if not substantial:
        return segments

    merged: list[ASRSegment] = []
    for index, segment in enumerate(segments):
        speaker = _normalized_speaker(segment.speaker_id or segment.speaker)
        if speaker not in short_speakers:
            merged.append(segment)
            continue
        replacement = _nearest_substantial_speaker(segments, index, substantial)
        if replacement is None:
            merged.append(segment)
            continue
        merged.append(
            segment.model_copy(
                update={
                    "speaker": replacement,
                    "speaker_id": replacement,
                    "speaker_confidence": min(segment.speaker_confidence or 0.65, 0.65),
                    "role_note": "短促声纹簇已按相邻稳定说话人合并",
                }
            )
        )
    return merged


def _merge_stable_utterances(segments: list[ASRSegment]) -> list[ASRSegment]:
    merged: list[ASRSegment] = []
    for segment in segments:
        if not merged:
            merged.append(segment)
            continue
        previous = merged[-1]
        same_speaker = (previous.speaker_id or previous.speaker) == (segment.speaker_id or segment.speaker)
        gap = (
            float(segment.start_time) - float(previous.end_time)
            if segment.start_time is not None and previous.end_time is not None
            else float("inf")
        )
        combined_duration = (
            float(segment.end_time) - float(previous.start_time)
            if segment.end_time is not None and previous.start_time is not None
            else float("inf")
        )
        combined_text = f"{previous.text}{segment.text}".strip()
        if (
            same_speaker
            and not previous.overlap
            and not segment.overlap
            and 0.0 <= gap <= 0.8
            and combined_duration <= 8.0
            and len(combined_text) <= 100
        ):
            merged[-1] = previous.model_copy(
                update={
                    "text": combined_text,
                    "end_time": segment.end_time,
                    "confidence": _minimum_optional(previous.confidence, segment.confidence),
                    "speaker_confidence": _minimum_optional(
                        previous.speaker_confidence,
                        segment.speaker_confidence,
                    ),
                }
            )
        else:
            merged.append(segment)
    return merged


def _nearest_substantial_speaker(
    segments: list[ASRSegment],
    index: int,
    substantial: set[str],
) -> str | None:
    for distance in range(1, len(segments)):
        candidates: list[tuple[float, str]] = []
        for candidate_index in (index - distance, index + distance):
            if candidate_index < 0 or candidate_index >= len(segments):
                continue
            candidate = segments[candidate_index]
            speaker = _normalized_speaker(candidate.speaker_id or candidate.speaker)
            if speaker not in substantial:
                continue
            temporal_gap = _temporal_gap(segments[index], candidate)
            candidates.append((temporal_gap, speaker))
        if candidates:
            candidates.sort(key=lambda item: item[0])
            return candidates[0][1]
    return None


def _assign_roles_by_speaker(segments: list[ASRSegment]) -> list[SpeakerRoleAssignment]:
    groups: dict[str, list[ASRSegment]] = defaultdict(list)
    for segment in segments:
        groups[_normalized_speaker(segment.speaker_id or segment.speaker)].append(segment)
    ordered_speakers = list(groups)
    manual_roles: dict[str, str] = {}
    for speaker, speaker_segments in groups.items():
        reviewed = [
            segment.role
            for segment in speaker_segments
            if segment.reviewed_by_doctor and segment.role in FINAL_ROLES
        ]
        if reviewed:
            manual_roles[speaker] = Counter(reviewed).most_common(1)[0][0]

    if len(groups) == 1:
        speaker = ordered_speakers[0]
        if speaker in manual_roles:
            return [
                SpeakerRoleAssignment(
                    speaker_id=speaker,
                    role=manual_roles[speaker],
                    confidence=0.99,
                    source="manual",
                    reason="医生已确认整位说话人的角色",
                )
            ]
        return [
            SpeakerRoleAssignment(
                speaker_id=speaker,
                role=None,
                confidence=0.0,
                source="single_speaker",
                reason="仅检测到一位真实说话人，不能伪造成医生和患者两人",
                requires_confirmation=True,
            )
        ]

    stats = {speaker: _speaker_stats(speaker, items) for speaker, items in groups.items()}
    assignments: dict[str, SpeakerRoleAssignment] = {}
    for speaker, role in manual_roles.items():
        assignments[speaker] = SpeakerRoleAssignment(
            speaker_id=speaker,
            role=role,
            confidence=0.99,
            source="manual",
            reason="医生已确认整位说话人的角色",
        )

    doctor_candidates = [speaker for speaker in ordered_speakers if speaker not in assignments]
    if doctor_candidates and not any(item.role == ROLE_DOCTOR for item in assignments.values()):
        ranked_doctors = sorted(
            doctor_candidates,
            key=lambda speaker: (
                stats[speaker].doctor_score - stats[speaker].patient_score,
                stats[speaker].doctor_score,
            ),
            reverse=True,
        )
        doctor = ranked_doctors[0]
        item = stats[doctor]
        margin = item.doctor_score - item.patient_score
        if item.doctor_score >= 2.0 and margin > 0:
            confidence = min(0.94, 0.72 + margin / max(item.doctor_score + item.patient_score, 1.0) * 0.22)
            assignments[doctor] = SpeakerRoleAssignment(
                speaker_id=doctor,
                role=ROLE_DOCTOR,
                confidence=round(confidence, 4),
                source="speaker_context_rules",
                reason="整位说话人的问诊提问和医生身份表达占主导",
                requires_confirmation=confidence < 0.75,
            )

    remaining = [speaker for speaker in ordered_speakers if speaker not in assignments]
    if remaining and not any(item.role == ROLE_PATIENT for item in assignments.values()):
        if len(remaining) == 1:
            patient = remaining[0]
            assignments[patient] = SpeakerRoleAssignment(
                speaker_id=patient,
                role=ROLE_PATIENT,
                confidence=0.86,
                source="global_two_party_constraint",
                reason="已锁定医生，唯一剩余主要说话人按患者处理",
            )
            remaining = []
        else:
            ranked_patients = sorted(
                remaining,
                key=lambda speaker: (
                    stats[speaker].patient_score - stats[speaker].doctor_score,
                    stats[speaker].duration,
                    stats[speaker].meaningful_length,
                ),
                reverse=True,
            )
            patient = ranked_patients[0]
            top = stats[patient]
            next_score = (
                stats[ranked_patients[1]].patient_score - stats[ranked_patients[1]].doctor_score
                if len(ranked_patients) > 1
                else -1.0
            )
            confidence = 0.78 if top.patient_score - top.doctor_score > next_score else 0.62
            assignments[patient] = SpeakerRoleAssignment(
                speaker_id=patient,
                role=ROLE_PATIENT,
                confidence=confidence,
                source="speaker_context_rules",
                reason="整位说话人的症状和个人经历叙述占主导",
                requires_confirmation=confidence < 0.75,
            )
            remaining = [speaker for speaker in remaining if speaker != patient]

    for speaker in remaining:
        assignments[speaker] = SpeakerRoleAssignment(
            speaker_id=speaker,
            role=ROLE_OTHER,
            confidence=0.55,
            source="multi_speaker_fallback",
            reason="检测到第三位及以上说话人，需一次全局映射确认其身份",
            requires_confirmation=True,
        )

    for speaker in ordered_speakers:
        if speaker not in assignments:
            assignments[speaker] = SpeakerRoleAssignment(
                speaker_id=speaker,
                role=None,
                confidence=0.0,
                source="unassigned",
                reason="上下文不足，需一次全局映射确认",
                requires_confirmation=True,
            )
    return [assignments[speaker] for speaker in ordered_speakers]


def _speaker_stats(speaker: str, segments: list[ASRSegment]) -> _SpeakerStats:
    text = "。".join(segment.text.strip() for segment in segments if segment.text.strip())
    durations = [
        max(0.0, float(segment.end_time) - float(segment.start_time))
        for segment in segments
        if segment.start_time is not None and segment.end_time is not None
    ]
    meaningful = FILLER_PATTERN.sub("", text)
    doctor_score = sum(text.count(keyword) for keyword in DOCTOR_KEYWORDS)
    doctor_score += sum(text.count(anchor) * 4 for anchor in DOCTOR_ANCHORS)
    doctor_score += min(text.count("？") + text.count("?"), 8) * 0.6
    patient_score = sum(text.count(keyword) for keyword in PATIENT_KEYWORDS)
    patient_score += min(len(re.findall(r"(?:^|[。！？])我[^，。！？]{1,20}", text)), 6) * 0.6
    return _SpeakerStats(
        speaker_id=speaker,
        text=text,
        text_length=len(re.sub(r"\s+", "", text)),
        meaningful_length=len(re.sub(r"[\s，。！？,.!?]", "", meaningful)),
        duration=round(sum(durations), 3),
        max_turn_duration=round(max(durations, default=0.0), 3),
        turn_count=len(segments),
        doctor_score=float(doctor_score),
        patient_score=float(patient_score),
    )


def _diarization_turns(segments: list[ASRSegment]) -> list[DiarizationTurn]:
    turns: list[DiarizationTurn] = []
    for segment in segments:
        if segment.start_time is None or segment.end_time is None:
            continue
        turns.append(
            DiarizationTurn(
                start_time=max(0.0, float(segment.start_time)),
                end_time=max(float(segment.start_time), float(segment.end_time)),
                speaker_id=segment.speaker_id or segment.speaker or "speaker_0",
                confidence=segment.speaker_confidence,
                overlap=segment.overlap,
            )
        )
    return turns


def _conversation_with_speaker_fallback(segments: list[ASRSegment]) -> str:
    aliases: dict[str, str] = {}
    lines: list[str] = []
    for segment in segments:
        speaker = segment.speaker_id or segment.speaker or "speaker_0"
        aliases.setdefault(speaker, f"说话人 {chr(65 + min(len(aliases), 25))}")
        label = segment.role if segment.role in FINAL_ROLES else aliases[speaker]
        if segment.text.strip():
            lines.append(f"[{label}] {segment.text.strip()}")
    return "\n".join(lines)


def _temporal_gap(left: ASRSegment, right: ASRSegment) -> float:
    if left.start_time is None or left.end_time is None or right.start_time is None or right.end_time is None:
        return float("inf")
    if right.end_time <= left.start_time:
        return left.start_time - right.end_time
    if left.end_time <= right.start_time:
        return right.start_time - left.end_time
    return 0.0


def _minimum_optional(left: float | None, right: float | None) -> float | None:
    values = [value for value in (left, right) if value is not None]
    return min(values) if values else None


def _normalized_speaker(speaker: str | None) -> str:
    return re.sub(r"\s+", "", (speaker or "").strip().lower())
