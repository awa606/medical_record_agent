"""Real saved role review paths on a synthetic transcript with conflicting identities."""
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api import asr_sessions, audio
from app.main import app
from app.schemas.asr import ASRResult, ASRSegment, ASRSessionRecord, AudioRecord, SpeakerRoleAssignment
from app.services.asr.role_quality import MANUAL_ROLE_CONFLICT, attach_speaker_role_quality, build_speaker_role_quality
from tests.auth_helpers import create_user


@pytest.fixture()
def review(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDICAL_RECORD_AGENT_DB", str(tmp_path / "trial.sqlite3"))
    monkeypatch.setenv("MEDICAL_RECORD_AGENT_UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setattr(audio, "ensure_record_provider_available", lambda: None)
    generated = []
    monkeypatch.setattr(audio, "run_record_generation_task", lambda *args: generated.append(args[0]))
    with TestClient(app) as client:
        owner = create_user(client, username="example-doctor")
        assert client.post("/api/auth/login", json={"username": "example-doctor", "password": "doctor-pass-123"}).is_success
        uid = uuid4().hex
        asr_sessions._write_session(ASRSessionRecord(session_id=uid, audio_id=uid, engine="mock",
                                                      status="completed", owner_user_id=owner["id"]))
        audio._write_audio_record(AudioRecord(audio_id=uid, filename="synthetic.wav", path="synthetic.wav",
                                              owner_user_id=owner["id"]))
        result = ASRResult(audio_id=uid, engine="mock", text="合成问诊", conversation_text="合成问诊",
            segments=[
                ASRSegment(segment_id="a", speaker_id="A", text="我来复查。", role="患者"),
                ASRSegment(segment_id="b", speaker_id="B", text="资料是我的。", role="陪同人员",
                           reviewed_by_doctor=True, role_source="manual"),
                ASRSegment(segment_id="c", speaker_id="B", text="我核对记录。", role="医生",
                           reviewed_by_doctor=True, role_source="manual"),
            ], speaker_assignments=[
                SpeakerRoleAssignment(speaker_id="A", role="患者", source="manual_speaker_map"),
                SpeakerRoleAssignment(speaker_id="B", role="陪同人员", source="manual_speaker_map"),
            ])
        # Reproduce a legacy, internally consistent-looking cached pass on the conflicting rows.
        clean = result.model_copy(deep=True)
        clean.segments[2].role = "陪同人员"
        result.role_quality = build_speaker_role_quality(clean)
        assert result.role_quality.status == "passed"
        asr_sessions._write_session_result(uid, result)
        audio._write_transcript(result)
        yield client, f"/api/asr/sessions/{uid}", f"/api/audio/{uid}", result, generated


def test_legacy_reads_and_bulk_save_do_not_overwrite_verified_segment(review):
    client, session, recording, original, generated = review
    for url in (session + "/result", recording + "/transcript"):
        saved = client.get(url).json()
        assert saved["needs_review"]
        assert saved["role_quality"]["pending_confirmation"][0]["reason_code"] == MANUAL_ROLE_CONFLICT
    blocked = client.post(recording + "/generate-record")
    assert blocked.status_code == 409 and blocked.json()["detail"]["reason_code"] == MANUAL_ROLE_CONFLICT
    assert not generated
    payload = {"speaker_roles": [{"speaker_id": "B", "role": "陪同人员"}],
               "segments": [{"index": 2, "role": "陪同人员", "text": "整组回填的不同正文。"}]}
    for _ in range(2):
        response = client.patch(session + "/result", json=payload)
        assert response.is_success
        saved = response.json()["asr_result"]
        assert saved["segments"][2] == original.segments[2].model_dump(mode="json")
        assert saved["role_quality"]["status"] == "needs_review"
        assert client.get(recording + "/transcript").json()["segments"][2] == saved["segments"][2]
        assert client.post(recording + "/generate-record").status_code == 409
    assert not generated
    # The clinician can expressly change a single verified row without remapping its entire group.
    single = client.patch(session + "/result", json={"segments": [{"index": 2, "role": "陪同人员"}]})
    assert single.json()["asr_result"]["role_quality"]["status"] == "passed"
    assert client.post(recording + "/generate-record").is_success
    assert len(generated) == 1


def test_unreviewed_group_maps_normally_and_can_be_changed_again(review):
    client, session, recording, raw, _ = review
    for row in raw.segments:
        row.reviewed_by_doctor = False
        row.role_source = "speaker_context_rules"
    asr_sessions._write_session_result(raw.audio_id, raw)
    for role in ("陪同人员", "医生"):
        payload = {"speaker_roles": [{"speaker_id": "B", "role": role}],
                   "segments": [{"index": i, "role": role} for i in (1, 2)]}
        saved = client.patch(session + "/result", json=payload).json()["asr_result"]
        assert saved["role_quality"]["status"] == "passed"
        for row in saved["segments"][1:]:
            assert row["role"] == role and row["role_source"] == "manual_speaker_map"
        assert saved["segments"] == client.get(recording + "/transcript").json()["segments"]


def test_legacy_individual_role_survives_group_change_and_uncheck(review):
    client, session, recording, raw, _ = review
    raw.segments.pop(1)
    raw.segments[1].role_source = None
    asr_sessions._write_session_result(raw.audio_id, raw)
    payload = {"speaker_roles": [{"speaker_id": "B", "role": "患者"}],
               "segments": [{"index": 1, "reviewed_by_doctor": False}]}
    saved = client.patch(session + "/result", json=payload).json()["asr_result"]
    assert saved["segments"][1] == raw.segments[1].model_dump(mode="json")
    assert saved["role_quality"]["pending_confirmation"][0]["reason_code"] == MANUAL_ROLE_CONFLICT
    blocked = client.post(recording + "/generate-record")
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["reason_code"] == MANUAL_ROLE_CONFLICT


def test_stricter_legacy_block_and_provisional_rows(review):
    client, session, recording, raw, _ = review
    raw.role_quality.status = "blocked"
    raw.role_quality.reasons = ["原有阻断"]
    audio._write_transcript(raw)
    quality = client.get(recording + "/transcript").json()["role_quality"]
    assert quality["status"] == "blocked" and "原有阻断" in quality["reasons"]
    raw.segments[2].provisional = True
    assert attach_speaker_role_quality(raw).role_quality.status == "passed"


def test_concurrent_group_save_and_merge_require_a_fresh_retry(review):
    client, session, recording, original, _ = review
    with asr_sessions._review_result_write(asr_sessions._result_path(original.audio_id)):
        for response in (
            client.patch(session + "/result", json={"speaker_roles": [{"speaker_id": "B", "role": "患者"}]}),
            client.post(session + "/speakers/merge", json={"source_speaker": "B", "target_speaker": "A"}),
        ):
            assert response.status_code == 409 and response.json()["detail"]["reason_code"] == "asr_review_in_progress"
    merged = client.post(session + "/speakers/merge", json={"source_speaker": "B", "target_speaker": "A"})
    assert merged.is_success
    saved = client.get(recording + "/transcript").json()
    assert [s["role"] for s in saved["segments"][1:]] == ["陪同人员", "医生"]
    assert saved["role_quality"]["status"] != "passed"


def test_generation_never_writes_a_stale_snapshot_over_a_new_review(review, monkeypatch):
    client, session, recording, raw, _ = review
    intervening = raw.model_copy(deep=True)
    raw.segments[2].role = "陪同人员"
    audio._write_transcript(attach_speaker_role_quality(raw))
    original_gate = audio._require_passed_role_quality

    def committed_during_generation(snapshot):
        checked = original_gate(snapshot)
        audio._write_transcript(attach_speaker_role_quality(intervening))
        return checked

    monkeypatch.setattr(audio, "_require_passed_role_quality", committed_during_generation)
    assert client.post(recording + "/generate-record").is_success
    latest = client.get(recording + "/transcript").json()
    assert latest["segments"][2]["role"] == "医生"
    assert latest["role_quality"]["status"] == "needs_review"
