from __future__ import annotations

import os
import tempfile
import unittest

from fastapi.testclient import TestClient

from app.main import app
from tests.auth_helpers import create_user, login_as_admin, login_as_user


class EncountersApiTests(unittest.TestCase):
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
        os.environ["MEDICAL_RECORD_AGENT_DB"] = os.path.join(self.temp_dir.name, "encounters.sqlite3")
        os.environ["MEDICAL_RECORD_AGENT_OUTPUT_DIR"] = os.path.join(self.temp_dir.name, "outputs")

    def tearDown(self):
        for key, value in self.original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.temp_dir.cleanup()

    def test_doctor_worklist_returns_owned_generated_encounter_and_restores_draft(self):
        client = TestClient(app)
        doctor = create_user(client, username="worklist-doctor")
        login_as_user(client, username="worklist-doctor")

        generated = client.post(
            "/api/records/generate",
            json={"conversation_text": "patient has fever for three days"},
        )
        self.assertEqual(generated.status_code, 200, generated.text)
        task_id = generated.json()["task_id"]

        worklist = client.get("/api/encounters?mine=true")
        self.assertEqual(worklist.status_code, 200, worklist.text)
        encounters = worklist.json()["encounters"]
        self.assertEqual(len(encounters), 1)
        self.assertEqual(encounters[0]["doctor_user_id"], doctor["id"])
        self.assertEqual(encounters[0]["task_id"], task_id)
        self.assertEqual(encounters[0]["status"], "pending_review")

        detail = client.get(f"/api/encounters/{encounters[0]['id']}")
        self.assertEqual(detail.status_code, 200, detail.text)
        payload = detail.json()
        self.assertEqual(payload["task"]["id"], task_id)
        self.assertIn("fields", payload["task"]["result_json"])
        self.assertEqual(payload["current_revision"]["revision_no"], 1)
        self.assertEqual(len(payload["revisions"]), 1)

    def test_doctor_cannot_read_other_doctor_encounter_but_admin_can(self):
        client = TestClient(app)
        create_user(client, username="encounter-owner")
        create_user(client, username="encounter-other")
        login_as_user(client, username="encounter-owner")
        created = client.post(
            "/api/encounters",
            json={"patient_deidentified_id": "P-001", "patient_display_name": "模拟患者A"},
        )
        self.assertEqual(created.status_code, 200, created.text)
        encounter_id = created.json()["id"]
        client.post("/api/auth/logout")

        login_as_user(client, username="encounter-other")
        forbidden = client.get(f"/api/encounters/{encounter_id}")
        self.assertEqual(forbidden.status_code, 403)
        self.assertEqual(client.get("/api/encounters?mine=true").json()["encounters"], [])
        client.post("/api/auth/logout")

        login_as_admin(client)
        admin_list = client.get("/api/encounters?mine=false")
        self.assertEqual(admin_list.status_code, 200)
        self.assertEqual(len(admin_list.json()["encounters"]), 1)
        admin_detail = client.get(f"/api/encounters/{encounter_id}")
        self.assertEqual(admin_detail.status_code, 200)

    def test_worklist_filters_by_status_and_deidentified_patient_query(self):
        client = TestClient(app)
        create_user(client, username="filter-doctor")
        login_as_user(client, username="filter-doctor")

        draft = client.post(
            "/api/encounters",
            json={"patient_deidentified_id": "P-FILTER-001", "patient_display_name": "Filter Patient"},
        )
        self.assertEqual(draft.status_code, 200, draft.text)
        generated = client.post(
            "/api/records/generate",
            json={"conversation_text": "patient has fever for three days"},
        )
        self.assertEqual(generated.status_code, 200, generated.text)

        draft_only = client.get("/api/encounters?status=draft")
        self.assertEqual(draft_only.status_code, 200)
        self.assertEqual(
            [item["patient_deidentified_id"] for item in draft_only.json()["encounters"]],
            ["P-FILTER-001"],
        )

        searched = client.get("/api/encounters?q=FILTER")
        self.assertEqual(searched.status_code, 200)
        self.assertEqual(len(searched.json()["encounters"]), 1)
        self.assertEqual(searched.json()["encounters"][0]["status"], "draft")


if __name__ == "__main__":
    unittest.main()
