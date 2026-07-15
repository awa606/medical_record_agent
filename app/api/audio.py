from __future__ import annotations

import json
import mimetypes
import os
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from app.agents import MedicalRecordOrchestrator
from app.api.records import run_record_generation_task
from app.schemas import ASREvaluationRequest, ASREvaluationResult, ASRResult, AudioRecord
from app.services.asr import ASREvaluator, apply_manifest_role_strategy, create_asr_engine
from app.services.asr.role_quality import attach_speaker_role_quality, build_speaker_role_quality
from app.services.asr.role_strategy import find_sample_config


router = APIRouter(prefix="/audio", tags=["audio"])

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


def _require_passed_role_quality(result: ASRResult) -> ASRResult:
    quality = result.role_quality or build_speaker_role_quality(result)
    if quality.status != "passed":
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Speaker role quality gate did not pass.",
                "role_quality": quality.model_dump(mode="json"),
            },
        )
    return result.model_copy(update={"role_quality": quality})


def _sample_id_from_record(record: AudioRecord) -> str:
    return Path(record.filename).stem or record.audio_id


@router.post("/upload")
def upload_audio(file: UploadFile = File(...)) -> AudioRecord:
    extension = _safe_extension(file.filename or "")
    upload_dir = get_upload_dir()
    upload_dir.mkdir(parents=True, exist_ok=True)

    audio_id = uuid.uuid4().hex
    filename = f"{audio_id}{extension}"
    destination = upload_dir / filename
    with destination.open("wb") as output:
        shutil.copyfileobj(file.file, output)

    record = AudioRecord(
        audio_id=audio_id,
        filename=file.filename or filename,
        path=str(destination),
        status="uploaded",
        content_type=getattr(file, "content_type", None),
        size_bytes=destination.stat().st_size,
        created_at=datetime.now(UTC).isoformat(),
    )
    _write_audio_record(record)
    return record


@router.get("/{audio_id}")
def read_audio(audio_id: str) -> AudioRecord:
    return _read_audio_record(audio_id)


@router.get("/{audio_id}/media")
def stream_audio_media(audio_id: str) -> FileResponse:
    record = _read_audio_record(audio_id)
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
    engine: str = Query(default="mock"),
) -> dict[str, Any]:
    record = _read_audio_record(audio_id)
    try:
        asr_engine = create_asr_engine(engine)
        result = asr_engine.transcribe(audio_id, Path(record.path))
        result = apply_manifest_role_strategy(result, _sample_id_from_record(record))
        result = attach_speaker_role_quality(result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    _write_transcript(result)
    return {
        "audio_id": audio_id,
        "status": "completed",
        "asr_result": result.model_dump(),
    }


@router.get("/{audio_id}/transcript")
def read_audio_transcript(audio_id: str) -> ASRResult:
    return _read_transcript(audio_id)


@router.post("/{audio_id}/evaluate")
def evaluate_audio(
    audio_id: str,
    payload: ASREvaluationRequest,
) -> ASREvaluationResult:
    transcript = _read_transcript(audio_id)
    record = _read_audio_record(audio_id)
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
) -> dict[str, object]:
    result = _read_transcript(audio_id)
    result = _require_passed_role_quality(result)
    conversation_text = result.conversation_text.strip()
    if not conversation_text:
        raise HTTPException(status_code=400, detail="Transcript conversation_text is empty")

    orchestrator = MedicalRecordOrchestrator()
    task_id = orchestrator.create_text_task(conversation_text)
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
