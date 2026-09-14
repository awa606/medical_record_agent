from __future__ import annotations

import io
import os
import tempfile
import unittest
import wave
from contextlib import closing
from pathlib import Path

from fastapi.testclient import TestClient

from app.api.asr_sessions import create_asr_session
from app.api.audio import _write_transcript, upload_audio
from app.db import (
    create_encounter,
    create_task,
    get_connection,
    get_encounter,
    set_task_owner,
)
from app.main import app
from app.schemas import ASRResult, ASRSegment, AudioRecord
from tests.auth_helpers import create_user, login_as_admin, login_as_user


def _wav_bytes() -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(16000)
        writer.writeframes((0).to_bytes(2, "little", signed=True) * 1600)
    return output.getvalue()


class FakeUploadFile:
    filename = "sample.wav"
    content_type = "audio/wav"

    def __init__(self, content: bytes):
        self.file = tempfile.SpooledTemporaryFile()
        self.file.write(content)
        self.file.seek(0)


class LocalPatientEncounterIsolationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_env = {
            key: os.environ.get(key)
            for key in [
                "MEDICAL_RECORD_AGENT_DB",
                "MEDICAL_RECORD_AGENT_UPLOAD_DIR",
                "MEDICAL_RECORD_AGENT_OUTPUT_DIR",
                "LLM_PROVIDER",
                "RECORD_PROVIDER_MODE",
                "ONLINE_LLM_API_BASE",
                "ONLINE_LLM_API_KEY",
                "ONLINE_LLM_MODEL",
                "OLLAMA_BASE_URL",
                "OLLAMA_MODEL",
            ]
        }
        for key in [
            "LLM_PROVIDER",
            "RECORD_PROVIDER_MODE",
            "ONLINE_LLM_API_BASE",
            "ONLINE_LLM_API_KEY",
            "ONLINE_LLM_MODEL",
            "OLLAMA_BASE_URL",
            "OLLAMA_MODEL",
        ]:
            os.environ.pop(key, None)
        os.environ["MEDICAL_RECORD_AGENT_DB"] = os.path.join(self.temp_dir.name, "isolation.sqlite3")
        os.environ["MEDICAL_RECORD_AGENT_UPLOAD_DIR"] = os.path.join(self.temp_dir.name, "uploads")
        os.environ["MEDICAL_RECORD_AGENT_OUTPUT_DIR"] = os.path.join(self.temp_dir.name, "outputs")

    def tearDown(self):
        for key, value in self.original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.temp_dir.cleanup()

    def test_local_registration_uses_session_doctor_and_check_in_actions(self):
        client = TestClient(app)
        doctor_a = create_user(client, username="enc-doctor-a")
        doctor_b = create_user(client, username="enc-doctor-b")
        login_as_user(client, username="enc-doctor-a")

        created = client.post(
            "/api/encounters",
            json={
                "patient_deidentified_id": "P-LOCAL-001",
                "patient_display_name": "Local Patient",
                "doctor_id": doctor_b["id"],
            },
        )
        self.assertEqual(created.status_code, 200, created.text)
        encounter = created.json()
        self.assertEqual(encounter["doctor_user_id"], doctor_a["id"])
        self.assertEqual(encounter["check_in_status"], "registered")

        blocked_generation = client.post(
            "/api/records/generate",
            json={"conversation_text": "patient has fever", "encounter_id": encounter["id"]},
        )
        self.assertEqual(blocked_generation.status_code, 409)

        checked_in = client.post(f"/api/encounters/{encounter['id']}/check-in")
        self.assertEqual(checked_in.status_code, 200, checked_in.text)
        self.assertEqual(checked_in.json()["check_in_status"], "checked_in")
        repeated_check_in = client.post(f"/api/encounters/{encounter['id']}/check-in")
        self.assertEqual(repeated_check_in.status_code, 200)

        started = client.post(f"/api/encounters/{encounter['id']}/start")
        self.assertEqual(started.status_code, 200, started.text)
        self.assertEqual(started.json()["check_in_status"], "in_progress")
        repeated_start = client.post(f"/api/encounters/{encounter['id']}/start")
        self.assertEqual(repeated_start.status_code, 200)
        self.assertEqual(client.post(f"/api/encounters/{encounter['id']}/cancel").status_code, 409)

        generated = client.post(
            "/api/records/generate",
            json={"conversation_text": "patient has fever for three days", "encounter_id": encounter["id"]},
        )
        self.assertEqual(generated.status_code, 200, generated.text)
        task_id = generated.json()["task_id"]
        detail = client.get(f"/api/encounters/{encounter['id']}")
        self.assertEqual(detail.json()["task"]["id"], task_id)
        self.assertEqual(detail.json()["check_in_status"], "in_progress")

        client.post("/api/auth/logout")
        login_as_user(client, username="enc-doctor-b")
        self.assertEqual(client.get(f"/api/encounters/{encounter['id']}").status_code, 403)
        self.assertEqual(client.get("/api/encounters?mine=true").json()["encounters"], [])

        client.post("/api/auth/logout")
        login_as_admin(client)
        admin_detail = client.get(f"/api/encounters/{encounter['id']}")
        self.assertEqual(admin_detail.status_code, 200)

    def test_other_doctor_cannot_access_task_routes_for_owned_encounter(self):
        client = TestClient(app)
        create_user(client, username="task-owner-a")
        create_user(client, username="task-owner-b")
        login_as_user(client, username="task-owner-a")
        encounter = client.post(
            "/api/encounters",
            json={"patient_deidentified_id": "P-TASK-001", "patient_display_name": "Task Patient"},
        ).json()
        client.post(f"/api/encounters/{encounter['id']}/check-in")
        generated = client.post(
            "/api/records/generate",
            json={"conversation_text": "patient has fever for three days", "encounter_id": encounter["id"]},
        )
        self.assertEqual(generated.status_code, 200, generated.text)
        task_id = generated.json()["task_id"]
        task_payload = client.get(f"/api/tasks/{task_id}").json()
        fields = task_payload["result_json"]["fields"]
        client.post("/api/auth/logout")

        login_as_user(client, username="task-owner-b")
        self.assertEqual(client.get(f"/api/tasks/{task_id}").status_code, 403)
        self.assertEqual(client.get(f"/api/tasks/{task_id}/steps").status_code, 403)
        self.assertEqual(client.get(f"/api/tasks/{task_id}/trace").status_code, 403)
        self.assertEqual(client.get(f"/api/tasks/{task_id}/events").status_code, 403)
        self.assertEqual(client.get(f"/api/tasks/{task_id}/export-readiness").status_code, 403)
        self.assertEqual(
            client.post(f"/api/tasks/{task_id}/review", json={"fields": fields}).status_code,
            403,
        )
        self.assertEqual(
            client.post(
                f"/api/tasks/{task_id}/approve",
                json={"revision_id": 1, "content_hash": "stale"},
            ).status_code,
            403,
        )
        self.assertEqual(client.post(f"/api/tasks/{task_id}/export").status_code, 403)
        self.assertEqual(client.get(f"/api/tasks/{task_id}/exports/docx").status_code, 403)

    def test_task_encounter_integrity_conflict_blocks_high_risk_even_for_admin(self):
        client = TestClient(app)
        doctor_a = create_user(client, username="integrity-a")
        doctor_b = create_user(client, username="integrity-b")
        task_id = create_task("text", "CREATED", input_text="seed")
        set_task_owner(task_id, doctor_a["id"])
        encounter = create_encounter(
            doctor_user_id=doctor_b["id"],
            deidentified_id="P-INTEGRITY",
            display_name="Integrity Patient",
            check_in_status="in_progress",
        )
        with closing(get_connection()) as connection:
            connection.execute(
                "UPDATE agent_task SET encounter_id = ? WHERE id = ?",
                (encounter["id"], task_id),
            )
            connection.execute(
                "UPDATE encounter SET task_id = ? WHERE id = ?",
                (task_id, encounter["id"]),
            )
            connection.commit()

        login_as_admin(client)
        self.assertEqual(client.get(f"/api/tasks/{task_id}").status_code, 200)
        self.assertEqual(client.get(f"/api/tasks/{task_id}/export-readiness").status_code, 409)
        self.assertEqual(client.post(f"/api/tasks/{task_id}/export").status_code, 409)

    def test_audio_transcript_and_generation_routes_enforce_owner(self):
        client = TestClient(app)
        create_user(client, username="audio-owner-a")
        create_user(client, username="audio-owner-b")
        login_as_user(client, username="audio-owner-a")
        upload = client.post(
            "/api/audio/upload",
            files={"file": ("owner-a.wav", _wav_bytes(), "audio/wav")},
        )
        self.assertEqual(upload.status_code, 200, upload.text)
        audio_id = upload.json()["audio_id"]
        _write_transcript(
            ASRResult(
                audio_id=audio_id,
                engine="mock",
                text="patient has fever",
                conversation_text="[患者] patient has fever",
                segments=[ASRSegment(role="患者", speaker="spk1", text="patient has fever")],
            )
        )
        client.post("/api/auth/logout")

        login_as_user(client, username="audio-owner-b")
        self.assertEqual(client.get(f"/api/audio/{audio_id}").status_code, 403)
        self.assertEqual(client.get(f"/api/audio/{audio_id}/media").status_code, 403)
        self.assertEqual(client.get(f"/api/audio/{audio_id}/transcript").status_code, 403)
        self.assertEqual(client.post(f"/api/audio/{audio_id}/transcribe?engine=mock").status_code, 403)
        self.assertEqual(
            client.post(
                f"/api/audio/{audio_id}/evaluate",
                json={"ground_truth_text": "patient has fever"},
            ).status_code,
            403,
        )
        self.assertEqual(client.post(f"/api/audio/{audio_id}/generate-record").status_code, 403)

    def test_legacy_null_owner_resources_are_doctor_forbidden_admin_readable(self):
        client = TestClient(app)
        create_user(client, username="legacy-doctor")

        encounter = create_encounter(
            doctor_user_id=None,
            deidentified_id="P-LEGACY-NULL",
            display_name="Legacy Patient",
            check_in_status="checked_in",
        )
        task_id = create_task("text", "CREATED", input_text="legacy")
        audio = upload_audio(FakeUploadFile(_wav_bytes()))
        session = create_asr_session(engine="mock")

        login_as_user(client, username="legacy-doctor")
        self.assertEqual(client.get(f"/api/encounters/{encounter['id']}").status_code, 403)
        self.assertEqual(client.get(f"/api/tasks/{task_id}").status_code, 403)
        self.assertEqual(client.get(f"/api/audio/{audio.audio_id}").status_code, 403)
        self.assertEqual(client.get(f"/api/asr/sessions/{session.session_id}").status_code, 403)
        self.assertEqual(client.get(f"/api/asr/sessions/{session.session_id}/chunks/status").status_code, 403)
        client.post("/api/auth/logout")

        login_as_admin(client)
        self.assertEqual(client.get(f"/api/encounters/{encounter['id']}").status_code, 200)
        self.assertEqual(client.get(f"/api/tasks/{task_id}").status_code, 200)
        self.assertEqual(client.get(f"/api/audio/{audio.audio_id}").status_code, 200)
        self.assertEqual(client.get(f"/api/asr/sessions/{session.session_id}").status_code, 200)
        self.assertEqual(client.get(f"/api/asr/sessions/{session.session_id}/chunks/status").status_code, 200)


if __name__ == "__main__":
    unittest.main()
