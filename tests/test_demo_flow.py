from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from scripts.demo_flow import Response, run_flow


ENV_KEYS = [
    "MEDICAL_RECORD_AGENT_DB",
    "MEDICAL_RECORD_AGENT_OUTPUT_DIR",
    "MEDICAL_RECORD_AGENT_BOOTSTRAP_ADMIN_USERNAME",
    "MEDICAL_RECORD_AGENT_BOOTSTRAP_ADMIN_PASSWORD",
    "MEDICAL_RECORD_AGENT_AUTH_BOOTSTRAP",
    "RECORD_PROVIDER_MODE",
    "LLM_PROVIDER",
    "MRA_ANONYMIZE",
]


class DemoHttpClient:
    """Adapter so the demo flow can run against TestClient in tests."""

    def __init__(self, client: TestClient) -> None:
        self.client = client

    def request(self, method: str, path: str, payload: dict | None = None) -> Response:
        if method == "GET":
            response = self.client.get(path)
        elif method == "POST":
            response = self.client.post(path, json=payload)
        else:
            raise AssertionError(f"Unsupported method {method}")
        return Response(
            status=response.status_code,
            body=response.content,
            headers=dict(response.headers),
        )


class DemoFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_env = {key: os.environ.get(key) for key in ENV_KEYS}
        for key in ENV_KEYS:
            os.environ.pop(key, None)
        os.environ["MEDICAL_RECORD_AGENT_DB"] = str(Path(self.temp_dir.name) / "demo.sqlite3")
        os.environ["MEDICAL_RECORD_AGENT_OUTPUT_DIR"] = str(Path(self.temp_dir.name) / "outputs")

    def tearDown(self):
        for key, value in self.original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        for attempt in range(5):
            try:
                self.temp_dir.cleanup()
                break
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(0.2)

    def _clients(self) -> tuple[DemoHttpClient, DemoHttpClient]:
        return DemoHttpClient(TestClient(app)), DemoHttpClient(TestClient(app))

    def test_demo_flow_runs_end_to_end(self):
        admin_http, doctor_http = self._clients()
        report = run_flow(admin_http, doctor_http)

        failed = [step for step in report["steps"] if not step["ok"]]
        self.assertEqual(failed, [], json.dumps(failed, ensure_ascii=False))
        self.assertTrue(report["ok"])
        self.assertEqual(report["version"]["service"], "medical-record-agent")
        self.assertTrue(report["ids"]["task_id"])
        self.assertTrue(report["ids"]["export_event_id"])
        names = {step["step"] for step in report["steps"]}
        for required in (
            "health",
            "version",
            "admin_login",
            "create_encounter",
            "check_in",
            "start_encounter",
            "generate_record",
            "doctor_edit_review",
            "approve",
            "export",
            "download_docx",
            "download_markdown",
            "reopen_encounter",
            "revision_history",
            "complete_encounter",
            "audit_chain",
            "metrics",
        ):
            self.assertIn(required, names)

    def test_second_run_reuses_the_demo_doctor(self):
        first = run_flow(*self._clients())
        self.assertTrue(first["ok"])
        second = run_flow(*self._clients())
        failed = [step for step in second["steps"] if not step["ok"]]
        self.assertEqual(failed, [], json.dumps(failed, ensure_ascii=False))
        self.assertTrue(second["ok"])

    def test_version_endpoint_exposes_build_identity(self):
        client = TestClient(app)
        response = client.get("/version")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["service"], "medical-record-agent")
        self.assertIn("version", body)
        self.assertIn("started_at", body)

    def test_seed_only_prepares_the_doctor_without_generating(self):
        report = run_flow(*self._clients(), seed_only=True)
        self.assertTrue(report["ok"])
        self.assertTrue(report["seed_only"])
        names = {step["step"] for step in report["steps"]}
        self.assertIn("ensure_demo_doctor", names)
        self.assertNotIn("generate_record", names)
        self.assertNotIn("export", names)


if __name__ == "__main__":
    unittest.main()


