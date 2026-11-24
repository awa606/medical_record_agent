import hashlib
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from threading import Barrier
from uuid import uuid4

import pymupdf
import pytest
from fastapi.testclient import TestClient

from app.api import audio
from app.db import get_connection, get_task
from app.db.sqlite import list_record_revisions_for_task, record_content_hash
from app.main import app
from app.schemas.asr import ASRResult, ASRSegment, AudioRecord, SpeakerRoleAssignment
from app.services.asr.role_quality import attach_speaker_role_quality
from app.services.audio_source_revisions import source_digest
from tests.approval_helpers import approval_payload_for_fields, review_payload_for_fields
from tests.auth_helpers import create_user, login_as_user


@pytest.fixture
def visit(tmp_path, monkeypatch):
    for name, value in {
        "MEDICAL_RECORD_AGENT_DB": tmp_path / "source.sqlite",
        "MEDICAL_RECORD_AGENT_UPLOAD_DIR": tmp_path / "uploads",
        "MEDICAL_RECORD_AGENT_OUTPUT_DIR": tmp_path / "outputs",
        "RECORD_PROVIDER_MODE": "demo",
        "LLM_PROVIDER": "mock",
    }.items():
        monkeypatch.setenv(name, str(value))
    with TestClient(app, raise_server_exceptions=False) as client:
        user = create_user(client, username="source-review-doctor")
        create_user(client, username="another-source-doctor")
        login_as_user(client, username="source-review-doctor")
        eid = client.post(
            "/api/encounters",
            json={"patient_deidentified_id": "SYN-SOURCE", "patient_display_name": "合成复核"},
        ).json()["id"]
        for op in ("check-in", "start"):
            assert client.post(f"/api/encounters/{eid}/{op}").is_success
        aid = uuid4().hex
        raw = ASRResult(
            audio_id=aid,
            engine="mock",
            text="右腕疼痛两天。\n检查报告待回。",
            conversation_text="[患者] 右腕疼痛两天。\n[陪同人员] 检查报告待回。",
            segments=[
                ASRSegment(
                    segment_id="a",
                    speaker_id="one",
                    role="患者",
                    text="右腕疼痛两天。",
                    reviewed_by_doctor=True,
                ),
                ASRSegment(
                    segment_id="b",
                    speaker_id="two",
                    role="陪同人员",
                    text="检查报告待回。",
                    reviewed_by_doctor=True,
                ),
            ],
            speaker_assignments=[
                SpeakerRoleAssignment(speaker_id="one", role="患者", source="manual_speaker_map"),
                SpeakerRoleAssignment(speaker_id="two", role="陪同人员", source="manual_speaker_map"),
            ],
        )
        audio._write_audio_record(
            AudioRecord(audio_id=aid, filename="example.wav", path="example.wav", owner_user_id=user["id"])
        )
        audio._write_transcript(attach_speaker_role_quality(raw))
        gen = client.post(f"/api/audio/{aid}/generate-record?encounter_id={eid}")
        assert gen.is_success, gen.text
        tid = gen.json()["task_id"]
        path = f"/api/tasks/{tid}"
        fields = client.get(path).json()["result_json"]["fields"]
        fields["chief_complaint"].update(value="手腕痛两天。", missing=False, status="complete")
        payload = review_payload_for_fields(tid, fields)
        payload["manual_takeover_fields"] = ["chief_complaint"]
        saved = client.post(path + "/review", json=payload)
        assert saved.is_success, saved.text
        latest = raw.model_copy(deep=True)
        latest.segments[1].role = latest.speaker_assignments[1].role = "医生"
        latest.conversation_text = latest.conversation_text.replace("[陪同人员]", "[医生]")
        audio._write_transcript(attach_speaker_role_quality(latest))
        yield client, tid, path, raw, latest


def select(client, path):
    route = path + "/audio-source-revision"
    response = client.get(route)
    assert response.is_success, response.text
    preview = response.json()
    body = {k: preview[k] for k in ("revision_id", "revision_hash", "source_hash")}
    choices = {k: {"action": "history_only"} for k in preview["previous_values"]}
    choices.update(
        chief_complaint={"action": "retain_as_doctor"}, auxiliary_exam={"action": "quote", "segment": 1}
    )
    body.update(request_id=str(uuid4()), reviewed=True, choices=choices)
    return route, body


def approve(client, tid, path):
    fields = client.get(path).json()["result_json"]["fields"]
    body = approval_payload_for_fields(fields, task_id=tid)
    body["fields"] = [x for x in body["fields"] if not fields[x["key"]].get("value")]
    response = client.post(path + "/approve", json=body)
    assert response.is_success, response.text
    return response.json()["result_json"]["approval"]


def test_new_revision_signs_the_reviewed_source_and_retains_old_rows(visit):
    client, tid, path, old, current = visit
    assert client.get(path + "/export-readiness").json()["can_recover_audio_source"]
    route, body = select(client, path)
    previous = list_record_revisions_for_task(tid)
    created = client.post(route, json=body)
    assert created.is_success, created.text
    receipt = created.json()
    assert receipt["revision"]["revision_no"] == 3
    assert client.post(route, json=body).json() == receipt
    assert client.post(route, json=dict(body, choices={})).status_code == 409
    versions = list_record_revisions_for_task(tid)
    assert len(versions) == 3
    assert [r for r in versions if r["id"] in {v["id"] for v in previous}] == previous
    task = client.get(path).json()
    result = task["result_json"]
    proof = result["audio_source_revision"]
    assert task["input_text"] == current.conversation_text
    assert result["fields"]["chief_complaint"]["value"] == "手腕痛两天。"
    assert result["fields"]["auxiliary_exam"]["source_spans"][0]["segment_id"] == "b"
    assert (
        proof["previous_source_sha256"] == source_digest(old.model_dump())
        and proof["source_sha256"] == receipt["source_sha256"]
    )
    assert record_content_hash(result) != record_content_hash(
        dict(result, audio_source_revision=dict(proof, source_sha256="0" * 64))
    )
    with closing(get_connection()) as conn, conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """INSERT INTO approval(encounter_id,revision_id,task_id,approved_by_user_id,
                content_hash,status,created_at,writer_protocol) VALUES(?,?,?,?,?,'active','today',4)""",
                (
                    receipt["encounter_id"],
                    receipt["revision"]["id"],
                    tid,
                    proof["reviewer_user_id"],
                    receipt["revision"]["content_hash"],
                ),
            )
    signed = approve(client, tid, path)
    exported = client.post(path + "/export")
    assert exported.is_success, exported.text
    export = exported.json()["exports"]
    assert signed["source_sha256"] == export["source_sha256"] == receipt["source_sha256"]
    assert signed["content_hash"] == export["content_hash"] == receipt["revision"]["content_hash"]
    downloaded = client.get(path + "/exports/pdf", params={"sha256": export["pdf_sha256"]})
    assert hashlib.sha256(downloaded.content).hexdigest() == export["pdf_sha256"]
    with pymupdf.open(stream=downloaded.content, filetype="pdf") as pdf:
        assert (
            receipt["source_sha256"] in pdf.metadata["subject"]
            and signed["content_hash"] in pdf.metadata["subject"]
        )
    audio._write_transcript(attach_speaker_role_quality(old))
    assert client.get(route).status_code == 409
    assert not client.get(path + "/export-readiness").json()["can_recover_audio_source"]
    assert client.post(route, json=body).json() == receipt
    assert (
        client.get(path + "/exports/pdf", params={"sha256": export["pdf_sha256"]}).content
        == downloaded.content
    )


def test_readonly_selection_scope_and_stale_data(visit):
    client, tid, path, old, current = visit
    before = list_record_revisions_for_task(tid)
    route, body = select(client, path)
    assert client.post(route, json=dict(body, choices={})).status_code == 409
    assert client.post(route, json=dict(body, reviewed=False)).status_code == 422
    assert client.post(route, json=dict(body, source_hash="a" * 64)).status_code == 409
    assert client.post(route, json=dict(body, revision_id=body["revision_id"] + 10)).status_code == 409
    login_as_user(client, username="another-source-doctor")
    assert client.get(route).status_code == client.post(route, json=body).status_code == 403
    login_as_user(client, username="source-review-doctor")
    current.segments[1].segment_id = None
    audio._write_transcript(attach_speaker_role_quality(current))
    assert client.get(route).status_code == client.post(route, json=body).status_code == 409
    assert not client.get(path + "/export-readiness").json()["can_recover_audio_source"]
    assert list_record_revisions_for_task(tid) == before


def test_logged_out_and_unrelated_or_handwritten_sources_do_not_offer_recovery(visit):
    client, tid, path, _old, _current = visit
    route, body = select(client, path)
    assert client.post("/api/auth/logout").is_success
    assert client.get(route).status_code == client.post(route, json=body).status_code == 401
    login_as_user(client, username="source-review-doctor")
    with closing(get_connection()) as conn, conn:
        rid = body["revision_id"]
        frozen = conn.execute("SELECT result_json FROM record_revision WHERE id=?", (rid,)).fetchone()[0]
        handwritten = json.loads(frozen)
        handwritten["clinician_draft_origin"] = {"kind": "doctor_manual_first"}
        conn.execute("UPDATE record_revision SET result_json=? WHERE id=?", (json.dumps(handwritten), rid))
    assert client.get(route).status_code == client.post(route, json=body).status_code == 409
    assert not client.get(path + "/export-readiness").json()["can_recover_audio_source"]
    gen = client.post("/api/records/generate", json={"conversation_text": "患者：我发热两天。"})
    assert gen.is_success
    plain = f"/api/tasks/{gen.json()['task_id']}"
    assert not client.get(plain + "/export-readiness").json()["can_recover_audio_source"]
    assert client.get(plain + "/audio-source-revision").status_code in (403, 409)


def test_existing_assessment_requires_a_decision_and_keeps_the_original_attribution(visit):
    client, tid, path, _old, _current = visit
    fields = client.get(path).json()["result_json"]["fields"]
    request = review_payload_for_fields(tid, fields)
    request["clinician_assessment"] = {
        "certainty": "under_consideration",
        "statement": "本次医生记录的合成评估。",
    }
    saved = client.post(path + "/review", json=request)
    assert saved.is_success, saved.text
    prior = saved.json()["result_json"]["clinician_assessment"]
    route, body = select(client, path)
    del body["choices"]["clinician_assessment"]
    assert client.post(route, json=body).status_code == 409
    body["choices"]["clinician_assessment"] = {"action": "retain_as_doctor"}
    accepted = client.post(route, json=body)
    assert accepted.is_success, accepted.text
    result = client.get(path).json()["result_json"]
    assert result["clinician_assessment"] == prior and prior["statement"] in result["draft"]
    next_revision = client.post(path + "/review", json=review_payload_for_fields(tid, result["fields"]))
    assert next_revision.is_success, next_revision.text
    assert next_revision.json()["result_json"]["audio_source_revision"] == result["audio_source_revision"]


def test_competing_edits_and_interrupted_receipt_are_atomic(visit):
    client, tid, path, old, current = visit
    route, body = select(client, path)
    prior = list_record_revisions_for_task(tid)
    old_task = get_task(tid)
    with closing(get_connection()) as conn, conn:
        conn.execute("""CREATE TRIGGER fail_audio_receipt BEFORE INSERT ON audio_source_revision_request
                        BEGIN SELECT RAISE(ABORT,'test interruption'); END""")
    assert client.post(route, json=body).status_code == 500
    assert list_record_revisions_for_task(tid) == prior and get_task(tid) == old_task
    with closing(get_connection()) as conn, conn:
        conn.execute("DROP TRIGGER fail_audio_receipt")
    barrier = Barrier(2)

    def save(_):
        barrier.wait(timeout=5)
        return client.post(route, json=dict(body, request_id=str(uuid4()))).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(save, [1, 2])) == [200, 409]
    assert len(list_record_revisions_for_task(tid)) == 3
