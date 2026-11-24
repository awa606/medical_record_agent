"""Build a new, unsigned record from the treating doctor's explicit source choices."""

import hashlib
import json
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas import ASRSegment, MedicalField, MedicalRecordFields, SourceSpan
from app.schemas.clinician_assessment import ClinicianAssessment
from app.services.asr.speaker_role_policy import normalize_role
from app.services.field_grounding import ground_fields
from app.services.record_quality import build_record_quality_report
from app.services.record_rules import check_draft_safety, render_draft


class RevisionConflict(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


class SourceChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["quote", "retain_as_doctor", "history_only"]
    segment: int | None = Field(default=None, ge=0)


class RevisionSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: UUID
    revision_id: int = Field(gt=0)
    revision_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    reviewed: Literal[True]
    choices: dict[str, SourceChoice]


def digest(document: Any) -> str:
    data = json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def source_segments(source: dict) -> list[dict]:
    rows = []
    for row in source.get("segments") or []:
        segment = ASRSegment.model_validate(row)
        rows.append(
            {
                "segment_id": segment.segment_id,
                "speaker_id": segment.speaker_id or segment.speaker,
                "role": normalize_role(segment.role),
                "text": segment.text,
                "start_time": segment.start_time,
                "end_time": segment.end_time,
                "provisional": segment.provisional,
            }
        )
    return rows


def source_digest(source: dict) -> str:
    return digest(
        {
            "audio_id": source["audio_id"],
            "conversation_text": source.get("conversation_text"),
            "segments": source_segments(source),
        }
    )


def doctor_values(old: dict) -> dict:
    fields = MedicalRecordFields.model_validate(old["fields"])
    values = {key: item.value for key, item in fields if isinstance(item, MedicalField) and item.value}
    if fields.candidate_diagnoses:
        values["candidate_diagnoses"] = [d.model_dump(mode="json") for d in fields.candidate_diagnoses]
    if old.get("clinician_assessment"):
        values["clinician_assessment"] = ClinicianAssessment.model_validate(
            old["clinician_assessment"]
        ).statement
    return values


def prepare_source_revision(
    old: dict, original: dict, current: dict, selection: RevisionSelection, actor_id: int
) -> dict:
    fields = MedicalRecordFields()
    values = doctor_values(old)
    if not set(values).issubset(selection.choices):
        raise RevisionConflict("incomplete_source_review", "请对上版每个有值项目选择本次处置。")
    assessment = None
    quoted = set()
    for key, choice in selection.choices.items():
        if choice.action != "quote" and (choice.segment is not None or key not in values):
            raise RevisionConflict("invalid_source_choice", "处置与原字段不匹配。")
        if key == "candidate_diagnoses" and choice.action == "history_only":
            continue
        if key == "clinician_assessment" and choice.action != "quote":
            if choice.action == "retain_as_doctor":
                assessment = old["clinician_assessment"]
            continue
        if not isinstance(getattr(fields, key, None), MedicalField):
            raise RevisionConflict("invalid_source_choice", "该项目不支持所选处置。")
        if choice.action == "quote":
            if choice.segment is None or choice.segment >= len(current["segments"]):
                raise RevisionConflict("invalid_source_choice", "请选择当前已核转写中的有效分段。")
            row = ASRSegment.model_validate(current["segments"][choice.segment])
            span = SourceSpan(
                text=row.text, segment_id=row.segment_id, start_time=row.start_time, end_time=row.end_time
            )
            item = MedicalField(
                value=row.text, source_spans=[span], doctor_review_note="医生根据本版已核转写引用"
            )
            quoted.add(key)
        elif choice.action == "retain_as_doctor":
            item = MedicalField(
                value=values[key],
                doctor_review_note="manual_doctor_edit_v1: 医生在本版独立确认保留上版文字。",
            )
        else:
            item = MedicalField.missing_field()
        setattr(fields, key, item)
    if not any(isinstance(v, MedicalField) and v.value for _, v in fields):
        raise RevisionConflict("empty_source_revision", "请至少保留或引用一项本次病历内容。")
    if quoted:
        fields = ground_fields(
            fields,
            current["conversation_text"],
            current["segments"],
            source_corrected_fields=quoted,
            only_corrected=True,
        )
    draft = render_draft(fields)
    safety = check_draft_safety(draft, fields)
    if not safety.passed or safety.blocked:
        raise RevisionConflict("source_revision_safety", "所选择内容未通过草稿的现有安全检查。")
    if assessment:
        entry = ClinicianAssessment.model_validate(assessment)
        draft += f"\n\n本次医生评估（手录）\n{entry.status_label}：{entry.statement}"
    proof = {
        "previous_revision_id": selection.revision_id,
        "previous_content_hash": selection.revision_hash,
        "previous_source_sha256": source_digest(original),
        "source_sha256": source_digest(current),
        "reviewer_user_id": actor_id,
        "choices": {k: v.model_dump() for k, v in selection.choices.items()},
    }
    result = {
        "asr_source": current,
        "conversation_text": current["conversation_text"],
        "fields": fields.model_dump(mode="json"),
        "draft": draft,
        "safety_check": safety.model_dump(mode="json"),
        "quality_report": build_record_quality_report(fields, safety, draft=draft),
        "llm_trace": {"operation": "doctor_audio_source_revision", "actual_provider": "local_rules"},
        "audio_source_revision": proof,
        "approved": False,
        "reviewed": False,
    }
    if assessment:
        result["clinician_assessment"] = assessment
    return result
