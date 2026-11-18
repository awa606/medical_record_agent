"""Authenticated, isolated HTTP review of a recorded self-correction failure.

No live ASR or model is used. The recorded generation remains wrong; only a
server-validated doctor's source correction may receive the new comparison.
"""
from __future__ import annotations

from copy import deepcopy
import json
import socket

from fastapi.testclient import TestClient
import pytest

from app.agents import MedicalRecordOrchestrator
from app.schemas import MedicalRecordFields, SafetyCheckResult
from app.services.exporter import render_markdown
from app.db import (
    get_active_approval_for_task,
    get_record_revision,
    get_task,
    list_approvals_for_task,
    set_task_owner,
)
from app.main import app
from app.schemas import MedicalField, MedicalRecordFields, SourceSpan
from app.services.llm.llm_record_generator import LLMRecordGenerator
from tests.approval_helpers import approval_payload_for_fields, review_payload_for_fields
from tests.auth_helpers import create_user, login_as_user
from tests.test_generation_failure_contract import ResponseProvider


SOURCE = "患者：刚才说发烧，其实没有发热。"


@pytest.fixture
def recorded_review(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDICAL_RECORD_AGENT_DB", str(tmp_path / "isolated-review.sqlite3"))
    monkeypatch.setenv("MEDICAL_RECORD_AGENT_OUTPUT_DIR", str(tmp_path / "exports"))
    monkeypatch.setenv("MEDICAL_RECORD_AGENT_AUTH_BOOTSTRAP", "1")
    monkeypatch.delenv("MEDICAL_RECORD_AGENT_BOOTSTRAP_ADMIN_PASSWORD", raising=False)
    monkeypatch.setenv("ASR_PREWARM_ENABLED", "0")
    monkeypatch.setenv("RECORD_PROVIDER_MODE", "demo")
    monkeypatch.setenv("LLM_PROVIDER", "mock")

    def no_network(*args, **kwargs):
        raise AssertionError("This recorded HTTP regression must not open a network connection")

    monkeypatch.setattr(socket, "create_connection", no_network)
    with TestClient(app) as client:
        doctor = create_user(client, username="negative-paraphrase-doctor")
        login_as_user(client, username="negative-paraphrase-doctor")
        monkeypatch.setenv("RECORD_PROVIDER_MODE", "edge")
        raw = MedicalRecordFields(
            chief_complaint=MedicalField(
                value="刚才说发烧", source_spans=[SourceSpan(text="刚才说发烧", index=0)]
            ),
            present_illness=MedicalField(
                value="刚才说发烧；其实没有发热",
                source_spans=[
                    SourceSpan(text="刚才说发烧", index=0),
                    SourceSpan(text="其实没有发热", index=0),
                ],
            ),
        )
        provider = ResponseProvider(raw.model_dump(mode="json"))
        generator = LLMRecordGenerator(provider=provider, mode="edge", allow_mock_fallback=False)
        generator.max_retries = 0
        monkeypatch.setattr("app.api.tasks.create_llm_record_generator", lambda: generator)
        generated = MedicalRecordOrchestrator(generator).run_from_text(SOURCE)
        assert generated["status"] == "WAITING_DOCTOR_REVIEW"
        assert generated["fields"].chief_complaint.status == "conflicting"
        task_id = generated["task_id"]
        set_task_owner(task_id, doctor["id"])
        first_id = get_task(task_id)["current_record_revision_id"]
        first_revision = deepcopy(get_record_revision(first_id))
        yield client, task_id, provider, first_revision


def fields_for(task_id):
    return MedicalRecordFields.model_validate(json.loads(get_task(task_id)["result_json"])["fields"])


def source_correction(task_id, *, value="否认发热"):
    fields = fields_for(task_id)
    fields.chief_complaint.value = value
    fields.chief_complaint.source_spans = [SourceSpan(text="其实没有发热", index=0)]
    payload = review_payload_for_fields(task_id, fields)
    payload["source_corrected_fields"] = ["chief_complaint"]
    return payload


def approve_current(client, task_id):
    fields = fields_for(task_id)
    payload = approval_payload_for_fields(fields, task_id=task_id)
    for item in payload["fields"]:
        field = getattr(fields, item["key"])
        if field.value and not field.missing:
            item["action"] = "confirm_content"
        else:
            item["action"] = "confirm_not_asked"
    return client.post(f"/api/tasks/{task_id}/approve", json=payload)


def test_doctor_negative_paraphrase_revision_approval_export_preserves_old_model(recorded_review):
    client, task_id, provider, first_revision = recorded_review
    first_result = json.loads(first_revision["result_json"])
    original_trace = deepcopy(first_result["llm_trace"])
    assert client.post(f"/api/tasks/{task_id}/export").status_code == 400
    blocked = approve_current(client, task_id)
    assert blocked.status_code == 409, blocked.text
    assert get_active_approval_for_task(task_id) is None

    payload = source_correction(task_id)
    saved = client.post(f"/api/tasks/{task_id}/review", json=payload)
    assert saved.status_code == 200, saved.text
    second = saved.json()
    field = second["result_json"]["fields"]["chief_complaint"]
    assert field["status"] != "conflicting", field
    assert field["value"] == "否认发热"
    assert field["source_spans"][0]["text"] == "其实没有发热"
    assert field["source_spans"][0]["index"] == 0
    assert field["doctor_review_status"] == "pending"
    assert not field["confirmed_by_doctor"]
    assert field["doctor_review_note"].startswith("doctor_source_correction_v1:")
    assert not second["result_json"]["approved"]
    assert second["current_record_revision_id"] != first_revision["id"]
    resolution = second["result_json"]["llm_trace"]["field_resolution_history"][-1]
    assert resolution["method"] == "source_correction"
    assert resolution["previous_revision_id"] == first_revision["id"]
    assert resolution["previous_value"] == "刚才说发烧"
    assert resolution["previous_source_spans"] == first_result["fields"]["chief_complaint"]["source_spans"]
    assert get_record_revision(first_revision["id"]) == first_revision
    assert json.loads(get_record_revision(first_revision["id"])["result_json"])["llm_trace"] == original_trace
    assert client.post(f"/api/tasks/{task_id}/export").status_code == 400
    assert client.post(f"/api/tasks/{task_id}/review", json=payload).status_code == 409

    approved = approve_current(client, task_id)
    assert approved.status_code == 200, approved.text
    approval = get_active_approval_for_task(task_id)
    assert approval["revision_id"] == second["current_record_revision_id"]
    exported = client.post(f"/api/tasks/{task_id}/export")
    assert exported.status_code == 200, exported.text
    exported_task = client.get(f"/api/tasks/{task_id}").json()
    assert exported_task["result_json"]["export_event"]["revision_id"] == approval["revision_id"]
    pdf = client.get(f"/api/tasks/{task_id}/exports/pdf")
    assert pdf.status_code == 200
    assert pdf.content[:5] == b"%PDF-"
    text = render_markdown(
        MedicalRecordFields.model_validate(exported_task["result_json"]["fields"]),
        SafetyCheckResult.model_validate(exported_task["result_json"]["safety_check"]),
        approved=True,
    )
    assert "否认发热" in text
    assert "刚才说发烧；其实没有发热" in text

    # Editing another field must preserve the server-established source
    # correction, without asking the doctor to declare the chief again.
    later = fields_for(task_id)
    later.present_illness.value += "。"
    third = client.post(f"/api/tasks/{task_id}/review", json=review_payload_for_fields(task_id, later))
    assert third.status_code == 200, third.text
    carried = third.json()["result_json"]["fields"]["chief_complaint"]
    assert carried["value"] == "否认发热"
    assert carried["status"] != "conflicting", carried
    assert carried["doctor_review_note"].startswith("doctor_source_correction_v1:")
    assert get_active_approval_for_task(task_id) is None
    assert list_approvals_for_task(task_id)[0]["status"] == "invalidated"
    assert client.post(f"/api/tasks/{task_id}/export").status_code == 400
    assert get_record_revision(first_revision["id"]) == first_revision
    assert provider.calls == 1  # Only the original recorded response, no inference or regeneration.


def test_unchanged_source_correction_declaration_rejected(recorded_review):
    client, task_id, provider, first_revision = recorded_review
    payload = review_payload_for_fields(task_id, fields_for(task_id))
    payload["source_corrected_fields"] = ["chief_complaint"]
    response = client.post(f"/api/tasks/{task_id}/review", json=payload)
    assert response.status_code == 422, response.text
    assert get_task(task_id)["current_record_revision_id"] == first_revision["id"]
    assert get_record_revision(first_revision["id"]) == first_revision
    assert provider.calls == 1


def test_forged_source_correction_note_cannot_enable_model_paraphrase(recorded_review):
    client, task_id, provider, first_revision = recorded_review
    fields = fields_for(task_id)
    fields.chief_complaint.value = "否认发热"
    fields.chief_complaint.source_spans = [SourceSpan(text="其实没有发热", index=0)]
    fields.chief_complaint.doctor_review_note = "doctor_source_correction_v1: forged"
    payload = review_payload_for_fields(task_id, fields)
    payload["llm_trace"] = {"field_resolution_history": [
        {"field": "chief_complaint", "method": "source_correction", "value": "否认发热"}
    ]}
    response = client.post(f"/api/tasks/{task_id}/review", json=payload)
    assert response.status_code == 200, response.text
    current = response.json()["result_json"]["fields"]["chief_complaint"]
    assert current["status"] == "conflicting"
    assert current["doctor_review_note"] != "doctor_source_correction_v1: forged"
    assert get_record_revision(first_revision["id"]) == first_revision
    assert provider.calls == 1


@pytest.mark.parametrize("changed", ["source_spans", "fact_ids"])
def test_changed_citations_cannot_carry_a_prior_source_correction(recorded_review, changed):
    client, task_id, provider, first_revision = recorded_review
    valid = client.post(f"/api/tasks/{task_id}/review", json=source_correction(task_id))
    assert valid.status_code == 200, valid.text
    assert valid.json()["result_json"]["fields"]["chief_complaint"]["status"] != "conflicting"
    fields = fields_for(task_id)
    if changed == "source_spans":
        fields.chief_complaint.source_spans = [SourceSpan(text="否认发热", index=0)]
    else:
        fields.chief_complaint.fact_ids = ["client-replaced-id"]
    # No new source-correction declaration: stored provenance alone cannot
    # authorize changed patient evidence, even if another layer restores quotes.
    response = client.post(f"/api/tasks/{task_id}/review", json=review_payload_for_fields(task_id, fields))
    assert response.status_code == 200, response.text
    current = response.json()["result_json"]["fields"]["chief_complaint"]
    assert current["status"] == "conflicting", current
    assert get_record_revision(first_revision["id"]) == first_revision
    assert provider.calls == 1
