from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.agents import MedicalRecordOrchestrator
from app.db import init_db, set_task_owner
from app.main import app
from tests.auth_helpers import create_user, login_as_admin, login_as_user


class AuthApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_env = {
            key: os.environ.get(key)
            for key in [
                "MEDICAL_RECORD_AGENT_DB",
                "MEDICAL_RECORD_AGENT_BOOTSTRAP_ADMIN_USERNAME",
                "MEDICAL_RECORD_AGENT_BOOTSTRAP_ADMIN_PASSWORD",
                "MEDICAL_RECORD_AGENT_AUTH_BOOTSTRAP",
                "RECORD_PROVIDER_MODE",
            ]
        }
        os.environ["MEDICAL_RECORD_AGENT_DB"] = os.path.join(self.temp_dir.name, "auth.sqlite3")
        os.environ.pop("RECORD_PROVIDER_MODE", None)

    def tearDown(self):
        for key, value in self.original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.temp_dir.cleanup()

    def test_default_admin_can_login_create_doctor_and_logout(self):
        client = TestClient(app)

        admin = login_as_admin(client)
        self.assertEqual(admin["role"], "admin")

        created = client.post(
            "/api/auth/users",
            json={
                "username": "doctor-a",
                "password": "doctor-pass-123",
                "display_name": "Doctor A",
                "role": "doctor",
            },
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["role"], "doctor")

        listed = client.get("/api/auth/users")
        self.assertEqual(listed.status_code, 200)
        self.assertIn("doctor-a", {user["username"] for user in listed.json()["users"]})

        logged_out = client.post("/api/auth/logout")
        self.assertEqual(logged_out.status_code, 200)
        self.assertEqual(client.get("/api/auth/me").status_code, 401)

    def test_doctor_cannot_manage_users(self):
        client = TestClient(app)
        create_user(client, username="doctor-b")
        login_as_user(client, username="doctor-b")

        response = client.get("/api/auth/users")

        self.assertEqual(response.status_code, 403)

    def test_anonymous_high_risk_routes_return_401(self):
        client = TestClient(app)

        self.assertEqual(client.post("/api/tasks/1/approve").status_code, 401)
        self.assertEqual(client.post("/api/tasks/1/export").status_code, 401)
        self.assertEqual(client.delete("/api/speaker-profiles/profile-1").status_code, 401)
        self.assertEqual(client.post("/api/asr/sessions?engine=mock").status_code, 401)

    def test_doctor_cannot_access_another_doctors_task(self):
        client = TestClient(app)
        doctor_a = create_user(client, username="doctor-owner")
        create_user(client, username="doctor-other")
        result = MedicalRecordOrchestrator().run_from_text("patient has fever for three days")
        task_id = result["task_id"]
        set_task_owner(task_id, doctor_a["id"])

        login_as_user(client, username="doctor-other")
        forbidden = client.get(f"/api/tasks/{task_id}")
        self.assertEqual(forbidden.status_code, 403)

        client.post("/api/auth/logout")
        login_as_admin(client)
        allowed = client.get(f"/api/tasks/{task_id}")
        self.assertEqual(allowed.status_code, 200)

    def test_live_or_edge_mode_rejects_default_bootstrap_password(self):
        os.environ["MEDICAL_RECORD_AGENT_DB"] = os.path.join(self.temp_dir.name, "edge.sqlite3")
        os.environ["RECORD_PROVIDER_MODE"] = "edge"
        os.environ.pop("MEDICAL_RECORD_AGENT_BOOTSTRAP_ADMIN_PASSWORD", None)

        with self.assertRaises(RuntimeError):
            init_db()

    def test_speaker_profile_delete_requires_admin(self):
        client = TestClient(app)
        create_user(client, username="voice-doctor")
        login_as_user(client, username="voice-doctor")

        forbidden = client.delete("/api/speaker-profiles/profile-1")
        self.assertEqual(forbidden.status_code, 403)

        client.post("/api/auth/logout")
        login_as_admin(client)
        with patch("app.api.speaker_profiles.delete_doctor_profile", return_value=True):
            deleted = client.delete("/api/speaker-profiles/profile-1")
        self.assertEqual(deleted.status_code, 204)


if __name__ == "__main__":
    unittest.main()
