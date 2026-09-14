from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.services.demo_knowledge import load_sources, retrieve_sources
from tests.auth_helpers import create_user, login_as_admin, login_as_user


class DemoKnowledgeApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_env = {
            key: os.environ.get(key)
            for key in [
                "MEDICAL_RECORD_AGENT_DB",
                "MEDICAL_RECORD_AGENT_OUTPUT_DIR",
                "LLM_PROVIDER",
                "RECORD_PROVIDER_MODE",
            ]
        }
        os.environ["MEDICAL_RECORD_AGENT_DB"] = os.path.join(self.temp_dir.name, "knowledge.sqlite3")
        os.environ["MEDICAL_RECORD_AGENT_OUTPUT_DIR"] = os.path.join(self.temp_dir.name, "outputs")
        os.environ.pop("LLM_PROVIDER", None)
        os.environ.pop("RECORD_PROVIDER_MODE", None)

    def tearDown(self):
        for key, value in self.original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.temp_dir.cleanup()

    def _make_knowledge_root(self, sources: list[dict], manifest_sources: list[str] | None = None) -> Path:
        root = Path(self.temp_dir.name) / "knowledge"
        source_dir = root / "sources"
        source_dir.mkdir(parents=True)
        paths = []
        for index, source in enumerate(sources, start=1):
            path = source_dir / f"source_{index}.json"
            path.write_text(json.dumps(source, ensure_ascii=False), encoding="utf-8")
            paths.append(f"sources/source_{index}.json")
        (root / "manifest.json").write_text(
            json.dumps(
                {
                    "version": "test",
                    "scope": "test",
                    "disclaimer": "test only",
                    "sources": manifest_sources or paths,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return root

    def _source(self, *, source_id: str = "s1", review_status: str = "verified_demo") -> dict:
        return {
            "source_id": source_id,
            "title": "演示资料：发热咳嗽",
            "publisher": "MediListen 课程演示资料组",
            "document_type": "clinical_guideline",
            "year": 2025,
            "version": "2025-demo",
            "review_status": review_status,
            "excerpt": "发热伴咳嗽需记录体温、咳嗽性质和危险信号。",
            "related_fields": ["主诉", "现病史", "风险提示"],
            "keywords": ["发热", "咳嗽"],
            "citation_anchor": "section-test",
            "source_url": None,
        }

    def _create_review_task(self, client: TestClient, username: str = "knowledge-doctor") -> int:
        create_user(client, username=username)
        login_as_user(client, username=username)
        response = client.post(
            "/api/records/generate",
            json={"conversation_text": "患者发热三天，咳嗽咳痰，胸闷。"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return int(response.json()["task_id"])

    def test_manifest_loads_verified_demo_sources(self):
        sources = load_sources()
        self.assertGreaterEqual(len(sources), 3)
        self.assertIn("guideline_demo_001", {source.source_id for source in sources})
        self.assertTrue(all(source.title.startswith("演示资料") for source in sources))

    def test_invalid_review_status_is_rejected(self):
        root = self._make_knowledge_root([self._source(review_status="real_hospital_verified")])
        with self.assertRaises(ValueError):
            load_sources(root)

    def test_duplicate_source_id_is_rejected(self):
        root = self._make_knowledge_root([self._source(source_id="dup"), self._source(source_id="dup")])
        with self.assertRaises(ValueError):
            load_sources(root)

    def test_source_list_detail_and_missing_detail_contract(self):
        client = TestClient(app)
        login_as_admin(client)

        listed = client.get("/api/knowledge/sources")
        self.assertEqual(listed.status_code, 200, listed.text)
        payload = listed.json()
        self.assertIn("sources", payload)
        self.assertTrue(any(item["review_status"] == "withdrawn" for item in payload["sources"]))

        detail = client.get("/api/knowledge/sources/guideline_demo_001")
        self.assertEqual(detail.status_code, 200, detail.text)
        self.assertEqual(detail.json()["status_label"], "人工核验演示资料")

        missing = client.get("/api/knowledge/sources/not-found")
        self.assertEqual(missing.status_code, 404)

    def test_retrieve_is_deterministic_and_excludes_withdrawn_sources(self):
        results = retrieve_sources(query="发热咳嗽咳痰", related_fields=["主诉", "处理建议"])
        source_ids = {item["source_id"] for item in results}
        self.assertIn("guideline_demo_001", source_ids)
        self.assertNotIn("guideline_demo_003", source_ids)
        self.assertTrue(all(item["matched_fields"] or item["matched_keywords"] for item in results))

    def test_task_evidence_requires_login_and_checks_doctor_owner(self):
        client = TestClient(app)
        task_id = self._create_review_task(client, username="knowledge-owner")
        client.post("/api/auth/logout")

        anonymous = client.get(f"/api/tasks/{task_id}/evidence")
        self.assertEqual(anonymous.status_code, 401)

        create_user(client, username="knowledge-other")
        login_as_user(client, username="knowledge-other")
        forbidden = client.get(f"/api/tasks/{task_id}/evidence")
        self.assertEqual(forbidden.status_code, 403)

        client.post("/api/auth/logout")
        login_as_user(client, username="knowledge-owner")
        allowed = client.get(f"/api/tasks/{task_id}/evidence")
        self.assertEqual(allowed.status_code, 200, allowed.text)
        self.assertGreaterEqual(allowed.json()["count"], 1)

    def test_retrieve_with_task_id_respects_task_access(self):
        client = TestClient(app)
        task_id = self._create_review_task(client, username="knowledge-retrieve-owner")
        response = client.post(
            "/api/knowledge/retrieve",
            json={"task_id": task_id, "query": "咳嗽", "related_fields": ["主诉"]},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertGreaterEqual(response.json()["count"], 1)

    def test_missing_task_evidence_returns_404(self):
        client = TestClient(app)
        login_as_admin(client)
        response = client.get("/api/tasks/999999/evidence")
        self.assertEqual(response.status_code, 404)

    def test_knowledge_evidence_does_not_change_export_readiness(self):
        client = TestClient(app)
        task_id = self._create_review_task(client, username="knowledge-readiness")
        before = client.get(f"/api/tasks/{task_id}/export-readiness").json()
        evidence = client.get(f"/api/tasks/{task_id}/evidence")
        self.assertEqual(evidence.status_code, 200, evidence.text)
        after = client.get(f"/api/tasks/{task_id}/export-readiness").json()
        self.assertEqual(before["ready"], after["ready"])
        self.assertEqual(before["revision_id"], after["revision_id"])
        self.assertEqual(before["content_hash"], after["content_hash"])


if __name__ == "__main__":
    unittest.main()
