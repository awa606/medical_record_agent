from __future__ import annotations

import asyncio
import gc
import json
import os
import shutil
import tempfile
import threading
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, File, Header, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse

from app.api.audio import (
    _safe_extension,
    _sample_id_from_record,
    _write_audio_record,
    _write_transcript,
    get_upload_dir,
)
from app.schemas import (
    ASRResult,
    ASRSegment,
    ASRSessionCorrectionRequest,
    ASRSessionCorrectionResponse,
    ASRSessionEvent,
    ASRSessionRecord,
    ASRSessionUploadResponse,
    ASRSpeakerMergeRequest,
    ASRSpeakerMergeResponse,
    AudioRecord,
    DiarizationTurn,
    SpeakerRoleAssignment,
)
from app.services.asr import (
    AudioChunk,
    ChunkTranscription,
    apply_manifest_role_strategy,
    create_asr_engine,
    enhance_speaker_diarization,
    merge_chunk_transcriptions,
    split_audio_to_chunks,
)
from app.services.asr.chunking import build_chunk_plan, probe_audio_duration
from app.services.asr.ffmpeg_utils import find_ffprobe_executable
from app.services.asr.role_quality import attach_speaker_role_quality
from app.services.asr.speaker_role_classifier import resolve_speaker_roles


router = APIRouter(prefix="/asr/sessions", tags=["asr-sessions"])

SUPPORTED_ASR_ENGINES = {"mock", "funasr", "sensevoice", "whisper", "qwen3", "online"}
CHUNKABLE_ASR_ENGINES = {"funasr", "sensevoice"}
REALTIME_UPLOAD_ASR_ENGINES = {"mock", "funasr"}
TRANSCRIBING_PROGRESS_INTERVAL_SECONDS = 5.0
TRANSCRIBING_PROGRESS_CAP = 0.88
STREAMING_PROGRESS_EVENT_INTERVAL_SECONDS = 3.0
STREAMING_PROGRESS_WALL_INTERVAL_SECONDS = 0.5
SHORT_AUDIO_CHUNK_SECONDS = 60
LONG_AUDIO_THRESHOLD_SECONDS = 600
DEFAULT_CHUNK_MIN_SECONDS = 120
DEFAULT_REALTIME_UPLOAD_CHUNK_SECONDS = 3
DEFAULT_REALTIME_UPLOAD_MAX_SECONDS = 120
REALTIME_UPLOAD_WARNING = "ASR result was produced by realtime upload chunk transcription."
CHUNKED_LONG_AUDIO_WARNING = "ASR result was produced by chunked long-audio transcription."
SUPPORTED_DIARIZATION_ENGINES = {"auto", "funasr_campp", "pyannote", "three_d_speaker"}
ROLE_LABELS = {
    "doctor": "医生",
    "医生": "医生",
    "patient": "患者",
    "患者": "患者",
    "companion": "陪同人员",
    "family": "陪同人员",
    "陪同": "陪同人员",
    "陪同人员": "陪同人员",
    "家属": "陪同人员",
    "other": "其他",
    "其他": "其他",
    "unknown": "待确认",
    "待确认": "待确认",
    "暂不确定": "待确认",
    "待校正": "待确认",
}

_EVENTS_LOCK = threading.Lock()
_EVENT_ID_CACHE: dict[str, int] = {}
_FUNASR_MODEL_CACHE_LOCK = threading.Lock()
_FUNASR_STREAMING_ENGINE: Any | None = None
_FUNASR_RECONCILIATION_ENGINE: Any | None = None


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _sessions_dir() -> Path:
    path = get_upload_dir() / "asr_sessions"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _assert_safe_session_id(session_id: str) -> None:
    if not session_id or Path(session_id).name != session_id:
        raise HTTPException(status_code=400, detail="Invalid ASR session id")


def _session_dir(session_id: str) -> Path:
    _assert_safe_session_id(session_id)
    return _sessions_dir() / session_id


def _session_path(session_id: str) -> Path:
    return _session_dir(session_id) / "session.json"


def _events_path(session_id: str) -> Path:
    return _session_dir(session_id) / "events.json"


def _event_log_path(session_id: str) -> Path:
    return _session_dir(session_id) / "events.jsonl"


def _result_path(session_id: str) -> Path:
    return _session_dir(session_id) / "result.json"


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)


def _normalize_engine_name(engine: str) -> str:
    normalized = (engine or "mock").strip().lower()
    if normalized not in SUPPORTED_ASR_ENGINES:
        raise HTTPException(
            status_code=400,
            detail="Unsupported ASR engine. Expected mock, funasr, sensevoice, whisper, qwen3, or online.",
        )
    return normalized


def _create_funasr_streaming_engine() -> Any:
    global _FUNASR_STREAMING_ENGINE
    from app.services.asr.funasr_streaming_engine import FunASRStreamingEngine

    with _FUNASR_MODEL_CACHE_LOCK:
        if _FUNASR_STREAMING_ENGINE is None:
            _FUNASR_STREAMING_ENGINE = FunASRStreamingEngine()
        return _FUNASR_STREAMING_ENGINE


def _create_funasr_reconciliation_engine() -> Any:
    global _FUNASR_RECONCILIATION_ENGINE
    from app.services.asr.funasr_engine import FunASREngine

    with _FUNASR_MODEL_CACHE_LOCK:
        if _FUNASR_RECONCILIATION_ENGINE is None:
            _FUNASR_RECONCILIATION_ENGINE = FunASREngine(enable_speaker_diarization=True)
        return _FUNASR_RECONCILIATION_ENGINE


def _write_session(session: ASRSessionRecord) -> None:
    _write_json(_session_path(session.session_id), session.model_dump())


def _read_session(session_id: str) -> ASRSessionRecord:
    path = _session_path(session_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="ASR session not found")
    return ASRSessionRecord.model_validate_json(path.read_text(encoding="utf-8"))


def _write_events(session_id: str, events: list[ASRSessionEvent]) -> None:
    path = _event_log_path(session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = "".join(
        json.dumps(event.model_dump(), ensure_ascii=False) + "\n"
        for event in events
    )
    tmp_path = path.with_name(f"{path.name}.tmp")
    tmp_path.write_text(payload, encoding="utf-8")
    tmp_path.replace(path)
    _EVENT_ID_CACHE[session_id] = events[-1].id if events else 0


def _last_event_id(session_id: str) -> int:
    cached = _EVENT_ID_CACHE.get(session_id)
    if cached is not None:
        return cached
    events = _read_events(session_id)
    value = events[-1].id if events else 0
    _EVENT_ID_CACHE[session_id] = value
    return value


def _append_events(session_id: str, events: list[ASRSessionEvent]) -> None:
    if not events:
        return
    with _EVENTS_LOCK:
        last_id = _last_event_id(session_id)
        next_events = [
            event.model_copy(update={"id": last_id + index + 1})
            for index, event in enumerate(events)
        ]
        path = _event_log_path(session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="\n") as output:
            for event in next_events:
                output.write(json.dumps(event.model_dump(), ensure_ascii=False) + "\n")
        _EVENT_ID_CACHE[session_id] = next_events[-1].id


def _read_events(session_id: str) -> list[ASRSessionEvent]:
    log_path = _event_log_path(session_id)
    if log_path.exists():
        events: list[ASRSessionEvent] = []
        for line in log_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                events.append(ASRSessionEvent.model_validate_json(line))
        return events

    # Read-only compatibility for sessions created before the append-only log.
    legacy_path = _events_path(session_id)
    if not legacy_path.exists():
        return []
    raw_events = json.loads(legacy_path.read_text(encoding="utf-8"))
    return [ASRSessionEvent.model_validate(event) for event in raw_events]


def _write_session_result(session_id: str, result: ASRResult) -> None:
    _write_json(_result_path(session_id), result.model_dump())


def _normalize_role(role: str | None) -> str | None:
    if role is None:
        return None
    normalized = ROLE_LABELS.get(role.strip())
    if normalized is None:
        raise HTTPException(status_code=400, detail=f"Unsupported segment role: {role}")
    return normalized


def _conversation_from_segments(segments: list[ASRSegment]) -> str:
    lines = []
    for segment in segments:
        label = segment.role or segment.speaker or "待确认"
        lines.append(f"[{label}] {segment.text}")
    return "\n".join(lines)


def _plain_text_from_segments(segments: list[ASRSegment]) -> str:
    return "\n".join(segment.text for segment in segments if segment.text.strip())


def _reviewed_event(
    *,
    session: ASRSessionRecord,
    result: ASRResult,
    reviewer: str | None,
    note: str | None,
) -> ASRSessionEvent:
    return ASRSessionEvent(
        id=1,
        event="role_reviewed",
        data={
            "session_id": session.session_id,
            "audio_id": result.audio_id,
            "engine": result.engine,
            "status": "reviewed",
            "reviewer": reviewer,
            "note": note,
            "segments": len(result.segments),
            "asr_result": result.model_dump(),
        },
        created_at=_now(),
    )


def _apply_segment_corrections(
    result: ASRResult,
    payload: ASRSessionCorrectionRequest,
) -> ASRResult:
    updated = result.model_copy(deep=True)
    if not updated.segments:
        updated.segments = [ASRSegment(speaker="asr", role="待确认", text=updated.text)]

    for speaker_correction in payload.speaker_roles:
        role = _normalize_role(speaker_correction.role)
        matched = False
        for segment in updated.segments:
            identity = segment.speaker_id or segment.speaker
            if identity != speaker_correction.speaker_id:
                continue
            matched = True
            segment.role = role
            segment.reviewed_by_doctor = speaker_correction.reviewed_by_doctor
            segment.needs_review = not speaker_correction.reviewed_by_doctor or role == "待确认"
            if speaker_correction.reviewed_by_doctor and role != "待确认":
                segment.role_source = "manual_speaker_map"
                segment.role_confidence = 0.98
                segment.role_note = "医生已确认该说话人的全局角色"
        if not matched:
            raise HTTPException(
                status_code=400,
                detail=f"Speaker id not found: {speaker_correction.speaker_id}",
            )
        assignment = next(
            (
                item
                for item in updated.speaker_assignments
                if item.speaker_id == speaker_correction.speaker_id
            ),
            None,
        )
        replacement = SpeakerRoleAssignment(
            speaker_id=speaker_correction.speaker_id,
            role=role,
            confidence=0.99 if speaker_correction.reviewed_by_doctor else 0.6,
            source="manual_speaker_map" if speaker_correction.reviewed_by_doctor else "manual_draft",
            reason="医生已确认整位说话人的全局角色",
            requires_confirmation=not speaker_correction.reviewed_by_doctor or role == "待确认",
        )
        if assignment is None:
            updated.speaker_assignments.append(replacement)
        else:
            updated.speaker_assignments = [
                replacement if item.speaker_id == speaker_correction.speaker_id else item
                for item in updated.speaker_assignments
            ]

    for correction in payload.segments:
        if correction.index >= len(updated.segments):
            raise HTTPException(status_code=400, detail=f"Segment index out of range: {correction.index}")
        segment = updated.segments[correction.index]
        if correction.role is not None:
            segment.role = _normalize_role(correction.role)
        if correction.text is not None:
            next_text = correction.text.strip()
            if not next_text:
                raise HTTPException(status_code=400, detail=f"Segment text cannot be empty: {correction.index}")
            if next_text != segment.text and not segment.original_text:
                segment.original_text = segment.text
            segment.text = next_text
        segment.reviewed_by_doctor = correction.reviewed_by_doctor
        segment.needs_review = not correction.reviewed_by_doctor or segment.role == "待确认"
        if correction.reviewed_by_doctor and segment.role and segment.role != "待确认":
            segment.role_source = "manual"
            segment.role_confidence = 0.98
            segment.role_note = "医生已人工确认"

    updated.text = _plain_text_from_segments(updated.segments)
    updated.conversation_text = _conversation_from_segments(updated.segments)
    updated.role_strategy = "manual_reviewed"
    all_segments_reviewed = bool(updated.segments) and all(
        segment.reviewed_by_doctor and segment.role != "待确认" for segment in updated.segments
    )
    assignment_review_pending = False if payload.segments and all_segments_reviewed else any(
        assignment.requires_confirmation for assignment in updated.speaker_assignments
    )
    updated.reviewed_by_doctor = all(segment.reviewed_by_doctor for segment in updated.segments)
    updated.needs_review = assignment_review_pending or any(
        segment.needs_review for segment in updated.segments
    )
    if updated.reviewed_by_doctor and "ASR segments were manually reviewed by doctor." not in updated.warnings:
        updated.warnings.append("ASR segments were manually reviewed by doctor.")
    return attach_speaker_role_quality(updated)


def _speaker_identity(segment: ASRSegment) -> str:
    return str(segment.speaker_id or segment.speaker or "").strip()


def _speaker_ids(result: ASRResult) -> list[str]:
    return sorted({_speaker_identity(segment) for segment in result.segments if _speaker_identity(segment)})


def _is_confirmed_role(role: str | None) -> bool:
    return role in {"医生", "患者", "陪同人员", "其他"}


def _merge_speaker_assignment(
    source: SpeakerRoleAssignment | None,
    target: SpeakerRoleAssignment | None,
    *,
    target_speaker: str,
) -> SpeakerRoleAssignment:
    if target is None and source is None:
        return SpeakerRoleAssignment(
            speaker_id=target_speaker,
            role=None,
            confidence=0.0,
            source="manual_speaker_merge",
            reason="说话人合并后仍需确认角色。",
            requires_confirmation=True,
        )
    if target is None and source is not None:
        return SpeakerRoleAssignment(
            speaker_id=target_speaker,
            role=source.role,
            confidence=min(source.confidence, 0.8),
            source="manual_speaker_merge",
            reason="来源说话人已合并到目标说话人，角色需医生复核。",
            requires_confirmation=True,
        )
    if source is None and target is not None:
        return target.model_copy(update={"speaker_id": target_speaker})

    assert source is not None and target is not None
    conflict = bool(source.role and target.role and source.role != target.role)
    role = None if conflict else (target.role or source.role)
    confidence = min(target.confidence, source.confidence)
    requires_confirmation = (
        conflict
        or target.requires_confirmation
        or source.requires_confirmation
        or not _is_confirmed_role(role)
    )
    reason = (
        "合并前两个说话人的角色不一致，需要医生重新确认。"
        if conflict
        else "说话人已人工合并，角色质量已重新计算。"
    )
    return SpeakerRoleAssignment(
        speaker_id=target_speaker,
        role=role,
        confidence=confidence,
        source="manual_speaker_merge",
        reason=reason,
        requires_confirmation=requires_confirmation,
    )


def _merged_speaker_assignments(
    assignments: list[SpeakerRoleAssignment],
    *,
    source_speaker: str,
    target_speaker: str,
) -> list[SpeakerRoleAssignment]:
    source = next((item for item in assignments if item.speaker_id == source_speaker), None)
    target = next((item for item in assignments if item.speaker_id == target_speaker), None)
    merged_target = _merge_speaker_assignment(source, target, target_speaker=target_speaker)

    output: list[SpeakerRoleAssignment] = []
    inserted = False
    for item in assignments:
        if item.speaker_id == source_speaker:
            if target is None and not inserted:
                output.append(merged_target)
                inserted = True
            continue
        if item.speaker_id == target_speaker:
            if not inserted:
                output.append(merged_target)
                inserted = True
            continue
        output.append(item)
    if not inserted:
        output.append(merged_target)
    return output


def _apply_assignment_to_segment(
    segment: ASRSegment,
    assignment: SpeakerRoleAssignment | None,
) -> ASRSegment:
    if assignment is None:
        return segment.model_copy(update={"needs_review": True, "reviewed_by_doctor": False})
    role = assignment.role if _is_confirmed_role(assignment.role) else "待确认"
    reviewed = (
        not assignment.requires_confirmation
        and _is_confirmed_role(assignment.role)
        and str(assignment.source or "").startswith("manual")
    )
    return segment.model_copy(
        update={
            "role": role,
            "role_confidence": assignment.confidence if _is_confirmed_role(assignment.role) else None,
            "role_source": assignment.source,
            "role_note": assignment.reason,
            "needs_review": assignment.requires_confirmation or not _is_confirmed_role(assignment.role),
            "reviewed_by_doctor": reviewed,
        }
    )


def _merge_speakers_in_result(
    result: ASRResult,
    *,
    source_speaker: str,
    target_speaker: str,
) -> tuple[ASRResult, list[str], int, int]:
    source_speaker = source_speaker.strip()
    target_speaker = target_speaker.strip()
    if source_speaker == target_speaker:
        raise HTTPException(status_code=400, detail="source_speaker and target_speaker must be different")

    before_ids = _speaker_ids(result)
    if source_speaker not in before_ids:
        raise HTTPException(status_code=404, detail=f"source_speaker not found: {source_speaker}")
    if target_speaker not in before_ids:
        raise HTTPException(status_code=404, detail=f"target_speaker not found: {target_speaker}")

    assignments = _merged_speaker_assignments(
        result.speaker_assignments,
        source_speaker=source_speaker,
        target_speaker=target_speaker,
    )
    assignment_map = {item.speaker_id: item for item in assignments}
    affected_segment_ids: list[str] = []
    merged_segments: list[ASRSegment] = []
    for index, segment in enumerate(result.segments):
        identity = _speaker_identity(segment)
        if identity == source_speaker:
            affected_segment_ids.append(segment.segment_id or f"segment-{index}")
            segment = segment.model_copy(
                update={
                    "speaker": target_speaker,
                    "speaker_id": target_speaker,
                    "speaker_normalized": target_speaker,
                    "diarization_source": "manual_speaker_merge",
                    "role_note": f"已由医生将 {source_speaker} 合并到 {target_speaker}。",
                }
            )
        merged_segments.append(_apply_assignment_to_segment(segment, assignment_map.get(_speaker_identity(segment))))

    merged_turns = [
        turn.model_copy(update={"speaker_id": target_speaker if turn.speaker_id == source_speaker else turn.speaker_id})
        for turn in result.diarization_turns
    ]
    warning = f"Speaker clusters merged manually: {source_speaker} -> {target_speaker}."
    warnings = list(result.warnings)
    if warning not in warnings:
        warnings.append(warning)

    merged = result.model_copy(
        update={
            "segments": merged_segments,
            "diarization_turns": merged_turns,
            "speaker_assignments": assignments,
            "text": _plain_text_from_segments(merged_segments),
            "conversation_text": _conversation_from_segments(merged_segments),
            "role_strategy": "manual_speaker_merge",
            "warnings": warnings,
            "reviewed_by_doctor": bool(merged_segments) and all(segment.reviewed_by_doctor for segment in merged_segments),
            "needs_review": any(segment.needs_review for segment in merged_segments)
            or any(item.requires_confirmation for item in assignments),
        }
    )
    merged = attach_speaker_role_quality(merged)
    return merged, affected_segment_ids, len(before_ids), len(_speaker_ids(merged))


def _segment_progress(segment: ASRSegment, index: int, total: int, duration: float | None) -> float:
    if duration and segment.end_time is not None:
        return round(min(max(segment.end_time / duration, 0.0), 1.0), 4)
    if total <= 0:
        return 1.0
    return round((index + 1) / total, 4)


def _fallback_segments(result: ASRResult) -> list[ASRSegment]:
    if result.segments:
        return result.segments
    if result.text:
        return [ASRSegment(speaker="asr", role=None, text=result.text)]
    return []


def _initial_asr_stream_events(session: ASRSessionRecord) -> list[ASRSessionEvent]:
    timestamp = _now()
    base = {
        "session_id": session.session_id,
        "audio_id": session.audio_id,
        "engine": session.engine,
    }
    return [
        ASRSessionEvent(
            id=1,
            event="session_created",
            data={**base, "status": "created"},
            created_at=timestamp,
        ),
        ASRSessionEvent(
            id=2,
            event="audio_uploaded",
            data={
                **base,
                "status": "uploaded",
                "filename": session.filename,
            },
            created_at=timestamp,
        ),
        ASRSessionEvent(
            id=3,
            event="transcribing",
            data={**base, "status": "transcribing"},
            created_at=timestamp,
        ),
    ]


def _session_event(
    *,
    session: ASRSessionRecord,
    event: str,
    data: dict[str, object],
) -> ASRSessionEvent:
    return ASRSessionEvent(
        id=1,
        event=event,
        data={
            "session_id": session.session_id,
            "audio_id": session.audio_id,
            "engine": session.engine,
            **data,
        },
        created_at=_now(),
    )


def _append_session_event(
    session_id: str,
    *,
    session: ASRSessionRecord,
    event: str,
    data: dict[str, object],
) -> None:
    _append_events(session_id, [_session_event(session=session, event=event, data=data)])


def _estimated_transcribing_progress(started_at: float, duration: float | None) -> float:
    elapsed = max(time.perf_counter() - started_at, 0.0)
    if duration:
        expected_seconds = max(30.0, min(float(duration) * 0.45, 300.0))
    else:
        expected_seconds = 180.0
    progress = 0.05 + (elapsed / expected_seconds) * 0.75
    return round(min(progress, TRANSCRIBING_PROGRESS_CAP), 4)


def _append_transcribing_progress_event(
    session_id: str,
    *,
    session: ASRSessionRecord,
    started_at: float,
    duration: float | None,
) -> None:
    elapsed = round(time.perf_counter() - started_at, 1)
    _append_session_event(
        session_id,
        session=session,
        event="transcribing_progress",
        data={
            "status": "transcribing",
            "phase": "model_processing",
            "progress": None,
            "progress_kind": "indeterminate",
            "processed_audio_seconds": None,
            "audio_duration_seconds": duration,
            "elapsed_seconds": elapsed,
            "duration": duration,
            "estimated": False,
        },
    )


def _start_transcribing_heartbeat(
    session_id: str,
    *,
    session: ASRSessionRecord,
    duration: float | None,
) -> tuple[threading.Event, threading.Thread, float]:
    stop_event = threading.Event()
    started_at = time.perf_counter()

    def run() -> None:
        while not stop_event.wait(TRANSCRIBING_PROGRESS_INTERVAL_SECONDS):
            current = _read_session(session_id)
            if current.status != "transcribing":
                return
            _append_transcribing_progress_event(
                session_id,
                session=session,
                started_at=started_at,
                duration=duration,
            )

    thread = threading.Thread(
        target=run,
        name=f"asr-progress-{session_id[:8]}",
        daemon=True,
    )
    thread.start()
    return stop_event, thread, started_at


def _append_result_events(
    session_id: str,
    *,
    session: ASRSessionRecord,
    result: ASRResult,
    emit_segments: bool = True,
) -> None:
    events: list[ASRSessionEvent] = []

    def append(event: str, data: dict[str, object]) -> None:
        events.append(_session_event(session=session, event=event, data=data))

    segments = _fallback_segments(result)
    total = len(segments)
    if emit_segments:
        for index, segment in enumerate(segments):
            append(
                "segment",
                {
                    "status": "streaming",
                    "index": index,
                    "total": total,
                    "progress": _segment_progress(segment, index, total, result.duration),
                    "role": segment.role,
                    "speaker": segment.speaker,
                    "text": segment.text,
                    "segment": segment.model_dump(),
                },
            )

    append(
        "completed",
        {
            "status": "completed",
            "segments": total,
            "duration": result.duration,
            "asr_result": result.model_dump(),
        },
    )
    _append_events(session_id, events)


def _offset_segment_for_chunk(segment: ASRSegment, chunk_start_seconds: float) -> ASRSegment:
    def offset(value: float | None) -> float | None:
        if value is None:
            return None
        return round(float(value) + float(chunk_start_seconds), 3)

    return ASRSegment(
        segment_id=segment.segment_id,
        revision=segment.revision,
        provisional=segment.provisional,
        speaker=segment.speaker,
        speaker_id=segment.speaker_id,
        speaker_raw=segment.speaker_raw,
        speaker_normalized=segment.speaker_normalized,
        diarization_source=segment.diarization_source,
        speaker_confidence=segment.speaker_confidence,
        role=segment.role,
        text=segment.text,
        start_time=offset(segment.start_time),
        end_time=offset(segment.end_time),
        confidence=segment.confidence,
        role_confidence=segment.role_confidence,
        role_source=segment.role_source,
        role_note=segment.role_note,
        speaker_turn=segment.speaker_turn,
        needs_review=True if not segment.role else segment.needs_review,
        reviewed_by_doctor=segment.reviewed_by_doctor,
        original_text=segment.original_text,
    )


def _append_partial_segment_events(
    session_id: str,
    *,
    session: ASRSessionRecord,
    chunk_index: int,
    total_chunks: int,
    chunk_start_seconds: float,
    chunk_result: ASRResult,
    start_index: int,
    mode: str = "chunked_long_audio",
) -> int:
    segments = _fallback_segments(chunk_result)
    events: list[ASRSessionEvent] = []
    progress = round(chunk_index / total_chunks, 4) if total_chunks else 1.0
    for offset, segment in enumerate(segments):
        adjusted = _offset_segment_for_chunk(segment, chunk_start_seconds)
        events.append(
            _session_event(
                session=session,
                event="segment",
                data={
                    "status": "streaming",
                    "partial": True,
                    "mode": mode,
                    "chunk_index": chunk_index,
                    "total_chunks": total_chunks,
                    "index": start_index + offset,
                    "total": start_index + len(segments),
                    "progress": progress,
                    "role": adjusted.role,
                    "speaker": adjusted.speaker,
                    "text": adjusted.text,
                    "segment": adjusted.model_dump(),
                },
            )
        )
    if events:
        _append_events(session_id, events)
    return len(segments)


def _failed_event(session: ASRSessionRecord, message: str) -> list[ASRSessionEvent]:
    hint = _retry_hint(session.engine)
    return [
        ASRSessionEvent(
            id=1,
            event="failed",
            data={
                "session_id": session.session_id,
                "audio_id": session.audio_id,
                "engine": session.engine,
                "status": "failed",
                "error": message,
                "retryable": True,
                "retry_hint": hint,
            },
            created_at=_now(),
        )
    ]


def _chunk_seconds() -> int:
    return _env_int("ASR_SESSION_CHUNK_SECONDS", 300)


def _short_chunk_seconds() -> int:
    return _env_int("ASR_SESSION_SHORT_CHUNK_SECONDS", SHORT_AUDIO_CHUNK_SECONDS)


def _chunk_min_seconds() -> int:
    return _env_int("ASR_SESSION_CHUNK_MIN_SECONDS", DEFAULT_CHUNK_MIN_SECONDS)


def _realtime_upload_enabled() -> bool:
    value = str(os.environ.get("ASR_SESSION_REALTIME_UPLOAD_ENABLED", "1")).strip().lower()
    return value not in {"0", "false", "no", "off"}


def _realtime_chunk_seconds() -> int:
    return _env_int("ASR_SESSION_REALTIME_CHUNK_SECONDS", DEFAULT_REALTIME_UPLOAD_CHUNK_SECONDS)


def _realtime_chunk_min_seconds() -> int:
    return _env_int("ASR_SESSION_REALTIME_CHUNK_MIN_SECONDS", 0)


def _realtime_max_seconds() -> float:
    return _env_float("ASR_SESSION_REALTIME_MAX_SECONDS", DEFAULT_REALTIME_UPLOAD_MAX_SECONDS)


def _realtime_mock_delay_seconds() -> float:
    return _env_float("ASR_SESSION_REALTIME_MOCK_DELAY_SECONDS", 0.0)


def _dynamic_chunking_enabled() -> bool:
    value = str(os.environ.get("ASR_SESSION_DYNAMIC_CHUNKING", "1")).strip().lower()
    return value not in {"0", "false", "no", "off"}


def _chunk_seconds_for_duration(duration: float | None) -> int:
    if not _dynamic_chunking_enabled() or duration is None:
        return _chunk_seconds()
    if duration < LONG_AUDIO_THRESHOLD_SECONDS:
        return _short_chunk_seconds()
    return _chunk_seconds()


def _env_int(name: str, default: int) -> int:
    try:
        value = int(str(os.environ.get(name, default)).strip())
    except ValueError:
        return default
    return value if value > 0 else default


def _env_float(name: str, default: float) -> float:
    try:
        value = float(str(os.environ.get(name, default)).strip())
    except ValueError:
        return default
    return value if value >= 0 else default


def _chunking_enabled() -> bool:
    value = str(os.environ.get("ASR_SESSION_CHUNK_ENABLED", "1")).strip().lower()
    return value not in {"0", "false", "no", "off"}


def _audio_duration_for_chunking(audio_path: Path) -> float | None:
    ffprobe = find_ffprobe_executable()
    if ffprobe is None:
        return None
    try:
        return probe_audio_duration(audio_path, ffprobe)
    except Exception:  # noqa: BLE001
        return None


def _should_use_chunked_session(engine_name: str, audio_path: Path) -> tuple[bool, float | None]:
    if not _chunking_enabled() or engine_name not in CHUNKABLE_ASR_ENGINES:
        return False, None
    duration = _audio_duration_for_chunking(audio_path)
    if duration is None:
        return False, None
    return duration >= _chunk_min_seconds(), duration


def _should_use_realtime_upload_session(
    engine_name: str,
    audio_path: Path,
    *,
    duration: float | None = None,
) -> tuple[bool, float | None]:
    if not _realtime_upload_enabled() or engine_name not in REALTIME_UPLOAD_ASR_ENGINES:
        return False, duration
    resolved_duration = duration if duration is not None else _audio_duration_for_chunking(audio_path)
    if engine_name == "funasr":
        return True, resolved_duration
    if resolved_duration is None:
        return engine_name == "mock", resolved_duration
    if resolved_duration < _realtime_chunk_min_seconds():
        return False, resolved_duration
    return resolved_duration <= _realtime_max_seconds(), resolved_duration


def _compact_error(exc: Exception) -> str:
    return str(exc).replace("\r", " ").replace("\n", " ")[:500]


def _retry_hint(engine_name: str) -> str:
    fallback = "FunASR" if engine_name == "sensevoice" else "SenseVoice 或 mock"
    return f"可重新上传重试；若同一切片再次失败，建议改用 {fallback} 或缩短 ASR_SESSION_CHUNK_SECONDS。"


def _sse_message(event: ASRSessionEvent) -> str:
    payload = json.dumps(event.data, ensure_ascii=False, default=str)
    return "\n".join(
        [
            f"id: {event.id}",
            f"event: {event.event}",
            f"data: {payload}",
            "",
        ]
    ) + "\n"


def _parse_last_event_id(last_event_id: str | None) -> int:
    if not last_event_id:
        return 0
    try:
        return int(last_event_id)
    except ValueError:
        return 0


async def _asr_session_event_stream(
    session_id: str,
    *,
    last_event_id: int = 0,
    delay_ms: int = 250,
):
    next_event_id = last_event_id
    sent_any = False
    keepalive_interval_seconds = 10.0
    last_output_at = time.monotonic()
    poll_seconds = max(min(delay_ms / 1000, 0.5), 0.05) if delay_ms > 0 else 0.0
    while True:
        events = [event for event in _read_events(session_id) if event.id > next_event_id]
        for event in events:
            sent_any = True
            next_event_id = event.id
            yield _sse_message(event)
            last_output_at = time.monotonic()
            if event.event in {"completed", "failed"}:
                return

        if events:
            continue

        session = _read_session(session_id)
        if session.status in {"stream_ready", "failed"}:
            if not sent_any:
                state = ASRSessionEvent(
                    id=next_event_id + 1,
                    event="state",
                    data={
                        "session_id": session.session_id,
                        "audio_id": session.audio_id,
                        "engine": session.engine,
                        "status": session.status,
                        "error": session.error,
                    },
                    created_at=_now(),
                )
                yield _sse_message(state)
            return

        if delay_ms <= 0:
            if not sent_any:
                state = ASRSessionEvent(
                    id=next_event_id + 1,
                    event="state",
                    data={
                        "session_id": session.session_id,
                        "audio_id": session.audio_id,
                        "engine": session.engine,
                        "status": session.status,
                    },
                    created_at=_now(),
                )
                yield _sse_message(state)
            return

        if time.monotonic() - last_output_at >= keepalive_interval_seconds:
            yield ": keepalive\n\n"
            last_output_at = time.monotonic()
        await asyncio.sleep(poll_seconds)


@router.post("")
def create_asr_session(
    engine: str = Query(default="mock"),
    doctor_profile_id: str | None = Query(default=None),
    diarization_engine: str = Query(default="auto"),
) -> ASRSessionRecord:
    normalized_engine = _normalize_engine_name(engine)
    if not isinstance(doctor_profile_id, str):
        doctor_profile_id = None
    normalized_diarization_engine = (
        diarization_engine.strip().lower()
        if isinstance(diarization_engine, str)
        else "auto"
    )
    if normalized_diarization_engine not in SUPPORTED_DIARIZATION_ENGINES:
        raise HTTPException(
            status_code=400,
            detail="Unsupported diarization engine. Expected auto, funasr_campp, pyannote, or three_d_speaker.",
        )
    session_id = uuid.uuid4().hex
    now = _now()
    session = ASRSessionRecord(
        session_id=session_id,
        engine=normalized_engine,
        status="created",
        events_url=f"/api/asr/sessions/{session_id}/events",
        result_url=f"/api/asr/sessions/{session_id}/result",
        doctor_profile_id=doctor_profile_id,
        diarization_engine=normalized_diarization_engine,
        created_at=now,
        updated_at=now,
    )
    _write_session(session)
    return session


@router.get("/{session_id}")
def read_asr_session(session_id: str) -> ASRSessionRecord:
    return _read_session(session_id)


def _run_asr_session_transcription(
    session_id: str,
    *,
    record: AudioRecord,
    audio_path: Path,
    pace_realtime: bool = False,
) -> None:
    session = _read_session(session_id)
    stop_heartbeat, heartbeat_thread, started_at = _start_transcribing_heartbeat(
        session_id,
        session=session,
        duration=None,
    )
    try:
        use_chunked, original_duration = _should_use_chunked_session(session.engine, audio_path)
        use_realtime, realtime_duration = _should_use_realtime_upload_session(
            session.engine,
            audio_path,
            duration=original_duration,
        )
        if use_realtime and session.engine == "funasr":
            stop_heartbeat.set()
            heartbeat_thread.join(timeout=1.0)
            result = _transcribe_funasr_streaming_session(
                session_id,
                session=session,
                record=record,
                audio_path=audio_path,
                original_duration=realtime_duration,
            )
            emit_segments = False
        elif use_realtime:
            stop_heartbeat.set()
            heartbeat_thread.join(timeout=1.0)
            asr_engine = create_asr_engine(session.engine)
            result = _transcribe_realtime_upload_session(
                session_id,
                session=session,
                engine=asr_engine,
                record=record,
                audio_path=audio_path,
                original_duration=realtime_duration,
                pace_realtime=pace_realtime,
            )
            emit_segments = False
        elif use_chunked:
            stop_heartbeat.set()
            heartbeat_thread.join(timeout=1.0)
            asr_engine = create_asr_engine(session.engine)
            result = _transcribe_chunked_session(
                session_id,
                session=session,
                engine=asr_engine,
                record=record,
                audio_path=audio_path,
                original_duration=original_duration,
            )
            emit_segments = False
        else:
            asr_engine = create_asr_engine(session.engine)
            result = asr_engine.transcribe(record.audio_id, audio_path)
            result = apply_manifest_role_strategy(result, _sample_id_from_record(record))
            result = enhance_speaker_diarization(result)
            _append_transcribing_progress_event(
                session_id,
                session=session,
                started_at=started_at,
                duration=original_duration,
            )
            emit_segments = True
        _write_transcription_success(session_id, session=session, result=result, emit_segments=emit_segments)
    except Exception as exc:  # noqa: BLE001
        message = _compact_error(exc)
        failed = session.model_copy(
            update={
                "status": "failed",
                "error": message,
                "updated_at": _now(),
            }
        )
        _write_session(failed)
        _append_events(session_id, _failed_event(failed, message))
    finally:
        stop_heartbeat.set()
        heartbeat_thread.join(timeout=1.0)


def _transcribe_funasr_streaming_session(
    session_id: str,
    *,
    session: ASRSessionRecord,
    record: AudioRecord,
    audio_path: Path,
    original_duration: float | None,
) -> ASRResult:
    _append_session_event(
        session_id,
        session=session,
        event="transcribing_progress",
        data={
            "status": "transcribing",
            "phase": "model_loading",
            "progress": None,
            "progress_kind": "indeterminate",
            "processed_audio_seconds": 0.0,
            "audio_duration_seconds": original_duration,
            "elapsed_seconds": 0.0,
        },
    )

    try:
        engine = _create_funasr_streaming_engine()
    except Exception as exc:  # noqa: BLE001
        return _fallback_from_streaming_failure(
            session_id,
            session=session,
            record=record,
            audio_path=audio_path,
            original_duration=original_duration,
            error=exc,
        )

    _append_session_event(
        session_id,
        session=session,
        event="transcribing_progress",
        data={
            "status": "transcribing",
            "phase": "model_ready",
            "progress": 0.0 if original_duration else None,
            "progress_kind": "actual" if original_duration else "indeterminate",
            "processed_audio_seconds": 0.0,
            "audio_duration_seconds": original_duration,
            "model_load_time_seconds": engine.model_load_time_seconds,
            "elapsed_seconds": 0.0,
        },
    )

    last_progress_audio_seconds = -STREAMING_PROGRESS_EVENT_INTERVAL_SECONDS
    last_progress_elapsed_seconds = -STREAMING_PROGRESS_WALL_INTERVAL_SECONDS
    last_progress_phase = ""

    def on_progress(data: dict[str, object]) -> None:
        nonlocal last_progress_audio_seconds, last_progress_elapsed_seconds, last_progress_phase
        processed = float(data.get("processed_audio_seconds") or 0.0)
        elapsed = float(data.get("elapsed_seconds") or 0.0)
        phase = str(data.get("phase") or "streaming")
        progress = data.get("progress")
        should_emit = (
            phase != last_progress_phase
            or (
                processed - last_progress_audio_seconds >= STREAMING_PROGRESS_EVENT_INTERVAL_SECONDS
                and elapsed - last_progress_elapsed_seconds >= STREAMING_PROGRESS_WALL_INTERVAL_SECONDS
            )
            or progress == 1.0
        )
        if not should_emit:
            return
        last_progress_audio_seconds = processed
        last_progress_elapsed_seconds = elapsed
        last_progress_phase = phase
        _append_session_event(
            session_id,
            session=session,
            event="transcribing_progress",
            data={"status": "transcribing", **data},
        )

    def on_segment(event_name: str, segment: ASRSegment, metadata: dict[str, object]) -> None:
        duration = metadata.get("audio_duration_seconds") or original_duration
        processed = metadata.get("processed_audio_seconds")
        progress = (
            round(float(processed) / float(duration), 4)
            if processed is not None and duration
            else None
        )
        _append_session_event(
            session_id,
            session=session,
            event=event_name,
            data={
                "status": "streaming",
                "partial": segment.provisional,
                "mode": "model_native_streaming",
                "segment_id": segment.segment_id,
                "revision": segment.revision,
                "progress": progress,
                "progress_kind": "actual" if progress is not None else "indeterminate",
                "processed_audio_seconds": processed,
                "audio_duration_seconds": duration,
                "role": segment.role,
                "speaker": segment.speaker,
                "text": segment.text,
                "segment": segment.model_dump(),
            },
        )

    try:
        result = engine.transcribe_streaming(
            record.audio_id,
            audio_path,
            on_progress=on_progress,
            on_segment=on_segment,
        )
    except Exception as exc:  # noqa: BLE001
        return _fallback_from_streaming_failure(
            session_id,
            session=session,
            record=record,
            audio_path=audio_path,
            original_duration=original_duration,
            error=exc,
        )

    del engine
    gc.collect()
    return _reconcile_streaming_result(
        session_id,
        session=session,
        record=record,
        audio_path=audio_path,
        streaming_result=result,
    )


def _reconcile_streaming_result(
    session_id: str,
    *,
    session: ASRSessionRecord,
    record: AudioRecord,
    audio_path: Path,
    streaming_result: ASRResult,
) -> ASRResult:
    _append_session_event(
        session_id,
        session=session,
        event="diarization_progress",
        data={
            "status": "reconciling",
            "phase": "speaker_calibration",
            "progress": None,
            "progress_kind": "indeterminate",
            "message": "正在校准标点、时间戳和说话人",
        },
    )
    try:
        calibration_engine = _create_funasr_reconciliation_engine()
        calibrated = calibration_engine.transcribe(record.audio_id, audio_path)
        calibrated = apply_manifest_role_strategy(calibrated, _sample_id_from_record(record))
        calibrated = enhance_speaker_diarization(calibrated)
        calibrated = resolve_speaker_roles(
            calibrated,
            audio_path=audio_path,
            doctor_profile_id=session.doctor_profile_id,
        )
        calibrated.segments = [
            segment.model_copy(
                update={
                    "segment_id": segment.segment_id or f"{record.audio_id}-cal-{index:04d}",
                    "revision": max(segment.revision, 1),
                    "provisional": False,
                    "speaker_id": segment.speaker_id or segment.speaker,
                }
            )
            for index, segment in enumerate(calibrated.segments, start=1)
        ]
        calibrated.text = _plain_text_from_segments(calibrated.segments)
        calibrated.conversation_text = _conversation_from_segments(calibrated.segments)
        calibrated = attach_speaker_role_quality(calibrated)
        diarization_events = [
            ASRSessionEvent(
                id=1,
                event="speaker_turn",
                data={
                    "status": "stable",
                    "segment": segment.model_dump(),
                    "speaker_id": segment.speaker_id,
                    "role": segment.role,
                    "start_time": segment.start_time,
                    "end_time": segment.end_time,
                    "overlap": segment.overlap,
                },
                created_at=_now(),
            )
            for segment in calibrated.segments
        ]
        mapping_event_name = (
            "speaker_mapping_required"
            if any(item.requires_confirmation for item in calibrated.speaker_assignments)
            else "speaker_mapping_update"
        )
        diarization_events.extend(
            [
                ASRSessionEvent(
                    id=1,
                    event=mapping_event_name,
                    data={
                        "status": "mapping_required" if mapping_event_name.endswith("required") else "mapped",
                        "assignments": [item.model_dump() for item in calibrated.speaker_assignments],
                    },
                    created_at=_now(),
                ),
                ASRSessionEvent(
                    id=1,
                    event="diarization_completed",
                    data={
                        "status": "completed",
                        "engine": "funasr_campp",
                        "requested_engine": session.diarization_engine,
                        "speaker_count": len(calibrated.speaker_assignments),
                        "turn_count": len(calibrated.diarization_turns),
                        "assignments": [item.model_dump() for item in calibrated.speaker_assignments],
                    },
                    created_at=_now(),
                ),
            ]
        )
        _append_events(session_id, diarization_events)
        _append_session_event(
            session_id,
            session=session,
            event="diarization_progress",
            data={
                "status": "completed",
                "phase": "speaker_calibration_completed",
                "progress": 1.0,
                "progress_kind": "actual",
                "speaker_count": len(
                    {
                        segment.speaker_id
                        for segment in calibrated.segments
                        if segment.speaker_id
                    }
                ),
            },
        )
        _append_session_event(
            session_id,
            session=session,
            event="reconciliation_completed",
            data={
                "status": "completed",
                "phase": "reconciliation_completed",
                "segments": len(calibrated.segments),
                "asr_result": calibrated.model_dump(),
            },
        )
        return calibrated
    except Exception as exc:  # noqa: BLE001
        # Streaming windows are not speaker turns. Keep them provisional when
        # calibration fails so they cannot enter structured medical previews.
        fallback = streaming_result.model_copy(deep=True)
        fallback.needs_review = True
        warning = (
            "Speaker calibration was unavailable; streaming transcript was retained for manual review. "
            f"Reason: {_compact_error(exc)}"
        )
        if warning not in fallback.warnings:
            fallback.warnings.append(warning)
        _append_session_event(
            session_id,
            session=session,
            event="diarization_progress",
            data={
                "status": "failed",
                "phase": "speaker_calibration_failed",
                "progress": None,
                "progress_kind": "indeterminate",
                "message": "说话人校准暂不可用，已保留转写结果供人工校正",
                "error": _compact_error(exc),
                "retryable": True,
            },
        )
        return fallback


def _fallback_from_streaming_failure(
    session_id: str,
    *,
    session: ASRSessionRecord,
    record: AudioRecord,
    audio_path: Path,
    original_duration: float | None,
    error: Exception,
) -> ASRResult:
    _append_session_event(
        session_id,
        session=session,
        event="transcribing_progress",
        data={
            "status": "transcribing",
            "phase": "streaming_fallback",
            "progress": None,
            "progress_kind": "indeterminate",
            "processed_audio_seconds": None,
            "audio_duration_seconds": original_duration,
            "error": _compact_error(error),
            "retryable": True,
        },
    )
    offline_engine = create_asr_engine("funasr")
    return _transcribe_chunked_session(
        session_id,
        session=session,
        engine=offline_engine,
        record=record,
        audio_path=audio_path,
        original_duration=original_duration,
        chunk_seconds=_short_chunk_seconds(),
        mode="streaming_fallback",
        engine_suffix="fallback",
    )


def _transcribe_chunked_session(
    session_id: str,
    *,
    session: ASRSessionRecord,
    engine: Any,
    record: AudioRecord,
    audio_path: Path,
    original_duration: float | None,
    chunk_seconds: int | None = None,
    mode: str = "chunked_long_audio",
    engine_suffix: str = "chunked",
) -> ASRResult:
    chunk_seconds = chunk_seconds or _chunk_seconds_for_duration(original_duration)
    with tempfile.TemporaryDirectory(prefix=f"{record.audio_id}_chunks_") as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        chunks = split_audio_to_chunks(audio_path, temp_dir, chunk_seconds=chunk_seconds)
        total_chunks = len(chunks)
        _append_session_event(
            session_id,
            session=session,
            event="chunk_plan",
            data={
                "status": "chunk_plan",
                "mode": mode,
                "chunk_seconds": chunk_seconds,
                "chunk_count": total_chunks,
                "total_chunks": total_chunks,
                "duration": original_duration,
                "progress": 0,
            },
        )

        transcriptions: list[ChunkTranscription] = []
        emitted_segments = 0
        for chunk in chunks:
            started_at = time.perf_counter()
            common = {
                "chunk_index": chunk.index,
                "total_chunks": total_chunks,
                "chunk_start_seconds": chunk.start_seconds,
                "chunk_duration_seconds": chunk.duration_seconds,
                "mode": mode,
            }
            _append_session_event(
                session_id,
                session=session,
                event="chunk_started",
                data={
                    **common,
                    "status": "chunk_transcribing",
                    "progress": round((chunk.index - 1) / total_chunks, 4) if total_chunks else 0,
                    "retryable": False,
                },
            )
            try:
                chunk_result = engine.transcribe(f"{record.audio_id}_chunk_{chunk.index:03d}", chunk.path)
                chunk_result = enhance_speaker_diarization(chunk_result)
            except Exception as exc:  # noqa: BLE001
                error = _compact_error(exc)
                _append_session_event(
                    session_id,
                    session=session,
                    event="chunk_failed",
                    data={
                        **common,
                        "status": "chunk_failed",
                        "progress": round((chunk.index - 1) / total_chunks, 4) if total_chunks else 0,
                        "error": error,
                        "retryable": True,
                        "retry_hint": _retry_hint(session.engine),
                        "elapsed_seconds": round(time.perf_counter() - started_at, 3),
                    },
                )
                raise RuntimeError(f"ASR chunk {chunk.index}/{total_chunks} failed: {error}") from exc

            transcriptions.append(ChunkTranscription(chunk=chunk, result=chunk_result))
            _append_session_event(
                session_id,
                session=session,
                event="chunk_completed",
                data={
                    **common,
                    "status": "chunk_completed",
                    "progress": round(chunk.index / total_chunks, 4) if total_chunks else 1,
                    "segments": len(chunk_result.segments),
                    "text_length": len(chunk_result.text),
                    "elapsed_seconds": round(time.perf_counter() - started_at, 3),
                },
            )
            emitted_segments += _append_partial_segment_events(
                session_id,
                session=session,
                chunk_index=chunk.index,
                total_chunks=total_chunks,
                chunk_start_seconds=chunk.start_seconds,
                chunk_result=chunk_result,
                start_index=emitted_segments,
                mode=mode,
            )

        merged = merge_chunk_transcriptions(
            record.audio_id,
            transcriptions,
            original_duration=original_duration,
            engine_name=f"{getattr(engine, 'name', session.engine)}-{engine_suffix}",
        )
        if mode == "realtime_upload":
            merged.warnings = [
                warning for warning in merged.warnings if warning != CHUNKED_LONG_AUDIO_WARNING
            ]
            if REALTIME_UPLOAD_WARNING not in merged.warnings:
                merged.warnings.insert(0, REALTIME_UPLOAD_WARNING)
        merged = apply_manifest_role_strategy(merged, _sample_id_from_record(record))
        return enhance_speaker_diarization(merged)


def _transcribe_realtime_upload_session(
    session_id: str,
    *,
    session: ASRSessionRecord,
    engine: Any,
    record: AudioRecord,
    audio_path: Path,
    original_duration: float | None,
    pace_realtime: bool = False,
) -> ASRResult:
    chunk_seconds = _realtime_chunk_seconds()
    if session.engine == "mock":
        return _transcribe_mock_realtime_upload_session(
            session_id,
            session=session,
            engine=engine,
            record=record,
            audio_path=audio_path,
            chunk_seconds=chunk_seconds,
            pace_realtime=pace_realtime,
        )
    return _transcribe_chunked_session(
        session_id,
        session=session,
        engine=engine,
        record=record,
        audio_path=audio_path,
        original_duration=original_duration,
        chunk_seconds=chunk_seconds,
        mode="realtime_upload",
        engine_suffix="realtime",
    )


def _relative_segment_for_chunk(
    segment: ASRSegment,
    chunk_start_seconds: float,
) -> ASRSegment:
    def relative(value: float | None) -> float | None:
        if value is None:
            return None
        return round(max(float(value) - float(chunk_start_seconds), 0.0), 3)

    return segment.model_copy(
        update={
            "start_time": relative(segment.start_time),
            "end_time": relative(segment.end_time),
        }
    )


def _segment_emit_time(segment: ASRSegment) -> float:
    if segment.end_time is not None:
        return float(segment.end_time)
    if segment.start_time is not None:
        return float(segment.start_time)
    return 0.0


def _segments_for_realtime_chunk(
    segments: list[ASRSegment],
    *,
    chunk_start_seconds: float,
    chunk_duration_seconds: float,
) -> list[ASRSegment]:
    chunk_end_seconds = chunk_start_seconds + chunk_duration_seconds
    selected: list[ASRSegment] = []
    for segment in segments:
        emit_time = _segment_emit_time(segment)
        if chunk_start_seconds < emit_time <= chunk_end_seconds or (
            chunk_start_seconds == 0 and emit_time == 0
        ):
            selected.append(_relative_segment_for_chunk(segment, chunk_start_seconds))
    return selected


def _maybe_sleep_mock_realtime(pace_realtime: bool) -> None:
    if not pace_realtime:
        return
    delay_seconds = _realtime_mock_delay_seconds()
    if delay_seconds > 0:
        time.sleep(delay_seconds)


def _transcribe_mock_realtime_upload_session(
    session_id: str,
    *,
    session: ASRSessionRecord,
    engine: Any,
    record: AudioRecord,
    audio_path: Path,
    chunk_seconds: int,
    pace_realtime: bool = False,
) -> ASRResult:
    result = engine.transcribe(record.audio_id, audio_path)
    duration = result.duration or _infer_result_duration(result)
    chunks = [
        (index, start_seconds, duration_seconds)
        for index, (start_seconds, duration_seconds) in enumerate(
            build_chunk_plan(duration, chunk_seconds),
            start=1,
        )
    ]
    total_chunks = len(chunks)
    _append_session_event(
        session_id,
        session=session,
        event="chunk_plan",
        data={
            "status": "chunk_plan",
            "mode": "realtime_upload",
            "chunk_seconds": chunk_seconds,
            "chunk_count": total_chunks,
            "total_chunks": total_chunks,
            "duration": duration,
            "progress": 0,
        },
    )

    transcriptions: list[ChunkTranscription] = []
    emitted_segments = 0
    for index, start_seconds, duration_seconds in chunks:
        started_at = time.perf_counter()
        common = {
            "chunk_index": index,
            "total_chunks": total_chunks,
            "chunk_start_seconds": start_seconds,
            "chunk_duration_seconds": duration_seconds,
            "mode": "realtime_upload",
        }
        _append_session_event(
            session_id,
            session=session,
            event="chunk_started",
            data={
                **common,
                "status": "chunk_transcribing",
                "progress": round((index - 1) / total_chunks, 4) if total_chunks else 0,
                "retryable": False,
            },
        )
        chunk_segments = _segments_for_realtime_chunk(
            result.segments,
            chunk_start_seconds=start_seconds,
            chunk_duration_seconds=duration_seconds,
        )
        chunk_result = ASRResult(
            audio_id=f"{record.audio_id}_chunk_{index:03d}",
            engine=result.engine,
            text="\n".join(segment.text for segment in chunk_segments if segment.text.strip()),
            conversation_text=_conversation_from_segments(chunk_segments),
            segments=chunk_segments,
            duration=duration_seconds,
            medical_keywords=result.medical_keywords,
        )
        transcriptions.append(
            ChunkTranscription(
                chunk=AudioChunk(
                    index=index,
                    path=audio_path,
                    start_seconds=start_seconds,
                    duration_seconds=duration_seconds,
                ),
                result=chunk_result,
            )
        )
        _append_session_event(
            session_id,
            session=session,
            event="chunk_completed",
            data={
                **common,
                "status": "chunk_completed",
                "progress": round(index / total_chunks, 4) if total_chunks else 1,
                "segments": len(chunk_segments),
                "text_length": len(chunk_result.text),
                "elapsed_seconds": round(time.perf_counter() - started_at, 3),
            },
        )
        emitted_segments += _append_partial_segment_events(
            session_id,
            session=session,
            chunk_index=index,
            total_chunks=total_chunks,
            chunk_start_seconds=start_seconds,
            chunk_result=chunk_result,
            start_index=emitted_segments,
            mode="realtime_upload",
        )
        if chunk_segments and index < total_chunks:
            _maybe_sleep_mock_realtime(pace_realtime)

    merged = merge_chunk_transcriptions(
        record.audio_id,
        transcriptions,
        original_duration=duration,
        engine_name=f"{result.engine}-realtime",
    )
    merged.medical_keywords = result.medical_keywords
    merged.warnings = [warning for warning in merged.warnings if warning != CHUNKED_LONG_AUDIO_WARNING]
    if REALTIME_UPLOAD_WARNING not in merged.warnings:
        merged.warnings.insert(0, REALTIME_UPLOAD_WARNING)
    return enhance_speaker_diarization(apply_manifest_role_strategy(merged, _sample_id_from_record(record)))


def _infer_result_duration(result: ASRResult) -> float:
    end_times = [segment.end_time for segment in result.segments if segment.end_time is not None]
    if end_times:
        return max(float(end_time) for end_time in end_times)
    return float(_realtime_chunk_seconds())


def _write_transcription_success(
    session_id: str,
    *,
    session: ASRSessionRecord,
    result: ASRResult,
    emit_segments: bool = True,
) -> None:
    result = attach_speaker_role_quality(result)
    _write_transcript(result)
    _write_session_result(session_id, result)
    ready_session = session.model_copy(
        update={
            "status": "stream_ready",
            "updated_at": _now(),
        }
    )
    _write_session(ready_session)
    _append_result_events(session_id, session=ready_session, result=result, emit_segments=emit_segments)


def upload_asr_session_audio(
    session_id: str,
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks | None = None,
) -> ASRSessionUploadResponse:
    session = _read_session(session_id)
    extension = _safe_extension(file.filename or "")
    upload_dir = get_upload_dir()
    upload_dir.mkdir(parents=True, exist_ok=True)

    audio_id = uuid.uuid4().hex
    destination = upload_dir / f"{audio_id}{extension}"
    with destination.open("wb") as output:
        shutil.copyfileobj(file.file, output)

    record = AudioRecord(
        audio_id=audio_id,
        filename=file.filename or destination.name,
        path=str(destination),
        status="uploaded",
        content_type=getattr(file, "content_type", None),
        size_bytes=destination.stat().st_size,
        created_at=_now(),
    )
    _write_audio_record(record)

    transcribing_session = session.model_copy(
        update={
            "status": "transcribing",
            "audio_id": audio_id,
            "filename": record.filename,
            "updated_at": _now(),
        }
    )
    _write_session(transcribing_session)
    _write_events(session_id, _initial_asr_stream_events(transcribing_session))

    if background_tasks is None:
        _run_asr_session_transcription(session_id, record=record, audio_path=destination)
        current_session = _read_session(session_id)
        result_path = _result_path(session_id)
        response_engine = (
            ASRResult.model_validate_json(result_path.read_text(encoding="utf-8")).engine
            if result_path.exists()
            else current_session.engine
        )
    else:
        background_tasks.add_task(
            _run_asr_session_transcription,
            session_id,
            record=record,
            audio_path=destination,
            pace_realtime=True,
        )
        current_session = transcribing_session
        response_engine = transcribing_session.engine

    return ASRSessionUploadResponse(
        session_id=session_id,
        audio_id=audio_id,
        status=current_session.status,
        filename=record.filename,
        engine=response_engine,
        events_url=current_session.events_url or f"/api/asr/sessions/{session_id}/events",
        result_url=current_session.result_url or f"/api/asr/sessions/{session_id}/result",
        media_url=f"/api/audio/{audio_id}/media",
        duration_seconds=_audio_duration_for_chunking(destination),
    )


@router.post("/{session_id}/audio")
def upload_asr_session_audio_route(
    session_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
) -> ASRSessionUploadResponse:
    return upload_asr_session_audio(session_id, file, background_tasks=background_tasks)


@router.patch("/{session_id}/result")
def update_asr_session_result(
    session_id: str,
    payload: ASRSessionCorrectionRequest,
) -> ASRSessionCorrectionResponse:
    session = _read_session(session_id)
    path = _result_path(session_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="ASR session result not found")

    result = ASRResult.model_validate_json(path.read_text(encoding="utf-8"))
    updated_result = _apply_segment_corrections(result, payload)
    updated_at = _now()
    reviewed_session = session.model_copy(update={"status": "reviewed", "updated_at": updated_at})

    _write_session_result(session_id, updated_result)
    _write_transcript(updated_result)
    _write_session(reviewed_session)
    _append_events(
        session_id,
        [
            _reviewed_event(
                session=reviewed_session,
                result=updated_result,
                reviewer=payload.reviewer,
                note=payload.note,
            )
        ],
    )
    return ASRSessionCorrectionResponse(
        session_id=session_id,
        audio_id=updated_result.audio_id,
        status="reviewed",
        asr_result=updated_result,
        updated_at=updated_at,
    )


@router.post("/{session_id}/speakers/merge")
def merge_asr_session_speakers(
    session_id: str,
    payload: ASRSpeakerMergeRequest,
) -> ASRSpeakerMergeResponse:
    session = _read_session(session_id)
    path = _result_path(session_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="ASR session result not found")

    result = ASRResult.model_validate_json(path.read_text(encoding="utf-8"))
    merged_result, affected_segment_ids, speaker_count_before, speaker_count_after = _merge_speakers_in_result(
        result,
        source_speaker=payload.source_speaker,
        target_speaker=payload.target_speaker,
    )
    updated_at = _now()
    updated_session = session.model_copy(update={"updated_at": updated_at})

    _write_session_result(session_id, merged_result)
    _write_transcript(merged_result)
    _write_session(updated_session)
    _append_events(
        session_id,
        [
            _session_event(
                session=updated_session,
                event="speakers_merged",
                data={
                    "status": "speakers_merged",
                    "audio_id": merged_result.audio_id,
                    "source_speaker": payload.source_speaker,
                    "target_speaker": payload.target_speaker,
                    "speaker_count_before": speaker_count_before,
                    "speaker_count_after": speaker_count_after,
                    "affected_segment_ids": affected_segment_ids,
                    "reviewer": payload.reviewer,
                    "note": payload.note,
                    "role_quality": merged_result.role_quality.model_dump(mode="json")
                    if merged_result.role_quality
                    else None,
                    "asr_result": merged_result.model_dump(),
                },
            )
        ],
    )
    return ASRSpeakerMergeResponse(
        session_id=session_id,
        audio_id=merged_result.audio_id,
        speaker_count_before=speaker_count_before,
        speaker_count_after=speaker_count_after,
        affected_segment_ids=affected_segment_ids,
        role_quality=merged_result.role_quality,
        asr_result=merged_result,
        updated_at=updated_at,
    )


@router.get("/{session_id}/events")
def read_asr_session_events(
    session_id: str,
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    delay_ms: int = Query(default=100, ge=0, le=5000),
) -> StreamingResponse:
    _read_session(session_id)
    return StreamingResponse(
        _asr_session_event_stream(
            session_id,
            last_event_id=_parse_last_event_id(last_event_id),
            delay_ms=delay_ms,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{session_id}/result")
def read_asr_session_result(session_id: str) -> ASRResult:
    _read_session(session_id)
    path = _result_path(session_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="ASR session result not found")
    return ASRResult.model_validate_json(path.read_text(encoding="utf-8"))
