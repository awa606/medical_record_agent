from __future__ import annotations

import asyncio
import json
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Header, HTTPException, Query, UploadFile
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
from app.services.asr import apply_manifest_role_strategy, create_asr_engine


router = APIRouter(prefix="/asr/sessions", tags=["asr-sessions"])

SUPPORTED_ASR_ENGINES = {"mock", "funasr", "sensevoice", "whisper", "qwen3", "online"}
ROLE_LABELS = {
    "doctor": "医生",
    "医生": "医生",
    "patient": "患者",
    "患者": "患者",
    "unknown": "待确认",
    "待确认": "待确认",
    "待校正": "待确认",
}


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
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


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


def _build_asr_stream_events(
    *,
    session: ASRSessionRecord,
    result: ASRResult,
    filename: str,
) -> list[ASRSessionEvent]:
    timestamp = _now()
    events: list[ASRSessionEvent] = []

    def append(event: str, data: dict[str, object]) -> None:
        events.append(
            ASRSessionEvent(
                id=len(events) + 1,
                event=event,
                data={
                    "session_id": session.session_id,
                    "audio_id": result.audio_id,
                    "engine": result.engine,
                    **data,
                },
                created_at=timestamp,
            )
        )

    append("session_created", {"status": "created"})
    append("audio_uploaded", {"status": "uploaded", "filename": filename})
    append("transcribing", {"status": "transcribing"})

    segments = _fallback_segments(result)
    total = len(segments)
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
    return events


def _failed_event(session: ASRSessionRecord, message: str) -> list[ASRSessionEvent]:
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
            },
            created_at=_now(),
        )
    ]


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
    events = [event for event in _read_events(session_id) if event.id > last_event_id]
    if not events:
        session = _read_session(session_id)
        events = [
            ASRSessionEvent(
                id=last_event_id + 1,
                event="state",
                data={
                    "session_id": session.session_id,
                    "audio_id": session.audio_id,
                    "engine": session.engine,
                    "status": session.status,
                },
                created_at=_now(),
            )
        ]

    for event in events:
        yield _sse_message(event)
        if delay_ms > 0 and event.event not in {"completed", "failed"}:
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


@router.post("/{session_id}/audio")
def upload_asr_session_audio(
    session_id: str,
    file: UploadFile = File(...),
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

    try:
        asr_engine = create_asr_engine(session.engine)
        result = asr_engine.transcribe(audio_id, destination)
        result = apply_manifest_role_strategy(result, _sample_id_from_record(record))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        failed = session.model_copy(
            update={
                "status": "failed",
                "audio_id": audio_id,
                "filename": record.filename,
                "error": str(exc),
                "updated_at": _now(),
            }
        )
        _write_session(failed)
        _write_events(session_id, _failed_event(failed, str(exc)))
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    _write_transcript(result)
    _write_session_result(session_id, result)
    ready_session = session.model_copy(
        update={
            "status": "stream_ready",
            "audio_id": audio_id,
            "filename": record.filename,
            "updated_at": _now(),
        }
    )
    _write_session(ready_session)
    _write_events(
        session_id,
        _build_asr_stream_events(
            session=ready_session,
            result=result,
            filename=record.filename,
        ),
    )
    return ASRSessionUploadResponse(
        session_id=session_id,
        audio_id=audio_id,
        status="stream_ready",
        filename=record.filename,
        engine=result.engine,
        events_url=ready_session.events_url or f"/api/asr/sessions/{session_id}/events",
        result_url=ready_session.result_url or f"/api/asr/sessions/{session_id}/result",
    )


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
