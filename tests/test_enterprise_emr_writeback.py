from __future__ import annotations

import json
import os
import tempfile
import unittest

from fastapi.testclient import TestClient

from app.db import get_audit_logs
from app.enterprise.idempotency import reset_enterprise_idempotency_store
from app.integrations.emr import mock_emr_write_count, reset_mock_emr_writes
from app.main import app
from tests.auth_helpers import create_user, login_as_user


ENTERPRISE_WRITEBACK_ENV_KEYS = [
    "MEDICAL_RECORD_AGENT_DB",
    "MEDICAL_RECORD_AGENT_OUTPUT_DIR",
    "LLM_PROVIDER",
    "RECORD_PROVIDER_MODE",
    "ONLINE_LLM_API_BASE",
    "ONLINE_LLM_API_KEY",
    "ONLINE_LLM_MODEL",
    "OLLAMA_BASE_URL",
    "OLLAMA_MODEL",
    "MRA_ENTERPRISE_ENABLED",
    "MRA_ENTERPRISE_EMR_ADAPTER",
]


class EnterpriseEMRWritebackTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_env = {key: os.environ.get(key) for key in ENTERPRISE_WRITEBACK_ENV_KEYS}
        for key in ENTERPRISE_WRITEBACK_ENV_KEYS:
            os.environ.pop(key, None)
        os.environ["MEDICAL_RECORD_AGENT_DB"] = os.path.join(self.temp_dir.name, "enterprise.sqlite3")
        os.environ["MEDICAL_RECORD_AGENT_OUTPUT_DIR"] = os.path.join(self.temp_dir.name, "outputs")
        os.environ["MRA_ENTERPRISE_ENABLED"] = "1"
        os.environ["MRA_ENTERPRISE_EMR_ADAPTER"] = "mock"
        reset_enterprise_idempotency_store()
        reset_mock_emr_writes()

    def tearDown(self):
        reset_enterprise_idempotency_store()
        reset_mock_emr_writes()
        for key, value in self.original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.temp_dir.cleanup()

    def test_writeback_requires_auth_and_idempotency_key(self):
        client = TestClient(app)

        unauthenticated = client.post("/api/enterprise/emr/writeback", json={"task_id": 1})
        self.assertEqual(unauthenticated.status_code, 401)

        create_user(client, username="enterprise-auth-doctor")
        login_as_user(client, username="enterprise-auth-doctor")
        missing_key = client.post("/api/enterprise/emr/writeback", json={"task_id": 1})
        self.assertEqual(missing_key.status_code, 400)

    def test_unapproved_record_is_blocked_from_mock_emr_writeback(self):
        client = self._logged_in_client("enterprise-unapproved-doctor")
        task_id = self._generate_task(client)

        response = client.post(
            "/api/enterprise/emr/writeback",
            json={"task_id": task_id},
            headers={"Idempotency-Key": "unapproved-1", "Authorization": "Bearer should-redact"},
        )

        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(mock_emr_write_count(), 0)
        self.assertTrue(any("Active doctor approval" in item for item in response.json()["detail"]["errors"]))
        logs = get_audit_logs(task_id)
        self.assertEqual(logs[-1]["event_type"], "enterprise_emr_writeback_blocked")
        event_detail = json.loads(logs[-1]["event_detail"])
        self.assertEqual(event_detail["details"]["authorization"], "[REDACTED]")

    def test_approved_record_writeback_is_idempotent(self):
        client = self._logged_in_client("enterprise-approved-doctor")
        task_id = self._generate_task(client)
        approved = client.post(f"/api/tasks/{task_id}/approve")
        self.assertEqual(approved.status_code, 200, approved.text)

        first = client.post(
            "/api/enterprise/emr/writeback",
            json={"task_id": task_id, "organization_id": "org-1", "department_id": "dept-1"},
            headers={"Idempotency-Key": "approved-key-1", "X-Correlation-ID": "corr-writeback"},
        )
        duplicate = client.post(
            "/api/enterprise/emr/writeback",
            json={"task_id": task_id, "organization_id": "org-1", "department_id": "dept-1"},
            headers={"Idempotency-Key": "approved-key-1", "X-Correlation-ID": "different-corr"},
        )

        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(duplicate.status_code, 200, duplicate.text)
        self.assertEqual(first.json(), duplicate.json())
        self.assertEqual(mock_emr_write_count(), 1)
        self.assertEqual(first.json()["receipt"]["adapter"], "mock_emr")
        self.assertEqual(first.json()["capability_state"], "mock")
        self.assertEqual(first.json()["correlation_id"], "corr-writeback")
        logs = get_audit_logs(task_id)
        self.assertEqual(
            [log["event_type"] for log in logs].count("enterprise_emr_writeback_completed"),
            1,
        )

        other_task_id = self._generate_task(client)
        approved_other = client.post(f"/api/tasks/{other_task_id}/approve")
        self.assertEqual(approved_other.status_code, 200, approved_other.text)
        conflict = client.post(
            "/api/enterprise/emr/writeback",
            json={"task_id": other_task_id},
            headers={"Idempotency-Key": "approved-key-1"},
        )
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(mock_emr_write_count(), 1)

    def _logged_in_client(self, username: str) -> TestClient:
        client = TestClient(app)
        create_user(client, username=username)
        login_as_user(client, username=username)
        return client

    def _generate_task(self, client: TestClient) -> int:
        response = client.post(
            "/api/records/generate",
            json={"conversation_text": "patient has fever for three days and cough"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return int(response.json()["task_id"])


if __name__ == "__main__":
    unittest.main()
