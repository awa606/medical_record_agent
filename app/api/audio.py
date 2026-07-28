from __future__ import annotations

import json
import mimetypes
import os
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse

from app.agents import MedicalRecordOrchestrator
from app.api.auth import assert_owner_or_admin, current_user_from_request, require_current_user
from app.api.records import ensure_record_provider_available, run_record_generation_task
from app.db import bind_task_to_encounter, get_encounter, set_task_owner
from app.schemas import ASREvaluationRequest, ASREvaluationResult, ASRResult, AudioRecord
from app.services.asr import ASREvaluator, apply_manifest_role_strategy, create_asr_engine
from app.services.asr.auto_roles import ensure_automatic_speaker_roles
from app.services.asr.config import configured_asr_backend, requested_asr_engine_mismatch
from app.services.asr.funasr_reliability import funasr_failure_payload
from app.services.asr.role_strategy import find_sample_config
from app.services.runtime_limits import audio_upload_max_bytes, copy_upload_with_limit


router = APIRouter(prefix="/audio", tags=["audio"], dependencies=[Depends(require_current_user)])

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_UPLOAD_DIR = PROJECT_ROOT / "data" / "uploads"
ALLOWED_AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".flac", ".ogg"}


def get_upload_dir() -> Path:
    return Path(os.environ.get("MEDICAL_RECORD_AGENT_UPLOAD_DIR", DEFAULT_UPLOAD_DIR))


def _safe_extension(filename: str) -> str:
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_AUDIO_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Only wav/mp3/m4a/flac/ogg audio files are supported")
    return extension


def _audio_path(audio_id: str) -> Path:
    upload_dir = get_upload_dir()
    matches = list(upload_dir.glob(f"{audio_id}.*"))
    audio_matches = [
        path for path in matches if path.suffix.lower() in ALLOWED_AUDIO_EXTENSIONS
    ]
    if not audio_matches:
        raise HTTPException(status_code=404, detail="Audio not found")
    return audio_matches[0]


def _record_path(audio_id: str) -> Path:
    return get_upload_dir() / f"{audio_id}.record.json"


def _transcript_path(audio_id: str) -> Path:
    return get_upload_dir() / f"{audio_id}.transcript.json"


def _write_audio_record(record: AudioRecord) -> None:
    path = _record_path(record.audio_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(record.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _read_audio_record(audio_id: str) -> AudioRecord:
    record_path = _record_path(audio_id)
    if record_path.exists():
        return AudioRecord.model_validate_json(record_path.read_text(encoding="utf-8"))

    audio_path = _audio_path(audio_id)
    return AudioRecord(
        audio_id=audio_id,
        filename=audio_path.name,
        path=str(audio_path),
        status="uploaded",
        size_bytes=audio_path.stat().st_size,
        created_at=None,
    )


def _assert_audio_access(record: AudioRecord, request: Request | None) -> None:
    assert_owner_or_admin(record.owner_user_id, request, resource_name="audio")


def _write_transcript(result: ASRResult) -> None:
    path = _transcript_path(result.audio_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(result.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _read_transcript(audio_id: str) -> ASRResult:
    path = _transcript_path(audio_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Transcript not found")
    return ASRResult.model_validate_json(path.read_text(encoding="utf-8"))


def _ensure_nonblocking_role_quality(result: ASRResult) -> ASRResult:
    return ensure_automatic_speaker_roles(result)


def _generation_owner_for_encounter(encounter_id: int, request: Request | None) -> int:
    user = current_user_from_request(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    encounter = get_encounter(encounter_id)
    if encounter is None:
        raise HTTPException(status_code=404, detail="Encounter not found")
    encounter_doctor_id = encounter.get("doctor_user_id")
    if encounter_doctor_id is None:
        raise HTTPException(status_code=409, detail="Encounter has no doctor owner")
    if user.role != "admin" and int(encounter_doctor_id) != user.id:
        raise HTTPException(status_code=403, detail="You are not allowed to access this encounter")
    check_in_status = encounter.get("check_in_status") or "checked_in"
    if check_in_status == "registered":
        raise HTTPException(status_code=409, detail="Encounter must be checked in before record generation")
    if check_in_status in {"completed", "cancelled"}:
        raise HTTPException(status_code=409, detail="Encounter is closed and cannot generate a record")
    if encounter.get("task_id") is not None:
        raise HTTPException(status_code=409, detail="Encounter is already bound to a task")
    return int(encounter_doctor_id)


def _sample_id_from_record(record: AudioRecord) -> str:
    return Path(record.filename).stem or record.audio_id


@router.post("/upload")
def upload_audio(
    file: UploadFile = File(...),
    request: Request = None,
    recognition_mode: Literal["fast", "follow"] = "fast",
) -> AudioRecord:
    extension = _safe_extension(file.filename or "")
    upload_dir = get_upload_dir()
    upload_dir.mkdir(parents=True, exist_ok=True)

    audio_id = uuid.uuid4().hex
    filename = f"{audio_id}{extension}"
    destination = upload_dir / filename
    size_bytes = copy_upload_with_limit(
        file.file,
        destination,
        max_bytes=audio_upload_max_bytes(),
    )

    record = AudioRecord(
        audio_id=audio_id,
        filename=file.filename or filename,
        path=str(destination),
        status="uploaded",
        content_type=getattr(file, "content_type", None),
        size_bytes=size_bytes,
        created_at=datetime.now(UTC).isoformat(),
        owner_user_id=current_user_from_request(request).id if current_user_from_request(request) else None,
        recognition_mode=recognition_mode,
    )
    _write_audio_record(record)
    return record


@router.get("/{audio_id}")
def read_audio(audio_id: str, request: Request = None) -> AudioRecord:
    record = _read_audio_record(audio_id)
    _assert_audio_access(record, request)
    return record


@router.get("/{audio_id}/media")
def stream_audio_media(audio_id: str, request: Request = None) -> FileResponse:
    record = _read_audio_record(audio_id)
    _assert_audio_access(record, request)
    audio_path = _audio_path(audio_id)
    media_type = record.content_type or mimetypes.guess_type(record.filename)[0] or "application/octet-stream"
    return FileResponse(
        audio_path,
        media_type=media_type,
        headers={"Accept-Ranges": "bytes", "Cache-Control": "private, max-age=3600"},
    )


@router.post("/{audio_id}/transcribe")
def transcribe_audio(
    audio_id: str,
    request: Request = None,
    engine: str = Query(default="mock"),
    recognition_mode: Literal["fast", "follow"] = "fast",
) -> dict[str, Any]:
    record = _read_audio_record(audio_id)
    _assert_audio_access(record, request)
    user = current_user_from_request(request)
    resolved_engine = configured_asr_backend(engine, user_role=user.role if user is not None else None)
    engine_mismatch = requested_asr_engine_mismatch(engine, resolved_engine)
    if engine_mismatch is not None:
        raise HTTPException(status_code=409, detail=engine_mismatch)
    if recognition_mode == "follow":
        from app.api.asr_sessions import start_follow_session_for_audio_record

        session = start_follow_session_for_audio_record(
            record,
            engine=resolved_engine,
            owner_user_id=user.id if user is not None else None,
        )
        return {
            "audio_id": audio_id,
            "status": session.status,
            "recognition_mode": "follow",
            "session_id": session.session_id,
            "events_url": session.events_url,
            "result_url": session.result_url,
            "media_url": f"/api/audio/{audio_id}/media",
        }

    started_at = time.perf_counter()
    try:
        asr_engine = create_asr_engine(resolved_engine)
        result = asr_engine.transcribe(audio_id, Path(record.path))
        result = apply_manifest_role_strategy(result, _sample_id_from_record(record))
        result = _ensure_nonblocking_role_quality(result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        if (resolved_engine or "").strip().lower() == "funasr":
            raise HTTPException(status_code=503, detail=funasr_failure_payload(exc)) from exc
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    processing_duration = max(time.perf_counter() - started_at, 0.0)
    audio_duration = result.duration or result.audio_duration_seconds
    rtf = round(processing_duration / audio_duration, 4) if audio_duration and audio_duration > 0 else None
    result = result.model_copy(
        update={
            "recognition_mode": recognition_mode,
            "audio_duration_seconds": audio_duration,
            "processing_duration_seconds": round(processing_duration, 4),
            "rtf": rtf,
        }
    )
    _write_transcript(result)
    _write_audio_record(
        record.model_copy(
            update={
                "status": "completed",
                "recognition_mode": recognition_mode,
            }
        )
    )
    return {
        "audio_id": audio_id,
        "status": "completed",
        "recognition_mode": recognition_mode,
        "audio_duration_seconds": audio_duration,
        "processing_duration_seconds": round(processing_duration, 4),
        "rtf": rtf,
        "asr_result": result.model_dump(),
    }


@router.get("/{audio_id}/transcript")
def read_audio_transcript(audio_id: str, request: Request = None) -> ASRResult:
    if request is not None:
        record = _read_audio_record(audio_id)
        _assert_audio_access(record, request)
    return _read_transcript(audio_id)


@router.post("/{audio_id}/evaluate")
def evaluate_audio(
    audio_id: str,
    payload: ASREvaluationRequest,
    request: Request = None,
) -> ASREvaluationResult:
    record = _read_audio_record(audio_id)
    _assert_audio_access(record, request)
    transcript = _read_transcript(audio_id)
    expected_keywords = payload.expected_keywords
    sample = find_sample_config(_sample_id_from_record(record))
    if not expected_keywords and sample:
        expected_keywords = sample.get("expected_keywords") or []
    return ASREvaluator().evaluate(
        audio_id=audio_id,
        engine=transcript.engine,
        ground_truth_text=payload.ground_truth_text,
        recognized_text=transcript.text,
        expected_keywords=expected_keywords,
    )


@router.post("/{audio_id}/generate-record")
def generate_record_from_audio(
    audio_id: str,
    background_tasks: BackgroundTasks,
    request: Request = None,
    encounter_id: int | None = None,
) -> dict[str, object]:
    try:
        record = _read_audio_record(audio_id)
    except HTTPException as exc:
        if exc.status_code != 404:
            raise
        record = None
    if record is not None:
        _assert_audio_access(record, request)
    result = _read_transcript(audio_id)
    result = _ensure_nonblocking_role_quality(result)
    _write_transcript(result)
    conversation_text = result.conversation_text.strip()
    if not conversation_text:
        raise HTTPException(status_code=400, detail="Transcript conversation_text is empty")

    ensure_record_provider_available()
    encounter_owner_id = (
        _generation_owner_for_encounter(encounter_id, request)
        if encounter_id is not None
        else None
    )
    orchestrator = MedicalRecordOrchestrator()
    task_id = orchestrator.create_text_task(conversation_text)
    user = current_user_from_request(request)
    if encounter_id is not None:
        try:
            bind_task_to_encounter(
                task_id,
                encounter_id,
                owner_user_id=encounter_owner_id,
                check_in_status="in_progress",
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    elif user is not None:
        set_task_owner(task_id, user.id)
    background_tasks.add_task(
        run_record_generation_task,
        task_id,
        conversation_text,
    )

    return {
        "task_id": task_id,
        "status": MedicalRecordOrchestrator.STATUS_CREATED,
        "events_url": f"/api/tasks/{task_id}/events",
    }
