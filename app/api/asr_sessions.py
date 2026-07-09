from __future__ import annotations

import asyncio
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
    AudioRecord,
)
from app.services.asr import (
    ChunkTranscription,
    apply_manifest_role_strategy,
    create_asr_engine,
    merge_chunk_transcriptions,
    split_audio_to_chunks,
)
from app.services.asr.chunking import probe_audio_duration
from app.services.asr.ffmpeg_utils import find_ffprobe_executable


router = APIRouter(prefix="/asr/sessions", tags=["asr-sessions"])

SUPPORTED_ASR_ENGINES = {"mock", "funasr", "sensevoice", "whisper", "qwen3", "online"}
CHUNKABLE_ASR_ENGINES = {"funasr", "sensevoice"}
TRANSCRIBING_PROGRESS_INTERVAL_SECONDS = 5.0
TRANSCRIBING_PROGRESS_CAP = 0.88
SHORT_AUDIO_CHUNK_SECONDS = 60
LONG_AUDIO_THRESHOLD_SECONDS = 600
DEFAULT_CHUNK_MIN_SECONDS = 120
ROLE_LABELS = {
    "doctor": "医生",
    "医生": "医生",
    "patient": "患者",
    "患者": "患者",
    "unknown": "待确认",
    "待确认": "待确认",
    "待校正": "待确认",
}

_EVENTS_LOCK = threading.Lock()


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


def _write_session(session: ASRSessionRecord) -> None:
    _write_json(_session_path(session.session_id), session.model_dump())


def _read_session(session_id: str) -> ASRSessionRecord:
    path = _session_path(session_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="ASR session not found")
    return ASRSessionRecord.model_validate_json(path.read_text(encoding="utf-8"))


def _write_events(session_id: str, events: list[ASRSessionEvent]) -> None:
    _write_json(_events_path(session_id), [event.model_dump() for event in events])


def _append_events(session_id: str, events: list[ASRSessionEvent]) -> None:
    with _EVENTS_LOCK:
        existing = _read_events(session_id)
        last_id = existing[-1].id if existing else 0
        next_events = [
            event.model_copy(update={"id": last_id + index + 1})
            for index, event in enumerate(events)
        ]
        _write_events(session_id, [*existing, *next_events])


def _read_events(session_id: str) -> list[ASRSessionEvent]:
    path = _events_path(session_id)
    if not path.exists():
        return []
    raw_events = json.loads(path.read_text(encoding="utf-8"))
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

    updated.text = _plain_text_from_segments(updated.segments)
    updated.conversation_text = _conversation_from_segments(updated.segments)
    updated.role_strategy = "manual_reviewed"
    updated.reviewed_by_doctor = all(segment.reviewed_by_doctor for segment in updated.segments)
    updated.needs_review = any(segment.needs_review for segment in updated.segments)
    if updated.reviewed_by_doctor and "ASR segments were manually reviewed by doctor." not in updated.warnings:
        updated.warnings.append("ASR segments were manually reviewed by doctor.")
    return updated


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
            "progress": _estimated_transcribing_progress(started_at, duration),
            "elapsed_seconds": elapsed,
            "duration": duration,
            "estimated": True,
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
        speaker=segment.speaker,
        role=segment.role,
        text=segment.text,
        start_time=offset(segment.start_time),
        end_time=offset(segment.end_time),
        confidence=segment.confidence,
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
    while True:
        events = [event for event in _read_events(session_id) if event.id > next_event_id]
        for event in events:
            sent_any = True
            next_event_id = event.id
            yield _sse_message(event)
            if event.event in {"completed", "failed"}:
                return
            if delay_ms > 0:
                await asyncio.sleep(delay_ms / 1000)

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

        await asyncio.sleep(delay_ms / 1000)


@router.post("")
def create_asr_session(
    engine: str = Query(default="mock"),
) -> ASRSessionRecord:
    normalized_engine = _normalize_engine_name(engine)
    session_id = uuid.uuid4().hex
    now = _now()
    session = ASRSessionRecord(
        session_id=session_id,
        engine=normalized_engine,
        status="created",
        events_url=f"/api/asr/sessions/{session_id}/events",
        result_url=f"/api/asr/sessions/{session_id}/result",
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
) -> None:
    session = _read_session(session_id)
    stop_heartbeat, heartbeat_thread, started_at = _start_transcribing_heartbeat(
        session_id,
        session=session,
        duration=None,
    )
    try:
        asr_engine = create_asr_engine(session.engine)
        use_chunked, original_duration = _should_use_chunked_session(session.engine, audio_path)
        if use_chunked:
            stop_heartbeat.set()
            heartbeat_thread.join(timeout=1.0)
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
            result = asr_engine.transcribe(record.audio_id, audio_path)
            result = apply_manifest_role_strategy(result, _sample_id_from_record(record))
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


def _transcribe_chunked_session(
    session_id: str,
    *,
    session: ASRSessionRecord,
    engine: Any,
    record: AudioRecord,
    audio_path: Path,
    original_duration: float | None,
) -> ASRResult:
    chunk_seconds = _chunk_seconds_for_duration(original_duration)
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
            )

        merged = merge_chunk_transcriptions(
            record.audio_id,
            transcriptions,
            original_duration=original_duration,
            engine_name=f"{getattr(engine, 'name', session.engine)}-chunked",
        )
        return apply_manifest_role_strategy(merged, _sample_id_from_record(record))


def _write_transcription_success(
    session_id: str,
    *,
    session: ASRSessionRecord,
    result: ASRResult,
    emit_segments: bool = True,
) -> None:
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


@router.get("/{session_id}/events")
def read_asr_session_events(
    session_id: str,
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    delay_ms: int = Query(default=250, ge=0, le=5000),
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
