"""Legacy unapproved results must not evade the current source coverage check."""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.agents import MedicalRecordOrchestrator
from app.db import get_active_approval_for_task, get_record_revision, get_task, set_task_owner
from app.main import app
from app.schemas import MedicalField, MedicalRecordFields, SourceSpan
from app.services.llm.llm_record_generator import LLMRecordGenerator
from scripts.demo_flow import DEFAULT_CONVERSATION
from tests.approval_helpers import approval_payload_for_fields, review_payload_for_fields
from tests.auth_helpers import create_user, login_as_user


def test_legacy_gap_blocks_approval_without_mutating_r1_and_saved_correction_can_sign(tmp_path, monkeypatch):
    database = tmp_path / "coverage.sqlite3"
    monkeypatch.setenv("MEDICAL_RECORD_AGENT_DB", str(database))
    monkeypatch.setenv("MEDICAL_RECORD_AGENT_OUTPUT_DIR", str(tmp_path / "exports"))
    monkeypatch.setenv("RECORD_PROVIDER_MODE", "demo")
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("MEDICAL_RECORD_AGENT_AUTH_BOOTSTRAP", "1")
    monkeypatch.delenv("MEDICAL_RECORD_AGENT_BOOTSTRAP_ADMIN_PASSWORD", raising=False)
    client = TestClient(app)
    doctor = create_user(client, username="legacy-coverage-doctor")
    login_as_user(client, username="legacy-coverage-doctor")
    symptoms = "发热、咳嗽、咽痛两天，最高体温38.2℃，没有胸痛，没有药物过敏史"
    medication = "昨天吃过一次布洛芬"
    fields = MedicalRecordFields(
        chief_complaint=MedicalField(value="发热两天", source_spans=[SourceSpan(text=symptoms, index=1)]),
        present_illness=MedicalField(value=symptoms, source_spans=[SourceSpan(text=symptoms, index=1)]),
        previous_treatment=MedicalField(value=medication, source_spans=[SourceSpan(text=medication, index=3)]),
    )
    generator = LLMRecordGenerator(mode="demo")
    # A historical pre-protection response has no new marker. Only fixture
    # creation bypasses extraction; all approvals/reviews use the real routes.
    with patch.object(generator, "extract_fields", return_value=fields):
        task_id = MedicalRecordOrchestrator(generator).run_from_text(DEFAULT_CONVERSATION)["task_id"]
    set_task_owner(task_id, doctor["id"])
    old_task = dict(get_task(task_id))
    first_id = old_task["current_record_revision_id"]
    old_revision = dict(get_record_revision(first_id))
    assert not fields.present_illness.missing_elements
    approval = approval_payload_for_fields(fields, task_id=task_id)
    blocked = client.post(f"/api/tasks/{task_id}/approve", json=approval)
    assert blocked.status_code == 409, blocked.text
    assert any("现病史漏记" in message for message in blocked.json()["detail"]["errors"])
    assert dict(get_record_revision(first_id)) == old_revision
    assert dict(get_task(task_id)) == old_task
    assert get_active_approval_for_task(task_id) is None
    with closing(sqlite3.connect(database)) as db:
        assert db.execute("select count(*) from approval").fetchone() == (0,)
        assert db.execute("select count(*) from export_event").fetchone() == (0,)

    # Merely clearing the marker/confirming partial content cannot cure it.
    fields.present_illness.value += "。"
    saved = client.post(f"/api/tasks/{task_id}/review", json=review_payload_for_fields(task_id, fields))
    assert saved.status_code == 200, saved.text
    fields = MedicalRecordFields.model_validate(saved.json()["result_json"]["fields"])
    assert any("本次病程用药待核对" in value for value in fields.present_illness.missing_elements)
    assert client.post(f"/api/tasks/{task_id}/approve", json=approval_payload_for_fields(fields, task_id=task_id)).status_code == 409

    fields.present_illness.value = symptoms + "；" + medication
    saved = client.post(f"/api/tasks/{task_id}/review", json=review_payload_for_fields(task_id, fields))
    assert saved.status_code == 200, saved.text
    fields = MedicalRecordFields.model_validate(saved.json()["result_json"]["fields"])
    assert not any("本次病程用药待核对" in value for value in fields.present_illness.missing_elements)
    payload = approval_payload_for_fields(fields, task_id=task_id)
    for item in payload["fields"]:
        if item["key"] == "present_illness":
            item["action"] = "confirm_content"
    approved = client.post(f"/api/tasks/{task_id}/approve", json=payload)
    assert approved.status_code == 200, approved.text
    assert dict(get_record_revision(first_id)) == old_revision
    signed_task = dict(get_task(task_id))
    signed_revision = dict(get_record_revision(signed_task["current_record_revision_id"]))
    assert client.get(f"/api/tasks/{task_id}").status_code == 200
    assert client.get(f"/api/tasks/{task_id}/export-readiness").status_code == 200
    assert dict(get_task(task_id)) == signed_task
    assert dict(get_record_revision(signed_revision["id"])) == signed_revision
    assert dict(get_record_revision(first_id)) == old_revision

    # A later normal edit which removes the medication is a new unsigned
    # revision; old approval remains history, never a way to sign the gap.
    fields.present_illness.value = symptoms
    saved = client.post(f"/api/tasks/{task_id}/review", json=review_payload_for_fields(task_id, fields))
    assert saved.status_code == 200, saved.text
    fields = MedicalRecordFields.model_validate(saved.json()["result_json"]["fields"])
    assert any("本次病程用药待核对" in value for value in fields.present_illness.missing_elements)
    assert get_active_approval_for_task(task_id) is None
    assert client.post(f"/api/tasks/{task_id}/approve", json=approval_payload_for_fields(fields, task_id=task_id)).status_code == 409
    assert client.post(f"/api/tasks/{task_id}/export").status_code == 400
    with closing(sqlite3.connect(database)) as db:
        assert db.execute("select count(*) from approval").fetchone() == (1,)
        assert db.execute("select count(*) from export_event").fetchone() == (0,)
    assert json.loads(old_revision["result_json"])["fields"]["present_illness"]["value"] == symptoms
