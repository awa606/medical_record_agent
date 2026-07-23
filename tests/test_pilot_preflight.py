from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.pilot_preflight import run_preflight, sanitized_for_output


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_KEYS = [
    "MEDICAL_RECORD_AGENT_DB",
    "MEDICAL_RECORD_AGENT_UPLOAD_DIR",
    "MEDICAL_RECORD_AGENT_OUTPUT_DIR",
    "MEDICAL_RECORD_AGENT_SPEAKER_PROFILE_DIR",
    "MEDICAL_RECORD_AGENT_MIN_FREE_BYTES",
    "MEDICAL_RECORD_AGENT_AUTH_BOOTSTRAP",
    "MEDICAL_RECORD_AGENT_BOOTSTRAP_ADMIN_USERNAME",
    "MEDICAL_RECORD_AGENT_BOOTSTRAP_ADMIN_PASSWORD",
    "RECORD_PROVIDER_MODE",
    "LLM_PROVIDER",
    "OLLAMA_BASE_URL",
    "OLLAMA_MODEL",
    "ONLINE_LLM_API_BASE",
    "ONLINE_LLM_API_KEY",
    "ONLINE_LLM_MODEL",
]
TEST_STRONG_PASSWORD = "TEST_ONLY_STRONG_PASSWORD_76!"
TEST_SECRET_VALUE = "REDACTION_TEST_VALUE"


class PilotPreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.original_env = {key: os.environ.get(key) for key in ENV_KEYS}
        for key in ENV_KEYS:
            os.environ.pop(key, None)
        os.environ["MEDICAL_RECORD_AGENT_DB"] = str(self.root / "runtime" / "pilot.sqlite3")
        os.environ["MEDICAL_RECORD_AGENT_UPLOAD_DIR"] = str(self.root / "runtime" / "uploads")
        os.environ["MEDICAL_RECORD_AGENT_OUTPUT_DIR"] = str(self.root / "runtime" / "outputs")
        os.environ["MEDICAL_RECORD_AGENT_SPEAKER_PROFILE_DIR"] = str(self.root / "runtime" / "speaker_profiles")
        os.environ["MEDICAL_RECORD_AGENT_MIN_FREE_BYTES"] = "1"

    def tearDown(self):
        for key, value in self.original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.temp_dir.cleanup()

    def test_demo_mode_preflight_creates_and_checks_runtime_dirs(self):
        report = run_preflight()

        self.assertTrue(report["ok"], report)
        self.assertTrue(report["checks"]["database"]["ok"])
        self.assertIn("will be created", report["checks"]["database"]["note"])
        self.assertTrue((self.root / "runtime" / "uploads").exists())
        self.assertTrue(report["checks"]["uploads"]["ok"])
        self.assertTrue(report["checks"]["outputs"]["ok"])
        self.assertTrue(report["checks"]["speaker_profiles"]["ok"])
        self.assertTrue(report["checks"]["disk"]["ok"])

    def test_require_existing_db_fails_when_database_is_missing(self):
        report = run_preflight(require_existing_db=True)

        self.assertFalse(report["ok"])
        self.assertFalse(report["checks"]["database"]["ok"])
        self.assertIn("does not exist", report["checks"]["database"]["error"])

    def test_edge_mode_accepts_strong_password_and_configured_ollama(self):
        os.environ["RECORD_PROVIDER_MODE"] = "edge"
        os.environ["MEDICAL_RECORD_AGENT_BOOTSTRAP_ADMIN_USERNAME"] = "pilot_admin"
        os.environ["MEDICAL_RECORD_AGENT_BOOTSTRAP_ADMIN_PASSWORD"] = TEST_STRONG_PASSWORD
        os.environ["LLM_PROVIDER"] = "ollama"
        os.environ["OLLAMA_BASE_URL"] = "http://127.0.0.1:11434"
        os.environ["OLLAMA_MODEL"] = "qwen3:4b-instruct"

        report = run_preflight()

        self.assertTrue(report["ok"], report)
        self.assertTrue(report["checks"]["auth"]["ok"])
        self.assertTrue(report["checks"]["provider"]["ok"])

    def test_edge_mode_rejects_missing_password(self):
        os.environ["RECORD_PROVIDER_MODE"] = "edge"
        os.environ["LLM_PROVIDER"] = "ollama"
        os.environ["OLLAMA_BASE_URL"] = "http://127.0.0.1:11434"
        os.environ["OLLAMA_MODEL"] = "qwen3:4b-instruct"

        report = run_preflight()

        self.assertFalse(report["ok"])
        self.assertFalse(report["checks"]["auth"]["ok"])
        self.assertIn("BOOTSTRAP_ADMIN_PASSWORD", report["checks"]["auth"]["error"])

    def test_edge_mode_rejects_mock_or_missing_provider(self):
        os.environ["RECORD_PROVIDER_MODE"] = "edge"
        os.environ["MEDICAL_RECORD_AGENT_BOOTSTRAP_ADMIN_PASSWORD"] = TEST_STRONG_PASSWORD
        os.environ["LLM_PROVIDER"] = "mock"

        report = run_preflight()

        self.assertFalse(report["ok"])
        self.assertFalse(report["checks"]["provider"]["ok"])
        self.assertIn("online or ollama", report["checks"]["provider"]["error"])

    def test_env_file_values_are_loaded_and_secret_output_is_redacted(self):
        env_file = self.root / "pilot.env"
        env_file.write_text(
            "\n".join(
                [
                    "RECORD_PROVIDER_MODE=edge",
                    "MEDICAL_RECORD_AGENT_BOOTSTRAP_ADMIN_USERNAME=pilot_admin",
                    f"MEDICAL_RECORD_AGENT_BOOTSTRAP_ADMIN_PASSWORD={TEST_STRONG_PASSWORD}",
                    "LLM_PROVIDER=online",
                    "ONLINE_LLM_API_BASE=https://llm.example.test",
                    f"ONLINE_LLM_API_KEY={TEST_SECRET_VALUE}",
                    "ONLINE_LLM_MODEL=pilot-model",
                ]
            ),
            encoding="utf-8",
        )

        report = run_preflight(env_file=env_file)
        raw_json = json.dumps(report, ensure_ascii=False)

        self.assertTrue(report["checks"]["provider"]["ok"], report)
        self.assertNotIn(TEST_SECRET_VALUE, raw_json)
        self.assertEqual(sanitized_for_output({"ONLINE_LLM_API_KEY": TEST_SECRET_VALUE})["ONLINE_LLM_API_KEY"], "***REDACTED***")

    def test_cli_runs_from_project_root_without_pythonpath(self):
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)

        completed = subprocess.run(
            [sys.executable, "scripts/pilot_preflight.py", "--json"],
            cwd=PROJECT_ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        report = json.loads(completed.stdout)
        self.assertTrue(report["ok"], report)


if __name__ == "__main__":
    unittest.main()
