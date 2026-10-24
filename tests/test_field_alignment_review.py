"""Explicit review saves refresh only owned coverage hints; no inference/network."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.agents import MedicalRecordOrchestrator
from app.db import get_active_approval_for_task, get_record_revision, get_task, set_task_owner
from app.main import app
from app.schemas import MedicalField, MedicalRecordFields, SourceSpan
from app.services.llm.llm_record_generator import LLMRecordGenerator
from tests.approval_helpers import approval_payload_for_fields, review_payload_for_fields
from tests.auth_helpers import create_user, login_as_user
from tests.test_generation_failure_contract import ResponseProvider


COVERAGE_HINT = "引用含本字段尚未写入的事实，请核对后补充；系统未自动补写。"
MANUAL_HINT = "医生手工修改；原始转写证据仅供对照，需在当前Revision中明确审核。"
SOURCE = "患者：发热两天，没有胸痛。患者：这两天没有服用药物。患者：这次还没有做检查。"


@pytest.mark.parametrize("edit_method", [
    "source_correction", "normal_edit", "normal_edit_cleared_quotes", "normal_edit_previous_no_quotes",
])
def test_review_refreshes_owned_gaps_and_keeps_revision_guards(tmp_path, monkeypatch, edit_method):
    """Fixed first response -> real authenticated HTTP approval/review endpoints."""
    monkeypatch.setenv("MEDICAL_RECORD_AGENT_DB", str(tmp_path / "review.sqlite3"))
    monkeypatch.setenv("MEDICAL_RECORD_AGENT_OUTPUT_DIR", str(tmp_path / "exports"))
    monkeypatch.setenv("RECORD_PROVIDER_MODE", "demo")
    monkeypatch.setenv("MEDICAL_RECORD_AGENT_AUTH_BOOTSTRAP", "1")
    monkeypatch.delenv("MEDICAL_RECORD_AGENT_BOOTSTRAP_ADMIN_PASSWORD", raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    client = TestClient(app)
    doctor = create_user(client, username="coverage-review-doctor")
    login_as_user(client, username="coverage-review-doctor")
    monkeypatch.setenv("RECORD_PROVIDER_MODE", "edge")
    original = MedicalRecordFields(
        chief_complaint=MedicalField(value="发热两天", source_spans=[SourceSpan(text="发热两天，没有胸痛", index=0)]),
        present_illness=MedicalField(value="发热两天", source_spans=[SourceSpan(text="发热两天，没有胸痛", index=0)]),
        previous_treatment=MedicalField(value="这两天没有服用药物", source_spans=[
            SourceSpan(text="这两天没有服用药物", index=1),
            SourceSpan(text="这次还没有做检查", index=2),
        ]),
    )
    provider = ResponseProvider(original.model_dump(mode="json"))
    generator = LLMRecordGenerator(provider=provider, mode="edge", allow_mock_fallback=False)
    generator.max_retries = 0
    monkeypatch.setattr("app.api.tasks.create_llm_record_generator", lambda: generator)
    generated = MedicalRecordOrchestrator(generator).run_from_text(SOURCE)
    task_id = generated["task_id"]
    set_task_owner(task_id, doctor["id"])
    assert generated["status"] == "WAITING_DOCTOR_REVIEW"
    first_id = get_task(task_id)["current_record_revision_id"]
    first_revision = dict(get_record_revision(first_id))
    fields = MedicalRecordFields.model_validate(json.loads(get_task(task_id)["result_json"])["fields"])
    assert fields.present_illness.status == fields.previous_treatment.status == "partial"
    assert fields.present_illness.hint == fields.previous_treatment.hint == COVERAGE_HINT

    # Approve the first, explicitly acknowledged incomplete version, then edit it.
    approval = approval_payload_for_fields(fields, task_id=task_id)
    for item in approval["fields"]:
        field = getattr(fields, item["key"])
        if field.value and not field.missing:
            item["action"] = "confirm_content"
    approved = client.post(f"/api/tasks/{task_id}/approve", json=approval)
    assert approved.status_code == 200, approved.text
    assert get_active_approval_for_task(task_id) is not None
    first_after_approval = dict(get_record_revision(first_id))
    assert first_after_approval == first_revision

    if edit_method == "normal_edit_previous_no_quotes":
        # Simulate an already saved, quote-free manual version. A later normal
        # save must not reach back to the original model revision to fill quotes.
        for key in ("present_illness", "previous_treatment"):
            getattr(fields, key).value += "。"
        takeover_payload = review_payload_for_fields(task_id, fields)
        takeover_payload["manual_takeover_fields"] = ["present_illness", "previous_treatment"]
        taken_over = client.post(f"/api/tasks/{task_id}/review", json=takeover_payload)
        assert taken_over.status_code == 200, taken_over.text
        fields = MedicalRecordFields.model_validate(taken_over.json()["result_json"]["fields"])
        assert not fields.present_illness.source_spans and not fields.previous_treatment.source_spans
        assert fields.present_illness.missing_elements and fields.previous_treatment.missing_elements

    fields.present_illness.value = "发热两天，没有胸痛"
    fields.previous_treatment.value = "这两天没有服用药物；这次还没有做检查"
    expected_values = {key: getattr(fields, key).value for key in ("present_illness", "previous_treatment")}
    expected_spans = {key: [span.model_dump() for span in getattr(fields, key).source_spans] for key in expected_values}
    previous_gaps = {key: list(getattr(fields, key).missing_elements) for key in expected_values}
    if edit_method == "normal_edit_cleared_quotes":
        for key in expected_values:
            getattr(fields, key).source_spans = []  # The visible normal editor clears client quotes.
    payload = review_payload_for_fields(task_id, fields)
    if edit_method == "source_correction":
        payload["source_corrected_fields"] = list(expected_values)
    saved = client.post(f"/api/tasks/{task_id}/review", json=payload)
    assert saved.status_code == 200, saved.text
    revised = saved.json()["result_json"]
    for key, expected in expected_values.items():
        field = revised["fields"][key]
        assert field["value"] == expected
        assert field["source_spans"] == expected_spans[key]
        assert field["status"] == ("complete" if edit_method == "source_correction" else "partial"), field
        assert field["missing_elements"] == (previous_gaps[key] if edit_method == "normal_edit_previous_no_quotes" else [])
        assert field["hint"] == (None if edit_method == "source_correction" else MANUAL_HINT)
        assert not field["confirmed_by_doctor"]
        assert field["doctor_review_status"] == "pending"
        assert field["doctor_review_note"].startswith(
            "doctor_source_correction_v1:" if edit_method == "source_correction" else "manual_doctor_edit_v1:")
    assert get_task(task_id)["current_record_revision_id"] != first_id
    assert dict(get_record_revision(first_id)) == first_revision
    assert get_active_approval_for_task(task_id) is None
    assert not revised["approved"]
    assert client.post(f"/api/tasks/{task_id}/export").status_code == 400
    assert client.post(f"/api/tasks/{task_id}/review", json=payload).status_code == 409
    assert provider.calls == generator.attempt_count == 1

    # A subsequent contradictory correction still goes through grounding first.
    wrong = MedicalRecordFields.model_validate(revised["fields"])
    wrong.present_illness.value = "发热两天，有胸痛"
    wrong.present_illness.status = "partial"
    wrong.present_illness.hint = COVERAGE_HINT
    wrong.present_illness.missing_elements = ["已引用但未写入：胸痛（无）"]
    if edit_method in {"source_correction", "normal_edit_previous_no_quotes"}:
        # Explicit selection is required to introduce evidence after a version
        # that already had none. The default editor is not allowed to infer it.
        wrong.present_illness.source_spans = [SourceSpan(text="发热两天，没有胸痛", index=0)]
    else:
        wrong.present_illness.source_spans = []
    bad_payload = review_payload_for_fields(task_id, wrong)
    if edit_method in {"source_correction", "normal_edit_previous_no_quotes"}:
        bad_payload["source_corrected_fields"] = ["present_illness"]
    rejected_content = client.post(f"/api/tasks/{task_id}/review", json=bad_payload)
    assert rejected_content.status_code == 200, rejected_content.text
    contradictory = rejected_content.json()["result_json"]["fields"]["present_illness"]
    assert contradictory["status"] == "conflicting"
    assert contradictory["value"] == "发热两天，有胸痛"
    assert dict(get_record_revision(first_id)) == first_revision
    assert client.post(f"/api/tasks/{task_id}/export").status_code == 400
    assert provider.calls == generator.attempt_count == 1


@pytest.mark.parametrize("value,expected_status,expected_gaps,expected_hint", [
    ("发热两天，没有胸痛", "complete", [], None),
    ("发热两天", "partial", ["已引用但未写入：胸痛（无）"], COVERAGE_HINT),
])
def test_refresh_recomputes_only_owned_coverage_preserving_content(value, expected_status, expected_gaps, expected_hint):
    from app.services.field_alignment import refresh_existing_coverage_hints

    fields = MedicalRecordFields(present_illness=MedicalField(
        value=value, status="partial", hint=COVERAGE_HINT,
        missing_elements=["已引用但未写入：陈旧诊断（无）"],
        source_spans=[SourceSpan(text="发热两天，没有胸痛", index=7, segment_id="source-7", start_time=3, end_time=5)],
        fact_ids=["retained-fact"], confidence=0.8,
        doctor_review_note="doctor_source_correction_v1: 根据原文修正",
    ))
    original = fields.model_dump()
    refreshed = refresh_existing_coverage_hints(fields)
    field = refreshed.present_illness
    assert fields.model_dump() == original
    assert field.status == expected_status
    assert field.hint == expected_hint
    assert field.missing_elements == expected_gaps
    for key in ("value", "source_spans", "fact_ids", "confidence", "doctor_review_note"):
        assert field.model_dump()[key] == original["present_illness"][key]
    assert not field.confirmed_by_doctor
    assert field.doctor_review_status == "pending"


def test_refresh_retains_unrelated_missing_elements_and_does_not_promote_them():
    from app.services.field_alignment import refresh_existing_coverage_hints

    fields = MedicalRecordFields(previous_treatment=MedicalField(
        value="这次还没有做检查", status="partial", hint=COVERAGE_HINT,
        missing_elements=["需医生补充既往检查时间", "已引用的检查状态未写入：患者：这次还没有做检查"],
        source_spans=[SourceSpan(text="患者：这次还没有做检查", index=2)],
    ))
    result = refresh_existing_coverage_hints(fields).previous_treatment
    assert result.status == "partial"
    assert result.missing_elements == ["需医生补充既往检查时间"]
    assert result.hint is None
    assert result.source_spans[0].text == "患者：这次还没有做检查"


@pytest.mark.parametrize("overrides", [
    {"status": "conflicting"},
    {"status": "complete"},
    {"hint": "其他校验器的提示"},
    {"hint": COVERAGE_HINT + "额外文字"},
    {"missing_elements": ["其他校验器的缺口"]},
    {"confirmed_by_doctor": True, "doctor_review_status": "content_confirmed"},
    {"doctor_review_note": "manual_doctor_edit_v1: 医生补录"},
    {"missing": True, "value": None},
])
def test_refresh_does_not_touch_unowned_conflicting_missing_manual_or_confirmed_fields(overrides):
    from app.services.field_alignment import refresh_existing_coverage_hints

    data = {"value": "发热两天，没有胸痛", "status": "partial", "hint": COVERAGE_HINT,
            "missing_elements": ["已引用但未写入：胸痛（无）"],
            "source_spans": [SourceSpan(text="发热两天，没有胸痛", index=0)]}
    data.update(overrides)
    fields = MedicalRecordFields(present_illness=MedicalField(**data))
    assert refresh_existing_coverage_hints(fields).model_dump() == fields.model_dump()


def test_refresh_does_not_classify_ordinary_fields_or_clear_other_field_coverage_labels():
    from app.services.field_alignment import refresh_existing_coverage_hints

    fields = MedicalRecordFields(
        present_illness=MedicalField(value="发热两天", source_spans=[SourceSpan(text="发热两天，没有胸痛")]),
        allergy_history=MedicalField(value="没有药物过敏史", status="partial", hint=COVERAGE_HINT,
            missing_elements=["已引用但未写入：胸痛（无）"], source_spans=[SourceSpan(text="没有药物过敏史")]),
    )
    assert refresh_existing_coverage_hints(fields).model_dump() == fields.model_dump()


@pytest.mark.parametrize("value,expected_gaps", [
    ("发热两天，没有胸痛", []),
    ("发热两天", ["已引用但未写入：胸痛（无）"]),
])
def test_default_manual_edit_refreshes_only_owned_gaps_and_keeps_manual_review(value, expected_gaps):
    from app.services.field_alignment import refresh_existing_coverage_hints

    fields = MedicalRecordFields(present_illness=MedicalField(
        value=value, status="partial", hint=MANUAL_HINT,
        missing_elements=["其他仍需补充的信息", "已引用但未写入：胸痛（无）"],
        source_spans=[SourceSpan(text="发热两天，没有胸痛", index=0)],
        doctor_review_note="manual_doctor_edit_v1: 医生手工修改",
    ))
    original = fields.model_dump()
    result = refresh_existing_coverage_hints(fields).present_illness
    assert fields.model_dump() == original
    assert result.status == "partial"
    assert result.hint == MANUAL_HINT
    assert result.missing_elements == ["其他仍需补充的信息", *expected_gaps]
    assert result.doctor_review_note == original["present_illness"]["doctor_review_note"]
    assert result.value == value
    assert [s.model_dump() for s in result.source_spans] == original["present_illness"]["source_spans"]
    assert not result.confirmed_by_doctor
    assert result.doctor_review_status == "pending"


@pytest.mark.parametrize("overrides", [
    {"source_spans": []},
    {"status": "conflicting", "hint": "否定状态与证据矛盾"},
    {"hint": "其他校验器的人工提示"},
    {"missing_elements": ["其他校验器的缺口"]},
])
def test_manual_takeover_and_other_manual_findings_are_not_refreshed(overrides):
    from app.services.field_alignment import refresh_existing_coverage_hints

    data = {"value": "发热两天，没有胸痛", "status": "partial", "hint": MANUAL_HINT,
            "missing_elements": ["已引用但未写入：胸痛（无）"],
            "source_spans": [SourceSpan(text="发热两天，没有胸痛", index=0)],
            "doctor_review_note": "manual_doctor_edit_v1: 医生补录"}
    data.update(overrides)
    fields = MedicalRecordFields(present_illness=MedicalField(**data))
    assert refresh_existing_coverage_hints(fields).model_dump() == fields.model_dump()
