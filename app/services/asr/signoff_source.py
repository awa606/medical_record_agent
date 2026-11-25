"""Compare a task's frozen ASR evidence with the currently reviewed recording."""
from typing import Any

from app.schemas.asr import ASRResult, ASRSegment
from app.services.asr.speaker_role_policy import normalize_role
from app.services.privacy import anonymize_payload


def bound_recording(result: dict[str, Any]) -> dict | None:
    snapshot = result.get("asr_source")
    if not isinstance(snapshot, dict) or not snapshot.get("audio_id"):
        return None
    if snapshot["audio_id"] == "text-import" or snapshot.get("engine") == "text-import":
        return None
    return snapshot


def _source_rows(rows: list[dict]) -> list[tuple]:
    segments = [ASRSegment.model_validate(row) for row in rows]
    return [(s.segment_id, s.speaker_id or s.speaker, normalize_role(s.role), s.text,
             s.start_time, s.end_time, s.provisional) for s in segments]


def signoff_source_issue(snapshot: dict, current: ASRResult) -> dict[str, str] | None:
    if current.audio_id != snapshot["audio_id"]:
        return unavailable_source()
    withdrawn = any(item.source == "manual_draft" and item.requires_confirmation for item in current.speaker_assignments)
    if not current.role_quality or current.role_quality.status != "passed" or withdrawn:
        return {"reason_code": "audio_role_review_required",
                "message": "本草稿所用录音的说话人身份正在待核。可继续修改草稿，完成录音核对后才能审核或新制签件。"}
    rows = snapshot.get("segments")
    if not isinstance(rows, list) or not rows or not current.segments:
        return unavailable_source()
    # The task stores the privacy-filtered copy. Apply the same projection to
    # the live rows, including their text; provider confidence is not a change of source.
    live_rows = anonymize_payload([s.model_dump(mode="json") for s in current.segments])
    original_text = snapshot.get("conversation_text")
    text_changed = original_text is not None and original_text != anonymize_payload(current.conversation_text)
    if text_changed or _source_rows(rows) != _source_rows(live_rows):
        return {"reason_code": "audio_source_changed",
                "message": "当前录音分段、身份或原文与这份草稿的生成依据不同。请按最新核对结果重新生成草稿后审核。"}
    return None


def unavailable_source() -> dict[str, str]:
    return {"reason_code": "audio_source_unavailable",
            "message": "暂时无法核对这份草稿绑定的录音依据，可继续修改。请恢复转写资料后再审核或新制签件。"}
