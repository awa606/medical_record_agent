from __future__ import annotations

import os
import tempfile
import unittest

from fastapi.testclient import TestClient

from app.db import init_db
from app.main import app
from tests.auth_helpers import login_as_admin


class KnowledgeApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self._old_env = {
            key: os.environ.get(key)
            for key in [
                "MEDICAL_RECORD_AGENT_DB",
                "MEDICAL_RECORD_AGENT_AUTH_BOOTSTRAP",
                "MEDICAL_RECORD_AGENT_BOOTSTRAP_ADMIN_USERNAME",
                "MEDICAL_RECORD_AGENT_BOOTSTRAP_ADMIN_PASSWORD",
            ]
        }
        os.environ["MEDICAL_RECORD_AGENT_DB"] = os.path.join(self.temp_dir.name, "knowledge.sqlite3")
        os.environ["MEDICAL_RECORD_AGENT_AUTH_BOOTSTRAP"] = "1"
        os.environ["MEDICAL_RECORD_AGENT_BOOTSTRAP_ADMIN_USERNAME"] = "admin"
        os.environ["MEDICAL_RECORD_AGENT_BOOTSTRAP_ADMIN_PASSWORD"] = "admin123456"
        init_db()

    def tearDown(self) -> None:
        for key, value in self._old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.temp_dir.cleanup()

    def test_knowledge_base_requires_login(self) -> None:
        response = TestClient(app).get("/api/knowledge")

        self.assertEqual(response.status_code, 401)

    def test_knowledge_base_lists_packs_and_references(self) -> None:
        client = TestClient(app)
        login_as_admin(client)

        response = client.get("/api/knowledge")

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        pack_ids = {item["pack_id"] for item in payload["packs"]}
        self.assertEqual(payload["version"], "clinical_knowledge_base_v1")
        self.assertIn("fever_respiratory_v1", pack_ids)
        self.assertIn("common_cold_course_mock_v1", pack_ids)
        self.assertGreaterEqual(len(payload["references"]), 4)
        self.assertTrue(
            all(reference["url"].startswith("https://") for reference in payload["references"])
        )
        self.assertTrue(
            all(
                reference["clinical_review_status"] == "needs_medical_review"
                for reference in payload["references"]
            )
        )
        self.assertTrue(payload["limits"])

    def test_reference_catalog_endpoint_is_serializable(self) -> None:
        client = TestClient(app)
        login_as_admin(client)

        response = client.get("/api/knowledge/references")

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["catalog_version"], "fever_respiratory_sources_v1")
        reference_ids = {item["reference_id"] for item in payload["references"]}
        self.assertIn("NHC_FLU_2025", reference_ids)
        self.assertIn("WHO_SARI_TOOLKIT_2022", reference_ids)


if __name__ == "__main__":
    unittest.main()
