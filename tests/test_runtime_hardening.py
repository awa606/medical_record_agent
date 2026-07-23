from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from scripts.edge_sqlite_backup import backup_sqlite, restore_sqlite
from tests.auth_helpers import login_as_admin


class RuntimeHardeningTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.original_env = {
            key: os.environ.get(key)
            for key in [
                "MEDICAL_RECORD_AGENT_DB",
                "MEDICAL_RECORD_AGENT_UPLOAD_DIR",
                "MEDICAL_RECORD_AGENT_OUTPUT_DIR",
                "MEDICAL_RECORD_AGENT_SPEAKER_PROFILE_DIR",
                "MEDICAL_RECORD_AGENT_MIN_FREE_BYTES",
                "MEDICAL_RECORD_AGENT_MAX_UPLOAD_BYTES",
                "MEDICAL_RECORD_AGENT_AUTH_BOOTSTRAP",
                "RECORD_PROVIDER_MODE",
                "LLM_PROVIDER",
            ]
        }
        os.environ["MEDICAL_RECORD_AGENT_DB"] = str(self.root / "runtime.sqlite3")
        os.environ["MEDICAL_RECORD_AGENT_UPLOAD_DIR"] = str(self.root / "uploads")
        os.environ["MEDICAL_RECORD_AGENT_OUTPUT_DIR"] = str(self.root / "outputs")
        os.environ["MEDICAL_RECORD_AGENT_SPEAKER_PROFILE_DIR"] = str(self.root / "speaker_profiles")
        os.environ["MEDICAL_RECORD_AGENT_MIN_FREE_BYTES"] = "1"
        os.environ.pop("RECORD_PROVIDER_MODE", None)
        os.environ.pop("LLM_PROVIDER", None)
        os.environ.pop("MEDICAL_RECORD_AGENT_AUTH_BOOTSTRAP", None)

    def tearDown(self):
        for key, value in self.original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.temp_dir.cleanup()

    def test_live_and_ready_report_runtime_health(self):
        client = TestClient(app)
        live = client.get("/live")
        self.assertEqual(live.status_code, 200)
        self.assertEqual(live.json()["status"], "alive")

        ready = client.get("/ready")
        self.assertEqual(ready.status_code, 200, ready.text)
        payload = ready.json()
        self.assertEqual(payload["status"], "ready")
        self.assertTrue(payload["checks"]["sqlite"]["ok"])
        self.assertEqual(payload["checks"]["sqlite"]["journal_mode"], "wal")
        self.assertTrue(payload["checks"]["uploads"]["ok"])
        self.assertTrue(payload["checks"]["outputs"]["ok"])
        self.assertTrue(payload["checks"]["provider"]["ok"])

    def test_ready_blocks_edge_mode_with_mock_provider(self):
        os.environ["MEDICAL_RECORD_AGENT_AUTH_BOOTSTRAP"] = "0"
        os.environ["RECORD_PROVIDER_MODE"] = "edge"
        os.environ["LLM_PROVIDER"] = "mock"
        client = TestClient(app)

        ready = client.get("/ready")
        self.assertEqual(ready.status_code, 503)
        payload = ready.json()
        self.assertEqual(payload["status"], "not_ready")
        self.assertFalse(payload["checks"]["provider"]["ok"])

    def test_audio_upload_exceeding_limit_returns_413(self):
        os.environ["MEDICAL_RECORD_AGENT_MAX_UPLOAD_BYTES"] = "8"
        client = TestClient(app)
        login_as_admin(client)

        response = client.post(
            "/api/audio/upload",
            files={"file": ("too-large.wav", b"0123456789", "audio/wav")},
        )
        self.assertEqual(response.status_code, 413)

    def test_sqlite_backup_and_restore_roundtrip_removes_post_backup_mutation(self):
        db_path = self.root / "source.sqlite3"
        backup_path = self.root / "backups" / "source.backup.sqlite3"
        with closing(sqlite3.connect(db_path)) as connection:
            connection.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY, value TEXT NOT NULL)")
            connection.execute("INSERT INTO sample (value) VALUES ('ok')")
            connection.commit()

        backup_sqlite(db_path, backup_path)
        self.assertTrue(backup_path.exists())
        with closing(sqlite3.connect(db_path)) as connection:
            connection.execute("INSERT INTO sample (value) VALUES ('mutation')")
            connection.commit()

        restore_sqlite(backup_path, db_path, force=True)

        with closing(sqlite3.connect(db_path)) as connection:
            values = [
                row[0]
                for row in connection.execute("SELECT value FROM sample ORDER BY id").fetchall()
            ]
        self.assertEqual(values, ["ok"])


if __name__ == "__main__":
    unittest.main()
