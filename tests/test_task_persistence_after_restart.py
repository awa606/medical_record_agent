from __future__ import annotations

import os
import tempfile
import unittest
from copy import deepcopy
from io import BytesIO
from zipfile import ZipFile

from fastapi.testclient import TestClient

from app.db import (
    get_active_approval_for_task,
    get_task,
    get_task_encounter,
    init_db,
    list_export_events_for_task,
    list_record_revisions_for_task,
)
from app.main import app
from app.services import WORD_NOTICE
from tests.auth_helpers import create_user, login_as_user


class TaskPersistenceAfterRestartTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_env = {
            key: os.environ.get(key)
            for key in [
                "MEDICAL_RECORD_AGENT_DB",
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
        os.environ["MEDICAL_RECORD_AGENT_DB"] = os.path.join(
            self.temp_dir.name,
            "restart.sqlite3",
        )
        os.environ["MEDICAL_RECORD_AGENT_OUTPUT_DIR"] = os.path.join(
            self.temp_dir.name,
            "outputs",
        )

    def tearDown(self):
        for key, value in self.original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.temp_dir.cleanup()

    def _create_doctor_and_generate_task(self) -> tuple[int, int]:
        with TestClient(app) as client:
            doctor = create_user(client, username="restart-doctor")
            login_as_user(client, username="restart-doctor")
            generated = client.post(
                "/api/records/generate",
                json={"conversation_text": "patient has fever for three days"},
            )
            self.assertEqual(generated.status_code, 200, generated.text)
            task_id = generated.json()["task_id"]
            encounter = get_task_encounter(task_id)
            self.assertIsNotNone(encounter)
            return task_id, int(doctor["id"])

    def _restart_app_and_login(self) -> TestClient:
        init_db()
        client = TestClient(app)
        login_as_user(client, username="restart-doctor")
        return client

    def test_exported_record_survives_app_restart_and_remains_downloadable(self):
        task_id, doctor_id = self._create_doctor_and_generate_task()

        with TestClient(app) as client:
            login_as_user(client, username="restart-doctor")
            approved = client.post(f"/api/tasks/{task_id}/approve")
            self.assertEqual(approved.status_code, 200, approved.text)
            exported = client.post(f"/api/tasks/{task_id}/export")
            self.assertEqual(exported.status_code, 200, exported.text)
            initial_docx = client.get(f"/api/tasks/{task_id}/exports/docx")
            self.assertEqual(initial_docx.status_code, 200, initial_docx.text)

        restarted_client = self._restart_app_and_login()
        try:
            restored_task = restarted_client.get(f"/api/tasks/{task_id}")
            self.assertEqual(restored_task.status_code, 200, restored_task.text)
            restored_payload = restored_task.json()
            self.assertEqual(restored_payload["current_stage"], "exported")
            self.assertEqual(restored_payload["owner_user_id"], doctor_id)
            self.assertIn("exports", restored_payload["result_json"])

            worklist = restarted_client.get("/api/encounters?mine=true")
            self.assertEqual(worklist.status_code, 200, worklist.text)
            matching = [
                item
                for item in worklist.json()["encounters"]
                if item["task_id"] == task_id
            ]
            self.assertEqual(len(matching), 1)
            self.assertEqual(matching[0]["status"], "exported")

            encounter_detail = restarted_client.get(f"/api/encounters/{matching[0]['id']}")
            self.assertEqual(encounter_detail.status_code, 200, encounter_detail.text)
            detail_payload = encounter_detail.json()
            self.assertEqual(detail_payload["task"]["id"], task_id)
            self.assertGreaterEqual(len(detail_payload["revisions"]), 2)
            self.assertIsNotNone(detail_payload["current_revision"])

            readiness = restarted_client.get(f"/api/tasks/{task_id}/export-readiness")
            self.assertEqual(readiness.status_code, 200, readiness.text)
            self.assertTrue(readiness.json()["ready"])
            self.assertFalse(readiness.json()["blocked"])

            downloaded_docx = restarted_client.get(f"/api/tasks/{task_id}/exports/docx")
            self.assertEqual(downloaded_docx.status_code, 200, downloaded_docx.text)
            with ZipFile(BytesIO(downloaded_docx.content)) as docx:
                document_xml = docx.read("word/document.xml").decode("utf-8")
            self.assertIn(WORD_NOTICE, document_xml)

            downloaded_markdown = restarted_client.get(f"/api/tasks/{task_id}/exports/markdown")
            self.assertEqual(downloaded_markdown.status_code, 200, downloaded_markdown.text)
            self.assertIn(WORD_NOTICE, downloaded_markdown.text)

            self.assertIsNotNone(get_task(task_id))
            self.assertIsNotNone(get_active_approval_for_task(task_id))
            self.assertEqual(len(list_export_events_for_task(task_id)), 1)
        finally:
            restarted_client.close()

    def test_post_restart_edit_invalidates_approval_and_blocks_stale_export(self):
        task_id, _ = self._create_doctor_and_generate_task()

        with TestClient(app) as client:
            login_as_user(client, username="restart-doctor")
            self.assertEqual(client.post(f"/api/tasks/{task_id}/approve").status_code, 200)
            self.assertIsNotNone(get_active_approval_for_task(task_id))

        restarted_client = self._restart_app_and_login()
        try:
            task = restarted_client.get(f"/api/tasks/{task_id}")
            self.assertEqual(task.status_code, 200, task.text)
            fields = deepcopy(task.json()["result_json"]["fields"])
            fields["chief_complaint"]["value"] = "doctor edited after restart"
            fields["chief_complaint"]["status"] = "partial"
            fields["chief_complaint"]["missing"] = False
            fields["chief_complaint"]["missing_elements"] = ["duration"]

            reviewed = restarted_client.post(
                f"/api/tasks/{task_id}/review",
                json={"fields": fields},
            )
            self.assertEqual(reviewed.status_code, 200, reviewed.text)
            self.assertIsNone(get_active_approval_for_task(task_id))

            revisions = list_record_revisions_for_task(task_id)
            self.assertGreaterEqual(len(revisions), 3)
            self.assertEqual(revisions[-1]["source"], "doctor_review")

            readiness = restarted_client.get(f"/api/tasks/{task_id}/export-readiness")
            self.assertEqual(readiness.status_code, 200, readiness.text)
            self.assertFalse(readiness.json()["ready"])
            self.assertTrue(readiness.json()["blocked"])

            blocked_export = restarted_client.post(f"/api/tasks/{task_id}/export")
            self.assertEqual(blocked_export.status_code, 400)
        finally:
            restarted_client.close()


if __name__ == "__main__":
    unittest.main()
