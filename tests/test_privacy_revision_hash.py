import json

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient

from app.services.privacy import AnonymousResponses, anonymize_payload, register_identity


# Real SHA of a synthetic revision. Its numeric run was mistaken for an ID.
REVISION_HASH = "01d053c7435c55d609bd41e790265729b337ab299891425705163274c47b8baa"


def test_hash_preserved_only_in_validated_technical_fields(tmp_path, monkeypatch):
    monkeypatch.setenv("MRA_ANONYMIZE", "1")
    monkeypatch.setenv("MEDICAL_RECORD_AGENT_DB", str(tmp_path / "privacy.sqlite3"))
    phone = "13800130000"
    register_identity("299891425705163274", "身份证")
    result = anonymize_payload({
        "content_hash": REVISION_HASH,
        "nested": {"content_sha256": REVISION_HASH},
        "patient_name": REVISION_HASH,
        "text": "联系电话" + phone,
        "invalid": {"content_hash": phone},
    })
    assert result["content_hash"] == REVISION_HASH
    assert result["nested"]["content_sha256"] == REVISION_HASH
    assert result["patient_name"] != REVISION_HASH
    assert phone not in result["text"]
    assert phone not in result["invalid"]["content_hash"]


def test_json_and_stream_preserve_hash_but_remove_personal_text(tmp_path, monkeypatch):
    monkeypatch.setenv("MRA_ANONYMIZE", "1")
    monkeypatch.setenv("MEDICAL_RECORD_AGENT_DB", str(tmp_path / "privacy.sqlite3"))
    app = FastAPI()
    app.add_middleware(AnonymousResponses)
    payload = {"content_hash": REVISION_HASH, "text": "联系电话13800130000"}

    @app.get("/json")
    def data():
        return payload

    @app.get("/events")
    def events():
        async def parts():
            frame = ("event: saved\ndata: " + json.dumps(payload) + "\n\n").encode()
            for start in range(0, len(frame), 7):
                yield frame[start:start + 7]
        return StreamingResponse(parts(), media_type="text/event-stream")

    with TestClient(app) as client:
        assert client.get("/json").json()["content_hash"] == REVISION_HASH
        stream = client.get("/events").text
    assert REVISION_HASH in stream
    assert "13800130000" not in stream


def test_readiness_hash_roundtrips_through_approval(tmp_path, monkeypatch):
    from app.agents import MedicalRecordOrchestrator
    from app.db import set_task_owner
    from app.main import app
    from tests.auth_helpers import login_as_admin
    from tests.approval_helpers import approval_payload_for_fields

    monkeypatch.setenv("MEDICAL_RECORD_AGENT_DB", str(tmp_path / "workflow.sqlite3"))
    monkeypatch.setenv("MEDICAL_RECORD_AGENT_OUTPUT_DIR", str(tmp_path / "outputs"))
    monkeypatch.setenv("RECORD_PROVIDER_MODE", "demo")
    monkeypatch.setenv("MRA_ANONYMIZE", "1")
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.setattr("app.db.sqlite.record_content_hash", lambda _result: REVISION_HASH)
    result = MedicalRecordOrchestrator().run_from_text("发热伴咳嗽三天")
    task_id = result["task_id"]
    with TestClient(app) as client:
        admin = login_as_admin(client)
        set_task_owner(task_id, admin["id"])
        response = client.get(f"/api/tasks/{task_id}/export-readiness")
        assert response.status_code == 200, response.text
        ready = response.json()
        payload = approval_payload_for_fields(result["fields"], task_id=task_id)
        fields = client.get(f"/api/tasks/{task_id}").json()["result_json"]["fields"]
        payload["fields"] = [
            {"key": key, "action": "confirm_content" if field.get("value") and not field.get("missing") else "accept_missing"}
            for key, field in fields.items() if isinstance(field, dict) and "missing" in field
        ]
        payload["content_hash"] = ready["content_hash"]
        assert payload["content_hash"] == REVISION_HASH
        response = client.post(f"/api/tasks/{task_id}/approve", json=payload)
        assert response.status_code == 200, response.text
        payload["content_hash"] = "0" * 64
        assert client.post(f"/api/tasks/{task_id}/approve", json=payload).status_code == 409
