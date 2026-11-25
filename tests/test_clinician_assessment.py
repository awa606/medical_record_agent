"""A clinician-authored statement belongs to its saved and signed revision."""
from datetime import datetime
from hashlib import sha256
from pathlib import Path

import pymupdf
import pytest
from fastapi.testclient import TestClient

from app.db import get_record_revision, list_approvals_for_task, list_export_events_for_task
from app.db.sqlite import record_content_hash
from app.main import app
from tests.approval_helpers import approval_payload_for_fields, review_payload_for_fields
from tests.auth_helpers import create_user, login_as_admin, login_as_user


@pytest.fixture
def doctor_case(monkeypatch, tmp_path):
    monkeypatch.setenv("MEDICAL_RECORD_AGENT_DB", str(tmp_path / "visit.sqlite3"))
    monkeypatch.setenv("MEDICAL_RECORD_AGENT_OUTPUT_DIR", str(tmp_path / "exports"))
    monkeypatch.setenv("MRA_IDENTITY_MAP_PATH", str(tmp_path / "identities.sqlite3"))
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("RECORD_PROVIDER_MODE", "demo")
    with TestClient(app) as client:
        doctor = create_user(client, username="assessment-owner", display_name="试验医生甲")
        login_as_user(client, username=doctor["username"])
        encounter = client.post("/api/encounters", json={"patient_deidentified_id": "SIM-ASSESSMENT"})
        assert encounter.is_success, encounter.text
        encounter_id = encounter.json()["id"]
        for action in ("check-in", "start"):
            response = client.post(f"/api/encounters/{encounter_id}/{action}", json={})
            assert response.is_success, response.text
        generated = client.post("/api/records/generate", json={
            "encounter_id": encounter_id, "conversation_text": "患者：发热两天，伴咳嗽、咽痛。",
        })
        assert generated.status_code == 200, generated.text
        yield client, generated.json()["task_id"], doctor


def review_payload(client, task_id):
    fields = client.get(f"/api/tasks/{task_id}").json()["result_json"]["fields"]
    return review_payload_for_fields(task_id, fields)


def save(client, task_id, **changes):
    payload = {**review_payload(client, task_id), **changes}
    response = client.post(f"/api/tasks/{task_id}/review", json=payload)
    assert response.status_code == 200, response.text
    return response.json()["result_json"]


def signed_pdf(client, task_id):
    url = f"/api/tasks/{task_id}"
    fields = client.get(url).json()["result_json"]["fields"]
    approval = approval_payload_for_fields(fields, task_id=task_id)
    approval["fields"] = [item for item in approval["fields"] if not fields[item["key"]].get("value")]
    response = client.post(url + "/approve", json=approval)
    assert response.status_code == 200, response.text
    ready = client.get(url + "/export-readiness").json()
    exported = client.post(url + "/export", params={
        "expected_revision_id": ready["revision_id"], "expected_approval_id": ready["approval_id"],
    })
    assert exported.status_code == 200, exported.text
    receipt = exported.json()["exports"]
    digest = receipt["pdf_sha256"]
    downloaded = client.get(url + "/exports/pdf", params={"sha256": digest})
    assert downloaded.status_code == 200
    assert sha256(downloaded.content).hexdigest() == digest
    with pymupdf.open(stream=downloaded.content, filetype="pdf") as document:
        text = "".join("".join(page.get_text().split()) for page in document)
    return receipt, downloaded.content, text


@pytest.mark.parametrize("certainty,label", [("documented", "医生记录"), ("under_consideration", "待排")])
def test_doctor_entry_is_separate_from_ai_and_binds_pdf_and_hash(doctor_case, certainty, label):
    client, task_id, doctor = doctor_case
    original = client.get(f"/api/tasks/{task_id}").json()["result_json"]
    old = review_payload(client, task_id)
    r1 = dict(get_record_revision(old["expected_revision_id"]))
    assert "clinician_assessment" not in original
    old_receipt, old_pdf_bytes, old_text = signed_pdf(client, task_id)
    first_export_event = dict(list_export_events_for_task(task_id)[0])
    assert "本次医生评估" not in old_text

    statement = "本次记录局部皮肤表现，复诊时核对变化。"
    result = save(client, task_id, clinician_assessment={"statement": statement, "certainty": certainty})
    entry = result["clinician_assessment"]
    assert (entry["statement"], entry["certainty"]) == (statement, certainty)
    assert (entry["recorded_by"], entry["recorder_name"]) == (doctor["id"], doctor["display_name"])
    assert datetime.fromisoformat(entry["recorded_at"]).tzinfo is not None
    assert "clinician_assessment" not in result["fields"]
    assert [item["name"] for item in result["fields"]["candidate_diagnoses"]] == [
        item["name"] for item in original["fields"]["candidate_diagnoses"]
    ]
    assert record_content_hash(result) != record_content_hash({
        key: value for key, value in result.items() if key != "clinician_assessment"
    })
    latest = review_payload(client, task_id)
    assert latest["expected_content_hash"] == record_content_hash(result)
    assert latest["expected_content_hash"] != old["expected_content_hash"]
    assert client.post(f"/api/tasks/{task_id}/export").status_code == 400
    new_receipt, _, new_text = signed_pdf(client, task_id)
    assert new_receipt["pdf_sha256"] != old_receipt["pdf_sha256"]
    assert "本次医生评估（手录）" in new_text
    assert f"{label}：{statement}" in new_text
    assert doctor["display_name"] in new_text and "系统候选诊断" in new_text
    # The download route serves the active approval. Earlier signed artifacts
    # remain bound to their own immutable receipt and original file.
    assert Path(old_receipt["pdf_path"]).read_bytes() == old_pdf_bytes
    assert first_export_event in [dict(row) for row in list_export_events_for_task(task_id)]
    assert dict(get_record_revision(old["expected_revision_id"])) == r1


def test_omission_keeps_origin_and_explicit_null_removes_only_new_revision(doctor_case):
    client, task_id, _ = doctor_case
    first = save(client, task_id, clinician_assessment={"statement": "保留此前表述。", "certainty": "documented"})
    entry = first["clinician_assessment"]
    payload = review_payload(client, task_id)
    revised_id = payload["expected_revision_id"]
    revised_snapshot = dict(get_record_revision(revised_id))
    # Simulate an older client editing another field, without knowing this new object.
    payload["fields"]["treatment_notes"].update(value="记录已核对。", missing=False, status="complete")
    saved = client.post(f"/api/tasks/{task_id}/review", json=payload)
    assert saved.status_code == 200, saved.text
    assert saved.json()["result_json"]["clinician_assessment"] == entry
    assert saved.json()["result_json"]["fields"]["treatment_notes"]["value"] == "记录已核对。"
    cleared = save(client, task_id, clinician_assessment=None)
    assert cleared.get("clinician_assessment") is None
    assert cleared["fields"]["treatment_notes"]["value"] == "记录已核对。"
    assert dict(get_record_revision(revised_id)) == revised_snapshot


def test_untrusted_origin_and_stale_clear_cannot_replace_record(doctor_case):
    client, task_id, _ = doctor_case
    url = f"/api/tasks/{task_id}/review"
    stale = review_payload(client, task_id)
    entry = {"statement": "保留待核原话。", "certainty": "under_consideration"}
    for invalid in ({**entry, "recorded_by": 999}, {**entry, "recorder_name": "代录人"},
                    {**entry, "recorded_at": "2001-01-01"}, {**entry, "certainty": "confirmed"},
                    {**entry, "statement": "  "}):
        response = client.post(url, json={**stale, "clinician_assessment": invalid})
        assert response.status_code == 422, response.text
    assert review_payload(client, task_id) == stale
    current = save(client, task_id, clinician_assessment=entry)["clinician_assessment"]
    latest = review_payload(client, task_id)
    for body in (stale, {**latest, "expected_content_hash": stale["expected_content_hash"]}):
        blocked = client.post(url, json={**body, "clinician_assessment": None})
        assert blocked.status_code == 409, blocked.text
    assert review_payload(client, task_id) == latest
    assert client.get(url.removesuffix("/review")).json()["result_json"]["clinician_assessment"] == current
    assert not list_approvals_for_task(task_id) and not list_export_events_for_task(task_id)


def test_only_assigned_doctor_can_change_or_clear_entry(doctor_case):
    client, task_id, owner = doctor_case
    entry = {"statement": "本次明确记录。", "certainty": "documented"}
    stored = save(client, task_id, clinician_assessment=entry)["clinician_assessment"]
    payload = review_payload(client, task_id)
    create_user(client, username="assessment-other")
    for user in ("assessment-other", "admin"):
        if user == "admin":
            login_as_admin(client)
        else:
            login_as_user(client, username=user)
        for value in ({"statement": "另一个表述。", "certainty": "documented"}, None):
            denied = client.post(f"/api/tasks/{task_id}/review", json={**payload, "clinician_assessment": value})
            assert denied.status_code == 403, denied.text
    login_as_user(client, username=owner["username"])
    assert review_payload(client, task_id) == payload
    assert client.get(f"/api/tasks/{task_id}").json()["result_json"]["clinician_assessment"] == stored
