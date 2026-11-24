from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path
from threading import Event
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api import audio, tasks
from app.db import list_approvals_for_task, list_export_events_for_task
from app.main import app
from app.schemas.asr import ASRResult, ASRSegment, AudioRecord, SpeakerRoleAssignment
from app.services.asr.role_quality import attach_speaker_role_quality
from app.services.asr.signoff_source import bound_recording, signoff_source_issue
from tests.approval_helpers import approval_payload_for_fields, review_payload_for_fields
from tests.auth_helpers import create_user, login_as_user


@pytest.fixture
def recording(tmp_path, monkeypatch):
    for key, value in {"MEDICAL_RECORD_AGENT_DB": tmp_path / "db.sqlite",
                       "MEDICAL_RECORD_AGENT_UPLOAD_DIR": tmp_path / "uploads",
                       "MEDICAL_RECORD_AGENT_OUTPUT_DIR": tmp_path / "exports",
                       "LLM_PROVIDER": "mock", "RECORD_PROVIDER_MODE": "demo"}.items():
        monkeypatch.setenv(key, str(value))
    with TestClient(app) as client:
        user = create_user(client, username="synthetic-signoff")
        login_as_user(client, username="synthetic-signoff")
        aid = uuid4().hex
        raw = ASRResult(audio_id=aid, engine="mock", text="我发热两天。", conversation_text="[患者] 我发热两天。",
            segments=[ASRSegment(speaker_id="A", role="患者", text="我发热两天。", reviewed_by_doctor=True)],
            speaker_assignments=[SpeakerRoleAssignment(speaker_id="A", role="患者", source="manual_speaker_map")])
        raw = attach_speaker_role_quality(raw)
        assert raw.role_quality.status == "passed"
        audio._write_audio_record(AudioRecord(audio_id=aid, filename="example.wav", path="example.wav",
                                              owner_user_id=user["id"]))
        audio._write_transcript(raw)
        response = client.post(f"/api/audio/{aid}/generate-record")
        assert response.status_code == 200, response.text
        tid = response.json()["task_id"]
        yield client, raw, tid, f"/api/tasks/{tid}"


def approval(client, path, tid):
    fields = client.get(path).json()["result_json"]["fields"]
    body = approval_payload_for_fields(fields, task_id=tid)
    body["fields"] = [item for item in body["fields"] if not fields[item["key"]].get("value")]
    return client.post(path + "/approve", json=body)


def withdraw(raw):
    pending = raw.model_copy(deep=True)
    pending.segments[0].role = "待确认"
    pending.segments[0].reviewed_by_doctor = False
    pending.speaker_assignments[0].role = None
    pending.speaker_assignments[0].requires_confirmation = True
    audio._write_transcript(attach_speaker_role_quality(pending))


def test_old_task_review_is_editable_but_must_match_the_current_recording(recording):
    client, raw, tid, path = recording
    withdraw(raw)
    fields = client.get(path).json()["result_json"]["fields"]
    assert client.post(path + "/review", json=review_payload_for_fields(tid, fields)).is_success
    denied = approval(client, path, tid)
    assert denied.status_code == 409 and denied.json()["detail"]["reason_code"] == "audio_role_review_required"
    changed = raw.model_copy(deep=True)
    changed.segments[0].role = changed.speaker_assignments[0].role = "医生"
    changed.conversation_text = "[医生] 我发热两天。"
    audio._write_transcript(attach_speaker_role_quality(changed))
    assert approval(client, path, tid).json()["detail"]["reason_code"] == "audio_source_changed"
    audio._transcript_path(raw.audio_id).unlink()
    assert approval(client, path, tid).json()["detail"]["reason_code"] == "audio_source_unavailable"
    audio._transcript_path(raw.audio_id).write_text("{", encoding="utf-8")
    assert approval(client, path, tid).json()["detail"]["reason_code"] == "audio_source_unavailable"
    assert not list_approvals_for_task(tid)
    audio._write_transcript(raw)
    assert approval(client, path, tid).status_code == 200


def test_preexisting_pdf_can_be_retrieved_but_no_new_file_can_be_issued(recording):
    client, raw, tid, path = recording
    assert approval(client, path, tid).is_success
    withdraw(raw)
    assert not client.get(path + "/export-readiness").json()["ready"]
    assert client.post(path + "/export").json()["detail"]["reason_code"] == "audio_role_review_required"
    audio._write_transcript(raw)
    receipt = client.post(path + "/export").json()["exports"]
    digest = receipt["pdf_sha256"]
    withdraw(raw)
    ready = client.get(path + "/export-readiness").json()
    assert ready["ready"] and not ready["can_create_export"]
    assert ready["audio_source_issue"]["reason_code"] == "audio_role_review_required"
    assert not client.post(path + "/export").is_success
    old = client.get(path + "/exports/pdf", params={"sha256": digest})
    assert old.is_success and sha256(old.content).hexdigest() == digest
    assert len(list_export_events_for_task(tid)) == 1


def test_signoff_and_render_commit_honor_concurrent_source_writes(recording, monkeypatch):
    client, raw, tid, path = recording
    with audio._transcript_lock(raw.audio_id):
        response = approval(client, path, tid)
        assert response.status_code == 409 and response.json()["detail"]["reason_code"] == "asr_review_in_progress"
    assert not list_approvals_for_task(tid)
    assert approval(client, path, tid).is_success
    original_render = tasks.export_record
    documents = []

    def change_during_render(*args, **kwargs):
        receipt = original_render(*args, **kwargs)
        documents.append(Path(receipt["pdf_path"]))
        withdraw(raw)
        return receipt

    monkeypatch.setattr(tasks, "export_record", change_during_render)
    response = client.post(path + "/export")
    assert response.status_code == 409 and response.json()["detail"]["reason_code"] == "audio_role_review_required"
    assert len(documents) == 1 and not documents[0].exists()
    assert not list_export_events_for_task(tid)


def test_historical_segment_shape_and_unbound_text(recording):
    _client, raw, _tid, _path = recording
    for source in (None, {}, {"segments": []}, {"audio_id": "text-import", "segments": []}):
        assert bound_recording({"asr_source": source}) is None
    old = {"audio_id": raw.audio_id, "segments": [{"speaker": "A", "role": "患者", "text": "我发热两天。"}]}
    assert signoff_source_issue(old, raw) is None
    assert signoff_source_issue({"audio_id": raw.audio_id}, raw)["reason_code"] == "audio_source_unavailable"
    old["segments"][0]["text"] = "另一句。"
    assert signoff_source_issue(old, raw)["reason_code"] == "audio_source_changed"
    raw.speaker_assignments[0].source = "manual_draft"
    raw.speaker_assignments[0].requires_confirmation = True
    assert signoff_source_issue(old, raw)["reason_code"] == "audio_role_review_required"


def test_overlapping_approvals_and_withdrawal_cannot_commit_under_one_another(recording, monkeypatch):
    client, raw, tid, path = recording
    entered, finish = Event(), Event()
    commit = tasks.create_approval_for_task

    def paused_commit(*args, **kwargs):
        entered.set()
        assert finish.wait(6)
        return commit(*args, **kwargs)

    monkeypatch.setattr(tasks, "create_approval_for_task", paused_commit)
    with ThreadPoolExecutor(max_workers=1) as worker:
        first = worker.submit(approval, client, path, tid)
        try:
            assert entered.wait(5)
            other = approval(client, path, tid)
            assert other.status_code == 409 and other.json()["detail"]["reason_code"] == "asr_review_in_progress"
            with pytest.raises(HTTPException) as collision:
                withdraw(raw)
            assert collision.value.detail["reason_code"] == "asr_review_in_progress"
        finally:
            finish.set()
        assert first.result().is_success
    assert len(list_approvals_for_task(tid)) == 1
    withdraw(raw)
    assert not client.post(path + "/export").is_success
