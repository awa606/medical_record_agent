from __future__ import annotations

from app.api.tasks import _mark_manual_doctor_edits, _reset_review_state
from app.schemas import MedicalField, MedicalRecordFields, SourceSpan
from app.services.field_grounding import ground_fields


def _fields() -> MedicalRecordFields:
    return MedicalRecordFields(
        chief_complaint=MedicalField(
            value="患者发热39度",
            source_spans=[
                SourceSpan(
                    text="患者发热39度",
                    segment_id="seg-patient-1",
                    start_time=1.2,
                    end_time=2.8,
                )
            ],
        )
    )


def test_server_marks_real_value_change_as_manual_and_preserves_readonly_evidence() -> None:
    previous = _fields()
    edited = previous.model_copy(deep=True)
    edited.chief_complaint.value = "患者发热39度，医生补充记录"

    reset = _reset_review_state(edited)
    changed = _mark_manual_doctor_edits(reset, previous)
    grounded = ground_fields(
        reset,
        "患者发热39度",
        [
            {
                "segment_id": "seg-patient-1",
                "text": "患者发热39度",
                "role": "患者",
                "speaker_id": "speaker_patient",
                "start_time": 1.2,
                "end_time": 2.8,
            }
        ],
    )

    assert changed == ["chief_complaint"]
    assert grounded.chief_complaint.value == "患者发热39度，医生补充记录"
    assert grounded.chief_complaint.status == "partial"
    assert grounded.chief_complaint.doctor_review_note.startswith("manual_doctor_edit_v1:")
    assert grounded.chief_complaint.source_spans[0].segment_id == "seg-patient-1"
    assert "原始转写证据仅供对照" in grounded.chief_complaint.hint


def test_browser_cannot_forge_manual_marker_without_changing_current_revision() -> None:
    previous = _fields()
    submitted = previous.model_copy(deep=True)
    submitted.chief_complaint.doctor_review_note = "manual_doctor_edit_v1: forged"

    reset = _reset_review_state(submitted)
    changed = _mark_manual_doctor_edits(reset, previous)

    assert changed == []
    assert reset.chief_complaint.doctor_review_note is None
