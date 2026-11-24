import json
import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError

from app.api.audio import _RECORDING_KEY, _read_transcript, _transcript_lock
from app.api.auth import require_current_user
from app.db.audio_source_revisions import (
    append_source_revision,
    saved_source_revision,
    source_revision_context,
)
from app.schemas import MedicalField, MedicalRecordFields
from app.schemas.auth import AuthenticatedUser
from app.services.asr.signoff_source import bound_recording, signoff_source_issue
from app.services.audio_source_revisions import (
    RevisionConflict,
    RevisionSelection,
    digest,
    doctor_values,
    prepare_source_revision,
    source_digest,
    source_segments,
)
from app.services.privacy import anonymize_payload


router = APIRouter(prefix="/tasks", tags=["tasks"])


def _doctor(user: AuthenticatedUser = Depends(require_current_user)):
    if user.role != "doctor":
        raise HTTPException(403, "仅经治医生可核对本次录音并创建修订。")
    return user


def _session_state(task_id, doctor_id):
    try:
        row = source_revision_context(task_id, doctor_id)
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    old = json.loads(row["result_json"] or "{}")
    if old.get("clinician_draft_origin") or old.get("degraded"):
        raise RevisionConflict("audio_source_revision_unavailable", "此入口仅支持普通、未降级的音频草稿。")
    original = bound_recording(old) or bound_recording(json.loads(row["task_result"] or "{}"))
    if not original:
        raise RevisionConflict("audio_source_unavailable", "本版没有可核对的原音频绑定。")
    return row, old, original


def _current_source(original):
    try:
        aid = original["audio_id"]
        # Check before using a historical identifier as a path on the server.
        if not isinstance(aid, str) or not _RECORDING_KEY.fullmatch(aid):
            raise ValueError("invalid stored audio id")
        live = _read_transcript(aid)
        issue = signoff_source_issue(original, live)
        if not issue or issue["reason_code"] != "audio_source_changed":
            raise RevisionConflict(
                "audio_role_review_required", "请先核对全部稳定分段，并确认本版音频依据确有变化。"
            )
        segment_ids = [s.segment_id for s in live.segments]
        if (
            not live.all_segments_reviewed()
            or live.needs_review
            or not all(segment_ids)
            or len(set(segment_ids)) != len(segment_ids)
            or any(not s.text.strip() for s in live.segments)
        ):
            raise RevisionConflict(
                "audio_role_review_required", "本次需要逐段核对完成且能定位到原声的转写。"
            )
        return anonymize_payload(live.model_dump(mode="json"))
    except RevisionConflict:
        raise
    except (ValueError, TypeError, OSError, sqlite3.Error, HTTPException) as exc:
        raise RevisionConflict(
            "audio_source_unavailable", "无法核对原录音与当前分段，请恢复资料后重试。"
        ) from exc


def _error(exc: RevisionConflict):
    return HTTPException(409, detail={"reason_code": exc.code, "message": str(exc)})


def recoverable_source(task_id, user):
    if user is None or user.role != "doctor":
        return False
    try:
        _, old, original = _session_state(task_id, user.id)
        _current_source(original)
        doctor_values(old)
    except (HTTPException, ValueError, TypeError, OSError):
        return False
    return True


@router.get("/{task_id}/audio-source-revision")
def preview_audio_revision(task_id: int, user: AuthenticatedUser = Depends(_doctor)):
    try:
        row, old, original = _session_state(task_id, user.id)
        current = _current_source(original)
        return {
            "audio_id": original["audio_id"],
            "revision_id": row["id"],
            "revision_number": row["revision_no"],
            "revision_hash": row["content_hash"],
            "source_hash": source_digest(current),
            "old_segments": source_segments(original),
            "new_segments": source_segments(current),
            "previous_values": doctor_values(old),
            "field_keys": [key for key, item in MedicalRecordFields() if isinstance(item, MedicalField)],
        }
    except RevisionConflict as exc:
        raise _error(exc) from exc
    except (ValidationError, TypeError, KeyError, ValueError) as exc:
        raise _error(
            RevisionConflict("audio_source_unavailable", "本版缺少可核对的完整来源或病历。")
        ) from exc


@router.post("/{task_id}/audio-source-revision")
def create_audio_revision(
    task_id: int, body: RevisionSelection, user: AuthenticatedUser = Depends(_doctor)
):
    request_id = str(body.request_id)
    request_hash = digest(body.model_dump(mode="json"))
    try:
        receipt = saved_source_revision(task_id, user.id, request_id, request_hash)
        if receipt:
            return receipt
        row, old, original = _session_state(task_id, user.id)
        if row["id"] != body.revision_id or row["content_hash"] != body.revision_hash:
            repeated = saved_source_revision(task_id, user.id, request_id, request_hash)
            if repeated:
                return repeated
            raise RevisionConflict("stale_record_revision", "本次病历已有新版本，请重新核对。")
        with _transcript_lock(original["audio_id"]):
            repeated = saved_source_revision(task_id, user.id, request_id, request_hash)
            if repeated:
                return repeated
            current = _current_source(original)
            if source_digest(current) != body.source_hash:
                raise RevisionConflict("stale_audio_source", "录音依据已变化，请重新查看转写及角色。")
            result = prepare_source_revision(old, original, current, body, user.id)
            return append_source_revision(task_id, user.id, request_id, request_hash, result)
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except RevisionConflict as exc:
        raise _error(exc) from exc
    except (ValidationError, TypeError, ValueError) as exc:
        raise _error(
            RevisionConflict("audio_source_unavailable", "本版缺少可核对的完整来源或病历。")
        ) from exc
