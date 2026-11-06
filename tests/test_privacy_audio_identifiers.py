"""ASR routing metadata must survive privacy filtering; clinical prose must not."""
from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient

from app.services.privacy import AnonymousResponses, anonymize_payload, register_identity


# UUID from an anonymous acceptance upload, not a personal identity number.
# Its 18-digit run previously matched the identity regex inside the UUID.
AUDIO_ID = "253b9c625940408081798193e500f717"
NUMERIC_RUN = "625940408081798193"
PHONE = "13800130000"
ID_KEYS = ("audio_id", "session_id", "live_session_id")
URLS = {
    "media_url": f"/api/audio/{AUDIO_ID}/media",
    "events_url": f"/api/asr/sessions/{AUDIO_ID}/events",
    "result_url": f"/api/asr/sessions/{AUDIO_ID}/result",
}


@pytest.fixture
def anonymous_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("MRA_ANONYMIZE", "1")
    monkeypatch.setenv("MEDICAL_RECORD_AGENT_DB", str(tmp_path / "privacy.sqlite3"))
    monkeypatch.setenv("MEDICAL_RECORD_AGENT_UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("MEDICAL_RECORD_AGENT_OUTPUT_DIR", str(tmp_path / "outputs"))
    monkeypatch.setenv("RECORD_PROVIDER_MODE", "demo")
    monkeypatch.setenv("ASR_PREWARM_ENABLED", "0")
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    return tmp_path


@pytest.mark.parametrize("preexisting_mapping", [False, True])
def test_json_and_chunked_sse_keep_exact_asr_metadata(anonymous_environment, preexisting_mapping):
    if preexisting_mapping:
        register_identity(NUMERIC_RUN, "身份证")
    payload = {
        **dict.fromkeys(ID_KEYS, AUDIO_ID),
        **URLS,
        "asr_result": {"audio_id": AUDIO_ID, "segments": [{"text": f"联系电话{PHONE}"}]},
        "conversation_text": f"患者身份证{NUMERIC_RUN}，联系电话{PHONE}",
    }
    app = FastAPI()
    app.add_middleware(AnonymousResponses)

    @app.get("/result")
    def result():
        return payload

    @app.get("/events")
    def events():
        async def parts():
            frame = ("event: reviewed\ndata: " + json.dumps(payload, ensure_ascii=False) + "\n\n").encode()
            for start in range(0, len(frame), 7):
                yield frame[start:start + 7]
        return StreamingResponse(parts(), media_type="text/event-stream")

    with TestClient(app) as client:
        result = client.get("/result")
        assert result.status_code == 200
        stream = client.get("/events")
        assert stream.status_code == 200
    data_line = next(line[6:] for line in stream.text.splitlines() if line.startswith("data: "))
    for result in (result.json(), json.loads(data_line)):
        for key in ID_KEYS:
            assert result[key] == AUDIO_ID
        for key, value in URLS.items():
            assert result[key] == value
        assert result["asr_result"]["audio_id"] == AUDIO_ID
        assert PHONE not in result["asr_result"]["segments"][0]["text"]
        assert NUMERIC_RUN not in result["conversation_text"]
        assert PHONE not in result["conversation_text"]


@pytest.mark.parametrize("key", ID_KEYS)
@pytest.mark.parametrize("invalid", [
    PHONE,
    NUMERIC_RUN,
    "prefix-" + AUDIO_ID,
    AUDIO_ID + "a",
    AUDIO_ID[:-1] + "z",
    AUDIO_ID[:12] + "1" + AUDIO_ID[13:],  # UUID version 1, not the generated v4 contract.
    AUDIO_ID[:16] + "1" + AUDIO_ID[17:],  # Not an RFC 4122 UUID variant.
])
def test_malformed_technical_ids_still_receive_anonymization(anonymous_environment, key, invalid):
    result = anonymize_payload({key: invalid})
    assert result[key] != invalid


@pytest.mark.parametrize("key", ["text", "conversation_text", "patient_name", "id", "request_id"])
def test_uuid_in_unapproved_fields_is_not_a_global_privacy_escape(anonymous_environment, key):
    register_identity(NUMERIC_RUN, "身份证")
    result = anonymize_payload({key: AUDIO_ID})
    assert result[key] != AUDIO_ID
    assert NUMERIC_RUN not in result[key]


@pytest.mark.parametrize("key,route", URLS.items())
@pytest.mark.parametrize("mutation", [
    lambda route: "https://example.invalid" + route,
    lambda route: route + "?contact=" + PHONE,
    lambda route: route + "#" + PHONE,
    lambda route: route + "/" + PHONE,
    lambda route: route.replace("/api/", "/other/"),
    lambda route: route.replace(AUDIO_ID, PHONE),
])
def test_only_exact_local_asr_routes_are_preserved(anonymous_environment, key, route, mutation):
    value = mutation(route)
    register_identity(NUMERIC_RUN, "身份证")
    result = anonymize_payload({key: value})
    assert result[key] != value
    assert PHONE not in result[key]
    assert NUMERIC_RUN not in result[key]


def test_url_in_wrong_metadata_field_is_not_preserved(anonymous_environment):
    register_identity(NUMERIC_RUN, "身份证")
    result = anonymize_payload({"media_url": URLS["events_url"], "source_url": URLS["media_url"]})
    assert result["media_url"] != URLS["events_url"]
    assert result["source_url"] != URLS["media_url"]


def test_role_save_response_roundtrips_to_real_transcript_lookup_without_llm(
    anonymous_environment, monkeypatch,
):
    from app.api import asr_sessions, audio
    from app.db import get_task
    from app.main import app
    from app.schemas import ASRResult, ASRSegment, ASRSessionRecord, AudioRecord
    from tests.auth_helpers import login_as_admin

    register_identity(NUMERIC_RUN, "身份证")
    background_inputs = []
    monkeypatch.setattr(audio, "ensure_record_provider_available", lambda: None)
    monkeypatch.setattr(
        "app.agents.medical_record_orchestrator.create_llm_record_generator", lambda: object(),
    )
    monkeypatch.setattr(
        audio, "run_record_generation_task",
        lambda task_id, text, source: background_inputs.append((task_id, text, source)),
    )
    with TestClient(app) as client:
        admin = login_as_admin(client)
        asr_sessions._write_session(ASRSessionRecord(
            session_id=AUDIO_ID, audio_id=AUDIO_ID, engine="fixture", status="completed",
            owner_user_id=admin["id"],
        ))
        raw = ASRResult(
            audio_id=AUDIO_ID, engine="fixture", text="发热两天。",
            conversation_text="患者：发热两天。",
            segments=[ASRSegment(speaker_id="A", speaker="A", text="发热两天。", role="待确认")],
        )
        asr_sessions._write_session_result(AUDIO_ID, raw)
        audio._write_transcript(raw)
        audio._write_audio_record(AudioRecord(
            audio_id=AUDIO_ID, filename="anonymous-fixture.wav", path="unused-fixture.wav",
            owner_user_id=admin["id"],
        ))
        saved = client.patch(f"/api/asr/sessions/{AUDIO_ID}/result", json={
            "reviewer": "doctor",
            "segments": [{"index": 0, "role": "患者", "reviewed_by_doctor": True}],
            "speaker_roles": [{"speaker_id": "A", "role": "患者", "reviewed_by_doctor": True}],
        })
        assert saved.status_code == 200, saved.text
        assert saved.json()["asr_result"]["role_quality"]["status"] == "passed"
        # Use the actual HTTP response ID, exactly as saveRoleReview does.
        generated = client.post(f"/api/audio/{saved.json()['audio_id']}/generate-record")
        assert generated.status_code == 200, generated.text
        assert saved.json()["audio_id"] == AUDIO_ID
        assert saved.json()["session_id"] == AUDIO_ID
        assert generated.json()["status"] == "CREATED"
        assert len(background_inputs) == 1
        task_id, text, source = background_inputs[0]
        assert task_id == generated.json()["task_id"]
        assert source["audio_id"] == AUDIO_ID
        assert source["segments"][0]["role"] == "患者"
        assert "发热两天" in text
        assert get_task(task_id)["input_text"] == text
        assert audio._read_transcript(AUDIO_ID).audio_id == AUDIO_ID
