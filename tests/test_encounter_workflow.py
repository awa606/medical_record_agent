from __future__ import annotations

import os
import tempfile
import unittest

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.agents import MedicalRecordOrchestrator
from app.api.tasks import ReviewRequest, approve_task, export_task, review_task
from app.db import (
    get_active_approval_for_task,
    get_task,
    get_task_encounter,
    list_export_events_for_task,
    list_record_revisions_for_task,
)
from app.main import app
from app.schemas import MedicalRecordFields
from tests.auth_helpers import create_user, login_as_user


class EncounterWorkflowTests(unittest.TestCase):
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
        os.environ["MEDICAL_RECORD_AGENT_DB"] = os.path.join(self.temp_dir.name, "workflow.sqlite3")
        os.environ["MEDICAL_RECORD_AGENT_OUTPUT_DIR"] = os.path.join(self.temp_dir.name, "outputs")

    def tearDown(self):
        for key, value in self.original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.temp_dir.cleanup()

    def test_generation_creates_encounter_and_pending_review_revision(self):
        result = MedicalRecordOrchestrator().run_from_text("patient has fever for three days")
        task_id = result["task_id"]

        task = get_task(task_id)
        encounter = get_task_encounter(task_id)
        revisions = list_record_revisions_for_task(task_id)

        self.assertIsNotNone(encounter)
        self.assertEqual(encounter["status"], "pending_review")
        self.assertEqual(task["encounter_id"], encounter["id"])
        self.assertEqual(task["current_record_revision_id"], revisions[0]["id"])
        self.assertEqual(revisions[0]["revision_no"], 1)
        self.assertEqual(revisions[0]["source"], "generation")

    def test_review_after_approval_invalidates_old_approval_and_blocks_export(self):
        result = MedicalRecordOrchestrator().run_from_text("patient has fever for three days")
        task_id = result["task_id"]

        approved = approve_task(task_id)
        active_approval = get_active_approval_for_task(task_id)
        self.assertIsNotNone(active_approval)
        self.assertEqual(approved["current_stage"], "approved")

        fields = MedicalRecordFields.model_validate(approved["result_json"]["fields"])
        fields.chief_complaint = fields.chief_complaint.model_copy(
            update={
                "value": "doctor reviewed complaint",
                "missing": False,
                "status": "partial",
                "missing_elements": ["duration"],
            }
        )
        reviewed = review_task(task_id, ReviewRequest(fields=fields))
        self.assertEqual(reviewed["current_stage"], "reviewed")

        self.assertIsNone(get_active_approval_for_task(task_id))
        revisions = list_record_revisions_for_task(task_id)
        self.assertGreaterEqual(len(revisions), 3)
        self.assertEqual(revisions[-1]["source"], "doctor_review")

        with self.assertRaises(HTTPException) as blocked:
            export_task(task_id)
        self.assertEqual(blocked.exception.status_code, 400)
        self.assertTrue(any("医生批准" in item for item in blocked.exception.detail["errors"]))

    def test_http_approval_and_export_bind_actor_revision_and_approval(self):
        client = TestClient(app)
        doctor = create_user(client, username="workflow-doctor")
        login_as_user(client, username="workflow-doctor")

        generated = client.post(
            "/api/records/generate",
            json={"conversation_text": "patient has fever for three days"},
        )
        self.assertEqual(generated.status_code, 200, generated.text)
        task_id = generated.json()["task_id"]
        task = client.get(f"/api/tasks/{task_id}").json()
        self.assertIsNotNone(task["encounter_id"])
        self.assertIsNotNone(task["current_record_revision_id"])

        approved = client.post(f"/api/tasks/{task_id}/approve")
        self.assertEqual(approved.status_code, 200, approved.text)
        approval = get_active_approval_for_task(task_id)
        self.assertIsNotNone(approval)
        self.assertEqual(approval["approved_by_user_id"], doctor["id"])
        self.assertEqual(approval["revision_id"], get_task(task_id)["current_record_revision_id"])

        duplicate = client.post(f"/api/tasks/{task_id}/approve")
        self.assertEqual(duplicate.status_code, 409)

        exported = client.post(f"/api/tasks/{task_id}/export")
        self.assertEqual(exported.status_code, 200, exported.text)
        events = list_export_events_for_task(task_id)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["exported_by_user_id"], doctor["id"])
        self.assertEqual(events[0]["approval_id"], approval["id"])
        self.assertEqual(events[0]["revision_id"], approval["revision_id"])


if __name__ == "__main__":
    unittest.main()
