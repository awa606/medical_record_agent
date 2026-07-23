from __future__ import annotations

import os
import unittest
from typing import Any

from scripts.pilot_smoke import PilotSmokeError, run_smoke


TEST_STRONG_PASSWORD = "TEST_ONLY_STRONG_PASSWORD_76!"


class FakeSmokeClient:
    def __init__(self):
        self.calls: list[tuple[str, str, dict[str, Any] | None]] = []
        self.task_reads = 0

    def request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        self.calls.append((method.upper(), path, payload))
        if method.upper() == "GET" and path == "/health":
            return {"status": "ok"}
        if method.upper() == "GET" and path == "/ready":
            return {"status": "ready"}
        if method.upper() == "POST" and path == "/api/auth/login":
            return {"user": {"username": payload["username"], "role": "admin"}}
        if method.upper() == "POST" and path == "/api/records/generate":
            self.generated_text = payload["conversation_text"]
            return {"task_id": 42, "status": "CREATED"}
        if method.upper() == "GET" and path == "/api/tasks/42":
            self.task_reads += 1
            if self.task_reads == 1:
                return {"id": 42, "status": "GENERATING_DRAFT"}
            return {
                "id": 42,
                "status": "WAITING_DOCTOR_REVIEW",
                "result_json": {"fields": self._fields(), "reviewed": False, "approved": False},
            }
        if method.upper() == "POST" and path == "/api/tasks/42/review":
            return {"id": 42, "result_json": {"fields": payload["fields"], "reviewed": True, "approved": False}}
        if method.upper() == "POST" and path == "/api/tasks/42/approve":
            return {"id": 42, "result_json": {"fields": self._fields(), "reviewed": True, "approved": True}}
        if method.upper() == "GET" and path == "/api/tasks/42/export-readiness":
            return {"task_id": 42, "ready": True, "blocked": False, "errors": []}
        if method.upper() == "POST" and path == "/api/tasks/42/export":
            return {"task_id": 42, "exports": {"markdown_path": "out.md", "word_path": "out.docx"}}
        raise AssertionError(f"unexpected request: {method} {path}")

    def _fields(self) -> dict[str, Any]:
        return {
            "chief_complaint": {"value": "发热三天", "missing": False, "confidence": 0.9, "source_spans": [], "confirmed_by_doctor": False},
            "present_illness": {"value": "最高体温39度，伴咳嗽", "missing": False, "confidence": 0.9, "source_spans": [], "confirmed_by_doctor": False},
            "previous_treatment": {"value": "服用布洛芬", "missing": False, "confidence": 0.8, "source_spans": [], "confirmed_by_doctor": False},
            "accompanying_symptoms": {"value": "咳嗽", "missing": False, "confidence": 0.8, "source_spans": [], "confirmed_by_doctor": False},
            "past_history": {"value": "未提及", "missing": True, "confidence": 0.4, "source_spans": [], "confirmed_by_doctor": False},
            "allergy_history": {"value": "无明确药物过敏", "missing": False, "confidence": 0.8, "source_spans": [], "confirmed_by_doctor": False},
            "physical_exam": {"value": "待医生查体补充", "missing": True, "confidence": 0.4, "source_spans": [], "confirmed_by_doctor": False},
            "candidate_diagnoses": [
                {"name": "上呼吸道感染", "confidence": 0.6, "reason": "发热咳嗽", "evidence": [], "suggested_checks": [], "risk_warnings": [], "medication_notes": [], "follow_up_questions": [], "confirmed_by_doctor": False}
            ],
        }


class PilotSmokeTests(unittest.TestCase):
    def test_smoke_runs_expected_http_sequence_without_exposing_password(self):
        client = FakeSmokeClient()

        report = run_smoke(
            client,
            username="pilot_admin",
            password=TEST_STRONG_PASSWORD,
            timeout_seconds=10,
            poll_interval_seconds=0,
        )

        self.assertTrue(report["ok"])
        self.assertEqual(report["task_id"], 42)
        self.assertEqual(
            [name for _, name, _ in client.calls[:4]],
            ["/health", "/ready", "/api/auth/login", "/api/records/generate"],
        )
        self.assertNotIn(TEST_STRONG_PASSWORD, str(report))

    def test_smoke_fails_when_ready_is_not_ready(self):
        class NotReadyClient(FakeSmokeClient):
            def request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
                if method.upper() == "GET" and path == "/ready":
                    return {"status": "not_ready"}
                return super().request(method, path, payload)

        with self.assertRaises(PilotSmokeError):
            run_smoke(
                NotReadyClient(),
                username="pilot_admin",
                password=TEST_STRONG_PASSWORD,
                timeout_seconds=10,
                poll_interval_seconds=0,
            )

    def test_password_env_name_can_be_used_without_printing_secret(self):
        os.environ["MRA_TEST_SMOKE_PASSWORD"] = TEST_STRONG_PASSWORD
        try:
            self.assertEqual(os.environ["MRA_TEST_SMOKE_PASSWORD"], TEST_STRONG_PASSWORD)
        finally:
            os.environ.pop("MRA_TEST_SMOKE_PASSWORD", None)


if __name__ == "__main__":
    unittest.main()
