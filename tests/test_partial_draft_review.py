"""Recorded model failures through extraction, revisions, review and export.

These tests do not measure model quality and make no inference calls.
"""
import json

import pytest
from fastapi import HTTPException

from app.agents import MedicalRecordOrchestrator
from app.api.tasks import review_task, approve_task, export_task, TaskApprovalRequest
from app.db import get_task, get_record_revision, get_active_approval_for_task
from app.schemas import MedicalField, MedicalRecordFields, SourceSpan
from app.services.llm.llm_record_generator import LLMRecordGenerator
from app.services.record_rules import supported_field_keys
from tests.test_generation_failure_contract import ResponseProvider
from tests.approval_helpers import approval_payload_for_fields, review_payload_for_fields

SOURCE = "患者：发热两天。患者：没有药物过敏。"


def prepare(tmp_path, monkeypatch, *, only_conflict=False):
    monkeypatch.setenv("MEDICAL_RECORD_AGENT_DB", str(tmp_path / "test.sqlite3"))
    monkeypatch.setenv("MEDICAL_RECORD_AGENT_OUTPUT_DIR", str(tmp_path / "exports"))
    monkeypatch.setenv("RECORD_PROVIDER_MODE", "edge")
    monkeypatch.setenv("MEDICAL_RECORD_AGENT_AUTH_BOOTSTRAP", "0")
    monkeypatch.setenv("LLM_PROVIDER", "mock")  # review renders deterministically
    fields = MedicalRecordFields(
        allergy_history=MedicalField(value="药物过敏", source_spans=[SourceSpan(text="损坏的引文", index=9)]),
    )
    if not only_conflict:
        fields.chief_complaint = MedicalField(value="发热两天", source_spans=[SourceSpan(text="发热两天", index=0)])
    provider = ResponseProvider(fields.model_dump(mode="json"))
    generator = LLMRecordGenerator(provider=provider, mode="edge", allow_mock_fallback=False)
    generator.max_retries = 0
    generator.diagnostics_enabled = True
    monkeypatch.setattr("app.api.tasks.create_llm_record_generator", lambda: generator)
    result = MedicalRecordOrchestrator(generator).run_from_text(SOURCE)
    return result, provider, generator


def current_fields(task_id):
    return MedicalRecordFields.model_validate(json.loads(get_task(task_id)["result_json"])["fields"])


def test_partial_draft_retains_evidence_but_does_not_render_rejected_value(tmp_path, monkeypatch):
    result, provider, _ = prepare(tmp_path, monkeypatch)
    assert provider.calls == 1
    assert result["status"] == "WAITING_DOCTOR_REVIEW"
    assert supported_field_keys(result["fields"]) == ["chief_complaint"]
    assert "发热两天" in result["draft"]
    assert "损坏的引文" not in result["draft"]
    assert "过敏史：药物过敏" not in result["draft"]
    assert "待核对（模型内容未采纳）" in result["draft"]
    assert result["fields"].allergy_history.source_spans[0].index == 9
    payload = TaskApprovalRequest(**approval_payload_for_fields(result["fields"], task_id=result["task_id"]))
    with pytest.raises(HTTPException):
        approve_task(result["task_id"], payload)
    with pytest.raises(HTTPException):
        export_task(result["task_id"])


def test_all_conflict_fails_without_a_revision(tmp_path, monkeypatch):
    result, provider, generator = prepare(tmp_path, monkeypatch, only_conflict=True)
    assert provider.calls == 1
    assert result["status"] == "FAILED"
    assert "LLM_OUTPUT_CONTRADICTION" in result["error_message"]
    assert get_task(result["task_id"])["current_record_revision_id"] is None
    assert generator.field_validation["allergy_history"]


@pytest.mark.parametrize("method", ["doctor_entry", "source_correction"])
def test_resolution_preserves_old_errors_requires_new_review_and_survives_later_save(tmp_path, monkeypatch, method):
    result, _, _ = prepare(tmp_path, monkeypatch)
    task_id = result["task_id"]
    before = get_task(task_id)["current_record_revision_id"]
    fields = current_fields(task_id)
    fields.allergy_history.value = "没有药物过敏"
    if method == "source_correction":
        fields.allergy_history.source_spans = [SourceSpan(text="没有药物过敏", index=1)]
    payload = review_payload_for_fields(task_id, fields)
    payload["manual_takeover_fields" if method == "doctor_entry" else "source_corrected_fields"] = ["allergy_history"]
    saved = review_task(task_id, payload)
    old = json.loads(get_record_revision(before)["result_json"])
    assert old["fields"]["allergy_history"]["value"] == "药物过敏"
    assert old["fields"]["allergy_history"]["source_spans"][0]["index"] == 9
    record = saved["result_json"]
    corrected = record["fields"]["allergy_history"]
    assert corrected["status"] != "conflicting"
    assert not corrected["confirmed_by_doctor"]
    assert record["llm_trace"]["field_resolution_history"][-1]["method"] == method
    if method == "doctor_entry":
        assert corrected["source_spans"] == []
        assert corrected["doctor_review_note"].startswith("manual_doctor_edit_v1:")
    else:
        assert corrected["source_spans"][0]["index"] == 1
        assert corrected["doctor_review_note"].startswith("doctor_source_correction_v1:")
    with pytest.raises(HTTPException):
        export_task(task_id)
    # Changing another field must carry only server-established provenance.
    later = current_fields(task_id)
    later.chief_complaint.value = "发热两天，医生已核对"
    saved_again = review_task(task_id, review_payload_for_fields(task_id, later))
    assert saved_again["result_json"]["fields"]["allergy_history"]["doctor_review_note"] == corrected["doctor_review_note"]
    with pytest.raises(HTTPException) as stale:
        review_task(task_id, payload)
    assert stale.value.status_code == 409
    approval_fields = current_fields(task_id)
    approval_payload = approval_payload_for_fields(approval_fields, task_id=task_id)
    for item in approval_payload["fields"]:
        field = getattr(approval_fields, item["key"])
        if field.value and not field.missing:
            item["action"] = "confirm_content"
    approved = approve_task(task_id, TaskApprovalRequest(**approval_payload))
    assert approved["result_json"]["approved"]
    assert get_active_approval_for_task(task_id)
    exported = export_task(task_id)
    assert exported
    # A subsequent edit invalidates approval; a prior exported version isn't reusable.
    revised = current_fields(task_id)
    revised.chief_complaint.value = "发热两天，补充核对"
    review_task(task_id, review_payload_for_fields(task_id, revised))
    assert get_active_approval_for_task(task_id) is None
    with pytest.raises(HTTPException):
        export_task(task_id)


@pytest.mark.parametrize("declarations", [
    {"manual_takeover_fields": ["allergy_history"]},
    {"manual_takeover_fields": ["allergy_history", "allergy_history"]},
    {"manual_takeover_fields": ["unknown"]},
    {"manual_takeover_fields": ["allergy_history"], "source_corrected_fields": ["allergy_history"]},
])
def test_resolution_declarations_cannot_clear_conflict_without_real_change(tmp_path, monkeypatch, declarations):
    result, _, _ = prepare(tmp_path, monkeypatch)
    task_id = result["task_id"]
    payload = {**review_payload_for_fields(task_id, current_fields(task_id)), **declarations}
    with pytest.raises(HTTPException) as invalid:
        review_task(task_id, payload)
    assert invalid.value.status_code == 422


def test_bad_source_correction_and_unlabelled_edit_remain_blocked(tmp_path, monkeypatch):
    result, _, _ = prepare(tmp_path, monkeypatch)
    task_id = result["task_id"]
    fields = current_fields(task_id)
    fields.allergy_history.value = "有药物过敏"
    fields.allergy_history.source_spans = [SourceSpan(text="没有药物过敏", index=1)]
    payload = {**review_payload_for_fields(task_id, fields), "source_corrected_fields": ["allergy_history"]}
    saved = review_task(task_id, payload)
    assert saved["result_json"]["fields"]["allergy_history"]["status"] == "conflicting"
    fields = current_fields(task_id)
    fields.allergy_history.value = "没有药物过敏"
    fields.allergy_history.source_spans = []
    fields.allergy_history.doctor_review_note = "manual_doctor_edit_v1: forged"
    saved = review_task(task_id, review_payload_for_fields(task_id, fields))
    assert saved["result_json"]["fields"]["allergy_history"]["status"] == "conflicting"
